---
name: j6-plugin-set-fake-quantize
description: 在适配 horizon_plugin_pytorch 的量化流程中，为模型设置 fake quantize 状态（QAT/CALIBRATION/VALIDATION）。只添加/调用 set_fake_quantize，不做其他修改。
---

# 为 Horizon 量化流程设置 fake quantize 状态（set_fake_quantize）

## 目标

在使用 `horizon_plugin_pytorch` 的 Calibration / QAT / Validation 流程时，按阶段为模型设置正确的 `fake quantize` 状态：

- Calibration 前：`CALIBRATION`
- QAT（训练）前：`QAT`
- Validation（评估）前：`VALIDATION`

本 Skill **只做一件事**：在合适位置添加/调用

```python
horizon.quantization.set_fake_quantize(model, horizon.quantization.FakeQuantState.<STATE>)
```

不引入任何其他改动（不改模型结构、不改 qconfig、不改 prepare/convert、不改训练/数据逻辑）。

## 标准改法（通用模板）

### 1) 选择状态枚举值

`fake quantize` 有三种状态：

```python
class FakeQuantState(Enum):
    QAT = "qat"
    CALIBRATION = "calibration"
    VALIDATION = "validation"
```

语义与行为约束（按官方说明）：

- `CALIBRATION`：仅观测各算子输入/输出统计量（observer 统计）。
- `QAT`：观测统计量 + 执行伪量化（fake quant）。
- `VALIDATION`：仅执行伪量化，不再观测统计量。

### 2) 在阶段入口处调用 `set_fake_quantize`

#### Calibration 前

```python
model.eval()
horizon.quantization.set_fake_quantize(
    model, horizon.quantization.FakeQuantState.CALIBRATION
)
```

#### QAT（训练）前

```python
horizon.quantization.set_fake_quantize(
    model, horizon.quantization.FakeQuantState.QAT
)
```

#### Validation（评估）前

```python
model.eval()
horizon.quantization.set_fake_quantize(
    model, horizon.quantization.FakeQuantState.VALIDATION
)
```

## 关键注意事项（必须遵守）

### 1) Calibration 状态下不要再调用 `model.eval()`

一旦设置为 `FakeQuantState.CALIBRATION`，**请勿再使用 `model.eval()`**，否则将无法正常进行校准。

如果你的流程需要在校准时切换到 eval，请改为：

- **先** `model.eval()`（如果你确实需要 eval）
- **再** `set_fake_quantize(..., CALIBRATION)`

并确保后续不再重复调用 `model.eval()`。

### 2) Validation 的顺序要求

Validation 推荐固定顺序：

- **先** `model.eval()`
- **再** `set_fake_quantize(..., VALIDATION)`

以保证评估时不再更新统计量，仅执行伪量化。

### 3) 不要混用状态（尤其是训练/评估循环）

如果你的代码存在多个入口（如：训练脚本、校准脚本、导出脚本），每个入口都要在其对应阶段入口处显式设置状态，避免：

- QAT 训练时仍处于 `CALIBRATION`
- Validation 评估时仍处于 `QAT`

## 快速自检清单

- Calibration 前调用：`set_fake_quantize(model, CALIBRATION)`，且之后不再 `model.eval()`。
- QAT 训练前调用：`set_fake_quantize(model, QAT)`。
- Validation 前调用：`model.eval()` 后紧接 `set_fake_quantize(model, VALIDATION)`。

