---
name: insert-nodes
description: 在HBIR模型的输入输出参数上插入预处理节点，包括pyramid/preprocess/resize/transpose/split/rle
---


> **除insert_rle外，insert_xxx API必须在convert阶段前调用**，以避免插入的算子没有经过转换pass。

# 代码示例

## 插入Pyramid输入（NV12模式）
```python
from hbdk4.compiler import load

module = load("model.bc")
func = module[0]
func.flatten_inputs[0].name = "img"

# NV12模式：输入变为y和uv两个参数
y, uv = func.flatten_inputs[0].insert_image_convert("nv12")
print(y)  # tensor<1x32x32x1xui8> img_y
print(uv)  # tensor<1x16x16x2xui8> img_uv

# 修改新参数名
func.flatten_inputs[0].name = "img_yyy"
func.flatten_inputs[1].name = "img_uvuvuv"
```

## 插入Pyramid输入（灰度图模式）
```python
new_y = func.flatten_inputs[0].insert_image_convert("gray")
# 输入变为y通道灰度图张量
```

## 插入Pyramid输入（16位Y输入模式）
```python
# nv12_yh12: 16位Y输入取高12位作为有效数据
y, uv = func.flatten_inputs[0].insert_image_convert("nv12_yh12")

# nv12_yh10: 16位Y输入取高10位作为有效数据
y, uv = func.flatten_inputs[0].insert_image_convert("nv12_yh10")
```

## 插入Preprocess输入
```python
from hbdk4.compiler import load

module = load("model.bc")
func = module.graphs[0]
func.flatten_inputs[0].name = "img"

# YUV转RGB后进行preprocess
yuv = func.flatten_inputs[0].insert_image_preprocess(
    mode="yuvbt601full2rgb",
    divisor=255,
    mean=[0.485, 0.456, 0.406],
    std=[0.229, 0.224, 0.225],
    is_signed=True,
    bit_width=8
)

# 不进行图像格式转换，仅preprocess
func.flatten_inputs[0].insert_image_preprocess(
    mode="skip",
    divisor=255,
    mean=[0.5, 0.5, 0.5],
    std=[0.5, 0.5, 0.5]
)

# BGR转RGB后preprocess
func.flatten_inputs[0].insert_image_preprocess(
    mode="bgr2rgb",
    divisor=255,
    mean=[0.485, 0.456, 0.406],
    std=[0.229, 0.224, 0.225]
)
```

## 插入Preprocess + Pyramid组合
```python
# 先插入preprocess，再插入image_convert
func.flatten_inputs[0].insert_image_preprocess(
    mode="yuvbt601full2rgb", divisor=255, mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]
)
func.flatten_inputs[0].insert_image_convert("nv12")
# 实现从NV12转YUV444-128转RGB后进行preprocess
```

## 插入ROI Resize输入
```python
from hbdk4.compiler import load

module = load("model.bc")
func = module[0]

# NV12模式：输入变为y, uv, roi三个参数
y, uv, roi = func.flatten_inputs[0].insert_roi_resize(mode="nv12")

# 指定插值方式和填充模式
y, uv, roi = func.flatten_inputs[0].insert_roi_resize(
    mode="nv12",
    interp_mode="nearest",
    pad_mode="constant",
    pad_value=(0, -128)
)

# 灰度图模式
y, roi = func.flatten_inputs[0].insert_roi_resize(mode="gray")

# 16位Y输入模式
y, uv, roi = func.flatten_inputs[0].insert_roi_resize(mode="nv12_yh12")
```

## 插入Transpose输入/输出
```python
from hbdk4.compiler import load

module = load("model.bc")
func = module[0]

# permutes[i] = 原维度i 放到 新维度permutes[i]
# 例如 NCHW(1,3,224,224) -> NHWC(1,224,224,3):
#   原dim0(N)->新dim0, 原dim1(C)->新dim3, 原dim2(H)->新dim1, 原dim3(W)->新dim2
#   所以 permutes=[0,3,1,2]
in_node = func.flatten_inputs[0].insert_transpose([0, 3, 1, 2])

# 输出transpose同理：NHWC(1,224,224,3) -> NCHW(1,3,224,224)
#   原dim0(N)->新dim0, 原dim1(H)->新dim2, 原dim2(W)->新dim3, 原dim3(C)->新dim1
#   所以 permutes=[0,3,1,2]
out_node = func.flatten_outputs[0].insert_transpose([0, 3, 1, 2])
```

## 插入Split输入/输出
```python
from hbdk4.compiler import load

module = load("model.bc")
func = module[0]

# 将输入参数的维度0拆分为多个输入参数
splits_in = func.flatten_inputs[0].insert_split(0)

# 将输出参数的维度3拆分为多个输出参数
splits_out = func.flatten_outputs[0].insert_split(3)
```

## 插入RLE（需在convert后调用）
```python
from hbdk4.compiler import load, convert, March

module = load("model.bc")
converted_module = convert(module, March.nash_e)
func = converted_module[0]

# 先删除输出上的Dequantize节点
func.remove_io_op(op_types=["Dequantize"])

# 再插入RLE
out_node = func.flatten_outputs[0].insert_rle()
```

# API参考

## `Argument.insert_image_convert(mode="nv12")`
插入image_convert节点，改变输入参数类型。
- **mode** (str): "nv12"(默认), "gray", "nv12_yh12", "nv12_yh10"
- **返回**: 新参数（元组或单个参数）
- **注意**: nv12模式返回(y, uv)，gray模式返回y，nv12_yh12/nv12_yh10返回(y, uv)

## `Argument.insert_image_preprocess(mode=None, divisor=None, mean=None, std=None, is_signed=True, bit_width=8, image_layout=None)`
插入preprocess节点。
- **mode** (str|None): "skip"(默认), "yuvbt601full2rgb", "yuvbt601full2bgr", "yuvbt601video2rgb", "yuvbt601video2bgr", "bgr2rgb", "rgb2bgr"
- **divisor** (int|None): 归一化除数，默认按位宽推断（8位=256, 16位=65536）
- **mean** (List[float]): 均值
- **std** (List[float]): 标准差
- **is_signed** (bool): 输入是否有符号，默认True
- **bit_width** (int): 输入位宽，8或16
- **image_layout** (str|None): "normal"(默认) 或 "yhuvl"

## `Argument.insert_roi_resize(mode="nv12", interp_mode="bilinear", pad_mode="constant", pad_value=(0, -128))`
插入roi_resize节点。
- **mode** (str): "nv12"(默认), "gray", "nv12_yh12", "nv12_yh10"
- **interp_mode** (str): "bilinear"(默认) 或 "nearest"
- **pad_mode** (str): "constant"(默认) 或 "border"
- **pad_value** (tuple): Y和UV填充值，默认(0, -128)

## `Argument.insert_transpose(permutes)`
插入transpose节点，改变维度顺序。input和output上的permutes含义一致。
- **permutes** (List[int]): permutes[i]表示原维度i放到新维度permutes[i]。例如 NCHW→NHWC 使用 `[0,3,1,2]`（原dim1(C)→新dim3, 原dim2(H)→新dim1, 原dim3(W)→新dim2）
- **注意**: 与numpy.transpose的axes含义是逆映射。numpy中NCHW→NHWC用 `[0,2,3,1]`，hbdk中用 `[0,3,1,2]`

## `Argument.insert_split(dim)`
插入split节点，拆分指定维度。
- **dim** (int): 拆分维度

## `Argument.insert_rle()`
插入RLE编码节点（**需在convert后调用**）。
- **返回**: 新的输出参数

# 注意事项
- **insert_xxx API（除insert_rle外）必须在convert前调用**，否则插入算子未经过转换pass
- **insert_rle必须在convert后调用**，且需先删除输出上的Dequantize节点
- 插入多个pyramid输入时，用倒序遍历避免动态调整index
- 返回的新参数可继续调用insert_xxx实现链式插入
- insert_image_preprocess的mode为"skip"或None时，不进行颜色空间转换，仅做归一化
