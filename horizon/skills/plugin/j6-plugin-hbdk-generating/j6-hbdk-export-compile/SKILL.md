---
name: j6-hbdk-export-compile
description: 为量化后的模型生成导出编译流程代码（export QAT BC → convert → remove_io_op → statistics 检查 CPU 算子 → compile HBM）。务必在用户提到导出编译、HBM 编译、模型部署编译、QAT BC 导出、remove_io_op、CPU 算子检查、模型编译部署、HBM 生成时触发此 skill，即使用户只提到其中一个步骤，只要涉及从 QAT BC 到 HBM 的任何环节都应触发。
---

# 基础结构导出编译流程代码生成

## 目标

将校准或 QAT 训练后的模型导出并编译为可部署的 HBM 文件。本 Skill 接收量化流程产出的模型（`calib_net` 或 `qat_net`），完成从 export 到编译的全部流程。

本 Skill 覆盖的流程：

```
export QAT BC → convert → remove_io_op → statistics → compile HBM
```

## 前置条件

本 Skill 依赖 `j6-plugin-quantization` skill 的输出：
- 校准后或 QAT 训练后的模型（`calib_net` 或 `qat_net`）
- 示例输入（`example_input`）
- 目标平台 march

## 导入

```python
from horizon_plugin_pytorch.quantization.hbdk4 import export
from hbdk4.compiler import convert, compile, statistics, save
```

**导入路径严禁违反以下规则：**

1. **`export` 必须从 `horizon_plugin_pytorch.quantization.hbdk4` 导入。** 不得从 `horizon_plugin_pytorch.quantization` 或 `horizon_plugin_pytorch` 导入。
2. **`convert, compile, statistics, save` 必须全部从 `hbdk4.compiler` 导入。** 不得从 `horizon_plugin_pytorch.quantization` 或任何其他模块路径导入。
3. 不得使用其他导入路径替代上述路径。

**注意：** 当本 sub-skill 作为 `j6-plugin-hbdk-generating`（编排型 skill）的一部分被调用时，导入语句必须与量化子 skill 的导入合并到文件顶部的一个统一导入块中，格式严格遵循 `references/full-pipeline-template.md`。

## Step 1: 导出 QAT BC

将量化模型导出为 BC 格式。先切换到 VALIDATION 状态，验证推理正常后再 export：

```python
# model 为 calib_net 或 qat_net
model.eval()
set_fake_quantize(model, FakeQuantState.VALIDATION)

# 验证量化模型在 VALIDATION 状态下推理正常
with torch.no_grad():
    model(example_input)

qat_bc = export(model, example_input)
```

## Step 2: Convert — 转换为量化模型

将 QAT BC 转换为目标平台专用的量化模型：

```python
quantized_model = convert(qat_bc, march)
save(quantized_model, "quantized.bc")
```

**convert 调用严禁违反以下规则：**

1. **`march` 参数不可省略。** 必须写成 `convert(qat_bc, march)`，禁止写成 `convert(qat_bc)` 或 `convert(exported_model)`。

## Step 3: Remove IO Op — 删除首尾 Quantize/Dequantize 算子

部署时输入输出不需要首尾的量化/反量化节点，必须删除。不删除会导致模型在 BPU 上无法正确运行：

```python
func = quantized_model.functions[0]
func.remove_io_op(op_types=["Dequantize", "Quantize"])
save(quantized_model, "quantized_remove.bc")
```

**remove_io_op 调用严禁违反以下规则：**

1. **必须先取 `quantized_model.functions[0]` 得到 func，再对 func 调用 `remove_io_op`。** 禁止直接对 `quantized_model` 调用 `remove_io_op()`（即 `converted_model.remove_io_op()` 是错误写法）。
2. **必须指定 `op_types=["Dequantize", "Quantize"]` 参数。** 禁止省略 `op_types` 写成 `func.remove_io_op()`，不指定 op_types 可能删除错误节点。
3. **remove_io_op 之后必须 `save`。** 保存 remove_io_op 后的 BC 文件，便于对比和排查。

## Step 4: Statistics — 检查 CPU 算子

如果模型中存在 CPU 算子（hbtl），说明有算子无法在 BPU 上运行，编译会失败或运行时回退 CPU。打印警告但继续执行后续流程：

```python
stats = statistics(quantized_model)
if "hbtl" in str(stats).lower():
    print("[WARNING] 模型中存在 CPU 算子 (hbtl)，编译可能失败或运行时回退 CPU")
    # 可用 visualize(quantized_model, "debug.onnx") 排查具体哪个算子
else:
    print("[OK] 无 CPU 算子")
```

**常见 CPU 算子原因：**
- 使用了 BPU 不支持的算子或参数配置
- 量化配置不正确导致部分算子无法量化
- 可用 `visualize` 生成 onnx 文件定位问题算子

## Step 5: Compile — 编译生成 HBM

将量化模型编译为最终部署产物：

```python
hbm_name = "model.hbm"
compile(quantized_model, hbm_name, march, opt=2, jobs=64, progress_bar=True, debug=False)
```

**compile 调用严禁违反以下规则：**

1. **所有参数不可省略。** 禁止写成 `compile(quantized_model)` 或 `compile(converted_model)`，必须包含完整的参数列表：`compile(quantized_model, hbm_name, march, opt=2, jobs=64, progress_bar=True, debug=False)`。

**compile 参数说明：**
- `opt=2`：优化等级，2 为最高
- `jobs=64`：并行编译线程数
- `progress_bar=True`：显示编译进度
- `debug=False`：不输出调试信息

## 输出产物

| 产物 | 说明 |
|------|------|
| `quantized.bc` | convert 后的量化 BC 文件 |
| `quantized_remove.bc` | remove_io_op 后的 BC 文件 |
| `*.hbm` | 最终部署产物 |

## 常见问题

### 存在 CPU 算子 (hbtl)
1. 使用 `visualize(quantized_model, "debug.onnx")` 生成 onnx 文件排查
2. 检查是否有不支持的算子或参数配置
3. 检查量化配置是否正确

### 编译失败
1. 检查 statistics 是否有 CPU 算子
2. 确认 march 设置与目标平台一致
3. 检查模型输入 shape 是否合理

## 快速自检清单

- export 前模型处于 VALIDATION 状态
- convert 使用正确的 march（`convert(qat_bc, march)`，march 不可省略）
- remove_io_op 通过 `func = quantized_model.functions[0]` + `func.remove_io_op(op_types=["Dequantize", "Quantize"])` 调用（禁止直接对 model 调用，禁止省略 op_types）
- statistics 检查无 CPU 算子 (hbtl)
- compile 生成 HBM 文件（所有参数完整，禁止只写 `compile(model)`）
- save 保存中间 BC 文件
