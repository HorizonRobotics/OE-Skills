# hbDNNQuantiType

- 类别: 枚举
- 头文件: `hobot/dnn/hb_dnn.h`

## 作用
标识张量量化类型。

## 枚举值
- `NONE = 0`: 无量化。
- `SCALE = 1`: 按 scale（可带 zero-point）量化。

## 使用注意事项
- 应与 `hbDNNTensorProperties.scale` 联合判断。
