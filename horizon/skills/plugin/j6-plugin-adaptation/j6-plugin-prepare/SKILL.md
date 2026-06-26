---
name: j6-plugin-prepare
description: 在适配 horizon_plugin_pytorch 的过程中对浮点模型执行 prepare（仅添加 prepare 调用；qconfig_setter 固定为全部双 int8 模板；不包含 dynamic_block 相关修改）。
---

# 给浮点模型添加 Horizon prepare（仅 prepare 调用版）

## 目标

把已有的 **浮点** `torch.nn.Module` 接入 `horizon_plugin_pytorch` 的 QAT 工具链：在代码中对模型执行 `prepare(...)`，得到可训练的 QAT 模型（含伪量化/qat 算子等变换）。

本 Skill 强约束：

- **只加 prepare**：仅新增/调整 `prepare(...)` 调用与必要 import，不做其它结构性改造。
- **不处理 dynamic_block**：不引入/不修改任何 `dynamic_block` / `Tracer.dynamic_block` 相关逻辑（动态控制流场景需要单独处理，不属于本 skill）。
- **qconfig_setter 固定**：一律使用“全部双 int8”模板构造的 `QconfigSetter`，不叠加其它 setter，不做敏感算子表等策略。

## prepare 会做什么（你需要知道的关键点）

基于图的 prepare（例如 `PrepareMethod.JIT_STRIP`）通常会：

- 捕获并裁剪计算图（会根据 `QuantStub/DeQuantStub` 位置识别并跳过前后处理）
- 替换部分 function 类算子为 module 形式（便于在 module 内插入伪量化等逻辑）
- 进行可融合 pattern 的算子融合
- 将浮点算子转换为 qat 算子，并按 qconfig 插入伪量化/伪转换节点
- 执行 QAT 模型结构检查并生成检查结果文件

## 标准改法（通用模板）

### 1) 增加 import

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
```

### 2) 选择 method，并准备 example_inputs

- 推荐默认用 `PrepareMethod.JIT_STRIP`
- 当 method 为 `PrepareMethod.JIT_STRIP` 或 `PrepareMethod.JIT` 时，**必须提供** `example_inputs`
- `example_inputs` 的目的：用于感知图结构，且应当能跑通目标 forward（通常用 eval/infer 路径）

### 3) 构造全双 int8 的 qconfig_setter，并调用 prepare

```python
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

### 4) 重要约束与注意事项（直接按这个执行）

- **prepare 之后不要再改模型结构**：prepare 会替换/融合/转换算子，之后再改模型（例如把 BN 改成 SyncBN）可能导致 qat 算子被再次修改，出现不可预期行为。
- **prepare 之后不要改任何 hook**：基于图的 function→module 替换依赖 hook 与特殊 wrapper tensor 机制；改动 hook 可能导致替换失效，进而报错或产生精度问题。
- **尽量只对“部署逻辑”做 prepare**：如果一个 `forward` 同时混入训练/评测分支、CPU/Numpy 后处理等，容易导致量化边界或图捕获不符合部署预期。建议把部署推理逻辑剥离到 `forward_infer`（或等价函数）并对其进行 prepare。

## PrepareMethod 简要选择建议

| method | 原理（高层） | 适用 |
|-------|--------------|------|
| `PrepareMethod.JIT_STRIP`（Graph Mode） | 感知图结构，在原 forward 上做算子替换/融合/qat 转换，并按 Quant/DeQuant 边界裁剪 | **默认推荐**，自动化程度高 |
| `PrepareMethod.EAGER`（Eager Mode） | 不感知图结构，很多替换/融合需要手动处理 | 特殊需求/过程强可控场景 |

注：本 Skill 只负责把 `prepare(...)` 正确接入；method 的更深层细节与动态图特殊处理不在本 skill 范围内。

## 快速自检清单

- 代码中新增了 `prepare(...)` 调用，且产物是 `qat_model`（后续训练/保存/导出都基于它）。
- `qconfig_setter` **仅为**基于 `QconfigSetter(...)` 构造的“全部双 int8”模板。
- 模板包含 `ModuleNameTemplate({"": qint8})`、`ConvDtypeTemplate(input_dtype=qint8, weight_dtype=qint8)`、`MatmulDtypeTemplate(input_dtypes=qint8)`。
- `PrepareMethod.JIT_STRIP/JIT` 场景下提供了可跑通 forward 的 `example_inputs`。
- prepare 之后没有再做结构性改动，也没有改动模型 hook。
