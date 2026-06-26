# Skill Basic Example

## Q1: 在 example.cpp 中补全使用 UCP 加载模型的代码

**用户需求：** 在已有框架代码中补全模型加载逻辑，模型路径 `resnet50_nv12.hbm`，模型名称 `resnet50_nv12`。

**思考过程：**
1. 阅读 Step 01 文档，确定涉及 API：`hbDNNInitializeFromFiles`、`hbDNNGetModelHandle`
2. 确定分支：从文件加载 + 用户指定模型名
3. 添加头文件 `hobot/dnn/hb_dnn.h`
4. 调用 `hbDNNInitializeFromFiles` 获得 `packed_handle`
5. 调用 `hbDNNGetModelHandle` 获得 `model_handle`

**回答：**
```cpp
#include "hobot/dnn/hb_dnn.h"

// 加载模型
hbDNNPackedHandle_t packed_handle = nullptr;
const char *model_file = model_path.c_str();
CHECK(hbDNNInitializeFromFiles(&packed_handle, &model_file, 1));

hbDNNHandle_t model_handle = nullptr;
CHECK(hbDNNGetModelHandle(&model_handle, packed_handle, model_name.c_str()));
```

---

## Q2: 添加准备输入输出张量的代码，输入张量暂时填充 0

**用户需求：** 补全 Step 02 张量准备逻辑。

**思考过程：**
1. 阅读 Step 02 文档
2. 根据模型名 `resnet50_nv12` 判断输入格式为 NV12，需使用动态 Stride 分支
3. 输入张量：动态 Stride 处理（NV12）
4. 输出张量：静态分配
5. 添加头文件 `hobot/hb_ucp_sys.h`
6. 输入填充 0

**回答：**
```cpp
// 准备输入张量
int32_t input_count = 0;
CHECK(hbDNNGetInputCount(&input_count, model_handle));
std::vector<hbDNNTensor> input_tensors(input_count);
for (int32_t i = 0; i < input_count; ++i) {
  hbDNNTensor &input_tensor = input_tensors[i];
  CHECK(hbDNNGetInputTensorProperties(&input_tensor.properties, model_handle, i));

  // 动态 Stride 处理（NV12 输入）
  for (int32_t j = input_tensor.properties.validShape.numDimensions - 1; j >= 0; --j) {
    if (input_tensor.properties.stride[j] == -1) {
      const int64_t next_stride = input_tensor.properties.stride[j + 1];
      const int64_t next_dim = input_tensor.properties.validShape.dimensionSize[j + 1];
      input_tensor.properties.stride[j] = ALIGN_64(next_stride * next_dim);
    }
  }

  int64_t mem_size = input_tensor.properties.stride[0] * input_tensor.properties.validShape.dimensionSize[0];
  CHECK(hbUCPMallocCached(&input_tensor.sysMem, mem_size, 0));
  memset(input_tensor.sysMem.virAddr, 0, mem_size);
}

// 准备输出张量
int32_t output_count = 0;
CHECK(hbDNNGetOutputCount(&output_count, model_handle));
std::vector<hbDNNTensor> output_tensors(output_count);
for (int32_t i = 0; i < output_count; ++i) {
  CHECK(hbDNNGetOutputTensorProperties(&output_tensors[i].properties, model_handle, i));
  CHECK(hbUCPMallocCached(&output_tensors[i].sysMem, output_tensors[i].properties.alignedByteSize, 0));
}
```

---

## Q3: 添加执行模型推理的逻辑，假设推理 10 轮次

**用户需求：** 补全 Step 03（缓存刷新）和 Step 04（执行推理）逻辑。

**思考过程：**
1. 阅读 Step 03 和 Step 04 文档
2. Step 03：输入数据需要 `hbUCPMemFlush(CLEAN)`
3. Step 04：使用异步执行分支，推理 10 轮次
4. 添加头文件 `hobot/hb_ucp.h`

**回答：**
```cpp
// 执行推理 10 轮次
for (int32_t iter = 0; iter < 10; ++iter) {
  // Step 03: 缓存刷新
  for (int32_t i = 0; i < input_count; ++i) {
    CHECK(hbUCPMemFlush(&input_tensors[i].sysMem, HB_SYS_MEM_CACHE_CLEAN));
  }

  // Step 04: 执行推理（异步）
  hbUCPTaskHandle_t task_handle = nullptr;
  CHECK(hbDNNInferV2(&task_handle, output_tensors.data(), input_tensors.data(), model_handle));

  hbUCPSchedParam ctrl_param;
  HB_UCP_INITIALIZE_SCHED_PARAM(&ctrl_param);
  ctrl_param.backend = HB_UCP_BPU_CORE_ANY;
  CHECK(hbUCPSubmitTask(task_handle, &ctrl_param));

  CHECK(hbUCPWaitTaskDone(task_handle, 0));
  CHECK(hbUCPReleaseTask(task_handle));
}
```

---

## Q4: 我的模型为 J6P 上的 3 核模型，需要改动代码哪些地方做适配

**用户需求：** 确认 J6P 多核模型是否需要特殊处理。

**思考过程：**
1. 根据文档，多核模型需要显式指定 BPU 核心
2. 当前代码使用 `HB_UCP_BPU_CORE_ANY`，需改为指定 3 个核心

**回答：**

是的，J6P 多核模型需要明确指定使用的 BPU 核心：

```cpp
ctrl_param.backend = HB_UCP_BPU_CORE_0 | HB_UCP_BPU_CORE_1 | HB_UCP_BPU_CORE_2;
```

| 配置 | 适用场景 |
|------|----------|
| `HB_UCP_BPU_CORE_ANY` | 单核模型，让系统自动选择 |
| 显式指定核心 | 多核模型，必须明确指定核心组合 |

---

## Q5: 模型输出仅有一个张量，形状为 [1, 1000]，元素类型为 float32，代表分类概率，帮我做下后处理部分

**用户需求：** 补全 Step 05 后处理逻辑。

**思考过程：**
1. 阅读 Step 05 文档
2. 输出读取前需要 `hbUCPMemFlush(INVALIDATE)`
3. 遍历 1000 个概率值，找最大值对应的索引

**回答：**
```cpp
// Step 05: 后处理 - 获取分类结果
CHECK(hbUCPMemFlush(&output_tensors[0].sysMem, HB_SYS_MEM_CACHE_INVALIDATE));
float *prob = reinterpret_cast<float *>(output_tensors[0].sysMem.virAddr);

int32_t max_idx = 0;
float max_prob = prob[0];
for (int32_t i = 1; i < 1000; ++i) {
  if (prob[i] > max_prob) {
    max_prob = prob[i];
    max_idx = i;
  }
}
```

---

## Q6: 资源释放如何做

**用户需求：** 补全 Step 06 资源释放逻辑。

**思考过程：**
1. 阅读 Step 06 文档
2. 释放模型：`hbDNNRelease`
3. 释放张量内存：`hbUCPFree`

**回答：**
```cpp
// Step 06: 资源释放
CHECK(hbDNNRelease(packed_handle));

for (hbDNNTensor &input_tensor : input_tensors) {
  CHECK(hbUCPFree(&input_tensor.sysMem));
}
for (hbDNNTensor &output_tensor : output_tensors) {
  CHECK(hbUCPFree(&output_tensor.sysMem));
}
```

---

## Q7: 假如输入是 Resizer 场景呢

**用户需求：** 适配 Resizer 输入场景。

**思考过程：**
1. Resizer 场景属于动态 Shape + 动态 Stride
2. 需要用户指定输入 Shape
3. 先填充动态 Shape，再计算动态 Stride

**回答：**

Resizer 场景与 NV12 场景的区别：

| 场景 | Shape | Stride | 处理方式 |
|------|-------|--------|----------|
| NV12 | 静态 | 动态 | 仅计算 Stride |
| Resizer | 动态 | 动态 | 先填充 Shape，再计算 Stride |

需要用户提供 Resizer 输入的实际 Shape。

---

## Q8: 第一个输入是 Y:[1,224,224,1]，第二个输入是 UV:[1,112,112,2]，第三个输入是 ROI:[1,4]，ROI 填 0, 0, 112, 112 即可

**用户需求：** 根据具体 Shape 配置 Resizer 输入。

**补充信息：** ROI 为 int32 类型。

**思考过程：**
1. 三个输入张量：Y、UV、ROI
2. ROI 数据类型为 int32
3. 使用动态 Shape + 动态 Stride 分支
4. 先填充动态 Shape，再计算动态 Stride
5. ROI 输入填充具体数据

**回答：**
```cpp
// Resizer 输入 Shape 配置
const int64_t input_shapes[3][4] = {
  {1, 224, 224, 1},  // Y
  {1, 112, 112, 2},  // UV
  {1, 4, 1, 1}       // ROI (需要补齐到4维)
};
const int32_t roi_data[4] = {0, 0, 112, 112};

// 准备输入张量（Resizer 场景：动态 Shape + 动态 Stride）
for (int32_t i = 0; i < input_count; ++i) {
  hbDNNTensor &input_tensor = input_tensors[i];
  CHECK(hbDNNGetInputTensorProperties(&input_tensor.properties, model_handle, i));

  // 填充动态 Shape
  for (int32_t j = 0; j < input_tensor.properties.validShape.numDimensions; ++j) {
    if (input_tensor.properties.validShape.dimensionSize[j] == -1) {
      input_tensor.properties.validShape.dimensionSize[j] = input_shapes[i][j];
    }
  }

  // 动态 Stride 处理（从后向前计算）
  for (int32_t j = input_tensor.properties.validShape.numDimensions - 1; j >= 0; --j) {
    if (input_tensor.properties.stride[j] == -1) {
      const int64_t next_stride = input_tensor.properties.stride[j + 1];
      const int64_t next_dim = input_tensor.properties.validShape.dimensionSize[j + 1];
      input_tensor.properties.stride[j] = ALIGN_64(next_stride * next_dim);
    }
  }

  int64_t mem_size = input_tensor.properties.stride[0] * input_tensor.properties.validShape.dimensionSize[0];
  CHECK(hbUCPMallocCached(&input_tensor.sysMem, mem_size, 0));

  // ROI 输入填充具体数据
  if (i == 2) {
    memcpy(input_tensor.sysMem.virAddr, roi_data, sizeof(roi_data));
  } else {
    memset(input_tensor.sysMem.virAddr, 0, mem_size);
  }
}
```

---

## Q9: 假如模型文件中有两个模型，分别为 resnet50_resizer_0 和 resnet50_resizer_1，我想同时推理这两个模型

**用户需求：** 多模型合批推理。

**思考过程：**
1. 使用 Step 04 分支3（多模型合批）
2. 从同一个 `packed_handle` 获取两个 `model_handle`
3. 两个模型各自准备输入/输出张量
4. 使用同一个 `task_handle` 打包多个推理任务
5. 只需一次提交、等待、释放

**回答：**
```cpp
// Step 01: 获取两个模型句柄
hbDNNHandle_t model_handles[2] = {nullptr, nullptr};
CHECK(hbDNNGetModelHandle(&model_handles[0], packed_handle, model_names[0].c_str()));
CHECK(hbDNNGetModelHandle(&model_handles[1], packed_handle, model_names[1].c_str()));

// Step 02: 两个模型各自准备输入输出张量
std::vector<hbDNNTensor> input_tensors[2];
std::vector<hbDNNTensor> output_tensors[2];
// ... (每个模型分别准备)

// Step 04: 多模型合批推理
hbUCPTaskHandle_t task_handle = nullptr;
CHECK(hbDNNInferV2(&task_handle, output_tensors[0].data(), input_tensors[0].data(), model_handles[0]));
CHECK(hbDNNInferV2(&task_handle, output_tensors[1].data(), input_tensors[1].data(), model_handles[1]));

hbUCPSchedParam ctrl_param;
HB_UCP_INITIALIZE_SCHED_PARAM(&ctrl_param);
ctrl_param.backend = HB_UCP_BPU_CORE_0 | HB_UCP_BPU_CORE_1 | HB_UCP_BPU_CORE_2;
CHECK(hbUCPSubmitTask(task_handle, &ctrl_param));

CHECK(hbUCPWaitTaskDone(task_handle, 0));
CHECK(hbUCPReleaseTask(task_handle));
```

**优势：**
- 两个模型在同一个任务中并行执行
- 减少任务提交开销
- 充分利用多核 BPU 资源

---

## Q10: 修改为同步执行推理任务

**用户需求：** 将异步执行改为同步执行。

**思考过程：**
1. 同步执行只需将 `task_handle` 传 nullptr
2. 接口返回即完成，无需 submit/wait/release

**回答：**
```cpp
// 同步执行
CHECK(hbDNNInferV2(nullptr, output_tensors[0].data(), input_tensors[0].data(), model_handles[0]));
CHECK(hbDNNInferV2(nullptr, output_tensors[1].data(), input_tensors[1].data(), model_handles[1]));
```

**注意：** 同步模式下两个模型串行执行，无法并行。

---

## Q11: 那就不应该同步推理吧，回退吧

**用户需求：** 回退到异步模式。

**回答：**

已回退。多模型合批场景下异步执行的优势：
- **并行执行**：两个模型同时运行
- **充分利用资源**：3核 BPU 可同时处理
- **减少开销**：只需一次提交/等待/释放

---

## Q12: 解释下内存刷新规则

**用户需求：** 解释 `hbUCPMemFlush` 的使用规则。

**回答：**

### 缓存刷新规则

| 场景 | Flag | 含义 |
|------|------|------|
| 输入数据 | `HB_SYS_MEM_CACHE_CLEAN` (2) | CPU 写 → BPU 读 |
| 输出数据 | `HB_SYS_MEM_CACHE_INVALIDATE` (1) | BPU 写 → CPU 读 |

### 原理图

```
┌─────────────┐         ┌─────────────┐
│     CPU     │         │     BPU     │
│  (写入缓存)  │         │  (读取内存)  │
└──────┬──────┘         └──────┬──────┘
       │                       │
       │   CLEAN: 将 CPU 缓存   │
       │   数据写回内存         │
       ├──────────────────────►│
       │                       │
       │   INVALIDATE: 使 CPU  │
       │   缓存失效，强制从     │
       │◄──────────────────────┤
       │   内存重新读取         │
```

### 为什么需要？

- **CPU 和 BPU 共享内存**，但各有独立的缓存
- **CPU 写入**数据 → 数据可能在 CPU 缓存中 → `CLEAN` 写回内存 → BPU 才能正确读取
- **BPU 写入**结果 → CPU 缓存可能是旧数据 → `INVALIDATE` 使缓存失效 → CPU 才能读到正确结果

---

## Q13: 对于动态输出该如何处理呢

**用户需求：** 解释动态输出的处理方式。

**回答：**

### 动态输出场景

当输出张量的 `validShape` 或 `stride` 包含 `-1` 时，表示输出形状动态，推理完成后才能确定。

### 处理步骤

```
推理流程：创建任务 → 提交 → 等待完成 → 获取动态输出属性 → 释放任务
                                            ↑
                                    必须在释放前获取
```

### 代码示例

```cpp
CHECK(hbUCPWaitTaskDone(task_handle, 0));

// 获取动态输出的实际 properties（必须在释放任务前）
for (int32_t i = 0; i < output_count; ++i) {
  hbDNNTensorProperties actual_properties;
  CHECK(hbDNNGetTaskOutputTensorProperties(&actual_properties, task_handle, 0, i));
  // 使用 actual_properties.validShape 进行后处理
}

CHECK(hbUCPReleaseTask(task_handle));
```

### 关键 API

```cpp
int32_t hbDNNGetTaskOutputTensorProperties(
  hbDNNTensorProperties *properties,  // 输出：实际属性
  hbUCPTaskHandle_t taskHandle,       // 任务句柄
  int32_t subModelIdx,                // 子模型索引（多模型合批时）
  int32_t outputIndex                 // 输出张量索引
);
```

### 对比静态输出

| 项目 | 静态输出 | 动态输出 |
|------|----------|----------|
| 属性获取 | Step 02 预先获取 | Step 04 推理后获取 |
| 内存大小 | 已知 `alignedByteSize` | 需根据实际 shape 计算 |
| 获取时机 | 任意 | 任务完成后、释放前 |

---

## 总结

### 六步流程

| Step | 功能 | 关键 API | 执行时机 |
|------|------|----------|----------|
| 01 | 模型加载 | `hbDNNInitializeFromFiles`, `hbDNNGetModelHandle` | 初始化时 |
| 02 | 张量准备 | `hbDNNGetInputTensorProperties`, `hbUCPMallocCached` | 初始化时 |
| 03 | 缓存刷新 | `hbUCPMemFlush(CLEAN)` | 每帧推理前 |
| 04 | 执行推理 | `hbDNNInferV2`, `hbUCPSubmitTask`, `hbUCPWaitTaskDone` | 每帧推理 |
| 05 | 后处理 | `hbUCPMemFlush(INVALIDATE)` | 每帧推理后 |
| 06 | 资源释放 | `hbDNNRelease`, `hbUCPFree` | 程序退出时 |

### 输入场景对比

| 场景 | Shape | Stride | 分支 |
|------|-------|--------|------|
| 静态输入 | 静态 | 静态 | 直接使用 `alignedByteSize` |
| NV12 输入 | 静态 | 动态 | 仅计算 Stride |
| Resizer 输入 | 动态 | 动态 | 先填充 Shape，再计算 Stride |

### 执行模式对比

| 模式 | 特点 | 适用场景 |
|------|------|----------|
| 同步 | `task_handle` 传 nullptr，接口返回即完成 | 单模型、调试 |
| 异步 | 创建任务、提交、等待、释放 | 多模型合批、流水线 |
