# HMCT 精度 Debug 工具参考文档

HMCT 提供了一套精度调试工具，用于分析量化模型的精度损失来源。支持**命令行（CLI）**和 **Python API** 两种使用方式。

---

## 目录

- [1. runall — 一键运行全部调试功能](#1-runall--一键运行全部调试功能)
- [2. get_sensitivity_of_nodes — 节点灵敏度分析](#2-get_sensitivity_of_nodes--节点灵敏度分析)
- [3. plot_distribution — 数据分布可视化](#3-plot_distribution--数据分布可视化)
- [4. get_channelwise_data_distribution — 逐通道数据分布](#4-get_channelwise_data_distribution--逐通道数据分布)
- [5. plot_acc_error — 累积误差可视化](#5-plot_acc_error--累积误差可视化)
- [6. sensitivity_analysis — 灵敏度分析](#6-sensitivity_analysis--灵敏度分析)
- [7. tensor_analysis — 张量分析](#7-tensor_analysis--张量分析)
---

## 1. runall — 一键运行全部调试功能

依次执行节点灵敏度分析、数据分布可视化、逐通道数据分布、累积误差可视化和灵敏度分析，结果保存到指定目录。

### CLI

```bash
hmct-debugger runall <model_or_file> <calibrated_data> [OPTIONS]
```

**必选参数：**

| 参数 | 说明 |
|------|------|
| `model_or_file` | 校准后的模型文件路径 |
| `calibrated_data` | 校准数据路径 |

**可选参数：**

| 短选项 | 长选项 | 类型 | 默认值 | 说明 |
|--------|--------|------|--------|------|
| `-s` | `--save_dir` | str | `./debug_result/` | 结果保存路径 |
| `-nm` | `--ns_metrics` | str | `cosine-similarity` | 节点灵敏度计算方法 |
| `-o` | `--output_node` | str | None | 用于计算灵敏度的输出节点 |
| `-nt` | `--node_type` | str | None | 计算灵敏度的节点类型，默认 `["weight", "activation"]` |
| `-dn` | `--data_num` | int | 1 | 计算灵敏度所需的数据量 |
| `-v` | `--verbose` | bool | False | 是否在终端显示灵敏度信息 |
| `-i` | `--interested_nodes` | str | None | 参与灵敏度排序的节点，默认全部参与 |
| `-dnl` | `--dis_nodes_list` | str | None | 需要绘制分布的节点列表 |
| `-cn` | `--cw_nodes_list` | str | None | 需要绘制逐通道分布的节点列表 |
| `-a` | `--axis` | int | None | 通道维度索引 |
| `-qn` | `--quantize_node` | str | None | 设置量化的节点 |
| `-nqn` | `--non_quantize_node` | str | None | 设置不量化的节点 |
| `-am` | `--ae_metric` | str | `cosine-similarity` | 累积误差计算方法 |
| `-avm` | `--average_mode` | bool | False | 是否计算累积误差的均值 |
| `-pt` | `--pick_threshold` | float | 0.999 | 筛选敏感节点的阈值 |
| `-sn` | `--sensitive_nodes` | str | None | 指定敏感节点 |

**示例：**

```bash
hmct-debugger runall calibrated_model.onnx ./cali_data/ -s ./my_debug/ -dn 4 -v True
```

### Python API

```python
from hmct.quantizer.debugger import runall

runall(
    model_or_file: str,
    calibrated_data: Union[str, Dataset],
    save_dir: str = "./debug_result/",
    ns_metrics: Union[str, List[str]] = "cosine-similarity",
    output_node: Optional[str] = None,
    node_type: Optional[str] = None,
    data_num: int = 1,
    verbose: bool = False,
    interested_nodes: Optional[Union[str, List[str]]] = None,
    dis_nodes_list: Optional[Union[List[str], str]] = None,
    cw_nodes_list: Optional[Union[List[str], str]] = None,
    axis: Optional[int] = None,
    quantize_node: Optional[Union[List[str], str]] = None,
    non_quantize_node: Optional[Union[List[str], str]] = None,
    ae_metric: str = "cosine-similarity",
    average_mode: bool = False,
    pick_threshold: float = 0.999,
    sensitive_nodes: Optional[list] = None,
)
```

**示例：**

```python
from hmct.quantizer.debugger import runall

runall(
    model_or_file="calibrated_model.onnx",
    calibrated_data="./cali_data/",
    save_dir="./my_debug/",
    data_num=4,
    verbose=True,
)
```

**输出目录结构：**

```
<save_dir>/
├── node_sensitivity/          # 节点灵敏度结果
│   ├── sensitivity_of_weight.log
│   └── sensitivity_of_activation.log
├── data_distribution/         # 数据分布图
├── channelwise_distribution/  # 逐通道分布图
├── accumulate_error/          # 累积误差图
└── sensitivity_analysis/      # 灵敏度分析结果
```

> **注意：** `non_quantize_node` 不能设置为 `"weight"` 或 `"activation"`，否则会抛出 `ValueError`。

---

## 2. get_sensitivity_of_nodes — 节点灵敏度分析

计算每个节点对模型量化精度的灵敏度，按灵敏度排序输出，帮助定位精度损失最大的节点。

### CLI

```bash
hmct-debugger get-sensitivity-of-nodes <model_or_file> <calibrated_data> [OPTIONS]
```

**必选参数：**

| 参数 | 说明 |
|------|------|
| `model_or_file` | 校准后的模型文件路径 |
| `calibrated_data` | 校准数据路径 |

**可选参数：**

| 短选项 | 长选项 | 类型 | 默认值 | 说明 |
|--------|--------|------|--------|------|
| `-m` | `--metrics` | str | `cosine-similarity` | 灵敏度计算方法 |
| `-o` | `--output_node` | str | None | 用于计算灵敏度的输出节点 |
| `-n` | `--node_type` | choice | `node` | 节点类型，可选 `node`、`weight`、`activation` |
| `-d` | `--data_num` | int | 1 | 计算灵敏度所需的数据量 |
| `-v` | `--verbose` | bool | False | 是否在终端显示灵敏度信息 |
| `-i` | `--interested_nodes` | str | None | 参与灵敏度排序的节点 |
| `-s` | `--save_dir` | str | None | 结果保存路径 |

**示例：**

```bash
hmct-debugger get-sensitivity-of-nodes calibrated_model.onnx ./cali_data/ \
    -m cosine-similarity -n weight -d 4 -v True -s ./sensitivity_result/
```

### Python API

```python
from hmct.quantizer.debugger import get_sensitivity_of_nodes

result = get_sensitivity_of_nodes(
    model_or_file: Union[ModelProto, str],
    metrics: Union[List[str], str] = "cosine-similarity",
    calibrated_data: Optional[Union[str, Dataset]] = None,
    output_node: Optional[str] = None,
    node_type: str = "node",
    data_num: int = 1,
    verbose: bool = False,
    interested_nodes: Optional[Union[str, List[str], List[List[str]]]] = None,
    save_dir: Optional[str] = None,
) -> Dict[str, Dict[str, str]]
```

**返回值：** `Dict[str, Dict[str, str]]` — 按灵敏度排序的字典，键为节点名，值为各指标的灵敏度得分。

**示例：**

```python
from hmct.quantizer.debugger import get_sensitivity_of_nodes

result = get_sensitivity_of_nodes(
    model_or_file="calibrated_model.onnx",
    calibrated_data="./cali_data/",
    metrics=["cosine-similarity"],
    node_type="weight",
    data_num=4,
    verbose=True,
    save_dir="./sensitivity_result/",
)

for node_name, scores in result.items():
    print(f"{node_name}: {scores}")
```

**`node_type` 说明：**

| 值 | 说明 |
|----|------|
| `node` | 以整个算子节点为单位计算灵敏度 |
| `weight` | 以权重校准节点为单位计算灵敏度 |
| `activation` | 以激活校准节点为单位计算灵敏度 |

> **注意：** 当指定 `interested_nodes` 时，`node_type` 会被自动重置为 `"node"`。

---

## 3. plot_distribution — 数据分布可视化

绘制指定节点的量化前后数据分布对比图，直观展示量化对数据分布的影响。

### CLI

```bash
hmct-debugger plot-distribution <model_or_file> <calibrated_data> -n <nodes_list> [OPTIONS]
```

**必选参数：**

| 参数 | 说明 |
|------|------|
| `model_or_file` | 校准后的模型文件路径 |
| `calibrated_data` | 校准数据路径 |
| `-n` / `--nodes_list` | 需要绘制分布的节点列表（必选） |

**可选参数：**

| 短选项 | 长选项 | 类型 | 默认值 | 说明 |
|--------|--------|------|--------|------|
| `-s` | `--save_dir` | str | `./debug_result/` | 结果保存路径 |

**示例：**

```bash
hmct-debugger plot-distribution calibrated_model.onnx ./cali_data/ \
    -n "[conv1_weight,conv2_weight]" -s ./distribution/
```

### Python API

```python
from hmct.quantizer.debugger import plot_distribution

plot_distribution(
    model_or_file: Union[ModelProto, str],
    calibrated_data: Union[str, Dataset],
    nodes_list: Union[List[str], str],
    save_dir: str = "./debug_result/",
)
```

**示例：**

```python
from hmct.quantizer.debugger import plot_distribution

plot_distribution(
    model_or_file="calibrated_model.onnx",
    calibrated_data="./cali_data/",
    nodes_list=["conv1_weight", "conv2_weight"],
    save_dir="./distribution/",
)
```

---

## 4. get_channelwise_data_distribution — 逐通道数据分布

获取指定节点在各通道上的数据分布情况，用于分析是否存在通道间分布不均匀的问题。

### CLI

```bash
hmct-debugger get-channelwise-data-distribution <model_or_file> <calibrated_data> \
    -n <nodes_list> [OPTIONS]
```

**必选参数：**

| 参数 | 说明 |
|------|------|
| `model_or_file` | 校准后的模型文件路径 |
| `calibrated_data` | 校准数据路径 |
| `-n` / `--nodes_list` | 需要分析的节点列表（必选） |

**可选参数：**

| 短选项 | 长选项 | 类型 | 默认值 | 说明 |
|--------|--------|------|--------|------|
| `-s` | `--save_dir` | str | `./debug_result/` | 结果保存路径 |
| `-a` | `--axis` | int | None | 通道维度索引 |

**示例：**

```bash
hmct-debugger get-channelwise-data-distribution calibrated_model.onnx ./cali_data/ \
    -n "[conv1_weight,conv2_weight]" -a 0 -s ./channelwise/
```

### Python API

```python
from hmct.quantizer.debugger import get_channelwise_data_distribution

get_channelwise_data_distribution(
    model_or_file: Union[ModelProto, str],
    calibrated_data: Union[str, Dataset],
    nodes_list: List[str],
    axis: Optional[int] = None,
    save_dir: str = "./debug_result/",
)
```

**示例：**

```python
from hmct.quantizer.debugger import get_channelwise_data_distribution

get_channelwise_data_distribution(
    model_or_file="calibrated_model.onnx",
    calibrated_data="./cali_data/",
    nodes_list=["conv1_weight", "conv2_weight"],
    axis=0,
    save_dir="./channelwise/",
)
```

---

## 5. plot_acc_error — 累积误差可视化

逐层累积量化误差并可视化，帮助定位误差传播和累积的关键路径。

### CLI

```bash
hmct-debugger plot-acc-error <model_or_file> <calibrated_data> [OPTIONS]
```

**必选参数：**

| 参数 | 说明 |
|------|------|
| `model_or_file` | 校准后的模型文件路径 |
| `calibrated_data` | 校准数据路径 |

**可选参数：**

| 短选项 | 长选项 | 类型 | 默认值 | 说明 |
|--------|--------|------|--------|------|
| `-s` | `--save_dir` | str | `./debug_result/` | 结果保存路径 |
| `-q` | `--quantize_node` | str | None | 设置需要量化的节点 |
| `-nq` | `--non_quantize_node` | str | None | 设置不量化的节点 |
| `-m` | `--metric` | str | `cosine-similarity` | 累积误差计算方法 |
| `-a` | `--average_mode` | bool | False | 是否计算累积误差的均值 |

**示例：**

```bash
hmct-debugger plot-acc-error calibrated_model.onnx ./cali_data/ \
    -q "[weight,activation]" -m cosine-similarity -s ./acc_error/
```

### Python API

```python
from hmct.quantizer.debugger import plot_acc_error

plot_acc_error(
    calibrated_data: Union[str, Dataset],
    model_or_file: Union[ModelProto, str],
    quantize_node: Optional[Union[List[str], str]] = None,
    non_quantize_node: Optional[Union[List[str], str]] = None,
    metric: str = "cosine-similarity",
    average_mode: bool = False,
    save_dir: str = "./debug_result/",
)
```

**示例：**

```python
from hmct.quantizer.debugger import plot_acc_error

plot_acc_error(
    calibrated_data="./cali_data/",
    model_or_file="calibrated_model.onnx",
    quantize_node=["weight", "activation"],
    metric="cosine-similarity",
    save_dir="./acc_error/",
)
```

> **注意：** `non_quantize_node` 不能设置为 `"weight"` 或 `"activation"`，否则会抛出 `ValueError`。

---

## 6. sensitivity_analysis — 灵敏度分析

对敏感节点进行深入分析，自动或手动指定敏感节点，评估将其设置为指定量化类型后的精度变化。

### CLI

```bash
hmct-debugger sensitivity-analysis <model_or_file> <calibrated_data> [OPTIONS]
```

**必选参数：**

| 参数 | 说明 |
|------|------|
| `model_or_file` | 校准后的模型文件路径 |
| `calibrated_data` | 校准数据路径 |

**可选参数：**

| 短选项 | 长选项 | 类型 | 默认值 | 说明 |
|--------|--------|------|--------|------|
| `-m` | `--metric` | str | `cosine-similarity` | 灵敏度计算指标 |
| `-p` | `--pick_threshold` | float | 0.999 | 筛选敏感节点的阈值 |
| `-d` | `--data_num` | int | 1 | 计算灵敏度所需的数据量 |
| `-sn` | `--sensitive_nodes` | str | None | 指定敏感节点列表 |
| `-q` | `--qtype` | str | `float32` | 敏感节点设置的量化类型 |
| `-sd` | `--save_dir` | str | `./debug_result/` | 结果保存路径 |

**示例：**

```bash
hmct-debugger sensitivity-analysis calibrated_model.onnx ./cali_data/ \
    -p 0.998 -d 4 -q float32 -sd ./sensitivity/
```

### Python API

```python
from hmct.quantizer.debugger import sensitivity_analysis

result = sensitivity_analysis(
    model_or_file: Union[ModelProto, str],
    calibrated_data: Union[Dataset, str],
    metric: str = "cosine-similarity",
    pick_threshold: float = 0.999,
    data_num: int = 1,
    sensitive_nodes: Optional[Sequence[str]] = None,
    qtype: str = "float32",
    output_separated: bool = False,
    save_dir: str = "./debug_result/",
) -> Mapping[str, Union[Dict[str, float], float]]
```

**返回值：** `Mapping[str, Union[Dict[str, float], float]]` — 灵敏度分析结果。

**示例：**

```python
from hmct.quantizer.debugger import sensitivity_analysis

result = sensitivity_analysis(
    model_or_file="calibrated_model.onnx",
    calibrated_data="./cali_data/",
    pick_threshold=0.998,
    data_num=4,
    qtype="float32",
    save_dir="./sensitivity/",
)
```

> **注意：** 若未指定 `sensitive_nodes`，API 会自动调用 `get_sensitivity_of_nodes` 计算灵敏度，并根据 `pick_threshold` 自动筛选敏感节点。`output_separated` 参数仅在 API 中可用。

---

## 7. tensor_analysis — 张量分析

对指定节点进行张量级别的详细分析，支持多进程并行加速。

### CLI

```bash
hmct-debugger tensor-analysis <model_or_file> <calibration_data> -n <node_names> [OPTIONS]
```

**必选参数：**

| 参数 | 说明 |
|------|------|
| `model_or_file` | 校准后的模型文件路径 |
| `calibration_data` | 校准数据路径 |
| `-n` / `--node_names` | 需要分析的节点名称（必选） |

**可选参数：**

| 短选项 | 长选项 | 类型 | 默认值 | 说明 |
|--------|--------|------|--------|------|
| `-s` | `--save_dir` | str | `./debug_result/` | 结果保存路径 |
| `-np` | `--num_processes` | int | 16 | 并行进程数 |

**示例：**

```bash
hmct-debugger tensor-analysis calibrated_model.onnx ./cali_data/ \
    -n "[conv1,conv2]" -np 8 -s ./tensor/
```

### Python API

```python
from hmct.quantizer.debugger import tensor_analysis

tensor_analysis(
    model_or_file: Union[str, ModelProto, OnnxModel],
    calibration_data: Union[str, Dataset],
    node_names: Union[str, Sequence[str]],
    save_dir: str = "./debug_result/",
    num_processes: int = 16,
) -> None
```

**示例：**

```python
from hmct.quantizer.debugger import tensor_analysis

tensor_analysis(
    model_or_file="calibrated_model.onnx",
    calibration_data="./cali_data/",
    node_names=["conv1", "conv2"],
    save_dir="./tensor/",
    num_processes=8,
)
```

> **注意：** 该函数在模块中导出时名为 `tensor_analysis`（`__init__.py` 中 `tensor_analysis_api as tensor_analysis`）。

---

## 列表参数格式说明

CLI 中多个节点名或指标以列表形式传入时，支持以下格式：

```bash
# 简单列表
-n "[conv1,conv2,conv3]"

# 带引号的列表
-n "['conv1','conv2']"

# 嵌套列表
-i "[[conv1,conv2],[conv3]]"
```

Python API 中直接传入 Python 列表即可：

```python
nodes_list=["conv1", "conv2", "conv3"]
```

---

## 推荐调试流程

```
1. 运行 get_sensitivity_of_nodes 获取节点灵敏度排序
       ↓
2. 对灵敏度较差的节点，运行 plot_distribution 查看数据分布
       ↓
3. 运行 get_channelwise_data_distribution 检查通道间分布是否均匀
       ↓
4. 运行 plot_acc_error 定位误差累积路径
       ↓
5. 运行 sensitivity_analysis 对敏感节点设置高精度量化类型
```

或直接使用 `runall` 一键执行上述全部步骤。
