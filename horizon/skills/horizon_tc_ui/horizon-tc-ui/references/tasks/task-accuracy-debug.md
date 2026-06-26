# 精度分析（Accuracy Debug）

## 适用场景

**触发关键词**：精度分析、cosine 低、精度掉点、逐层对比、accuracy debug、层间分析

**前置条件**：
- 已完成一次完整编译并生成 HBM
- 已确认精度不达标（cosine 值低于预期或 consistency 不通过）
- 已有测试输入数据

> **重要**：深度精度分析（逐层 cosine 对比、层间误差传播分析）已 **delegate 到 horizon-model-cosine-analyzer skill**。本文档仅覆盖本地工具链的桥接和分阶段产物保留方法。

## 产出物

| 产物文件 | 路径 | 说明 |
|---------|------|------|
| ONNX 模型 | 用户指定 | 原始浮点模型 |
| HBIR 中间产物 (.bc) | `{working_dir}/{prefix}_*.bc` | 分阶段保留的中间模型 |
| HBM 模型 | `{working_dir}/{prefix}.hbm` | 编译产物 |
| hb_verifier 输出 | 控制台 / 日志 | 一致性 / cosine 对比结果 |
| 逐层分析结果 | delegate 到 horizon-model-cosine-analyzer | 深度精度分析 |

## 步骤

### 步骤 1：使用 hb_verifier 做基础精度验证

hb_verifier 支持对比两种模型的输出一致性：

```bash
# ONNX vs BC 对比（cosine 模式）
hb_verifier -m model.onnx,model_output/model_quantized_model.bc \
  -i input_data.npy

# BC vs HBM 对比（consistency 模式）
hb_verifier -m model_output/model_quantized_model.bc,model_output/model.hbm \
  -i input_data.npy

# ONNX vs ONNX 对比（cosine 模式）
hb_verifier -m model_original.onnx,model_calibrated.onnx \
  -i input_data.npy
```

**多输入模型**：
```bash
hb_verifier -m model_output/model_quantized_model.bc,model_output/model.hbm \
  -i input0.npy -i input1.npy
```

### 步骤 2：使用 --skip-sim / --skip-arm 控制执行阶段

```bash
# 只跑仿真（不跑板端），跳过 ARM 板端推理
hb_verifier -m model_output/model_quantized_model.bc,model_output/model.hbm \
  -i input_data.npy \
  --skip-arm

# 只跑板端，跳过仿真
hb_verifier -m model_output/model_quantized_model.bc,model_output/model.hbm \
  -i input_data.npy \
  --skip-sim \
  --ip 192.168.1.100 -u root -p password --port 22 \
  --remote-root /userdata/
```

> **注意**：`--skip-sim` 和 `--skip-arm` 不能同时指定。

### 步骤 3：调整对比精度

```bash
# 设置对比小数位数（默认 5）
hb_verifier -m model_output/model_quantized_model.bc,model_output/model.hbm \
  -i input_data.npy \
  -c 3
```

### 步骤 4：consistency vs cosine 模式判定

hb_verifier 根据**模型类型组合**自动选择对比模式（源码 `verifier/params_check.py:check_mode()`）：

| 对比模式 | 触发条件（模型组合） | 说明 |
|---------|-------------------|------|
| **consistency** | `bc vs hbm` 或 `hbm vs hbm` | 逐元素对比，使用 `np.allclose`，容忍度由 `compare_digits` 控制 |
| **cosine** | `onnx vs onnx`、`onnx vs bc`、`bc vs bc` | 计算余弦相似度，值越接近 1 越好 |

**consistency 模式输出**：
- `ret`: 是否通过（True/False）
- `mismatched`: 不匹配元素数量和比例（如 `10/1000 (1.00%)`）
- `max_abs_diff`: 最大绝对差异
- `max_rel_diff`: 最大相对差异

**cosine 模式输出**：
- 每个输出 tensor 的余弦相似度值
- 值范围：-1 ~ 1，越接近 1 表示越相似

### 步骤 5：保留分阶段模型用于逐层分析

在 DEBUG 模式下，hb_compile 会保留中间产物：

```bash
# 设置环境变量开启 DEBUG 模式
export HORIZON_TC_UI_DEBUG=1

# 重新编译
hb_compile -c compile_config.yaml
```

DEBUG 模式下会生成以下中间产物：
- `{prefix}_ptq_model.bc` - PTQ 导出后的浮点 HBIR
- `{prefix}_inserted_model.bc` - 插入预处理节点后的 HBIR
- `{prefix}_quantized_model.bc` - 量化后的 HBIR
- `{prefix}_quantized_removed_model.bc` - 移除节点后的 HBIR

使用这些中间产物可以逐阶段验证精度：

```bash
# 验证 export 阶段精度（ONNX vs 浮点 HBIR）
hb_verifier -m model.onnx,model_output/model_ptq_model.bc \
  -i input_data.npy --skip-arm

# 验证 convert 阶段精度（浮点 HBIR vs 量化 HBIR）
hb_verifier -m model_output/model_ptq_model.bc,model_output/model_quantized_model.bc \
  -i input_data.npy --skip-arm

# 验证 compile 阶段精度（量化 HBIR vs HBM）
hb_verifier -m model_output/model_quantized_model.bc,model_output/model.hbm \
  -i input_data.npy --skip-arm
```

### 步骤 6：使用 skip 分阶段编译

```bash
# 只执行 export 阶段
hb_compile -c compile_config.yaml --skip convert

# 执行 export + convert 阶段
hb_compile -c compile_config.yaml --skip compile
```

配合 DEBUG 模式，可以精确定位精度损失发生在哪个阶段。

### 步骤 7：Delegate 到 horizon-model-cosine-analyzer

当需要深度精度分析（逐层 cosine 对比、层间误差传播）时：

> **DELEGATE**: 使用 `horizon-model-cosine-analyzer` skill 进行逐层精度分析。
>
> 前置准备：
> 1. 保留原始 ONNX 模型
> 2. 保留编译生成的 HBM 模型
> 3. 准备测试输入数据（.npy 文件）
> 4. 如有分阶段中间产物（.bc 文件），一并提供

## 校验清单

- [ ] hb_verifier 命令正常执行完成，无报错
- [ ] 输出日志中包含每个 output tensor 的对比结果
- [ ] consistency 模式：`ret` 为 True 或 mismatched 比例在可接受范围
- [ ] cosine 模式：余弦相似度 > 0.99（一般期望值）
- [ ] 分阶段验证时，每个阶段的精度衰减可追踪
- [ ] `--skip-sim` 和 `--skip-arm` 不同时使用
- [ ] 输入数据文件格式正确（仅支持 `.npy`），shape 与模型输入匹配
- [ ] 板端推理时 SSH 连接正常（如使用）

## 常见偏差与修法

| 偏差 | 修法 | 对应 troubleshooting |
|-----|------|---------------------|
| `--skip-sim` 和 `--skip-arm` 同时指定 | 去掉其中一个 | runtime-errors.md |
| 输入数据与模型输入不匹配 | 确认输入 shape 和格式 | runtime-errors.md |
| 模型路径不存在 | 确认模型文件存在且后缀正确 | runtime-errors.md |
| 只支持两个模型对比 | 每次只对比两个模型 | runtime-errors.md |
| cosine 值过低 | 参考 calibration-tuning.md 调整校准参数 | calibration-errors.md |
| consistency 大量不匹配 | 检查 compare_digits 是否过严 | runtime-errors.md |

## 相关工具 / 模块链接

- **hb_verifier**：精度验证工具，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/hb_verifier.py`
- **VerifierComparator**：对比逻辑，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/verifier/comparator.py`
- **VerifierParamsCheck**：参数校验，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/verifier/params_check.py`
- **hb_compile**：分阶段编译 → `task-float-to-hbm.md`
- **Calibration 调优**：→ `task-calibration-tuning.md`
- **板端验证**：→ `task-board-deploy-verify.md`
- **深度精度分析**：delegate 到 `horizon-model-cosine-analyzer` skill
