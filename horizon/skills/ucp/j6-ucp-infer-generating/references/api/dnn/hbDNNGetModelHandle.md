# hbDNNGetModelHandle

- 类别: 函数
- 原型: `int32_t hbDNNGetModelHandle(hbDNNHandle_t *dnnHandle, hbDNNPackedHandle_t dnnPackedHandle, char const *modelName);`
- 头文件: `hobot/dnn/hb_dnn.h`

## 作用
按模型名从 packed handle 获取单模型句柄。

## 使用注意事项
- `modelName` 必须是 `hbDNNGetModelNameList` 返回列表中的有效名称。
