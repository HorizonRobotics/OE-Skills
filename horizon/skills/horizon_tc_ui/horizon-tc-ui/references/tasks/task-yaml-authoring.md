# 从零编写编译配置 YAML

## 适用场景

**触发关键词**：写 yaml、生成配置、编译配置、模板、config generator

**前置条件**：
- 已安装 `horizon_tc_ui` 工具包
- 已有待编译的模型文件（`.onnx` 或 `.caffemodel` + `.prototxt`）
- 已确认目标芯片架构（march）

## 产出物

| 产出文件 | 命名规则 | 说明 |
|---------|---------|------|
| `simple_compile_config.yaml` | 固定名 | 精简模板，仅包含必填参数 |
| `full_compile_config.yaml` | 固定名 | 完整模板，包含所有常用参数 |

> **注意**：生成的文件名是固定的（`{generate_type}_compile_config.yaml`），生成后建议重命名为项目相关名称。

## 步骤

### 步骤 1：使用 hb_config_generator 生成模板

hb_config_generator 支持两种模板类型：

**生成 simple 模板**（最小配置，适合快速验证）：
```bash
hb_config_generator -s -m model.onnx --march nash-e
```

**生成 full 模板**（完整配置，适合生产使用）：
```bash
hb_config_generator -f -m model.onnx --march nash-e
```

> **注意**：`fast_perf_template.yaml` 模板由 `hb_compile --fast-perf` 内部自动使用，不通过 `hb_config_generator` 直接生成。

**参数说明**：
- `-s` / `--simple-yaml`：生成精简模板
- `-f` / `--full-yaml`：生成完整模板
- `-m` / `--model`：模型文件路径（可选，提供后会自动填充模型信息）
- `-p` / `--proto`：Caffe 模型的 prototxt 文件（Caffe 模型必填）
- `--march`：目标 BPU 架构，可选值见下方 march 列表

**Caffe 模型示例**：
```bash
hb_config_generator -f -m model.caffemodel -p model.prototxt --march nash-e
```

**march 可选值**（官方文档及 CLI 帮助）：
- `nash-b-lite`, `nash-b`, `nash-b-plus`, `nash-e`, `nash-m`, `nash-p`, `nash-h`

### 步骤 2：根据场景选择模板骨架

hb_config_generator 生成的模板是通用模板。根据任务类别，可参考以下骨架快速调整：

| 任务类别 | 推荐模板 | 关键配置特点 |
|---------|---------|------------|
| 分类模型 | simple / full | 单输入，`input_type_rt: nv12`, `input_type_train: bgr` |
| 检测模型 | full | 可能需要多尺度、较大校准样本量 |
| 分割模型 | full | 高分辨率，内存敏感的 compiler 参数 |
| 多输入模型 | full | `input_name` / `input_shape` / `input_type_*` 使用分号分隔列表 |
| 快速性能评估 | fast_perf_template | `optimization: run_fast`, `optimize_level: O2` |

**simple 模板内容**（最小配置）：
```yaml
model_parameters:
  working_dir: .hb_compile
input_parameters:
  input_name: ''
  input_shape: ''
  input_space_and_range: ''
  input_type_rt: featuremap
  input_type_train: featuremap
compiler_parameters:
  compile_mode: latency
  core_num: 1
  jobs: 32
  max_time_per_fc: 0
  optimize_level: O0
```

**full 模板内容**（完整配置）：
```yaml
model_parameters:
  onnx_model: ''
  caffe_model: ''
  prototxt: ''
  march: ''
  working_dir: ./model_output
  output_model_file_prefix: model
  output_nodes: ''
  remove_node_type: ''
  remove_node_name: ''
  debug_mode: ''
input_parameters:
  input_name: ''
  input_type_rt: 'nv12'
  input_type_train: 'bgr'
  input_layout_train: 'NCHW'
  input_shape: ''
  separate_batch: false
  mean_value: ''
  scale_value: ''
  std_value: ''
calibration_parameters:
  cal_data_dir: ./calibration_data_dir
  quant_config: {}
compiler_parameters:
  compile_mode: latency
  optimize_level: O2
  core_num: 1
  max_time_per_fc: 0
  jobs: 16
  input_source: {}
  advice: 0
  balance_factor: 0
  cache_path: ""
  cache_mode: disable
```

### 步骤 3：根据输入场景修改关键参数

**单输入 - 图像模型（最常见）**：
```yaml
input_parameters:
  input_name: 'data'          # 模型输入节点名
  input_type_rt: 'nv12'       # 推理时输入格式
  input_type_train: 'bgr'     # 训练时输入格式
  input_layout_train: 'NCHW'  # 训练时数据布局
  input_shape: '1x3x224x224'  # 输入 shape
  mean_value: '123.675 116.28 103.53'  # 均值（可选，空格分隔各通道值）
  scale_value: '0.0171 0.0175 0.0174'  # 缩放（可选，空格分隔各通道值）
```

**多输入模型**（使用分号分隔多个值）：
```yaml
input_parameters:
  input_name: 'input0;input1'
  input_type_rt: 'nv12;featuremap'
  input_type_train: 'bgr;featuremap'
  input_layout_train: 'NCHW;NCHW'
  input_shape: '1x3x224x224;1x256'
```

**featuremap 输入**（无图像预处理）：
```yaml
input_parameters:
  input_type_rt: 'featuremap'
  input_type_train: 'featuremap'
  # featuremap 不需要 mean_value / scale_value / std_value
```

### 关于 input_source 的显式声明

当用户明确指定了输入数据来源（如 `resizer`）时，必须在 YAML 的 `compiler_parameters` 中**显式写入 `input_source` 字段**，不要依赖默认自动推导。

```yaml
compiler_parameters:
  input_source:
    data: resizer    # 显式声明，而非留空依赖默认值
```

默认推导规则：`input_type_rt` 属于 pyramid 支持列表时默认 `pyramid`，否则默认 `ddr`。如果用户实际期望使用 `resizer`，不显式写入会导致编译器自动选择 `pyramid`，与预期不符。

### 关于 input_type_train 与前处理代码的一致性

`input_type_train` 描述的是**训练阶段模型接收的数据格式**，必须与训练前处理代码中的实际数据格式一致。在生成或修改 YAML 时，应主动提醒用户核对这一点：

- 训练代码中图片以 **BGR** 格式送入模型 → `input_type_train: 'bgr'`
- 训练代码中图片以 **RGB** 格式送入模型 → `input_type_train: 'rgb'`
- 不一致会导致编译器的色彩空间转换与训练时错位，影响精度

常见风险场景：
- 用户从 PyTorch 训练迁移（通常用 RGB），但模板默认 `input_type_train: 'bgr'`
- 使用了 OpenCV 读取图片（默认 BGR），但训练框架配置写了 RGB

> 建议用户使用 `hb_model_info model.onnx` 确认模型的输入节点信息，并对照训练代码的前处理逻辑检查。

### 步骤 4：使用 validate_yaml.py 预检

> **注意**：validate_yaml.py 脚本位于 `horizon_tc_ui/scripts/` 目录下（规划中）。当前可直接使用 `hb_compile -c config.yaml` 进行参数校验，校验失败会抛出详细错误信息。

```bash
# 方式一：使用 hb_compile 校验（当前推荐）
hb_compile -c your_config.yaml --skip export

# 方式二：使用 Python 直接调用 ParamsParser（调试用）
python3 -c "
from horizon_tc_ui.config.params_parser import ParamsParser
parser = ParamsParser('your_config.yaml')
parser.validate_parameters()
print('YAML 校验通过')
"
```

### 步骤 5：校验与确认

```bash
# 确认生成的 yaml 内容
cat simple_compile_config.yaml

# 使用 hb_model_info 确认模型输入信息匹配
hb_model_info model.onnx
```

## 校验清单

- [ ] yaml 文件中 `model_parameters.onnx_model` 或 `caffe_model + prototxt` 已正确填写且文件存在
- [ ] `march` 值在合法列表中（`nash-b-lite`, `nash-b`, `nash-b-plus`, `nash-e`, `nash-m`, `nash-p`, `nash-h`）
- [ ] `input_name` 与模型实际输入节点名一致（可通过 `hb_model_info model.onnx` 确认）
- [ ] `input_shape` 格式正确（如 `1x3x224x224`），维度与模型匹配
- [ ] `input_type_rt` 和 `input_type_train` 的组合合法（参见 `mapper_consts.legal_trans_dict`）
- [ ] `input_type_train` 与训练前处理代码中的数据格式一致（BGR vs RGB 等，对照训练代码检查）
- [ ] 用户指定了 `input_source`（如 `resizer`）时，已在 `compiler_parameters` 中显式写入 `input_source` 字段，未依赖默认推导
- [ ] 多输入模型时，所有列表参数数量与输入节点数一致
- [ ] `cal_data_dir` 目录存在且包含校准数据（非 skip 模式时）
- [ ] `working_dir` 目录已创建或可自动创建
- [ ] `output_model_file_prefix` 非空
- [ ] `optimize_level` 在合法范围内（`O0`, `O1`, `O2`）
- [ ] `core_num` 与 march 匹配（如 `nash-h` 支持 1-4，`nash-b` 仅支持 1）

## 常见偏差与修法

| 偏差 | 修法 | 对应 troubleshooting |
|-----|------|---------------------|
| `input_name` 与模型不匹配 | 使用 `hb_model_info model.onnx` 查看真实输入名 | yaml-schema-errors.md |
| `input_type_rt` 和 `input_type_train` 组合不合法 | 参考 `legal_trans_dict` 选择合法组合 | yaml-schema-errors.md |
| `input_type_train` 与训练前处理不一致 | 对照训练代码，确认 BGR/RGB 等格式后修正 | yaml-schema-errors.md |
| 用户指定了 `input_source: resizer` 但未显式写入 YAML | 在 `compiler_parameters` 中显式写入 `input_source` 字典 | compile-errors.md |
| 多输入模型参数数量不匹配 | 确保分号分隔的值数量等于输入节点数 | yaml-schema-errors.md |
| `march` 值不合法 | 使用 `hb_config_generator --march` 查看可选值 | compile-errors.md |
| `nv12` 输入但 shape 有奇数维度 | nv12 不支持奇数宽高，调整为偶数 | yaml-schema-errors.md |
| `featuremap` 输入但配置了 mean/scale | featuremap 不支持归一化参数，删除即可 | yaml-schema-errors.md |
| `scale_value` 和 `std_value` 同时指定 | 只能二选一 | yaml-schema-errors.md |
| `separate_batch` 和 `separate_name` 同时使用 | 二者互斥，只能选一个 | yaml-schema-errors.md |

## 相关工具 / 模块链接

- **hb_config_generator**：模板生成工具，源码入口 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/hb_config_generator.py`
- **ParamsParser**：YAML 参数校验，源码入口 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/config/params_parser.py`
- **schema_yaml**：YAML Schema 定义，源码入口 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/config/schema_yaml.py`
- **mapper_consts**：常量定义（合法值列表、转换关系等），源码入口 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/config/mapper_consts.py`
- **hb_model_info**：模型信息查看 → `task-model-inspection.md`
- **模板文件**：`/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/template/`
  - `simple_template.yaml` - 精简模板
  - `full_template.yaml` - 完整模板
  - `fast_perf_template.yaml` - 快速性能评估模板
  - `check_template.yaml` - 检查模式模板
