# Step 06 - 资源释放

## 涉及头文件
- `hobot/dnn/hb_dnn.h`
- `hobot/hb_ucp_sys.h`

## 涉及 API
- `hbUCPFree`
  原型: `int32_t hbUCPFree(hbUCPSysMem *mem);`
  作用：释放 UCP 分配的系统内存。

- `hbDNNRelease`
  原型: `int32_t hbDNNRelease(hbDNNPackedHandle_t dnnPackedHandle);`
  作用：释放 packed handle 关联的模型资源。

## 产出
- 完整资源回收，支持安全退出或下一轮推理。

## 示例代码

无泄漏地释放内存与模型资源。释放前确保关联任务已结束。

```cpp
// Step 1: 释放模型
CHECK(hbDNNRelease(packed_handle));

// Step 2: 释放输入输出内存
for (hbDNNTensor &input_tensor : input_tensors) {
  CHECK(hbUCPFree(&input_tensor.sysMem));
}
for (hbDNNTensor &output_tensor : output_tensors) {
  CHECK(hbUCPFree(&output_tensor.sysMem));
}
```
