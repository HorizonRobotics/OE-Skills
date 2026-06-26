# hbDNNGetHBMDesc

- 类别: 函数
- 原型: `int32_t hbDNNGetHBMDesc(char const **desc, uint32_t *size, int32_t *type, hbDNNPackedHandle_t dnnPackedHandle, int32_t index);`
- 头文件: `hobot/dnn/hb_dnn.h`

## 作用
获取指定 HBM（在 packed handle 中按加载顺序索引）的描述信息。

## 使用注意事项
- `index` 范围对应初始化接口传入模型数组下标。
