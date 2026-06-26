# Horizon 完整 QAT 适配 Skill - 使用示例

本示例文档说明何时应触发 `j6-plugin-adaptation`，以及 agent 应如何按固定顺序编排多个子 skill，为浮点模型完成 Horizon QAT 适配。

## 触发方式

以下类型的 prompt 会触发该 skill：

### 直接触发（明确要求完整适配 horizon_plugin_pytorch）

```text
帮我把这个浮点模型完整适配到 horizon_plugin_pytorch 的 QAT 流程
```

```text
按地平线量化链路把 @test.py 改好，包括 march、quant/dequant、prepare 和 fake quantize
```

```text
给这个模型做完整的 Horizon QAT adaptation
```

### 间接触发（描述“从浮点模型接入 Horizon QAT”）

```text
这个模型现在只是普通 PyTorch 浮点模型，我要让它能走地平线机器人的 QAT 工具链
```

```text
请按 Horizon 的要求把这个网络改造成可 calibration / qat / validation 的模型
```

### 隐式触发（要求按多个子步骤顺序协同适配）

```text
把这个模型按标准流程接到 horizon_plugin_pytorch，顺序你来安排
```

---

## Prompt 中需要包含的关键信息

### 必须提供的信息

| 信息 | 说明 | 示例 |
|------|------|------|
| 目标文件/目标模型 | 要修改哪个文件/类/入口脚本 | `@test.py` / `@tools/train.py` |
| 是否是完整适配 | 明确不是只做某一步 | “完整适配 Horizon QAT” |

### 需要进一步确认的信息

| 信息 | 是否必须先确认 | 说明 |
|------|----------------|------|
| `march` | **必须** | 没确认前不能进入第一步之后的流程 |
| 部署输入/输出边界 | 通常需要 | 决定 quant/dequant 如何插入 |
| 是否存在动态控制流 | 需要结合代码判断 | 决定是否用 `j6-plugin-dynamic-block` |
| 当前阶段目标 | calibration / qat / validation | 决定 fake quantize 状态 |

---

## 关键行为：严格按子 skill 顺序执行

当用户请求完整 Horizon QAT 适配时，agent 不应跳着做，而应按以下顺序：

1. `j6-plugin-set-march`
2. `j6-plugin-insert-quant-dequant`
3. `j6-plugin-dynamic-block`
4. `j6-plugin-prepare`
5. `j6-plugin-set-fake-quantize`

这个顺序不能随意打乱。

---

## 完整使用流程示例

### 示例 1：用户要求完整适配，但还没说 march

**用户 Prompt：**

```text
帮我把 @test.py 完整适配到 horizon_plugin_pytorch 的 QAT 流程。
```

**正确执行方式：**

agent 首先识别这是一个“完整 QAT 适配”需求，然后立刻进入第一步 skill：`j6-plugin-set-march`。

此时因为 march 还没给，必须先问：

```text
你想使用哪个 march？
例如：
- horizon.march.March.NASH_E
- horizon.march.March.NASH_P
- horizon.march.March.NASH_B
```

在用户没有回答 march 之前，不应继续做 `QuantStub/DeQuantStub`、`prepare` 或 fake quantize。

---

### 示例 2：用户已经给了 march，要求一步完成

**用户 Prompt：**

```text
把 @test.py 适配成 Horizon QAT 模型，march 用 NASH_P。
```

**Agent 执行顺序：**

1. 调用 `j6-plugin-set-march`
   - 在脚本入口、模型构建前插入：
   ```python
   horizon.march.set_march(horizon.march.March.NASH_P)
   ```

2. 调用 `j6-plugin-insert-quant-dequant`
   - 在模型输入边界加 `QuantStub`
   - 在模型输出边界加 `DeQuantStub`

3. 调用 `j6-plugin-dynamic-block`
   - 若 `forward` 中有动态循环/动态分支，并且块内有 Tensor/function 逻辑，则加 `Tracer.dynamic_block(...)`

4. 调用 `j6-plugin-prepare`
   - 用 `prepare(...)` 生成 QAT 模型

5. 调用 `j6-plugin-set-fake-quantize`
   - 根据目标阶段设置 `QAT/CALIBRATION/VALIDATION`

---

### 示例 3：用户只要求某一个子步骤，不该触发本 Skill

**用户 Prompt：**

```text
给这个模型插入 QuantStub/DeQuantStub
```

**正确行为：**

这时不应该触发 `j6-plugin-adaptation`，而应该直接调用：

- `j6-plugin-insert-quant-dequant`

因为这只是局部需求，不是完整适配链路。

---

## 最小执行模板（调度思维，不是代码模板）

当识别到完整适配需求时，agent 应按这种思路工作：

```text
Step 1. 调用 j6-plugin-set-march
Step 2. 调用 j6-plugin-insert-quant-dequant
Step 3. 调用 j6-plugin-dynamic-block
Step 4. 调用 j6-plugin-prepare
Step 5. 调用 j6-plugin-set-fake-quantize
```

而不是直接一次性说：

```text
我会帮你把所有东西都加进去
```

却没有体现阶段、顺序和依赖关系。

---

## 失败/返工场景示例

### 场景 1：还没确认 march 就先做 prepare

**问题：**
- 破坏 skill 顺序
- 后续平台相关逻辑可能落在错误 march 上

**正确做法：**
- 先完成 `j6-plugin-set-march`
- 再进入后续步骤

### 场景 2：先 prepare，后面再补 quant/dequant 或 dynamic_block

**问题：**
- 这会违背 `j6-plugin-prepare` 的结构稳定性约束
- prepare 之后再改结构，容易导致图/scale/hook 相关问题

**正确做法：**
- 所有结构性修改（quant/dequant、dynamic_block）都必须在 prepare 前完成

### 场景 3：把本 Skill 当成“自动 patch 所有内容”的大杂烩

**问题：**
- 会忽略子 skill 的细粒度约束
- 容易跳过关键确认步骤（尤其是 march）

**正确做法：**
- 始终显式按子 skill 分步执行

---

## 快速自检清单

- 用户需求是否真的是“完整 Horizon QAT 适配”？
- march 是否已经确认？
- 是否按顺序执行了 5 个子 skill？
- quant/dequant 和 dynamic block 是否在 prepare 前完成？
- fake quantize 是否根据当前阶段设置正确？
- 如果只是局部需求，是否避免误触发整个 `j6-plugin-adaptation`？
