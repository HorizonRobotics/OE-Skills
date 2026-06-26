---
name: j6-plugin-export
description: 使用 horizon_plugin_pytorch 的 hbdk4.export 将 QAT 模型导出为 HBIR IR 模块。以独立导出脚本的形式执行，不在训练或评测脚本中添加导出逻辑。
---

# 为 Horizon QAT 模型创建独立 HBIR 导出脚本（hbdk4.export）

## 目标

在使用 `horizon_plugin_pytorch` 的 QAT 工具链完成校准/训练后，**创建一个独立的导出脚本**，将 QAT 模型导出为 HBIR IR 模块，用于后续编译部署。

本 Skill **只做一件事**：创建独立导出脚本，脚本中包含

```python
from horizon_plugin_pytorch.quantization import hbdk4 as hb4
from hbdk4.compiler import save

model.eval()
set_fake_quantize(model, FakeQuantState.VALIDATION)
hbir_model = hb4.export(model, example_inputs, ...)
save(hbir_model, "output_path")
```

不引入任何其他改动（不改模型结构、不改 qconfig、不改 prepare/convert、不改训练/数据逻辑、**不在训练或评测脚本中添加导出逻辑**）。

## 强约束（必须遵守）

### 1) 必须以独立导出脚本的形式执行

导出逻辑**必须**放在独立脚本中，**禁止**在训练脚本、评测脚本或其他已有脚本中添加导出逻辑。

原因：

- 导出是一次性动作，不应与训练/评测流程耦合
- 独立脚本便于单独调试、复用和版本管理
- 避免训练/评测脚本因导出逻辑变得臃肿

### 2) 独立导出脚本的标准结构

独立导出脚本必须包含以下步骤，**按固定顺序执行**：

1. `set_march` — 设置目标平台
2. 构建/加载 QAT 模型 — 从 checkpoint 恢复
3. `model.eval()` — 切换到推理模式
4. `set_fake_quantize(model, FakeQuantState.VALIDATION)` — 切换到验证状态
5. QAT 模型验证 — 检查模型包含 fake-quant 模块，确保是 QAT 模型
6. 构造 `example_inputs`
7. `hb4.export(model, example_inputs, ...)` — 执行导出
8. `save(hbir_model, output_path)` — 保存 HBIR 模型到文件

### 3) 不在训练/评测脚本中添加导出逻辑

即使训练/评测脚本末尾是"导出的自然位置"，也不应在其中插入导出代码。应创建独立脚本。

### 4) 导出前必须验证模型是 QAT 模型

`hb4.export` 不区分 QAT 模型和 float 模型，如果误传 float 模型，导出会静默成功但结果无意义。因此：

**Agent 侧约束**：创建导出脚本前，必须确认用户提供的 checkpoint 是 QAT checkpoint（已完成 prepare + 校准/训练），而非 float checkpoint。如果用户未明确说明，应主动询问确认。

**运行时检查**：导出脚本中必须在 export 之前加入 QAT 模型验证，检查模型是否包含 fake-quant 模块：

```python
# 验证模型是 QAT 模型（包含 fake-quant 模块）
_has_fq = any(
    "FakeQuantize" in type(m).__name__
    for m in model.modules()
)
assert _has_fq, (
    "当前模型不包含 FakeQuantize 模块，不是 QAT 模型。"
    "请确认使用的是 QAT checkpoint 而非 float checkpoint。"
)
```

## 标准改法（通用模板）

### 1) 增加 import

```python
import torch
import horizon_plugin_pytorch as horizon
from horizon_plugin_pytorch.quantization import hbdk4 as hb4
from horizon_plugin_pytorch.quantization import FakeQuantState, set_fake_quantize
from hbdk4.compiler import save
```

### 2) 独立导出脚本完整模板

```python
import torch
import horizon_plugin_pytorch as horizon
from horizon_plugin_pytorch.quantization import hbdk4 as hb4
from horizon_plugin_pytorch.quantization import FakeQuantState, set_fake_quantize
from hbdk4.compiler import save

# 1. 设置 march
horizon.march.set_march(horizon.march.March.NASH_E)

# 2. 构建/加载 QAT 模型
model = build_model()
model.load_state_dict(torch.load("qat_checkpoint.pth"))

# 3. eval
model.eval()

# 4. 切换到 VALIDATION
set_fake_quantize(model, FakeQuantState.VALIDATION)

# 5. 验证是 QAT 模型
_has_fq = any("FakeQuantize" in type(m).__name__ for m in model.modules())
assert _has_fq, (
    "当前模型不包含 FakeQuantize 模块，不是 QAT 模型。"
    "请确认使用的是 QAT checkpoint 而非 float checkpoint。"
)

# 6. 构造 example_inputs
example_input = torch.randn(1, 3, 224, 224)

# 7. 导出
hbir_model = hb4.export(model, (example_input,))

# 8. 保存
save(hbir_model, "output.bc")
```

### 3) 带自定义输入/输出名称和描述

```python
import torch
import horizon_plugin_pytorch as horizon
from horizon_plugin_pytorch.quantization import hbdk4 as hb4
from horizon_plugin_pytorch.quantization import FakeQuantState, set_fake_quantize
from hbdk4.compiler import save

horizon.march.set_march(horizon.march.March.NASH_E)

model = build_model()
model.load_state_dict(torch.load("qat_checkpoint.pth"))

model.eval()
set_fake_quantize(model, FakeQuantState.VALIDATION)

# 验证是 QAT 模型
_has_fq = any("FakeQuantize" in type(m).__name__ for m in model.modules())
assert _has_fq, (
    "当前模型不包含 FakeQuantize 模块，不是 QAT 模型。"
    "请确认使用的是 QAT checkpoint 而非 float checkpoint。"
)

example_input = torch.randn(1, 3, 224, 224)

hbir_model = hb4.export(
    model,
    (example_input,),
    input_names={"image": "input_image"},
    output_names={"feature": "feat_map", "raw": "raw_map"},
    input_descs={"image": "RGB input image"},
    output_descs={"feature": "ReLU features", "raw": "raw conv output"},
)

save(hbir_model, "output.bc")
```

### 4) 调用导出模型

导出后的 `hbir_model` 可通过 `functions` 属性访问导出的函数：

```python
# native_pytree=True（默认，推荐）
hbir_ret = hbir_model.functions[0](model_args)
```

## 参数详解

| 参数 | 类型 | 默认值 | 是否必填 | 说明 |
|------|------|--------|----------|------|
| `model` | `nn.Module` | — | **必填** | 待导出的 QAT 模型，必须处于 eval 模式且已切换到 VALIDATION |
| `example_inputs` | `Any` | — | **必填** | tracing 示例输入，支持 Tensor、tuple、dict 或嵌套结构 |
| `name` | `str` | `"forward"` | 可选 | 导出模块中的函数名 |
| `input_names` | `Optional[Any]` | `None` | 可选 | HBIR 输入名称，结构须与 `example_inputs` 一致 |
| `output_names` | `Optional[Any]` | `None` | 可选 | HBIR 输出名称，结构须与模型输出一致 |
| `input_descs` | `Optional[Any]` | `None` | 可选 | HBIR 输入描述，结构须与 `example_inputs` 一致 |
| `output_descs` | `Optional[Any]` | `None` | 可选 | HBIR 输出描述，结构须与模型输出一致 |
| `native_pytree` | `bool` | `True` | 可选 | 是否使用 hbdk4 原生 pytree，推荐 `True` |

### save 参数

| 参数 | 类型 | 默认值 | 是否必填 | 说明 |
|------|------|--------|----------|------|
| `module` | HBIR Module | — | **必填** | `hb4.export` 返回的 HBIR 模型 |
| `output_path` | `str` | — | **必填** | 保存路径，如 `"output.bc"` |

## 关键注意事项（必须遵守）

### 1) eval + VALIDATION 是导出的硬性前提，缺一不可

导出前必须按固定顺序执行：

```python
model.eval()
set_fake_quantize(model, FakeQuantState.VALIDATION)
```

- `model.eval()` 确保模型处于推理模式（BN 等算子使用 running stats）
- `set_fake_quantize(model, FakeQuantState.VALIDATION)` 确保 observer 不再更新统计量，仅执行伪量化

如果忘记切换状态，observer 可能仍在更新统计量，导致导出结果不可预期。

### 2) set_march 必须在模型构建/导出之前

独立导出脚本中必须在最开始设置 march，确保后续所有平台相关逻辑都在正确的上下文中执行。

### 3) example_inputs 必须与 forward 签名对齐

`example_inputs` 应当与模型 `forward` 的输入签名匹配，能跑通目标 forward 路径。如果模型 forward 有多个参数，`example_inputs` 应为对应的 tuple 或 dict。

### 4) input_names / output_names 的结构须与输入/输出一致

- `input_names` 的结构须与 `example_inputs` 一致
- `output_names` 的结构须与模型输出一致

例如：如果 `example_inputs` 是 dict，`input_names` 也应是 dict 且 key 对应。

### 5) 导出前不要改模型结构

export 前不要修改模型结构（hook、子模块等），所有结构修改应在 prepare 之前完成。

### 6) 不要分析或处理 tensor 转 Python 类型的 tracing warning

导出时可能出现如下 warning：

```
Converting a tensor to a Python {} might cause the trace to be incorrect. We can't record the data flow of Python values, so this value will be treated as a constant. This means that the exported hbir might not generalize to other inputs!
```

这是 `hb4.export` tracing 过程中的已知行为，**不要**尝试分析、定位或修复该 warning。该 warning 不影响导出流程，不属于本 Skill 的处理范围。

## 适用场景

本 Skill 适用于：

- QAT 模型校准/训练完成后，创建独立脚本导出 HBIR 用于编译部署
- 需要为导出的 HBIR 模型指定输入/输出名称和描述
- 多次导出同一 QAT 模型（不同 name / 不同 example_inputs）

## 不适用场景

以下情况不属于本 Skill 的直接处理范围：

- 给模型做 `prepare(...)` → 用 `j6-plugin-prepare`
- 设置 fake quantize 状态 → 用 `j6-plugin-set-fake-quantize`
- 设置 march → 用 `j6-plugin-set-march`
- 插入 QuantStub/DeQuantStub → 用 `j6-plugin-insert-quant-dequant`
- 导出浮点模型（非 QAT 模型）
- 编译 HBIR 模型（导出后的下一步）
- 在训练/评测脚本中添加导出逻辑 → 应创建独立脚本

如果用户同时提这些需求，应分步处理，export 仅负责其中一环。

## 导出在 QAT 流程中的位置

在完整的 Horizon QAT 工作流中，export 是 **最后一步**：

因此：
- export 依赖模型已经完成 prepare 和校准/训练
- export 前必须确保 `model.eval()` + `set_fake_quantize(model, VALIDATION)` 已调用
- export 以独立脚本形式执行，不嵌入训练/评测流程
- export 之后的 HBIR 模型不再依赖 `horizon_plugin_pytorch` 的 QAT 机制

## 快速自检清单

- 导出逻辑在独立脚本中，不在训练/评测脚本中。
- 脚本开头设置了 `set_march`。
- 模型已处于 `eval()` 模式。
- 已调用 `set_fake_quantize(model, FakeQuantState.VALIDATION)`。
- 导出脚本中包含 QAT 模型验证（assert 检查 FakeQuantize 模块存在）。
- 确认用户使用的是 QAT checkpoint 而非 float checkpoint。
- `example_inputs` 能跑通模型的 forward 路径，且与 forward 签名对齐。
- 代码中新增了 `from horizon_plugin_pytorch.quantization import hbdk4 as hb4`。
- 代码中新增了 `from horizon_plugin_pytorch.quantization import FakeQuantState, set_fake_quantize`。
- 代码中新增了 `hbir_model = hb4.export(model, example_inputs, ...)` 调用。
- 代码中新增了 `from hbdk4.compiler import save`。
- 代码中新增了 `save(hbir_model, output_path)` 调用。
- 如果使用了 `input_names`/`output_names`，其结构与 `example_inputs`/模型输出一致。
- 导出前没有改模型结构。
