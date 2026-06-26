# 删除/保留模型 IO 节点（Quantize/Dequantize/Cast 等）策略指南

## 适用场景

**触发关键词**：删除节点、删Quantize、删Dequantize、删Cast、保留节点、不删、remove_node_type、remove_node_name

**前置条件**：
- 已有 `.bc` 模型文件（PTQ 量化后的定点 BC）
- 已安装 `horizon_tc_ui` 工具包

**使用时机**：用户要求编译模型时删除或保留部分 IO 节点的 Quantize/Dequantize/Cast 等算子。

---

## YAML 中可用的参数

YAML `model_parameters` 中只有两个删除相关参数：

| 参数 | 类型 | 说明 |
|------|------|------|
| `remove_node_type` | str | 分号分隔的类型列表，按类型批量删除 |
| `remove_node_name` | str | 分号分隔的节点名列表，按名称精确删除 |

> **重要**：YAML 中**没有** `preserve_input_nodes`、`preserve_output_nodes`、`remove_input_nodes`、`remove_output_nodes` 等参数。部分删除只能通过 `remove_node_name` 精确指定要删除的节点名来实现。

### 支持删除的节点类型

由 `mapper_consts.py` 中的 `removal_list` 定义：

**Quantize**、**Dequantize**、**Cast**、**Transpose**、**Reshape**、**Softmax**

---

## 前置步骤：查询模型可删除的 IO 节点

在配置删除策略前，**必须先查询模型有哪些可删除的 IO 节点**。

```bash
hb_model_info model.bc
```

该命令内部调用 `get_removable_io_op()` 查询所有可删除的 IO 相邻节点，输出示例：

```
############# Removable node info #############
| Node Name                          | Node Type   |
|------------------------------------|-------------|
| imgs_Quantize_0                    | Quantize    |
| extrinsics_Quantize_0              | Quantize    |
| da_reference_points_cam_Quantize_0 | Quantize    |
| output_Dequantize_0                | Dequantize  |
| lidar2img_mat_Dequantize_0         | Dequantize  |
| Cast_0                             | Cast        |
```

从输出中提取：
- 所有**可删除节点的名称**（第一列）
- 所有**可删除节点的类型**（第二列）
- 确定哪些是用户想删除的，哪些是想保留的

> **提示**：节点名必须与 `hb_model_info` 输出**完全一致**（含大小写、下划线、后缀）。获取节点名后，再决定使用哪种策略。

---

## 策略决策

核心思路：**先确定删除范围，再选择按类型还是按名称删除**。

### 第一步：确定删除范围

| 用户意图 | 策略 |
|---------|------|
| "删除所有 Quantize/Dequantize/Cast" | 按类型删：`remove_node_type` |
| "只删 Quantize，其他不动" | 按类型删：`remove_node_type` |
| "删大部分，但保留几个" | 按名称删：`remove_node_name`（列出要删的，不列要保留的）|
| "只删特定几个节点" | 按名称删：`remove_node_name` |

### 第二步：选择参数

**按类型全删** → 只设 `remove_node_type`

**部分删除（保留某些节点）** → 只设 `remove_node_name`，将查询结果中**除要保留节点外的所有节点名**列入

**按类型全删 + 同时按名称删其他类型** → `remove_node_type` + `remove_node_name` 组合使用

---

## 策略详解

### 策略 1：按类型全删

**场景**：删除所有 Quantize + Dequantize + Cast 节点

```yaml
model_parameters:
  remove_node_type: "Quantize;Dequantize;Cast"
```

**效果**：所有 Quantize、Dequantize、Cast 类型的可删除 IO 节点全部删除。

### 策略 2：按类型删除部分类型

**场景**：只删 Quantize，不动 Dequantize 和 Cast

```yaml
model_parameters:
  remove_node_type: "Quantize"
```

### 策略 3：按名称精确删除（部分删除 — 最常用）

**场景**：想删大部分 Quantize，但保留 `extrinsics` 和 `da_reference_points_cam` 的 Quantize

**步骤**：

1. 运行 `hb_model_info model.bc`，获取所有可删除节点列表
2. 从列表中**排除**要保留的节点（`extrinsics_Quantize_0`、`da_reference_points_cam_Quantize_0`）
3. 将**剩余要删除的节点名**写入 `remove_node_name`

```yaml
model_parameters:
  remove_node_name: "imgs_Quantize_0;other_input_Quantize_0;output_Dequantize_0"
```

> **原理**：`remove_node_name` 是精确匹配，只有在列表中的节点才会被删除。不在列表中的节点（包括你想保留的）不受影响。这就是"跳过不想删的节点"的实现方式。

### 策略 4：按类型删 + 按名称删组合

**场景**：全删 Cast，同时精确删除部分 Quantize 和 Dequantize（保留某些）

```yaml
model_parameters:
  remove_node_type: "Cast"
  remove_node_name: "imgs_Quantize_0;other_Quantize_0;output_Dequantize_0"
```

**效果**：
- Cast：按类型全部删除
- Quantize/Dequantize：仅删除 `remove_node_name` 中列出的节点

---

## 常见坑点

### 1. 不能跳着删除

删除操作只能作用于 IO 节点的**直接相邻**算子，不能跳过靠近 IO 的节点去删除更深层的节点。

例如输入侧图结构：`Input → Quantize → Dequantize → Conv`

- 只能先删除与 Input 直接相邻的 Quantize
- 不能跳过 Quantize 去直接删除 Dequantize
- 若需同时删除 Quantize 和 Dequantize，需使用 `remove_node_type` 按类型批量删除，或分两次操作

### 2. 节点名必须精确匹配

`remove_node_name` 中的节点名必须与 `hb_model_info` 输出的名称完全一致，包括大小写、下划线和后缀编号。建议先用 `hb_model_info` 确认节点名。

### 3. YAML 中没有 preserve 机制

不存在 `preserve_input_nodes` 或 `preserve_output_nodes` 参数。如果要保留某些节点不删，**不要把它们列入 `remove_node_name`** 即可。

### 4. Cast 等类型按类型全删时无法保留部分

使用 `remove_node_type: "Cast"` 会删除所有 Cast 节点，无法保留部分 Cast。如果用户需要保留某些 Cast，需改用 `remove_node_name` 精确指定要删除的 Cast 节点名。

### 5. remove_node_name 只列要删的，不列就是不删

`remove_node_name` 是"黑名单"模式 — 只有明确列出的节点才会被删除。查询结果中没被列入的节点会自动保留。

### 6. 查询结果可能随模型变化

同一个 ONNX 模型在不同量化配置下，可删除的 IO 节点可能不同。每次编译前都应重新运行 `hb_model_info` 确认可删除节点列表。

---

## 操作流程总结

```
1. hb_model_info model.bc
   ↓ 获取所有可删除的 IO 节点名称和类型
2. 确定要保留哪些节点
   ↓ 从可删除列表中排除要保留的
3. 选择策略：
   - 全删某类型 → remove_node_type
   - 部分删除 → remove_node_name（列出要删的节点名）
   - 组合 → remove_node_type + remove_node_name
4. 写入 YAML 配置
5. 编译验证
```

---

## 校验清单

配置完成后，检查以下项：

- [ ] `remove_node_type` 中的类型均在支持列表中（Quantize, Dequantize, Cast, Transpose, Reshape, Softmax）
- [ ] `remove_node_name` 中的节点名与 `hb_model_info` 输出完全一致
- [ ] 要保留的节点**没有**出现在 `remove_node_name` 中
- [ ] 没有跳着删除（删除的节点必须是 IO 直接相邻的）
- [ ] 如需按类型全删某类型同时保留部分，已改用 `remove_node_name` 精确控制

---

## 相关文档

- **编译主流程**：[task-float-to-hbm.md](../tasks/task-float-to-hbm.md) — export/convert/compile 三阶段说明
- **YAML 模型参数**：[model_parameters.md](../yaml/model_parameters.md) — `remove_node_type` / `remove_node_name` 参数定义
- **模型信息查看**：[task-model-inspection.md](../tasks/task-model-inspection.md) — `hb_model_info` 工具使用
- **BC 模型类型判断**：[detect-bc-type.md](detect-bc-type.md) — 判断 BC 是定点还是浮点
