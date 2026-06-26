# hb_model_info 工具参考

## 1. 概述

`hb_model_info` 是用于查看模型编译参数、属性和结构的诊断工具，支持 `.hbm`、`.bc`、`.onnx` 三种模型格式。它能够输出模型的依赖信息、输入输出参数、量化配置、编译器参数以及内存使用情况，并可选启动 Netron 进行可视化。

**入口点**（`setup.py` 中的 `console_scripts`）：

```
hb_model_info = horizon_tc_ui.hb_model_info:cmd_main
```

## 2. 命令签名

```bash
hb_model_info [OPTIONS] MODEL_PATH
```

| 选项 | 类型 | 默认值 | 必填 | 隐藏 | 说明 |
|------|------|--------|------|------|------|
| `MODEL_PATH` | `str`（argument） | 无 | 是 | - | 模型文件路径（`.hbm` / `.bc` / `.onnx`） |
| `-n, --name` | `str` | `""` | 否 | 是 | 仅输出指定名称的子模型信息（用于多函数打包的 HBM 模型） |
| `-v, --visualize` | `flag` | `False` | 否 | 否 | 启动 Netron 服务器展示模型结构 |

> **⚠️ 严重警告：`-v/--visualize` 会阻塞进程！**
>
> 使用 `-v/--visualize` 参数会启动 Netron HTTP 服务器，**进程将永久挂起、不会自动退出**。
> - **必须**手动 `Ctrl+C` 终止，否则后续所有操作都会被卡住
> - **禁止**在自动化脚本/流水线中使用 `--visualize`，除非在后台运行（`&`）或设置了超时机制
> - AI agent 调用此命令时，**必须**以后台方式运行或提醒用户手动关闭

| `-h, --help` | `flag` | - | 否 | 否 | 显示帮助信息 |
| `--version` | `flag` | - | 否 | 否 | 显示版本信息 |

## 3. 典型调用示例

### 最小调用（查看 ONNX 模型信息）

```bash
hb_model_info model.onnx
```

### 常用调用（查看 HBM 模型信息 + 可视化）

> **⚠️ 以下命令会阻塞终端！** 必须 `Ctrl+C` 手动终止，否则会卡住。

```bash
hb_model_info -v model.hbm
```

### 全量调用（查看多函数打包 HBM 中的指定子模型）

```bash
hb_model_info -n resnet50 -v packed_model.hbm
```

### 查看 BC 模型信息

```bash
hb_model_info quantized_model.bc
```

## 4. 输入要求

### 文件格式

支持以下三种后缀的模型文件：

| 后缀 | 模型类型 | 依赖 |
|------|----------|------|
| `.hbm` | BPU 可执行模型 | hbdk4-compiler >= 4.0.22 |
| `.bc` | HBIR 量化模型 | hbdk4-compiler >= 4.0.22 |
| `.onnx` | ONNX 浮点/量化模型 | onnx（已安装） |

### 多函数打包模型

- 当 HBM 模型包含多个函数（`func_num > 1`）时，默认打印所有子模型信息并给出警告
- 使用 `-n` 选项可过滤只查看指定名称的子模型
- 若指定的名称不在 `func_names` 列表中，将抛出 `ValueError`

## 5. 输出产物

### 控制台输出

根据不同模型类型，输出以下信息模块：

**所有模型类型共有**：
- 输入/输出信息（NAME, TYPE, SHAPE, DATA_TYPE 表格）

**`.bc` / `.hbm` 模型额外输出**：
- 模型依赖信息（BUILDER_VERSION, HBDK_VERSION, HMCT_VERSION / HORIZON_NN_VERSION）
- model_parameters 信息（march, working_dir, output_model_file_prefix 等）
- input_parameters 信息（input_name, input_type_rt, input_type_train, input_shape, norm_type 等）
- calibration_parameters 信息（calibration_type, cal_data_dir, per_channel, optimization 等）
- compiler_parameters 信息（仅 `.hbm`）（optimize_level, core_num, compile_mode, max_time_per_fc 等）
- custom_op 信息（如有）
- 可删除节点信息（仅 `.bc`）（Removable node info）
- 内存信息（仅 `.hbm`，来自 perf JSON）（input/output/static/dynamic/intermediate/temporary memory, min memory requirement）

### 输出目录

工具在当前目录下创建 `.hb_model_info/` 目录：

```
.hb_model_info/
├── {model_name}.json          # HBM 性能分析 JSON（由 hbdk4.compiler.hbm_perf 生成）
├── {model_name}.onnx          # BC 模型可视化转换产物（--visualize 时）
└── {model_name}.prototxt      # HBM 模型可视化转换产物（--visualize 时）
```

### 日志位置

- 日志文件：`./hb_model_info.log`（当前工作目录）
- console 级别：`INFO`；file 级别：`DEBUG`

### 其他产物

- 当模型有已删除节点时，在当前目录生成 `deleted_nodes_info.txt`

## 6. 退出码与错误约定

| 退出码 | 含义 |
|--------|------|
| `0` | 成功完成 |
| `-1` | 执行过程中发生异常（由 `@on_exception_exit` 装饰器处理） |

常见错误场景：
- 模型后缀不是 `.hbm` / `.bc` / `.onnx` → `ValueError: The model xxx is invalid`
- 模型文件不存在 → `ValueError: The xxx does not exist!`
- `-n` 指定的子模型名称不在 HBM 的 func_names 中 → `ValueError: Desired model invalid`
- BC 模型加载失败 → `ValueError: The model xxx load failed`

## 7. 版本兼容性

| 依赖 | 最低版本 | 说明 |
|------|----------|------|
| hbdk4-compiler | `>=4.0.22` | 仅 `.hbm` / `.bc` 模型需要，通过 `import_from("hbdk4.compiler", "load", ">=4.0.22", "hbdk4-compiler")` 校验 |
| hmct | 任意 | 无版本限制 |
| onnx | 已安装 | `.onnx` 模型需要 |

## 8. 源码入口

| 模块 | 路径 | 说明 |
|------|------|------|
| CLI 入口 | `horizon_tc_ui/hb_model_info.py` | `cmd_main()` 函数，`main()` 分发逻辑 |
| HBM 信息处理 | `horizon_tc_ui/hb_model_info.py` | `hbm_model_info()` 函数 |
| BC 信息处理 | `horizon_tc_ui/hb_model_info.py` | `bc_model_info()` 函数 |
| ONNX 信息处理 | `horizon_tc_ui/hb_model_info.py` | `onnx_model_info()` 函数 |
| HBM 处理器 | `horizon_tc_ui/hbm_handle.py` | `HBMHandle` 类，HBM 文件解析 |
| HBIR 运行时 | `horizon_tc_ui/hb_hbirruntime.py` | `HB_HBIRRuntime` 类，BC 模型运行时 |
| ONNX 运行时 | `horizon_tc_ui/hb_onnxruntime.py` | `HB_ONNXRuntime` 类，ONNX 模型运行时 |
| HBM 运行时 | `horizon_tc_ui/hb_hbmruntime.py` | `HB_HBMRuntime` 类，HBM 模型运行时 |
| 可视化工具 | `horizon_tc_ui/visualize.py` | `Visualize` 类，Netron 可视化 |
| 常量定义 | `horizon_tc_ui/config/mapper_consts.py` | `removal_list` 等 |
