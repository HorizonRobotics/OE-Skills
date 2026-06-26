---
name: j6-plugin-model-check-result
description: 在 horizon_plugin_pytorch 量化配置检查中，读取并分析 prepare 产出的 model_check_result.txt，定位模型结构与 qconfig 问题（算子融合、共享模块、qconfig 异常、averaging_constant 非默认值、算子输入浮点检查）。
---

# 分析 Horizon `model_check_result.txt`（模型结构与量化配置检查）

## 目标

在模型完成 `prepare(...)` 后，基于运行目录中的 `model_check_result.txt`，快速发现并解释以下四类问题：

1. 算子融合异常（可融合但未融合）
2. 共享模块风险（同一 module 多次调用）
3. qconfig 配置异常（dtype/高精度输出/可疑 qconfig）
4. averaging_constant 非默认值（observer 的 averaging_constant != 0.01）
5. 算子输入浮点检查（非 QuantStub/DeQuantStub 算子的输入为浮点类型）

本 Skill 聚焦“**检查结果解读与修复建议**”，用于连接 prepare 之后的排查阶段。

## 背景约束（必须知道）

- `prepare` 已集成 `check_qat_model`；通常不需要额外手动调用，直接查看 `model_check_result.txt` 即可。
- 该检查工具会给出“需要你复核”的线索，并非每条提示都一定是错误。
- 真正是否需要修改，必须结合模型拓扑、部署边界、精度对比结果综合判断。

## 本 Skill 强约束

- **只做结果分析与修复路径建议**：不擅自改动大量模型结构。
- **先读结果再下结论**：必须依据 `model_check_result.txt` 中的具体表格与条目，不做臆测。
- **分五块输出结论**：
  1) 融合问题
  2) 共享问题
  3) qconfig 问题
  4) averaging_constant 非默认值提示
  5) 算子输入浮点检查提示
- **给出“是否必改”的判断等级**：
  - 高优先级（明确错误/高风险）
  - 中优先级（可能影响精度/性能）
  - 低优先级（提示项，需业务确认）

## 重点检查项与判定标准

### 1) 算子融合检查（Fusable modules）

关注 `Fusable modules are listed below:` 段落。

若存在未融合模块，常见原因如下：

- 动态代码块里涉及替换/融合逻辑，但缺少 `dynamic_block` 标注
- 未融合模块为共享模块。

输出建议时要明确：

- 这是“结构正确性 + 性能/精度”问题，不一定每个未融合都必须改
- 若未融合位置伴随共享或动态逻辑，应优先处理

### 2) 共享模块检查（Each module called times）

关注 `Each module called times:` 段落。

基础判定：

- `called times = 1`：正常
- `called times = 0`：未调用（需检查是否死分支/配置问题）
- `called times > 1`：共享调用

关键解释：

- “共享调用”本身不必然错误
- 只有当多次调用的数据分布差异明显时，才容易因共用一组量化参数导致较大误差

建议流程：

从 `called times > 1` 列出候选模块，建议用户自行排查决定是否需要拆分共享模块

### 3) qconfig 正确性检查

重点看以下内容：

- `Each layer out qconfig:`
- `Weight qconfig:`
- `input/output dtype statistics:`
- `Please check if these OPs qconfigs are expected.`

高精度输出判定标准：

检查每个 `DeQuantStub` 的输入 dtype，按以下三级判定：

- **DeQuantStub 输入为 `torch.float32`**：✅ 高精度浮点输出路径已生效。上游算子输出 fp32 直连 DeQuantStub，说明该路径保持了浮点精度。标注为正常行为。
- **DeQuantStub 输入为 `qint16`**：✅ 高精度量化输出已开启。上游算子使用 qint16（相比 qint8 提供更高量化精度）进行量化，DeQuantStub 将 qint16 反量化为 float32 是标准的高精度量化输出链路。标注为正常行为，说明模型已开启高精度量化配置。
- **DeQuantStub 输入为 `qint8`**：ℹ️ 标准 int8 量化输出。这是常规的 int8 量化配置，DeQuantStub 将 qint8 反量化为 float32 是标准的反量化行为。无异常，但也不属于高精度输出。

常见异常模式：

- DeQuantStub 输入为 qint8 但用户期望高精度输出：需提示用户检查 qconfig 中是否正确设置了 qint16 或 fp32 的高精度输出 dtype
- Fixed scale / 可疑 qconfig 提示（不一定错，但必须复核）

判断原则：

- 工具提示是“需要检查”，不是“必错”。

### 4) averaging_constant 非默认值检查

在 `Each layer out qconfig` 和 `Weight qconfig` 表格中，检查各 observer 的 `averaging_constant` 值。

**默认值为 0.01**。若存在 `averaging_constant != 0.01` 的模块，需给出提示。

判定标准：

- `averaging_constant = 0.01`：默认值，正常
- `averaging_constant != 0.01`：非默认值，需提示用户确认是否有意为之

输出要求：

- 列出所有 `averaging_constant != 0.01` 的模块名称、类型、当前值
- 提示用户：该值偏离默认值 0.01，请确认是否为有意设置
- 特别注意 `averaging_constant=0` 的情况（等价于关闭滑动平均，observer 仅使用当前 batch 的 min/max）

### 5) 算子输入浮点检查

关注 `input/output dtype statistics:` 段落以及 `Each layer out qconfig:` 表格中各算子的输入 dtype 信息。

在量化模型中，算子的输入应为量化后的整型（如 `torch.quint8`、`torch.qint8`），而非浮点类型（`torch.float32`）。

**例外情况**：

1. `QuantStub`/`DeQuantStub` 本身承担浮点↔量化的边界转换职责，它们的输入/输出为浮点类型是正常的，不属于异常。
2. Conv/Linear 与 ReLU 的融合：在某些融合模式下，Conv/Linear 输出 `torch.float32` 且紧接的 ReLU 输入为 `torch.float32`，这是融合实现的正常中间态，不属于异常。此时表明 Conv+ReLU 已完成融合，中间以 fp32 传递是预期行为。

**判定标准**：

- `QuantStub`/`DeQuantStub` 的输入为 `torch.float32`：正常，无需提示
- Conv/Linear 输出 `torch.float32` 且下游 ReLU 输入 `torch.float32`（构成融合对）：正常，属于融合实现的中间态，无需提示
- 其他算子的输入为 `torch.float32`：异常，需提示用户检查 qconfig 配置是否符合预期
- 其他算子的输入为量化整型：正常

**异常原因推断**：

- 该算子未被正确配置 qconfig，导致输入未经过量化
- 上游算子的 qconfig 缺失或配置错误，导致输出仍为浮点
- 量化边界（QuantStub/DeQuantStub）位置不合理，浮点区域覆盖了本应量化的算子

**输出要求**：

- 列出所有非 QuantStub/DeQuantStub 且输入为 `torch.float32` 的算子名称、类型
- 提示用户：该算子的输入为浮点类型，请检查其 qconfig 配置是否符合预期
- 建议用户检查该算子及其上游链路的 qconfig 是否完整

## 标准分析模板（建议输出结构）

### A. 检查输入

- prepare method：`JIT_STRIP`
- 检查文件：`model_check_result.txt`
- 当前阶段：calibration/QAT/validation（可选）

### B. 四块结论

1. 融合检查结论
   - 未融合模块列表（按 block 聚合）
   - 原因推断（dynamic_block / 共享模块）

2. 共享检查结论
   - `called times > 1` 模块列表

3. qconfig 检查结论
   - DeQuantStub 输入 dtype 判定：`torch.float32` = 高精度浮点输出 ✅ / `qint16` = 高精度量化输出 ✅ / `qint8` = 标准 int8 输出 ℹ️
   - 异常 qconfig 提示是否需要人工确认

4. averaging_constant 非默认值提示
   - 列出 `averaging_constant != 0.01` 的模块及当前值
   - 提示用户确认是否为有意设置

5. 算子输入浮点检查提示
   - 列出非 QuantStub/DeQuantStub 且输入为 `torch.float32` 的算子
   - 提示用户检查这些算子的 qconfig 配置是否符合预期

### C. 具体改动建议（最小集）

- 只给最小必要改动，不做大规模“全量重构”建议
- 每条建议都要绑定证据（来自哪一段检查结果）

## 适用场景

- 模型已经执行过 `prepare(...)`
- 需要解读 `model_check_result.txt`
- calibration 或 QAT 后精度异常，需要优先排结构与配置问题

## 不适用场景

- 模型尚未 prepare（没有 `model_check_result.txt`）
- 用户要求直接写 quant/dequant、prepare 等代码（应转对应 skill）
- 只做运行脚本整理，不涉及量化检查

## 常见坑（按本 Skill 直接规避）

- 把“提示项”当“必错项”
- 看到共享模块就全部拆分，导致改动过大
- 只给结论不给证据（无法复核）

## 快速自检清单

- 已基于 `model_check_result.txt` 输出五块结论：融合/共享/qconfig/averaging_constant/算子输入浮点检查。
- 每条结论都引用了具体检查项（表格或段落）。
- 给出的修复建议是最小必要改动，并且可执行。
- 对于 `averaging_constant != 0.01` 的模块，已列出并提示用户确认。
