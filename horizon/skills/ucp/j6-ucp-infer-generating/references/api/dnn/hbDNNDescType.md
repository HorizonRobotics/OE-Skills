# hbDNNDescType

- 类别: 枚举
- 头文件: `hobot/dnn/hb_dnn.h`

## 作用
描述信息类型标识。

## 枚举值
- `HB_DNN_DESC_TYPE_UNKNOWN = 0`
- `HB_DNN_DESC_TYPE_STRING = 1`

## 使用注意事项
- 读取 `hbDNNGet*Desc` 返回值时先检查 `type`。
