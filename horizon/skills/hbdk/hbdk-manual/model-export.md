---
name: model-export
description: 将ONNX模型（ptq.onnx）导出为伪量化HBIR模型（.bc文件），支持模型统计和可视化
---


# 代码示例

## ONNX导出流程
```python
import onnx
from hbdk4.compiler.onnx import statistics, export
from hbdk4.compiler import statistics as hbir_statistics, visualize, save

# 加载ONNX模型
onnx_model = onnx.load("ptq.onnx")

# 打印ONNX算子列表和数量
statistics(onnx_model)

# 将ONNX导出为HBIR
exported_module = export(onnx_model, name="OnnxModel")

# 打印HBIR算子列表和数量
hbir_statistics(exported_module)

# 可视化模型
visualize(exported_module, save_as_external_data=True)
visualize(exported_module, use_netron=True)

# 保存为.bc文件
save(exported_module, "converted.bc")
```

## 使用onnxsim优化后导出（适用于未校准模型）
```python
import onnx
from onnxsim import simplify
from hbdk4.compiler.onnx import export

onnx_model = onnx.load("model.onnx")
onnx_model = simplify(onnx_model)[0]
exported_module = export(onnx_model, name="OnnxModel")
```

# API参考

## `hbdk4.compiler.onnx.export(proto, *, name=None) -> Module`
将ONNX模型导出为HBIR MLIR。
- **proto** (onnx.ModelProto): onnx protobuf
- **name** (Optional[str]): 重命名函数名，默认使用onnx graph name
- **返回**: Module对象

## `hbdk4.compiler.onnx.statistics(proto)`
打印ONNX模型op统计。
- **proto** (onnx.ModelProto): onnx protobuf

## `hbdk4.compiler.statistics(m, expand_fusion=True) -> list`
打印HBIR模型op统计信息。
- **m** (Module): HBIR模块
- **expand_fusion** (bool): 是否展开fusion算子

## `hbdk4.compiler.visualize(m, onnx_file=None, use_netron=False, host=None, port=None, save_as_external_data=False, external_data_file=None)`
生成可视化ONNX文件。
- **m** (Module): HBIR模块
- **onnx_file** (str): 保存onnx文件路径
- **use_netron** (bool): 是否启动netron服务
- **host** (str): netron服务地址
- **port** (int|Tuple[int]): netron服务端口，多function时可为tuple
- **save_as_external_data** (bool): 是否保存权重数据文件
- **external_data_file** (str): 指定外部权重数据文件名

# 注意事项
- ONNX模型的shape必须已记录在onnx proto中
- 不支持动态batch和动态shape的模型
- 未经过horizon_nn校准的模型或包含不支持的算子（Shape算子、If branch）时，需先用onnxsim优化
