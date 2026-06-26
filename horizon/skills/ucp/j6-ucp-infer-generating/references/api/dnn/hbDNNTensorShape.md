# hbDNNTensorShape

- 类别: 结构体
- 头文件: `hobot/dnn/hb_dnn.h`

## 作用
描述张量形状信息。

## 字段说明
- `int32_t dimensionSize[HB_DNN_TENSOR_MAX_DIMENSIONS]`: 各维长度。
- `int32_t numDimensions`: 维度数量。

## 使用注意事项
- 有效维度仅前 `numDimensions` 项。
