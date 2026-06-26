# hbDNNTensorProperties

- 类别: 结构体
- 头文件: `hobot/dnn/hb_dnn.h`

## 作用
描述张量属性（形状、类型、量化、对齐、stride）。

## 字段说明
- `hbDNNTensorShape validShape`: 有效形状。
- `int32_t tensorType`: 数据类型（见 `hbDNNDataType`）。
- `hbDNNQuantiScale scale`: 量化参数。
- `hbDNNQuantiType quantiType`: 量化类型。
- `int32_t quantizeAxis`: 量化轴。
- `int64_t alignedByteSize`: 对齐后总字节数。
- `int64_t stride[HB_DNN_TENSOR_MAX_DIMENSIONS]`: 各维步长。

## 使用注意事项
- 分配输入输出内存时以 `alignedByteSize` 为准。
