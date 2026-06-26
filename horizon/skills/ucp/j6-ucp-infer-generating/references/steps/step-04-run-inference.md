# Step 04 - 执行推理

## 涉及头文件
- `hobot/dnn/hb_dnn.h`
- `hobot/hb_ucp.h`

## 涉及 API
- `hbDNNInferV2`
  原型: `int32_t hbDNNInferV2(hbUCPTaskHandle_t *taskHandle, hbDNNTensor *output, hbDNNTensor const *input, hbDNNHandle_t dnnHandle);`
  作用：执行模型推理（支持同步与异步/多子任务场景）。

- `hbUCPSubmitTask`
  原型: `int32_t hbUCPSubmitTask(hbUCPTaskHandle_t taskHandle, hbUCPSchedParam *schedParam);`
  作用：按调度参数将异步任务提交到 UCP。

- `hbUCPWaitTaskDone`
  原型: `int32_t hbUCPWaitTaskDone(hbUCPTaskHandle_t taskHandle, int32_t timeout);`
  作用：阻塞等待异步任务完成。

- `hbUCPReleaseTask`
  原型: `int32_t hbUCPReleaseTask(hbUCPTaskHandle_t taskHandle);`
  作用：释放异步任务及关联资源。

- `hbUCPSchedParam`
  描述异步任务提交到 UCP 时的调度参数。

## 产出
- 已完成的推理结果上下文（可安全读取输出）。

## 示例代码

### 1. 执行推理

#### 分支 1：异步执行（默认）

```cpp
// Step 1: 创建任务
hbUCPTaskHandle_t task_handle = nullptr;
CHECK(hbDNNInferV2(&task_handle, output_tensors.data(), input_tensors.data(), model_handle));

// Step 2: 提交任务
hbUCPSchedParam ctrl_param;
HB_UCP_INITIALIZE_SCHED_PARAM(&ctrl_param);
ctrl_param.backend = HB_UCP_BPU_CORE_ANY;
CHECK(hbUCPSubmitTask(task_handle, &ctrl_param));

// Step 3: 等待完成
CHECK(hbUCPWaitTaskDone(task_handle, 0));

// Step 4: 释放任务
CHECK(hbUCPReleaseTask(task_handle));
```

#### 分支 2：同步执行

```cpp
// taskHandle 传 nullptr 走同步执行，接口返回即完成
CHECK(hbDNNInferV2(nullptr, output_tensors.data(), input_tensors.data(), model_handle));
```

#### 分支 3：多模型合批

```cpp
// Step 1: 创建第一个模型任务
hbUCPTaskHandle_t task_handle = nullptr;
CHECK(hbDNNInferV2(&task_handle, output_tensors1.data(), input_tensors1.data(), model_handle1));

// 复用 task_handle 将多个模型推理任务打包到同一个 task_handle
CHECK(hbDNNInferV2(&task_handle, output_tensors2.data(), input_tensors2.data(), model_handle2));

// Step 2: 提交任务
hbUCPSchedParam ctrl_param;
HB_UCP_INITIALIZE_SCHED_PARAM(&ctrl_param);
ctrl_param.backend = HB_UCP_BPU_CORE_ANY;
CHECK(hbUCPSubmitTask(task_handle, &ctrl_param));

// Step 3: 等待完成
CHECK(hbUCPWaitTaskDone(task_handle, 0));

// Step 4: 释放任务
CHECK(hbUCPReleaseTask(task_handle));
```

#### 分支 4：动态输出

如果输出的 validShape/stride 中含 -1，则需要推理完成后且任务释放前再获取实际 properties，用于后处理步骤。

```cpp
// Step 1: 创建任务
hbUCPTaskHandle_t task_handle = nullptr;
CHECK(hbDNNInferV2(&task_handle, output_tensors.data(), input_tensors.data(), model_handle));

// Step 2: 提交任务
hbUCPSchedParam ctrl_param;
HB_UCP_INITIALIZE_SCHED_PARAM(&ctrl_param);
ctrl_param.backend = HB_UCP_BPU_CORE_ANY;
CHECK(hbUCPSubmitTask(task_handle, &ctrl_param));

// Step 3: 等待完成
CHECK(hbUCPWaitTaskDone(task_handle, 0));

// 获取动态输出的实际 properties
for (int32_t output_index = 0; output_index < output_count; ++output_index) {
  hbDNNTensorProperties task_output_properties;
  CHECK(hbDNNGetTaskOutputTensorProperties(&task_output_properties, task_handle, 0, output_index));
  // 使用 task_output_properties 进行后处理
}

// Step 4: 释放任务
CHECK(hbUCPReleaseTask(task_handle));
```

#### 分支 5：多核模型

仅 J6P/H 平台支持多核模型推理，且多核模型推理需要明确指定要使用的 BPU 核心。

```cpp
// ...

hbUCPSchedParam ctrl_param;
HB_UCP_INITIALIZE_SCHED_PARAM(&ctrl_param);
// 假设为两核模型，其他多核情况可类推
ctrl_param.backend = HB_UCP_BPU_CORE_0 | HB_UCP_BPU_CORE_1;
CHECK(hbUCPSubmitTask(task_handle, &ctrl_param));

// ...
```
