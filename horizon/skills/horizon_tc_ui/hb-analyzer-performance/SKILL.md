---
name: hb-analyzer-performance
description: 使用 hb_analyzer 分析 J5/J6 模型性能。当用户提到模型文件（.onnx/.bc/.hbm）并想了解性能、延时、带宽、BPU利用率、瓶颈、实测、对比时触发。常见场景：评测模型、检查性能、找瓶颈、板端测试、分析 perf JSON。关键词："性能"、"延时"、"带宽"、"BPU"、"瓶颈"、"太慢"、"实测"、"对比"、"评测"、"hb_analyzer"。即使用户没明确说"分析"，只要提到模型+性能相关词就应该触发。
---

# HB Analyzer 模型性能分析

当用户需要在 Horizon Robotics J5/J6 平台上使用 hb_analyzer 工具分析模型性能时，使用此技能。

## 何时使用

- 用户要求分析模型性能
- 用户想检查模型带宽或延时
- 用户提到 "hb_analyzer" 或性能评测
- 用户需要性能报告或瓶颈分析
- 用户想评估浮点/量化模型

## 工作流程

按照以下步骤执行性能分析。详细说明请参考 `references/` 目录中的文档。

### 第 1 步：理解需求

参考：`references/step1-requirements.md`

### 第 2 步：运行分析

参考：`references/step2-run-analysis.md`

### 第 3 步：检查结果

参考：`references/step3-check-results.md`

### 第 4 步：解读报告

参考：`references/step4-interpret-results.md`

> **重要**：对于包含 Transformer/Attention 结构的模型，或延时不达标需要深入分析的场景，必须执行 step4 中的进阶分析（§F Block 级深度分析、§G 量化配置精度审计、§H 模型结构与硬件匹配分析），不能仅停留在算子类型聚合（`hbm_op_time_by_type`）层面。

### 第 5 步：提供建议

参考：`references/step5-recommendations.md`

## 快速参考

**支持的模型格式**：
- ONNX (.onnx)
- HBIR (.bc)
- HBM (.hbm)

**关键输出文件**：
- `hb_analyzer_report.html` - 交互式性能报告
- `analysis_summary.json` - 详细分析数据
- `hb_analyzer*.log` - 执行日志

**常见问题**：参考 `references/troubleshooting.md`
