# 板端部署预检参考

> 从 j6-board-monitor SKILL.md 拆出，部署模型（尤其是 LLM 模型）到板端前按需加载。

## 部署前检查清单

在部署模型到板端之前，必须验证以下条件。跳过预检可能导致模型加载失败、内存溢出或 BPU 资源不足。

### 1. ION 内存容量检查

通过 SSH 检查板端可用 ION 内存：

```bash
ssh root@<board_ip> "cat /sys/kernel/debug/ion/heaps/system"
```

板端 ION 内存参考值：

| 板端 | 总 ION | CMA heap 单次分配上限 | 实际可用（模型+KV cache） |
|------|--------|---------------------|------------------------|
| J6P (nash-p) | ~4GB | ~2GB | ~3.5GB（系统占用约 500MB） |
| J6E/J6M (nash-e/m) | ~2GB | ~1GB | ~1.5GB |

### 2. 模型内存需求估算

模型板端内存占用 = 模型文件大小 + KV cache + 运行时开销

**模型文件大小**：直接查看 `.hbm` 文件大小。2B 参数模型 W8 量化约 2.5GB，1B 参数约 1.2GB。

**KV cache 大小**（参考值，取决于模型维度和 `max_kvcache_len`）：

| 模型 | cache_512 | cache_1024 | cache_2048 |
|------|-----------|------------|------------|
| Qwen3-VL-2B | ~0.66GB | ~1.3GB | ~2.6GB |
| Qwen2.5-VL-7B | ~1.8GB | ~3.6GB | - |
| InternVL-1B/2B | ~0.3GB | ~0.6GB | ~1.2GB |

**运行时开销**：约 200-400MB（包括 BPU 调度器、DMA 缓冲区等）。

**判断公式**：
```
模型.hbm大小 + KV_cache(对应cache_len) + 0.4GB < 板端可用ION
```

不满足时 → 减小 `max_kvcache_len` 重新编译，或换更大内存的板端。

### 3. 模型-板端兼容性矩阵

| 模型 | 最小板端 | 推荐 max_kvcache_len | core_num | L2M 配置 | 备注 |
|------|---------|---------------------|----------|---------|------|
| Qwen3-VL-2B (W8) | J6P (4核) | 512 (ION<4GB) / 1024 (ION≥4GB) | 4 | 6:6:6:6 | 模型约 2.5GB |
| Qwen2.5-VL-7B (W8) | J6P (4核) | 512 | 4 | 6:6:6:6 | 模型约 7GB，需分片 |
| InternVL-1B (W8) | J6E 或 J6P | 512 | 1 | 24:0:0:0 | 模型约 1.2GB |
| InternVL-2B (W8) | J6E 或 J6P | 512 | 1 | 24:0:0:0 | 模型约 2GB |

### 4. HB_DNN_USER_DEFINED_L2M_SIZES 配置

此环境变量控制 BPU L2 内存的分配方式，**必须与编译时的 `core_num` 匹配**：

| core_num | L2M 配置 | 适用模型 |
|----------|---------|---------|
| 1 | `24:0:0:0` | 单核模型（InternVL-1B/2B 等小模型） |
| 4 | `6:6:6:6` | 四核模型（Qwen3-VL-2B、Qwen2.5-VL-7B 等） |

**运行时 JSON 配置**的 `backends` 字段也必须匹配：

```json
{
  "backends": {
    "vit": [1,2,3,4],
    "prefill": [1,2,3,4],
    "decode": [1,2,3,4]
  }
}
```

core_num=1 时 backends 应为 `[1]`，core_num=4 时为 `[1,2,3,4]`。

**不匹配的后果**：模型加载时报 `L2M size mismatch` 错误或静默降级到单核运行（性能大幅下降）。

### 5. 检查失败时的处理

| 检查项 | 失败原因 | 处理方式 |
|--------|---------|---------|
| ION 不足 | 模型+KV cache 超过可用 ION | 减小 `max_kvcache_len` 重新编译；或换更大内存的板端 |
| L2M 不匹配 | 运行时 L2M 与编译时 core_num 不一致 | 修改 `remote_environment.HB_DNN_USER_DEFINED_L2M_SIZES` 或重新编译 |
| 板端连接失败 | SSH 不可达 | 检查 IP、网络、密钥认证 |
| 模型文件传输失败 | 磁盘空间不足 | 清理 `BOARD_WORKDIR` 下的旧模型文件 |

### 6. 循环推理脚本模板

板端资源监控（`j6-board-monitor` Scenario A）需要模型在监控期间持续推理。标准的循环推理方式：

```bash
# 部署到板端后，在板端执行循环推理
while true; do
  ./simple_demo_request --config_path config.json --image_path test.jpg 2>/dev/null
done
```

或使用 `oellm_batch_request` 示例程序进行批量推理。监控工具（`hrt_ucp_monitor`）在本地通过 SSH 启动，采集 BPU/DDR/内存数据。
