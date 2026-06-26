# horizon-tc-ui 文档索引

本文档提供三视图索引，按不同维度组织所有参考文档。

## 一、按任务视图（用户想干什么）

首选入口。按用户意图组织，每个任务对应一个端到端的指南。

| 任务 | 关键词 | 文件 |
|---|---|---|
| 从零写 YAML 配置 | 生成yaml、模板、配置 | [task-yaml-authoring.md](tasks/task-yaml-authoring.md) |
| 完整编译流程（ONNX→HBM） | 编译、量化、HBM | [task-float-to-hbm.md](tasks/task-float-to-hbm.md) |
| 快速性能估算 | fast-perf、性能、不要精度 | [task-fast-perf.md](tasks/task-fast-perf.md) |
| 精度掉点调优 | calibration、量化调优、掉点 | [task-calibration-tuning.md](tasks/task-calibration-tuning.md) |
| 精度分析调试 | cosine、consistency、精度 | → Delegate 见 [delegations.md](delegations.md) |
| 编译失败排查 | 编译报错、OP不支持 | [task-compile-debug.md](tasks/task-compile-debug.md) |
| 性能分析调试 | 性能瓶颈、perf | → Delegate 见 [delegations.md](delegations.md) |
| 查看模型信息 | 模型信息、输入输出shape | [task-model-inspection.md](tasks/task-model-inspection.md) |
| 评估数据预处理 | eval_preprocess、评估数据 | [task-eval-preprocess.md](tasks/task-eval-preprocess.md) |
| 板端部署验证 | 板端、SSH、推理验证 | [task-board-deploy-verify.md](tasks/task-board-deploy-verify.md) |

## 二、按工具视图（6个 CLI 工具）

按 CLI 工具组织，每个工具一份完整参考手册。

| 工具 | 一句话定位 | 文件 |
|---|---|---|
| `hb_compile` | 模型编译主工具：ONNX/Caffe → PTQ → HBIR → HBM | [hb_compile.md](tools/hb_compile.md) |
| `hb_model_info` | 查看模型信息：支持 .onnx / .bc / .hbm | [hb_model_info.md](tools/hb_model_info.md) |
| `hb_verifier` | 精度验证：仿真 vs 板端一致性对比 | [hb_verifier.md](tools/hb_verifier.md) |
| `hb_analyzer` | 性能分析 + 模型可视化 | [hb_analyzer.md](tools/hb_analyzer.md) |
| `hb_config_generator` | 生成 YAML 配置模板 | [hb_config_generator.md](tools/hb_config_generator.md) |
| `hb_eval_preprocess` | 评估数据预处理 | [hb_eval_preprocess.md](tools/hb_eval_preprocess.md) |

## 三、按模块视图（参数、排错、脚本）

### YAML 配置参考

| 文件 | 内容 |
|---|---|
| [overview.md](yaml/overview.md) | 四大 section 概览 + 权威 schema 声明 |
| [model_parameters.md](yaml/model_parameters.md) | 模型参数组详解 |
| [input_parameters.md](yaml/input_parameters.md) | 输入参数组详解 |
| [calibration_parameters.md](yaml/calibration_parameters.md) | 校准参数组详解 |
| [compiler_parameters.md](yaml/compiler_parameters.md) | 编译参数组详解 |
| [common-errors.md](yaml/common-errors.md) | YAML 常见报错按原文倒排索引 |
| [recipes-by-task.md](yaml/recipes-by-task.md) | 按任务类别的推荐参数组合 |

### Troubleshooting

| 文件 | 内容 |
|---|---|
| [yaml-schema-errors.md](troubleshooting/yaml-schema-errors.md) | YAML schema 校验报错 |
| [compile-errors.md](troubleshooting/compile-errors.md) | hb_compile 编译报错 |
| [calibration-errors.md](troubleshooting/calibration-errors.md) | 校准/量化报错 |
| [runtime-errors.md](troubleshooting/runtime-errors.md) | 运行时/推理报错 |
| [board-ssh-errors.md](troubleshooting/board-ssh-errors.md) | 板端 SSH 连接报错 |

### 脚本（scripts/）

| 文件 | 内容 |
|---|---|
| [README.md](../scripts/README.md) | 脚本统一调用规约 |
| validate_yaml.py | YAML 预检（调用 ParamsParser） |
| parse_compile_log.py | 编译日志解析 |
| extract_verifier_summary.py | 验证结果摘要提取 |
| diff_yaml.py | 两份 YAML 对比 |
| detect_env.py | 环境检测（版本/依赖/PATH） |
| export_schema.py | 从 schema_yaml.py 导出 JSON Schema |

### 提示（Tips）

| 文件 | 内容 |
|---|---|
| [detect-bc-type.md](tips/detect-bc-type.md) | BC 模型定点/浮点类型判断方法 |
| [remove-io-nodes.md](tips/remove-io-nodes.md) | 删除/保留模型 IO 节点（QDQ/Cast 等）策略指南 |

### 资产（assets/）

| 目录 | 内容 |
|---|---|
| `assets/templates/` | 4 个 YAML 模板（simple/full/fast_perf/check） |
| `assets/recipes/` | 真实任务骨架配置（分类/检测/分割/多输入/fast_perf） |
| `assets/schemas/` | JSON Schema（由 export_schema.py 自动生成） |
