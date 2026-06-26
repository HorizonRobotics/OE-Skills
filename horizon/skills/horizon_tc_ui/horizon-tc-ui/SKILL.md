---
name: horizon-tc-ui
description: >
  OpenExplorer 工具链 CLI 包的集成 Skill。适用于处理 hb_compile、hb_model_info、
  hb_verifier、hb_analyzer、hb_config_generator、hb_eval_preprocess 等工具相关问题，
  包括 YAML 配置编写、ONNX/Caffe 模型编译、PTQ 量化、HBIR/HBM 产物生成、
  模型信息查看、精度验证、性能分析、评估数据预处理和板端部署验证。
  当用户提到 OpenExplorer、horizon_tc_ui、工具链、编译模型、生成 YAML、量化、
  calibration、HBIR、HBM、march、fast-perf、check 模式、板端推理、
  定点/浮点 BC 模型判断等场景时，应优先使用本 Skill。
---

# horizon-tc-ui Skill

## 适用范围

本 Skill 用于 OpenExplorer 工具链 CLI 包相关任务，覆盖以下六个核心工具：

- `hb_compile`
- `hb_model_info`
- `hb_verifier`
- `hb_analyzer`
- `hb_config_generator`
- `hb_eval_preprocess`

主要覆盖流程：

```text
ONNX/Caffe 模型 → YAML 配置 → PTQ 量化 → HBIR(.bc) → HBM(.hbm) → 精度验证 / 性能分析 / 板端部署
```

## 触发词

以下关键词触发本 Skill：

- **工具名**：`hb_compile`、`hb_model_info`、`hb_verifier`、`hb_analyzer`、`hb_config_generator`、`hb_eval_preprocess`
- **领域术语**：`yaml配置`、`编译`、`量化`、`板端部署`、`PTQ`、`HBIR`、`HBM`、`march`、`calibration`、`cal_data_dir`、`定点`、`浮点`、`bc类型`
- **常见操作**：`生成yaml`、`编译模型`、`模型信息`、`精度验证`、`性能分析`、`板端推理`、`fast-perf`、`check模式`
- **架构名**：`nash-b-lite`、`nash-b`、`nash-b-plus`、`nash-e`、`nash-m`、`nash-p`、`nash-h`
- **项目名**：`horizon_tc_ui`、`OpenExplorer`、`工具链`

## 场景路由表

用户意图 → 参考文件：

| 用户想做什么 | 关键词示例 | 参考文件 |
|---|---|---|
| 从零写 YAML 配置 | 生成yaml、写配置、模板 | `references/tasks/task-yaml-authoring.md` |
| 编译模型为 HBM | 编译、hb_compile、量化 | `references/tasks/task-float-to-hbm.md` |
| 快速性能估算 | fast-perf、性能估算、不要精度 | `references/tasks/task-fast-perf.md` |
| 精度掉点调优 | 精度掉点、calibration、量化调优 | `references/tasks/task-calibration-tuning.md` |
| 精度分析调试 | 精度分析、cosine、consistency | → **Delegate** 见 [delegations.md](references/delegations.md) |
| 编译失败排查 | 编译报错、OP不支持、shape推导 | `references/tasks/task-compile-debug.md` |
| 性能分析调试 | 性能分析、perf、瓶颈 | → **Delegate** 见 [delegations.md](references/delegations.md) |
| 查看模型信息 | 模型信息、hb_model_info、输入输出 | `references/tasks/task-model-inspection.md` |
| 评估数据预处理 | hb_eval_preprocess、评估数据 | `references/tasks/task-eval-preprocess.md` |
| 板端部署验证 | 板端、hb_verifier、SSH、推理 | `references/tasks/task-board-deploy-verify.md` |
| 判断 BC 模型定点/浮点 | 定点、浮点、bc类型、quantized/float bc | `references/tips/detect-bc-type.md` |
| 删除/保留模型 IO 节点 | 删除节点、删Quantize、删Dequantize、删Cast、保留节点、remove_node_type、remove_node_name | `references/tips/remove-io-nodes.md` |
| YAML 参数含义查询 | 参数说明、schema、字段 | `references/yaml/overview.md` |
| 报错排查 | 报错、error、失败 | `references/troubleshooting/` 下对应文件 |

## Delegate 决策

本 Skill 在以下场景 delegate 到外部 Skill：

| 场景 | Delegate 目标 | 判定条件 |
|---|---|---|
| 精度分析（cosine/consistency 深度分析） | `horizon-model-cosine-analyzer` | 用户询问精度掉点原因、逐层 cosine 对比、定位精度问题根因 |
| 性能分析（HBM 性能瓶颈分析） | `hb-analyzer-performance` | 用户询问性能瓶颈、算子耗时、内存占用优化 |

**模糊场景处理原则**：

- 编译 + 性能：先完成编译产出 HBM，再进行性能分析
- 精度 + 性能：先确认精度达标，再分析性能
- 编译失败 + 精度问题：先解决编译问题

详细 delegate 规则见 [references/delegations.md](references/delegations.md)。

## 快速参考

```bash
# 生成 YAML 模板
hb_config_generator -s                                # 简单模板
hb_config_generator -f -m model.onnx --march nash-e   # 完整模板（带模型信息）

# 编译模型
hb_compile -c config.yaml                             # 标准编译
hb_compile -m model.onnx --march nash-e               # check 模式（自动生成 yaml）
hb_compile --fast-perf -m model.onnx --march nash-e   # fast-perf 模式

# 查看模型信息
hb_model_info model.onnx                              # ONNX 模型信息
hb_model_info model.bc                                # HBIR 模型信息
hb_model_info model.hbm                               # HBM 模型信息

# ⚠️ 下方命令会阻塞终端：
# -v 会启动 HTTP 服务，进程不会自动退出，必须 Ctrl+C 终止
hb_model_info model.hbm -v                            # 可视化模型结构（阻塞，需手动关闭）

# 精度验证
hb_verifier -m model.onnx,model.hbm -i input.bin       # 一致性验证

# 性能分析
hb_analyzer analyze -m model.hbm --march nash-e        # 分析模型

# ⚠️ 下方命令会阻塞终端：
# visualize 会启动 HTTP 服务，进程不会自动退出，必须 Ctrl+C 终止
hb_analyzer visualize -m model.bc                      # 可视化（阻塞，需手动关闭）

# 评估数据预处理
hb_eval_preprocess -m mobilenetv1 -i ./images -o ./output
```

## 通用工作流

```text
ONNX/Caffe 模型
    │
    ├─ 1. hb_config_generator 生成 YAML 模板
    │
    ├─ 2. 编辑 YAML 配置（填写模型路径、march、输入参数等）
    │
    ├─ 3. hb_compile -c config.yaml  →  PTQ量化 → HBIR(.bc) → HBM(.hbm)
    │
    ├─ 4. hb_verifier 验证精度（板端/仿真）
    │
    ├─ 5. hb_analyzer 分析性能
    │
    └─ 6. hb_model_info 查看最终模型信息
```

## 产物约定

| 产物 | 默认路径 | 说明 |
|---|---|---|
| HBM 模型 | `{working_dir}/{prefix}.hbm` | 最终编译产物 |
| HBIR 模型 | `{working_dir}/{prefix}_quantized_model.bc` | 量化中间产物 |
| 编译日志 | `{working_dir}/hb_compile.log` | 自动复制 |
| 性能 JSON | `{working_dir}/{prefix}.json` | hbm_perf 产出 |
| Per-graph 性能 JSON | `.hb_analyzer/<graph_name>.json` | hb_analyzer 核心数据源（FPS、latency、计算量、带宽等） |
| 分析汇总 | `.hb_analyzer/analysis_summary.json` | hb_analyzer 汇总数据（`hbm_key_indicators` 为 list 结构） |
| 验证日志 | `hb_verifier.log` | 精度验证结果 |
| 分析报告 | `.hb_analyzer/hb_analyzer_report.html` | hb_analyzer 产出 |

## 使用原则

处理用户问题时优先遵循以下顺序：

1. 先判断用户处于哪个阶段：配置、编译、量化、验证、性能分析、部署或排错。
2. 再根据“场景路由表”选择对应参考文件。
3. 如果用户提供了 YAML、命令、日志或报错信息，应优先基于用户给出的上下文分析，不要泛泛解释。
4. 如果涉及阻塞命令，例如 `hb_model_info -v` 或 `hb_analyzer visualize`，必须提醒用户该命令会启动服务并持续占用终端。
5. 如果问题属于精度深度分析或性能瓶颈深度分析，应根据 Delegate 规则交给对应 Skill。
6. 如果用户问题同时包含多个阶段，先处理前置阻塞项，例如先解决编译失败，再分析精度或性能。

## 全量导航

完整的文档索引见 [references/INDEX.md](references/INDEX.md)。