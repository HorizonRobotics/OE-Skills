# YAML 参数参考 — calibration_parameters

> 源码依据：`horizon_tc_ui/config/schema_yaml.py`（schema 定义）
> 校验逻辑：`horizon_tc_ui/config/params_parser.py` → `_validate_calibration_parameters()`
> 常量定义：`horizon_tc_ui/config/mapper_consts.py`

## 完整参数表

| 参数 | 类型 | 默认值 | 必填 | 可选范围 | 说明 |
|------|------|--------|------|----------|------|
| `cal_data_dir` | str | `None` | 条件必填 | 目录路径，多个用分号分隔 | 校准数据目录。当 `calibration_type` 不是 `skip` 时必填，数量须与模型输入数匹配 |
| `calibration_type` | str | `""` | 否 | `kl`, `max`, `mix`, `skip` | 量化校准策略。未指定且无校准数据时自动设为 `skip` |
| `per_channel` | bool/str/int | `false` | 否 | bool | 是否按通道（per-channel）量化。默认 per-tensor |
| `max_percentile` | float/None | `None` | 否 | 0.0 ~ 1.0 | max 校准时的百分位截断值 |
| `run_on_cpu` | str | `None` | 否 | 分号分隔的节点名 | 强制指定节点在 CPU 上运行 |
| `run_on_bpu` | str | `None` | 否 | 分号分隔的节点名 | 强制指定节点在 BPU 上运行 |
| `optimization` | str | `None` | 否 | `set_model_output_int8`, `set_model_output_int16` | 校准优化选项。详见下方 `calibration_optimization` 章节 |
| `quant_config` | str/dict/None | `None` | 否 | 字典或路径 | 量化配置文件路径或字典，用于精细控制量化行为 |
| `preprocess_on` | bool/str/int | 无 | 否 | - | **已废弃**，指定此参数无效 |
| `cal_data_type` | str | `None` | 否 | - | **已废弃**。请切换校准数据集为 npy 格式 |

## calibration_type 详解

源码位置：`mapper_consts.py` → `autoq_caltype_list` / `preq_caltype_list`

| 值 | 说明 | 是否需要 cal_data_dir |
|----|------|----------------------|
| `kl` | KL 散度校准（推荐，精度通常更好） | 是 |
| `max` | 最大值校准（速度更快） | 是 |
| `mix` | **已废弃**，混合校准 | 是 |
| `skip` | 跳过校准（使用预训练量化参数或直接跳过） | 否 |

## 条件必填规则

1. 当 `calibration_type` 为 `skip` 时，`cal_data_dir` 可不填
2. 当 `calibration_type` 为 `kl`/`max` 时，`cal_data_dir` **必填**
3. 当 `cal_data_dir` 未指定时，系统自动将 `calibration_type` 设为 `skip`
4. `cal_data_dir` 的数量必须等于模型输入数量，或为 0（全部不指定）

源码：`params_parser.py` → `_validate_cal_data_dir()` L793-L818

## run_on_cpu / run_on_bpu 与 node_info 的优先级

当同时指定 `node_info`（model_parameters）和 `run_on_cpu`/`run_on_bpu` 时，
`node_info` 的配置具有最高优先级。

源码：`params_parser.py` → `_validate_node_info()` L368-L384

## calibration_optimization 选项

源码位置：`mapper_consts.py` → `cali_optimization_list`

| 值 | 说明 |
|----|------|
| `set_model_output_int8` | 将模型输出量化为 int8 |
| `set_model_output_int16` | 将模型输出量化为 int16 |

**特殊路径：`run_fast`**

`run_fast` 不属于 `cali_optimization_list` 中的标准选项，而是在 `params_parser.py` 中作为特殊路径硬编码处理。当 `optimization` 设为 `run_fast` 时：
- 跳过 `_validate_input_name` 和 `_validate_input_shape` 的部分校验（`params_parser.py` L394, L432）
- 用于 fast-perf 模式快速性能测试，跳过校准流程
- 由 `hb_compile --fast-perf` 自动生成，通常不需要手动配置

## 已废弃参数

| 参数 | 废弃原因 | 替代方案 |
|------|---------|---------|
| `preprocess_on` | 预处理逻辑已变更 | 无需替代，参数无效 |
| `cal_data_type` | 统一使用 npy 格式 | 将校准数据转换为 npy 格式 |

源码：`params_parser.py` → `_validate_deprecated_params()` L1075-L1100
以及 `_validate_cal_data_type()` L820-L859

## 典型错误

| 错误片段 | 原因 | 修法 |
|---------|------|------|
| `The specified calibration_type 'Xxx' is invalid` | calibration_type 不在合法列表中 | 使用 `kl`/`max`/`skip` |
| `Wrong cal_data_dir num received` | cal_data_dir 数量与输入数不匹配 | 确保数量等于模型输入数 |
| `The specified cal_data_dir Xxx does not exist` | 校准数据目录不存在 | 创建目录或修正路径 |
| `The specified max_percentile Xxx is invalid, avaliable range: 0~1` | max_percentile 超出范围 | 设置为 0.0~1.0 之间的值 |
