# 运行时错误排错指南

本文档按报错文本倒排索引，覆盖模型运行时（hb_hbmruntime / hb_hbirruntime / hb_onnxruntime / verifier inference）的常见错误。

---

## `The input hbm model {model_file} does not exist.`

- **原因**：指定的 HBM 模型文件不存在。
- **修法**：
  1. 检查 HBM 文件路径是否正确（绝对路径或相对路径）。
  2. 确认文件未被删除或移动。
  3. 检查文件权限是否可读。
- **源码定位**：`horizon_tc_ui/hb_hbmruntime.py:22-25`

---

## `The model {model_file} is invalid. Only models with .hbm suffixes are supported.`

- **原因**：传入的文件不是 `.hbm` 后缀。
- **修法**：确保传入的是编译生成的 `.hbm` 文件。
- **源码定位**：`horizon_tc_ui/hb_hbmruntime.py:26-30`

---

## `Input model {model_file} is a packed model and is not supported now.`

- **原因**：HBM 文件是一个打包模型（包含多个 graph），当前不支持。
- **修法**：
  1. 使用非打包的单个 HBM 模型。
  2. 如果必须使用打包模型，需要拆分后分别加载。
- **源码定位**：`horizon_tc_ui/hb_hbmruntime.py:34-38`

---

## `The {model_file} does not exist !!!`

- **原因**：HBIR Runtime 加载 bc 模型时文件不存在。
- **修法**：检查 bc 文件路径是否正确。
- **源码定位**：`horizon_tc_ui/hb_hbirruntime.py:23-24`

---

## `The model {model_file} is invalid. Only models with .bc suffixes are supported.`

- **原因**：HBIR Runtime 要求 `.bc` 后缀的模型文件。
- **修法**：确保传入的是 `.bc` 格式的 HBIR 模型文件。
- **源码定位**：`horizon_tc_ui/hb_hbirruntime.py:25-29`

---

## `Please provide either model file or onnx model.`

- **原因**：HB_ONNXRuntime 初始化时既没有提供模型文件也没有提供 onnx 模型对象。
- **修法**：至少提供 `model_file` 或 `onnx_model` 其中一个参数。
- **源码定位**：`horizon_tc_ui/hb_onnxruntime.py:26-27`

---

## `The onnx_model does not have input index {index}!`

- **原因**：尝试获取不存在的输入索引。
- **修法**：检查索引值是否小于模型输入数量。
- **源码定位**：`horizon_tc_ui/hb_onnxruntime.py:200-203`

---

## `Wrong index: {index}. Model has {input_num} inputs.`

- **原因**：在 `get_hw` 方法中使用了超出范围的索引。
- **修法**：确保索引值在模型输入数量范围内（0 到 input_num-1）。
- **源码定位**：
  - `horizon_tc_ui/hb_hbirruntime.py:149-152`
  - `horizon_tc_ui/hb_onnxruntime.py:210-213`

---

## `The input data type {dtype} is illegal! The input type of the input model [{name}] is float, only {dtype_supported} data types are supported.`

- **原因**：ONNX 模型输入类型为 float，但传入的数据类型不在 `[uint8, int8, float32]` 范围内。
- **修法**：
  1. 将输入数据转换为 `uint8`、`int8` 或 `float32` 类型。
  2. 检查 npy 校准数据文件的 dtype 是否正确。
- **源码定位**：`horizon_tc_ui/hb_onnxruntime.py:248-254`

---

## `The input data type {dtype} is illegal! The input type of the input model [{name}] is uint8, only {dtype_supported} data types are supported.`

- **原因**：ONNX 模型输入类型为 uint8，但传入的数据类型不是 `uint8` 或 `int8`。
- **修法**：将输入数据转换为 `uint8` 或 `int8` 类型。
- **源码定位**：`horizon_tc_ui/hb_onnxruntime.py:281-287`

---

## `The input data type {dtype} is illegal! The input type of the input model [{name}] is int8, only {dtype_supported} data types are supported.`

- **原因**：ONNX 模型输入类型为 int8，但传入的数据类型不是 `uint8` 或 `int8`。
- **修法**：将输入数据转换为 `uint8` 或 `int8` 类型。
- **源码定位**：`horizon_tc_ui/hb_onnxruntime.py:301-307`

---

## `The input model [{name}] expects type is {dtype}, but the data type {dtype} of the input_data is not supported.`

- **原因**：ONNX 模型期望的输入数据类型与实际传入的数据类型不匹配，且不在自动转换范围内。
- **修法**：
  1. 检查输入数据的 dtype 是否与模型输入定义一致。
  2. 使用 `np.astype()` 转换为正确的 dtype。
- **源码定位**：`horizon_tc_ui/hb_onnxruntime.py:341-346`

---

## `Please provide input_info parameter.`

- **原因**：调用模型推理时未提供 `input_info` 参数。
- **修法**：
  1. 传入 `input_info` 字典，格式为 `{input_name: np.ndarray}`。
  2. 确保 input_name 与模型输入名称匹配。
- **源码定位**：
  - `horizon_tc_ui/hb_hbmruntime.py:149`（run_arm）
  - `horizon_tc_ui/hb_hbmruntime.py:195`（run_sim）
  - `horizon_tc_ui/hb_hbirruntime.py:225`（run）
  - `horizon_tc_ui/hb_hbirruntime.py:282`（run_direct）
  - `horizon_tc_ui/hb_onnxruntime.py:396`（run）
  - `horizon_tc_ui/hb_onnxruntime.py:451`（run_direct）

---

## `The output_name parameter has been deprecated, do not use both output_name and output_names.`

- **原因**：同时使用了已废弃的 `output_name` 和新的 `output_names` 参数。
- **修法**：只使用 `output_names` 参数，移除 `output_name`。
- **源码定位**：
  - `horizon_tc_ui/hb_hbirruntime.py:217-220`
  - `horizon_tc_ui/hb_onnxruntime.py:388-391`

---

## `The model type {model_type} is not supported now`

- **原因**：verifier inference 阶段遇到不支持的模型类型。当前仅支持 `onnx`、`bc`、`hbm`。
- **修法**：确保传入的模型文件后缀为 `.onnx`、`.bc` 或 `.hbm`。
- **源码定位**：`horizon_tc_ui/verifier/inference.py:32-35`

---

## `The model type {model_type} under {path} is invalid.`

- **原因**：verifier 数据预处理阶段遇到不支持的模型类型。
- **修法**：同上，确保模型类型正确。
- **源码定位**：`horizon_tc_ui/verifier/data_preprocess.py:70-71`

---

## `Wrong model type {other_model_type}.`

- **原因**：verifier 数据预处理中 batch 处理时遇到非预期的模型类型组合。
- **修法**：确保两个对比模型为支持的组合（onnx/bc/hbm）。
- **源码定位**：
  - `horizon_tc_ui/verifier/data_preprocess.py:335-336`
  - `horizon_tc_ui/verifier/data_preprocess.py:369-370`

---

## `Package '{package_name}'=={version} does not satisfy version spec '{version_spec}'.`

- **原因**：运行时依赖包版本不兼容。例如 hbdk4-compiler 要求 `>=4.0.22`，hbm_infer 要求 `>=3.9.0`。
- **修法**：
  1. 检查已安装包版本：`pip show hbdk4-compiler hmct hbm_infer`。
  2. 升级到满足要求的版本。
  3. 确保 hbdk4 和 hmct 版本匹配（通常来自同一 SDK 版本）。
- **源码定位**：
  - `horizon_tc_ui/utils/tool_utils.py:716-721`
  - `horizon_tc_ui/hb_compile.py:31-35`（hbdk4/hmct 版本检查）
  - `horizon_tc_ui/hb_hbmruntime.py:135-137`（hbm_infer 版本检查）
  - `horizon_tc_ui/verifier/params_check.py:163-169`（verifier 中 hbdk4 版本检查）

---

## `Package '{package_name}' is not installed, cannot verify version.`

- **原因**：运行时依赖的包未安装。
- **修法**：安装缺失的包：
  - `hbdk4-compiler`：编译和 HBIR runtime 必需
  - `hmct`：量化和 ONNX runtime 必需
  - `hbm_infer`：板端推理必需
- **源码定位**：`horizon_tc_ui/utils/tool_utils.py:709-713`

---

## `Cannot import symbol '{symbol}' from package '{package_name}' as attribute or submodule.`

- **原因**：包已安装但找不到指定的 API 符号，通常因为包版本过旧或 API 变更。
- **修法**：
  1. 升级包到最新版本。
  2. 检查包的 API 文档确认符号是否存在。
- **源码定位**：`horizon_tc_ui/utils/tool_utils.py:740-744`

---

## `Package '{package_name}' is required but not found. Please install it.`

- **原因**：`import_from` 尝试导入的包完全不存在。
- **修法**：安装对应的包。
- **源码定位**：`horizon_tc_ui/utils/tool_utils.py:726-730`

---

## `Cannot find function '{function_name}' in the module '{module_name}'.`

- **原因**：`import_function_from_module` 在指定模块中找不到目标函数。
- **修法**：
  1. 确认模块文件中确实定义了该函数。
  2. 检查函数名称拼写是否正确。
- **源码定位**：`horizon_tc_ui/utils/tool_utils.py:537-541`

---

## `Cannot find the module named '{module_name}'.`

- **原因**：`import_function_from_module` 找不到指定的模块。
- **修法**：
  1. 确认模块文件存在于正确的路径下。
  2. 检查模块的 `__init__.py` 是否存在。
- **源码定位**：`horizon_tc_ui/utils/tool_utils.py:542-545`

---

## `The input layout {input_layout} is invalid.`

- **原因**：`get_hw_index` 函数收到的 layout 不是 `NHWC` 或 `NCHW`。
- **修法**：检查 `input_layout_train` 配置是否为 `NHWC` 或 `NCHW`。
- **源码定位**：`horizon_tc_ui/utils/tool_utils.py:248-255`

---

## `Model desc parse failed, error log: {error}`

- **原因**：HBIR Runtime 解析模型 desc JSON 信息失败。
- **修法**：
  1. 检查 bc 模型文件是否完整。
  2. 确认模型是由 hb_compile 正常生成的。
  3. 如果 desc 为空不影响基本推理功能。
- **源码定位**：`horizon_tc_ui/hb_hbirruntime.py:132-133`

---

## `Model desc parse failed: {error}`

- **原因**：HBIRHandle 解析模型 desc 信息失败。
- **修法**：同上。
- **源码定位**：`horizon_tc_ui/hbir_handle.py:68-69`

---

## `No output to compare.`

- **原因**：verifier 一致性比较时没有找到可比较的输出。
- **修法**：
  1. 确认两个模型都有输出。
  2. 检查输出名称是否匹配（quantized 模型可能带有 `_quantized` 后缀）。
- **源码定位**：`horizon_tc_ui/verifier/comparator.py:68-69`

---

## `The model output consistency compare was failed.`

- **原因**：两个模型的输出在指定精度范围内不一致。
- **修法**：
  1. 检查量化参数是否合理（calibration_type、max_percentile 等）。
  2. 降低 `--compare_digits` 值放宽比较精度要求。
  3. 查看具体的 mismatch 信息定位差异较大的输出。
- **源码定位**：`horizon_tc_ui/verifier/comparator.py:73-74`

---

## `The output of {name} is empty, skip this tensor calculation.`

- **原因**：verifier cosine 比较时某个输出 tensor 为空。
- **修法**：检查模型该输出节点是否正常运行，输入数据是否有效。
- **源码定位**：`horizon_tc_ui/verifier/comparator.py:137-140`

---

## `The model [{name}] has different shapes, skip this tensor calculation. Model shape is different: {shape1} vs {shape2}`

- **原因**：verifier cosine 比较时两个模型同名输出 tensor shape 不同。
- **修法**：
  1. 确认两个模型的输入 shape 一致。
  2. 检查是否有 batch 维度差异导致的 shape 不匹配。
- **源码定位**：`horizon_tc_ui/verifier/comparator.py:149-154`

---

## `Input data shape does not match model input shape.`

- **原因**：verifier 预处理阶段输入数据 shape 与模型输入 shape 不匹配（非 batch 维度差异）。
- **修法**：确保输入数据的 shape（排除 batch 维度）与模型输入定义一致。
- **源码定位**：`horizon_tc_ui/verifier/data_preprocess.py:156-159`
