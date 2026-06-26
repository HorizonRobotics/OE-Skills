# hbDNNInferV2

- 类别: 函数
- 原型: `int32_t hbDNNInferV2(hbUCPTaskHandle_t *taskHandle, hbDNNTensor *output, hbDNNTensor const *input, hbDNNHandle_t dnnHandle);`
- 头文件: `hobot/dnn/hb_dnn.h`

## 作用
执行模型推理（支持同步与异步/多子任务场景）。

## 使用注意事项
- 输入输出数组长度需分别匹配 `hbDNNGetInputCount` / `hbDNNGetOutputCount`。
- 场景 1: `taskHandle != nullptr` 且 `*taskHandle == nullptr`，创建新任务句柄并以异步任务方式提交。
- 场景 2: `taskHandle != nullptr` 且 `*taskHandle != nullptr`，将当前推理附加到已有任务句柄；该句柄需由场景 1 创建，且尚未提交或释放。
- 场景 3: `taskHandle == nullptr`，走同步执行路径；接口返回即完成，且无法获取任务句柄用于后续轮询或动态输出查询。
