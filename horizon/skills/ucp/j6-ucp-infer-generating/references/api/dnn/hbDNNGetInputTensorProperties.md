# hbDNNGetInputTensorProperties

- 类别: 函数
- 原型: `int32_t hbDNNGetInputTensorProperties(hbDNNTensorProperties *properties, hbDNNHandle_t dnnHandle, int32_t inputIndex);`
- 头文件: `hobot/dnn/hb_dnn.h`

## 作用
获取指定输入张量属性。

## 使用注意事项
- 常用于输入内存分配与预处理布局校验。
