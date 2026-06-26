---
name: remove-io-nodes
description: 删除HBIR模型输入输出相邻节点或指定类型/名称的节点
---


# 代码示例

## 检查节点是否可删除
```python
from hbdk4.compiler import load

module = load("model.bc")
func = module[0]

# 检查输入参数相邻节点是否可删除
removable, reason = func.flatten_inputs[0].is_removable
print(removable)  # True/False
print(reason)     # 不可删除的原因分析
```

## 获取相邻节点
```python
# 获取输入/输出参数相邻的所有op
oplist = func.flatten_inputs[0].get_attached_op
# 返回 List[Operation]
```

## 删除相邻节点
```python
# 删除输入/输出参数相邻节点
result = func.flatten_inputs[0].remove_attached_op()
print(result[0])  # True表示成功删除
print(result[1])  # 失败时的原因
```

## 按算子类型删除节点
```python
from hbdk4.compiler import load

model = load("qat.bc")
# 删除Transpose和Reshape节点（convert前）
model.functions[0].remove_io_op(op_types=["Transpose", "Reshape"])
```

## 按算子名称删除节点
```python
model = load("quantied.bc")
model.functions[0].remove_io_op(op_names=["transpose_123"])
```

## 删除量化和反量化节点（需convert后）
```python
from hbdk4.compiler import load, convert, March

model = load("model.bc")
converted = convert(model, March.nash_e)
# 删除量化和反量化节点，需在convert之后
converted.functions[0].remove_io_op(op_types=["Quantize", "Dequantize"])
```

## 删除参数本身
```python
# 从函数参数中移除该参数
result = func.flatten_inputs[0].erase()
print(result[0])  # True表示成功
```

# API参考

## `Argument.is_removable` (property)
检查相邻操作是否可删除。
- **返回**: Tuple[bool, str] - 第一个元素为是否可删除，第二个为不可删除时的诊断信息

## `Argument.get_attached_op` (property)
获取参数相邻的操作。
- **返回**: List[Operation]

## `Argument.remove_attached_op()`
删除唯一的相邻操作。
- **返回**: Tuple[bool, str]
- **注意**: Quantize和Dequantize op应在convert后删除

## `Argument.erase()`
从函数参数中移除该参数。
- **返回**: Tuple[bool, str]

## `Function.remove_io_op(op_types=None, op_names=None)`
按类型或名称删除节点，支持递归删除。
- **op_types** (list[str]|tuple[str]): 要删除的算子类型列表
- **op_names** (list[str]|tuple[str]): 要删除的算子名称列表
- **注意**: op_types和op_names二选一，同时指定时只有op_names生效
- **支持的删除类型**: ["Dequantize", "Quantize", "Transpose", "FilterCopy", "Cast", "Reshape", "Softmax", "RlePostProcess"]

# 注意事项
- 删除量化和反量化节点需在convert之后进行
- remove_io_op的op_types和op_names二选一，同时指定时op_names优先
- 可删除的算子应为单输入单输出（FilterCopy除外）