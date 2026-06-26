# hbDNNGetModelNameList

- 类别: 函数
- 原型: `int32_t hbDNNGetModelNameList(char const ***modelNameList, int32_t *modelNameCount, hbDNNPackedHandle_t dnnPackedHandle);`
- 头文件: `hobot/dnn/hb_dnn.h`

## 作用
获取 packed handle 内模型名列表及数量。

## 使用注意事项
- 返回字符串由库管理，不应手动释放。
