# UCP Trace 抓取示例

## 示例 1：In-Process 模式抓取 UCP trace

**用户问题**：抓取 UCP Trace，采用 In-Process 模式，开发板：10.103.53.177，远程工作区：/map/lidong.guo/output_shared_J6_aarch64/aarch64/bin，App 启动命令：export LD_LIBRARY_PATH=../lib:$LD_LIBRARY_PATH && ./hrt_model_exec perf --model_file googlenet_224x224_nv12.hbm --frame_count=2000 --thread_num=12，抓取时长 15s。

**Step 1**: 修改配置文件中的 duration_ms 为 15000

**Step 2**: 传输配置文件

```bash
scp reference/ucp_in_process.json reference/ucp_in_process.cfg root@10.103.53.177:/map/lidong.guo/output_shared_J6_aarch64/aarch64/bin/
```

**Step 3**: SSH 到开发板执行抓取

```bash
ssh root@10.103.53.177 << 'EOF'
cd /map/lidong.guo/output_shared_J6_aarch64/aarch64/bin
rm -f ucp.pftrace
export HB_UCP_PERFETTO_CONFIG_PATH=ucp_in_process.json
export HB_UCP_ENABLE_PERFETTO=true
export LD_LIBRARY_PATH=../lib:$LD_LIBRARY_PATH
./hrt_model_exec perf --model_file googlenet_224x224_nv12.hbm --frame_count=2000 --thread_num=12
EOF
```

**Step 4**: 拉取 trace 文件

```bash
scp root@10.103.53.177:/map/lidong.guo/output_shared_J6_aarch64/aarch64/bin/ucp.pftrace ./
```

**结果**: 抓取 15s，处理 2000 帧，帧率 15930 FPS，输出文件 3.4MB

---

## 示例 2：启用 BPU Trace

**用户问题**：抓取 UCP Trace，启用 BPU Trace，开发板：10.103.53.177，远程工作区：/map/lidong.guo/output_shared_J6_aarch64/aarch64/bin，App 启动命令：export LD_LIBRARY_PATH=../lib:$LD_LIBRARY_PATH && ./hrt_model_exec perf --model_file googlenet_224x224_nv12.hbm --frame_count=2000 --thread_num=12，抓取时长 15s。

**Step 1**: 修改 ucp_system.cfg 中的 duration_ms 为 15000

**Step 2**: 传输配置文件

```bash
scp reference/ucp_system.json reference/ucp_system.cfg root@10.103.53.177:/map/lidong.guo/output_shared_J6_aarch64/aarch64/bin/
```

**Step 3**: 执行抓取

```bash
ssh root@10.103.53.177 << 'EOF'
cd /map/lidong.guo/output_shared_J6_aarch64/aarch64/bin
rm -f ucp.pftrace
pkill -f "tracebox" 2>/dev/null || true
sleep 1

tracebox traced --background
tracebox traced_probes --background --reset-ftrace

BPU_CORE_NUM=$(cat /sys/devices/system/bpu/core_num)
for i in $(seq 0 $(expr $BPU_CORE_NUM - 1)); do
    echo 0 > /sys/devices/system/bpu/bpu${i}/power_enable 2>/dev/null || true
    echo 1 > /sys/devices/system/bpu/bpu${i}/trace
done

tracebox perfetto --txt -c ucp_system.cfg -o ucp.pftrace &
PERFETTO_PID=$!

export HB_UCP_PERFETTO_CONFIG_PATH=ucp_system.json
export HB_UCP_ENABLE_PERFETTO=true
export LD_LIBRARY_PATH=../lib:$LD_LIBRARY_PATH
./hrt_model_exec perf --model_file googlenet_224x224_nv12.hbm --frame_count=2000 --thread_num=12

wait $PERFETTO_PID

for i in $(seq 0 $(expr $BPU_CORE_NUM - 1)); do
    echo 0 > /sys/devices/system/bpu/bpu${i}/trace
done
EOF
```

**Step 4**: 拉取 trace 文件

```bash
scp root@10.103.53.177:/map/lidong.guo/output_shared_J6_aarch64/aarch64/bin/ucp.pftrace ./ucp_bpu.pftrace
```

**结果**: 抓取 15s，处理 2000 帧，帧率 14794 FPS，输出文件 8.6MB

---


## 常见问题

| 问题 | 解决 |
|------|------|
| `hrt_model_exec: command not found` | 使用完整路径 `./hrt_model_exec` |
| trace 文件已存在 | 抓取前执行 `rm -f ucp.pftrace` |
| trace 为空或 0 字节 | 环境变量必须在同一个 SSH session 中设置 |
| 旧进程干扰 | 抓取前执行 `pkill -f "tracebox"` |

## 查看 trace

- **标准 trace**: 使用 [Perfetto UI](https://ui.perfetto.dev/)
- **BPU trace**: 需要 `hbperfetto` 工具（联系 Horizon 支持）

## Perfetto UI 快捷键

| 快捷键 | 功能 |
|--------|------|
| `w` / `s` | 缩放 |
| `a` / `d` | 左右平移 |
| `?` | 帮助 |
