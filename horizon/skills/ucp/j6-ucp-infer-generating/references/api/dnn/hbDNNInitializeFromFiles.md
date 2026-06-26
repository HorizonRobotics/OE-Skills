# hbDNNInitializeFromFiles

- 类别: 函数
- 原型: `int32_t hbDNNInitializeFromFiles(hbDNNPackedHandle_t *dnnPackedHandle, char const **modelFileNames, int32_t modelFileCount);`
- 头文件: `hobot/dnn/hb_dnn.h`

## 作用
从模型文件路径列表加载并初始化 DNN 打包句柄。

## 使用注意事项
- 成功后需调用 `hbDNNRelease` 释放。
