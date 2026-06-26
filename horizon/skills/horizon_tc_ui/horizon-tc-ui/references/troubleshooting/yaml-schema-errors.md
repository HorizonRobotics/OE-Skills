# YAML Schema 校验错误排错指南

本文档涵盖 hb_compile/hb_verifier 在 YAML 配置校验阶段（Schema 校验 + 参数校验）可能遇到的所有错误。

---

## 1. 模型文件相关错误

### `It is not supported to specify both onnx_model and caffe_model`

| 项目 | 内容 |
|------|------|
| **报错原文** | `It is not supported to specify both onnx_model and caffe_model, please specify it based on the actual` |
| **原因** | 同时指定了 `onnx_model` 和 `caffe_model`/`prototxt`，二者互斥 |
| **修法** | 只保留 `onnx_model` 或 `caffe_model` + `prototxt` 其中一组 |
| **源码定位** | `params_parser.py:168-171` |

### `The model file has not been correctly specified`

| 项目 | 内容 |
|------|------|
| **报错原文** | `The model file has not been correctly specified, please specify the caffe_model or the onnx_model in your yaml config file` |
| **原因** | `onnx_model`、`caffe_model`、`prototxt` 全部为空或未指定 |
| **修法** | 在 `model_parameters` 中指定有效的模型文件路径 |
| **源码定位** | `params_parser.py:172-176` |

### `The file invalid: {file_path}. It should be a '{suffix}' file`

| 项目 | 内容 |
|------|------|
| **报错原文** | `The file invalid: {file_path}. It should be a '{suffix}' file` |
| **原因** | 模型文件后缀不匹配（如 onnx_model 指向非 .onnx 文件） |
| **修法** | 确认文件路径和后缀正确：onnx 用 `.onnx`，caffe 用 `.caffemodel` + `.prototxt` |
| **源码定位** | `params_parser.py:1199-1201` (`file_check`) |

### `Can not find file specified: {file_path}`

| 项目 | 内容 |
|------|------|
| **报错原文** | `Can not find file specified: {file_path},please check the configuration` |
| **原因** | 指定的模型文件路径不存在 |
| **修法** | 检查文件路径是否正确，支持相对路径（相对于 YAML 所在目录）和绝对路径 |
| **源码定位** | `params_parser.py:1203-1205` (`file_check`) |

---

## 2. march 架构相关错误

### `The specified march '{march}' is invalid`

| 项目 | 内容 |
|------|------|
| **报错原文** | `The specified march '{march}' is invalid, the march parameter only supports values in {march_list}` |
| **原因** | `march` 值不在支持列表中。支持的 march 包括：`nash-b-lite`, `nash-b`, `nash-b-plus`, `nash-e`, `nash-m`, `nash-p`, `nash-h` |
| **修法** | 将 `march` 修改为支持的值，例如 `march: "nash-m"` |
| **源码定位** | `params_parser.py:201-204`；`mapper_consts.py:124-133` |

---

## 3. 必填字段 / 空值错误

### `The output_model_file_prefix cannot be empty`

| 项目 | 内容 |
|------|------|
| **报错原文** | `The output_model_file_prefix cannot be empty, please specify a valid prefix in your yaml config file` |
| **原因** | `output_model_file_prefix` 为空字符串 |
| **修法** | 指定非空的前缀，如 `output_model_file_prefix: "my_model"` |
| **源码定位** | `params_parser.py:218-221` |

### `Model has more than one input! It is necessary to explicitly specify all the input_name`

| 项目 | 内容 |
|------|------|
| **报错原文** | `Model has more than one input! It is necessary to explicitly specify all the input_name to ensure the sequence is correct.` |
| **原因** | 多输入模型未显式指定 `input_name` |
| **修法** | 在 `input_parameters` 中用分号分隔指定所有输入名称，如 `input_name: "input0;input1"` |
| **源码定位** | `params_parser.py:402-406` |

### `This model has non-featuremap inputs, please specify the input_layout_train`

| 项目 | 内容 |
|------|------|
| **报错原文** | `This model has non-featuremap inputs, please specify the input_layout_train` |
| **原因** | 模型包含非 featuremap 输入但未指定 `input_layout_train`（NHWC 或 NCHW） |
| **修法** | 添加 `input_layout_train: "NHWC"` 或 `input_layout_train: "NCHW"` |
| **源码定位** | `params_parser.py:627-630` |

---

## 4. 类型不匹配错误（Schema 校验阶段）

### `Invalid value for {name}: {v}`

| 项目 | 内容 |
|------|------|
| **报错原文** | `Invalid value for {name}: {v}` |
| **原因** | `max_l2m_size` 等字段传入了无法转换为 int 的字符串（非数字且非 'none'） |
| **修法** | 将值改为整数或 `none`/`None`，如 `max_l2m_size: 0` 或 `max_l2m_size: none` |
| **源码定位** | `schema_yaml.py:17` 和 `schema_yaml.py:23` (`use_none_or_int`) |

### Schema 校验通用类型错误

| 项目 | 内容 |
|------|------|
| **报错原文** | `SchemaError: Key 'xxx' error: ...`（schema 库抛出的通用类型错误） |
| **原因** | YAML 中字段类型与 schema 定义不一致。例如 `march` 需要 str 但传了 int；`log_level` 需要 int 但传了 str；`core_num` 需要 int 但传了 str |
| **修法** | 对照 `schema_yaml.py` 中的类型定义修正 YAML 值。关键字段类型如下：<br>- `march`: str<br>- `log_level`: int<br>- `core_num`: int<br>- `jobs`: int<br>- `max_time_per_fc`: int<br>- `advice`: float<br>- `balance_factor`: int<br>- `max_percentile`: float 或 null |
| **源码定位** | `schema_yaml.py:27-100` |

### `Wrong parameter '{name}' specified, bool value is required but get type {type}`

| 项目 | 内容 |
|------|------|
| **报错原文** | `Wrong parameter '{name}' specified, bool value is required but get type {type}` |
| **原因** | 布尔类型参数（如 `enable_vpu`, `enable_spu`, `layer_out_dump`, `separate_batch`, `per_channel`, `debug`, `preprocess_on`, `hbdk3_compatible_mode`）传入了非布尔值 |
| **修法** | 使用 `true`/`false`（YAML 原生布尔值），不要用 `"true"`/`"false"` 字符串或 `1`/`0` |
| **源码定位** | `params_parser.py:1231-1245` (`bool_type_check`) |

---

## 5. 互斥字段 / 冲突配置错误

### `Only one of scale_value and std_value can be specified`

| 项目 | 内容 |
|------|------|
| **报错原文** | `Only one of scale_value and std_value can be specified` |
| **原因** | 同时指定了 `scale_value` 和 `std_value`，二者互斥 |
| **修法** | 只保留其中一个。`scale_value` 用于 `data_scale` 归一化，`std_value` 用于 `data_std` 归一化 |
| **源码定位** | `params_parser.py:673-675` |

### `The separate_batch and separate_name can not both be specified`

| 项目 | 内容 |
|------|------|
| **报错原文** | `The separate_batch and separate_name can not both be specified` |
| **原因** | `separate_batch` 和 `separate_name` 互斥，不能同时配置 |
| **修法** | 根据需求选择其一：按 batch 拆分用 `separate_batch: true`；按名称拆分用 `separate_name: "input_name"` |
| **源码定位** | `params_parser.py:524-526` |

### `The input_type_train '{train_type}' ... is not supported to be transformed to input_type_rt '{rt_type}'`

| 项目 | 内容 |
|------|------|
| **报错原文** | `The input_type_train '{train_type}' of the input {idx} is not supported to be transformed to input_type_rt '{rt_type}' now` |
| **原因** | `input_type_train` 到 `input_type_rt` 的转换组合不在合法映射表中 |
| **修法** | 参考 `mapper_consts.py` 中的 `legal_trans_dict` 选择合法组合。例如 `rgb` -> `bgr`/`nv12`/`yuv444`/`yuv444_128`/`yuv420sp_bt601_video` |
| **源码定位** | `params_parser.py:649-654`；`mapper_consts.py:57-70` |

### `The specified input_space_and_range: {value} and input_type_rt {rt} combination is invalid`

| 项目 | 内容 |
|------|------|
| **报错原文** | `The specified input_space_and_range: {value} and input_type_rt {rt} combination is invalid` |
| **原因** | `bt601_video` 只能与 `nv12` 搭配，不能与其他 `input_type_rt` 组合 |
| **修法** | 将 `input_type_rt` 改为 `nv12`，或将 `input_space_and_range` 改为 `regular` |
| **源码定位** | `params_parser.py:562-569` |

---

## 6. 输入参数校验错误

### `Wrong num of input_name specified`

| 项目 | 内容 |
|------|------|
| **报错原文** | `Wrong num of input_name specified. Num of input_name specified: {n}, while model file has {m} inputs` |
| **原因** | `input_name` 数量与模型实际输入数量不一致 |
| **修法** | 确保 `input_name` 的分号分隔数量与模型输入数一致 |
| **源码定位** | `params_parser.py:414-418` |

### `Input names duplicated: '{names}'`

| 项目 | 内容 |
|------|------|
| **报错原文** | `Input names duplicated: '{names}'` |
| **原因** | `input_name` 中存在重复值 |
| **修法** | 移除重复的输入名称 |
| **源码定位** | `params_parser.py:419-420` |

### `The specified input_name {name} does not exist in model file`

| 项目 | 内容 |
|------|------|
| **报错原文** | `The specified input_name {name} does not exist in model file. The name list should be specified: {model_input_names}` |
| **原因** | 指定的 `input_name` 在模型中不存在 |
| **修法** | 使用模型实际的输入名称，可通过 ONNX 工具查看 |
| **源码定位** | `params_parser.py:422-427` |

### `Num of input_shape specified: {n}, while model file has {m} inputs`

| 项目 | 内容 |
|------|------|
| **报错原文** | `Num of input_shape specified: {n}, while model file has {m} inputs` |
| **原因** | `input_shape` 数量与模型输入数量不匹配 |
| **修法** | 确保每个输入都有对应的 shape，用分号分隔多个 shape |
| **源码定位** | `params_parser.py:442-446` |

### `The input_shape parse failed. Input index {idx}: {item}`

| 项目 | 内容 |
|------|------|
| **报错原文** | `The input_shape parse failed. Input index {idx}: {item}` |
| **原因** | `input_shape` 格式解析失败，应为 `1x3x224x224` 格式（小写 x 分隔） |
| **修法** | 使用正确的格式，如 `input_shape: "1x3x224x224"` 或多个 `input_shape: "1x3x224x224;1x1x100"` |
| **源码定位** | `params_parser.py:456-459` |

### `The model is a dynamically input model. Please specify the 'input_shape' parameter`

| 项目 | 内容 |
|------|------|
| **报错原文** | `The model is a dynamically input model. Please specify the 'input_shape' parameter in the 'input_parameters'` |
| **原因** | 模型包含动态维度（值为 0）且未指定 `input_shape` |
| **修法** | 在 `input_parameters` 中明确指定固定的 `input_shape` |
| **源码定位** | `params_parser.py:463-468` |

### `The first dimension of input_shape must be 1, got {n}`

| 项目 | 内容 |
|------|------|
| **报错原文** | `The first dimension of input_shape must be 1, got {n}` |
| **原因** | 使用 `input_batch` 时，`input_shape` 的第一维必须为 1 |
| **修法** | 将 `input_shape` 的第一维改为 1，如 `1x3x224x224` |
| **源码定位** | `params_parser.py:500-503` |

### `The input_batch parameter can only be specified as a single value`

| 项目 | 内容 |
|------|------|
| **报错原文** | `The input_batch parameter can only be specified as a single value. But {n} values have been specified` |
| **原因** | `input_batch` 只能指定一个值，不能分号分隔多个 |
| **修法** | 只指定单个值，如 `input_batch: "4"` |
| **源码定位** | `params_parser.py:494-498` |

### `Wrong {name} num received`

| 项目 | 内容 |
|------|------|
| **报错原文** | `Wrong {name} num received. Num of {name} given: {n} is not equal to input num {m}` |
| **原因** | 参数数量（如 `input_type_rt`, `input_type_train`, `norm_type`, `mean_value` 等）与模型输入数量不一致 |
| **修法** | 确保每个输入都有对应的参数值，用分号分隔 |
| **源码定位** | `params_parser.py:902-908` (`_validate_num`) |

### `The specified {name} is invalid, the {name}: '{value}' can only be specified as values in {expect}`

| 项目 | 内容 |
|------|------|
| **报错原文** | `The specified {name} is invalid, the {name}: '{value}' can only be specified as values in {expect}` |
| **原因** | 枚举类型参数值不在允许范围内 |
| **修法** | 参考以下合法值列表：<br>- `input_type_rt`: `nv12`, `yuv444`, `yuv444_128`, `featuremap`, `rgb`, `bgr`, `gray`, `yuv_bt601_full`, `yuv_bt601_video`<br>- `input_type_train`: `rgb`, `bgr`, `featuremap`, `gray`, `yuv444`, `yuv444_128`, `yuv_bt601_full`, `yuv_bt601_video`<br>- `input_layout_train`: `NHWC`, `NCHW`<br>- `input_space_and_range`: `regular`, `bt601_video` |
| **源码定位** | `params_parser.py:1208-1215` (`mconsts_check`)；`mapper_consts.py:13-46, 94-116, 161` |

### `The specified input_type_rt is {rt}, but the input_shape is not four-dimensional`

| 项目 | 内容 |
|------|------|
| **报错原文** | `The specified input_type_rt is {rt}, but the input_shape is not four-dimensional, please set the input_type_rt and input_type_train to featuremap` |
| **原因** | 非 featuremap 类型的输入必须是四维 shape，否则需设置为 `featuremap` |
| **修法** | 如果是 featuremap 输入，将 `input_type_rt` 和 `input_type_train` 都设为 `featuremap`；否则确保 `input_shape` 为四维 |
| **源码定位** | `params_parser.py:572-579` |

### `The input shape: {shape} is invalid, nv12 type does not support odd number input size`

| 项目 | 内容 |
|------|------|
| **报错原文** | `The input shape: {shape} is invalid, nv12 type does not support odd number input size` |
| **原因** | `nv12` 类型的输入的 H 和 W 维度不能为奇数 |
| **修法** | 将 H 和 W 调整为偶数 |
| **源码定位** | `params_parser.py:756-769` (`_validate_odd_shape`) |

---

## 7. 编译参数校验错误

### `The specified optimize_level '{level}' is invalid`

| 项目 | 内容 |
|------|------|
| **报错原文** | `The specified optimize_level '{level}' is invalid, it can only be specified as values in ['O0', 'O1', 'O2']` |
| **原因** | hbdk4 仅支持 `O0`, `O1`, `O2`，不支持 `O3` |
| **修法** | 将 `optimize_level` 改为 `O0`, `O1` 或 `O2` |
| **源码定位** | `params_parser.py:911-916`；`mapper_consts.py:159` |

### `Wrong core_num {n} specified`

| 项目 | 内容 |
|------|------|
| **报错原文** | `Wrong core_num {n} specified, it can only be specified as values in range {range}` 或 `Wrong core_num {n} specified, it must be a positive integer` |
| **原因** | `core_num` 超出对应 march 的支持范围。例如 `nash-b-lite/b/b-plus/e/m` 仅支持 `[1]`，`nash-h/p` 支持 `[1, 2, 3, 4]` |
| **修法** | 根据 march 选择合适的 core_num |
| **源码定位** | `params_parser.py:976-992`；`mapper_consts.py:174-182` |

### `The specified compile_mode {mode} is invalid`

| 项目 | 内容 |
|------|------|
| **报错原文** | `The specified compile_mode {mode} is invalid, it can only be specified as values in ['bandwidth', 'latency', 'balance']` |
| **原因** | `compile_mode` 值不在允许范围内 |
| **修法** | 使用 `bandwidth`, `latency` 或 `balance` |
| **源码定位** | `params_parser.py:1012-1017`；`mapper_consts.py:187` |

### `Parameter compile_mode is set to balance, please set balance_factor to use this mode`

| 项目 | 内容 |
|------|------|
| **报错原文** | `Parameter compile_mode is set to balance, please set balance_factor to use this mode` |
| **原因** | `compile_mode: balance` 时必须指定 `balance_factor` |
| **修法** | 添加 `balance_factor: 50`（范围 0-100） |
| **源码定位** | `params_parser.py:1037-1039` |

### `The specified balance_factor {n} is invalid, it can only be specified as values in range 0-100`

| 项目 | 内容 |
|------|------|
| **报错原文** | `The specified balance_factor {n} is invalid, it can only be specified as values in range 0-100` |
| **原因** | `balance_factor` 超出 0-100 范围 |
| **修法** | 将 `balance_factor` 设为 0-100 之间的整数 |
| **源码定位** | `params_parser.py:1040-1043` |

### `The specified max_time_per_fc is invalid`

| 项目 | 内容 |
|------|------|
| **报错原文** | `The specified max_time_per_fc is invalid, it can only be specified as 0 or range 1000-10000000` |
| **原因** | `max_time_per_fc` 不在合法范围内（0 或 1000-10000000） |
| **修法** | 设为 `0`（禁用）或 `1000` 到 `10000000` 之间的值 |
| **源码定位** | `params_parser.py:1046-1052` |

### `The specified cache_path {path} does not exist`

| 项目 | 内容 |
|------|------|
| **报错原文** | `The specified cache_path {path} does not exist, please create it before compilation` |
| **原因** | 指定的缓存目录不存在 |
| **修法** | 提前创建该目录 |
| **源码定位** | `params_parser.py:268-272` |

### `The specified cache_mode {mode} is invalid`

| 项目 | 内容 |
|------|------|
| **报错原文** | `The specified cache_mode {mode} is invalid, it can only be specified as values in ['enable', 'force_overwrite', 'disable']` |
| **原因** | `cache_mode` 值不合法 |
| **修法** | 使用 `enable`, `force_overwrite` 或 `disable` |
| **源码定位** | `params_parser.py:276-281`；`mapper_consts.py:237` |

### `The cache_path must be specified when the cache_mode is not disable`

| 项目 | 内容 |
|------|------|
| **报错原文** | `The cache_path must be specified when the cache_mode is not disable` |
| **原因** | 启用了缓存但未指定 `cache_path` |
| **修法** | 添加 `cache_path: "/path/to/cache"` |
| **源码定位** | `params_parser.py:282-285` |

### `The specified max_l2m_size {n} is invalid`

| 项目 | 内容 |
|------|------|
| **报错原文** | `The specified max_l2m_size {n} is invalid, it can only be specified as values in range 0-25165824` |
| **原因** | `max_l2m_size` 超出 0-24MB 范围 |
| **修法** | 设为 0（禁用）或不超过 25165824（24MB）的值 |
| **源码定位** | `params_parser.py:994-1004` |

### `The specified march {march} does not support setting max_l2m_size`

| 项目 | 内容 |
|------|------|
| **报错原文** | `The specified march {march} does not support setting max_l2m_size` |
| **原因** | `nash-b*`, `nash-e`, `nash-m` 系列不支持 `max_l2m_size` |
| **修法** | 移除 `max_l2m_size` 配置或改用支持该参数的 march（如 nash-h/nash-p） |
| **源码定位** | `params_parser.py:1005-1008` |

---

## 8. 节点操作相关错误

### `Unsupport removing {types} now`

| 项目 | 内容 |
|------|------|
| **报错原文** | `Unsupport removing {types} now` |
| **原因** | `remove_node_type` 指定了不支持的节点类型。仅支持：`Quantize`, `Transpose`, `Dequantize`, `Cast`, `Reshape`, `Softmax` |
| **修法** | 仅使用上述支持的节点类型 |
| **源码定位** | `params_parser.py:235-241`；`mapper_consts.py:163-165` |

### `The format you gave is {value}, currently we only support the following format: Conv_0:int16;Conv_1:int16`

| 项目 | 内容 |
|------|------|
| **报错原文** | `The format you gave is {value}, currently we only support the following format: Conv_0:int16;Conv_1:int16` |
| **原因** | `node_info` 字符串格式不正确 |
| **修法** | 使用 `节点名:数据类型` 格式，多个节点用分号分隔 |
| **源码定位** | `params_parser.py:313-315` |

### `The value you gave is {key}, currently we only support specifying it as ON, OutputType and InputType\d+`

| 项目 | 内容 |
|------|------|
| **报错原文** | `The value you gave is {key},currently we only support specifying it as ON, OutputType and InputType\d+` |
| **原因** | `node_info` 字典中使用了不支持的 key |
| **修法** | 只使用 `ON`, `OutputType`, `InputType0`, `InputType1` 等合法 key |
| **源码定位** | `params_parser.py:332-337` |

---

## 9. input_source 相关错误

### `The specified input_source {item} is invalid`

| 项目 | 内容 |
|------|------|
| **报错原文** | `The specified input_source {item} is invalid. It can only be specified as values in ['pyramid', 'ddr', 'resizer']` |
| **原因** | `input_source` 值不在允许范围内 |
| **修法** | 使用 `pyramid`, `ddr` 或 `resizer` |
| **源码定位** | `params_parser.py:946-950`；`mapper_consts.py:172` |

### `Wrong input_source specified. The input_type_rt {rt} does not support input_source {source}`

| 项目 | 内容 |
|------|------|
| **报错原文** | `Wrong input_source specified. The input_type_rt {rt} does not support input_source {source}` |
| **原因** | `input_type_rt` 与 `input_source` 组合不支持。支持关系如下：<br>- `pyramid`: `nv12`, `gray`, `yuv420sp_bt601_video`, `yuv_bt601_full`<br>- `ddr`: `rgb`, `bgr`, `yuv444`, `yuv444_128`, `gray`, `featuremap`<br>- `resizer`: `nv12`, `gray`, `yuv420sp_bt601_video`, `yuv_bt601_full` |
| **修法** | 根据 `input_type_rt` 选择兼容的 `input_source` |
| **源码定位** | `params_parser.py:953-957`；`mapper_consts.py:138-142` |

---

## 10. 已废弃参数警告

### `Please note that the parameter '{name}' has been deprecated`

| 项目 | 内容 |
|------|------|
| **报错原文** | `Please note that the parameter '{name}' has been deprecated. Specifying this parameter will have no effect` |
| **原因** | 使用了已废弃的参数：`set_node_data_type`, `input_layout_rt`, `preprocess_on`, `hbdk3_compatible_mode` |
| **修法** | 移除这些参数，它们不会产生任何效果 |
| **源码定位** | `params_parser.py:296-298, 590-592, 1093-1100` |

### `Please note that the parameter norm_type has been deprecated`

| 项目 | 内容 |
|------|------|
| **报错原文** | `Please note that the parameter norm_type has been deprecated and will be determined by the specification of the mean/scale/std parameters` |
| **原因** | `norm_type` 已废弃，现在由 `mean_value`/`scale_value`/`std_value` 自动推断 |
| **修法** | 移除 `norm_type`，直接配置 `mean_value`, `scale_value` 或 `std_value` |
| **源码定位** | `params_parser.py:664-666` |
