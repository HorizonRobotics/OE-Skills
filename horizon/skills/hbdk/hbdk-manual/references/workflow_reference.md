# HBDK4 工作流参考

## 典型端到端工作流

### PTQ流程（训练后量化）

```
ONNX模型(ptq.onnx) → HBIR(ptq.bc) → 定点模型(quantized.bc) → HBM(deploy.hbm)
```

```python
import onnx
from hbdk4.compiler.onnx import export
from hbdk4.compiler import save, load, convert, compile, link, March

# 1. 导入ONNX模型
onnx_model = onnx.load("ptq.onnx")
exported_module = export(onnx_model, name="MyModel")
save(exported_module, "ptq.bc")

# 2. 定点化
module = load("ptq.bc")
converted_module = convert(module, March.nash_e, advice=True)
save(converted_module, "quantized.bc")

# 3. 编译
hbo = compile(converted_module, "deploy.hbo", March.nash_e, 0)
hbm = link([hbo], "deploy.hbm")
```

### QAT流程（量化感知训练）

```
QAT模型(qat.bc) → 定点模型(quantized.bc) → HBM(deploy.hbm)
```

```python
from hbdk4.compiler import load, convert, compile, link, March

# 1. 加载QAT模型
module = load("qat.bc")

# 2. 定点化
converted_module = convert(module, March.nash_e)

# 3. 编译
hbm = compile(converted_module, "deploy.hbm", March.nash_e, 0)
```

### 带输入修改的流程

```
HBIR模型 → 插入节点 → 定点化 → 编译 → HBM
```

```python
from hbdk4.compiler import load, convert, compile, link, March

module = load("model.bc")
func = module[0]

# 在convert前插入节点
y, uv = func.flatten_inputs[0].insert_image_convert("nv12")
func.flatten_inputs[0].insert_image_preprocess(
    mode="yuvbt601full2rgb",
    divisor=255,
    mean=[0.485, 0.456, 0.406],
    std=[0.229, 0.224, 0.225]
)

# 定点化 + 编译
converted_module = convert(module, March.nash_e)
hbm = compile(converted_module, "deploy.hbm", March.nash_e, 0)
```

### 带RLE输出的流程

```
HBIR模型 → 定点化 → 删除Dequantize → 插入RLE → 编译 → HBM
```

```python
from hbdk4.compiler import load, convert, compile, March

module = load("model.bc")
converted_module = convert(module, March.nash_e)

# convert后操作：先删除Dequantize，再插入RLE
func = converted_module[0]
func.remove_io_op(op_types=["Dequantize"])
func.flatten_outputs[0].insert_rle()

hbm = compile(converted_module, "deploy.hbm", March.nash_e, 0)
```

### 多模型打包流程

```python
from hbdk4.compiler import compile, link, March

# 分别编译
hbo1 = compile(converted_module_1, "model1.hbo", March.nash_e, 0)
hbo2 = compile(converted_module_2, "model2.hbo", March.nash_e, 0)

# 打包
hbm = link([hbo1, hbo2], "combined.hbm")
```

### 精度调优流程

```python
from hbdk4.compiler import load, convert, compile, March
from hbdk4.compiler.overlay import PrecisionConfig

module = load("model.bc")

# 对特定算子配置精度
module.precision_config = {
    "sensitive_conv": PrecisionConfig.KEEP_FLOAT,
    "output_conv": PrecisionConfig.HIGH_PRECISION_QPP,
}

converted_module = convert(module, March.nash_e)
hbm = compile(converted_module, "deploy.hbm", March.nash_e)
```

## 关键注意事项

1. **insert_xxx API（除insert_rle外）必须在convert前调用**，否则插入的算子可能不会经过转换pass
2. **insert_rle必须在convert后调用**，且需先删除输出上的Dequantize节点
3. **删除Quantize/Dequantize需在convert后进行**
4. **不支持动态batch和动态shape的模型**
5. **ONNX模型需先经过horizon_nn校准或使用onnxsim优化**
6. **模型输入输出数量不超过512，单个不超过2GB，tensor维度不超过10**
7. **输入输出名称必须唯一**
8. **precision_config的key匹配算子的OriginalName字段**

## 文件格式说明

| 格式 | 说明 |
|------|------|
| `.onnx` | ONNX模型文件 |
| `.bc` | HBIR MLIR bytecode文件 |
| `.mlir` | HBIR MLIR文本文件 |
| `.hbo` | 编译后的目标文件（需link） |
| `.hbm` | 最终部署模型文件 |

## 编译路径选择

| 场景 | 推荐方式 | 说明 |
|------|----------|------|
| 单模型部署 | 直接compile到.hbm | 内部自动HBO+link |
| 多模型打包 | 先compile到.hbo，再link | 可合并多个HBO |
| 增量编译 | compile到.hbo + CacheMode.enable | 复用命中的搜索评估结果 |
