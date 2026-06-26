---
name: model-serialization
description: 将HBIR模型保存到.bc文件，或从.bc文件加载HBIR模型。支持加载MLIR文本和bytecode格式
---


# 代码示例

## 基本保存与加载
```python
from hbdk4.compiler import save, load, statistics

# 将Module序列化为bytecode
save(exported_module, "converted.bc")

# 从bytecode文件载入Module
restored_module = load("converted.bc")
statistics(restored_module)
```

## 从MLIR文本解析Module
```python
from hbdk4.compiler.overlay import Module

mlir_text = open("model.mlir", "r").read()
module = Module.parse(mlir_text)
```

# API参考

## `hbdk4.compiler.load(path) -> Module`
- **path** (str): 加载文件路径，支持".bc"(bytecode)和".mlir"(文本)格式
- **返回**: Module对象
- **异常**: ValueError - 文件后缀不是.bc或.mlir；RuntimeError - 加载兼容性处理失败

## `hbdk4.compiler.save(m, path) -> None`
- **m** (Module): HBIR模块
- **path** (str): 保存路径，必须以.bc结尾
- **注意**: save会clone模块后再保存，不影响原始Module对象

## `Module.parse(asm) -> Module`
- **asm** (str): MLIR文本内容
- **返回**: Module对象

# 注意事项
- save时会clone模块，原始Module对象不会被修改
- load的.bc文件需与当前HBDK版本兼容
- 支持的数据类型: ui8/si8/si16/ui32/si32/si64/float/bool
