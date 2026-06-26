---
name: hmct-workflow
description: >
  HMCT 模型转换与精度调优总入口。根据用户意图自动路由：
  (1) 提供了校准数据 → 调用 reference/run_build.py build 执行完整量化构建；
  (2) 未提供校准数据 → 调用 reference/run_build.py check 使用随机数据快速验证转换流程；
  (3) 用户希望进行精度调优 → 转交 j6-hmct-cosine-similarity-tuning SKILL 执行多阶段调优；
  (4) 用户希望进行单项精度 debug 分析（节点灵敏度、数据分布、累积误差等）→ 调用 hmct-debugger CLI 执行对应分析工具。
  当用户提示词中出现 HMCT、模型转换、模型量化、PTQ、精度调优、cosine similarity、节点灵敏度、数据分布、累积误差、debug 等关键词时应触发此 Skill。
---

# HMCT 工作流路由

本 Skill 是 HMCT 工具链的统一入口，根据用户意图自动分发到对应子流程。

## 路由规则

```
用户请求
  │
  ├─ 意图：模型转换 / 量化构建 / PTQ，且提供了校准数据（cali_data_dir）
  │   └─→ 路由 A：完整量化构建
  │
  ├─ 意图：模型转换 / 验证模型 / 快速检查，未提供校准数据
  │   └─→ 路由 B：快速验证
  │
  ├─ 意图：精度调优 / cosine similarity 不达标 / 混精度配置
  │   └─→ 路由 C：精度调优工作流
  │
  ├─ 意图：单项 debug 分析（灵敏度、分布、累积误差等）
  │   └─→ 路由 D：精度 Debug 工具
  │
  └─ 不确定
      └─→ 询问用户意图后再路由
```

---

## 路由 A：完整量化构建（build）

**触发条件：** 用户希望执行模型量化转换，且提供了校准数据。

**关键词：** 模型转换、量化构建、build_model、PTQ 构建、校准

### 需要收集的参数

#### 必填

| 参数 | 说明 |
|------|------|
| `--onnx_path` | 输入 ONNX 模型路径 |

#### 校准数据（二选一）

| 参数 | 说明 |
|------|------|
| `--cali_data_dir` | 校准数据目录（子目录名需与模型输入名一致） |
| `--cali_dict_path` | `cali_dict` JSON 文件路径，指定后将覆盖 `--cali_data_dir` |

#### 可选参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--march` | `nash-p` | BPU 芯片架构 |
| `--input_dict_path` | - | `input_dict` JSON（input_shape / transformer / color_convert 等） |
| `--quant_config_path` | - | `quant_config` JSON（PTQ 量化配置） |
| `--name_prefix` | `model` | 输出模型名称或路径前缀 |
| `--quiet` | 关闭 | 关闭 verbose 输出 |

### 执行方式

```bash
# 最简：ONNX + 校准目录
python3 HMCT_Skill/reference/run_build.py build \
    --onnx_path <模型路径> \
    --cali_data_dir <校准数据目录> \
    --march <芯片架构> \
    --name_prefix <输出前缀>

# 自定义 cali_dict + input_dict
python3 HMCT_Skill/reference/run_build.py build \
    --onnx_path model.onnx \
    --cali_dict_path cali_dict.json \
    --input_dict_path input_dict.json \
    --march nash-e

# 指定 quant_config
python3 HMCT_Skill/reference/run_build.py build \
    --onnx_path model.onnx \
    --cali_data_dir ./cali_data \
    --quant_config_path quant_config.json
```

### 执行步骤

1. 确认 `--onnx_path`，未提供则询问
2. 确认校准数据来源：`--cali_data_dir` 或 `--cali_dict_path`，未提供则询问
3. 根据用户需求收集可选参数（`--input_dict_path` / `--quant_config_path` / `--name_prefix`）
4. 确认 `--march` 参数，未指定则使用默认值 `nash-p`
5. 运行 `run_build.py build` 命令
6. 检查输出日志，确认构建成功
7. 向用户报告结果和输出文件路径

### 参考文档

详细参数说明见 [reference/build_model.md](reference/build_model.md)

---

## 路由 B：快速验证（check）

**触发条件：** 用户希望验证模型是否能走通转换流程，但未提供校准数据。底层基于 `build_model(check_mode=True)`，使用随机数据完成校准。

**关键词：** 验证模型、check_model、快速检查、测试转换、能不能转

### 需要收集的参数

`check` 子命令不接收校准数据相关参数（`--cali_data_dir` / `--cali_dict_path`），其余与路由 A 一致。

#### 必填

| 参数 | 说明 |
|------|------|
| `--onnx_path` | 输入 ONNX 模型路径 |

#### 可选参数

`--march`（默认 `nash-p`）、`--input_dict_path`、`--quant_config_path`、`--name_prefix`、`--quiet`，含义与路由 A 相同。

### 执行方式

```bash
# 最简：仅验证 ONNX 模型可转换
python3 HMCT_Skill/reference/run_build.py check \
    --onnx_path <模型路径> \
    --march <芯片架构>

# 验证 + 自定义 input_dict
python3 HMCT_Skill/reference/run_build.py check \
    --onnx_path model.onnx \
    --input_dict_path input_dict.json \
    --march nash-e
```

### 执行步骤

1. 确认 `--onnx_path`，未提供则询问
2. 根据用户需求收集可选参数（`--input_dict_path` / `--quant_config_path` / `--name_prefix`）
3. 确认 `--march` 参数，未指定则使用默认值 `nash-p`
4. 运行 `run_build.py check` 命令
5. 检查输出，若通过则告知用户模型兼容；若失败则分析错误原因

### 参考文档

详细参数说明见 [reference/build_model.md](reference/build_model.md)

---

## 路由 C：精度调优工作流

**触发条件：** 用户希望对量化后模型进行精度调优，或反馈 cosine similarity 不达标。

**关键词：** 精度调优、cosine similarity、精度不达标、混精度、INT16、敏感节点、node_config、PTQ 调优

### 转交目标

转交至 **j6-hmct-cosine-similarity-tuning** Skill 处理。

### 需要收集的参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `--onnx_path` | 是 | 输入 ONNX 模型路径 |
| `--cali_data_dir` | 是 | 校准数据目录 |
| `--march` | 否 | BPU 芯片架构，默认 `nash-p` |
| `--work_dir` | 否 | 工作目录，默认 ONNX 所在目录 |
| `--node_config_path` | 否 | 固定节点配置文件 |
| `--num_sample` | 否 | 敏感度分析的 bad case 数量，默认 1 |
| `--progressive_thresholds` | 否 | 渐进阈值列表，默认 `0.99 0.999 0.9999 0.99999` |
| `--calibration_type` | 否 | 激活校准方法，写入 `model_config.activation.calibration_type`；默认不指定（由 HMCT 决定）；可传单值（如 `max`）或多值（如 `max kl`，触发 modelwise search），可选值参考 HMCT：`max`、`kl`、`load` 等 |
| `--per_channel` | 否 | 激活 per-channel 量化开关，写入 `model_config.activation.per_channel`；接受 `true/false`（可同时传两个值触发搜索），HMCT 默认 `false` |
| `--asymmetric` | 否 | 激活非对称量化开关，写入 `model_config.activation.asymmetric`；接受 `true/false`（可同时传两个值触发搜索），HMCT 默认 `false` |
| `--bias_correction` | 否 | 是否开启权重 bias correction，写入 `model_config.weight.bias_correction`；接受 `true/false`，HMCT 默认 `disabled` |
| `--bias_correction_num_sample` | 否 | bias correction 样本数（`int >= 1`），仅 `--bias_correction true` 时生效，HMCT 默认 `1` |
| `--bias_correction_metric` | 否 | bias correction 误差度量，可选 `cosine-similarity`/`mse`/`mae`/`mre`/`sqnr`/`chebyshev`，仅 `--bias_correction true` 时生效，HMCT 默认 `cosine-similarity` |

### 执行方式

```bash
# 默认（由 HMCT 自动选择校准方法）
python3 HMCT_Skill/j6-hmct-cosine-similarity-tuning/script/hmct_precision_tuning.py \
    --onnx_path <模型路径> \
    --cali_data_dir <校准数据目录> \
    --march <芯片架构>

# 显式指定单一校准方法
python3 HMCT_Skill/j6-hmct-cosine-similarity-tuning/script/hmct_precision_tuning.py \
    --onnx_path <模型路径> \
    --cali_data_dir <校准数据目录> \
    --calibration_type max

# 多校准方法（HMCT 触发 modelwise search）
python3 HMCT_Skill/j6-hmct-cosine-similarity-tuning/script/hmct_precision_tuning.py \
    --onnx_path <模型路径> \
    --cali_data_dir <校准数据目录> \
    --calibration_type max kl

# 显式开关 per_channel / asymmetric / bias_correction
python3 HMCT_Skill/j6-hmct-cosine-similarity-tuning/script/hmct_precision_tuning.py \
    --onnx_path <模型路径> \
    --cali_data_dir <校准数据目录> \
    --per_channel true false \
    --asymmetric true false \
    --bias_correction true \
    --bias_correction_num_sample 4 \
    --bias_correction_metric mse
```

### 执行步骤

1. 确认用户提供了 `onnx_path` 和 `cali_data_dir`（精度调优必须有校准数据），未提供则询问
2. 确认 `march` 参数
3. 按 [j6-hmct-cosine-similarity-tuning/SKILL.md](j6-hmct-cosine-similarity-tuning/SKILL.md) 中定义的完整流程执行
4. 调优完成后向用户报告结果，包括达标配置和调优报告路径

### 调优流程概览

```
INT8 基线 → 全 INT16 ─┬─ 达标 → INT8+INT16 渐进回退
                      └─ 未达标 → INT16+dual-int16 ─┬─ 达标 → 渐进回退
                                                    └─ 未达标 → 全 FP16 ─┬─ 达标 → 渐进回退
                                                                         └─ 未达标 → 深层分析
```

### 参考文档

完整调优流程见 [j6-hmct-cosine-similarity-tuning/SKILL.md](j6-hmct-cosine-similarity-tuning/SKILL.md)

---

## 路由 D：精度 Debug 工具（单项分析）

**触发条件：** 用户希望针对性地运行某一项 debug 分析（如节点灵敏度、数据分布、累积误差），而非完整调优流程。

**关键词：** 节点灵敏度、数据分布、逐通道分布、累积误差、tensor 分析、debug、hmct-debugger

### 可用工具

| 工具 | 说明 | CLI 命令 |
|------|------|----------|
| `get-sensitivity-of-nodes` | 节点灵敏度排序 | `hmct-debugger get-sensitivity-of-nodes` |
| `plot-distribution` | 量化前后数据分布对比 | `hmct-debugger plot-distribution` |
| `get-channelwise-data-distribution` | 逐通道数据分布 | `hmct-debugger get-channelwise-data-distribution` |
| `plot-acc-error` | 逐层累积误差可视化 | `hmct-debugger plot-acc-error` |
| `tensor-analysis` | 张量级详细分析 | `hmct-debugger tensor-analysis` |
| `sensitivity-analysis` | 敏感节点深入分析 | `hmct-debugger sensitivity-analysis` |
| `runall` | 一键运行全部 debug 功能 | `hmct-debugger runall` |

### 需要收集的参数

| 参数 | 必填 | 说明 |
|------|------|------|
| 模型路径 | 是 | 校准后的模型文件路径 |
| 校准数据路径 | 是 | 校准数据路径 |
| 分析目标节点 | 视工具而定 | 部分工具需要指定节点列表 |

### 执行步骤

1. 确认用户需要运行哪项分析工具
2. 确认模型路径和校准数据路径
3. 如果不确定运行哪项，建议先运行 `runall` 一键分析
4. 使用 CLI 命令或 Python API 执行，向用户报告输出路径

### 参考文档

完整参数说明见 [reference/debug_tools.md](reference/debug_tools.md)

---

## 路由判定示例

| 用户输入 | 路由 | 原因 |
|----------|------|------|
| "帮我把 model.onnx 转换为量化模型，校准数据在 ./cali_data" | A | 有校准数据，执行完整构建 |
| "构建时帮我加上 input_dict 做归一化预处理" | A | 需要传 `--input_dict_path` |
| "用 quant_config.json 量化这个模型" | A | 显式 `--quant_config_path` |
| "我想看下这个模型能不能在 nash-e 上跑通" | B | 验证意图，无校准数据 |
| "帮我验证一下 model.onnx 能否转换成功" | B | 验证意图 |
| "用随机数据快速跑一遍流程，校验 input_dict 配置" | B | 验证意图 + `--input_dict_path` |
| "量化后精度下降了，帮我调优" | C | 精度调优意图 |
| "cosine similarity 只有 0.95，怎么提升" | C | 精度不达标 |
| "帮我做混精度配置，把敏感节点设成 INT16" | C | 精度调优意图 |
| "调优时用 max 校准方法" / "用 kl 和 max 一起搜一下校准" | C | 精度调优 + `--calibration_type` |
| "开启 per-channel 权重量化做调优" / "试试 asymmetric 激活" / "加上 bias correction" | C | 精度调优 + 量化策略开关 |
| "帮我看看哪些节点灵敏度最差" | D | 单项 debug 分析 |
| "画一下 conv1 的数据分布" | D | 单项 debug 分析 |
| "跑一下累积误差分析" | D | 单项 debug 分析 |
| "我有个 ONNX 模型想用 HMCT 处理" | 询问 | 意图不明确，需进一步确认 |

---

## 目录结构

```
HMCT_Skill/
├── SKILL.md                                    ← 本文件（路由入口）
├── reference/
│   ├── build_model.md                          ← build_model / check_model 参考文档
│   ├── run_build.py                            ← 一键构建/验证脚本
│   └── debug_tools.md                          ← 精度 debug 工具参考文档
└── j6-hmct-cosine-similarity-tuning/
    ├── SKILL.md                                ← 精度调优 Skill 定义
    ├── example.md                              ← Prompt 示例
    └── script/
        ├── hmct_precision_tuning.py            ← 主调优脚本（含构建逻辑）
        └── get_sensitivity_of_nodes.py         ← 敏感度分析脚本
```
