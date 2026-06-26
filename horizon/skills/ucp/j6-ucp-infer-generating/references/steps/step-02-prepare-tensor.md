# Step 02 - 张量信息与内存申请

## 涉及头文件
- `hobot/dnn/hb_dnn.h`
- `hobot/hb_ucp_sys.h`

## 涉及 API
- `hbDNNGetInputCount`
  原型: `int32_t hbDNNGetInputCount(int32_t *inputCount, hbDNNHandle_t dnnHandle);`
  作用：获取模型输入张量数量。

- `hbDNNGetInputTensorProperties`
  原型: `int32_t hbDNNGetInputTensorProperties(hbDNNTensorProperties *properties, hbDNNHandle_t dnnHandle, int32_t inputIndex);`
  作用：获取指定输入张量属性。

- `hbDNNGetOutputCount`
  原型: `int32_t hbDNNGetOutputCount(int32_t *outputCount, hbDNNHandle_t dnnHandle);`
  作用：获取模型输出张量数量。

- `hbDNNGetOutputTensorProperties`
  原型: `int32_t hbDNNGetOutputTensorProperties(hbDNNTensorProperties *properties, hbDNNHandle_t dnnHandle, int32_t outputIndex);`
  作用：获取指定输出张量属性。

- `hbUCPMallocCached`
  原型: `int32_t hbUCPMallocCached(hbUCPSysMem *mem, uint64_t size, int32_t deviceId);`
  作用：分配可缓存系统内存。

- `hbDNNTensor`
  封装 DNN 张量内存与属性。

## 产出
- 已绑定 `sysMem` 的输入、输出 tensor 数组，供后续填充数据与 `hbDNNInferV2` 使用。

## 示例代码

### 1. 准备输入张量

NV12 输入，走动态 Stride 分支；Pyramid 输入，走动态 Stride 分支；Resizer 输入，走动态 Shape + 动态 Stride 分支。

NV12 输入场景中，模型中一般包含 Y、UV 两类张量，布局默认为 NHWC。

#### 分支 1：静态输入张量（默认）

```cpp
int32_t input_count = 0;
CHECK(hbDNNGetInputCount(&input_count, model_handle));
std::vector<hbDNNTensor> input_tensors(input_count);
for (int32_t input_index = 0; input_index < input_count; ++input_index) {
  hbDNNTensor &input_tensor = input_tensors[input_index];
  CHECK(hbDNNGetInputTensorProperties(&input_tensor.properties, model_handle, input_index));
  CHECK(hbUCPMallocCached(&input_tensor.sysMem, input_tensor.properties.alignedByteSize, 0));
}
```

#### 分支 2：动态 Stride

```cpp
int32_t input_count = 0;
CHECK(hbDNNGetInputCount(&input_count, model_handle));
std::vector<hbDNNTensor> input_tensors(input_count);
for (int32_t input_index = 0; input_index < input_count; ++input_index) {
  hbDNNTensor &input_tensor = input_tensors[input_index];
  CHECK(hbDNNGetInputTensorProperties(&input_tensor.properties, model_handle, input_index));

  // 填充动态 Stride（从后向前计算）
  for (int32_t i = input_tensor.properties.validShape.numDimensions - 1; i >= 0; --i) {
    if (input_tensor.properties.stride[i] == -1) {
      const int64_t next_stride = input_tensor.properties.stride[i + 1];
      const int64_t next_dim = input_tensor.properties.validShape.dimensionSize[i + 1];
      const int64_t cur_stride = next_stride * next_dim;
      // **分支**：J6P/H 按 64 对齐，其余按 32 对齐
      input_tensor.properties.stride[i] = ALIGN(cur_stride);
    }
  }

  // 计算内存大小（动态 Shape/Stride 场景下 alignedByteSize 可能为 -1）
  int64_t mem_size = input_tensor.properties.stride[0] * input_tensor.properties.validShape.dimensionSize[0];
  CHECK(hbUCPMallocCached(&input_tensor.sysMem, mem_size, 0));
}
```

#### 分支 3：动态 Shape + 动态 Stride

```cpp
int32_t input_count = 0;
CHECK(hbDNNGetInputCount(&input_count, model_handle));
std::vector<hbDNNTensor> input_tensors(input_count);
for (int32_t input_index = 0; input_index < input_count; ++input_index) {
  hbDNNTensor &input_tensor = input_tensors[input_index];
  CHECK(hbDNNGetInputTensorProperties(&input_tensor.properties, model_handle, input_index));

  // 填充动态 Shape
  for (int32_t i = 0; i < input_tensor.properties.validShape.numDimensions; ++i) {
    if (input_tensor.properties.validShape.dimensionSize[i] == -1) {
      input_tensor.properties.validShape.dimensionSize[i] = user_shape[i];
    }
  }

  // 填充动态 Stride（从后向前计算）
  for (int32_t i = input_tensor.properties.validShape.numDimensions - 1; i >= 0; --i) {
    if (input_tensor.properties.stride[i] == -1) {
      const int64_t next_stride = input_tensor.properties.stride[i + 1];
      const int64_t next_dim = input_tensor.properties.validShape.dimensionSize[i + 1];
      const int64_t cur_stride = next_stride * next_dim;
      // **分支**：J6P/H 按 64 对齐，其余按 32 对齐
      input_tensor.properties.stride[i] = ALIGN(cur_stride);
    }
  }

  // 计算内存大小（动态 Shape/Stride 场景下 alignedByteSize 可能为 -1）
  int64_t mem_size = input_tensor.properties.stride[0] * input_tensor.properties.validShape.dimensionSize[0];
  CHECK(hbUCPMallocCached(&input_tensor.sysMem, mem_size, 0));
}
```

### 2. 准备输出张量

```cpp
int32_t output_count = 0;
CHECK(hbDNNGetOutputCount(&output_count, model_handle));
std::vector<hbDNNTensor> output_tensors(output_count);
for (int32_t output_index = 0; output_index < output_count; ++output_index) {
  hbDNNTensor &output_tensor = output_tensors[output_index];
  CHECK(hbDNNGetOutputTensorProperties(&output_tensor.properties, model_handle, output_index));
  CHECK(hbUCPMallocCached(&output_tensor.sysMem, output_tensor.properties.alignedByteSize, 0));
}
```
