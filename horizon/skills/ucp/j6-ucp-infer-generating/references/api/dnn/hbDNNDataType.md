# hbDNNDataType

- 类别: 枚举
- 头文件: `hobot/dnn/hb_dnn.h`

## 作用
定义张量数据类型（S8/U8/F32 等）。

## 枚举值（完整）
- `HB_DNN_TENSOR_TYPE_S4`
- `HB_DNN_TENSOR_TYPE_U4`
- `HB_DNN_TENSOR_TYPE_S8`
- `HB_DNN_TENSOR_TYPE_U8`
- `HB_DNN_TENSOR_TYPE_F16`
- `HB_DNN_TENSOR_TYPE_S16`
- `HB_DNN_TENSOR_TYPE_U16`
- `HB_DNN_TENSOR_TYPE_F32`
- `HB_DNN_TENSOR_TYPE_S32`
- `HB_DNN_TENSOR_TYPE_U32`
- `HB_DNN_TENSOR_TYPE_F64`
- `HB_DNN_TENSOR_TYPE_S64`
- `HB_DNN_TENSOR_TYPE_U64`
- `HB_DNN_TENSOR_TYPE_BOOL8`
- `HB_DNN_TENSOR_TYPE_MAX`: 枚举上限标记，不作为实际张量数据类型使用。

## 使用注意事项
- 需与模型编译产物和输入输出 buffer 的真实类型一致。
