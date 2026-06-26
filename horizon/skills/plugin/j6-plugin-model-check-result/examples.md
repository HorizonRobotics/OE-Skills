# Horizon `model_check_result` 分析 Skill - 使用示例

本示例文档说明何时触发 `j6-plugin-model-check-result`，以及如何基于 `model_check_result.txt` 给出可落地的排查结论。

## 触发方式

### 直接触发（明确提及 model_check_result / check_qat_model）

```text
帮我分析 model_check_result.txt，看看量化配置哪里有问题
```

```text
prepare 后精度掉了，按 model_check_result 做一轮结构和 qconfig 检查
```

```text
请解读 check_qat_model 输出，按融合/共享/qconfig 分类给建议
```

### 间接触发（描述 prepare 后的结构检查需求）

```text
我做完 jit-strip prepare 了，现在想先排查未融合和共享模块
```

```text
QAT 后精度不稳定，先帮我看下是不是 qconfig 配错了
```

---

## Prompt 中建议包含的信息

### 必须信息

| 信息 | 说明 | 示例 |
|------|------|------|
| 检查文件 | `model_check_result.txt` 路径或内容片段 | `./output/model_check_result.txt` |
| prepare method | 当前以 `JIT_STRIP` 为主 | `PrepareMethod.JIT_STRIP` |

### 强烈建议信息

| 信息 | 说明 | 示例 |
|------|------|------|
| 目标量化预期 | 用于判断 qconfig 是否正确 | “主干 int8，部分 matmul int16，高精度输出在 dequant 前” |
| 当前问题现象 | 帮助排序优先级 | “calibration 后 mAP 明显下降” |

---

## 完整使用流程示例

### 示例 1：JIT_STRIP 下未融合问题排查

**用户 Prompt：**

```text
这是 prepare(jit-strip) 后的 model_check_result.txt，
请重点看 Fusable modules，告诉我哪些是高优先级问题。
```

**Agent 应输出：**

1. 逐条列出未融合模块（按 block 聚合）
2. 结合 method 推断根因：
   - 是否缺少 `dynamic_block`
  - 是否与共享模块相关（shared）
3. 给最小修复路径：
   - 哪段代码需要加 dynamic_block
  - 哪些 shared 模块需要优先复核

---

### 示例 2：共享模块是否要拆分

**用户 Prompt：**

```text
Each module called times 里有很多 >1，
是不是都要拆成非共享？
```

**Agent 应输出：**

- 先说明：`called times > 1` 不是必改
- 给筛选策略：
  1) 从 `called times > 1` 先列出候选模块
  2) 建议用户结合精度对比再决定是否拆分
  3) 优先关注高频且与异常层邻近的共享模块
- 最终输出“建议优先排查清单”（而非直接要求全部拆分）

---

### 示例 3：averaging_constant 非默认值提示

**用户 Prompt：**

```text
帮我分析 model_check_result_260412_2347_85651.txt，看看有没有配置异常
```

**Agent 应输出：**

1. 从 `Each layer out qconfig` 和 `Weight qconfig` 表格中检查 observer 的 `averaging_constant` 值
2. 发现非默认值（!=0.01）时，列出具体模块：

```
averaging_constant 非默认值提示：
- 模块 quant (QuantStub)：averaging_constant=0（默认值为 0.01）
  ⚠ averaging_constant=0 等价于关闭滑动平均，observer 仅使用当前 batch 的 min/max，请确认是否为有意设置。
```

3. 其余 `averaging_constant=0.01` 的模块为默认值，无需额外提示

---

### 示例 4：qconfig 结果与预期不一致

**用户 Prompt：**

```text
请帮我看 qconfig 有没有明显异常，
尤其是高精度输出和 fixed scale 提示是否合理。
```

**Agent 应输出：**

1. 从 `Each layer out qconfig` 和 `Weight qconfig` 抽取关键层对照
2. 检查每个 `DeQuantStub` 的输入 dtype：
   - 输入为 `torch.float32`：✅ 高精度浮点输出已生效，无需提示
   - 输入为 `qint16`：✅ 高精度量化输出已开启（qint16 比 qint8 精度更高），标注为正常行为
   - 输入为 `qint8`：ℹ️ 标准 int8 量化输出，常规配置。若用户期望高精度输出，提示检查 qconfig 是否设置了 qint16
3. 检查除 `QuantStub/DeQuantStub` 外是否存在异常 `torch.float32` 输入
4. 对 `Please check if these OPs qconfigs are expected` 中提示项做”需人工复核”标注
5. 列出非 QuantStub/DeQuantStub 且输入为 `torch.float32` 的算子，提示用户检查 qconfig 配置是否符合预期

---

### 示例 5：非 QuantStub/DeQuantStub 算子输入为浮点

**用户 Prompt：**

```text
帮我分析 model_check_result.txt，看看有没有算子输入是浮点的情况
```

**Agent 应输出：**

1. 从 `input/output dtype statistics:` 和 `Each layer out qconfig:` 表格中检查各算子的输入 dtype
2. 排除 `QuantStub` 和 `DeQuantStub`（它们的浮点输入/输出是正常的边界行为）
3. 排除 Conv/Linear + ReLU 融合对：若 Conv/Linear 输出 `torch.float32` 且紧接的 ReLU 输入也为 `torch.float32`，说明它们已完成融合，中间 fp32 是预期行为，不算异常
4. 对其余输入为 `torch.float32` 的算子，列出具体信息：

```
算子输入浮点检查提示：
- 算子 conv2 (Conv2d)：输入 dtype=torch.float32
  ⚠ 该算子不是 QuantStub/DeQuantStub，但其输入为浮点类型。请检查其 qconfig 配置是否符合预期，以及上游链路的 qconfig 是否完整。
- 算子 relu1 (ReLU)：输入 dtype=torch.float32（上游 conv1 输出同为 fp32）
  ℹ Conv+ReLU 融合对，中间 fp32 为融合实现的正常中间态，无需处理。
```

4. 建议用户优先检查这些算子及其上游的 qconfig 配置，确认量化边界是否合理
5. Conv/Linear + ReLU 融合对（中间 fp32）标记为正常，无需处理

---

## 常见失败场景

### 场景 1：只看汇总统计，不看逐层明细

**问题：**

- 只能看到“有异常”，无法定位“哪层异常”

**正确做法：**

- 汇总表用于发现问题范围
- 逐层表用于确定具体模块与修复点

### 场景 2：把“Please check if these OPs qconfigs are expected”当成绝对错误

**问题：**

- 误改本来合理的 fixed-scale 或特殊层配置

**正确做法：**

- 先对齐业务预期，再决定是否改动

### 场景 3：忽略本 skill 的固定检查框架

**问题：**

- 在当前检查阶段引入与本 skill 无关的 method 分支结论，造成排查发散

**正确做法：**

- 按本 skill 的固定检查框架输出：融合 / 共享 / qconfig
- 对融合仅聚焦 `dynamic_block` 与 `shared` 两类高频原因

---

## 最小输出模板（建议）

当用户让你分析检查结果时，可按以下结构输出：

1. **融合检查结论**：未融合模块 + 原因（`dynamic_block`/`shared`）+ 优先级
2. **共享检查结论**：`called times > 1` 候选模块 + 建议复核顺序
3. **qconfig 检查结论**：DeQuantStub 输入 dtype 属于哪级（fp32=高精度浮点 ✅ / qint16=高精度量化 ✅ / qint8=标准 int8 ℹ️） / 可疑 qconfig 提示是否符合预期
4. **averaging_constant 提示**：非默认值（!=0.01）模块列表 + 提示确认是否有意设置
5. **算子输入浮点检查提示**：非 QuantStub/DeQuantStub 且输入为浮点的算子列表 + 提示检查 qconfig 配置是否符合预期
6. **最小修复建议**：仅列必要改动项

---

## 快速自检清单

- 是否覆盖了融合/共享/qconfig/averaging_constant/算子输入浮点检查五类检查。
- 是否引用了具体结果证据（而不是泛泛而谈）。
- 是否区分“必须改”与“建议复核”。
- 是否避免输出本 skill 未覆盖的大范围改造建议。
