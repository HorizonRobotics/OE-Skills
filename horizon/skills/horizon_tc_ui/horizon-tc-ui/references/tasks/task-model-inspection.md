# hb_model_info 模型信息查看

## 适用场景

**触发关键词**：模型信息、model info、查看模型、模型结构、输入输出、可视化、netron

**前置条件**：
- 已有模型文件（`.onnx` / `.bc` / `.hbm` 之一）
- 已安装 `horizon_tc_ui` 工具包

## 产出物

| 产物 | 路径 | 说明 |
|-----|------|------|
| 控制台输出 | 终端 | 模型信息文本输出 |
| 日志文件 | `.hb_model_info/` 目录 | 详细日志 |
| 可视化文件 | `.hb_model_info/` 目录 | `.onnx`（bc 模型）或 `.prototxt`（hbm 模型） |

## 步骤

### 步骤 1：基本命令

```bash
# 查看 ONNX 模型信息
hb_model_info model.onnx

# 查看 BC（HBIR）模型信息
hb_model_info model_output/model_quantized_model.bc

# 查看 HBM 模型信息
hb_model_info model_output/model.hbm
```

### 步骤 2：可视化模型结构

> **⚠️ 严重警告：`--visualize` 会阻塞进程，必须手动 `Ctrl+C` 终止！**
>
> `--visualize` 会启动 Netron HTTP 服务器，**进程将永久挂起、不会自动退出**。
> - **禁止**在前台直接运行，否则后续所有操作都会被卡住
> - **推荐做法**：在后台运行（`&`）或直接查看生成的可视化产物文件

```bash
# 启动 netron 可视化（⚠️ 会阻塞终端，需 Ctrl+C 终止）
hb_model_info model.onnx --visualize

# BC 模型可视化（生成 .onnx 文件）
hb_model_info model_output/model_quantized_model.bc --visualize
# 产物：.hb_model_info/{model_name}.onnx

# HBM 模型可视化（生成 .prototxt 文件）
hb_model_info model_output/model.hbm --visualize
# 产物：.hb_model_info/{model_name}.prototxt
```

### 步骤 3：多函数模型过滤

对于打包模型（packed model，包含多个函数/子模型），使用 `-n` 参数过滤：

```bash
# 查看所有子模型信息（默认行为）
hb_model_info model_output/model.hbm

# 只查看指定子模型的信息
hb_model_info model_output/model.hbm -n submodel_name
```

> 如果不指定 `-n` 且模型包含多个函数，会输出警告提示：
> `This model is a packed model. If no model is specified, all model information will be printed by default.`

### 步骤 4：不同模型类型可查询的信息

#### ONNX 模型（`.onnx`）

| 信息类别 | 内容 |
|---------|------|
| opset version | ONNX opset 版本 |
| 输入/输出 | 名称、类型、shape、数据类型 |

**源码入口**：`hb_model_info.py:onnx_model_info()` → 使用 `HB_ONNXRuntime` 解析

#### BC/HBIR 模型（`.bc`）

| 信息类别 | 内容 |
|---------|------|
| 模型依赖 | BUILDER_VERSION, HBDK_VERSION, HMCT_VERSION / HORIZON_NN_VERSION |
| model_parameters | march, working_dir, output_model_file_prefix, layer_out_dump 等 |
| input_parameters | input_name, input_type_rt, input_type_train, input_shape, mean/scale/std 等 |
| calibration_parameters | calibration_type, cal_data_dir, per_channel, quant_config 等 |
| custom_op | custom_op_method, custom_op_dir, custom_op_reg_files |
| 输入/输出 | 名称、shape、dtype、quant_info |
| 可移除节点 | 可移除的 Quantize/Transpose/Dequantize/Cast/Reshape/Softmax 节点列表 |

**源码入口**：`hb_model_info.py:bc_model_info()` → 使用 `HB_HBIRRuntime` 解析

#### HBM 模型（`.hbm`）

| 信息类别 | 内容 |
|---------|------|
| 模型依赖 | 同 BC 模型 |
| model_parameters | 同 BC 模型 |
| input_parameters | 同 BC 模型 |
| calibration_parameters | 同 BC 模型 |
| compiler_parameters | optimize_level, core_num, max_time_per_fc, compile_mode, balance_factor, cache_mode 等 |
| custom_op | 同 BC 模型 |
| 内存信息 | input/output/static/dynamic/intermediate/temporary memory, min memory requirement |
| 输入/输出 | 名称、shape、数据类型（仅单函数模型） |

**源码入口**：`hb_model_info.py:hbm_model_info()` → 使用 `HBMHandle` 解析 + `hbm_perf` 获取内存信息

### 步骤 5：输出字段解读

#### 模型依赖信息
```
builder version      : x.x.x
hbdk version         : x.x.x
hmct version         : x.x.x
```

#### model_parameters 信息
```
bpu march            : nash-b
working dir          : ./model_output
output_model_file_prefix : model
```

#### 输入/输出信息
```
NAME          TYPE      SHAPE           DATA_TYPE
input_0       input     1x3x224x224     FLOAT
output_0      output    1x1000          FLOAT
```

#### 内存信息（仅 HBM）
```
input memory         : xxx
output memory        : xxx
static memory        : xxx
dynamic memory       : xxx
intermediate memory  : xxx
temporary memory     : xxx
min memory requirement : xxx
```

### 步骤 6：检查 .bc 文件的可移除节点

```bash
hb_model_info model_output/model_quantized_model.bc
```

输出中包含可移除节点信息：
```
############# Removable node info #############
Node Name              Type
Quantize_0             Quantize
Transpose_0            Transpose
Dequantize_0           Dequantize
```

支持移除的节点类型（源码 `mapper_consts.removal_list`）：
`Quantize`, `Transpose`, `Dequantize`, `Cast`, `Reshape`, `Softmax`

## 校验清单

- [ ] 模型文件存在且后缀正确（`.onnx` / `.bc` / `.hbm`）
- [ ] 命令执行完成，无 ValueError 报错
- [ ] 输出中包含输入/输出信息表
- [ ] 输入 shape 与预期一致
- [ ] HBM 模型的内存信息数值合理
- [ ] `.hb_model_info/` 目录已创建
- [ ] `--visualize` 模式下可视化文件已生成
- [ ] 多函数模型时，`-n` 指定的子模型名在 `func_names` 中存在

## 常见偏差与修法

| 偏差 | 修法 | 对应 troubleshooting |
|-----|------|---------------------|
| 模型后缀不支持 | 仅支持 `.onnx` / `.bc` / `.hbm` | runtime-errors.md |
| 模型文件不存在 | 确认文件路径正确 | runtime-errors.md |
| `-n` 指定的子模型不存在 | 先不带 `-n` 查看所有 func_names | runtime-errors.md |
| HBM 无 memory info | 模型可能无 BPU 算子 | runtime-errors.md |
| BC 模型加载失败 | 确认 BC 文件完整且 HBDK 版本兼容 | runtime-errors.md |
| 可视化文件未生成 | 确认 netron 依赖可用 | runtime-errors.md |

## 相关工具 / 模块链接

- **hb_model_info**：模型信息工具，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/hb_model_info.py`
- **HBMHandle**：HBM 操作，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/hbm_handle.py`
- **HBIRHandle**：HBIR 操作，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/hbir_handle.py`
- **HB_ONNXRuntime**：ONNX 运行时封装
- **HB_HBIRRuntime**：HBIR 运行时封装
- **HB_HBMRuntime**：HBM 运行时封装
- **Visualize**：可视化模块，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/visualize.py`
- **mapper_consts**：常量定义，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/config/mapper_consts.py`
