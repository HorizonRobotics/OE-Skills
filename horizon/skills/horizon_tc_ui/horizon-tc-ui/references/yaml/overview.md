# YAML 配置参考文档 — 概览

## 权威 Schema 来源

YAML 配置的权威 schema 定义位于 `horizon_tc_ui/config/schema_yaml.py`。
所有参数的类型、默认值、是否必填均由该文件通过 `schema` 库声明。
校验逻辑由 `horizon_tc_ui/config/params_parser.py` 中的 `ParamsParser` 类实现，
最终解析结果存储在 `horizon_tc_ui/config/config_info.py` 的 `ConfigInfo` 数据结构中。

## 配置加载流程

```
YAML 文件
  │
  ├─ 1. yaml.safe_load() 加载文件内容
  │
  ├─ 2. dict_add_key() 补齐缺失的 section（input_parameters / calibration_parameters / compiler_parameters / custom_op）
  │
  ├─ 3. Schema(schema_yaml).validate() 按 schema 校验类型与默认值
  │
  ├─ 4. ParamsParser.validate_parameters() 逐项业务逻辑校验
  │     ├─ _validate_model_parameters()
  │     ├─ _validate_input_parameters()
  │     ├─ _validate_calibration_parameters()
  │     ├─ _validate_compiler_parameters()
  │     ├─ _validate_custom_op_parameters()
  │     └─ _validate_deprecated_params()
  │
  └─ 5. 生成 ConfigInfo 对象（conf），供后续编译流程使用
```

## 四大 Section 职责

| Section | 职责 | 典型参数 |
|---------|------|---------|
| `model_parameters` | 描述模型来源、目标架构、输出路径等编译全局信息 | `onnx_model`, `caffe_model`, `march`, `working_dir` |
| `input_parameters` | 描述模型输入的数据格式、形状、预处理方式 | `input_type_rt`, `input_shape`, `mean_value`, `scale_value` |
| `calibration_parameters` | 描述量化校准策略、校准数据路径、量化配置 | `cal_data_dir`, `calibration_type`, `per_channel`, `quant_config` |
| `compiler_parameters` | 描述编译器行为、优化策略、硬件资源配置 | `compile_mode`, `optimize_level`, `core_num`, `jobs` |

此外还有一个可选 section `custom_op`，用于注册自定义算子。

## 模板文件

系统内置 4 个模板文件，位于 `horizon_tc_ui/template/` 目录：

| 模板文件 | 用途 |
|---------|------|
| `full_template.yaml` | 完整参数模板，包含所有常用参数 |
| `simple_template.yaml` | 最简模板，仅包含必填项 |
| `fast_perf_template.yaml` | 快速性能测试模板（`optimization: run_fast`） |
| `check_template.yaml` | 模型检查模板（featuremap 输入，O0 优化） |
