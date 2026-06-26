# Horizon prepare 接入方法（仅 prepare 调用版）- 使用示例

本示例文档用于指导你在适配 `horizon_plugin_pytorch` 时，为现有**浮点 PyTorch 模型**补齐 `prepare(...)` 调用，得到 QAT 模型。

约束回顾：

- 本 skill **只加 prepare**（以及必要 import/调用点调整）
- **不做 dynamic_block 相关修改**
- qconfig_setter 固定为全部双 int8 模板

## 触发方式

以下类型的 prompt 会触发该 skill：

### 直接触发（明确提及 prepare / PrepareMethod / horizon_plugin_pytorch）

```
帮我给这个模型接入 horizon_plugin_pytorch 的 prepare，把 float model 变成 qat model
```

```
在 @train.py 里加上 horizon 的 prepare 调用
```

### 间接触发（提及 Horizon QAT/量化准备流程）

```
我已经插入了 quant/dequant 边界，下一步需要做 prepare
```

---

## Prompt 中需要包含的关键信息

为了让 agent 能“只加 prepare 且一次改对”，建议在 prompt 里提供以下信息。

### 必须提供的信息

| 信息 | 说明 | 示例 |
|------|------|------|
| 目标文件/入口 | prepare 应该放在哪个脚本/函数里（训练入口、导出入口等） | `@tools/qat/train.py` / `@export.py` |
| float 模型变量名 | 需要被 prepare 的模型对象 | `model` / `float_model` |
| example_inputs 来源 | 能跑通目标 forward 的输入（通常是 eval/infer 路径） | `example_inputs = (img, meta)` |
| 期望 method | 推荐 `PrepareMethod.JIT_STRIP`，或你明确指定 | `JIT_STRIP` |

说明：

- `PrepareMethod.JIT_STRIP` / `PrepareMethod.JIT` **必须**提供 `example_inputs`。
- `example_inputs` 应该匹配你要量化/部署的那条 forward 路径，尽量不要混入训练损失分支与 CPU/Numpy 后处理。

---

## 完整使用流程示例

### 示例 1：在训练入口脚本中对模型执行 prepare

**用户 Prompt：**

```
在 @train.py 里把 float 模型接入 horizon_plugin_pytorch 的 prepare。
float 模型变量叫 model，example_inputs 用 eval_loader 的一条 batch（只走推理路径）。
method 用 JIT_STRIP，qconfig_setter 固定为全部双 int8 模板
```

**Agent 执行流程：**

1. 读取 `train.py`，定位模型构建完成、optimizer 之前的合适位置
2. 增加 import：`prepare/PrepareMethod/QconfigSetter`
3. 组装/获取 `example_inputs`（确保能跑通目标 forward）
4. 调用 `prepare(...)` 生成 `qat_model`，并替换后续训练用的模型引用
5. 自检：prepare 后不再改模型结构，不改 hook；qconfig_setter 固定为全部双 int8 模板

**最小代码模板（仅展示 prepare 相关片段）：**

```python
from horizon_plugin_pytorch.dtype import qint8
from horizon_plugin_pytorch.quantization import get_qconfig
from horizon_plugin_pytorch.quantization.prepare import PrepareMethod, prepare
from horizon_plugin_pytorch.quantization.qconfig_setter import (
    ConvDtypeTemplate,
    MatmulDtypeTemplate,
    ModuleNameTemplate,
    QconfigSetter,
)

# float_model: torch.nn.Module
# example_inputs: Any  (需能跑通目标 forward)
int8_qconfig_setter = QconfigSetter(
    reference_qconfig=get_qconfig(),
    templates=[
        ModuleNameTemplate({"": qint8}),
        ConvDtypeTemplate(input_dtype=qint8, weight_dtype=qint8),
        MatmulDtypeTemplate(input_dtypes=qint8),
    ],
)

qat_model = prepare(
    float_model,
    example_inputs=example_inputs,
    qconfig_setter=int8_qconfig_setter,
    method=PrepareMethod.JIT_STRIP,
)
```

---

### 示例 2：先剥离部署逻辑，再对部署逻辑做 prepare（推荐）

当原 `forward` 混合了训练/评测分支、loss、numpy/CPU 后处理等，建议剥离出“部署推理”逻辑，再对其 prepare。

**用户 Prompt：**

```
这个模型 forward 里有 training 分支和 loss，请把部署推理逻辑抽到 forward_infer，
然后只对 forward_infer 路径做 horizon prepare（JIT_STRIP）。
```

**参考结构（示意）：**

```python
def forward_infer(self, x):
    # 仅部署推理逻辑
    ...
    return y

def forward(self, x, gt=None):
    y = self.forward_infer(x)
    if self.training:
        ...
        return loss
    return y
```

随后在入口侧使用能跑通 `forward_infer` 的 `example_inputs` 来 prepare。

---

## 失败/返工场景示例（常见）

### 场景 1：prepare 之后又修改了模型结构

**典型问题：**

- prepare 后再把 BN 转 SyncBN
- prepare 后替换子模块、重注册 hook

**修复策略：**

- 把结构性变更（如 SyncBN 转换）移动到 prepare 之前
- 保证 prepare 后模型结构与 hook 不再被改动

### 场景 2：example_inputs 跑不通或走错路径

**典型问题：**

- `example_inputs` 对不上 forward 的签名/shape
- 触发了训练分支（走 loss），与部署路径不一致

**修复策略：**

- 用 eval/infer 形态的输入构造 `example_inputs`
- 若必须支持多分支，优先剥离部署逻辑并只对部署逻辑 prepare

---

## 快速自检清单

- `prepare(...)` 调用存在且输出为 `qat_model`
- qconfig_setter 固定为全部双 int8 模板（没有叠加其它 setter）
- `PrepareMethod.JIT_STRIP/JIT` 时提供了可跑通的 `example_inputs`
- prepare 后没有再修改模型结构或 hook

# Horizon prepare（horizon_plugin_pytorch）- 使用示例

本示例文档用于指导你在适配 `horizon_plugin_pytorch` 量化链路时，**为浮点 PyTorch 模型正确执行 prepare**（推荐 `PrepareMethod.JIT_STRIP`），并规避部署逻辑混入、example_inputs 不可复现等常见坑。

## 触发方式

以下类型的 prompt 会触发该 skill：

### 直接触发（明确提及 prepare / PrepareMethod / JIT_STRIP）

```
帮我把这个模型适配 horizon_plugin_pytorch，补齐 prepare（推荐 JIT_STRIP）
```

```
给 @some/model.py 的模型添加 horizon prepare（JIT_STRIP），并输出 qat_model
```

### 间接触发（提及 Horizon QAT、伪量化、算子替换/融合）

```
我要走地平线的 QAT 工具链，模型需要 prepare 成 qat_model
```

```
这个模型 prepare 后 forward 报错，帮我定位是 example_inputs / 部署路径 / prepare 参数哪里有问题
```

---

## Prompt 中需要包含的关键信息

Agent 通常会先界定“部署路径”和 `example_inputs`，再落地 prepare。你可以在 prompt 中直接提供，也可以让 agent 通过阅读代码推断。

### 必须提供的信息

| 信息 | 说明 | 示例 |
|------|------|------|
| 目标文件/目标类 | 要适配的模型位置 | `@hat/models/backbones/resnet.py` / `ResNet` |
| example_inputs | 用于感知图结构，必须可跑通 forward | `(img, points)` / `{"x": ...}` |
| 部署态 | prepare 时应处于 eval 还是 train | 通常 `model.eval()` 对齐部署 |

### 强烈建议提供的信息（能显著减少返工）

| 信息 | 说明 | 示例 |
|------|------|------|
| PrepareMethod | 推荐 `JIT_STRIP`；特殊需求才用 `EAGER` | `PrepareMethod.JIT_STRIP` |
| 部署边界定义 | `JIT_STRIP` 下用于剔除前后处理 | “输入开始量化，输出回 float” |

---

## 完整使用流程示例

### 示例 1：最小 prepare（JIT_STRIP）

**用户 Prompt：**

```
给 @xxx/model.py 的 MyNet 接入 horizon_plugin_pytorch。
我会提供 example_inputs（能跑通 forward），请用 PrepareMethod.JIT_STRIP 执行 prepare 并返回 qat_model。
```

**Agent 执行要点：**

1. 读取目标模型，确认部署 forward 路径与 `example_inputs` 对齐（类型/shape/设备）。
2. 若模型包含前后处理且希望剔除：确认已用 `QuantStub/DeQuantStub` 定义部署边界。
3. 执行：

```python
from horizon_plugin_pytorch.quantization.prepare import prepare, PrepareMethod

qat_model = prepare(
    float_model,
    example_inputs=example_inputs,
    method=PrepareMethod.JIT_STRIP,
)
```

4. 自检：
   - 生成 `model_check_result.txt`
   - 多次 prepare 的 graph 一致（可选但强烈推荐）
   - prepare 后不再修改模型结构/不再改 hook

---

### 示例 2：forward 混入训练分支/非部署逻辑（建议剥离部署路径再 prepare）

**典型问题：**

- forward 中存在 `if self.training: loss(...) else: postprocess(...)`
- 量化边界（quant/dequant）在两条路径上难以保持一致，prepare 结果不可控

**推荐结构：**

```python
def forward_infer(self, x):
    out = self.net(x)
    return out

def forward(self, x, gt=None):
    out = self.forward_infer(x)
    if self.training:
        return self.loss(out, gt)
    return out
```

**prepare 建议：**

- 尽量只对 `forward_infer`（部署逻辑）对应的计算路径进行 prepare（由项目封装或在调用侧选择）。
- 如果无法剥离：
  - 检查加载 ckpt 的 missing/unexpected key（量化参数/模型参数对齐）
  - 检查多次 prepare 的 fx graph 是否一致

---

## 失败/返工场景（常见）

### 场景 1：prepare 后又改了模型（尤其是 hooks / 子模块替换）

**现象：**

- function 算子替换失效、forward 报错、或精度异常波动

**修复策略：**

- 把所有结构性改动（如 SyncBN 转换、模块替换、hook 注册等）前移到 prepare 之前
- 重新执行 prepare，并保持 prepare 后模型冻结结构

### 场景 2：example_inputs 跑不通或不稳定

**现象：**

- prepare 直接失败
- 多次 prepare 的图不一致（同一模型同一配置下）

**修复策略：**

- 保证 example_inputs 覆盖部署路径、且类型/shape/设备稳定
- 避免 forward 依赖随机分支或外部状态导致执行路径漂移（必要时固定种子/显式开关）

---

## 快速自检清单

- `example_inputs` 可跑通 forward，且覆盖部署路径。
- `PrepareMethod.JIT_STRIP` 下部署边界清晰（必要时先插入 `QuantStub/DeQuantStub`）。
- prepare 后不再修改模型结构、不再改 hooks。
- `model_check_result.txt` 结果符合预期；多次 prepare 图一致（建议做）。

