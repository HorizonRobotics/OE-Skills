---
name: j6-plugin-hbdk-generating
description: 为基础网络结构生成从量化到编译的完整流程代码（set_march → Quant/DeQuant → 量化配置 → prepare → 校准 → QAT → export → convert → remove_io_op → statistics → compile HBM）。当用户需要同时覆盖量化和编译多个步骤时触发，如"帮我写量化编译全流程代码"、"Conv+BN+ReLU 量化部署"、"地平线量化编译"、"基础结构量化到 HBM"。即使用户没有明确说"全流程"，只要涉及从量化到编译的多个步骤都应触发。如果用户只需要量化或只需要编译，应路由到对应子 skill。关键词："量化编译"、"量化部署"、"全流程"、"set_march 到 HBM"、"地平线量化"、"Horizon 量化编译"、"基础结构量化"、"QAT 量化编译"。
---

# 基础结构量化编译全流程代码生成（编排型）

## 目标

根据用户提供的浮点模型结构，生成一份完整的量化编译全流程代码，从 `set_march` 到最终编译 HBM。

本 Skill 是编排型 skill，负责按固定顺序调用两个子 skill，不直接实现具体逻辑。

## 必须遵守的调用顺序

本 Skill 必须按以下顺序调用子 skill，不得跳序：

1. `j6-plugin-quantization`（路径：`j6-plugin-quantization/SKILL.md`）— 量化流程
2. `j6-hbdk-export-compile`（路径：`j6-hbdk-export-compile/SKILL.md`）— 导出编译流程

以 `export` 为界：export 之前属于量化，export 及之后属于导出编译。

## 为什么必须按这个顺序

### 1) `j6-plugin-quantization`（量化）

先完成量化流程，产出校准后或 QAT 训练后的模型。量化流程包括：

- `set_march` — 设置目标平台
- 定义模型（含 Quant/DeQuant 边界）— 插入部署边界节点
- 配置量化参数 — 根据 march 选择全局激活类型和 observer
- `prepare` — 插入伪量化节点
- 校准（CALIBRATION）— 使用 HistogramObserver 收集统计信息
- QAT 训练（可选）— 使用 MinMaxObserver 重新 prepare 后训练

量化流程的输出取决于用户选择：
- 仅校准：输出 `calib_net`
- 校准 + QAT：输出 `qat_net`

### 2) `j6-hbdk-export-compile`（导出编译）

基于量化流程产出的 QAT 模型，完成导出编译：

- `export` — 切换到 VALIDATION 状态后导出 QAT BC
- `convert` — 转换为量化模型
- `remove_io_op` — 删除首尾 Quantize/Dequantize 算子
- `statistics` — 检查 CPU 算子
- `compile` — 编译生成 HBM

## 各子 skill 的职责边界

### A. `j6-plugin-quantization`

负责：
- 设置 march
- 在模型中插入 QuantStub/DeQuantStub 部署边界
- 配置量化参数（全局激活类型、observer、Conv/Matmul dtype）
- 执行 prepare、校准
- 询问用户是否进行 QAT 训练（可选）

关键约束：
- 校准用 HistogramObserver，QAT 训练用 MinMaxObserver
- qconfig_setter 只能通过 prepare 传入，QAT 需要重新 prepare 浮点模型
- Quant/DeQuant 每个输入/输出独立 stub，不设置 scale

### B. `j6-hbdk-export-compile`

负责：
- 切换到 VALIDATION 状态并导出 QAT BC（接收 `calib_net` 或 `qat_net`）
- 将 QAT BC 转换为量化模型
- 删除首尾量化/反量化节点
- 检查是否存在 CPU 算子
- 编译生成 HBM

关键约束：
- remove_io_op 必须执行，否则 BPU 无法正确运行
- statistics 检查有 hbtl 打印警告，但仍继续执行后续流程

## 标准执行流程

### 第一步：确认是否是完整量化编译需求

符合以下描述时，应触发本 Skill：
- "帮我生成量化编译全流程代码"
- "基础结构量化部署"
- "Conv+BN+ReLU+Linear 量化编译"

如果用户只需要量化（不编译），或只需要编译（已有 QAT BC），则直接调用对应子 skill。

### 第二步：确认 march

在调用子 skill 前，必须先确认用户的 march（目标平台）。如果用户未指定，暂停流程并询问：

向用户提供以下选项：

| march | 平台 | 说明 |
|-------|------|------|
| `"nash-p"` | J6P | 推荐，全局激活支持 float16 |
| `"nash-h"` | J6H | 全局激活支持 float16 |
| `"nash-m"` | J6M | 全局激活为 qint8 |
| `"nash-e"` | J6E | 全局激活为 qint8 |
| `"nash-b"` | J6B | 全局激活为 qint8 |

march 未确认前，不应继续后续步骤。

### 第三步：确认是否进行 QAT 训练

在调用子 skill 前，必须询问用户校准后的流程选择：

| 选项 | 说明 |
|------|------|
| 仅校准（calib-only） | 校准后直接导出，速度快，适合精度要求不高的场景 |
| 校准 + QAT 训练（calib+qat） | 校准后重新 prepare 并进行 QAT 训练，精度更高，推荐用于精度敏感场景 |

### 第四步：依次调用子 skill

严格按顺序：
1. `j6-plugin-quantization` — 产出 `calib_net`（仅校准）或 `qat_net`（校准+QAT）
2. `j6-hbdk-export-compile` — 使用产出的模型，产出 HBM

### 第五步：完成后做整体一致性检查

- march 在两个子 skill 中一致
- 量化流程产出的 `qat_net` 被导出编译流程正确使用
- 最终 HBM 文件生成成功

## 代码生成格式规范

生成的代码 **必须严格遵循** `references/full-pipeline-template.md` 的格式。以下规则不可违反：

### 规则 1：统一脚本格式

生成的代码必须是 **单个统一的 Python 脚本**，包含从 `set_march` 到 `compile HBM` 的完整线性流程。不要拆分为多个文件或多个阶段脚本。

### 规则 2：强制函数包裹

生成的代码 **必须** 使用 `run_quantization_pipeline(march)` 函数包裹全流程逻辑，模型类定义在函数外部，所有流程代码（set_march、创建模型、量化配置、prepare、校准、export、convert、remove_io_op、statistics、compile）放在函数体内。**禁止**生成脚本式平铺代码（顶层直接写 `march = "nash-b"` / `set_march(march)` / `model = MyNet()` 等语句）。

正确格式参见 `references/full-pipeline-template.md`，结构如下：

```python
# 导入块（文件顶部）

# 模型类定义（函数外部）
class MyNet(nn.Module):
    ...

# 流程函数（必须）
def run_quantization_pipeline(march="nash-p"):
    set_march(march)
    model = MyNet()
    ...
    # 全部流程代码

if __name__ == "__main__":
    run_quantization_pipeline()
```

**禁止**的格式：
```python
# 顶层平铺（错误！）
march = "nash-b"
set_march(march)
model = MyNet()
...
```

### 规则 3：禁止在代码中展示子 skill 调用标签

代码中 **不得** 出现子 skill 调用标签，如 `"Sub Skill 1: j6-plugin-quantization"`、`"子 Skill 1"` 等。流程分段只能使用模板中的注释格式：

```python
# ===== j6-plugin-quantization: 量化流程 =====
# ===== j6-hbdk-export-compile: 导出编译流程 =====
```

### 规则 4：统一导入块

所有 import 语句必须在文件顶部 **合并为一个导入块**，不得按子 skill 拆分为多个导入段落。导入语句必须与 `references/full-pipeline-template.md` 完全一致：

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
from horizon_plugin_pytorch.quantization.hbdk4 import export
from horizon_plugin_pytorch.quantization.observer_v2 import HistogramObserver, MinMaxObserver
from horizon_plugin_pytorch.quantization.qconfig_setter import (
    ModuleNameTemplate, ConvDtypeTemplate, MatmulDtypeTemplate,
)
from hbdk4.compiler import convert, compile, statistics, save
```

### 规则 5：导入路径不可偏离

以下导入路径是固定的，**禁止使用其他路径**：

- `export` **必须** 从 `horizon_plugin_pytorch.quantization.hbdk4` 导入
- `convert, compile, statistics, save` **必须全部** 从 `hbdk4.compiler` 导入
- **禁止** 从 `horizon_plugin_pytorch.quantization` 或 `horizon_plugin_pytorch` 导入上述函数

### 规则 6：API 参数不可省略

以下 API 调用的参数 **必须与模板完全一致，不得省略或留空**：

1. **`ConvDtypeTemplate(input_dtype=qint8, weight_dtype=qint8)`** — 两个参数都不可省略，不得写成 `ConvDtypeTemplate()`
2. **`MatmulDtypeTemplate(input_dtypes=[qint8, qint8])`** — 参数不可省略，不得写成 `MatmulDtypeTemplate()`
3. **`func.remove_io_op(op_types=["Dequantize", "Quantize"])`** — 必须先取 `quantized_model.functions[0]` 得到 func，再调用 `func.remove_io_op(op_types=[...])`。禁止直接对 model 调用 `remove_io_op()`，禁止省略 `op_types` 参数
4. **`prepare(model, (example_input,), qconfig_setter=qconfig_setter)`** — 第二个参数 `(example_input,)` 不可省略
5. **`convert(qat_bc, march)`** — `march` 参数不可省略
6. **`compile(quantized_model, hbm_name, march, opt=2, jobs=64, progress_bar=True, debug=False)`** — 所有参数不可省略，不得写成 `compile(model)`

### 规则 7：march 未指定时的默认值

当用户未指定 march 时（如 eval 场景无法交互），使用 `"nash-p"` 作为默认值，并在代码注释中标注：

```python
def run_quantization_pipeline(march="nash-p"):  # 默认 nash-p，用户未指定时使用
```

**不得**自行选择其他 march（如 `nash-b`），除非用户明确指定。

## 关键输入说明

| 输入 | 是否必须 | 说明 |
|------|---------|------|
| 目标平台（march） | 必须 | 从 nash-p / nash-h / nash-m / nash-e / nash-b 中选择，影响全局激活类型 |
| 是否进行 QAT 训练 | 必须 | 校准后直接导出（calib-only）还是校准+QAT 训练再导出（calib+qat） |
| 模型结构 | 可选 | 浮点网络结构描述，默认 Conv+BN+ReLU+Linear |
| 输入 shape | 可选 | 模型输入张量维度，默认 (1, 3, 32, 32) |
| 自定义量化配置 | 可选 | 是否需要指定某些层使用 qint16 等，默认不需要 |

## 关键输出说明

| 输出 | 说明 |
|------|------|
| 完整量化编译 Python 代码 | 一份从 set_march 到 compile HBM 的可运行脚本 |
| 中间产物 | calib_net 或 qat_net（量化模型）、quantized.bc / quantized_remove.bc（BC 文件） |
| 最终产物 | HBM 文件，可直接部署到目标平台 |
| CPU 算子检查结果 | statistics 输出，标注是否存在 hbtl（CPU 算子） |

## 适用场景

- 从零开始生成基础结构的量化编译全流程代码
- 用户需要完整的 set_march → HBM 代码

## 不适用场景

- 只需要量化流程 → 直接调用 `j6-plugin-quantization`
- 只需要导出编译流程（已有 QAT 模型）→ 直接调用 `j6-hbdk-export-compile`
- 模型有动态控制流 → 本 skill 不覆盖 dynamic_block 场景，需要额外处理

## 快速自检清单

- 用户已明确指定 march（未指定时默认 `nash-p`，不得自选其他值）
- 是否按顺序调用了 `j6-plugin-quantization` → `j6-hbdk-export-compile`？
- 量化流程产出的 `qat_net` 是否被导出编译流程正确使用？
- 两个子 skill 中的 march 是否一致？
- 代码是否使用 `run_quantization_pipeline(march)` 函数包裹？（禁止脚本式平铺）
- `ConvDtypeTemplate(input_dtype=qint8, weight_dtype=qint8)` 参数是否完整？（禁止 `ConvDtypeTemplate()` 无参调用）
- `MatmulDtypeTemplate(input_dtypes=[qint8, qint8])` 参数是否完整？（禁止 `MatmulDtypeTemplate()` 无参调用）
- `remove_io_op` 是否通过 `func = quantized_model.functions[0]` + `func.remove_io_op(op_types=["Dequantize", "Quantize"])` 调用？（禁止 `model.remove_io_op()` 直接调用）
- `convert` 是否传入了 march 参数？
- `compile` 是否传入了完整的参数列表？

## 参考文件索引

| 文件 | 说明 |
|------|------|
| `references/full-pipeline-template.md` | 两个子 skill 合并后的完整端到端代码模板 |
| `examples/examples.md` | 使用示例和触发场景说明 |
