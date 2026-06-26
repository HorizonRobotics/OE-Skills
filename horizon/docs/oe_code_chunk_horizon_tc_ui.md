# oe_code_chunk_horizon_tc_ui

## 仓库概述

- **Name**: `horizon_tc_ui` v3.5.16
- **Summary**: Horizon Algorithm Toolchain User Interface — the CLI and user-facing auxiliary layer of the Horizon Robotics Open Explorer toolchain
- **Target Hardware**: Journey 6 (Nash) BPU family: `nash-b-lite`, `nash-b`, `nash-b-plus`, `nash-e`, `nash-m`, `nash-p`, `nash-starry-p`, `nash-h`
- **Role in Toolchain**: Provides six `hb_*` console_scripts that wrap `hbdk4_compiler` (BPU compiler), `hmct` (calibration/quantization), `hbdnn`/`hbm_infer` (runtime inference). It is the entry-point users interact with for: model compilation (`hb_compile`), config generation, model inspection, verification (simulator + ARM board SSH), analysis/visualization, and eval dataset preprocessing.
- **Python**: `>=3.10,<3.12`; dependencies include `click`, `onnx==1.15.0`, `numpy`, `opencv-python`, `paramiko`, `pydantic>2`, `pyyaml`, `schema`, `scikit-image`.
- **Distribution**: Installed as a pre-built wheel; no source build system, tests, or lint config. Ships with `horizon_tc_ui-3.5.16.dist-info/`.

## 目录结构

```
horizon_tc_ui-3.5.16-py3/
├── CLAUDE.md                          # 仓库指引（含 CLI 表、编译流水线、约定）
├── horizon_tc_ui-3.5.16.dist-info/    # wheel 元信息（entry_points.txt, METADATA）
└── horizon_tc_ui/
    ├── __init__.py                    # 仅暴露 __version__
    ├── version.py                     # __version__ 字符串
    ├── hb_compile.py                  # hb_compile CLI：编译主流水线
    ├── hb_verifier.py                 # hb_verifier CLI：ONNX/BC/HBM 推理比对
    ├── hb_analyzer.py                 # hb_analyzer CLI group (analyze + visualize)
    ├── hb_config_generator.py         # hb_config_generator CLI：生成 YAML 模板
    ├── hb_model_info.py               # hb_model_info CLI：模型依赖/编译参数/节点信息
    ├── hb_eval_preprocess.py          # hb_eval_preprocess CLI：精度评测数据预处理
    ├── hb_runtime.py                  # HBRuntime：按文件后缀分发到三种 runtime
    ├── hb_onnxruntime.py              # .onnx runtime
    ├── hb_hbirruntime.py              # .bc (HBIR) runtime
    ├── hb_hbmruntime.py               # .hbm (已编译 BPU 模型) runtime
    ├── hbir_handle.py                 # HBIR 图改写/量化 advice/perf 抽取（依赖 hbdk4）
    ├── hbm_handle.py                  # HBM handle（依赖 hbdk4）
    ├── helper.py                      # 辅助函数
    ├── analyzer/                      # HBAnalyzer + JsonParser + AnalysisPrinter
    ├── compile/                       # PTQModelBuilder (校准) + HBMBuilder (编译+perf)
    ├── config/                        # ConfigInfo dataclass + ParamsParser + schema_yaml + mapper_consts
    ├── data/                          # DataLoader 工厂：cifar/coco/imagenet/voc/raw
    ├── eval_preprocess/               # EvalPreprocess + data_transformer（精度评测预处理）
    ├── parser/                        # caffe_parser + onnx_parser + horizon_caffe_pb2
    ├── template/                      # simple/full/fast_perf/check_template.yaml + sample_custom.py
    ├── utils/                         # tool_utils, log_format, colour, model_utils, node_info, yaml_builder, shell_wrapper, wrap_utils
    ├── verifier/                      # VerifierParamsCheck + DataPreprocess + Inference + Comparator
    └── visualize/                     # Visualize（Netron 启动 + .bc/.hbm → .onnx 转换）
```

## 关键模块与 API

### CLI 入口（`console_scripts` in `entry_points.txt`）

| 命令 | 入口 | 主要功能 |
|---|---|---|
| `hb_compile` | `hb_compile:main` | 浮点模型 → 量化模型 → `.hbm` |
| `hb_verifier` | `hb_verifier:cmd_main` | Simulator + ARM 板端推理 + 输出比对 |
| `hb_analyzer` | `hb_analyzer:hb_analyzer` | Click group: `analyze` / `visualize` |
| `hb_config_generator` | `hb_config_generator:cmd_main` | 生成 `simple`/`full`/`fast_perf` YAML |
| `hb_model_info` | `hb_model_info:cmd_main` | 输出 deps / compile info / removable nodes |
| `hb_eval_preprocess` | `hb_eval_preprocess:cmd_main` | ImageNet/COCO/CIFAR/VOC 数据预处理 |

### 编译流水线（`hb_compile.py`）

- `params_check(yaml_path) -> ConfigInfo` — 校验 YAML，返回 `ConfigInfo`
- `ptq_model_build(conf) -> ModelProto` — 校准（`PTQModelBuilder.build()`）
- `fast_perf_handle(model, proto, march, input_shape, core_num)` — fast-perf 模式
- `copy_compile_log_file(working_dir)` — 复制日志到 working_dir
- 模式分支由 `-c/--config`、`-m/--model`、`--fast-perf` 组合决定：
  - Config mode（仅 `-c`）→ `onnx_config_mode`
  - Fast-perf（`--fast-perf -m`）→ `fast_perf_mode`（内部 `YamlBuilder` 生成 YAML）
  - BC recompile（`-c -m foo.bc`）→ `bc_config_mode` → `hbm_build_from_bc`
  - Check mode（仅 `-m`）→ `check_mode`

### 配置体系

- `config/schema_yaml.py` — 参数 schema（单一来源：key / default / 校验规则）
- `config/params_parser.py::ParamsParser(yaml_path)` — 解析 YAML，产出 `ConfigInfo`
- `config/config_info.py::ConfigInfo(ConfigBase)` — dataclass，贯穿所有 builder；支持 `conf.get(name, default)` 和 `conf[name]`
- `config/mapper_consts.py` — march 列表、input type、BPU 算子、layout、`core_num_range`
- `template/{simple,full,fast_perf,check}_template.yaml` — schema 子集模板

### Runtime 与 Handle

- `hb_runtime.py::HBRuntime(path)` — 按后缀分发：`.onnx` → `HB_ONNXRuntime`；`.bc` → `HB_HBIRRuntime`；`.hbm` → `HB_HBMRuntime`
- `hbir_handle.py::HBIRHandle(model)` — HBIR 图改写、量化 advice、perf 抽取（import `hbdk4.compiler`）
- `hbm_handle.py::HBMHandle(hbm_path)` — HBM 操作、`visualize(save_path=...)`
- `compile/ptq_model_builder.py::PTQModelBuilder(model, march, conf, name_prefix)` — 校准
- `compile/hbm_builder.py::HBMBuilder` — 编译 + perf 生成

### 分析 / 可视化 / 验证

- `analyzer/analyzer.py::HBAnalyzer(model, march, perf_json, work_space=".hb_analyzer/", remote_ip, ...)` — 模型 + perf JSON 分析
- `visualize/visualize.py::Visualize(model_path, save_path)` — `.check()` / `.convert_model()` / `.start_server()` (Netron)
- `verifier/`: `VerifierParamsCheck` → `VerifierDataPreprocess` → `VerifierInference` → `VerifierComparator`（mode=`consistency` | `cosine`）
- `parser/caffe_parser.py::CaffeParser` — Caffe 模型解析（不走 `HBRuntime`）

### 工具函数（`utils/tool_utils.py`）

- `import_from(package, symbol, version_spec, package_name)` — 懒加载 + 版本校验
- `init_root_logger(name, level)` — rolling log（1 MB × 10）到 `<cwd>/<name>.log`
- `on_exception_exit(fn)` — CLI 装饰器，DEBUG 打印 traceback 并以 `-1` 退出
- `get_march_list()` — 优先 `hbdk4.march.get_all_bpu_march_names()`，回退 `mapper_consts.march_list`
- `get_list_from_txt` / `get_str_from_list` — 分号分隔字符串 ↔ list
- `verify_ssh_connection(...)` — paramiko SSH 校验
- `get_ip()` / `print_table(...)` / `update_yaml(...)`

## 常用查询映射

| 用户意图 | 推荐搜索关键词 | 说明 |
|---|---|---|
| CLI 入口列表 | `console_scripts`, `entry_points.txt` | 6 个 `hb_*` 命令 |
| 编译流水线/编译模式 | `hb_compile`, `onnx_config_mode`, `fast_perf_mode`, `bc_config_mode`, `check_mode` | 由 `-c`/`-m`/`--fast-perf` 组合决定 |
| YAML 配置生成 | `hb_config_generator`, `ConfigGenerator`, `simple_template.yaml`, `full_template.yaml` | 生成编译模板 |
| 参数 schema/默认值 | `schema_yaml`, `ParamsParser`, `ConfigInfo` | 配置单一来源 + 解析 |
| 量化/校准 (PTQ) | `PTQModelBuilder`, `ptq_model_build`, `calibration_model` | 校准流水线 |
| 编译成 .hbm | `HBMBuilder`, `hbm_build_from_bc`, `compile/hbm_builder.py` | BPU 编译 + perf |
| 模型信息/依赖查询 | `hb_model_info`, `deps info`, `removable node` | 模型元数据 |
| 模型可视化 (Netron) | `Visualize`, `start_server`, `netron`, `.bc`, `.hbm` | 启动可视化服务器 |
| 模型分析 (perf JSON) | `HBAnalyzer`, `analyze`, `JsonParser`, `AnalysisPrinter` | 模型 + perf 分析 |
| 推理/验证 (simulator + 板端) | `hb_verifier`, `VerifierInference`, `VerifierComparator` | 输出一致性/余弦比对 |
| 余弦相似度比对 | `cosine_similarity`, `consistency`, `VerifierComparator.run` | 精度比对模式 |
| 数据集预处理 (eval) | `hb_eval_preprocess`, `EvalPreprocess`, `MODEL_DICT` | ImageNet/COCO/CIFAR/VOC |
| DataLoader / 数据加载 | `data_loader_factory`, `DataLoader`, `dataset_loader`, `raw_data_reader` | 校准数据加载 |
| Caffe 模型解析 | `CaffeParser`, `horizon_caffe_pb2`, `caffe_parser` | Caffe 专用路径 |
| ONNX 模型解析 | `onnx_parser`, `HB_ONNXRuntime` | ONNX 处理 |
| Runtime 分发 | `HBRuntime`, `HB_ONNXRuntime`, `HB_HBIRRuntime`, `HB_HBMRuntime` | 按文件后缀分发 |
| HBIR 图改写 / advice | `HBIRHandle`, `hbir_handle`, `quantize advice` | 依赖 `hbdk4.compiler` |
| HBM 操作 | `HBMHandle`, `hbm_handle`, `visualize` | 已编译模型 |
| SSH 板端连接 | `paramiko`, `verify_ssh_connection`, `board_ip`, `remote_root` | verifier/analyzer 共用 |
| 日志配置 | `init_root_logger`, `init_tool_logger`, `log_format`, `<name>.log` | rolling 1MB×10 |
| CLI 异常处理 | `on_exception_exit`, `@on_exception_exit` | 装饰器 |
| march / 目标架构 | `march_list`, `get_march_list()`, `nash-b`, `nash-p`, `core_num_range` | BPU 架构枚举 |
| 懒加载 + 版本校验 | `import_from`, `hbdk4.compiler`, `hmct.api` | 必须用 `import_from` |
| 分号分隔参数 | `get_list_from_txt`, `get_str_from_list` | 多值参数编码 |
| YAML 构建辅助 | `YamlBuilder`, `yaml_builder`, `update_yaml` | fast-perf 自动生成 YAML |
| 隐藏产物目录 | `.hb_model_info/`, `.hb_analyzer/` | analyzer/model_info 默认写到这里 |
| 编译日志复制 | `copy_compile_log_file`, `hb_compile.log` | 拷贝到 `conf.working_dir` |
| 表格打印 | `print_table`, `tool_utils` | CLI 输出格式化 |
| ConfigInfo 字段访问 | `conf.get(name, default)`, `conf[name]`, `ConfigBase` | 统一访问方式 |
| 自定义算子模板 | `sample_custom.py`, `custom_op`, `template/` | 自定义算子配置样本 |
| 颜色输出 | `colour.py`, `RCS`, `GCS`, `YCS`, `ENDING` | ANSI 着色常量 |

## 规则与约定

- **懒加载 import**：`hbdk4` / `hmct` 必须通过 `utils/tool_utils.py::import_from(package, symbol, version_spec, package_name)` 获取，**禁止**在模块顶层直接 `import hbdk4` / `import hmct`。
- **CLI 装饰器模式**：每个 Click 命令都用 `@on_exception_exit` 包裹；命令体内第一件事必须是 `init_root_logger("<tool_name>")`。
- **日志文件**：`init_root_logger` 在 cwd 写 `<name>.log`（rolling，1 MB × 10）；`hb_compile` 额外把 `hb_compile.log` 拷贝到 `conf.working_dir`。
- **隐藏产物目录**：`hb_model_info` → `.hb_model_info/`；`hb_analyzer` → `.hb_analyzer/`。
- **`ConfigInfo` 访问**：优先 `conf.get(name, default)` 或 `conf[name]`（定义在 `ConfigBase`）。
- **多值参数**：以分号分隔字符串 `"a;b;c"` 形式编码，用 `get_list_from_txt` / `get_str_from_list` 互转。
- **SSH 访问**：verifier/analyzer 通过 `paramiko`；统一用 `tool_utils.verify_ssh_connection`。
- **目标架构**：`--march` 取 Nash 家族；仅 `nash-h`/`nash-p`/`nash-starry-p` 支持 `core_num > 1`（详见 `mapper_consts.core_num_range`）。
- **Caffe 模型**：不走 `HBRuntime`，经由 `parser/caffe_parser.py`。
- **版本约束**：`hbdk4_compiler >= 4.0.22`；`onnx==1.15.0`；`numpy==1.23.0` (py3.10) / `1.24.2` (py3.11)。
- **本包是预编译 wheel**：目录中没有 build/test/lint 配置；CLAUDE.md 已包含完整架构指引，建议优先阅读。
