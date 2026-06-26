# YAML 参数参考 — model_parameters

> 源码依据：`horizon_tc_ui/config/schema_yaml.py`（schema 定义）
> 校验逻辑：`horizon_tc_ui/config/params_parser.py` → `_validate_model_parameters()`

## 完整参数表

| 参数 | 类型 | 默认值 | 必填 | 可选范围 | 说明 |
|------|------|--------|------|----------|------|
| `onnx_model` | str | `None` | 条件必填 | 文件路径，`.onnx` 后缀 | ONNX 模型文件路径。与 `caffe_model` 互斥 |
| `caffe_model` | str | `None` | 条件必填 | 文件路径，`.caffemodel` 后缀 | Caffe 模型文件路径。与 `onnx_model` 互斥 |
| `prototxt` | str | `None` | 使用 caffe 时必填 | 文件路径，`.prototxt` 后缀 | Caffe 网络定义文件。与 `caffe_model` 配合使用 |
| `march` | str | `""` | **必填** | 见下方合法值列表 | 目标芯片架构，必须显式指定 |
| `log_level` | int | 无 | 否 | int | **已废弃**。控制台日志固定为 info，文件日志固定为 debug |
| `layer_out_dump` | bool/str/int | `false` | 否 | bool | 是否逐层输出中间结果（调试用） |
| `working_dir` | str | `./model_output` | 否 | 目录路径 | 编译输出目录，不存在时自动创建 |
| `output_model_file_prefix` | str | `model` | 否 | 非空字符串 | 输出模型文件前缀，不能为空 |
| `output_nodes` | str | `None` | 否 | 分号分隔的节点名列表 | 指定模型输出节点，用于截断模型 |
| `remove_node_type` | str | `None` | 否 | 分号分隔的类型列表，见下方支持列表 | 指定要移除的节点类型 |
| `remove_node_name` | str | `None` | 否 | 分号分隔的节点名列表 | 指定要移除的节点名称 |
| `node_info` | str/dict | `None` | 否 | 字符串或字典格式 | 指定节点的数据类型或运行位置（CPU/BPU），优先级最高 |
| `debug_mode` | str | `None` | 否 | `dump_calibration_data` | 模型调试模式 |
| `enable_vpu` | bool | `true` | 否 | bool | 是否启用 VPU（向量处理单元） |
| `enable_spu` | bool | `true` | 否 | bool | 是否启用 SPU（标量处理单元） |
| `set_node_data_type` | - | - | 否 | - | **已废弃**，指定此参数无效 |

## march 合法值列表

源码位置：`mapper_consts.py` → `march_list`

| march 值 | 支持的 core_num |
|----------|----------------|
| `nash-b-lite` | `[1]` |
| `nash-b` | `[1]` |
| `nash-b-plus` | `[1]` |
| `nash-e` | `[1]` |
| `nash-m` | `[1]` |
| `nash-h` | `[1, 2, 3, 4]` |
| `nash-p` | `[1, 2, 3, 4]` |
| `nash-starry-p` | `[1, 2, 3, 4]` |

源码位置：`mapper_consts.py` → `core_num_range`

## remove_node_type 支持列表

源码位置：`mapper_consts.py` → `removal_list`

仅支持移除以下节点类型：`Quantize`, `Transpose`, `Dequantize`, `Cast`, `Reshape`, `Softmax`

## 互斥关系

1. **`onnx_model` vs `caffe_model`+`prototxt`**：不能同时指定 ONNX 和 Caffe 模型文件
   - 源码：`params_parser.py` → `_validate_model_file()` L168-L171

2. 三者必须至少指定一组：
   - `onnx_model` 单独使用
   - `caffe_model` + `prototxt` 组合使用

## node_info 格式说明

支持两种格式：

**字符串格式**（仅指定输出类型）：
```yaml
node_info: "Conv_0:int16;Conv_1:int16"
```

**字典格式**（可指定输入类型、输出类型、运行位置）：
```yaml
node_info:
  Conv_0:
    OutputType: int16
    InputType0: int8
    ON: BPU
```

支持的键：`ON`（值：`BPU`/`CPU`）、`OutputType`、`InputType`、`InputType0`/`InputType1`/...

## 影响阶段

| 参数 | 影响阶段 |
|------|---------|
| `onnx_model`/`caffe_model`/`prototxt` | 模型加载与解析 |
| `march` | 量化、编译全流程（决定后端目标） |
| `working_dir`/`output_model_file_prefix` | 输出文件路径 |
| `output_nodes` | 模型图截断 |
| `remove_node_type`/`remove_node_name` | 模型图优化 |
| `node_info` | 量化阶段（节点数据类型/运行位置） |
| `debug_mode` | 模型调试数据收集 |
| `enable_vpu`/`enable_spu` | 编译阶段（硬件单元启用） |

## 典型错误

| 错误片段 | 原因 | 修法 |
|---------|------|------|
| `It is not supported to specify both onnx_model and caffe_model` | 同时指定了 ONNX 和 Caffe | 只保留一种模型格式 |
| `The model file has not been correctly specified` | 未指定任何模型文件 | 指定 `onnx_model` 或 `caffe_model`+`prototxt` |
| `The specified march 'xxx' is invalid` | march 值不在合法列表中 | 使用上方合法值列表中的值 |
| `The output_model_file_prefix cannot be empty` | 前缀为空字符串 | 指定非空前缀 |
| `Unsupport removing Xxx now` | `remove_node_type` 包含不支持的类型 | 仅使用 `removal_list` 中的类型 |
