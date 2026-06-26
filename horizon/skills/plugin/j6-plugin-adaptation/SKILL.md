---
name: j6-plugin-adaptation
description: 为用户的浮点 PyTorch 模型适配地平线机器人公司的 QAT 工具 `horizon_plugin_pytorch`。这是一个编排型 skill，必须按固定顺序依次调用：`j6-plugin-set-march` → `j6-plugin-insert-quant-dequant` → `j6-plugin-dynamic-block` → `j6-plugin-prepare` → `j6-plugin-set-fake-quantize`。
---

# 为浮点模型执行完整 Horizon QAT 适配（组合调度版）

## 目标

把一个普通的**浮点 PyTorch 模型**，按地平线机器人公司的 `horizon_plugin_pytorch` 量化工具链要求，逐步改造成可进入 QAT / calibration / validation 流程的模型。

这个 Skill **不是单独做某一步改动**，而是一个**总控/编排类 skill**。它负责根据用户需求，将完整适配过程拆成多个标准子 skill，并**严格按照固定顺序执行**。

## 必须遵守的调用顺序

本 Skill 必须按以下顺序调用目录下的 skill，不得跳序：

1. `j6-plugin-set-march`
2. `j6-plugin-insert-quant-dequant`
3. `j6-plugin-dynamic-block`
4. `j6-plugin-prepare`
5. `j6-plugin-set-fake-quantize`

## 为什么必须按这个顺序

### 1) `j6-plugin-set-march`

先设置 `march`，让后续模型构建、prepare、量化逻辑和平台相关分支都在正确的目标平台上下文中执行。

### 2) `j6-plugin-insert-quant-dequant`

在部署输入/输出边界插入 `QuantStub/DeQuantStub`，明确量化图边界。后续 prepare 依赖这些边界信息感知部署范围。

### 3) `j6-plugin-dynamic-block`

处理动态控制流中可能触发 function 替换或算子融合的区域。必须在 prepare 前处理，否则 prepare/JIT_STRIP 阶段可能产生 scope 错乱或 forward 报错。

### 4) `j6-plugin-prepare`

对浮点模型执行 `prepare(...)`，把模型变成 QAT 模型。prepare 之后不应再随意改模型结构、hook 或动态图 scope 逻辑。

### 5) `j6-plugin-set-fake-quantize`

在 calibration / qat / validation 阶段入口设置对应的 fake quantize 状态。这一步依赖模型已经具有 prepare 后的 QAT 结构。

---

## 这个 Skill 具体负责什么

当用户表达“让我这个浮点模型适配 `horizon_plugin_pytorch`”时，本 Skill 应：

1. 识别目标模型文件/类/脚本入口。
2. 依次调用下列子 skill：
   - `j6-plugin-set-march`
   - `j6-plugin-insert-quant-dequant`
   - `j6-plugin-dynamic-block`
   - `j6-plugin-prepare`
   - `j6-plugin-set-fake-quantize`
4. 在每一步都遵守对应 skill 的约束，而不是把所有逻辑揉成一次性粗暴修改。

---

## 各子 skill 的职责边界

### A. `j6-plugin-set-march`

负责：

- 询问用户想使用哪个 `march`
- 在脚本入口、模型构建前插入：

```python
horizon.march.set_march(...)
```

关键约束：

- 如果用户未给出 march，必须先询问，不能擅自假设。

---

### B. `j6-plugin-insert-quant-dequant`

负责：

- 在部署输入边界插入 `QuantStub`
- 在部署输出边界插入 `DeQuantStub`

关键约束：

- 每个输入/输出使用独立 stub
- `QuantStub()` 不设置 `scale`
- 只在部署边界插入，不提前 dequant

---

### C. `j6-plugin-dynamic-block`

负责：

- 为动态控制流中、会触发 function 替换/算子融合的非 module scope 逻辑添加 `dynamic_block`

关键约束：

- 只包需要替换/融合的逻辑块，不包整个循环
- 不对已经是 `nn.Module.forward` scope 的子模块调用重复包 dynamic_block

---

### D. `j6-plugin-prepare`

负责：

- 调用 `prepare(...)` 把浮点模型变成 QAT 模型

关键约束：

- 只加 prepare 调用
- prepare 之后不要再改结构/hook

---

### E. `j6-plugin-set-fake-quantize`

负责：

- 在 Calibration / QAT / Validation 阶段设置 fake quantize 状态

关键约束：

- Calibration：`CALIBRATION`
- QAT：`QAT`
- Validation：`VALIDATION`
- Validation 前先 `model.eval()`，再 `set_fake_quantize`

---

## 标准执行流程（组合 Skill 模板）

### 第一步：确认是否是完整 QAT 适配需求

符合以下描述时，应触发本 Skill：

- “帮我把这个浮点模型适配成 horizon_plugin_pytorch 的 QAT 模型”
- “按地平线量化工具链把这个模型改好”
- “我要做 Horizon QAT，帮我把模型接上完整适配流程”

### 第二步：确认 march（必须先于其他步骤）

如果用户没有给具体 march，先暂停整个流程并询问：

- 你想使用哪个 `march`？

在 march 没确认前，不应继续后面的 skill。

### 第三步：依次执行子 skill

严格按顺序：

1. `j6-plugin-set-march`
2. `j6-plugin-insert-quant-dequant`
3. `j6-plugin-dynamic-block`
4. `j6-plugin-prepare`
5. `j6-plugin-set-fake-quantize`

### 第四步：完成后做整体一致性检查

检查至少包括：

- march 是否在模型构建/prepare 前设置
- quant/dequant 是否只在部署边界
- dynamic block 是否只标注了必要区域
- prepare 是否在所有结构性改动之后执行
- fake quantize 状态是否与当前阶段一致

---

## 适用场景

本 Skill 适用于：

- 从零开始把一个浮点模型接入 Horizon QAT 工具链
- 你已经明确要使用 `horizon_plugin_pytorch`
- 需要 agent 按标准顺序自动补齐适配步骤
- 希望多个子 skill 协同工作，而不是手动逐个触发

---

## 不适用场景

以下情况不应直接使用本 Skill，或者应拆分使用：

- 只想设置 `march`
- 只想补 `QuantStub/DeQuantStub`
- 只想做 `prepare`
- 只想设置 fake quantize 状态
- 模型已经是 QAT 模型，不再是浮点模型
- 用户只要求某一个局部适配动作，而不是完整链路

如果只是单步需求，应直接调用对应子 skill，不必走总控 skill。

---

## 关键注意事项

### 1) 这是“编排 skill”，不是“大杂烩 patch skill”

本 Skill 的重点是**顺序和边界**。不要不分主次地一次性往目标文件里乱塞所有改动；要按子 skill 的职责逐步落地。

### 2) march 未确认时，流程必须暂停

由于 `j6-plugin-set-march` 的硬约束是先问用户 march，所以整个完整适配流程也必须继承这一约束。

### 3) prepare 之后不要再继续做结构性改动

因此：

- quant/dequant 插入
- dynamic block 补齐

都必须在 `prepare` 之前完成。

### 4) fake quantize 状态设置是“阶段行为”，不是单纯静态代码插桩

如果用户同时要求支持 calibration / qat / validation，agent 应根据目标脚本阶段把状态设置在正确位置，而不是机械地只写一处。

### 5) 子 skill 的约束优先级高于本 Skill 的简化描述

如果本 Skill 与某个子 skill 的细则冲突，以子 skill 为准。例如：

- `j6-plugin-set-march` 要求先询问用户 march
- `j6-plugin-insert-quant-dequant` 要求每个输入输出独立 stub
- `j6-plugin-dynamic-block` 要求不要包整个循环

### 6) 本 Skill 默认采用“强依赖接入”，禁止兼容性兜底写法

当用户要求把浮点模型适配为 `horizon_plugin_pytorch` 的 QAT 模型时，默认前提是：

- 目标环境已经安装并可直接导入 `horizon_plugin_pytorch`
- 用户要的是**正式接入 Horizon 工具链**，不是保留“没有 Horizon 也能运行”的兼容路径

因此必须遵守以下硬约束：

- **禁止**使用 `try/except ImportError` 为 `horizon_plugin_pytorch` 或其相关模块做导入兜底
- **禁止**在导入失败时把模块、类或函数设为 `None`
- **禁止**使用 `nn.Identity()`、空函数、空模块等方式替代 `QuantStub`、`DeQuantStub`、`prepare`、`dynamic_block`、`set_fake_quantize`
- **禁止**为了兼容未知版本 API，编写基于 `getattr(..., None)`、多命名空间回退、异常后重试的探测式逻辑
- Horizon 相关接口应基于目标版本的明确 API 直接导入、直接调用
- 如果依赖缺失、导入失败或 API 不匹配，应直接报错，不要静默降级或回退到普通浮点路径

### 7) 代码修改风格应偏向“直接接入”，不要保留双模式路径

除非用户明确要求保留浮点兼容路径，否则：

- 不要同时维护“普通 PyTorch 路径”和“Horizon QAT 路径”两套并行分支
- 不要为了让脚本在非目标环境继续运行而额外加入保护性分支
- 对 Horizon 必需步骤，宁可硬失败，也不要通过 fallback 隐藏配置或环境问题
- 适配代码应尽量直接、确定、单路径，避免“先尝试 A，再回退 B”的写法

---

## 快速自检清单

- 是否确认了用户要做的是“完整 Horizon QAT 适配”？
- 是否已经先确认用户的 march？
- 是否按顺序调用了：
  - `j6-plugin-set-march`
  - `j6-plugin-insert-quant-dequant`
  - `j6-plugin-dynamic-block`
  - `j6-plugin-prepare`
  - `j6-plugin-set-fake-quantize`
- 是否确保所有结构性改动都发生在 `prepare` 前？
- 是否根据阶段正确设置了 fake quantize 状态？
