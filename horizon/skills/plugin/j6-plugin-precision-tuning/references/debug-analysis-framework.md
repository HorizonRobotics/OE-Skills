# floatvscalib Debug 结果解读框架

本文档定义了如何从 float vs calibration（fake_quant）的 debug 产物中解读精度问题，并给出差异化的修复建议。

## 1. 产物文件说明

| 文件 | 内容 | 关键字段 |
|------|------|----------|
| `badcase.txt` | Badcase 索引与指标汇总 | 样本编号、L1/COSINE/ATOL 各指标值 |
| `compare_per_layer_out.csv` | 逐层对比数据（float vs calibration） | `base_model_min`, `base_model_max`, `analy_model_min`, `analy_model_max`, `COSINE`, `ATOL`, `max_qscale_diff` |
| `abnormal_layer_advisor.csv` | 异常层检测（clamp error 统计） | 算子名、clamp error 数量、`Set fixed scale X` 建议值 |
| `output_xxx_sensitive_ops.txt` | 敏感度排序表（按输出指标排列） | 算子名、ATOL 值、当前 dtype、clamp error 百分比 |
| `statistic.txt`（analysis_model / baseline_model） | 各层的量化统计信息 | scale、min、max、mean、var |
| `qconfig_dtypes.pt.py` | 各模块的量化 dtype 配置 | input/weight/output dtype |

## 2. 误差类型分类标准

对每个 top-k 敏感算子，结合 `compare_per_layer_out.csv` 和 `abnormal_layer_advisor.csv` 判定误差类型：

### 截断误差（Truncation Error）

**定义**：量化 scale 过小，导致数据超出量化范围被 clamp 截断。

**数据特征**（满足任意一条即可判定）：
- `abnormal_layer_advisor.csv` 中该算子有 clamp error 报告
- `base_model_max` 与 `analy_model_max` 差异显著（analy_model 的值域被截断，明显窄于 base_model）
- `base_model_min` 与 `analy_model_min` 差异显著（同理）
- 算子数据中存在 `Set fixed scale X` 建议值

**典型场景**：backbone 的 ReLU 激活、encoder 的 SiLU 激活、数据范围随 batch 变化大的算子。

### 舍入误差（Rounding Error）

**定义**：量化范围足够，但 int8 的精度粒度不够（256 级量化无法精确表示连续值）。

**数据特征**（需同时满足）：
- `base_model` 与 `analy_model` 的 min/max 范围接近（量化范围未被截断）
- 但 COSINE < 0.95 或 ATOL 仍然较大
- `max_qscale_diff` 较小（scale 差异不大，说明范围覆盖没问题）
- `abnormal_layer_advisor.csv` 中该算子无显著 clamp error

**典型场景**：decoder 的 self-attention matmul、softmax 后的 mul、attention score 分布尖锐的算子。

## 3. 误差类型→解决方案对照表

| 误差类型 | 解决方案 | 具体操作 | 优先级 |
|----------|----------|----------|--------|
| **截断误差** | fix-scale | 从 `abnormal_layer_advisor.csv` 中读取该算子的 `Set fixed scale X` 建议值，通过 `FixedScaleObserver` 或 `ModuleNameTemplate(threshold=X)` 手动设置 fix-scale 为该算子实际数据范围 | 高 |
| **截断误差** | 增加校准样本量 | 将校准样本量从当前数量增加到 50~100 张，使 scale 的统计估计更准确，减少 outlier 导致的 clamp error | 中 |
| **舍入误差** | 提高量化精度 | 通过 `QconfigSetter` 的 `ModuleNameTemplate` 将对应算子的 output dtype 从 qint8 提升到 qint16 | 高 |
| **舍入误差** | SensitivityTemplate 调优 | 使用 `SensitivityTemplate` 做系统性混合精度调优，自动搜索最优 dtype 组合 | 中 |

## 4. Top-k 敏感算子逐一分析流程

在解读 floatvscalib debug 结果时，**必须**对敏感度排序表中 top-5 的算子逐一执行以下步骤：

### 步骤 1：提取算子列表

从 `output_xxx_sensitive_ops.txt` 中提取 top-5 敏感算子名称和对应的 ATOL 值。

### 步骤 2：逐算子检索逐层对比数据

对每个算子，用 grep 从 `compare_per_layer_out.csv` 中提取完整行数据：

```bash
grep "<算子名>" compare_per_layer_out.csv
```

提取以下字段：
- `base_model_min`, `base_model_max`（float 模型的值域）
- `analy_model_min`, `analy_model_max`（calibration 模型的值域）
- `COSINE`, `ATOL`（精度指标）
- `max_qscale_diff`（scale 差异）

### 步骤 3：判定误差类型

按第 2 节的标准，对比 base_model 和 analy_model 的 min/max：
- 若 analy_model 值域被截断（明显窄于 base_model）→ **截断误差**
- 若值域接近但 COSINE/ATOL 仍差 → **舍入误差**

### 步骤 4：给出差异化修复建议

按第 3 节的对照表，为每个算子给出具体修复建议：
- 截断误差：列出 abnormal_layer_advisor 中的 fix-scale 建议值，并建议增加样本量
- 舍入误差：建议提升 dtype 到 qint16，并给出具体的 QconfigSetter 配置

### 步骤 5：在报告中结构化输出

在分析报告的「关键发现」部分，对每个 top-k 算子输出：

```
#### 算子：<算子名>
- 敏感度排名：Top-X（ATOL=Y.YY）
- 值域对比：base_model [min, max] vs analy_model [min, max]
- 误差类型：截断误差 / 舍入误差
- 修复建议：<具体方案>
```

## 5. 常见误区

| 误区 | 正确做法 |
|------|----------|
| 将所有精度问题统一归为"量化精度不足"并建议提升 dtype | 先做误差归因，截断和舍入的修复方案不同 |
| 只看敏感度排名，不检索 compare_per_layer_out 数据 | 必须逐算子提取 min/max 数据才能判定误差类型 |
| 忽略 abnormal_layer_advisor.csv 中的 fix-scale 建议值 | 这些建议值是数据驱动的，应直接引用 |
| 只看 COSINE/ATOL 数值大小，不看 min/max 范围 | COSINE/ATOL 告诉你"有多差"，min/max 告诉你"为什么差" |
