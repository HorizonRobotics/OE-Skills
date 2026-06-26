---
name: j6-plugin-graph-diff
description: 对比两份 FX Graph 计算图文件，精确定位计算图结构和算子参数差异，并根据 diff 报告在原始模型代码中找到对应的差异位置。
tools:
  - name: j6_plugin_graph_diff.py
    type: script
    description: 计算图差异对比脚本，解析两个 FX Graph 文件并生成结构化 diff 报告
    path: j6-plugin-graph-diff/j6_plugin_graph_diff.py
    required: true
---

# FX Graph 计算图对比与源码定位工具

## 强约束（必须遵守）

### 1) 必须调用外挂脚本，禁止 Agent 自行实现差异对比

本 Skill 的计算图差异对比**必须**通过调用外挂脚本 `j6_plugin_graph_diff.py` 完成，**严禁** Agent 自己编写 Python 代码实现 diff 逻辑。

- ✅ **必须**：通过 Bash 工具执行 `python j6-plugin-graph-diff/j6_plugin_graph_diff.py --file1 ... --file2 ...`
- ❌ **禁止**：Agent 自行编写 difflib/正则匹配等代码来解析计算图
- ❌ **禁止**：用 Bash 的 diff 命令替代外挂脚本
- ❌ **禁止**：用 Read 工具读取两个文件后自行比较

**原因**：外挂脚本包含完整的 FX Graph 解析逻辑（节点解析、差异分类、相似度计算等），Agent 自行实现容易遗漏格式兼容性、分类精度等问题。

### 2) 外挂脚本调用前必须确认文件存在

在调用脚本前，Agent 必须确认两个输入文件路径存在且可读，避免脚本执行失败。

### 3) 脚本路径

外挂脚本位于：`j6-plugin-graph-diff/j6_plugin_graph_diff.py`

调用时使用相对路径：
```bash
python j6-plugin-graph-diff/j6_plugin_graph_diff.py --file1 <path1> --file2 <path2> -o <output_path>
```

## 目标

对比两份 FX Graph 计算图文件（例如评测与导出、训练与推理、不同版本之间的计算图），实现：

1. **精确识别计算图差异**：找出第一个不一致点、所有差异块（由外挂脚本完成）
2. **差异分类统计**：按差异类型（算子变化、参数变化、结构变化）进行分类
3. **源码反向定位**：根据 diff 报告，由 Agent 分析并将差异映射回原始模型代码位置

## 职责分工

本 Skill 采用**外挂脚本 + Agent 分析**的分工模式：

| 组件 | 职责 | 输入 | 输出 |
|------|------|------|------|
| **外挂脚本** `j6_plugin_graph_diff.py` | 计算图差异对比 | 两个 FX Graph 文件 | diff 报告（文本格式） |
| **Agent Skill** | 源码定位与分析 | diff 报告 + 模型源码 | 源码位置、修复建议 |

> **重要**：Agent 不得自行实现外挂脚本的职责。差异对比必须调用外挂脚本，Agent 只负责解读脚本输出并进行源码定位。

### 外挂脚本职责（j6_plugin_graph_diff.py）

外挂脚本**只负责计算图层面的差异对比**，不涉及源码分析：

- ✅ 解析两个 FX Graph 文件
- ✅ 找出第一个差异点
- ✅ 找出所有差异块
- ✅ 对差异进行分类（operator_change / parameter_change / structure_change）
- ✅ 计算相似度
- ✅ 生成结构化 diff 报告
- ❌ **不负责**源码反向定位

### Agent Skill 职责

Agent 负责**根据 diff 报告进行源码定位和问题分析**：

- ✅ 调用外挂脚本生成 diff 报告
- ✅ 分析 diff 报告，理解差异内容
- ✅ 根据差异节点信息，在模型源码中搜索对应位置
- ✅ 提供源码上下文和修复建议
- ✅ 判断差异是否预期（结合用户提供的场景说明）

## 适用范围

本 Skill 适用于以下场景：

- **评测与导出对比**：对比模型评测和导出阶段的计算图差异
- **训练与推理对比**：对比训练模式和推理模式的计算图差异
- **版本对比**：对比不同版本模型的结构变化
- **调试定位**：快速定位计算图异常点，并映射回源码

## 核心能力

### 1. 计算图差异识别（外挂脚本）

- ✅ 识别算子类型变化（如 `torch.relu` → `torch.leaky_relu`）
- ✅ 识别算子参数变化（如 `args=(x, 1)` → `args=(x, 0.5)`）
- ✅ 识别结构变化（如新增/删除节点、改变连接关系）

### 2. 源码反向定位（Agent Skill）

- ✅ 解析 diff 报告，提取关键差异节点
- ✅ 在模型源码中搜索对应的操作（如模块名、函数名）
- ✅ 匹配 forward 函数中的调用位置
- ✅ 提供代码上下文（前后 N 行）便于理解
- ✅ 判断差异是否符合预期场景

### 3. 差异分析与报告

- ✅ 生成结构化对比报告（外挂脚本）
- ✅ 按影响程度排序（高/中/低优先级）
- ✅ 提供修复建议（Agent Skill，针对常见问题）

## 输入要求

### 必需输入

| 信息 | 说明 | 示例 |
|------|------|------|
| fx_graph 文件 1 | 第一个计算图文件路径 | `graph_before.txt` |
| fx_graph 文件 2 | 第二个计算图文件路径 | `graph_after.txt` |

### 强烈建议输入

| 信息 | 说明 | 示例 |
|------|------|------|
| 原始模型代码 | PyTorch 模型定义文件 | `model.py` |
| 模型类名 | 便于精确定位 | `class ResNet` |

## 标准执行流程

### 第一步：调用外挂脚本生成 diff 报告（必须执行）

> **硬约束**：本步骤不可跳过，不可由 Agent 自行替代。必须通过 Bash 工具调用外挂脚本。

```bash
# 使用外挂脚本对比两个 FX Graph 文件
python j6-plugin-graph-diff/j6_plugin_graph_diff.py --file1 fx_graph_1.txt --file2 fx_graph_2.txt -o diff_report.txt
```

**Agent 职责：**
- 构建正确的命令行调用
- 捕获脚本的输出报告
- 读取脚本生成的 diff 报告文件

**脚本输出：**
- 第一个差异点位置（行号、节点名）
- 所有差异块列表（带上下文）
- 差异分类（operator_change / parameter_change / structure_change）
- 整体相似度统计

### 第二步：分析 diff 报告

**Agent 职责：**
- 解析脚本输出的 diff 报告
- 理解每个差异节点的内容：
  - `opcode`: 操作类型（call_module, call_function, call_method 等）
  - `target`: 目标模块/函数名
  - `args`: 输入参数
  - `name`: 节点名称

**关键信息提取：**
```python
# 从 diff 报告中提取差异节点
diff_nodes = extract_diff_nodes(diff_report)
for node in diff_nodes:
    print(f"节点名: {node.name}")
    print(f"操作类型: {node.node_type}")
    print(f"目标: {node.target}")
    print(f"差异分类: {node.category}")
```

### 第三步：源码反向定位（Agent 分析）

**Agent 职责：**
- 读取模型源码文件
- 根据差异节点的 `target` 和 `name` 在源码中搜索：
  - 模块定义位置（`self.xxx = ...`）
  - forward 函数中的调用位置（`self.xxx(...)`）
- 提供代码上下文

**定位策略：**

1. **call_module 类型节点**：
   - 在 `__init__` 中搜索模块定义：`self.{name} = ...`
   - **处理嵌套模块**：如果直接搜索失败，按层级拆分 name（如 `backbone.layer1.conv`）：
     - 先找父模块：`self.backbone`
     - 再在父模块类中找子模块：`self.layer1`
     - 逐层深入直到找到目标模块
   - 在 `forward` 中搜索调用：`self.{name}(...)`

2. **call_function 类型节点**：
   - 在 `forward` 中搜索函数调用：`F.{target}(...)` 或 `torch.{target}(...)`

3. **call_method 类型节点**：
   - 在 `forward` 中搜索方法调用：`tensor.{target}(...)`

4. **get_attr 类型节点**：
   - 在 `__init__` 或类属性中搜索定义

### 第四步：生成综合报告

**Agent 职责：**
- 整合外挂脚本的 diff 报告
- 添加源码定位结果
- 提供修复建议（根据差异类型和场景）

## 输出报告结构

### 1. 外挂脚本输出（diff 报告）

```
================================================================================
FX Graph 计算图对比报告
================================================================================
文件 1: fx_graph_pred.txt (评测)
文件 2: fx_graph_export.txt (导出)
图1总节点数: 1250
图2总节点数: 1248
整体相似度: 98.5%
================================================================================

📍 第一个差异点位置:
   文件1 行号: 342
   文件2 行号: 340
   差异类型: operator_change

📝 差异内容:
   文件1: call_function target=torch.relu args=(x41,)
   文件2: call_function target=torch.leaky_relu args=(x41,)

📊 差异分类统计
================================================================================
OPERATOR_CHANGE (3 处):
  ...

PARAMETER_CHANGE (5 处):
  ...
```

### 2. Agent 源码定位输出

```
================================================================================
🔗 源码反向定位 (Agent 分析)
================================================================================

差异点 #1: torch.relu → torch.leaky_relu
  差异类型: operator_change
  源码位置: model.py:156 (forward 函数)

  代码上下文:
    154 |     def forward(self, x):
    155 |         x = self.conv(x)
    156 |         x = F.relu(x)  # ← 差异点：评测与导出不一致
    157 |         return x

  修复建议:
    - 检查导出配置中是否有算子替换规则
    - 确认评测和导出是否使用了不同的模型配置

差异点 #2: Conv2d 参数不一致
  差异类型: parameter_change
  源码位置: model.py:89 (__init__ 函数)

  代码上下文:
    87 |     def __init__(self):
    88 |         super().__init__()
    89 |         self.conv = nn.Conv2d(3, 64, 3, padding=1)  # ← padding 参数差异
    90 |         ...

  修复建议:
    - 检查导出时的参数配置
    - 确认是否为预期的参数调整
```

## 常见差异模式与处理建议

### 1. 算子类型差异（operator_change）

**差异模式：**
- `torch.relu` → `torch.leaky_relu`
- `torch.add` → `torch.cat`

**判断标准：**
- ❌ 如果没有预期修改，属于**异常**
- 🔍 需要检查配置文件、导出脚本

### 2. 算子参数差异（parameter_change）

**差异模式：**
- `args=(x, 1)` → `args=(x, 0.5)`
- `padding=0` → `padding=1`
- `kernel_size=3` → `kernel_size=5`

**判断标准：**
- ⚠️ 需要确认是否为预期配置差异
- 🔍 检查评测和导出是否使用相同配置

### 3. 结构差异（structure_change）

**差异模式：**
- 新增/删除节点
- 改变节点连接关系
- 分支条件变化

**判断标准：**
- ❌ 结构差异通常需要重点关注
- 🔍 验证评测和导出的模型定义是否一致

### 4. 动态控制流差异

**差异模式：**
- 循环次数变化
- 分支条件变化
- 动态 shape 处理

**判断标准：**
- ⚠️ 动态控制流在图模式下可能被特殊处理
- 🔍 需要验证 trace/export 时的输入是否正确

## 使用场景示例

### 场景 1：评测与导出对比验证

```bash
# 用户输入
"对比评测和导出的计算图，看看是否一致"

# Agent 执行流程
1. 【调用脚本】python j6-plugin-graph-diff/j6_plugin_graph_diff.py --file1 fx_graph_pred.txt --file2 fx_graph_export.txt -o diff_report.txt
2. 【分析报告】解析 diff 报告，识别差异类型
3. 【源码定位】对于关键差异节点，在模型源码中定位
4. 【判断预期】根据"评测与导出对比"场景，判断差异是否合理：
   - ✅ 无差异：评测和导出一致
   - ❌ 算子替换（如 relu → leaky_relu）：需排查
   - ⚠️ 参数差异：检查配置是否一致
5. 【生成报告】输出综合分析结果
```

### 场景 2：训练与推理模式对比

```bash
# 用户输入
"对比训练模式和推理模式的计算图差异"

# Agent 执行流程
1. 【调用脚本】生成 diff 报告
2. 【分析报告】重点识别：
   - 是否有意外的算子替换（operator_change）
   - 是否有参数值异常（parameter_change）
   - Dropout、BatchNorm 等训练/推理差异是否正常
3. 【源码定位】在模型源码中找到问题位置
4. 【提供建议】针对异常差异给出修复建议
```

### 场景 3：模型结构对比

```bash
# 用户输入
"对比两个模型的计算图结构差异"

# Agent 执行流程
1. 【调用脚本】python j6-plugin-graph-diff/j6_plugin_graph_diff.py --file1 model_a_graph.txt --file2 model_b_graph.txt -o diff_report.txt
2. 【分析报告】关注 structure_change 类型的差异
3. 【源码定位】定位到两个模型源码中的对应位置
4. 【生成报告】说明结构差异的具体含义
```

## 关键注意事项

### 1. 职责边界清晰

- **外挂脚本**：只负责计算图层面的差异对比，输出标准化的 diff 报告
- **Agent Skill**：负责理解 diff 报告，进行源码定位和问题分析
- 不应在外挂脚本中实现源码定位功能（保持工具单一职责）

### 2. 计算图格式兼容性

- FX Graph 应当为 horizon_plugin_pytorch 产生
- 外挂脚本自动识别格式并解析

### 3. 源码映射策略

- Agent 使用多种策略进行源码定位：
  - 模块名匹配：`self.stem_conv` → 搜索 `self.stem_conv = ...`
  - 嵌套模块匹配：`backbone.layer1.conv` → 逐层搜索 `self.backbone` → `self.layer1` → `self.conv`
  - 函数名匹配：`target=torch.relu` → 搜索 `F.relu` 或 `torch.relu`
  - 变量名推断：根据 forward 数据流推断位置
- 动态生成的代码可能无法精确定位，Agent 应说明原因

### 4. 差异判断的主观性

- 某些差异可能是预期优化（如算子融合、量化）
- Agent 需要结合用户提供的场景说明判断差异合理性
- 不应武断判断所有差异都是问题

### 5. 大规模计算图处理

- 对于超大计算图（>10000 节点），可能需要分块对比
- 优先关注关键路径上的差异
- 可以配置过滤规则（如忽略变量名差异）

## 快速自检清单

### 外挂脚本执行检查
- ✅ 是否成功调用 `j6_plugin_graph_diff.py`
- ✅ 是否生成了 diff 报告
- ✅ 报告中是否包含差异分类和相似度统计

### Agent 分析检查
- ✅ 是否正确解析了 diff 报告中的差异节点
- ✅ 是否提取了关键信息（target、name、args）
- ✅ 是否在模型源码中进行了搜索定位
- ✅ 是否提供了代码上下文
- ✅ 是否根据对比场景判断了差异的合理性
- ✅ 是否给出了清晰的修复建议（针对异常差异）

## 依赖工具

### 外挂脚本（必须调用）

- **脚本路径**: `j6-plugin-graph-diff/j6_plugin_graph_diff.py`（相对于项目根目录）
- **Python 库**: `difflib`, `re`, `pathlib`, `dataclasses`
- **输入**: 两个 FX Graph 文件路径
- **输出**: 文本格式的 diff 报告

> **硬约束**：Agent 不得自行实现脚本的差异对比逻辑，必须通过 `python j6-plugin-graph-diff/j6_plugin_graph_diff.py` 调用。

### 脚本使用方式

```bash
# 基本用法（输出到文件）
python j6-plugin-graph-diff/j6_plugin_graph_diff.py --file1 graph1.txt --file2 graph2.txt -o report.txt
```

### Agent 所需能力

- **文件读取**: 读取 diff 报告和模型源码
- **代码搜索**: Grep/Glob 工具搜索源码
- **代码理解**: 理解 PyTorch 模型结构
- **报告生成**: 整合分析结果生成最终报告
