# Step 05 - 输出解析

## 涉及头文件
- `hobot/dnn/hb_dnn.h`
- `hobot/hb_ucp_sys.h`

## 涉及 API
- `hbDNNTensor`
  封装 DNN 张量内存与属性。

- `hbDNNTensorProperties`
  描述张量属性（形状、类型、量化、对齐、stride）。

- `hbUCPMemFlush`
  原型: `int32_t hbUCPMemFlush(hbUCPSysMem const *mem, int32_t flag);`
  作用：执行内存缓存维护操作。

## 产出
- 输出指针 + shape/type 等元信息。

## 示例代码

在异步路径中，要确保此步骤发生在任务完成之后。输出读取前执行内存一致性处理（BPU 写 -> CPU 读，执行 INVALIDATE）。

```cpp
for (int32_t output_index = 0; output_index < output_count; ++output_index) {
  // Step 1: Flush 每个输出张量内存，BPU 写 -> CPU 读，执行 INVALIDATE
  hbDNNTensor &output_tensor = output_tensors[output_index];
  CHECK(hbUCPMemFlush(&output_tensor.sysMem, HB_SYS_MEM_CACHE_INVALIDATE));

  // Step 2: 读取输出转换为对应类型（示例为 float），根据输出张量属性进入后处理程序
  float *output_data_ptr = reinterpret_cast<float *>(output_tensor.sysMem.virAddr);
}
```
