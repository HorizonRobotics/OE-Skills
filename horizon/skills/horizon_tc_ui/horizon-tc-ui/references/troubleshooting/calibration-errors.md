# 校准/量化阶段错误排错指南

本文档按报错文本倒排索引，覆盖校准（calibration）和量化（PTQ）阶段的常见错误。

---

## `The specified calibration_type '{calibration_type}' is invalid, it can only be specified as values in {check_list}`

- **原因**：`calibration_type` 不在允许的取值范围内。
- **修法**：将 `calibration_type` 改为以下值之一：
  - `kl`：KL 散度校准（autoq）
  - `max`：最大值校准（autoq）
  - `skip`：跳过量化（preq，不需要校准数据）
  - 留空：使用默认校准方式
- **源码定位**：
  - `horizon_tc_ui/config/params_parser.py:772-784`（`_validate_calibration_type`）
  - `horizon_tc_ui/config/mapper_consts.py:117-123`（`autoq_caltype_list` 和 `preq_caltype_list`）

---

## `Wrong cal_data_dir num received.`

- **原因**：`cal_data_dir` 的数量与模型输入数量不匹配，且不为 0。
- **修法**：
  1. 确保 `cal_data_dir` 的数量等于模型输入数量（`input_num`）。
  2. 或者留空（数量为 0），此时校准方式自动设为 `skip`。
  3. 多输入模型用分号分隔多个目录，如 `cal_data_dir: ./cal_data/input1;./cal_data/input2`。
- **源码定位**：`horizon_tc_ui/config/params_parser.py:801-804`

---

## `The specified cal_data_dir {cal_data_dir} does not exist`

- **原因**：指定的校准数据目录路径不存在。
- **修法**：
  1. 确认校准数据目录已创建且路径正确。
  2. 如果使用相对路径，注意路径相对于 yaml 配置文件所在目录。
  3. 如果不需要校准数据，将 `calibration_type` 设为 `skip` 或留空 `cal_data_dir`。
- **源码定位**：`horizon_tc_ui/config/params_parser.py:814-817`

---

## `The calibration dataset has not been specified, the calibration method is modified to skip`

- **原因**：未指定 `cal_data_dir`，系统自动将校准方式改为 `skip`。这不是错误，而是一条信息日志。
- **修法**：
  1. 如果确实不需要校准（如 QAT 模型），可以忽略此信息。
  2. 如果需要校准，请在 `calibration_parameters` 中指定 `cal_data_dir`。
- **源码定位**：`horizon_tc_ui/config/params_parser.py:806-809`

---

## `The specified cal_data_type '{type}' is invalid, it can only be specified as values in {cal_data_type_list}`

- **原因**：`cal_data_type` 不在 `['uint8', 'float32']` 范围内。
- **修法**：
  1. 将 `cal_data_type` 改为 `uint8` 或 `float32`。
  2. 注意：该参数已被标记为 deprecated，建议直接将校准数据集转换为 `.npy` 格式。
- **源码定位**：
  - `horizon_tc_ui/config/params_parser.py:838-843`（`_validate_cal_data_type`）
  - `horizon_tc_ui/config/mapper_consts.py:185`（`cal_data_type_list`）

---

## `The suffix of the calibration dir name is not the same as the value {cal_data_type} specified by the parameter cal_data_type`

- **原因**：校准数据目录名称的后缀（如 `_uint8` 或 `_f32`）与 `cal_data_type` 参数不一致。
- **修法**：
  1. 确保目录名称后缀与 `cal_data_type` 一致（`_uint8` 对应 `uint8`，`_f32` 对应 `float32`）。
  2. 或者直接移除 `cal_data_type` 参数，系统会根据目录后缀自动判断。
- **源码定位**：`horizon_tc_ui/config/params_parser.py:844-858`

---

## `The specified max_percentile {max_percentile} is invalid, avaliable range: 0~1`

- **原因**：`max_percentile` 值不在 0 到 1 的范围内。
- **修法**：
  1. 将 `max_percentile` 设置为 0.0 到 1.0 之间的浮点数。
  2. 常用值：`0.9995`、`0.9999`、`1.0`。
  3. 如果不需要设置，留空或设为 `None`。
- **源码定位**：`horizon_tc_ui/config/params_parser.py:868-877`

---

## `Directory {data_dir} is empty, please check calibration pics.`

- **原因**：校准数据目录为空，没有任何文件。
- **修法**：
  1. 将校准图片/数据放入指定目录。
  2. 确认目录路径没有写错。
  3. 校准数据通常需要一定数量的样本（建议 100+ 张图片）。
- **源码定位**：`horizon_tc_ui/data/loader.py:203`

---

## `Directory {dataset} is empty.`

- **原因**：数据处理阶段发现数据集目录为空。
- **修法**：同上，确保校准数据目录包含有效的数据文件。
- **源码定位**：`horizon_tc_ui/data/data_processer.py:50`

---

## `The read mode is {read_mode}, but the {image_read_mode} package is not installed.`

- **原因**：指定的图片读取模式对应的 Python 包未安装。
- **修法**：
  1. 安装对应的包：`skimage`（scikit-image）、`opencv`（opencv-python）、`PIL`（Pillow）。
  2. 或者修改 `image_read_mode` 为已安装的模式。
- **源码定位**：`horizon_tc_ui/data/data_processer.py:53`

---

## `The data type {dtype} is invalid!`

- **原因**：校准数据的 dtype 不是支持的类型。
- **修法**：确保校准数据为 `uint8` 或 `float32` 类型。
- **源码定位**：`horizon_tc_ui/data/data_processer.py:68`

---

## `The read mode {read_mode} is invalid.`

- **原因**：图片读取模式不在 `['skimage', 'opencv', 'PIL']` 中。
- **修法**：将 `image_read_mode` 改为 `skimage`、`opencv` 或 `PIL`。
- **源码定位**：
  - `horizon_tc_ui/data/data_processer.py:87`
  - `horizon_tc_ui/config/mapper_consts.py:214`（`image_read_mode_list`）

---

## `Failed to open {file} with skimage.`

- **原因**：使用 skimage 读取校准图片失败，文件可能损坏或格式不支持。
- **修法**：
  1. 检查该图片文件是否完整、可正常打开。
  2. 确认图片格式为支持的类型（jpg、png、bmp 等）。
  3. 尝试更换读取模式（如 `opencv`）。
- **源码定位**：`horizon_tc_ui/data/loader.py:269-270`

---

## `The file {file} load failed,`

- **原因**：校准数据文件加载失败，可能是 npy 文件格式损坏或不兼容。
- **修法**：
  1. 检查 npy 文件是否完整，尝试用 `np.load()` 单独加载验证。
  2. 确认 npy 文件的 shape 与模型输入 shape 匹配。
  3. 重新生成校准数据文件。
- **源码定位**：
  - `horizon_tc_ui/data/loader.py:308-309`
  - `horizon_tc_ui/data/loader.py:341-342`

---

## `Input data shape does not match model input shape.`

- **原因**：校准数据的 shape 与模型输入 shape 不匹配（排除 batch 维度扩展的情况）。
- **修法**：
  1. 检查校准数据的 shape 是否与 `input_shape` 一致。
  2. 对于 NCHW/NHWC 布局差异，确认 `input_layout_train` 配置正确。
  3. 重新生成正确 shape 的校准数据。
- **源码定位**：`horizon_tc_ui/verifier/data_preprocess.py:156-159`

---

## `The input_type_rt {idx} is featuremap, configuration of mean/scale/std is not supported`

- **原因**：对 featuremap 类型的输入配置了 mean/scale/std 归一化参数，但 featuremap 输入不支持归一化。
- **修法**：
  1. 移除该输入的 mean_value、scale_value、std_value 配置。
  2. 或者将 `input_type_rt` 改为非 featuremap 类型。
- **源码定位**：`horizon_tc_ui/config/params_parser.py:693-697`

---

## `Only one of scale_value and std_value can be specified`

- **原因**：同时指定了 `scale_value` 和 `std_value`，两者只能选一个。
- **修法**：
  1. 只保留 `scale_value` 或 `std_value` 其中一个。
  2. `scale_value` 表示对输入做乘法缩放，`std_value` 语义相同但命名不同。
- **源码定位**：`horizon_tc_ui/config/params_parser.py:673-675`

---

## `Wrong format of mean_value {mean_value} specified, please refer to user manual`

- **原因**：`mean_value` 格式解析失败。正确格式为逗号或空格分隔的浮点数列表，多个输入用分号分隔。
- **修法**：
  1. 检查 mean_value 格式，例如：`123.675, 116.28, 103.53`（RGB 三通道）。
  2. 多输入示例：`123.675,116.28,103.53; 128.0`。
  3. 灰度图只需一个值。
- **源码定位**：`horizon_tc_ui/config/params_parser.py:702-718`

---

## `Wrong format of scale_value {scale_value} specified, please refer to user manual`

- **原因**：同上，`scale_value` 格式不正确。
- **修法**：同上，确保格式正确。例如：`0.017, 0.017, 0.017`。
- **源码定位**：`horizon_tc_ui/config/params_parser.py:720-736`

---

## `Wrong format of std_value {std_value} specified, please refer to user manual`

- **原因**：同上，`std_value` 格式不正确。
- **修法**：同上，确保格式正确。
- **源码定位**：`horizon_tc_ui/config/params_parser.py:738-754`

---

## `The specified input_type_rt is {input_type_rt}, but the input_shape is not four-dimensional, please set the input_type_rt and input_type_train to featuremap`

- **原因**：输入 shape 不是 4 维但 `input_type_rt` 不是 `featuremap`。非 featuremap 类型（如 nv12、rgb、bgr 等）需要 4 维输入（NHWC 或 NCHW）。
- **修法**：
  1. 如果输入确实是 featuremap，将 `input_type_rt` 和 `input_type_train` 都设为 `featuremap`。
  2. 如果是图像输入，确保 `input_shape` 为 4 维（如 `1x224x224x3`）。
- **源码定位**：`horizon_tc_ui/config/params_parser.py:572-579`

---

## `The input shape: {shape} is invalid, nv12 type does not support odd number input size`

- **原因**：`input_type_rt` 为 `nv12` 时，输入的 H 或 W 维度为奇数。NV12 格式要求宽高均为偶数。
- **修法**：将输入的 H 和 W 维度调整为偶数（如 224、448 等）。
- **源码定位**：`horizon_tc_ui/config/params_parser.py:756-769`

---

## `The specified input_space_and_range: {value} and input_type_rt {input_type_rt} combination is invalid`

- **原因**：`input_space_and_range` 为 `bt601_video` 但 `input_type_rt` 不是 `nv12`。该组合仅支持 nv12。
- **修法**：
  1. 如果使用 `bt601_video`，将 `input_type_rt` 改为 `nv12`。
  2. 如果使用其他 `input_type_rt`，将 `input_space_and_range` 改为 `regular`。
- **源码定位**：`horizon_tc_ui/config/params_parser.py:562-569`

---

## `The specified input_type_train '{train_type}' of the input {idx} is not supported to be transformed to input_type_rt '{rt_type}' now`

- **原因**：`input_type_train` 到 `input_type_rt` 的颜色空间转换组合不在 `legal_trans_dict` 映射表中。
- **修法**：
  1. 查看 `mapper_consts.legal_trans_dict` 支持的转换组合。
  2. 修改 `input_type_train` 或 `input_type_rt` 为支持的组合。
  3. 或将两者设为相同值跳过颜色转换。
- **源码定位**：
  - `horizon_tc_ui/config/params_parser.py:633-659`（`_validate_input_type_association`）
  - `horizon_tc_ui/config/mapper_consts.py:57-70`（`legal_trans_dict`）

---

## `Input {idx} has input_type_rt {rt_type} with input_layout_train NCHW is not supported on bernoulli2 for now.`

- **原因**：在 bernoulli2 march 上不支持 `yuv444`/`yuv444_128` + NCHW 的组合。
- **修法**：
  1. 将 `input_layout_train` 改为 `NHWC`。
  2. 或将 `input_type_rt` 改为其他类型。
- **源码定位**：`horizon_tc_ui/config/params_parser.py:638-645`

---

## `The specified input_type_train is gray, but the channel dim of input_shape {shape} is not 1`

- **原因**：`input_type_train` 为 `gray` 但输入 shape 的通道维度不是 1。
- **修法**：确保灰度图的 channel 维度为 1，如 `1x224x224x1`（NHWC）或 `1x1x224x224`（NCHW）。
- **源码定位**：`horizon_tc_ui/config/params_parser.py:611-617`

---

## `The specified input_layout_train is: {layout}, but the channel dim of input_shape {shape} is not 3`

- **原因**：非灰度图输入的 channel 维度不是 3。
- **修法**：确保 RGB/BGR 等 3 通道输入的 channel 维度为 3。
- **源码定位**：`horizon_tc_ui/config/params_parser.py:618-624`

---

## `This model has non-featuremap inputs, please specify the input_layout_train`

- **原因**：模型有非 featuremap 的输入但未指定 `input_layout_train`。
- **修法**：在 `input_parameters` 中指定 `input_layout_train` 为 `NHWC` 或 `NCHW`。
- **源码定位**：`horizon_tc_ui/config/params_parser.py:626-630`

---

## `Wrong {name} num received. Num of {name} given: {len} is not equal to input num {input_num}`

- **原因**：某个输入参数的数量与模型输入数量不一致。
- **修法**：确保以下参数的数量等于模型输入数量（用分号分隔多个值）：
  - `input_type_rt`
  - `input_type_train`
  - `input_space_and_range`
  - `input_layout_train`
  - `norm_type`
  - `cal_data_type`
- **源码定位**：`horizon_tc_ui/config/params_parser.py:902-908`（`_validate_num`）

---

## `The parameter advice must be a positive integer`

- **原因**：`advice` 参数无法解析为浮点数。
- **修法**：将 `advice` 设置为一个浮点数（如 `0.5`），或留空。
- **源码定位**：`horizon_tc_ui/config/params_parser.py:1057-1065`

---

## `Your specified custom op method {cop_method} is invalid`

- **原因**：自定义 OP 注册方法不是 `register`。
- **修法**：将 `custom_op_method` 设为 `register`。
- **源码定位**：`horizon_tc_ui/compile/ptq_model_builder.py:71-73`

---

## `workspace does not exist. workspace: {workspace}`

- **原因**：PTQModelBuilder 的工作目录不存在。
- **修法**：创建 workspace 目录或在 yaml 中指定存在的 `working_dir`。
- **源码定位**：`horizon_tc_ui/compile/ptq_model_builder.py:58-60`

---

## `The specified march {march} is invalid, the march parameter only supports values in {march_list}`

- **原因**：PTQModelBuilder 初始化时 march 不在支持列表中。
- **修法**：使用有效的 march 值。
- **源码定位**：`horizon_tc_ui/compile/ptq_model_builder.py:41-45`

---

## `*** ERROR-OCCUR-DURING hmct.api.build_model ***`

- **原因**：调用 hmct 的 `build_model` 进行模型量化时失败。这是量化阶段的核心入口，子错误通常来自 hmct 内部。
- **修法**：
  1. 检查校准数据是否正确加载（查看日志中 "Processing calibration set data" 相关输出）。
  2. 确认校准数据数量足够（建议 100+ 张）。
  3. 检查 `calibration_type`、`per_channel`、`max_percentile` 等参数是否合理。
  4. 查看 hmct 输出的详细错误信息定位具体问题。
  5. 确认 ONNX/Caffe 模型结构完整无异常。
- **源码定位**：
  - `horizon_tc_ui/compile/ptq_model_builder.py:225-237`（`build_model` 方法）
  - `horizon_tc_ui/utils/wrap_utils.py:36-56`（`try_except_wrapper`）

---

## `*** ERROR-OCCUR-DURING hmct.custom.op_registration.op_register ***`

- **原因**：自定义 OP 注册失败。通常因为注册文件路径不正确或模块导入失败。
- **修法**：
  1. 确认 `op_register_files` 中指定的 .py 文件路径正确。
  2. 确认 `custom_op_dir` 目录存在且包含正确的注册代码。
  3. 检查注册文件中是否有语法错误或依赖缺失。
- **源码定位**：`horizon_tc_ui/compile/ptq_model_builder.py:65-91`

---

## `The input_batch value is missing. Please check the bc model.`

- **原因**：在 verifier 数据预处理阶段，`separate_batch` 为 True 但 bc 模型的 desc 中缺少 `input_batch` 值。
- **修法**：
  1. 检查 bc 模型的 desc 信息是否完整。
  2. 重新编译 bc 模型确保 desc 中包含 `input_batch` 信息。
- **源码定位**：`horizon_tc_ui/verifier/data_preprocess.py:321-322`

---

## `Input name {input_name} is not found in model.`

- **原因**：verifier 数据预处理时找不到对应的输入名称。
- **修法**：
  1. 检查输入名称是否与模型定义一致。
  2. 确认 `input_source` 配置中的输入名称正确。
- **源码定位**：`horizon_tc_ui/verifier/data_preprocess.py:176-177`

---

## `Input name {input_name} not found in model.`

- **原因**：在反向预处理量化模型时，输入名称不存在于模型的 inputs 字典中。
- **修法**：检查模型输入名称与数据名称是否匹配，注意 `_y`、`_uv`、`_roi` 后缀的处理。
- **源码定位**：`horizon_tc_ui/verifier/data_preprocess.py:404-405`

---

## `Unsupported dtype: {dtype}`

- **原因**：verifier 生成随机数据时遇到不支持的 numpy dtype。
- **修法**：确保模型输入 dtype 为支持的类型（uint8/16/32/64, int8/16/32/64, float16/32/64）。
- **源码定位**：`horizon_tc_ui/verifier/data_preprocess.py:138-139`
