# Horizon QAT dynamic_block 标注 - 使用示例

本示例文档用于指导你在适配 `horizon_plugin_pytorch`（尤其是 `prepare` 的 `JIT_STRIP/JIT` 图模式）时，如何为**动态循环/动态控制流**中涉及**算子替换/算子融合**的逻辑自动补齐 `dynamic_block` 标注，以稳定 Scope，避免替换错乱和 `forward` 报错。

## 触发方式

以下类型的 prompt 会触发该 skill：

### 直接触发（明确提及 dynamic_block / Tracer.dynamic_block / Scope）

```
给这个模型做 horizon_plugin_pytorch 量化适配，动态循环里帮我补上 dynamic_block 标注
```

```
@hat/models/xxx.py 里 forward 有随机次数循环，prepare(JIT_STRIP) 会报错，帮我加 Tracer.dynamic_block
```

### 间接触发（描述“动态控制流 + prepare 图模式不稳定/报错/替换错乱”）

```
这个网络里有 while/for 动态分支，horizon prepare 后量化信息错乱，怎么处理？
```

```
同一行 torch function 在不同路径调用次数不一致，qat 的 scale 对不上
```

---

## Prompt 中需要包含的关键信息

为了让 agent 精准落点（避免过度包裹或漏标），建议在 prompt 中提供：

### 必须信息

| 信息 | 说明 | 示例 |
|------|------|------|
| 目标文件/目标类 | 要修改的模型文件或类名 | `@hat/models/xxx.py` |
| prepare 模式 | 是否使用 `PrepareMethod.JIT_STRIP/JIT` | `JIT_STRIP` |
| 动态逻辑位置 | 哪段是动态循环/动态分支 | `for _ in range(np.random...)`|

### 强烈建议提供

| 信息 | 说明 | 示例 |
|------|------|------|
| 哪段逻辑触发替换/融合 | 需要被标注成 Scope 的“算子逻辑块” | `conv+bn+add` / `torch.reciprocal` |
| 期望的块语义名 | 用于 `Tracer.dynamic_block(self, "<Name>")` | `"ConvBnAdd"` / `"ReciprocalBlock"` |

---

## 完整使用流程示例

### 示例 1：动态循环 + Conv/BN/Add（推荐 Tracer.dynamic_block）

**用户 Prompt：**

```
给 @hat/models/xxx.py 里的 Net.forward 做 horizon prepare(JIT_STRIP) 适配。
里面有随机次数循环，循环里做 conv+bn+add，prepare 后会报错；帮我补 Tracer.dynamic_block，名字用 ConvBnAdd。
```

**Agent 执行流程：**

1. 读取目标 `forward`，定位动态循环/分支与其中的算子逻辑块。
2. 引入 `from horizon_plugin_pytorch.fx.jit_scheme import Tracer`（若尚未引入）。
3. 在动态循环/分支内，仅包住会触发替换/融合的算子段：
   - `with Tracer.dynamic_block(self, "ConvBnAdd"):` + 相关算子
4. 自检：
   - 没有把整个循环“粗暴包住”（只包逻辑块）
   - 名称稳定且与语义一致

---

## 最小代码模板（可直接照抄）

### 模板 1：命名 dynamic_block（推荐）

```python
from horizon_plugin_pytorch.fx.jit_scheme import Tracer


class Net(torch.nn.Module):
    def forward(self, x, y):
        for _ in range(n):  # n 动态
            with Tracer.dynamic_block(self, "SomeStableName"):
                x = self.conv(x)
                x = self.bn(x)
                x = x + y
        return x
```

### 模板 2：context manager dynamic_block（备选）

```python
import horizon_plugin_pytorch


class Net(torch.nn.Module):
    def forward(self, x):
        for _ in range(n):  # n 动态
            with horizon_plugin_pytorch.fx.jit_scheme.dynamic_block():
                x = torch.reciprocal(x)
        return x
```

---

## 失败/返工场景示例（常见）

### 场景 1：标注包住了整个循环，但问题仍然存在

**典型问题：**
- `with dynamic_block():` 放在 `for` 外层，导致 Scope 粒度过大，无法精准隔离“替换/融合逻辑块”。

**修复策略：**
- 把 `dynamic_block` 移到循环内部，只包住会触发替换/融合的算子段（而不是控制流本身）。

### 场景 2：dynamic_block 名字不稳定（拼了随机数/依赖输入）

**典型问题：**
- `with Tracer.dynamic_block(self, f"Block_{randint()}"):`，导致 Scope 不可复现。

**修复策略：**
- 改成固定且语义化的名字（如 `"ConvBnAdd"`、`"ReciprocalBlock"`）。

### 场景 3：动态块里没有替换/融合，但被过度标注

**典型问题：**
- 把纯张量 reshape/简单算子也包进 dynamic_block，造成阅读成本上升且难以审查。

**修复策略：**
- 只在“动态代码块涉及算子替换或融合”的情况下标注；其他保持原样。

---

## 快速自检清单

- 动态循环/分支中，涉及 **算子替换/融合** 的逻辑块均已标注为 `dynamic_block`。
- 标注粒度合理：包的是逻辑块，不是控制流；命名稳定且语义清晰。
- 使用 `JIT_STRIP/JIT` 时，prepare 后不会再随意改动模型 hook/结构。
