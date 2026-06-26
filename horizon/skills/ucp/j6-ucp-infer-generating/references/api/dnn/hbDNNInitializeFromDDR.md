# hbDNNInitializeFromDDR

- 类别: 函数
- 原型: `int32_t hbDNNInitializeFromDDR(hbDNNPackedHandle_t *dnnPackedHandle, const void **modelData, int32_t *modelDataLengths, int32_t modelDataCount);`
- 头文件: `hobot/dnn/hb_dnn.h`

## 作用
从内存中的模型数据初始化 DNN 打包句柄。

## 使用注意事项
- `modelData` 指向内存需在加载阶段保持有效。
