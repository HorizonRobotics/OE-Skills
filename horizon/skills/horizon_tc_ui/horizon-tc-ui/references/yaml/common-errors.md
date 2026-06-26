# YAML 配置常见错误速查

> 来源：`horizon_tc_ui/config/params_parser.py` 中所有 `_validate_*` 函数
> 按报错文本倒排索引，覆盖所有校验错误

## 模型文件相关

### `It is not supported to specify both onnx_model and caffe_model`
- **原因**：同时指定了 ONNX 和 Caffe 模型文件，两种格式互斥
- **修法**：只保留一种模型格式。使用 `onnx_model` 或 `caffe_model`+`prototxt`
- **源码**：`_validate_model_file()` L168-L171

### `The model file has not been correctly specified`
- **原因**：未指定任何模型文件（onnx_model、caffe_model、prototxt 全为空）
- **修法**：指定 `onnx_model` 或 `caffe_model`+`prototxt`
- **源码**：`_validate_model_file()` L172-L176

### `The file invalid: Xxx. It should be a '.onnx' file`（或 `.caffemodel`/`.prototxt`）
- **原因**：模型文件后缀不匹配
- **修法**：确保文件路径后缀与预期格式一致
- **源码**：`file_check()` L1199-L1201

### `Can not find file specified: Xxx`
- **原因**：模型文件路径不存在
- **修法**：检查文件路径是否正确
- **源码**：`file_check()` L1203-L1205

## march 相关

### `The specified march 'Xxx' is invalid, the march parameter only supports values in [...]`
- **原因**：march 值不在合法列表中
- **修法**：使用合法值：`nash-b-lite`, `nash-b`, `nash-b-plus`, `nash-e`, `nash-m`, `nash-h`, `nash-p`
- **源码**：`_validate_march()` L198-L205

## output_model_file_prefix 相关

### `The output_model_file_prefix cannot be empty`
- **原因**：output_model_file_prefix 为空字符串
- **修法**：指定非空前缀，如 `model`
- **源码**：`_validate_output_model_file_prefix()` L217-L221

## remove_node_type 相关

### `Unsupport removing Xxx now`
- **原因**：remove_node_type 包含不支持的节点类型
- **修法**：仅使用 `Quantize`, `Transpose`, `Dequantize`, `Cast`, `Reshape`, `Softmax`
- **源码**：`_validate_remove_node_type()` L232-L242

## node_info 相关

### `currently we only support the following format: Conv_0:int16;Conv_1:int16`
- **原因**：node_info 字符串格式不正确
- **修法**：使用 `节点名:数据类型` 格式，多个节点用分号分隔
- **源码**：`__get_node_dict_by_str()` L312-L315

### `currently we only support the following format: {Conv_0:{'InputType0':'int16','OutputType':'int16'}}`
- **原因**：node_info 字典格式不正确
- **修法**：确保每个节点的值是一个字典
- **源码**：`__get_node_dict_by_dict()` L323-L329

### `currently we only support specifying it as ON, OutputType and InputType\d+`
- **原因**：node_info 字典中使用了不支持的键
- **修法**：仅使用 `ON`, `OutputType`, `InputType`, `InputType0`, `InputType1` 等键
- **源码**：`__get_node_dict_by_dict()` L331-L337

### `Currently we only support values in: ['BPU', 'CPU']`
- **原因**：node_info 中 ON 的值不是 BPU 或 CPU
- **修法**：使用 `BPU` 或 `CPU`
- **源码**：`__get_node_dict_by_dict()` L339-L341

## enable_vpu / enable_spu 相关

### `Wrong parameter 'enable_vpu' specified, bool value is required`
- **原因**：enable_vpu 不是 bool 类型
- **修法**：使用 `true` 或 `false`（YAML 布尔值）
- **源码**：`_validate_enable_vpu()` + `bool_type_check()` L1231-L1245

### `Wrong parameter 'enable_spu' specified, bool value is required`
- **原因**：enable_spu 不是 bool 类型
- **修法**：使用 `true` 或 `false`
- **源码**：`_validate_enable_spu()` + `bool_type_check()`

## cache 相关

### `The specified cache_path Xxx does not exist`
- **原因**：cache_path 目录不存在
- **修法**：创建目录后再运行
- **源码**：`_validate_cache_path()` L268-L272

### `The specified cache_mode Xxx is invalid, it can only be specified as values in ['enable', 'force_overwrite', 'disable']`
- **原因**：cache_mode 值不在合法列表中
- **修法**：使用 `enable`, `force_overwrite` 或 `disable`
- **源码**：`_validate_cache_mode()` L276-L281

### `The cache_path must be specified when the cache_mode is not disable`
- **原因**：cache_mode 为 enable 或 force_overwrite 但未指定 cache_path
- **修法**：同时指定 cache_path
- **源码**：`_validate_cache_mode()` L282-L285

## input_name 相关

### `Model has more than one input! It is necessary to explicitly specify all the input_name`
- **原因**：多输入模型未显式指定 input_name
- **修法**：在 input_parameters 中列出所有输入名称，用分号分隔
- **源码**：`_validate_input_name()` L402-L406

### `Wrong num of input_name specified. Num of input_name specified: X, while model file has Y inputs`
- **原因**：input_name 数量与模型实际输入数量不匹配
- **修法**：确保数量一致
- **源码**：`_validate_input_name()` L414-L418

### `Input names duplicated: 'Xxx'`
- **原因**：input_name 中有重复项
- **修法**：去除重复的输入名称
- **源码**：`_validate_input_name()` L419-L420

### `The specified input_name Xxx does not exist in model file. The name list should be specified: [...]`
- **原因**：指定的 input_name 在模型中不存在
- **修法**：使用模型实际的输入名称
- **源码**：`_validate_input_name()` L422-L427

## input_shape 相关

### `Num of input_shape specified: X, while model file has Y inputs`
- **原因**：input_shape 数量与模型输入数量不匹配
- **修法**：确保每个输入都有一个对应的 shape
- **源码**：`_validate_input_shape()` L442-L446

### `The input_shape parse failed. Input index X: Xxx`
- **原因**：input_shape 格式不正确，无法解析
- **修法**：使用 `1x3x224x224` 格式（小写 x 分隔维度），多个输入用分号分隔
- **源码**：`_validate_input_shape()` L456-L459

### `The model is a dynamically input model. Please specify the 'input_shape' parameter`
- **原因**：模型包含动态维度（值为 0）但未指定 input_shape
- **修法**：显式指定完整的 input_shape
- **源码**：`_validate_input_shape()` L463-L468

## input_batch 相关

### `The input_batch parameter can only be specified as a single value. But X values have been specified`
- **原因**：input_batch 指定了多个值
- **修法**：只指定一个整数值
- **源码**：`_validate_input_batch()` L494-L498

### `The first dimension of input_shape must be 1, got X`
- **原因**：使用 input_batch 时 input_shape 第一维不是 1
- **修法**：将 input_shape 第一维设为 1
- **源码**：`_validate_input_batch()` L500-L503

## separate_batch / separate_name 相关

### `The separate_batch and separate_name can not both be specified`
- **原因**：同时指定了 separate_batch 和 separate_name（互斥）
- **修法**：只使用其中一个
- **源码**：`_validata_separate_name()` L524-L526

### `The specified separate_name Xxx is not in the input_names`
- **原因**：separate_name 指定的名称不在 input_names 中
- **修法**：使用已定义的 input_name
- **源码**：`_validata_separate_name()` L529-L532

## input_type 相关

### `Wrong input_type_rt num received. Num of input_type_rt given: X is not equal to input num Y`
- **原因**：input_type_rt 数量与模型输入数不匹配
- **修法**：确保数量一致
- **源码**：`_validate_input_type()` + `_validate_num()` L902-L908

### `The specified input_type_rt is invalid, the input_type_rt: 'Xxx' can only be specified as values in [...]`
- **原因**：input_type_rt 值不在合法列表中
- **修法**：使用 `nv12`, `yuv444`, `rgb`, `bgr`, `gray`, `featuremap` 等
- **源码**：`_validate_input_type()` + `mconsts_check()` L1208-L1215

### `The specified input_type_train is invalid, the input_type_train: 'Xxx' can only be specified as values in [...]`
- **原因**：input_type_train 值不在合法列表中
- **修法**：使用 `rgb`, `bgr`, `featuremap`, `gray`, `yuv444` 等
- **源码**：`_validate_input_type()` + `mconsts_check()`

### `The specified input_type_rt is Xxx, but the input_shape is not four-dimensional, please set the input_type_rt and input_type_train to featuremap`
- **原因**：非 featuremap 类型但 input_shape 不是 4 维
- **修法**：将 input_type_rt 和 input_type_train 设为 `featuremap`，或修正 shape 为 4 维
- **源码**：`_validate_input_type()` L572-L579

## input_layout 相关

### `This model has non-featuremap inputs, please specify the input_layout_train`
- **原因**：存在非 featuremap 输入但未指定 input_layout_train
- **修法**：设置 `input_layout_train: NCHW` 或 `NHWC`
- **源码**：`_validate_input_layout()` L627-L630

### `The specified input_type_train is gray, but the channel dim of input_shape [...] is not 1`
- **原因**：gray 类型的通道维度不是 1
- **修法**：确保 gray 输入的通道维为 1
- **源码**：`_validate_input_layout()` L612-L617

### `The specified input_layout_train is: Xxx, but the channel dim of input_shape [...] is not 3`
- **原因**：非 gray 类型的通道维度不是 3
- **修法**：确保 RGB/BGR 等输入的通道维为 3
- **源码**：`_validate_input_layout()` L618-L624

## input_type 关联校验

### `Input X has input_type_rt Xxx with input_layout_train NCHW is not supported on bernoulli2 for now`
- **原因**：yuv444/yuv444_128 + NCHW 在 bernoulli2 上不支持
- **修法**：改用 NHWC 布局或其他 input_type
- **源码**：`_validate_input_type_association()` L639-L645

### `The input_type_train 'Xxx' of the input X is not supported to be transformed to input_type_rt 'Yyy' now`
- **原因**：train → rt 类型转换不合法
- **修法**：参考 input_parameters.md 中的 train→rt 合法转换表
- **源码**：`_validate_input_type_association()` L649-L654

## input_space_and_range 相关

### `The specified input_space_and_range: Xxx and input_type_rt Yyy combination is invalid`
- **原因**：`bt601_video` 只能与 `nv12` 配合使用
- **修法**：将 input_type_rt 改为 `nv12`，或将 input_space_and_range 改为 `regular`
- **源码**：`_validate_input_type()` L562-L569

## NV12 奇数维度

### `The input shape: [...] is invalid, nv12 type does not support odd number input size`
- **原因**：NV12 输入的 H 或 W 维度为奇数
- **修法**：将 H/W 调整为偶数
- **源码**：`_validate_odd_shape()` L767-L769

## mean/scale/std 相关

### `Only one of scale_value and std_value can be specified`
- **原因**：同时指定了 scale_value 和 std_value（互斥）
- **修法**：只保留一个
- **源码**：`_validate_norm_type()` L673-L675

### `Wrong format of mean_value Xxx specified, please refer to user manual`
- **原因**：mean_value 格式不正确
- **修法**：使用逗号分隔的浮点数，多个输入用分号分隔，如 `123.675,116.28,103.53`
- **源码**：`_validate_mean_value()` L714-L717

### `Wrong format of scale_value Xxx specified, please refer to user manual`
- **原因**：scale_value 格式不正确
- **修法**：使用逗号分隔的浮点数
- **源码**：`_validate_scale_value()` L732-L735

### `Wrong format of std_value Xxx specified, please refer to user manual`
- **原因**：std_value 格式不正确
- **修法**：使用逗号分隔的浮点数
- **源码**：`_validate_std_value()` L748-L751

### `The input_type_rt X is featuremap, configuration of mean/scale/std is not supported`
- **原因**：featuremap 输入不支持 mean/scale/std 预处理
- **修法**：移除 featuremap 输入的 mean/scale/std 配置
- **源码**：`_validate_norm_type()` L693-L697

## calibration_type 相关

### `The specified calibration_type 'Xxx' is invalid, it can only be specified as values in [...]`
- **原因**：calibration_type 不在合法列表中
- **修法**：使用 `kl`, `max`, `mix`, `skip`
- **源码**：`_validate_calibration_type()` L779-L783

## cal_data_dir 相关

### `Wrong cal_data_dir num received.`
- **原因**：cal_data_dir 数量既不等于输入数也不为 0
- **修法**：确保数量等于模型输入数，或全部不指定
- **源码**：`_validate_cal_data_dir()` L803-L804

### `The specified cal_data_dir Xxx does not exist`
- **原因**：校准数据目录不存在
- **修法**：创建目录或修正路径
- **源码**：`_validate_cal_data_dir()` L814-L817

## max_percentile 相关

### `The specified max_percentile Xxx is invalid, avaliable range: 0~1`
- **原因**：max_percentile 超出 0~1 范围
- **修法**：设置为 0.0~1.0 之间的浮点数
- **源码**：`_validate_max_percentile()` L873-L876

## cal_data_type 相关

### `The specified cal_data_type 'Xxx' is invalid, it can only be specified as values in ['uint8', 'float32']`
- **原因**：cal_data_type 值不合法（此参数已废弃）
- **修法**：切换校准数据集为 npy 格式，移除此参数
- **源码**：`_validate_cal_data_type()` L838-L843

## optimize_level 相关

### `The specified optimize_level 'Xxx' is invalid, it can only be specified as values in ['O0', 'O1', 'O2']`
- **原因**：optimize_level 不在 HBDK4 支持列表中
- **修法**：使用 `O0`, `O1`, `O2`（不支持 O3）
- **源码**：`_validate_optimize_level()` L911-L916

## input_source 相关

### `The specified input_source format is invalid, the input_source should be a dict`
- **原因**：input_source 不是字典格式
- **修法**：使用字典格式按输入名称指定
- **源码**：`_validate_input_source()` L922-L924

### `The specified input_source Xxx is invalid. It can only be specified as values in ['pyramid', 'ddr', 'resizer']`
- **原因**：input_source 值不在合法列表中
- **修法**：使用 `pyramid`, `ddr` 或 `resizer`
- **源码**：`_validate_input_source()` L946-L950

### `Wrong input_source specified. The input_type_rt Xxx does not support input_source Yyy`
- **原因**：input_source 与 input_type_rt 不兼容
- **修法**：参考 compiler_parameters.md 中的兼容性表
- **源码**：`_validate_input_source()` L953-L957

## core_num 相关

### `Wrong core_num X specified, it can only be specified as values in range [...]`
- **原因**：core_num 与当前 march 不兼容
- **修法**：参考 compiler_parameters.md 中 core_num 与 march 的关系表
- **源码**：`_validate_core_num()` L978-L984

### `Wrong core_num X specified, it must be a positive integer`
- **原因**：core_num 不是正整数
- **修法**：使用正整数
- **源码**：`_validate_core_num()` L987-L991

## compile_mode / balance_factor 相关

### `The specified compile_mode Xxx is invalid, it can only be specified as values in ['bandwidth', 'latency', 'balance']`
- **原因**：compile_mode 值不合法
- **修法**：使用 `bandwidth`, `latency` 或 `balance`
- **源码**：`_validate_compile_mode()` L1012-L1017

### `Parameter compile_mode is set to balance, please set balance_factor to use this mode`
- **原因**：balance 模式未指定 balance_factor
- **修法**：设置 0~100 的 balance_factor
- **源码**：`_validate_balance_factor()` L1037-L1039

### `The specified balance_factor X is invalid, it can only be specified as values in range 0-100`
- **原因**：balance_factor 超出 0~100 范围
- **修法**：设置为 0~100 之间的整数
- **源码**：`_validate_balance_factor()` L1040-L1043

## max_time_per_fc 相关

### `The specified max_time_per_fc is invalid, it can only be specified as 0 or range 1000-10000000`
- **原因**：max_time_per_fc 不在有效范围内
- **修法**：设为 0（不限）或 1000~10000000
- **源码**：`_validate_max_time_per_fc()` L1047-L1051

## max_l2m_size 相关

### `The specified max_l2m_size X is invalid, it can only be specified as values in range 0-25165824`
- **原因**：max_l2m_size 超出 0~24MB 范围
- **修法**：设置为 0~25165824 之间的值
- **源码**：`_validate_max_l2m_size()` L1000-L1004

### `The specified march Xxx does not support setting max_l2m_size`
- **原因**：nash-b/nash-e/nash-m 系列不支持 max_l2m_size
- **修法**：移除此参数或设为 0
- **源码**：`_validate_max_l2m_size()` L1005-L1008

## advice 相关

### `The parameter advice must be a positive integer`
- **原因**：advice 不是有效的浮点数
- **修法**：使用浮点数
- **源码**：`_validate_advice()` L1063-L1065

## fast_perf 模式相关

### `The number of your specified input names X is not equal to the number of model input names Y`
- **原因**：run_fast 模式下指定的 input_name 数量超过模型输入数
- **修法**：减少 input_name 数量或修正名称
- **源码**：`_validate_fast_perf()` L1143-L1147

### `The specified input_name Xxx is not in model inputs`
- **原因**：run_fast 模式下指定的 input_name 不在模型中
- **修法**：使用模型实际的输入名称
- **源码**：`_validate_fast_perf()` L1152-L1154

### `The length of specified input_shape [...] is not equal to the input_shape [...] in model`
- **原因**：run_fast 模式下 input_shape 维度数与模型不一致
- **修法**：确保维度数一致
- **源码**：`_validate_fast_perf()` L1157-L1160

### `Your input shape [...] but model input shape is [...], we only supports modifying the dim value of a dynamic batch`
- **原因**：run_fast 模式下修改了非动态维度的值
- **修法**：只修改动态维度（值为 `?`/`0`/`-1`）的值
- **源码**：`_validate_fast_perf()` L1161-L1165

### `The input Xxx has the dynamic input_shape [...], but the dim of this dynamic input_shape is not the first dim`
- **原因**：动态维度不在第一维（batch 维）
- **修法**：通过 input_shape 显式配置所有动态维度
- **源码**：`_validate_fast_perf()` L1172-L1179

## 类型校验（通用）

### `Wrong parameter 'Xxx' specified, bool value is required but get type Yyy`
- **原因**：需要 bool 类型的参数传入了其他类型
- **修法**：使用 YAML 布尔值 `true`/`false`
- **源码**：`bool_type_check()` L1231-L1245

### `Invalid value for max_l2m_size: Xxx`
- **原因**：max_l2m_size 值无法解析为整数或 None
- **修法**：使用整数或 `None`
- **源码**：`schema_yaml.py` → `use_none_or_int()` L12-L24
