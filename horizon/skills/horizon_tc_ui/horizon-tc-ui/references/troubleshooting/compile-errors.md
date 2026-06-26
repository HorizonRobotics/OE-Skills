# 编译阶段错误排错指南

本文档按报错文本倒排索引，覆盖编译阶段（hb_compile / HBMBuilder / HBIRHandle）的常见错误。

---

## `*** ERROR-OCCUR-DURING hbdk.export ***`

- **原因**：ONNX 模型导出到 HBIR 失败。通常因为模型中存在不支持的 OP、shape 推导失败、ONNX 格式异常。
- **修法**：
  1. 检查 ONNX 模型是否可用 `onnx.checker.check_model()` 通过校验。
  2. 查看日志中 hbdk.export 子错误，确认是否包含不支持的算子。
  3. 尝试使用 `--skip export` 跳过导出步骤（如已有 bc 文件）。
  4. 设置 `HORIZON_TC_UI_DEBUG=1` 环境变量获取更详细日志。
- **源码定位**：
  - `horizon_tc_ui/hbir_handle.py:72-80`（`export_hbir` 方法，`@try_except_wrapper(module_info="hbdk.export")`）
  - `horizon_tc_ui/utils/wrap_utils.py:36-56`（`try_except_wrapper` 生成 `ERROR-OCCUR-DURING` 前缀）

---

## `*** ERROR-OCCUR-DURING hbdk.convert ***`

- **原因**：HBIR 浮点模型转量化模型失败。常见原因：
  - 模型中存在 BPU 不支持的算子且无法 fallback 到 CPU。
  - `input_type_rt` / `input_type_train` 配置与实际输入不匹配导致 preprocess op 插入失败。
  - `march` 参数与模型不兼容。
- **修法**：
  1. 检查日志中 convert 子错误，确认具体失败的算子。
  2. 通过 `node_info` 参数指定有问题的 OP 运行在 CPU（`ON: CPU`）。
  3. 确认 `input_type_rt` 和 `input_type_train` 的组合在 `mapper_consts.legal_trans_dict` 中合法。
  4. 设置 `HORIZON_TC_UI_DEBUG=1` 保留中间 `_inserted_model.bc` 文件排查。
- **源码定位**：
  - `horizon_tc_ui/hbir_handle.py:82-98`（`convert_quantize_model` 方法）
  - `horizon_tc_ui/compile/hbm_builder.py:287-301`（`convert_model` 方法）

---

## `*** ERROR-OCCUR-DURING hbdk.compile ***`

- **原因**：HBIR 量化模型编译为 HBM 文件失败。常见原因：
  - 编译超时（`max_time_per_fc` 设置过小）。
  - 编译内存不足（L2M 或系统内存）。
  - `core_num` 配置超出当前 march 支持范围。
  - `optimize_level` 不合法。
- **修法**：
  1. 增大 `max_time_per_fc`（有效范围 1000-10000000，0 表示不限）。
  2. 降低 `optimize_level`（如从 O2 降到 O1）。
  3. 减少 `core_num` 或增大 `max_l2m_size`（最大 24M = 25165824）。
  4. 增加系统可用内存或减少编译并行数 `jobs`。
- **源码定位**：
  - `horizon_tc_ui/hbir_handle.py:100-109`（`compile_model` 方法）
  - `horizon_tc_ui/compile/hbm_builder.py:310-319`（`compile_model` 方法）

---

## `*** ERROR-OCCUR-DURING hbdk.save ***`

- **原因**：保存 HBIR/HBM 模型文件失败。通常因为磁盘空间不足、目标路径无写权限。
- **修法**：
  1. 检查 `working_dir` 所在磁盘空间是否充足（`df -h`）。
  2. 确认对 `working_dir` 有写权限。
  3. 检查 `output_model_file_prefix` 是否包含非法字符。
- **源码定位**：
  - `horizon_tc_ui/compile/hbm_builder.py:303-308`（`save` 方法）

---

## `*** ERROR-OCCUR-DURING hbdk.statistics ***`

- **原因**：获取模型统计信息失败，通常在量化后统计 OP 分布时出现。
- **修法**：
  1. 确认量化模型（bc）文件完整未损坏。
  2. 检查 hbdk4 版本是否兼容。
- **源码定位**：
  - `horizon_tc_ui/hbir_handle.py:111-114`（`statistics` 方法）

---

## `*** ERROR-OCCUR-DURING hbdk.insert_split ***`

- **原因**：在模型输入处插入 Split OP 失败。通常因为 `input_batch` 配置与模型输入 shape 不匹配。
- **修法**：
  1. 确认 `input_shape` 的第一个维度为 1（使用 `input_batch` 时要求）。
  2. 检查 `input_batch` 值是否合理。
- **源码定位**：
  - `horizon_tc_ui/hbir_handle.py:132-134`（`insert_split` 方法）
  - `horizon_tc_ui/compile/hbm_builder.py:187-215`（`input_insert_nodes_based_separate_batch` 方法）

---

## `*** ERROR-OCCUR-DURING hbdk.insert_image_preprocess ***`

- **原因**：插入图像预处理 OP 失败。通常因为 `input_type_rt` 与 `input_type_train` 的组合不在 `preprocess_mode_map` 中。
- **修法**：
  1. 检查 `input_type_rt` 和 `input_type_train` 的组合是否在 `mapper_consts.preprocess_mode_map` 中。
  2. 如果不需要颜色转换，将 `input_type_rt` 和 `input_type_train` 设为相同值。
- **源码定位**：
  - `horizon_tc_ui/hbir_handle.py:136-150`（`insert_image_preprocess` 方法）
  - `horizon_tc_ui/compile/hbm_builder.py:78-128`（`insert_image_preprocess` 方法）
  - `horizon_tc_ui/config/mapper_consts.py:224-235`（`preprocess_mode_map` 映射表）

---

## `*** ERROR-OCCUR-DURING hbdk.insert_image_convert ***`

- **原因**：插入图像转换 OP 失败（pyramid input_source 专用）。
- **修法**：
  1. 确认 `input_type_rt` 是 pyramid 支持的类型：`nv12`, `gray`, `yuv420sp_bt601_video`, `yuv_bt601_full`。
  2. 如果不使用 pyramid，将 `input_source` 改为 `ddr`。
- **源码定位**：
  - `horizon_tc_ui/hbir_handle.py:152-154`（`insert_image_convert` 方法）
  - `horizon_tc_ui/compile/hbm_builder.py:153-158`（pyramid 分支）

---

## `*** ERROR-OCCUR-DURING hbdk.insert_transpose ***`

- **原因**：插入 Transpose OP 失败。通常因为 `input_layout_train` 为 NCHW 时需要转 NHWC，但输入维度不匹配。
- **修法**：
  1. 确认 `input_layout_train` 为 NCHW 时输入 shape 是 4 维。
  2. 如果已经是 NHWC 格式，将 `input_layout_train` 改为 NHWC。
- **源码定位**：
  - `horizon_tc_ui/hbir_handle.py:156-158`（`insert_transpose` 方法）
  - `horizon_tc_ui/compile/hbm_builder.py:142-146`（NCHW 转置逻辑）

---

## `*** ERROR-OCCUR-DURING hbdk.insert_roi_resize ***`

- **原因**：插入 ROI Resize OP 失败（resizer input_source 专用）。
- **修法**：
  1. 确认 `input_type_rt` 是 resizer 支持的类型：`nv12`, `gray`, `yuv420sp_bt601_video`, `yuv_bt601_full`。
  2. 如果不使用 resizer，将 `input_source` 改为 `ddr`。
- **源码定位**：
  - `horizon_tc_ui/hbir_handle.py:160-162`（`insert_roi_resize` 方法）
  - `horizon_tc_ui/compile/hbm_builder.py:159-164`（resizer 分支）

---

## `*** ERROR-OCCUR-DURING hbdk.overlay.remove_io_op ***`

- **原因**：移除输入/输出端 OP 失败。指定的 OP 类型或名称不在可移除列表中。
- **修法**：
  1. 确认 `remove_node_type` 中的类型在 `mapper_consts.removal_list` 中（`Quantize`, `Transpose`, `Dequantize`, `Cast`, `Reshape`, `Softmax`）。
  2. 确认 `remove_node_name` 指定的节点名称存在于模型中。
- **源码定位**：
  - `horizon_tc_ui/hbir_handle.py:164-176`（`remove_io_op` 方法）
  - `horizon_tc_ui/config/mapper_consts.py:163-165`（`removal_list`）

---

## `The model {model_path} is invalid. Only models with .bc suffixes are supported.`

- **原因**：从 bc 文件重新编译时，指定的模型文件不是 .bc 后缀。
- **修法**：确保传入的模型文件路径以 `.bc` 结尾。
- **源码定位**：`horizon_tc_ui/hb_compile.py:160-163`

---

## `The {model_path} does not exist.`

- **原因**：指定的 bc 模型文件或 yaml 配置文件不存在。
- **修法**：检查文件路径是否正确，文件是否已被删除或移动。
- **源码定位**：`horizon_tc_ui/hb_compile.py:165-166`

---

## `The config file or march value is missing, please specify either -c/--config or --march parameter.`

- **原因**：从 bc 文件重新编译时，bc 文件中没有 desc 信息，且未通过 `--march` 或 `-c/--config` 指定 march。
- **修法**：使用 `--march` 指定 march 或通过 `-c` 提供包含 march 的 yaml 配置文件。
- **源码定位**：`horizon_tc_ui/hb_compile.py:187-192`

---

## `Only the bc model supports being recompiled.`

- **原因**：尝试重新编译的模型不是 bc 格式。
- **修法**：仅对 `.bc` 后缀的模型使用重新编译功能。
- **源码定位**：`horizon_tc_ui/hb_compile.py:264-265`

---

## `The fast-perf mode is turned on, the incoming config file {config} cannot be used.`

- **原因**：同时启用了 `--fast-perf` 和 `-c/--config`，两者互斥。
- **修法**：关闭 fast-perf 模式或不传入 config 文件。
- **源码定位**：`horizon_tc_ui/hb_compile.py:358-367`

---

## `The model file is missing, please specify the -m/--model parameter.`

- **原因**：启用 fast-perf 模式但未指定模型文件。
- **修法**：使用 `-m/--model` 参数指定模型文件路径。
- **源码定位**：`horizon_tc_ui/hb_compile.py:368-372`

---

## `The model file or config file is missing, please specify either -m/--model or -c/--config parameter.`

- **原因**：既没有指定模型文件也没有指定配置文件。
- **修法**：至少指定 `-m/--model` 或 `-c/--config` 其中一个参数。
- **源码定位**：`horizon_tc_ui/hb_compile.py:373-378`

---

## `The --core-num option is only available with check/fast-perf mode.`

- **原因**：在使用 config 模式时指定了 `--core-num`，该选项仅在 check/fast-perf 模式下有效。
- **修法**：移除 `--core-num` 参数，或在 yaml 中通过 `compiler_parameters.core_num` 配置。
- **源码定位**：`horizon_tc_ui/hb_compile.py:379-383`

---

## `The fast-perf mode currently only supports onnx and caffe models.`

- **原因**：fast-perf 模式下传入了不支持的模型类型（如 bc、hbm）。
- **修法**：fast-perf 模式仅支持 `.onnx` 和 `.caffemodel` 模型。
- **源码定位**：`horizon_tc_ui/hb_compile.py:88-95`

---

## `The --fast-perf mode only supports the .onnx and .caffemodel model.`

- **原因**：同上，fast-perf 模式入口处的模型后缀检查。
- **修法**：使用 `.onnx` 或 `.caffemodel` 模型。
- **源码定位**：`horizon_tc_ui/hb_compile.py:237-241`

---

## `The current model {model} is not the onnx or caffe model, please specify the config file and re-execute hb_compile.`

- **原因**：check 模式下模型文件后缀不是 onnx/caffemodel/caffe。
- **修法**：使用正确格式的模型文件或通过 yaml config 模式执行。
- **源码定位**：`horizon_tc_ui/hb_compile.py:123-128`

---

## `The specified march '{march}' is invalid, the march parameter only supports values in {march_list}`

- **原因**：指定的 march 不在支持列表中。
- **修法**：使用 `get_march_list()` 返回的支持列表中的值，如 `nash-b`, `nash-h`, `nash-p` 等。
- **源码定位**：
  - `horizon_tc_ui/config/params_parser.py:198-204`（`_validate_march`）
  - `horizon_tc_ui/compile/ptq_model_builder.py:42-45`

---

## `The specified optimize_level '{optimize_level}' is invalid, it can only be specified as values in {optimize_level_hbdk4}`

- **原因**：`optimize_level` 不在 `['O0', 'O1', 'O2']` 范围内（hbdk4 仅支持到 O2）。
- **修法**：将 `optimize_level` 改为 `O0`、`O1` 或 `O2`。
- **源码定位**：
  - `horizon_tc_ui/config/params_parser.py:910-917`（`_validate_optimize_level`）
  - `horizon_tc_ui/config/mapper_consts.py:159`（`optimize_level_hbdk4`）

---

## `Wrong core_num {core_num} specified, it can only be specified as values in range {core_num_range}`

- **原因**：`core_num` 超出当前 march 支持的 core 数量范围。例如 `nash-b` 只支持 1 core，`nash-h` 支持 1-4 core。
- **修法**：根据 march 调整 `core_num`，参考 `mapper_consts.core_num_range`。
- **源码定位**：
  - `horizon_tc_ui/config/params_parser.py:975-992`（`_validate_core_num`）
  - `horizon_tc_ui/config/mapper_consts.py:174-182`（`core_num_range`）

---

## `Wrong core_num {core_num} specified, it must be a positive integer`

- **原因**：`core_num` 不是正整数。
- **修法**：将 `core_num` 设置为 >= 1 的整数。
- **源码定位**：`horizon_tc_ui/config/params_parser.py:987-991`

---

## `The specified max_l2m_size {max_l2m_size} is invalid, it can only be specified as values in range 0-25165824`

- **原因**：`max_l2m_size` 超出 0 ~ 24MB 范围。
- **修法**：将 `max_l2m_size` 设置在 0 到 25165824 之间，或设为 0 使用默认值。
- **源码定位**：`horizon_tc_ui/config/params_parser.py:994-1009`

---

## `The specified march {march} does not support setting max_l2m_size`

- **原因**：`nash-b*`、`nash-e`、`nash-m` 系列 march 不支持设置 `max_l2m_size`。
- **修法**：将 `max_l2m_size` 设为 0 或不设置，或切换到支持该参数的 march（如 nash-h、nash-p）。
- **源码定位**：`horizon_tc_ui/config/params_parser.py:1005-1008`

---

## `The specified compile_mode {compile_mode} is invalid, it can only be specified as values in {compile_mode_list}`

- **原因**：`compile_mode` 不在 `['bandwidth', 'latency', 'balance']` 中。
- **修法**：将 `compile_mode` 改为 `bandwidth`、`latency` 或 `balance`。
- **源码定位**：
  - `horizon_tc_ui/config/params_parser.py:1011-1018`（`_validate_compile_mode`）
  - `horizon_tc_ui/config/mapper_consts.py:187`（`compile_mode_list`）

---

## `Parameter compile_mode is set to balance, please set balance_factor to use this mode`

- **原因**：`compile_mode` 设为 `balance` 但未指定 `balance_factor`。
- **修法**：在 `compiler_parameters` 中设置 `balance_factor`（范围 0-100）。
- **源码定位**：`horizon_tc_ui/config/params_parser.py:1037-1039`

---

## `The specified balance_factor {balance_factor} is invalid, it can only be specified as values in range 0-100`

- **原因**：`balance_factor` 不在 0-100 范围内。
- **修法**：将 `balance_factor` 设置为 0 到 100 之间的整数。
- **源码定位**：`horizon_tc_ui/config/params_parser.py:1040-1043`

---

## `The specified max_time_per_fc is invalid, it can only be specified as 0 or range 1000-10000000`

- **原因**：`max_time_per_fc` 不在有效范围内（0 或 1000-10000000）。
- **修法**：将 `max_time_per_fc` 设为 0（不限）或 1000 到 10000000 之间的值。
- **源码定位**：`horizon_tc_ui/config/params_parser.py:1045-1052`

---

## `The specified cache_path {cache_path} does not exist, please create it before compilation`

- **原因**：指定的编译缓存路径不存在。
- **修法**：创建缓存目录后再执行编译，或将 `cache_mode` 设为 `disable`。
- **源码定位**：`horizon_tc_ui/config/params_parser.py:268-272`

---

## `The specified cache_mode {cache_mode} is invalid, it can only be specified as values in {cache_mode_list}`

- **原因**：`cache_mode` 不在 `['enable', 'force_overwrite', 'disable']` 中。
- **修法**：将 `cache_mode` 改为 `enable`、`force_overwrite` 或 `disable`。
- **源码定位**：
  - `horizon_tc_ui/config/params_parser.py:275-292`（`_validate_cache_mode`）
  - `horizon_tc_ui/config/mapper_consts.py:237`（`cache_mode_list`）

---

## `The cache_path must be specified when the cache_mode is not disable`

- **原因**：启用了缓存模式但未指定缓存路径。
- **修法**：在 `compiler_parameters` 中设置 `cache_path` 或将 `cache_mode` 改为 `disable`。
- **源码定位**：`horizon_tc_ui/config/params_parser.py:282-285`

---

## `The output_model_file_prefix cannot be empty, please specify a valid prefix in your yaml config file`

- **原因**：`output_model_file_prefix` 为空字符串。
- **修法**：在 yaml 的 `model_parameters` 中指定非空的 `output_model_file_prefix`。
- **源码定位**：`horizon_tc_ui/config/params_parser.py:217-225`

---

## `Unsupport removing {types} now`

- **原因**：`remove_node_type` 中包含了不在 `removal_list` 中的 OP 类型。
- **修法**：只使用 `Quantize`、`Transpose`、`Dequantize`、`Cast`、`Reshape`、`Softmax` 中的类型。
- **源码定位**：
  - `horizon_tc_ui/config/params_parser.py:232-242`（`_validate_remove_node_type`）
  - `horizon_tc_ui/config/mapper_consts.py:163-165`（`removal_list`）

---

## `The model has been specified with input_type_train as {train} and input_type_rt as {rt}, the image preprocess op will not be inserted`

- **原因**：`input_type_train` 到 `input_type_rt` 的颜色转换组合不在 `preprocess_mode_map` 中。
- **修法**：修改 `input_type_train` 和 `input_type_rt` 的组合为支持的转换，或将两者设为相同值跳过颜色转换。
- **源码定位**：`horizon_tc_ui/compile/hbm_builder.py:92-96`

---

## `Invalid parameter configuration.`

- **原因**：hb_compile 命令行参数组合无法匹配任何已知模式。
- **修法**：检查 `--config`、`--model`、`--fast-perf` 的组合，确保符合以下模式之一：
  - 仅 `--config`：config 模式
  - 仅 `--model` + `--fast-perf`：fast-perf 模式
  - `--config` + `--model`：bc 重新编译模式
  - 仅 `--model`：check 模式
- **源码定位**：`horizon_tc_ui/hb_compile.py:404-405`

---

## `Package '{package_name}' is not installed, cannot verify version.`

- **原因**：hb_compile 启动时检查依赖包版本，发现指定包未安装。
- **修法**：安装缺失的包，例如 `pip install hbdk4-compiler` 或 `pip install hmct`。
- **源码定位**：`horizon_tc_ui/utils/tool_utils.py:709-713`

---

## `Package '{package_name}'=={version} does not satisfy version spec '{version_spec}'.`

- **原因**：已安装的包版本不满足要求。例如 hbdk4-compiler 要求 `>=4.0.22`。
- **修法**：升级或降级包到满足版本要求的范围。
- **源码定位**：`horizon_tc_ui/utils/tool_utils.py:716-721`

---

## `Cannot import symbol '{symbol}' from package '{package_name}' as attribute or submodule.`

- **原因**：包已安装但找不到指定的符号（函数/类/子模块）。
- **修法**：确认包版本正确，检查 API 是否在当前版本中可用。
- **源码定位**：`horizon_tc_ui/utils/tool_utils.py:740-744`

---

## `Failed to generate node info: {error}`

- **原因**：生成节点信息时发生异常，通常在 convert 之后的 node_info 阶段。
- **修法**：检查 `node_info` 参数配置是否正确，查看具体错误日志。
- **源码定位**：`horizon_tc_ui/compile/hbm_builder.py:264-274`
