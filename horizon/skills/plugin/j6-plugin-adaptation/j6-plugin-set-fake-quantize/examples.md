# Horizon fake quantize 状态设置（set_fake_quantize）- 使用示例

本示例文档用于指导你在 `horizon_plugin_pytorch` 的量化流程中，为模型设置 `fake quantize` 状态：`QAT / CALIBRATION / VALIDATION`。

## 触发方式

以下类型的 prompt 会触发该 skill：

### 直接触发（明确提及 set_fake_quantize / FakeQuantState）

```
帮我在 calibration 前加 set_fake_quantize(CALIBRATION)
```

```
我要用 horizon_plugin_pytorch 做 QAT/validation，帮我把 fake quantize 状态切换补齐
```

### 间接触发（描述“校准/QAT/验证状态切换”需求）

```
校准阶段只统计 observer，不做 fake quant；验证阶段只做 fake quant，不更新统计量
```

```
训练/评估时 fake quantize 状态总是乱的，帮我按阶段设置
```

---

## Prompt 中需要包含的关键信息

你在 prompt 里最好明确以下信息，agent 才能把 `set_fake_quantize` 放在正确的阶段入口：

### 必须提供的信息

| 信息 | 说明 | 示例 |
|------|------|------|
| 目标代码位置 | 哪个文件/函数/脚本要加状态切换 | `@tools/calibrate.py` / `train.py` / `Trainer.validate()` |
| 目标阶段 | 你要设置的是 calibration / qat / validation 哪个阶段 | `CALIBRATION` / `QAT` / `VALIDATION` |
| 执行顺序要求 | 是否会调用 `model.eval()`/`model.train()` | “校准前会先 eval” / “validation 入口会 eval” |

### 可选信息（有助于避免返工）

| 信息 | 说明 | 示例 |
|------|------|------|
| 是否存在多个入口 | 不同脚本/不同分支是否都会跑到 | “有单独的 calibrate 脚本和 validate 函数” |
| 循环结构 | 是否在 epoch/step 内频繁切换 | “每个 epoch 后会跑一次 validation” |

---

## 最小使用模板（可直接照抄）

### Calibration

```python
horizon.quantization.set_fake_quantize(
    model, horizon.quantization.FakeQuantState.CALIBRATION
)
```

**注意**：设置为 `CALIBRATION` 后，**不要再调用** `model.eval()`，否则校准会异常。

### QAT

```python
horizon.quantization.set_fake_quantize(
    model, horizon.quantization.FakeQuantState.QAT
)
```

### Validation

```python
model.eval()
horizon.quantization.set_fake_quantize(
    model, horizon.quantization.FakeQuantState.VALIDATION
)
```

---

## 常见失败/返工场景示例（高频）

### 场景 1：校准入口里先 set_fake_quantize(CALIBRATION)，后又调用了 model.eval()

**典型问题：**

```
set_fake_quantize(CALIBRATION)
...
model.eval()   # 后面某处又 eval 了一次
```

**修复策略：**

- 如果校准确实需要 eval：把 `model.eval()` 放到 `set_fake_quantize(CALIBRATION)` 之前，并保证后续不再重复 eval。
- 如果不需要 eval：直接移除校准阶段的 `model.eval()` 调用（本 skill 本身不会帮你移除，只会指出顺序约束与正确落点）。

### 场景 2：validation 仍处于 QAT 状态，导致评估时统计量在变

**典型问题：**

- 验证时忘了切换到 `VALIDATION`，observer 仍在更新。

**修复策略：**

- 在 validation 入口固定加入：
  - `model.eval()`
  - `set_fake_quantize(model, VALIDATION)`

