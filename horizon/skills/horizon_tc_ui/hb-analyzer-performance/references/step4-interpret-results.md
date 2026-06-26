# 第 4 步：解读报告

读取生成的文件并提取关键性能指标。

## 主要数据源

### 1. analysis_summary.json

这是最重要的数据文件，包含所有性能指标。

**读取方式**：
```bash
cat .hb_analyzer/analysis_summary.json
```

### 2. hb_analyzer_report.html

交互式 HTML 报告，建议用户在浏览器中打开查看。

## 关键指标解读

### A. 延时（Latency）

**位置**：`perf_json_data.summary.performance["latency (us)"]`

**含义**：模型单次推理耗时（微秒）

**示例输出**：
- "模型总延时：15.2 ms"
- "推理速度：65.8 FPS"

### B. DDR 带宽

**位置**：`hbm_ddr_bytes_per_run`

**含义**：每次推理的 DDR 数据传输量

**示例输出**：
- "DDR 带宽：120 MB/run"
- "带宽效率：中等"

### C. 算子耗时分布

**位置**：`hbm_op_time_by_type`

**含义**：不同算子类型的时间占比

**重点关注**：
- Conv2D 耗时
- CPU 算子耗时（应尽量少）
- 最耗时的算子类型

**示例输出**：
- "Conv2D 占总时间 65%"
- "检测到 3 个 CPU 算子，占 8% 时间"

### D. 瓶颈层

**位置**：`hbm_top_layers_by_total_time`

**含义**：耗时最长的层

**示例输出**：
- "瓶颈层：layer_23 (Conv2D)，耗时 3.2ms"
- "Top 3 耗时层占总时间 45%"

### E. BPU vs CPU

**位置**：`bc_quantized_model_cpu_ops`

**含义**：哪些算子在 CPU 上运行

**重要性**：CPU 算子会降低性能，应尽量避免

**示例输出**：
- "所有算子均在 BPU 运行 ✓"
- "发现 2 个 CPU 算子：Resize, Softmax"

### F. Block 级深度分析（进阶）

`hbm_op_time_by_type` 只给出算子类型的聚合时间，但 BPU 会将复合算子（如 softmax、LayerNorm、attention）分解为多个底层子操作，每个子操作对应 `hbm_block_time` 中的一个 block。仅看算子类型聚合可能误判瓶颈。

**位置**：`hbm_block_time`（每个 block 的 `block` 命名遵循 `<模块路径>.<子操作>` 格式）

#### 为什么要做 block 级分析

- `hbm_op_time_by_type` 中 `torch.matmul` 可能显示为最大算子
- 但 `hbm_block_time` 中 softmax 的 exp/sub/mul/sum/reciprocal 等子操作分散在多个 block 中，合计可能超过 matmul
- 类似的，LayerNorm 的 mean/var/rsqrt/mul/add 也会分散

#### 分析方法

1. **按命名前缀聚合 block**：

   将 `hbm_block_time` 中的 block 按逻辑算子前缀分组并求和：

   ```python
   # 按逻辑算子前缀聚合
   from collections import defaultdict
   groups = defaultdict(lambda: {"count": 0, "total_us": 0})
   for b in hbm_block_time:
       name = b["block"]
       # 提取逻辑算子前缀（如 "encoder.0.attn"）
       prefix = extract_logical_prefix(name)
       groups[prefix]["count"] += 1
       groups[prefix]["total_us"] += b["total_time_us"]
   # 按合计耗时降序排列
   sorted_groups = sorted(groups.items(), key=lambda x: -x[1]["total_us"])
   ```

2. **识别常见的复合算子分解模式**：

   | 复合算子 | BPU 上常见的子操作 block 命名关键词 |
   |----------|-------------------------------------|
   | softmax | `.softmax.exp`, `.softmax.sub`, `.softmax.mul`, `.softmax.sum`, `.softmax.reciprocal` |
   | LayerNorm | `.norm.mean`, `.norm.var`, `.norm.rsqrt`, `.norm.mul`, `.norm.add` |
   | Attention | `.attn.matmul`, `.attn.attn_matmul`, `.attn.softmax.*`, `.attn.mask_add` |
   | GELU/SiLU | `.act.mul`, `.act.sigmoid` / `.act.erf` |

3. **对比聚合结果与 `hbm_op_time_by_type`**：

   将聚合后的复合算子耗时与算子类型聚合表对比，确保瓶颈排序准确。如果某个复合算子的聚合耗时显著高于 `hbm_op_time_by_type` 中任何单一算子类型，说明该复合算子才是真正瓶颈。

#### 输出示例

```
Block 级瓶颈分析（按逻辑算子聚合 hbm_block_time）：

1. Attention 模块（encoder.0-7）: 38,647 us (51.2%)
   - attn_matmul: 14,562 us (8 层 x ~1,820 us)
   - softmax 子操作合计: 19,580 us  <-- 实际最大瓶颈
     (exp: 5,603 us, sub: 3,045 us, mul: 3,050 us, sum: 3,343 us, ...)
   - mask_add: 3,344 us
   - matmul (attn x V): 4,325 us
2. Conv2D（backbone）: 27,897 us (37.0%)
3. Linear 层: 13,700 us (18.2%)
```

### G. 输入/输出 dtype 审计（补充）

检查模型**边界**（输入/输出）的 dtype 分布。这只是量化精度审计的补充部分——**核心分析见 §I（MAC 计算精度分布）**，那里决定了 BPU 内部计算的实际精度。

**数据源**：
- `bc_model_info.quantized_model_inputs` — 每个输入张量的 name、shape、dtype
- `bc_model_info.quantized_model_outputs` — 每个输出张量的 name、shape、dtype

**注意**：输入 dtype 中的 float32/float16 影响的是 DDR 带宽（数据搬运量），而非 BPU 计算吞吐量。很多 float32 输入是小张量（坐标矩阵、标量属性），对总体带宽影响有限。真正决定 BPU 计算效率的是 §I 中的 int16 vs int8 MAC 比例。

#### 分析方法

1. **统计 dtype 分布**：

   ```python
   dtype_counts = {}
   for inp in bc_model_info["quantized_model_inputs"]:
       dt = inp.get("dtype", "unknown")
       dtype_counts[dt] = dtype_counts.get(dt, 0) + 1
   ```

2. **评估高精度输入占比**：

   将 float32 和 float16 视为高精度类型，**int8 视为量化类型**（注意：int16 不属于量化类型，见 §I）。

   | 高精度输入占比 | 评估 | 建议 |
   |--------------|------|------|
   | < 20% | 量化充分 | 无需调整 |
   | 20%-50% | 部分高精度 | 检查是否有可量化的输入 |
   | > 50% | 大量高精度 | 应审查量化配置，有较大优化空间 |

3. **关联带宽分析**：

   如果高精度输入占比高 **且** `hbm_ddr_bytes_per_run` 偏高，应在报告中建议用户审查非关键输入的量化配置。**但务必同时执行 §I 的 MAC 精度分析**，那才是影响 BPU 计算效率的关键。

#### 输出示例

```
输入/输出 dtype 审计（补充）：
- 模型输入：33 个（float32: 27, float16: 3, int8: 3）
- 高精度输入占比：91% (30/33)
- 注：大部分 float32 输入为小张量（3x3 矩阵、标量），带宽影响有限
- 核心分析见 MAC 精度分布（§I）
```

### H. 模型结构与硬件匹配分析（进阶）

从 block 命名和模型 shape 信息推断模型结构参数，检查是否满足 BPU 硬件的对齐要求。

**数据源**：
- `hbm_block_time` 的 block 命名（包含模块路径，可推断层数、结构）
- `hbm_model_info.hbm_model_inputs/outputs` 的 shape 信息

#### 从 block 命名推断结构

block 命名中的序号可以推断模型层数：
- `encoder.0` ~ `encoder.7` 出现 → 8 层 Transformer Encoder
- `decoder.layer.0` ~ `decoder.layer.5` → 6 层 Decoder
- `backbone.stage.0` ~ `backbone.stage.3` → 4 个 Stage

#### BPU Nash 系列硬件对齐规则

| 维度 | 对齐要求 | 影响的算子 | 不满足时的影响 |
|------|---------|-----------|--------------|
| Channel | 16 对齐 | Conv2D, Linear | padding 计算浪费，利用率下降 |
| Head Dim | 64 对齐 | Multi-Head Attention | padding 开销大，可能降级到标量计算 |
| Sequence Length | 无硬性要求，128 的倍数更优 | Attention | 硬件利用率低 |

#### 分析方法

1. 从 block 命名推断 num_heads、num_layers 等参数
2. 从 `hbm_model_inputs` 的 shape 推断 embed_dim、head_dim 等
3. 检查关键维度是否满足对齐要求
4. 如果不满足，在报告中给出调整建议

#### 输出示例

```
模型结构与硬件匹配分析：
- Transformer 层数：8 层（从 encoder.0-7 推断）
- Attention 结构：Multi-Head Self-Attention
- 推断参数：embed_dim=384, num_heads=8, head_dim=48
- 硬件对齐检查：head_dim=48 不满足 64 对齐

建议：
- 当前 head_dim=48 不满足 BPU 的 64 对齐要求
- 方案 A：减少 head 数量到 6, head_dim=64
- 方案 B：调整 embed_dim 到 512, head_dim=64
```

### I. MAC 计算精度分布分析（核心）

检查模型**内部计算**的精度分布。**这是量化精度审计的核心**——§G 只分析模型边界的输入/输出 dtype，本节分析模型内部的实际计算精度，后者直接决定 BPU 计算吞吐量。

在 BPU 上，**int8 是最高效的计算精度**。如果模型大量使用 int16 feature（feature int16 + weight int8），会显著降低 BPU 计算吞吐量。**注意：fp16 是 J6P 等 Nash 系列平台的默认精度，不应被单独识别为"高精度配置问题"。**

**数据源**：

hb_analyzer 产出的原始 perf JSON 文件（位于 `.hb_analyzer/` 目录下，文件名随模型变化）中的 `summary` → `model info` 部分。

**读取方式**：

```bash
# 在 .hb_analyzer/ 目录下找到 perf JSON 文件
ls .hb_analyzer/*.json
# 读取 model info 中的 MAC 精度统计
cat .hb_analyzer/<perf_json_file> | python3 -c "
import json, sys
data = json.load(sys.stdin)
mi = data['summary']['model info']
for k, v in mi.items():
    if 'mac' in k.lower() or 'int' in k.lower():
        print(f'{k}: {v:,}' if isinstance(v, int) else f'{k}: {v}')
"
```

**关键字段**：

| 字段 | 含义 | 理想情况 |
|------|------|---------|
| `double int16 macs` | feature 和 weight 均为 int16 的 MACs | 应尽量为 0 |
| `feature int16 weight int8 macs` | feature 为 int16、weight 为 int8 的 MACs | 应尽量低 |
| `feature int8 weight int16 macs` | feature 为 int8、weight 为 int16 的 MACs | 应尽量低 |
| `double int8 macs` | feature 和 weight 均为 int8 的 MACs | 应尽量高 |
| `original conv ops` | 原始卷积操作总数 | 参考值 |

#### 分析方法

1. **计算 int16 占比**：

   ```python
   double_int16 = mi["double int16 macs"]
   feat_int16_w_int8 = mi["feature int16 weight int8 macs"]
   feat_int8_w_int16 = mi["feature int8 weight int16 macs"]
   double_int8 = mi["double int8 macs"]

   total_macs = double_int16 + feat_int16_w_int8 + feat_int8_w_int16 + double_int8
   int16_macs = double_int16 + feat_int16_w_int8 + feat_int8_w_int16
   int16_ratio = int16_macs / total_macs * 100
   ```

2. **评估 int16 占比**：

   | int16 MACs 占比 | 评估 | 建议 |
   |----------------|------|------|
   | < 10% | 量化充分 | 无需调整 |
   | 10%-30% | 部分 int16 | 检查是否有可降级的层 |
   | > 30% | 大量 int16 | 应审查量化配置，有较大优化空间 |

3. **区分"输入高精度"和"内部计算高精度"**：

   - **内部计算高精度**（本节，核心）：模型内部卷积/线性层的 int16 feature。直接决定 BPU 计算吞吐量。
   - **输入高精度**（§G，补充）：模型输入/输出的 float32/float16 dtype。通常是小张量（坐标矩阵、标量属性），对带宽影响可能有限。

   在报告中应**优先报告内部计算精度（MAC 分布）**，输入 dtype 作为补充。

#### 输出示例

```
MAC 计算精度分布分析（核心）：
- double int8 MACs: 64,862,337,024 (16.7%)
- feature int16 + weight int8 MACs: 322,634,117,632 (83.3%)
- double int16 MACs: 1,827,840 (<0.1%)
- int16 相关 MACs 占比: 83.3%  <-- 偏高

分析：模型 83.3% 的内部计算使用了 int16 feature 精度，
仅 16.7% 使用了 BPU 最高效的 double int8。int16 会显著
降低 BPU 计算吞吐量。

建议：审查量化配置文件（qconfig），将更多层的 feature
从 int16 降级为 int8，降低 int16 计算比例。
```

## 输出格式

向用户总结时，使用清晰的格式：

```
性能分析结果：

总体性能
- 延时：15.2 ms
- 吞吐：65.8 FPS
- DDR 带宽：120 MB/run

算子分布
- Conv2D：65% (9.8ms)
- BPU 利用率：92%
- CPU 算子：2 个 (8%)

瓶颈识别
- 最慢层：layer_23 (Conv2D, 3.2ms)
- 建议优化：[见第 5 步]

Block 级深度分析（当模型含 Transformer/Attention 或延时不达标时必须输出）
- Attention 模块聚合耗时：38.6 ms (51%)
  - softmax 子操作合计：19.6 ms  <-- 真正瓶颈
  - matmul 合计：18.9 ms
- 建议：审查 softmax 的计算图优化空间

量化精度审计（必须输出，核心为 MAC 精度，§G 输入 dtype 为补充）
- MAC 精度分布（核心）：
  - double int8 MACs: 64.9B (16.7%)
  - feature int16 MACs: 322.6B (83.3%)
  - int16 占比: 83.3%  <-- 偏高
  - 建议：将更多层的 feature 从 int16 降级为 int8
- 输入 dtype 分布（补充）：float32: 27, float16: 3, int8: 3
  - 注：大部分 float32 输入为小张量，带宽影响有限

硬件匹配分析（当发现对齐问题时必须输出）
- head_dim=48，不满足 BPU 64 对齐
- 建议：调整 head 数量或 embed_dim
```

完成解读后，进入第 5 步提供优化建议。