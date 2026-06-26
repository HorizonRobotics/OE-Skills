---
name: j6-plugin-dynamic-block
description: 在适配 horizon_plugin_pytorch（prepare/JIT_STRIP）时，自动为动态控制流/动态循环中涉及算子替换或融合的逻辑添加 dynamic_block 标注，避免 scope/替换错乱与 forward 报错。
---

# 为 Horizon QAT 自动添加 dynamic_block 标注（Scope 约束版）

## 目标

在使用 `horizon_plugin_pytorch` 的基于图（如 `PrepareMethod.JIT_STRIP` / `PrepareMethod.JIT`）的 `prepare` 流程适配模型时，针对**动态循环/动态控制流**里会触发 **function 算子替换** 或 **算子融合** 的代码段，自动补齐 `dynamic_block` 标注，把该段逻辑定义为独立的 **Scope**，避免：

- 同一行 function 多次调用在不同 trace 次数/路径下导致的 **scale/scope 错位**
- 动态部分与静态部分意外融合，造成 **forward 报错**
- 算子替换/融合在动态控制流中发生时的 **量化信息错乱**

## 适用范围

- 你正在为 `horizon_plugin_pytorch` 做量化适配，并使用 `prepare(..., method=PrepareMethod.JIT_STRIP/JIT)` 这类**基于图**的模式。
- 模型 `forward` 存在运行次数/执行路径不稳定的逻辑，例如：
  - 循环次数由输入/随机数/外部状态决定（`numpy.random`/数据相关分支等）
- 且该动态逻辑内部包含可能被 `prepare` 替换/融合的算子（例如某些 torch function、可融合的 Conv+BN(+Add) 等 pattern）。

**重要限制：**
- 如果你的逻辑是**纯静态**的（没有数据依赖的 for/while、没有根据输入/随机数决定执行次数），即使其中有**可替换或可融合算子**，**也不应该额外包 dynamic_block**。

## 强约束（本 Skill 的“必须做到”）

- **只标注需要算子替换/融合的逻辑块，不要把整个 for/while 循环都包进去**：标注的是“块内的算子替换/融合逻辑”，不是控制流本身。
- **`Tracer.dynamic_block` 的第一个参数必须是当前 `nn.Module` 实例（通常是 `self`），不是 function / lambda / 普通 callable**：正确用法是 `Tracer.dynamic_block(self, "BlockName")`，不要写成 `Tracer.dynamic_block(some_func, "BlockName")`。
- **`with Tracer.dynamic_block(...)` 必须放在循环/分支内部，只包住需要替换/融合的语句，不要把 `for/while` 控制流包进 `with`**：控制流负责“执行次数/路径”，`dynamic_block` 负责给其中那段非 module scope 的动态算子逻辑建立稳定 Scope。
- **不要对“已经处于 Module Scope 内”的逻辑额外加 dynamic_block**：
  - `nn.Module.forward` 本身就是一个 Scope。
  - 因此如果动态控制流里只有“子 module 调用”（例如循环里只做 `x = self.layer1(x)`），通常不需要也不应该再包 `dynamic_block`。
  - `dynamic_block` 的主要目标是：动态控制流中出现的 **非 module scope 的 function/Tensor 逻辑**（例如 `x = x + 1`、`x = torch.relu(x)`、`x = sub_one(x)`）导致的 function 替换/融合错误的问题。
- **动态块必须是稳定可复现的 Scope**：
  - 同一段逻辑每次执行应使用同一个 `dynamic_block` 名称（如果用命名 API）。
  - 不要在同一 `forward` 里复用同一个名字去标不同语义的块。
- **优先使用 `Tracer.dynamic_block(self, "<Name>")`**（当代码中已引入/可引入 `Tracer` 且希望显式命名）。
- **如果已有 dynamic_block 标注，不重复嵌套/不改语义**：只在缺失且确有必要的位置补齐。

## 标准改法（优先推荐）

### 1) 引入 Tracer（推荐写法）

```python
from horizon_plugin_pytorch.fx.jit_scheme import Tracer
```

### 2) 在动态循环/动态分支中，包住需要替换/融合的算子段

```python
for _ in range(n):  # n 可能是动态的
    # 只标注需要算子替换/融合的逻辑块（不是整个循环）
    with Tracer.dynamic_block(self, "ConvBnAdd"):
        x = self.conv(x)
        x = self.bn(x)
        x = x + y
```

这里有两个硬性要求：

- 第一个参数传 `self`（或等价的当前 `nn.Module` 实例），**不要传 function**。
- `with` 写在循环/分支体内部，**不要把 `for` 本身写进 `dynamic_block`**。

### 3) 明确反例：这些写法都不对

```python
# 反例 1：把 function 当成第一个参数传入
with Tracer.dynamic_block(sub_one, "SubOne"):
    x = sub_one(x)

# 反例 2：把整个循环都包进 dynamic_block
with Tracer.dynamic_block(self, "Loop"):
    for _ in range(n):
        x = torch.relu(x)
```

### 4) 对应正例：控制流在外，dynamic_block 在内

```python
for _ in range(n):
    x = self.stem(x)  # 子 module scope，通常不用加 dynamic_block

    with Tracer.dynamic_block(self, "ReluAdd"):
        x = torch.relu(x)
        x = x + skip
```

### 5) 备选写法（context manager，无显式命名）

当你无法/不希望引入 `Tracer` 命名 API 时，可使用：

```python
import horizon_plugin_pytorch

with horizon_plugin_pytorch.fx.jit_scheme.dynamic_block():
    x = torch.reciprocal(x)  # 示例：可能触发 function->Module 替换的区域
```

## 什么时候“必须”加 dynamic_block（判断准则）

- **同时满足这两个条件时，才需要加：**
  1. 代码块处于 **动态控制流** 内：
     - 循环次数依赖输入/随机数/外部状态的 for/while
     - 根据输入/随机数/决定执行次数
  2. 该代码块内部包含可能被 `prepare` 做 **function 替换或算子融合** 的逻辑（例如 Conv+BN(+Add)、某些 torch function ➜ Module 的替换）。

- 如果只满足其中之一：
  - **只有可融合 / 可替换，但控制流是静态，不要加 dynamic_block**。
  - **只有控制流是动态，但里面不参与替换/融合**：通常也不需要加 dynamic_block。

- 快速判定（避免误包子 module）：
  - **动态块里如果只有 `self.xxx(...)` 这类子 module 调用**：通常不加 `dynamic_block`（子 module 的 `forward` 已经提供 Scope）。
  - **动态块里如果包含非 module scope 的 function/Tensor 逻辑**（`torch.xxx` / `x + y`）：要加 `dynamic_block`。
  - **如果你想写 `Tracer.dynamic_block(...)`，先检查第一个参数是不是 `self` / 当前 module；如果不是，就停下来重写。**
  - **如果 `with Tracer.dynamic_block(...)` 的下一行是 `for` / `while`，大概率包大了；应把 `with` 下沉到真正会发生替换/融合的语句块。**

## 常见坑（按本 Skill 直接规避）

- **把 dynamic_block 包在错误的层级**：把整个循环都包住通常不是你想要的；应只包住那段会触发替换/融合的算子逻辑。
- **把 function 传给 `Tracer.dynamic_block`**：第一个参数必须是 module 实例，用于绑定稳定 Scope；传 function 会让 Scope 语义和调用约束都出错。
- **对已经是子 module scope 的调用再包一层 dynamic_block**：例如循环里只做 `x = self.layer1(x)`，子 module `self.layer1` 已经是在一个 Scope 中，额外包 dynamic_block 通常是冗余的。
- **dynamic_block 名称不稳定**：名称如果随条件变化/拼接随机数，会破坏 Scope 的稳定性，导致替换/量化信息错乱。
- **prepare 后再改 hook/结构**：prepare 依赖 hook 与 wrapper 机制；prepare 完成后不要改动相关 hook（否则替换失效，可能报错/精度异常）。
- **在纯静态网络里，为了“万无一失”全部包上 dynamic_block，这是不推荐的：**：额外的 dynamic_block 不会提升安全性，反而增加审查与维护成本。

## 快速自检清单

- 动态循环/分支里，凡是会触发 **function 替换/算子融合** 的逻辑都被 `dynamic_block` 包住。
- 标注的是“逻辑块”，不是控制流本身；块的语义与边界清晰。
- 每一个 `Tracer.dynamic_block(...)` 都满足“第一个参数是当前 module（通常是 `self`），不是 function/callable”。
- 没有任何 `with Tracer.dynamic_block(...)` 直接包住 `for` / `while`。
- `dynamic_block` 的命名稳定、可复现，且同名只对应同一语义块。

## 参考：dynamic_block / Scope 原理

以下内容用于解释为什么 `dynamic_block` 能解决“动态调用次数不一致导致的替换/scale 错位”问题，以及图模式 `prepare` 下的注意事项。

### Scope 与 function 算子替换

function 算子替换依赖计算图，但是计算图中同一行代码的多次调用会展开为多个节点，替换为多个 Module。若模型中存在训练和推理阶段调用次数不一致的代码块，会导致 scale 错位，影响模型精度。

为了解决这一问题，我们引入 “Scope” 的概念，在进行算子替换时，**同一个 Scope 中的同一次 func 代码调用，将替换为同一个共享 Module**。当前有两种方式定义 Scope：

1. 一个 Module 类型的 forward 方法，定义了一个 Scope；
2. 使用 `horizon_plugin_pytorch.fx.jit_scheme.dynamic_block` 接口标记的代码块，是一个 Scope。

### 通过 `dynamic_block` 定义 Scope（示例）

```python
def sub_one(x):
    return x - 1


class Net(torch.nn.Module):
    def forward(self, x):
        for _ in range(numpy.random.randint(1, 10)):
            with horizon_plugin_pytorch.fx.jit_scheme.dynamic_block():
                x += 1  # self._generated_add_0
                x = sub_one(x)  # self._generated_sub_1
                x += 1  # self._generated_add_1
        return x
```

### prepare 图模式下的动态代码块注意事项

1. 动态代码块涉及到算子替换或算子融合时，必须使用 Tracer.dynamic_block 进行标注，否则将导致量化信息错乱或 forward 报错。
2. 模型中调用次数变化的部分（子 module 或 dynamic_block），若在 trace 时仅执行了一次，则有可能和非动态部分产生算子融合，导致 forward 报错。

### hook/Wrapper 机制相关注意事项

注意：为了实现 function 向 Module 的跳转，我们为 `torch.Tensor` 实现了一个特殊的 Wrapper 子类，此 Wrapper 的封装和解封通过在模型中合适的 Module 上注册 hook 实现。因此**在 prepare 完成后请不要修改模型中的任何 hook，以免替换失效，造成报错或精度问题**。
