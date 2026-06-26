---
name: j6-plugin-consistency-debug
description: 当用户遇到 Horizon Plugin PyTorch 训练部署一致性问题（QAT 模型正常但 BC/HBM 掉点、export/convert/compile 阶段精度偏差）时使用。本 skill 引导用户按 qat.pt -> qat.export.pt -> qat.bc -> quantized.bc -> hbm 分段定位问题，并在每个阶段帮助适配工具、分析工具产出物。
---

# J6 Horizon Plugin PyTorch 训练部署一致性问题定位

## 核心原则

训练侧与部署侧不追求比特一致。先用稳定评测精度、可复现 badcase、多帧可视化结果确认问题真实存在，再按 `qat.pt -> qat.export.pt -> qat.bc -> quantized.bc -> hbm / 板端` 分段定位。不要只凭单帧数值差异下结论。

## 执行前门禁

在开始执行任何分析命令、修改脚本或给出结论前，先确认信息是否足够。

### 必需信息

| 信息 | 为什么需要 |
| --- | --- |
| 当前异常现象 | 用来判断优先排查 export、convert 还是 compile / 部署 |
| 已验证正常和异常的产物 | 必须知道哪一段开始掉点 |
| 至少一个稳定可复现 badcase，或可复现实验数据集 | `QuantAnalysis`、逐层对比和敏感度分析都依赖稳定输入 |
| 使用平台 / march | J6E/M 才优先考虑高一致性 QAT 策略 |
| plugin、profiler、hbdk 版本 | 部分接口和一致性策略有版本前提 |

**compile / 板端问题时额外必需：**

| 信息 | 为什么需要 |
| --- | --- |
| 输入输出前后处理、layout、部署适配说明 | compile / 板端问题经常来自用户侧适配差异 |

如果上述信息缺失且会影响下一步判断，先反问用户。不要在缺少 badcase、模型阶段结果或平台信息时直接跑完整链路或武断归因。

### 推荐信息

- `qat.pt` / QAT 模型、`qat.export.pt`、`qat.bc`、`quantized.bc`、`hbm` 的可用路径。
- `example_inputs` 或构造方式。
- 评测脚本、后处理脚本、板端推理脚本。
- `model_check_result.txt`、`fx_graph.txt`、`compare_per_layer_out.txt`、`output_xxx_sensitive_ops.txt/.pt`。
- 用户已经尝试过的修复或规避方式。

## 先判断问题落在哪一段

**这是最关键的一步。** 错误的阶段判断会导致后续所有分析方向偏离。请严格按下面的现象-阶段映射表定位，不要凭直觉跳过。

| 现象 | 优先阶段 | 下一步 |
| --- | --- | --- |
| `qat.pt` 正常，`qat.bc` 异常 | export | 先看 `qat.export.pt` 是否已异常，再比较 `qat.export.pt` 与 `qat.bc` |
| `qat.export.pt` 已异常 | pre_export / 查表转定点 | 用 `QuantAnalysis(qat_pt, qat_export_pt, "pre_export")` 定位 LUT / 图改写误差 |
| `qat.export.pt` 正常，`qat.bc` 异常 | export / HBIR 表达 | 用 `QuantAnalysis(qat_export_pt, qat_bc, "export")` 定位导出差异 |
| `qat.bc` 正常，`quantized.bc` 异常 | convert | 用 `QuantAnalysis(qat_bc, quantized_bc, "convert")` 做 badcase 和逐层对比 |
| `quantized.bc` 正常，`hbm` 或板端异常 | compile / 部署适配 | 优先检查输入输出、插入节点、前后处理、layout、padding、板端接入 |
| 不确定从哪开始 | 基线确认 | 先验证 `quantized.bc` 精度，再决定是否继续看 compile / 板端 |

## 正确 API 用法

### fake quant 状态

普通导出和一致性分析前，QAT 模型应处于 eval + validation 状态：

```python
from horizon_plugin_pytorch.quantization import FakeQuantState, set_fake_quantize

qat_pt.eval()
set_fake_quantize(qat_pt, FakeQuantState.VALIDATION)
```

`FakeQuantState._FLOAT` 只适合作为诊断手段，用来关闭伪量化验证 bc 推理流程或输入输出适配是否明显有问题；不要把它当成正常导出状态。

### export 与 pre_export

```python
from horizon_plugin_pytorch.quantization.hbdk4 import export, pre_export

qat_pt.eval()
set_fake_quantize(qat_pt, FakeQuantState.VALIDATION)
qat_export_pt = pre_export(qat_pt)
qat_bc = export(qat_pt, example_inputs)
```

`pre_export(model, inplace=False)` 会复制模型并执行 export 中的非等价转换，当前主要包括 Segment LUT 转换；它会检查模型处于 eval 且 observer 关闭。若这里报状态错误，先修模型状态，不要绕过检查。

### convert

`convert` 来自 `hbdk4.compiler`，不是 `horizon_plugin_pytorch.quantization.hbdk4`：

```python
from hbdk4.compiler import convert

quantized_bc = convert(qat_bc, march)
```

### QuantAnalysis

```python
from horizon_plugin_profiler import QuantAnalysis
```

支持的 `analysis_model_type`：

| 类型 | 基线模型 | 分析模型 | 说明 |
| --- | --- | --- | --- |
| `"fake_quant"` | float 模型 | calibration / QAT 模型 | 量化总体影响 |
| `"pre_export"` | calibration / QAT 模型 | `pre_export(qat_model)` | 查表转定点误差 |
| `"export"` | `qat.export.pt` | `qat.bc`（HBIR） | 导出 / HBIR 表达差异 |
| `"convert"` | `qat.bc` / `qat.export.pt` | `quantized.bc` | convert 差异 |

完整流程：

```python
qa = QuantAnalysis(
    baseline_model,
    analysis_model,
    analysis_model_type,
    out_dir="./horizon_quant_analysis",  # 可自定义输出目录
)
qa.auto_find_bad_case(dataloader)
qa.run()
qa.compare_per_layer()
qa.sensitivity()
```

当 torch 模型与 bc 模型不能接受同一格式输入时，允许分开跑两侧 profiler，但两边输入除格式外内容必须一致：

```python
qa.set_bad_case(pt_badcase)
qa.run(run_baseline_model=True, run_analysis_model=False)
qa.set_bad_case(bc_badcase)
qa.run(run_baseline_model=False, run_analysis_model=True)
qa.compare_per_layer()
```

`run()` 必须在 `auto_find_bad_case()`、`set_bad_case()` 或 `load_bad_case()` 之后执行，否则没有可回放输入。

### J6E/M 高一致性 QAT 策略

仅当问题主要表现为 convert 或部署阶段偏差，并且平台是 J6E/M 时，才优先考虑：

```python
from horizon_plugin_pytorch.qat_mode import ConsistencyStrategy

# 必须在 prepare 之前设置
ConsistencyStrategy.set_consistency_level(1)
qat_pt = prepare(float_model)
```

使用前提和注意事项：

- `hbdk4_compiler >= 4.4.2`，参考资料中建议 plugin 不低于 `3.1.2`。
- level 0：统计型 scale + high precision qpp + 关闭 requantize fuse，适合不重训的补救评估。
- level 1：activation 使用 POT scale，开启 resize / gridsample / mean / mod_centered 高一致性路径，推荐作为 J6E/M convert 一致性问题的起点。
- level 2：activation / weight 都使用 POT scale，在 level 1 仍不足时再尝试。
- level 1 / level 2 应在设置后重新训练；不要直接套到已有 checkpoint 后声称有效。
- 高一致性策略主要影响 convert / 部署一致性，对 pre_export 查表转定点问题没有直接帮助。

---

## 分阶段排查流程与工具适配

### 0. 先排除明显用户侧问题

1. 确认模型版本、checkpoint、qconfig、march 一致。
2. 确认前后处理、后处理、输入 layout、归一化、padding、NCHW/NHWC、量化输入 scale 一致。
3. 用小数据集在 CPU 上比较 `qat.export.pt` 与 `qat.bc`，先验证 bc 推理流程。
4. 如果比较失败，可临时关闭伪量化再验证：

```python
qat_pt.eval()
set_fake_quantize(qat_pt, FakeQuantState._FLOAT)
qat_bc = export(qat_pt, example_inputs)
qat_export_pt = pre_export(qat_pt)
```

关闭伪量化后一致，优先检查 validation 状态是否设置正确。关闭伪量化后仍不一致，继续逐层对比 `qat.export.pt` 与 `qat.bc`。

### 1. Export / pre_export 问题

适用：`qat.pt` 正常，但 `qat.bc` 异常。

#### 适配工具

仅使用 QuantAnalysis，根据 `qat.export.pt` 是否异常选择对应的 `analysis_model_type`：

| `analysis_model_type` | 基线模型 | 分析模型 | 何时使用 |
| --- | --- | --- | --- |
| `"pre_export"` | QAT 模型 | `qat.export.pt` | `qat.export.pt` 异常时 |
| `"export"` | `qat.export.pt` | `qat.bc` | `qat.export.pt` 正常但 `qat.bc` 异常时 |

#### 执行步骤

1. 生成并评测 `qat.export.pt`。
2. 如果 `qat.export.pt` 异常，定位查表转定点或 pre_export 图改写：

```python
qa = QuantAnalysis(qat_pt, qat_export_pt, "pre_export", out_dir="./qa_pre_export")
qa.auto_find_bad_case(dataloader)
qa.run()
qa.compare_per_layer()
qa.sensitivity()
```

3. 如果 `qat.export.pt` 正常但 `qat.bc` 异常，比较 `qat.export.pt` 与 `qat.bc`：

```python
qa = QuantAnalysis(qat_export_pt, qat_bc, "export", out_dir="./qa_export")
qa.set_bad_case(badcase)
qa.run()
qa.compare_per_layer()
qa.sensitivity()
```

4. 如果怀疑图结构不一致，查看 `fx_graph.txt` 和 `model_check_result.txt`；存在 `if deploy`、动态分支、循环次数变化时尤其要检查。
5. 常规逐层仍无法缩小范围时，可对局部模块执行 `pre_export` 做分段定位：

```python
qat_pt.module_a = pre_export(qat_pt.module_a)
```

#### 产出物分析

##### `compare_per_layer` 产出

| 文件 | 格式 | 内容与解读 |
| --- | --- | --- |
| `compare_per_layer_out.txt` | psql 表格 | 每层对比：mod_name, base_op_type, analy_op_type, shape, dtype, qscale, L1, COSINE, ATOL, max_qscale_diff, base/analy_model_min/max/mean, advice |
| `compare_per_layer_out.csv` | CSV | 同上，便于脚本处理 |

**解读要点：**
- 优先查看 `compare_per_layer_out.csv`，关注 **COSINE 骤降** 或 **ATOL 骤增** 的层 → 误差起点

##### `sensitivity` 产出

一致性问题排查使用 v1 sensitivity（ablation 方法），每层一行，指标值即为该层单独开启 fake quant 时的输出误差。

| 文件 | 格式 | 内容与解读 |
| --- | --- | --- |
| `output_{name}_case_{n}_{metric}_sensitive_ops.txt` | psql 表格 | 每层敏感度排序表 |

**v1 表格列解读：**
- `op_name` → 模块限定名
- `op_type` → 模块类型
- `{metric}` → 该层单独开启 fake quant 时的输出误差（默认 ATOL）
- 表格按指标值降序排列，排在最前面的层即为最敏感层

**解读要点：**
- 指标值远大于其他层的 → 该层是精度损失的主要贡献者
- 多个层指标值接近 → 可能是累积效应，需结合 `compare_per_layer` 找误差起点
- 与 `compare_per_layer` 结合看：`compare_per_layer` 找误差扩散起点，`sensitivity` 量化各层独立贡献

##### `auto_find_bad_case` 产出

| 文件 | 格式 | 内容与解读 |
| --- | --- | --- |
| `badcase.txt` | 文本 | 三段式报告：(1) 每个 output 的最差数据索引 (2) 每个 output 的最差指标值 (3) 整体最差 output |
| `all_badcase_info.pt` | PT | 序列化的 BadCaseReport，供后续 `load_bad_case` 加载 |
| `badcase_report.html` | HTML | 各指标/输出组合的直方图和百分位图 |

**解读要点：**
- 如果不同 output 的最差索引不同，说明误差分布在多个输入样本上
- 直方图分布过于离散 → 输入分布可能有问题或量化参数不稳定
- 用 `load_bad_case()` 直接加载，不需重复搜索

### 2. Convert 问题

适用：`qat.bc` 正常，但 `quantized.bc` 异常。

#### 适配工具

| 工具 | 用途 | 何时使用 |
| --- | --- | --- |
| `QuantAnalysis(..., "convert")` | 定位 convert 逐层差异 | 标准排查路径 |
| `bc_editor`（QatBcEditor） | 删除指定 fake quant 重新 convert 定位 | 逐层无法缩小范围时 |
| `ConsistencyStrategy` | 评估高一致性策略 | J6E/M 平台 convert 偏差时 |

#### 执行步骤

1. 确认 `quantized.bc` 掉点稳定可复现。
2. 用同一套输入和后处理比较 `qat.bc` 与 `quantized.bc`：

```python
qa = QuantAnalysis(qat_bc, quantized_bc, "convert", out_dir="./qa_convert")
qa.auto_find_bad_case(dataloader)
qa.run()
qa.compare_per_layer()
```

3. 基于同一 badcase，再结合 `qat.export.pt` 做敏感度分析：

```python
qa = QuantAnalysis(qat_export_pt, quantized_bc, "convert", out_dir="./qa_convert_sens")
qa.load_bad_case()  # 默认读取 out_dir/all_badcase_info.pt
qa.sensitivity()
```

4. 若仍无法定位，考虑 `bc_editor`：

```python
from horizon_plugin_profiler.bc_editor.bc_editor import QatBcEditor

# 先查看 bc 中的 HBIR 结构
asm_info = qat_bc.module.get_asm(enable_debug_info=True)
# 找到可疑 fake quant 的 HBIR 编号范围

# 编写配置，删除指定 HBIR 编号的 fake quant
# config.json 示例：删除编号 1-100 和 102 的 fake quant
# {
#     "remove_fake_quant": [[1, 100], 102]
# }

editor = QatBcEditor(
    bc_path="qat.bc",
    config_path="config.json",
    new_bc_path="qat_modified.bc"
)
editor.run()

# 然后 convert 编辑后的 bc，对比表现
quantized_modified_bc = convert(qat_modified_bc, march)
```

5. J6E/M 平台 convert 偏差，评估高一致性策略（按优先级递进）：

```python
# Level 0：不重训的补救评估
ConsistencyStrategy.set_consistency_level(0)
# 等价于：STATISTIC scale + high precision qpp + 关闭 requantize fuse

# Level 1：推荐起点（需重新训练）
ConsistencyStrategy.set_consistency_level(1)
# 等价于：A_POT scale + 高一致性 resize/gridsample/mean/mod_centered

# Level 2：加强方案（需重新训练）
ConsistencyStrategy.set_consistency_level(2)
# 等价于：POT scale（activation + weight）+ 所有高一致性路径
```

#### 产出物分析

`compare_per_layer` 和 `badcase` 产出格式与 Export 阶段相同，解读方法一致。

convert 阶段的特殊关注点：
- **多个连续层 COSINE 逐步衰减** → 误差在逐步累积，源头更靠前
- **单层 COSINE 骤降** → 该层是主误差源，关注其算子类型和量化参数

### 3. Compile / 部署问题

适用：`quantized.bc` 正常，但 `hbm`、x86 hbm 仿真或板端结果异常。

**重要：Compile / 部署问题不适用 QuantAnalysis 工具。** QuantAnalysis 仅用于 pre_export、export、convert 三个阶段的一致性对比，compile/部署阶段的误差来源是配置、输入适配、前后处理等部署侧问题，不是算子量化一致性差异，因此不应为 compile/部署问题适配 QuantAnalysis。

#### 必须先完成的部署侧排查清单

在分析具体算子或代码之前，**必须逐一检查**以下部署侧常见适配问题，并在报告中列举检查结果。即使后续通过代码审查找到了根因，这份清单也不可跳过——它帮助排除共存的其他问题，也避免遗漏真正来源。

| 检查项 | 关注点 |
| --- | --- |
| 输入预处理 | 归一化方式、通道顺序（RGB/BGR）、resize 插值是否与训练一致 |
| layout | NCHW / NHWC 转换是否正确 |
| 量化输入 scale | 板端输入 scale 与 QAT 校准时是否一致 |
| 前后处理 | 首尾节点的删除/插入是否正确，后处理 decode 是否一致 |
| padding / 对齐 | 模型输入 padding 策略是否与训练时一致 |

#### x86 仿真与板端异常的对比分析

当 x86 hbm 仿真和板端结果**均异常**时，说明问题不在板端特有的硬件行为，而更可能在 compile 配置或输入适配层面。报告应明确指出这一推断：
- x86 仿真正常 + 板端异常 → 优先怀疑板端部署接入、数据准备差异
- x86 仿真 + 板端均异常 → 问题在 compile 配置或输入适配（两者共用同一 hbm 和 compile 流程，一致异常排除了板端独有因素）

#### 执行步骤

1. 先确认 `quantized.bc` 自身正常；若异常，返回 convert 一致性问题排查路径。
2. 区分是 hbm 仿真异常，还是仅板端接入异常，并根据上述对比分析推断问题来源。
3. **逐一检查部署侧排查清单中的每一项**，在报告中列举结果。
4. 检查 compile 配置、输入输出定义、插入节点、删除首尾节点。
5. 保留 hbm、compile 配置、板端输入输出 dump、日志和 badcase。

## 需要保留给支持或继续分析的产物

### Export / pre_export

- `qat.pt`、`qat.export.pt`、`qat.bc`
- `example_inputs` / badcase
- `model_check_result.txt`、`fx_graph.txt`
- `compare_per_layer_out.{txt,csv}`
- `output_xxx_sensitive_ops.txt`
- `badcase.txt`、`all_badcase_info.pt`

### Convert

- `qat.bc`、`quantized.bc`、`qat.export.pt`
- badcase 或可复现实验数据
- `compare_per_layer_out.{txt,csv}`
- `output_xxx_sensitive_ops.txt`
- 如使用 `bc_editor`，保留配置文件和编辑后的 bc

### Compile / 板端

- `quantized.bc`、`hbm`
- compile 配置
- x86 / 板端输入输出 dump
- 前后处理脚本、部署脚本和日志
- 可复现 badcase

## 输出报告模板

每次定位结束，按下面结构输出，避免只给零散命令：

```markdown
## 结论摘要
- 当前最可能阶段：export / pre_export / convert / compile / 用户侧适配 / 暂不能判断
- 证据：列出支持该判断的评测结果、badcase、逐层或敏感度产物

## 已确认事实
- 正常产物：...
- 异常产物：...
- 平台 / 版本：...
- badcase：...

## 执行过的检查
1. ...

## 关键发现
- 第一个明显异常层 / 算子：...
- 指标：Cosine / L1 / Atol / qscale / range ...
- 误差来源分析：requantize / 查表近似 / 输入输出适配 / 图结构差异 / 其他 ...
- 已应用的修复策略及效果：...
- QuantAnalysis 产出物摘要：列出 compare_per_layer 中 COSINE 骤降或 ATOL 骤增的层、sensitivity 中最敏感的层（compile / 部署问题写"不适用"）

## 下一步建议
- 最小可验证动作：...
- 需要用户补充的信息或产物：...

## 需要保留的产物
- ...
```

如果证据不足，明确写"暂不能判断"，并列出最少需要补充的输入；不要为了完成报告而猜测根因。

## 常见误区

| 误区 | 正确做法 |
| --- | --- |
| 单帧输出不一致就判定工具 bug | 用数据集精度、稳定 badcase、多帧可视化确认 |
| `quantized.bc` 未验证就归因 compile / 板端 | 先验证 `quantized.bc`，异常则回到 convert |
| export 异常时直接看 `qat.pt` vs `qat.bc` | 先插入 `qat.export.pt`，拆出 pre_export / 查表阶段 |
| 忽略 fake quant / observer 状态 | 导出前确保 eval + `FakeQuantState.VALIDATION` |
| torch 和 bc 输入格式不同却直接比较 | 分开跑两侧 profiler，但保证内容一致 |
| 看到最差层就当根因层 | 找误差起点，结合 sensitivity 分析 |
| J6E/M convert 掉点直接上 level 2 | 先评估 level 0；再评估 level 1；level 2 是加强方案 |
| 对 pre_export 查表问题使用高一致性策略 | 高一致性策略主要改善 convert 偏差 |
| 只产出 compare_per_layer 不看 sensitivity | compare_per_layer 看累积误差，sensitivity 看单算子贡献，需结合 |
| compile / 部署问题却用 QuantAnalysis 分析 | compile / 部署问题应按部署侧排查清单逐项检查，QuantAnalysis 不适用此阶段 |
| level 1/2 设置后直接套用已有 checkpoint | level 1 / level 2 必须重新训练，不能直接套用到已有 checkpoint |
