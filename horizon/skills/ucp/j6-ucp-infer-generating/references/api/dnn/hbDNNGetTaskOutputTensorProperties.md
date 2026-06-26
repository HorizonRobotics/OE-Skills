# hbDNNGetTaskOutputTensorProperties

- 类别: 函数
- 原型: `int32_t hbDNNGetTaskOutputTensorProperties(hbDNNTensorProperties *properties, hbUCPTaskHandle_t taskHandle, int32_t subTaskIndex, int32_t outputIndex);`
- 头文件: `hobot/dnn/hb_dnn.h`

## 作用
获取指定任务子任务输出张量属性（动态输出场景）。

## 使用注意事项
- 不支持同步模式动态输出属性获取（因无法取得 taskHandle）。
