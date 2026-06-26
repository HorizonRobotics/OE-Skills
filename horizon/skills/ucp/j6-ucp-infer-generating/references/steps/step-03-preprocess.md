# Step 03 - 预处理（数据填充与缓存刷新）

## 涉及头文件
- `hobot/hb_ucp_sys.h`

## 涉及 API
- `hbUCPMemFlush`
  原型: `int32_t hbUCPMemFlush(hbUCPSysMem const *mem, int32_t flag);`
  作用：执行内存缓存维护操作。

- `hbUCPSysMemFlushFlag`
  定义缓存维护操作类型。枚举值：`HB_SYS_MEM_CACHE_INVALIDATE = 1`、`HB_SYS_MEM_CACHE_CLEAN = 2`。

## 产出
- 内容已就绪且已 flush 的输入 tensor，可传入 `hbDNNInferV2`。

## 示例代码

CPU 写入后执行 cache flush，保证设备侧能读到一致数据。将输入数据写入 `input_tensor.sysMem.virAddr`，然后执行 `hbUCPMemFlush`（CPU 写 → BPU 读，使用 `HB_SYS_MEM_CACHE_CLEAN`）。

```cpp
for (int32_t input_index = 0; input_index < input_count; ++input_index) {
  // Step 1: 填充用户输入数据

  // Step 2: Flush 每个输入张量内存，CPU 写 -> BPU 读，执行 CLEAN
  hbDNNTensor &input_tensor = input_tensors[input_index];
  CHECK(hbUCPMemFlush(&input_tensor.sysMem, HB_SYS_MEM_CACHE_CLEAN));
}
```
