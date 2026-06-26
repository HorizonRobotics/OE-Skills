# HMCT 模型构建工具参考文档

HMCT 提供 `build_model` 和 `check_model` 两个核心函数，用于将 ONNX/Caffe 模型转换为量化混合模型。

---

## 目录

- [1. build_model — 模型量化构建](#1-build_model--模型量化构建)
- [2. check_model — 快速验证模型转换](#2-check_model--快速验证模型转换)
- [3. 使用示例](#3-使用示例)

---

## 1. build_model — 模型量化构建

将 ONNX 模型进行量化校准和编译，生成可部署的量化模型。

### 函数签名

```python
from hmct.api import build_model

result = build_model(
    onnx_model: Optional[ModelProto] = None,
    march: str = "nash",
    cali_data: Optional[Union[Sequence[np.ndarray], Dict[str, Sequence[np.ndarray]]]] = None,
    quant_config: Optional[Union[str, Dict[str, Any]]] = None,
    input_dict: Optional[Dict[str, Any]] = None,
    name_prefix: Optional[str] = None,
    verbose: Optional[bool] = True,
    **kwargs,
) -> Union[ModelBuilder, ModelProto, None]
```

### 参数说明

#### 主要参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `onnx_model` | ModelProto / None | None | ONNX 模型对象。与 `onnx_file` 二选一 |
| `march` | str | `"nash"` | BPU 芯片架构 |
| `cali_data` | Sequence[ndarray] / Dict / None | None | 校准数据 |
| `quant_config` | str / Dict / None | None | 量化配置，可以是 JSON 文件路径或字典 |
| `input_dict` | Dict / None | None | 模型输入相关参数，键为输入节点名 |
| `name_prefix` | str / None | None | 输出模型名称或路径前缀 |
| `verbose` | bool | True | 是否打印模型量化信息 |

#### kwargs 扩展参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `onnx_file` | str | None | ONNX 模型文件路径（与 `onnx_model` 二选一） |
| `prototxt_file` | str | None | Caffe prototxt 文件路径 |
| `caffemodel_file` | str | None | Caffe 模型文件路径 |
| `cali_dict` | Dict | None | 校准相关参数字典 |
| `output_nodes` | List[str] | None | 指定模型输出节点名列表，会替换原始输出 |
| `node_dict` | Dict | None | 节点相关参数，键为节点名，值为对该节点的操作列表 |
| `debug_methods` | List | None | 模型编译时的调试方法列表 |
| `optimization_methods` | List | None | 模型编译的优化方法列表 |
| `return_builder` | bool | False | 是否返回完整的 ModelBuilder 对象 |
| `check_mode` | bool | False | 是否使用随机数据进行校准（快速验证模式） |
| `save_model` | bool | True | 是否保存构建过程中生成的模型文件 |

### march 可选值

| 值 | 说明 |
|----|------|
| `nash` | Nash 架构（默认） |
| `nash-b` | Nash-B 架构 |
| `nash-b-lite` | Nash-B-Lite 架构 |
| `nash-b-plus` | Nash-B-Plus 架构 |
| `nash-e` | Nash-E 架构 |
| `nash-m` | Nash-M 架构 |
| `nash-h` | Nash-H 架构 |
| `nash-p` | Nash-P 架构 |
| `expt` | 实验性架构 |

### 模型输入方式

`build_model` 支持三种模型输入方式（按优先级排序）：

1. **直接传入模型对象** — `onnx_model=model_proto`
2. **通过文件路径** — `onnx_file="model.onnx"`
3. **Caffe 模型** — 同时指定 `prototxt_file` 和 `caffemodel_file`

### 校准数据格式

**单输入模型** — 直接传入 ndarray 列表：

```python
cali_data = [np.random.randn(1, 3, 224, 224).astype(np.float32) for _ in range(50)]
```

**多输入模型** — 传入字典，键为输入节点名：

```python
cali_data = {
    "input_0": [np.random.randn(1, 3, 224, 224).astype(np.float32) for _ in range(50)],
    "input_1": [np.random.randn(1, 10).astype(np.float32) for _ in range(50)],
}
```

### 返回值

| 条件 | 返回值 |
|------|--------|
| `return_builder=False`（默认） | 量化后的 `ModelProto` 对象 |
| `return_builder=True` | `ModelBuilder` 对象（包含完整构建信息） |

---

## 2. check_model — 快速验证模型转换

使用随机数据快速验证模型转换流程是否成功，无需准备真实校准数据。

### 函数签名

```python
from hmct.api import check_model

result = check_model(
    onnx_model: ModelProto,
    march: str,
    input_dict: Optional[Dict[str, Any]] = None,
) -> ModelProto
```

### 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `onnx_model` | ModelProto | — | ONNX 模型对象（必选） |
| `march` | str | — | BPU 芯片架构（必选） |
| `input_dict` | Dict / None | None | 输入相关参数字典 |

### 返回值

经过模型转换流程后的量化模型（`ModelProto`）。

### 典型用途

- 验证模型结构是否支持目标 BPU 架构
- 在没有真实校准数据时快速检查转换流程
- CI/CD 流水线中的模型兼容性检查

---

## 3. 使用示例

### 示例 1：基础 build_model 使用

```python
import numpy as np
from hmct.api import build_model

# 单输入模型
cali_data = [np.random.randn(1, 3, 224, 224).astype(np.float32) for _ in range(50)]

ptq_model = build_model(
    onnx_file="model.onnx",
    march="nash-e",
    cali_data=cali_data,
    name_prefix="output/model",
)
```

### 示例 2：使用 quant_config

```python
from hmct.api import build_model

quant_config = {
    "model_config": {
        "all_node_type": "int8",
        "activation": {
            "calibration_type": "max",
        },
    },
}

ptq_model = build_model(
    onnx_file="model.onnx",
    march="nash-p",
    cali_data=cali_data,
    quant_config=quant_config,
    name_prefix="output/model",
)
```

### 示例 3：使用 quant_config JSON 文件

```python
from hmct.api import build_model

ptq_model = build_model(
    onnx_file="model.onnx",
    march="nash-p",
    cali_data=cali_data,
    quant_config="quant_config.json",
    name_prefix="output/model",
)
```

### 示例 4：check_model 快速验证

```python
import onnx
from hmct.api import check_model

onnx_model = onnx.load("model.onnx")
quant_model = check_model(onnx_model=onnx_model, march="nash-e")
print("Model check passed!")
```

### 示例 5：多输入模型 + 自定义节点配置

```python
import numpy as np
from hmct.api import build_model

cali_data = {
    "image": [np.random.randn(1, 3, 512, 512).astype(np.float32) for _ in range(30)],
    "mask":  [np.random.randn(1, 1, 512, 512).astype(np.float32) for _ in range(30)],
}

quant_config = {
    "model_config": {
        "all_node_type": "int8",
    },
    "node_config": {
        "sensitive_conv_0": {"ON": "int16"},
        "sensitive_conv_1": {"ON": "int16"},
    },
}

ptq_model = build_model(
    onnx_file="model.onnx",
    march="nash-p",
    cali_data=cali_data,
    quant_config=quant_config,
    name_prefix="output/model",
    save_model=True,
)
```
