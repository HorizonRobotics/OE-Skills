# Horizon Graph Diff - 使用示例

本文档说明何时触发 `j6-plugin-graph-diff`，以及如何基于计算图对比结果给出可落地的排查结论。

## 触发方式

### 直接触发（明确提及计算图对比）

```text
帮我对比这两份计算图文件，看看有什么差异
```

```text
对比评测和导出的 fx_graph，找出哪里发生了变化
```

```text
这两个模型的计算图不一样，帮我找出差异点并定位到源码
```

### 间接触发（描述计算图对比需求）

```text
帮我看下计算图有没有异常变化
```

```text
验证一下模型评测和导出的计算图是否一致
```

---

## Prompt 中建议包含的信息

### 必须信息

| 信息 | 说明 | 示例 |
|------|------|------|
| 计算图文件 1 | 第一个 fx_graph 文件路径 | `./graph_before.txt` |
| 计算图文件 2 | 第二个 fx_graph 文件路径 | `./graph_after.txt` |

### 强烈建议信息

| 信息 | 说明 | 示例 |
|------|------|------|
| 原始模型代码 | PyTorch 模型定义文件 | `model.py` |
| 对比场景 | 帮助判断差异是否预期 | "导出与评测对比"、"训练与评测对比" |
| 关注重点 | 指定需要重点检查的差异类型 | "只看backbone"、"忽略某个head的不一致" |

---

## 完整使用流程示例

### 示例 1：评测与导出对比验证

**用户 Prompt：**

```text
对比评测和导出的计算图：
- 评测：fx_graph_pred.txt
- 导出：fx_graph_export.txt
- 模型代码：model.py

重点检查head1的不一致。
```

**Agent 应输出：**

1. **总览**：
   - 图1节点数：1250
   - 图2节点数：1248
   - 相似度：98.5%
   - 差异类型：主要为参数差异

2. **差异分类**：
   - ⚠️ 需关注：`torch.relu` → `torch.leaky_relu`（1 处，operator_change）
   - ⚠️ 需关注：Conv2d padding 参数不一致（3 处，parameter_change）
   - ✅ 结构一致：无新增/删除节点

3. **源码定位**（针对异常差异）：
   ```
   差异点：torch.relu → torch.leaky_relu
   位置：model.py:156 (head1)
   代码：x = F.relu(x)  # 评测用 relu，导出变成 leaky_relu

   建议：检查导出配置中是否有算子替换规则
   ```

4. **结论**：
   - 评测和导出存在算子类型差异
   - 发现 1 处非预期算子替换，需要检查导出配置
   - 参数差异需要确认是否为预期配置

---

### 示例 2：版本间对比

**用户 Prompt：**

```text
对比 v1 和 v2 版本的模型计算图：
- v1：graph_v1.txt
- v2：graph_v2.txt
- 模型代码：yolov5.py

看看结构有什么变化。
```

**Agent 应输出：**

1. **结构变化统计**：
   - v1 节点数：2150
   - v2 节点数：2180
   - 新增节点：35 个
   - 删除节点：5 个

2. **差异详情**：
   ```
   差异 #1: 新增 SPPF 模块
   位置：yolov5.py:201 (neck)
   变化：v2 新增了 SPPF 层
   判断：✅ 预期修改（版本升级）

   差异 #2: Conv 参数变化
   位置：yolov5.py:89 (backbone.conv1)
   变化：kernel_size=6 → kernel_size=3
   判断：⚠️ 需确认是否为预期修改
   ```

3. **版本差异总结**：
   - ✅ 结构变化符合版本升级预期
   - ⚠️ 1 处参数变化需要确认

---

### 示例 3：动态控制流对比

**用户 Prompt：**

```text
对比两个版本的计算图，看看动态控制流是否有差异：
- v1：graph_v1.txt
- v2：graph_v2.txt
- 模型代码：transformer.py

重点关注循环和分支部分。
```

**Agent 应输出：**

1. **动态控制流差异**：
   ```
   差异 #1: 循环展开次数变化
   位置：transformer.py:145 (decoder layers)
   变化：
   - v1: 循环 6 次（动态）
   - v2: 循环 12 次（静态展开）

   差异 #2: 分支条件变化
   位置：transformer.py:167 (attention mask)
   变化：
   - v1: if mask is not None (动态)
   - v2: 固定路径（移除条件）
   ```

2. **影响分析**：
   - 循环展开：可能影响性能（加速但增加内存）
   - 分支移除：可能影响灵活性（固定输入 shape）

3. **建议**：
   - 确认 v2 的静态化是否符合预期
   - 验证输入 shape 是否需要固定

---

## 常见失败场景

### 场景 1：只看节点数，不看节点内容

**问题：**
- 只能发现"有差异"，无法定位"哪里差异"

**正确做法：**
- 先看总览（节点数、相似度）
- 再看具体差异点（节点内容、参数）
- 最后定位源码（文件、行号、代码片段）

### 场景 2：忽略差异的上下文

**问题：**
- 单看差异节点，无法理解影响范围

**正确做法：**
- 显示差异点前后 3-5 行代码
- 标注差异节点在计算图中的位置（输入/输出连接）
- 分析差异的传播路径

### 场景 3：不提供原始模型代码

**问题：**
- 只能定位到计算图差异，无法映射回源码

**正确做法：**
- 尽量提供原始模型代码文件
- 提供模型类名（便于精确定位）
- 如果无法提供源码，至少提供模型结构说明

### 场景 4：忽略差异类型分类

**问题：**
- 所有差异都被同等对待，无法区分优先级

**正确做法：**
- operator_change：通常需要重点关注
- parameter_change：需要确认是否为预期配置
- structure_change：结构差异需要仔细分析

---

## 最小输出模板（建议）

当用户让你对比计算图时，可按以下结构输出：

1. **总览**：节点数、相似度、差异类型分布
2. **第一个差异点**：位置、内容、上下文
3. **差异分类**：按类型分类（operator_change / parameter_change / structure_change）
4. **源码定位**：映射回原始代码（如果提供了模型代码）
5. **结论与建议**：差异是否合理、需要关注的点、修复建议

---

## 快速自检清单

- ✅ 是否成功加载并解析了两份计算图
- ✅ 是否识别了第一个差异点和所有差异块
- ✅ 是否提供了差异的上下文（前后代码）
- ✅ 是否对差异进行了分类（operator_change / parameter_change / structure_change）
- ✅ 是否映射回了原始模型代码（如果提供了）
- ✅ 是否根据对比场景判断了差异的合理性
- ✅ 是否给出了清晰的修复建议（针对异常差异）

---

## 与其他 Skill 的配合

### 与 `j6-plugin-model-check-result` 配合

```text
用户：评测和导出结果不一致，帮我排查问题。

Agent：
1. 先用 j6-plugin-model-check-result 分析 model_check_result.txt
   → 发现 head1 输出差异

2. 再用 j6-plugin-graph-diff 对比评测和导出计算图
   → 定位到具体的算子差异节点

3. 映射到源码，给出修复建议
```

---

## 高级用法

### 1. 批量对比

```bash
# 对比多个版本的计算图
for i in {1..10}; do
    python j6_plugin_graph_diff.py --file1 graph_v$i.txt --file2 graph_ref.txt -o diff_v$i.txt
done
```

### 2. 过滤特定差异

Agent 在分析 diff 报告时可以过滤特定类型的差异：

```python
# 只关注算子类型差异
def filter_operator_changes(all_diffs):
    return [d for d in all_diffs if d.category == 'operator_change']

# 只关注参数差异
def filter_parameter_changes(all_diffs):
    return [d for d in all_diffs if d.category == 'parameter_change']

# 排除特定模块的差异
def exclude_module(all_diffs, module_name):
    return [d for d in all_diffs if module_name not in d.node_1.name]
```
