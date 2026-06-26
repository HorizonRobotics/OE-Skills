---
name: model-info-query
description: 查询和修改HBIR模型的输入输出、版本号、march信息、tensor名称、模型描述、精度配置等
---


# 代码示例

## 查询模型输入输出
```python
from hbdk4.compiler import load

module = load("model.bc")

# 通过参数顺序获取输入输出
input0 = module.graphs[0].flatten_inputs[0]
output0 = module.graphs[0].flatten_outputs[0]

# 查看输入输出的名称、形状、类型
print(input0.name)
print(input0.type.shape)
print(input0.type.np_dtype)
```

## Pytree风格查询
```python
# 当模型提供TreeSpec信息时，支持pytree风格查询
if module.graphs[0].support_pytree:
    input0 = module.graphs[0].inputs["img"].y
    output0 = module.graphs[0].outputs["result"]
```

## 查询模型版本号和march信息
```python
from hbdk4.compiler import load

module = load("model.bc")

print(module.version)  # HBDK导出版本号
print(module.march)    # convert前的模型march为None
```

## 修改tensor name
```python
from hbdk4.compiler import load

module = load("model.bc")
func = module[0]

func.flatten_inputs[0].name = "img"
func.flatten_outputs[0].name = "output"

print(func)
```

## 修改模型描述（desc）
```python
from hbdk4.compiler import load

module = load("model.bc")
func = module[0]

func.desc = "model description"
func.flatten_inputs[0].desc = "RGB input"
func.flatten_outputs[0].desc = "gesture"

print(func.desc)
print(func.flatten_inputs[0].desc)
print(func.flatten_outputs[0].desc)
```

## 设置精度配置
```python
from hbdk4.compiler import load, convert, compile, March
from hbdk4.compiler.overlay import PrecisionConfig

module = load("model.bc")

# 保持指定算子为浮点运算（不量化）
module.precision_config = {"conv1": PrecisionConfig.KEEP_FLOAT}

# 或对指定算子使用高精度量化后处理
module.precision_config = {"conv2": PrecisionConfig.HIGH_PRECISION_QPP}

# 也可逐个设置
module.precision_config["conv3"] = PrecisionConfig.KEEP_FLOAT

# 配置后正常走convert + compile流程
converted_module = convert(module, March.nash_e)
hbm = compile(converted_module, "deploy.hbm", March.nash_e)
```

## 替换int64为int32
```python
from hbdk4.compiler import load

module = load("model.bc")
module.replace_index_tensor_type()
```

## 提取子图
```python
from hbdk4.compiler import load

module = load("model.bc")
func = module[0]

# 根据输入输出名称提取子图，返回新Module
sub_module = func.extract_function(
    input_names=["input_0"],
    output_names=["output_0"]
)
```

## 查看模型统计信息
```python
from hbdk4.compiler import load, statistics

module = load("model.bc")

# 打印op列表和数量
statistics(module)

# 也可通过function查看
func = module[0]
func.statistics(expand_fusion=True)
```

## 可视化模型
```python
from hbdk4.compiler import load, visualize

module = load("model.bc")

# 只保存onnx文件
visualize(module, save_as_external_data=True)

# 生成netron链接查看
visualize(module, use_netron=True)

# 生成netron链接并保存权重数据
visualize(module, use_netron=True, save_as_external_data=True)
```

# API参考

## `Module.version` (property)
返回HBDK导出版本号字符串。

## `Module.march` (property)
返回模型的march信息，convert前为None。

## `Module.graphs` / `Module.functions` (property)
返回所有function列表，每个元素为FunctionHelper。

## `Module.precision_config` (property/setter)
精度配置字典，key为算子的OriginalName，value为PrecisionConfig枚举。
- `PrecisionConfig.KEEP_FLOAT`: 保持浮点运算，不量化
- `PrecisionConfig.HIGH_PRECISION_QPP`: 使用高精度量化后处理

## `Function.flatten_inputs` / `flatten_outputs` (property)
返回模型的扁平化输入/输出参数列表。

## `Function.support_pytree` (property)
是否支持pytree风格查询。

## `Function.inputs["key"]` / `outputs["key"]`
Pytree风格的输入输出查询路径。

## `Function.extract_function(input_names, output_names) -> Module`
根据指定的输入输出名称提取子图，返回新的Module。
- **input_names** (List[str]): 子图输入名称列表
- **output_names** (List[str]): 子图输出名称列表

## `Argument.name` (property/setter)
获取/设置参数名称。

## `Argument.desc` (property/setter)
获取/设置参数描述。

## `Argument.type.shape` / `type.np_dtype`
获取参数的形状和numpy数据类型。

## `Module.replace_index_tensor_type()`
将模型中所有si64类型替换为si32类型。

## `statistics(module, expand_fusion=True)`
打印模型op统计信息。

## `visualize(module, onnx_file=None, use_netron=False, host=None, port=None, save_as_external_data=False, external_data_file=None)`
可视化模型。

# 注意事项
- convert前的模型march为None
- replace_index_tensor_type替换后需确保不会发生数据溢出
- pytree风格查询需模型提供TreeSpec信息
- precision_config的key匹配的是算子的OriginalName字段（debug info中记录）
- extract_function主要用于调试，不建议用于生产环境
