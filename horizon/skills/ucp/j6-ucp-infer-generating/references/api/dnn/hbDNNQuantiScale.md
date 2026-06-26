# hbDNNQuantiScale

- 类别: 结构体
- 头文件: `hobot/dnn/hb_dnn.h`

## 作用
描述按 scale / zero-point 的量化与反量化参数。

## 字段说明
- `int32_t scaleLen`: scale 长度。
- `float *scaleData`: scale 数据。
- `int32_t zeroPointLen`: zero-point 长度。
- `int32_t *zeroPointData`: zero-point 数据。

## 使用注意事项
- `zeroPointLen=0` 与 `>0` 时公式不同，需按模型属性解释。
- 指针有效期需覆盖推理使用周期。
