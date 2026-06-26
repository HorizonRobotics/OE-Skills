# hbDNNRelease

- 类别: 函数
- 原型: `int32_t hbDNNRelease(hbDNNPackedHandle_t dnnPackedHandle);`
- 头文件: `hobot/dnn/hb_dnn.h`

## 作用
释放 packed handle 关联的模型资源。

## 使用注意事项
- 释放前确保关联任务已结束。
