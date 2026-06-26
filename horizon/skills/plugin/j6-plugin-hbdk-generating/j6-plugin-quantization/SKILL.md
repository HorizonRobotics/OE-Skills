---
name: j6-plugin-quantization
description: 为基础网络结构生成量化流程代码（set_march → 插入 Quant/DeQuant → 配置量化参数 → prepare → 校准 → QAT 训练）。务必在用户提到模型量化、量化流程、QAT 校准、Horizon 量化适配、HistogramObserver/MinMaxObserver 配置、量化参数配置、校准训练、QuantStub 插入时触发此 skill，即使用户只问其中一个步骤，只要涉及 Horizon 量化流程的任何环节都应触发。
---

# 基础结构量化流程代码生成

## 目标

根据用户提供的浮点模型结构，生成量化流程代码，从 `set_march` 到 QAT 训练完成。生成后的代码可直接运行（在正确安装了 `horizon_plugin_pytorch` 和 `hbdk4` 的环境中）。

本 Skill 覆盖的流程：

```
set_march → 定义模型（含 Quant/DeQuant）→ 配置量化参数 → prepare → 校准 → [可选] QAT 训练
```

量化流程的输出取决于用户选择：
- 仅校准：输出 `calib_net`
- 校准 + QAT：输出 `qat_net`

供 `j6-hbdk-export-compile` skill 消费。

## 第一步：确认信息

在生成代码前，必须确认以下信息。march 是必选项，必须由用户明确指定，不能擅自假设默认值。如果用户未指定且无法交互（如 eval 场景），则使用 `"nash-p"` 作为默认值，不得自行选择其他 march。

### 必须询问：march（目标平台）

向用户询问目标平台，给出以下选项：

| march | 平台 | 说明 |
|-------|------|------|
| `"nash-p"` | J6P | 推荐，全局激活支持 float16 |
| `"nash-h"` | J6H | 全局激活支持 float16 |
| `"nash-m"` | J6M | 全局激活为 qint8 |
| `"nash-e"` | J6E | 全局激活为 qint8 |
| `"nash-b"` | J6B | 全局激活为 qint8 |

如果用户未指定，暂停代码生成，等待用户确认。不同的 march 会影响全局激活类型的选择：
- nash-p / nash-h：推荐全局激活 `torch.float16`
- nash-m / nash-e / nash-b：推荐全局激活 `qint8`

### 必须询问：校准后是否进行 QAT 训练

向用户询问校准后的流程选择：

| 选项 | 说明 |
|------|------|
| 仅校准（calib-only） | 校准后直接导出，速度快，适合精度要求不高的场景 |
| 校准 + QAT 训练（calib+qat） | 校准后重新 prepare 并进行 QAT 训练，精度更高，推荐用于精度敏感场景 |

两种选项的代码差异：

**仅校准**：校准完成后，输出 `calib_net`，后续由 `j6-hbdk-export-compile` 直接 export。

**校准 + QAT**：校准完成后，使用 MinMaxObserver 重新 prepare 浮点模型，执行 QAT 训练，输出 `qat_net`。

### 可选确认（用户未提供时使用默认值）

| 信息 | 默认值 | 说明 |
|------|--------|------|
| 模型结构 | Conv+BN+ReLU+Linear | 基础网络结构 |
| 输入 shape | (1, 3, 32, 32) | 示例输入大小 |
| 是否有自定义量化配置 | 否 | 是否需要指定某些层使用 qint16 等 |

## 第二步：生成代码 — 按步骤组织

### Step 1: 导入

```python
import torch
import torch.nn as nn
from horizon_plugin_pytorch.quantization import QuantStub
from torch.quantization import DeQuantStub
from horizon_plugin_pytorch import set_march
from horizon_plugin_pytorch.quantization import (
    prepare, set_fake_quantize, FakeQuantState,
    QconfigSetter, get_qconfig, qint8, qint16,
)
from horizon_plugin_pytorch.quantization.observer_v2 import HistogramObserver, MinMaxObserver
from horizon_plugin_pytorch.quantization.qconfig_setter import (
    ModuleNameTemplate, ConvDtypeTemplate, MatmulDtypeTemplate,
)
```

**注意：** 当本 sub-skill 作为 `j6-plugin-hbdk-generating`（编排型 skill）的一部分被调用时，导入语句必须与导出编译子 skill 的导入合并到文件顶部的一个统一导入块中，格式严格遵循 `references/full-pipeline-template.md`。

### Step 2: 设置平台

用字符串直接指定 march，不用 `March` 枚举：

```python
set_march(march)
```

### Step 3: 定义模型（含 Quant/DeQuant 边界）

模型必须包含 `QuantStub` 和 `DeQuantStub` 作为部署边界。完整的插入规则和多种场景模板见 `references/quant-dequant-rules.md`。

**核心规则：**
- `quant/dequant` 是部署边界：标记从哪里开始/结束部署（进入/离开量化图）
- 每个输入和输出都单独创建 `quant/dequant`：不要复用同一个 stub
- `QuantStub` 初始化不设置 `scale`
- `QuantStub` 只针对浮点 tensor：scalar、bool tensor、整型/索引 tensor 不插 quant
- quant 和 dequant 之间只放部署逻辑：loss、训练标签处理、评价指标、前后处理、可视化等非部署逻辑必须放在边界之外
- train/eval 的边界定义必须一致

**单输入单输出模板：**

```python
class MyNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv = nn.Conv2d(...)
        self.bn = nn.BatchNorm2d(...)
        self.relu = nn.ReLU(inplace=True)
        self.fc = nn.Linear(...)

        self.quant = QuantStub()
        self.dequant = DeQuantStub()

    def forward(self, x):
        x = self.quant(x)            # 部署输入边界
        x = self.relu(self.bn(self.conv(x)))
        x = self.fc(x)
        x = self.dequant(x)          # 部署输出边界
        return x
```

**多输入/多输出/混合输入等模板**：遇到这些场景时，阅读 `references/quant-dequant-rules.md` 获取完整模板。

### Step 4: 配置量化参数

根据平台选择全局激活类型：

- **nash-p / nash-h**：推荐全局激活 `torch.float16`
- **nash-m / nash-e / nash-b**：推荐全局激活 `qint8`

Conv 和 Matmul 类算子默认配置为全 int8 输入，也支持配置 qint16：

```python
if march in ("nash-p", "nash-h"):
    global_output_dtype = torch.float16
else:
    global_output_dtype = qint8

qconfig_setter = QconfigSetter(
    get_qconfig(observer=HistogramObserver),
    templates=[
        ModuleNameTemplate({"": global_output_dtype}),
        ConvDtypeTemplate(input_dtype=qint8, weight_dtype=qint8),
        MatmulDtypeTemplate(input_dtypes=[qint8, qint8]),
    ],
)
```

**QconfigSetter 参数严禁违反以下规则：**

1. **`march` 不得作为 QconfigSetter 的参数传入。** march 只能通过 `set_march(march)` 独立设置（见 Step 2）。QconfigSetter 不接受也不需要 march 参数。
2. **QconfigSetter 的第一个位置参数必须是 `get_qconfig(observer=...)`。** 不得替换为捏造的关键字参数如 `activation_observer=`、`weight_observer=`、`march=`、`dtype_template_list=` 等。
3. **模板列表的关键字必须是 `templates=`，不得使用 `dtype_template_list=` 或其他名称。**
4. **`ModuleNameTemplate({"": global_output_dtype})` 必须始终是 templates 列表的第一项。** 省略此项意味着全局激活类型未配置，属于严重错误。
5. **`ConvDtypeTemplate` 和 `MatmulDtypeTemplate` 的参数不可省略。** 必须写成 `ConvDtypeTemplate(input_dtype=qint8, weight_dtype=qint8)` 和 `MatmulDtypeTemplate(input_dtypes=[qint8, qint8])`，禁止写成无参调用 `ConvDtypeTemplate()` 或 `MatmulDtypeTemplate()`。省略参数会导致量化精度无法保证。
6. **`prepare` 的第二个参数 `(example_input,)` 不可省略。** 必须写成 `prepare(model, (example_input,), qconfig_setter=qconfig_setter)`，禁止写成 `prepare(model, qconfig_setter=qconfig_setter)`。

**如果需要指定某些层使用 qint16**，追加 `ModuleNameTemplate`：

```python
sensitive_layers = ["backbone.conv1", "head.fc"]
int16_dict = {
    name: {"output": qint16, "weight": qint16}
    for name in sensitive_layers
}

qconfig_setter = QconfigSetter(
    get_qconfig(observer=HistogramObserver),
    templates=[
        ModuleNameTemplate({"": global_output_dtype}),
        ConvDtypeTemplate(input_dtype=qint8, weight_dtype=qint8),
        MatmulDtypeTemplate(input_dtypes=[qint8, qint8]),
        ModuleNameTemplate(int16_dict),
    ],
)
```

**如果用户在 prompt 中明确指定了某个算子/block 的量化精度**（如"输入精度 int16"、"grid 用 qint16"、"conv1 输出 qint16"），必须在对应的 `ModuleNameTemplate` 中加上 `freeze=True`，防止被自动覆盖为其他精度：

```python
# 用户明确指定输入精度为 qint16
int16_input_dict = {
    "quant_img": {"output": qint16},
    "quant_grid": {"output": qint16},
}

qconfig_setter = QconfigSetter(
    get_qconfig(observer=HistogramObserver),
    templates=[
        ModuleNameTemplate({"": global_output_dtype}),
        ModuleNameTemplate(int16_input_dict, freeze=True),  # 用户指定的精度，加 freeze=True
        ConvDtypeTemplate(input_dtype=qint8, weight_dtype=qint8),
        MatmulDtypeTemplate(input_dtypes=[qint8, qint8]),
    ],
)
```

**`freeze=True` 使用规则：**
- 用户 prompt 中明确指定了某个模块/算子的量化精度 → 加 `freeze=True`
- 用户仅提到"精度敏感"等模糊表述，未指定具体精度 → 不加 `freeze=True`（让框架自动选择）
- `freeze=True` 的效果：该模块的量化精度不会被自动调整，强制保持用户指定的值

**常用 Observer：**

| Observer | 说明 | 适用阶段 |
|----------|------|----------|
| `HistogramObserver` | 基于直方图统计分布，校准精度高 | 校准（CALIBRATION）阶段推荐 |
| `MinMaxObserver` | 基于最大最小值计算 scale，计算开销小 | QAT 训练阶段推荐 |
| `MSEObserver` | 基于均方误差优化 scale | 可选 |

### Step 5: Prepare（插入伪量化节点）

prepare 之前，先验证浮点模型能正常推理：

```python
# 验证浮点模型推理正常
model.eval()
with torch.no_grad():
    model(example_input)

calib_net = prepare(model, (example_input,), qconfig_setter=qconfig_setter)
```

注意：
- prepare 会替换/融合/转换算子，prepare 之后不要再改模型结构或 hook
- `example_input` 必须能跑通 forward

### Step 6: 校准（CALIBRATION）

校准阶段使用 `HistogramObserver`。顺序：先 `model.eval()`，再 `set_fake_quantize(CALIBRATION)`，校准期间不要再次 `model.eval()`：

```python
calib_net.eval()
set_fake_quantize(calib_net, FakeQuantState.CALIBRATION)
with torch.no_grad():
    calib_net(example_input)
```

校准完成后，根据用户选择的流程分支：

#### 分支 A：仅校准（calib-only）

校准完成后直接进入导出，不需要 QAT 训练。输出 `calib_net`：

```python
# 校准完成，直接进入导出编译流程
# 输出: calib_net
```

#### 分支 B：校准 + QAT 训练（calib+qat）

QAT 阶段推荐使用 `MinMaxObserver`。

**重要：`qconfig_setter` 只能通过 `prepare` 传入，不能在 prepare 之后单独调用。** 因此要切换 observer，必须重新对浮点模型执行 `prepare`：

```python
qconfig_setter_qat = QconfigSetter(
    get_qconfig(observer=MinMaxObserver),
    templates=[
        ModuleNameTemplate({"": global_output_dtype}),
        ConvDtypeTemplate(input_dtype=qint8, weight_dtype=qint8),
        MatmulDtypeTemplate(input_dtypes=[qint8, qint8]),
    ],
)

# 重新从浮点模型 prepare，使用 MinMaxObserver
qat_net = prepare(model, (example_input,), qconfig_setter=qconfig_setter_qat)
qat_net.train()
set_fake_quantize(qat_net, FakeQuantState.QAT)

# 正常训练循环
optimizer = torch.optim.SGD(qat_net.parameters(), lr=1e-4)
for data, target in train_loader:
    optimizer.zero_grad()
    output = qat_net(data)
    loss = criterion(output, target)
    loss.backward()
    optimizer.step()

# QAT 训练完成，输出: qat_net
```

## FakeQuantState 状态说明

| 状态 | 用途 | 行为 |
|------|------|------|
| `CALIBRATION` | 校准阶段 | 仅观测各算子输入/输出统计量 |
| `QAT` | QAT 训练阶段 | 观测统计量 + 执行伪量化 |
| `VALIDATION` | 验证/导出阶段 | 仅执行伪量化，不再观测统计量 |

**顺序要求：**
- 校准：先 `model.eval()`，再 `set_fake_quantize(CALIBRATION)`，校准期间不要再调 `model.eval()`
- QAT 训练：`model.train()` + `set_fake_quantize(QAT)`
- 导出前需切换到 VALIDATION 状态（由 `j6-hbdk-export-compile` skill 处理）

## 常见问题

### 校准后 scale 为 1
确保在 CALIBRATION 模式下执行了前向传播，且输入数据合理。

### 量化精度损失严重
1. 校准阶段使用 HistogramObserver 提高精度
2. QAT 训练阶段使用 MinMaxObserver 适配训练
3. 对精度敏感的层使用 qint16
4. 检查输入数据分布

## 快速自检清单

- 用户已明确指定 march（未指定时默认 `nash-p`，不得自选其他值），march 在模型构建/prepare 前设置
- 模型包含 QuantStub/DeQuantStub，每个输入/输出独立 stub
- QuantStub 不设置 scale
- quant 和 dequant 之间只包含部署逻辑
- 根据平台正确选择全局激活类型（nash-p/h → float16，nash-m/e/b → qint8）
- 校准阶段使用 HistogramObserver，QAT 训练阶段使用 MinMaxObserver
- qconfig_setter 只能通过 prepare 传入，切换 observer 必须重新 prepare 浮点模型
- 校准前 model.eval() + set_fake_quantize(CALIBRATION)，校准期间不再 eval
- 用户明确指定的量化精度，ModuleNameTemplate 中须加 freeze=True
- ConvDtypeTemplate 和 MatmulDtypeTemplate 参数完整（禁止无参调用）
- prepare 第二个参数 (example_input,) 未省略
