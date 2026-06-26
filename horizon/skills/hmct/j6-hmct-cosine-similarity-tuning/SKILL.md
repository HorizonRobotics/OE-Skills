---
name: j6-hmct-cosine-similarity-tuning
description: >
  HMCT PTQ 精度调优工作流。自动按 INT8→INT16→dual-int16→FP16 逐级验证上限，
  结合节点敏感度分析渐进回退，找到满足 Cosine Similarity 阈值（默认 >=0.99）的
  最小混精度 quant_config，产出达标配置与调优报告。
  触发关键词：HMCT 精度调优、PTQ 调优、量化精度、cosine similarity 不达标、混合精度。
---

# J6 HMCT Cosine Similarity 调优（工作流）

## 适用前提（必须一致）

- **同一 onnx / 同一校准数据 / 同一评测口径**：对比不同量化配置时只改变 `quant_config`，其余输入保持一致。
- **目标**：以 HMCT 打印的 `The quantized model output` 中 **Cosine Similarity（输出节点级）** 为达标指标（默认阈值 ≥0.99）。

## 脚本文件

本 Skill 提供以下脚本：

| 脚本 | 说明 |
|------|------|
| `script/hmct_precision_tuning.py` | **主调优脚本**：自动执行阶段 1-7 完整流程 |
| `script/get_sensitivity_of_nodes.py` | 节点敏感度分析脚本 |

## 快速开始

### 完整自动调优（推荐）

```bash
python3 script/hmct_precision_tuning.py \
  --onnx_path "model.onnx" \
  --cali_data_dir "./cali_data" \
  --march nash-p
```

### 使用用户固定配置

```bash
python3 script/hmct_precision_tuning.py \
  --onnx_path "model.onnx" \
  --cali_data_dir "./cali_data" \
  --node_config_path "fixed_config.json"
```

### 指定 bad case 数量

```bash
python3 script/hmct_precision_tuning.py \
  --onnx_path "model.onnx" \
  --cali_data_dir "./cali_data" \
  --num_sample 5
```

### 自定义渐进式阈值

```bash
python3 script/hmct_precision_tuning.py \
  --onnx_path "model.onnx" \
  --cali_data_dir "./cali_data" \
  --progressive_thresholds 0.99 0.999 0.9999
```

### 指定校准方法（默认不指定）

默认情况下脚本不在 `quant_config` 中写入 `calibration_type`，由 HMCT 内部决定校准策略。
若需要显式指定，可使用 `--calibration_type`：

```bash
# 单一方法
python3 script/hmct_precision_tuning.py \
  --onnx_path "model.onnx" \
  --cali_data_dir "./cali_data" \
  --calibration_type max

# 多方法（HMCT 会做 modelwise search）
python3 script/hmct_precision_tuning.py \
  --onnx_path "model.onnx" \
  --cali_data_dir "./cali_data" \
  --calibration_type max kl
```

可选值参考 HMCT：`max`、`kl`、`load` 等。

### 配置量化策略开关（默认不指定）

可在调优过程中显式开关三类量化策略，所有阶段都会以相同配置写入 `quant_config`：

| 参数 | 写入字段 | 含义 |
|------|----------|------|
| `--per_channel` | `model_config.activation.per_channel` | 激活 per-channel 量化开启与否，可选 `false` / `true`，HMCT 默认 `false`；支持同时传两个值（如 `true false`）触发 modelwise search |
| `--asymmetric` | `model_config.activation.asymmetric` | 激活非对称量化开启与否，可选 `false` / `true`，HMCT 默认 `false`；支持同时传两个值触发 modelwise search |
| `--bias_correction` | `model_config.weight.bias_correction` | 是否开启权重 bias correction；当为 `true` 时写入 `bias_correction` 子结构 |
| `--bias_correction_num_sample` | `model_config.weight.bias_correction.num_sample` | bias correction 样本数，`int >= 1`，默认 `1`；仅当 `--bias_correction true` 时生效 |
| `--bias_correction_metric` | `model_config.weight.bias_correction.metric` | bias correction 误差度量，可选 `cosine-similarity` / `mse` / `mae` / `mre` / `sqnr` / `chebyshev`，默认 `cosine-similarity`；仅当 `--bias_correction true` 时生效 |

`--per_channel` / `--asymmetric` / `--bias_correction` 接受布尔字面量（`true`/`false`、`1`/`0`、`yes`/`no`、`on`/`off`）。**不传即不写入**，由 HMCT 走默认策略。

```bash
# 启用 per_channel + asymmetric 的搜索（HMCT 自动比较 true/false 两种）
python3 script/hmct_precision_tuning.py \
  --onnx_path "model.onnx" \
  --cali_data_dir "./cali_data" \
  --per_channel true false \
  --asymmetric true false

# 启用 bias_correction，并自定义 num_sample / metric
python3 script/hmct_precision_tuning.py \
  --onnx_path "model.onnx" \
  --cali_data_dir "./cali_data" \
  --bias_correction true \
  --bias_correction_num_sample 4 \
  --bias_correction_metric mse

# 仅启用 per_channel，其余沿用 HMCT 默认
python3 script/hmct_precision_tuning.py \
  --onnx_path "model.onnx" \
  --cali_data_dir "./cali_data" \
  --per_channel true
```

## 参数说明

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--onnx_path` | ✓ | - | 输入 ONNX 模型路径 |
| `--cali_data_dir` | ✓ | - | 校准数据目录（子目录名需与输入名一致） |
| `--march` | | `nash-p` | BPU 架构 |
| `--work_dir` | | ONNX所在目录 | 工作目录 |
| `--node_config_path` | | - | 用户固定配置文件（不会被覆盖） |
| `--num_sample` | | `1` | 敏感度分析时查找的 bad case 数量 |
| `--progressive_thresholds` | | `[0.99, 0.999, 0.9999, 0.99999]` | 渐进式提升到高精度算子的阈值列表 |
| `--calibration_type` | | 不指定（HMCT 默认） | 激活校准方法，写入 `model_config.activation.calibration_type`；可传单值或多值（多值会触发 modelwise search） |
| `--per_channel` | | 不指定（HMCT 默认 `false`） | 激活 per-channel 量化，写入 `model_config.activation.per_channel`；接受 `true/false`，可传两个值触发搜索 |
| `--asymmetric` | | 不指定（HMCT 默认 `false`） | 激活非对称量化，写入 `model_config.activation.asymmetric`；接受 `true/false`，可传两个值触发搜索 |
| `--bias_correction` | | 不指定（HMCT 默认 `disabled`） | 是否开启权重 bias correction，写入 `model_config.weight.bias_correction`；接受 `true/false` |
| `--bias_correction_num_sample` | | 不指定（HMCT 默认 `1`） | bias correction 样本数（`int >= 1`），仅 `--bias_correction true` 时生效 |
| `--bias_correction_metric` | | 不指定（HMCT 默认 `cosine-similarity`） | bias correction 误差度量，可选 `cosine-similarity`/`mse`/`mae`/`mre`/`sqnr`/`chebyshev`，仅 `--bias_correction true` 时生效 |

## 输出

- 各阶段输出保存在独立目录
- `tuning_report.md`：调优报告
- `final_quant_config.json`：达标配置

## 输出目录

| 阶段 | save_dir |
|------|----------|
| 阶段 1（INT8 基线） | `./output_int8` |
| 阶段 2（全 INT16） | `./output_int16` |
| 阶段 3（INT8+INT16 渐进回退） | `./output_int8_int16_mixed` |
| 阶段 4（INT16+dual-int16） | `./output_dual_int16` |
| 阶段 5（INT16+dual-int16 渐进回退） | `./output_int16_dual_int16_mixed` |
| 阶段 6（全 FP16） | `./output_float16` |
| 阶段 7（INT16+FP16 渐进回退） | `./output_dual_int16_float16_mixed` |

## 自动调优主流程

整体按一条从低代价到高代价的链路推进：

```
INT8 基线 → 全 INT16 ─┬─ 达标 → INT8+INT16 渐进混合回退（寻找最小 INT16 集合）
                     └─ 未达标 → INT16+dual-int16 ─┬─ 达标 → INT16 + dual-int16 渐进混合回退
                                                  └─ 未达标 → 全 FP16 ─┬─ 达标 → INT16+dual-int16+FP16 渐进混合回退
                                                                      └─ 未达标 → 深层分析
```

### 阶段 1：INT8 基线

- **目的**：确认全 INT8 退化幅度，作为调优基线
- **判定**：若所有输出均 ≥0.99，结束；否则进入阶段 2

### 阶段 2：全 INT16 上限

- **目的**：判断是否为 INT8 位宽问题
- **判定**：若达标进入阶段 3；否则进入阶段 4

### 阶段 3：INT8 + INT16 渐进混合回退

- **前提**：阶段 2 全 INT16 已达标
- **目标**：找到能达标的**最小 INT16 节点集合**
- **方法**：对 INT8 校准模型运行敏感度分析，按阈值渐进回退

### 阶段 4：INT16 + Conv/Gemm/MatMul dual-int16

- **前提**：阶段 2 全 INT16 未达标
- **方法**：全 INT16 + Conv/Gemm/MatMul 算子 dual-int16
- **判定**：若达标进入阶段 5；否则进入阶段 6

### 阶段 5：INT16 + dual-int16 渐进混合回退

- **前提**：阶段 4 已达标
- **目标**：找到能达标的**最小 dual-int16 节点集合**

### 阶段 6：全 FP16

- **目的**：判断是否为 INT16 位宽问题
- **判定**：若达标进入阶段 7；否则建议联系地平线研发

### 阶段 7：INT16 + dual-int16 + FP16 渐进混合回退

- **前提**：阶段 6 全 FP16 已达标
- **目标**：找到能达标的**最小 FP16 节点集合**

## 渐进阈值扩展流程

阶段 3、5、7 共用此机制。默认阈值列表为 `[0.99, 0.999, 0.9999, 0.99999]`，可通过 `--progressive_thresholds` 参数自定义：

| 轮次 | 默认阈值 | 含义 |
|------|------|------|
| 1 | `<= 0.99` | 仅提升最敏感的节点 |
| 2 | `<= 0.999` | 扩大到中等敏感节点 |
| 3 | `<= 0.9999` | 扩大到较轻微敏感节点 |
| 4 | `<= 0.99999` | 扩大到几乎所有非完美节点 |

### 回退策略

- **阶段 3**：如果所有阈值仍未达标，直接采用阶段 2（全 INT16）结果，结束调优
- **阶段 5**：如果所有阈值仍未达标，直接采用阶段 4（INT16 + dual-int16）结果，结束调优
- **阶段 7**：如果所有阈值仍未达标，直接采用阶段 6（全 FP16）结果，结束调优

### 操作要点

- 节点敏感度分析只需运行一次
- 每轮的 `node_config` 是**累积的**
- 用户传入的 `node_config_path` 配置不会被改变

## quant_config 配置模板

> 默认不写入 `activation.calibration_type` / `activation.per_channel` /
> `activation.asymmetric` / `weight.bias_correction`，由 HMCT 选择默认策略；这些字段
> 仅在通过对应 CLI 参数（`--calibration_type` / `--per_channel` / `--asymmetric` /
> `--bias_correction`、`--bias_correction_num_sample`、`--bias_correction_metric`）
> 显式指定时才会出现。下方示例的注释行展示了字段位置。

### 阶段 3：INT8 基线 + 局部 INT16

```python
quant_config = {
    "model_config": {
        "all_node_type": "int8",
        # "activation": {                                                       # 仅在显式指定时出现
        #     "calibration_type": "max",
        #     "per_channel": [True, False],
        #     "asymmetric": [True, False],
        # },
        # "weight": {"bias_correction": {"num_sample": 4, "metric": "mse"}},   # 仅在 --bias_correction true 时出现
    },
    "node_config": {
        "SensitiveNode1": {"qtype": "int16"},
        "SensitiveNode2": {"qtype": "int16"}
    }
}
```

### 阶段 5：INT16 基线 + 局部 dual-int16

```python
quant_config = {
    "model_config": {
        "all_node_type": "int16",
        # "activation": {                                                       # 仅在显式指定时出现
        #     "calibration_type": "max",
        #     "per_channel": [True, False],
        #     "asymmetric": [True, False],
        # },
        # "weight": {"bias_correction": {"num_sample": 4, "metric": "mse"}},   # 仅在 --bias_correction true 时出现
    },
    "node_config": {
        "SensitiveConvNode1": {"input0": "int16", "input1": "int16"},
        "SensitiveGemmNode2": {"input0": "int16", "input1": "int16"}
    }
}
```

### 阶段 7：INT16 + dual-int16 基线 + 局部 FP16

```python
quant_config = {
    "model_config": {
        "all_node_type": "int16",
        # "activation": {                                                       # 仅在显式指定时出现
        #     "calibration_type": "max",
        #     "per_channel": [True, False],
        #     "asymmetric": [True, False],
        # },
        # "weight": {"bias_correction": {"num_sample": 4, "metric": "mse"}},   # 仅在 --bias_correction true 时出现
    },
    "op_config": {
        "Conv": {"qtype": "dual-int16"},
        "MatMul": {"qtype": "dual-int16"},
        "Gemm": {"qtype": "dual-int16"}
    },
    "node_config": {
        "SensitiveNode1": {"qtype": "float16"},
        "SensitiveNode2": {"qtype": "float16"}
    }
}
```

## 调优报告示例

脚本自动生成 `tuning_report.md`：

```markdown
# PTQ 精度调优报告

## 背景与目标
- 模型：model.onnx
- 校准数据：./cali_data
- BPU架构：nash-p
- 指标与阈值：Cosine Similarity（≥0.99）

## 调优过程与结果
| # | Phase | Configuration | Output Cosine Similarity | Threshold Met |
|---|-------|--------------|--------------------------|---------------|
| 1 | INT8_BASELINE | all_node_type=int8 | output1=0.9876 | NO |
| 2 | INT16_UPPER | all_node_type=int16 | output1=0.9950 | YES |
| 3 | INT8_INT16_MIXED | Progressive (int16) | output1=0.9910 | YES |

## Final quant_config
quant_config = {...}
```
