# hb_compile 工具参考

## 1. 概述

`hb_compile` 是将浮点模型（ONNX / Caffe）映射为量化模型并最终编译为 BPU 可执行 `.hbm` 文件的核心工具。它覆盖从 PTQ 量化、HBIR 导出、算子转换到 HBM 编译的完整流水线。

**入口点**（`setup.py` 中的 `console_scripts`）：

```
hb_compile = horizon_tc_ui.hb_compile:main
```

## 2. 命令签名

```bash
hb_compile [OPTIONS]
```

| 选项 | 类型 | 默认值 | 必填 | 说明 |
|------|------|--------|------|------|
| `-c, --config` | `click.Path(exists=True)` | `None` | 否 | 模型转换配置文件（YAML 路径） |
| `-m, --model` | `click.Path(exists=True)` | `None` | 否 | 待编译或修改的模型文件（ONNX / Caffe / BC） |
| `--proto` | `click.Path(exists=True)` | `None` | 否 | Caffe prototxt 文件（与 `--model` 配合使用） |
| `--march` | `click.Choice(...)` | `None` | 否 | BPU 微架构，合法值见下文 march 列表 |
| `-i, --input-shape` | `(str, str)`，`multiple=True` | `()` | 否 | 指定模型输入形状，格式：`--input-shape input1 1x3x224x224`，可多次指定 |
| `--fast-perf` | `flag` | `False` | 否 | 以 fast-perf 模式构建，自动推断 input_type |
| `--core-num` | `int` | `None` | 否 | BPU 核心数，仅在 check / fast-perf 模式下可用 |
| `--skip` | `str` | `None` | 否 | 跳过指定阶段，可选值：`export`、`convert`、`compile` |

**互斥规则**：
- `--fast-perf` 与 `--config` 互斥（同时指定会报错）
- `--core-num` 仅在 check / fast-perf 模式下可用，与 `--config` 模式互斥
- `--fast-perf` 必须配合 `--model` 使用，不能单独使用
- `--model` 和 `--config` 至少指定一个

**4 种运行模式**（由参数组合自动判定）：

| 模式 | 触发条件 | 说明 |
|------|----------|------|
| config mode | `--config` 且无 `--model`、无 `--fast-perf` | 基于 YAML 配置文件的完整编译流程 |
| fast-perf mode | `--fast-perf` + `--model` 且无 `--config` | 快速性能评估，自动生成临时 YAML |
| check mode | `--model` 且无 `--config`、无 `--fast-perf` | 模型检查模式，验证 ONNX / Caffe 模型是否可编译 |
| bc_config mode | `--config` + `--model`（`.bc`） | 从已有的 `.bc` 量化模型重新编译为 `.hbm` |

## 3. 典型调用示例

### 最小调用（config mode）

```bash
hb_compile -c compile_config.yaml
```

### 常用调用（fast-perf mode）

```bash
hb_compile --fast-perf -m model.onnx --march nash-e --input-shape input 1x3x224x224
```

### 全量调用（fast-perf mode + 指定 core_num + 跳过阶段）

```bash
hb_compile --fast-perf -m model.onnx --march nash-p \
  --input-shape input 1x3x224x224 \
  --core-num 4 \
  --skip compile
```

### Caffe 模型 fast-perf

```bash
hb_compile --fast-perf -m model.caffemodel --proto model.prototxt --march nash-e
```

### BC 模型重新编译

```bash
hb_compile -c compile_config.yaml -m quantized_model.bc --march nash-e
```

### check mode

```bash
hb_compile -m model.onnx --march nash-e --input-shape input 1x3x224x224
```

## 4. 输入要求

### 文件格式

| 模式 | 支持的模型格式 |
|------|----------------|
| config mode | ONNX（通过 YAML 中的 `onnx_model` 或 `caffe_model` 指定） |
| fast-perf mode | `.onnx`、`.caffemodel` |
| check mode | `.onnx`、`.caffemodel`、`.caffe` |
| bc_config mode | `.bc` |

### shape / layout 约束

- `--input-shape` 格式为 `输入名 维度x维度x...`，如 `input 1x3x224x224`
- 支持动态 batch：当第一个维度为动态时，自动设为 `1`
- 非首个维度的动态维度不支持，需通过 `--input-shape` 显式指定所有动态维度
- fast-perf 模式自动推断 `input_type_rt` / `input_type_train`：
  - 4 维输入且通道数为 3、H/W 均为偶数、模型有 layout 信息 → `nv12` / `bgr`
  - 否则 → `featuremap`

### march 合法值

```
nash-b-lite, nash-b, nash-b-plus, nash-e, nash-m, nash-p, nash-starry-p, nash-h
```

当 `hbdk4.march` 模块可用时，优先使用 `hbdk4.march.get_all_bpu_march_names()` 的结果。

## 5. 输出产物

### 命名规则

所有产物以 `output_model_file_prefix` 为前缀（默认取模型文件名去掉后缀）。

| 产物 | 命名规则 | 说明 |
|------|----------|------|
| HBM 模型 | `{prefix}.hbm` | 最终 BPU 可执行模型 |
| 量化 HBIR | `{prefix}_quantized_model.bc` | convert 阶段产物 |
| 删除节点后 HBIR | `{prefix}_quantized_removed_model.bc` | 有节点被删除时生成 |
| PTQ 模型（调试） | `{prefix}_ptq_model.bc` | 仅当 `HORIZON_TC_UI_DEBUG` 环境变量启用 |
| 插入节点后 HBIR（调试） | `{prefix}_inserted_model.bc` | 仅当 `HORIZON_TC_UI_DEBUG` 环境变量启用 |
| 性能分析 JSON | `{prefix}.json` | 在 `working_dir` 下 |

### 目录结构

各模式下 `working_dir` 语义不同：

| 模式 | working_dir 默认值 | 说明 |
|------|-------------------|------|
| config mode | YAML 中 `model_parameters.working_dir` | 用户指定 |
| fast-perf mode | `model_output/`（或 `model_output_{timestamp}/`） | 自动生成 |
| check mode | `.hb_compile/` | 自动生成 |
| bc_config mode | YAML 中 `model_parameters.working_dir` | 用户指定 |

产物目录示例（config mode）：

```
{working_dir}/
├── {prefix}.hbm
├── {prefix}_quantized_model.bc
├── {prefix}.json              # 性能分析结果
└── hb_compile.log             # 编译日志副本
```

### 日志位置

- 主日志：`./hb_compile.log`（当前工作目录）
- 日志副本：自动复制到 `{working_dir}/hb_compile.log`
- 日志格式：`%(asctime)s file: %(filename)s func: %(module)s line No: %(lineno)d %(message)s`
- console 级别：`INFO`；file 级别：`DEBUG`

## 6. 退出码与错误约定

| 退出码 | 含义 |
|--------|------|
| `0` | 成功完成 |
| `-1` | 执行过程中发生异常（由 `@on_exception_exit` 装饰器处理） |

常见错误场景：
- `--fast-perf` 与 `--config` 同时指定 → `ValueError`
- `--fast-perf` 未指定 `--model` → `ValueError`
- `--model` 和 `--config` 均未指定 → `ValueError`
- `--core-num` 与 `--config` 模式同时使用 → `ValueError`
- fast-perf / check 模式下 `--march` 未指定 → `ValueError`
- 模型文件不存在或格式不支持 → `ValueError`
- 动态 shape 非首维度 → `ValueError`

## 7. 版本兼容性

| 依赖 | 最低版本 | 说明 |
|------|----------|------|
| hbdk4-compiler | `>=4.0.22` | 通过 `import_from("hbdk4.compiler", "load", ">=4.0.22", "hbdk4-compiler")` 校验 |
| hmct | 任意 | 通过 `import_from("hmct.api", "version", package_name="hmct")` 导入，无版本限制 |

## 8. 源码入口

| 模块 | 路径 | 说明 |
|------|------|------|
| CLI 入口 | `horizon_tc_ui/hb_compile.py` | `main()` 函数，模式分发 |
| HBM 构建器 | `horizon_tc_ui/compile/hbm_builder.py` | `HBMBuilder` 类，export → convert → compile → perf 流水线 |
| HBIR 处理器 | `horizon_tc_ui/hbir_handle.py` | `HBIRHandle` 类，HBIR 操作封装 |
| YAML 构建器 | `horizon_tc_ui/utils/yaml_builder.py` | `YamlBuilder` 类，fast_perf / check 模式自动生成 YAML |
| 参数解析器 | `horizon_tc_ui/config/params_parser.py` | `ParamsParser` 类，YAML 校验 |
| 配置信息 | `horizon_tc_ui/config/config_info.py` | `ConfigInfo` 数据结构 |
| PTQ 构建器 | `horizon_tc_ui/compile/ptq_model_builder.py` | `PTQModelBuilder` 类，PTQ 量化 |
| 常量定义 | `horizon_tc_ui/config/mapper_consts.py` | march 列表、input_type 列表等 |
