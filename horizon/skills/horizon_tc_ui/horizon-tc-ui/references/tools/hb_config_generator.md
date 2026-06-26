# hb_config_generator 工具参考

## 1. 概述

`hb_config_generator` 是用于生成 YAML 编译配置模板的工具，支持简单模板（simple）、完整模板（full）和自定义算子模板（custom-op）。它可以从模型文件（ONNX / Caffe / BC）中自动读取输入名称、形状、layout 等信息并填充到模板中，同时与 `schema_yaml` 进行交叉验证确保模板字段合法。

**入口点**（`setup.py` 中的 `console_scripts`）：

```
hb_config_generator = horizon_tc_ui.hb_config_generator:cmd_main
```

## 2. 命令签名

```bash
hb_config_generator [OPTIONS]
```

| 选项 | 类型 | 默认值 | 必填 | 隐藏 | 说明 |
|------|------|--------|------|------|------|
| `-s, --simple-yaml` | `flag` | `False` | 三选一 | 否 | 生成简单 YAML 模板 |
| `-f, --full-yaml` | `flag` | `False` | 三选一 | 否 | 生成完整 YAML 模板 |
| `-c, --custom-op` | `flag` | `False` | 三选一 | 是 | 生成自定义算子模板文件（当前不支持） |
| `-m, --model` | `str` | `None` | 否 | 否 | 待编译的模型文件路径（ONNX / Caffe / BC），用于自动填充参数 |
| `-p, --proto` | `str` | `None` | 否 | 否 | Caffe prototxt 文件（与 `-m` 配合使用） |
| `--march` | `click.Choice(...)` | `None` | 否 | 否 | BPU 微架构，合法值见 march 列表 |
| `-h, --help` | `flag` | - | 否 | 否 | 显示帮助信息 |

**互斥规则**：
- `-s`、`-f`、`-c` 三选一，只能指定一个（同时指定多个会报错）
- 都不指定时报错：`Please specify one mode to run`
- `-c/--custom-op` 当前不支持，调用时仅输出警告并返回
- 提供 `-p/--proto` 时必须同时提供 `-m/--model`

## 3. 典型调用示例

### 最小调用（生成简单模板）

```bash
hb_config_generator -s
```

### 常用调用（生成完整模板 + 自动填充模型信息）

```bash
hb_config_generator -f -m resnet50.onnx --march nash-e
```

### 全量调用（Caffe 模型 + 完整模板）

```bash
hb_config_generator -f -m resnet50.caffemodel -p deploy.prototxt --march nash-e
```

### 仅生成完整模板（不填充模型信息）

```bash
hb_config_generator -f
```

## 4. 输入要求

### 文件格式

`-m/--model` 支持以下模型格式：

| 格式 | 说明 | 是否需要 `-p/--proto` |
|------|------|----------------------|
| `.onnx` | ONNX 模型 | 否 |
| `.bc` | HBIR 量化模型 | 否 |
| `.caffemodel` | Caffe 模型 | 是（需同时提供 prototxt） |

### 自动模型信息填充

提供 `-m/--model` 时，工具自动从模型中读取以下信息并填入模板：

| 字段 | 来源 |
|------|------|
| `onnx_model` / `caffe_model` / `prototxt` | 模型文件相对路径 |
| `output_model_file_prefix` | 从文件名提取（去掉后缀） |
| `input_name` | 模型输入节点名称（分号分隔） |
| `input_shape` | 模型输入形状（`NxHxWxC` 格式，分号分隔） |
| `input_type_train` | 根据 input_layout 推断：有 layout → `bgr`，无 → `featuremap` |
| `input_type_rt` | 根据 input_layout 推断：有 layout → `nv12`，无 → `featuremap` |
| `input_layout_train` | 从模型提取，空则默认 `NCHW` |
| `cal_data_dir` | 按输入节点数量重复填充（分号分隔） |

### march 合法值

```
nash-b-lite, nash-b, nash-b-plus, nash-e, nash-m, nash-p, nash-starry-p, nash-h
```

## 5. 输出产物

### 命名规则

生成的 YAML 文件保存在当前工作目录：

| 模板类型 | 输出文件名 |
|----------|-----------|
| simple | `simple_compile_config.yaml` |
| full | `full_compile_config.yaml` |

### 模板内容差异

**简单模板（simple）**包含最基础参数：
- `model_parameters`：caffe_model, prototxt, onnx_model, march
- `input_parameters`：input_type_rt, input_type_train, input_layout_train
- `compiler_parameters`：optimize_level

**完整模板（full）**包含所有常用参数：
- `model_parameters`：全部参数（onnx_model, caffe_model, prototxt, march, working_dir, output_model_file_prefix, output_nodes, remove_node_type, remove_node_name, debug_mode 等）
- `input_parameters`：全部参数（input_name, input_type_rt, input_type_train, input_layout_train, input_shape, input_layout_rt, separate_batch, mean_value, scale_value, std_value, norm_type 等）
- `calibration_parameters`：cal_data_dir, quant_config
- `compiler_parameters`：全部参数（compile_mode, optimize_level, core_num, max_time_per_fc, jobs, input_source, advice, balance_factor, cache_path, cache_mode 等）

### 日志位置

- 日志文件：`./hb_config_generator.log`（当前工作目录）
- console 级别：`INFO`；file 级别：`DEBUG`

## 6. 退出码与错误约定

| 退出码 | 含义 |
|--------|------|
| `0` | 成功完成 |
| `-1` | 执行过程中发生异常（由 `@on_exception_exit` 装饰器处理） |

常见错误场景：
- `-s`、`-f`、`-c` 均未指定 → `ValueError: Please specify one mode to run`
- 同时指定多个模式 → `ValueError: We only support specify one mode`
- 提供 `--proto` 但未提供 `--model` → `ValueError`
- 模板字段不在 `schema_yaml` 中 → `ValueError: The key xxx is not in schema_yaml`
- 模型格式不支持（非 onnx/caffe/bc） → `ValueError: Unsupport model`

## 7. 版本兼容性

| 依赖 | 最低版本 | 说明 |
|------|----------|------|
| hbdk4-compiler | 无特殊要求 | 读取 `.bc` 模型信息时需要 |
| hmct | 无特殊要求 | 无版本限制 |

## 8. 源码入口

| 模块 | 路径 | 说明 |
|------|------|------|
| CLI 入口 | `horizon_tc_ui/hb_config_generator.py` | `cmd_main()` 函数 |
| 生成器核心 | `horizon_tc_ui/hb_config_generator.py` | `ConfigGenerator` 类 |
| Schema 定义 | `horizon_tc_ui/config/schema_yaml.py` | `schema_yaml` 参数定义（交叉验证依据） |
| 模板来源 | `horizon_tc_ui/template/` | `simple_template.yaml`, `full_template.yaml`, `fast_perf_template.yaml`, `check_template.yaml` |
| ONNX 运行时 | `horizon_tc_ui/hb_onnxruntime.py` | `HB_ONNXRuntime` 类（读取 ONNX 模型信息） |
| Caffe 解析器 | `horizon_tc_ui/parser/caffe_parser.py` | `CaffeParser` 类（读取 Caffe 模型信息） |
| HBIR 运行时 | `horizon_tc_ui/hb_hbirruntime.py` | `HB_HBIRRuntime` 类（读取 BC 模型信息） |
| 常量定义 | `horizon_tc_ui/config/mapper_consts.py` | march 列表等 |
