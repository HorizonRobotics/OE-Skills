# Horizon QAT 模型 HBIR 导出（hbdk4.export）- 使用示例

本示例文档用于指导你在 `horizon_plugin_pytorch` 的 QAT 流程中，创建独立导出脚本，使用 `hbdk4.export` 将 QAT 模型导出为 HBIR IR 模块。

核心约束：**导出逻辑必须放在独立脚本中，禁止在训练或评测脚本中添加导出逻辑。**

## 触发方式

以下类型的 prompt 会触发该 skill：

### 直接触发（明确提及 export / hbdk4 / HBIR 导出）

```
帮我创建一个独立导出脚本，用 hbdk4.export 导出 QAT 模型
```

```
我要用 horizon_plugin_pytorch 导出 QAT 模型，帮我写一个独立的 export 脚本
```

### 间接触发（描述"导出/编译/部署/落板"需求）

```
模型 QAT 训练完了，帮我写一个导出脚本
```

```
校准结束了，创建独立脚本把 QAT 模型导出来准备编译
```

---

## Prompt 中需要包含的关键信息

你在 prompt 里最好明确以下信息，agent 才能创建正确的独立导出脚本：

### 必须提供的信息

| 信息 | 说明 | 示例 |
|------|------|------|
| 模型构建方式 | 如何构建/加载 QAT 模型 | `MyNet()` + `load_state_dict` / `build_model(cfg)` |
| checkpoint 路径 | QAT 模型权重文件 | `qat_checkpoint.pth` / `outputs/qat_best.pth` |
| march | 目标平台 | `NASH_E` / `NASH_P` / `NASH_B` |
| example_inputs | 能跑通模型 forward 的示例输入 | `torch.randn(1, 3, 224, 224)` |

### 可选信息（有助于避免返工）

| 信息 | 说明 | 示例 |
|------|------|------|
| 输入/输出名称 | 是否需要自定义 HBIR 输入/输出名称 | `input_names={"image": "input_image"}` |
| 导出函数名 | 是否需要指定 name 参数 | `name="forward_infer"` |
| 脚本输出路径 | 导出脚本文件名 | `tools/export_hbir.py` |

---

## 最小使用模板（可直接照抄）

### 独立导出脚本（标准形式）

```python
import torch
import horizon_plugin_pytorch as horizon
from horizon_plugin_pytorch.quantization import hbdk4 as hb4
from horizon_plugin_pytorch.quantization import FakeQuantState, set_fake_quantize
from hbdk4.compiler import save

# 1. 设置 march
horizon.march.set_march(horizon.march.March.NASH_E)

# 2. 加载 QAT 模型
model = MyNet()
model.load_state_dict(torch.load("qat_checkpoint.pth"))

# 3. eval + VALIDATION
model.eval()
set_fake_quantize(model, FakeQuantState.VALIDATION)

# 4. 验证是 QAT 模型
_has_fq = any("FakeQuantize" in type(m).__name__ for m in model.modules())
assert _has_fq, (
    "当前模型不包含 FakeQuantize 模块，不是 QAT 模型。"
    "请确认使用的是 QAT checkpoint 而非 float checkpoint。"
)

# 5. 构造 example_inputs
example_input = torch.randn(1, 3, 224, 224)

# 5. 导出
hbir_model = hb4.export(model, (example_input,))

# 6. 保存
save(hbir_model, "output.bc")
print("HBIR export done.")
```

### 带自定义输入/输出名称和描述

```python
import torch
import horizon_plugin_pytorch as horizon
from horizon_plugin_pytorch.quantization import hbdk4 as hb4
from horizon_plugin_pytorch.quantization import FakeQuantState, set_fake_quantize
from hbdk4.compiler import save

horizon.march.set_march(horizon.march.March.NASH_E)

model = MyNet()
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

---

## 完整使用流程示例

### 示例 1：从 checkpoint 加载 QAT 模型并导出

**用户 Prompt：**

```
帮我创建一个独立导出脚本，从 qat_checkpoint.pth 加载 QAT 模型，用 hbdk4.export 导出。
模型是 MyNet，march 用 NASH_E，example_input 用 torch.randn(1, 3, 512, 512)。
导出时指定 input_names 和 output_names。
```

**Agent 执行流程：**

1. 创建独立导出脚本（如 `tools/export_hbir.py`）
2. 按固定顺序写入：set_march → 加载 QAT 模型 → eval → set_fake_quantize(VALIDATION) → 验证 QAT 模型 → export → save
3. 自检：所有前置条件满足，脚本可独立运行

**导出脚本：**

```python
import torch
import horizon_plugin_pytorch as horizon
from horizon_plugin_pytorch.quantization import hbdk4 as hb4
from horizon_plugin_pytorch.quantization import FakeQuantState, set_fake_quantize
from hbdk4.compiler import save

horizon.march.set_march(horizon.march.March.NASH_E)

# 加载 QAT 模型
model = MyNet()
model.load_state_dict(torch.load("qat_checkpoint.pth"))

# 导出前准备
model.eval()
set_fake_quantize(model, FakeQuantState.VALIDATION)

# 验证是 QAT 模型
_has_fq = any("FakeQuantize" in type(m).__name__ for m in model.modules())
assert _has_fq, (
    "当前模型不包含 FakeQuantize 模块，不是 QAT 模型。"
    "请确认使用的是 QAT checkpoint 而非 float checkpoint。"
)

# 构造 example_inputs
example_input = torch.randn(1, 3, 512, 512)

# 导出
hbir_model = hb4.export(
    model,
    (example_input,),
    input_names={"image": "input_image"},
    output_names={"output": "detection_result"},
)

save(hbir_model, "output.bc")

print("HBIR export done.")
```

---

### 示例 2：使用项目构建函数加载 QAT 模型

**用户 Prompt：**

```
帮我创建独立导出脚本。模型用 build_model(cfg) 构建，然后 load_state_dict。
march 用 NASH_P，checkpoint 在 outputs/qat_best.pth。
模型 forward 接受 (x,) ，example_input 用 torch.randn(1, 3, 640, 640)。
```

**导出脚本：**

```python
import torch
import horizon_plugin_pytorch as horizon
from horizon_plugin_pytorch.quantization import hbdk4 as hb4
from horizon_plugin_pytorch.quantization import FakeQuantState, set_fake_quantize
from hbdk4.compiler import save
from my_project.models import build_model
from my_project.config import Config

horizon.march.set_march(horizon.march.March.NASH_P)

# 加载 QAT 模型
cfg = Config.fromfile("config.py")
model = build_model(cfg)
model.load_state_dict(torch.load("outputs/qat_best.pth"))

# 导出前准备
model.eval()
set_fake_quantize(model, FakeQuantState.VALIDATION)

# 验证是 QAT 模型
_has_fq = any("FakeQuantize" in type(m).__name__ for m in model.modules())
assert _has_fq, (
    "当前模型不包含 FakeQuantize 模块，不是 QAT 模型。"
    "请确认使用的是 QAT checkpoint 而非 float checkpoint。"
)

# 构造 example_inputs
example_input = torch.randn(1, 3, 640, 640)

# 导出
hbir_model = hb4.export(model, (example_input,))

save(hbir_model, "output.bc")

print("HBIR export done.")
```

---

### 示例 3：多输入 QAT 模型的导出

**用户 Prompt：**

```
帮我创建独立导出脚本。QAT 模型 forward 签名是 forward(self, image, points, meta=None)，
其中 image 和 points 是浮点 tensor，meta 是 dict 不参与 tracing。
march 用 NASH_B，example_inputs 只传 image 和 points。
```

**导出脚本：**

```python
import torch
import horizon_plugin_pytorch as horizon
from horizon_plugin_pytorch.quantization import hbdk4 as hb4
from horizon_plugin_pytorch.quantization import FakeQuantState, set_fake_quantize
from hbdk4.compiler import save

horizon.march.set_march(horizon.march.March.NASH_B)

# 加载 QAT 模型
model = MyNet()
model.load_state_dict(torch.load("qat_checkpoint.pth"))

# 导出前准备
model.eval()
set_fake_quantize(model, FakeQuantState.VALIDATION)

# 验证是 QAT 模型
_has_fq = any("FakeQuantize" in type(m).__name__ for m in model.modules())
assert _has_fq, (
    "当前模型不包含 FakeQuantize 模块，不是 QAT 模型。"
    "请确认使用的是 QAT checkpoint 而非 float checkpoint。"
)

# 构造 example_inputs
example_image = torch.randn(1, 3, 224, 224)
example_points = torch.randn(1, 1000, 3)

# 导出
hbir_model = hb4.export(
    model,
    (example_image, example_points),
    input_names={"image": "input_image", "points": "input_points"},
    output_names={"output": "pred"},
)

save(hbir_model, "output.bc")

print("HBIR export done.")
```

---

## 常见失败/返工场景示例（高频）

### 场景 1：在训练脚本末尾添加导出逻辑

**典型问题：**

```python
# train.py 末尾
model.eval()
set_fake_quantize(model, FakeQuantState.VALIDATION)
hbir_model = hb4.export(model, (example_input,))
```

**修复策略：**

- 导出逻辑必须放在独立脚本中，不应在训练脚本中添加
- 创建 `tools/export_hbir.py`，在独立脚本中完成导出和保存

### 场景 2：导出前忘记 eval + VALIDATION

**典型问题：**

```python
# 独立脚本中，忘了 eval 和 VALIDATION
hbir_model = hb4.export(model, (example_input,))
```

**修复策略：**

- 在 export 前加 `model.eval()` 和 `set_fake_quantize(model, FakeQuantState.VALIDATION)`

### 场景 3：只做了 eval，没做 VALIDATION

**典型问题：**

```python
model.eval()
hbir_model = hb4.export(model, (example_input,))  # 缺少 VALIDATION
```

**修复策略：**

- QAT 模型导出前必须先切换到 VALIDATION 状态
- `eval()` 只控制 BN/Dropout 等行为，不控制 fake quantize 状态

### 场景 4：独立脚本中忘记 set_march

**典型问题：**

- 独立导出脚本中没有 `set_march`，依赖运行环境中残留的 march

**修复策略：**

- 独立脚本必须在开头显式调用 `horizon.march.set_march(...)`
- 不依赖环境中的全局残留 march

### 场景 5：example_inputs 与 forward 签名不匹配

**典型问题：**

- forward 接受 `(self, x, y)` 但 `example_inputs = (x,)`
- forward 接受 dict 输入但 `example_inputs` 传了 tuple

**修复策略：**

- 确保 `example_inputs` 的结构与 forward 签名对齐
- 如果 forward 有可选参数且不参与 tracing，可不传入

### 场景 6：input_names/output_names 结构与输入/输出不一致

**典型问题：**

- `example_inputs` 是 tuple，但 `input_names` 传了 dict
- 模型输出是 `(logits, boxes)` 但 `output_names` 只有一个名称

**修复策略：**

- `input_names` 结构必须与 `example_inputs` 一致
- `output_names` 结构必须与模型输出一致
- tuple 输出应对应 tuple 形式的 `output_names`

### 场景 7：导出前又改了模型结构

**典型问题：**

- 独立脚本中加载模型后，又修改了 hook、子模块等
- 导致导出结果与训练/校准阶段不一致

**修复策略：**

- 加载模型后不要再修改结构，直接 eval → VALIDATION → 验证 QAT → export
- 所有结构修改应在 prepare 之前完成

### 场景 8：误将 float 模型当作 QAT 模型导出

**典型问题：**

- 用户提供了 float checkpoint（未经 prepare），导出静默成功但结果无意义
- `hb4.export` 不区分 QAT 模型和 float 模型，不会报错

**修复策略：**

- 导出脚本中加 assert 检查模型是否包含 FakeQuantize 模块
- Agent 创建脚本前应确认用户使用的是 QAT checkpoint

---

## 快速自检清单

- 导出逻辑在独立脚本中，不在训练/评测脚本中。
- 独立脚本开头设置了 `set_march`。
- 模型已 `eval()`。
- QAT 模型已 `set_fake_quantize(model, FakeQuantState.VALIDATION)`。
- 导出脚本中包含 QAT 模型验证（assert 检查 FakeQuantize 模块存在）。
- 确认用户使用的是 QAT checkpoint 而非 float checkpoint。
- `example_inputs` 能跑通 forward 且与签名对齐。
- `hb4.export(model, example_inputs, ...)` 调用存在。
- `from hbdk4.compiler import save` 已添加。
- `save(hbir_model, output_path)` 调用存在。
- `input_names`/`output_names` 结构与输入/输出一致（如使用）。
- 没有 `native_pytree=False`。
- 导出前没有改模型结构。
