---
name: hbm-modify
description: 修改HBM模型的描述信息和名称，查询量化信息。修改通过staged机制缓存，调用save_by_staged_info时写入文件
---


# 代码示例

## 修改HBM描述
```python
from hbdk4.compiler import Hbm

hbm = Hbm("models.hbm")

# 查询desc
print(hbm.desc.data)

# 设置staged_desc（str或bytes）
hbm.staged_desc = "model desc"

# 保存到新文件
hbm.save_by_staged_info("updated.hbm")
```

## 修改Function或Tensor的name/desc
```python
from hbdk4.compiler import Hbm

hbm = Hbm("models.hbm")

# 查询desc
print(hbm.functions[0].desc.data)
print(hbm.functions[0].flatten_inputs[0].desc.data)

# 设置staged信息
hbm.functions[0].staged_desc = "function desc"
hbm.functions[0].flatten_inputs[0].staged_desc = b"input binary desc"
hbm.functions[0].flatten_outputs[0].staged_desc = b"output binary desc"

# 修改名称
hbm.functions[0].staged_name = "new_func_name"
hbm.functions[0].flatten_inputs[0].staged_name = "new_input_name"
hbm.functions[0].flatten_outputs[0].staged_name = "new_output_name"

# 保存修改到新文件
hbm.save_by_staged_info("updated.hbm")
```

## 查询HBM输入输出的量化信息
```python
from hbdk4.compiler import Hbm

hbm = Hbm("models.hbm")

# 查询量化信息
print(hbm.graphs[0].flatten_inputs[0].type.quant_info)
print(hbm.graphs[0].flatten_outputs[0].type.quant_info)
```

# API参考

## `Hbm.desc` (property)
查询HBM描述信息，返回Description对象。

## `Hbm.staged_desc` (property/setter)
设置/获取HBM的staged描述，支持str或bytes类型。

## `Hbm.functions[i].staged_desc` / `staged_name`
设置/获取function的staged描述和名称。

## `Hbm.functions[i].flatten_inputs[j].staged_desc` / `staged_name`
设置/获取输入tensor的staged描述和名称。

## `Hbm.functions[i].flatten_outputs[j].staged_desc` / `staged_name`
设置/获取输出tensor的staged描述和名称。

## `Hbm.save_by_staged_info(filename)`
将staged信息写入新的HBM文件。
- **filename** (str): 输出HBM文件路径

## `Variable.type.quant_info` (property)
查询量化信息，返回QuantInfo对象（含scales, zero_points, channel_axis等）。

# 注意事项
- staged_desc/staged_name设置后不会立即修改HBM对象，需调用save_by_staged_info写入文件
- desc支持str或bytes类型
- 名称不能重复，否则save_by_staged_info会报错