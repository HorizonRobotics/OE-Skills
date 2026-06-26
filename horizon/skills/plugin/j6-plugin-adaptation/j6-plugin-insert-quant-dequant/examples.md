# Horizon 部署边界 Quant/DeQuant 插入方法 - 使用示例

本示例文档用于指导你如何在**浮点 PyTorch 模型**中插入 `horizon_plugin_pytorch` 量化工具链所需的**部署边界**节点：`QuantStub` / `DeQuantStub`。

补充约束：`QuantStub` 只针对**浮点 tensor**。如果某个输入是 scalar，或者是 `bool` / 整型 / 索引 / 已有定点语义的 tensor，则**不需要**插入 `QuantStub`。

## 触发方式

以下类型的 prompt 会触发该 skill：

### 直接触发（明确提及 horizon、QuantStub/DeQuantStub、部署边界）

```
帮我给这个模型适配 horizon_plugin_pytorch，插入 QuantStub/DeQuantStub 作为部署边界
```

```
给 @hat/models/backbones/resnet.py 插入 quant/dequant 节点（horizon_plugin_pytorch）
```

### 间接触发（提及 Horizon 量化链路/量化适配关键词）

```
我要做地平线部署量化，模型需要加 quant/dequant 边界节点
```

```
这个网络要走 horizon 的 QAT 工具链，帮我补齐 QuantStub/DeQuantStub
```

### 隐式触发（描述“部署边界/量化图边界”需求）

```
模型里现在没有量化边界，推理部署要从输入开始量化、输出再转回 float
```

---

## Prompt 中需要包含的关键信息

Agent 通常会先明确“部署边界定义”，然后再落地插入 stub。你可以在 prompt 中直接提供，也可以让 agent 通过追问/阅读代码推断。

### 必须提供的信息

| 信息 | 说明 | 示例 |
|------|------|------|
| 目标文件/目标类 | 要修改的模型文件或类名 | `@hat/models/backbones/resnet.py` |
| 部署输入边界 | 哪些 `forward` 入参属于部署输入 tensor | `x` / `img, points` |
| 部署输出边界 | 哪些返回值属于部署输出 tensor | `z` / `(logits, boxes)` / `{"logits":..., ...}` |

### 可选信息（有默认值或 agent 会推断）

| 信息 | 默认值 | 说明 |
|------|--------|------|
| 输入里哪些不量化 | 非浮点对象不量化 | 如 `meta`、`img_metas`、`shape`、scalar、`bool` tensor、整型 index tensor |
| 早返回分支的语义 | agent 会结合代码判断 | 如 `return_features=True` 时是否算部署输出 |
| 输出结构语义名 | agent 会从变量名推断 | 用于命名 `dequant_logits`、`dequant_boxes` 等 |

### 信息越完整，执行越快

如果你在一条 prompt 中提供了所有关键点，agent 可以直接改代码而不需要来回确认：

```
给 @hat/models/backbones/resnet.py 的 ResNet 插入部署边界：
输入只有 x，需要 quant；输出只有 z，需要 dequant。
```

---

## 完整使用流程示例

### 示例：单输入单输出（ResNet 类）

**用户 Prompt：**

```
给 @hat/models/backbones/resnet.py 适配 horizon_plugin_pytorch，插入 quant/dequant 节点。
forward(self, x) 里 x 是部署输入，z 是部署输出。
```

**Agent 执行流程：**

1. **Phase 1 - 读取并界定边界**
   - 读取目标文件，确认 `forward` 的输入/输出结构。
2. **Phase 2 - 插入 stub**
   - 增加 import：`QuantStub` / `DeQuantStub`
   - 在 `__init__` 中创建：
     - `self.quant_x = QuantStub()`（每个输入独立）
     - `self.dequant_z = DeQuantStub()`（每个输出独立）
3. **Phase 3 - 在 `forward` 落地边界调用**
   - 在进入部署图处：`x = self.quant_x(x)`
   - 在离开部署图处：`z = self.dequant_z(z)`
4. **Phase 4 - 自检**
   - 确认没有 `QuantStub(scale=...)`
   - 确认每条 `return` 路径都遵守同一边界定义

---

## 最小代码模板（可直接照抄）

### 单输入、单输出

```python
import torch.nn as nn
from horizon_plugin_pytorch.quantization import QuantStub
from torch.quantization import DeQuantStub


class Model(nn.Module):
    def __init__(self, net: nn.Module):
        super().__init__()
        self.quant_x = QuantStub()      # 不设置 scale
        self.dequant_y = DeQuantStub()
        self.net = net

    def forward(self, x):
        x = self.quant_x(x)             # 部署输入边界
        y = self.net(x)
        y = self.dequant_y(y)           # 部署输出边界
        return y
```

### 多输入（每个 tensor 输入一个 QuantStub）

```python
class Model(nn.Module):
    def __init__(self, net: nn.Module):
        super().__init__()
        self.quant_img = QuantStub()
        self.quant_points = QuantStub()
        self.dequant_out = DeQuantStub()
        self.net = net

    def forward(self, img, points, meta=None):
        img = self.quant_img(img)
        points = self.quant_points(points)
        out = self.net(img, points, meta=meta)  # meta 非 tensor 通常不量化
        out = self.dequant_out(out)
        return out
```

### 混合输入（只有浮点 tensor 才插 QuantStub）

```python
class Model(nn.Module):
    def __init__(self, net: nn.Module):
        super().__init__()
        self.quant_x = QuantStub()
        self.dequant_out = DeQuantStub()
        self.net = net

    def forward(self, x, mask, ids, scale_factor: float):
        x = self.quant_x(x)  # x 是 float tensor，需要 quant
        # mask 是 bool tensor，不插 quant
        # ids 是整型/索引 tensor，不插 quant
        # scale_factor 是 scalar，不插 quant
        out = self.net(x, mask=mask, ids=ids, scale_factor=scale_factor)
        out = self.dequant_out(out)
        return out
```

### 多输出 tuple/list（每个输出一个 DeQuantStub）

```python
class Model(nn.Module):
    def __init__(self, backbone: nn.Module, head: nn.Module):
        super().__init__()
        self.quant_x = QuantStub()
        self.dequant_logits = DeQuantStub()
        self.dequant_boxes = DeQuantStub()
        self.backbone = backbone
        self.head = head

    def forward(self, x):
        x = self.quant_x(x)
        feats = self.backbone(x)
        logits, boxes = self.head(feats)
        logits = self.dequant_logits(logits)
        boxes = self.dequant_boxes(boxes)
        return logits, boxes
```

### dict 输出（按 key 独立 dequant）

```python
class Model(nn.Module):
    def __init__(self, net: nn.Module):
        super().__init__()
        self.quant_x = QuantStub()
        self.dequant_logits = DeQuantStub()
        self.dequant_boxes = DeQuantStub()
        self.net = net

    def forward(self, x):
        x = self.quant_x(x)
        out = self.net(x)  # out: dict
        out["logits"] = self.dequant_logits(out["logits"])
        out["boxes"] = self.dequant_boxes(out["boxes"])
        return out
```

---

## 失败/返工场景示例（常见）

### 场景 1：复用了同一个 stub 处理多个输入/输出

**典型问题：**
- `self.quant = QuantStub()` 同时量化 `img` 和 `points`
- `self.dequant = DeQuantStub()` 同时反量化 `logits` 和 `boxes`

**修复策略：**
- 改为 `quant_img/quant_points`、`dequant_logits/dequant_boxes` 这种**一一对应**的 stub。

### 场景 2：存在早返回分支，但没有覆盖所有 return 路径

**典型问题：**

- `if return_features: return feats`（但 `feats` 实际是部署输出）

**修复策略：**
- 先明确该分支返回是否属于“部署输出”：
  - **是部署输出**：给 `feats` 增加独立 `DeQuantStub()` 并在该分支 dequant 后返回
  - **不是部署输出**：不要 dequant，保持量化态供后续模块消费

### 场景 3：把 dequant 放得太早（导致后续模块跑在 float 上）

**典型问题：**
- 中间特征提前 `dequant`，后续本应在量化图内的模块被迫在 float 执行

**修复策略：**
- 只在真正“离开部署/量化图”的输出边界处做 dequant。

---

## 快速自检清单

- `__init__`：每个部署输入**浮点 tensor** 都有独立的 `QuantStub()`；每个部署输出**浮点 tensor** 都有独立的 `DeQuantStub()`。
- scalar、`bool` tensor、整型/索引 tensor、已是定点语义的 tensor，没有被误加 `QuantStub()`。
- `forward`：所有 `return` 路径都遵守同一套部署边界定义。
- 没有任何 `QuantStub(scale=...)`。

