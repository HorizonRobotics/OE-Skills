# Board Monitor — 技术参考

## hrt_ucp_monitor 参数详解

板端实时监控工具，采集 BPU 占用率、DDR 带宽、内存使用等数据。

### 参数列表

| 参数 | 短格式 | 类型 | 默认值 | 范围 | 说明 |
|------|--------|------|--------|------|------|
| --batch | -b | flag | interactive | - | 批处理模式，输出适合文件重定向 |
| --delay | -d | int | 1000 | [100, 10000] | 刷新间隔 (ms) |
| --enable | -e | string | all | bpu,dsp,memory | 启用指定监控类型，逗号分隔 |
| --freq | -f | int | 500 | [10, 1000] | BPU/DSP 采样频率 (Hz) |
| --number | -n | int | 0(无限) | >0 | 最大刷新次数，**必须指定以避免无限运行** |
| --time | -t | int | 0(无限) | >0 | 运行时间 (秒) |
| --verbose | -v | flag | - | - | 显示额外调试信息 |

### 输出字段说明

**BPU Utilization 段**：
```
BPU Utilization:
  Core 0: busy=85.2%  idle=14.8%
  Core 1: busy=72.1%  idle=27.9%
```

**DDR Bandwidth 段**：
```
DDR Bandwidth:
  Read:  2048.5 MiB/s
  Write: 1024.3 MiB/s
```

**ION Memory 段**：
```
ION Memory:
  uncache: 256 MB
```

**Process Memory 段**：
```
Process Memory:
  hrt_model_exec: RSS=128 MB
```

### 使用示例

```bash
# 监控 BPU + 内存，每秒采样一次，共 30 次
hrt_ucp_monitor -b -e bpu,memory -d 1000 -n 30 -f 500 > ucp_monitor.txt

# 仅监控 BPU，500ms 间隔，共 60 次
hrt_ucp_monitor -b -e bpu -d 500 -n 60 -f 500 > ucp_monitor.txt
```

---

## hrut_ddr 参数详解

DDR 带宽采集工具，按指定周期采样 DDR 读写带宽并输出 CSV。

### 参数列表

| 参数 | 短格式 | 类型 | 默认值 | 范围 | 说明 |
|------|--------|------|--------|------|------|
| --type | -t | string | (必填) | bpu, bpu_p0, bpu_p1, cpu, mcu | 监控目标类型 |
| --period | -p | int | 1000 | [1000, 2000000] | 采样周期 (μs)，推荐 1000000 (1秒) |
| --device | -d | string/int | 0 | J6E:[0-5], J6P:[0-15] | DDR 设备号，多设备用空格分隔 |
| --csv | -c | flag | - | - | CSV 格式输出 |
| --filename | -f | string | stdout | - | CSV 输出文件路径 |
| --number | -n | int | 0(无限) | >0 | 采样次数，**必须指定** |
| --raw | -r | flag | - | - | 输出原始十六进制数据 |

### CSV 输出格式

```csv
timestamp,read_MiB/s,write_MiB/s
1699000000,2048.5,1024.3
1699000001,2100.1,980.7
...
```

### 使用示例

```bash
# J6E: 监控 BPU DDR 带宽，每秒采样，共 30 次
hrut_ddr -t bpu -p 1000000 -n 30 -c -f ddr_bandwidth.csv

# J6P: 监控 BPU core 0 的 DDR 带宽
hrut_ddr -t bpu_p0 -p 1000000 -n 30 -c -f ddr_bandwidth.csv

# J6P: 监控多设备 DDR 带宽
hrut_ddr -d "0 1 2 3" -t bpu_p0 -p 1000000 -n 30 -c -f ddr_bandwidth.csv
```

---

## 平台差异对照表

| 特性 | J6E (nash-e/nash-m) | J6P (nash-p) |
|------|---------------------|-------------|
| hrut_ddr `-t` 参数 | `bpu` | `bpu_p0` (core 0), `bpu_p1` (core 1) |
| BPU 核心数 | 1 (2 logical) | 4 |
| hrut_ddr `-d` 范围 | [0-5] | [0-15] |
| 典型板端工作目录 | /map/oe-skill-test | /backhaul/oe-skill-test |
| hrt_ucp_monitor `-e bpu` | 监控全部 BPU | 监控全部 BPU |
| hrt_model_exec `--core_id` | 0 | 0-3 |

### 平台检测方法

```bash
# 从 .env.board 读取平台类型
BOARD_TYPE=$(grep '^BOARD_TYPE=' .horizon/.env.board | head -1 | cut -d= -f2)

if echo "$BOARD_TYPE" | grep -q "nash-p"; then
  # J6P
  DDR_TYPE="bpu_p0"
  BPU_CORES=4
  DDR_DEVICES="0 1 2 3"
else
  # J6E
  DDR_TYPE="bpu"
  BPU_CORES=1
  DDR_DEVICES="0"
fi
```

---

## hrt_model_exec 受控帧率推理

### 方法 1: Wrapper Script（推荐）

通过 shell 脚本在每次推理后用 `usleep` 补齐帧间隔，精确控制帧率：

```bash
#!/bin/sh
# run_at_fps.sh — 受控帧率推理 wrapper
# 用法: run_at_fps.sh <model_path> <target_fps> <frame_count> <core_id>
MODEL=$1
TARGET_FPS=$2
FRAME_COUNT=$3
CORE_ID=${4:-0}
INTERVAL_US=$((1000000 / TARGET_FPS))

i=0
while [ $i -lt $FRAME_COUNT ]; do
  START_NS=$(date +%s%N)
  hrt_model_exec perf --model_file="$MODEL" --frame_count=1 \
    --core_id=$CORE_ID --thread_num=1 2>/dev/null
  END_NS=$(date +%s%N)
  ELAPSED_US=$(( (END_NS - START_NS) / 1000 ))
  SLEEP_US=$((INTERVAL_US - ELAPSED_US))
  if [ $SLEEP_US -gt 0 ]; then
    usleep $SLEEP_US 2>/dev/null || sleep $(echo "scale=6; $SLEEP_US / 1000000" | bc)
  fi
  i=$((i + 1))
done
```

**优点**：无需修改源码，帧率精确，适配所有平台
**限制**：当单帧推理时间 > 1/FPS 秒时，无法达到目标帧率（此时实际帧率 = 推理吞吐量上限）

### 方法 2: --perf_fps 参数（需修改源码）

社区方案（参考 https://developer.horizon.auto/blog/13054），修改 `hrt_model_exec` 源码添加 `--perf_fps` 参数。需要 `LINARO_GCC_ROOT` 交叉编译器和 `build_aarch64.sh` 构建脚本。

**不推荐**：构建环境依赖复杂，容易失败。Wrapper script 方案更简单可靠。

### 为什么不能用 gRPC/hbm_infer

| 指标 | 板端 hrt_model_exec | 远程 gRPC/hbm_infer |
|------|---------------------|---------------------|
| 单帧延时 | <10ms (典型) | ~6800ms (ana-002 实测) |
| 通信开销 | 无 | ~6.8s/帧 |
| 10Hz 目标实际帧率 | ~10Hz | 0.148Hz (ana-002 实测) |
| 适用场景 | 板端实时监控 | 单次推理验证 |

**结论**：gRPC 通信开销约 6.8s/帧，无法达到 >0.15Hz 的实际帧率。**严禁在监控场景使用**。

---

## SSH 命令模板

### 连通性检查

```bash
ssh -o ConnectTimeout=5 root@<IP> "echo ok"
```

### 工具验证

```bash
ssh root@<IP> "which hrt_ucp_monitor && which hrut_ddr && which hrt_model_exec"
```

### 文件传输

```bash
# 上传模型
scp <local_model_path> root@<IP>:<BOARD_WORKDIR>/

# 上传 wrapper 脚本
scp /tmp/run_at_fps.sh root@<IP>:<BOARD_WORKDIR>/
ssh root@<IP> "chmod +x <BOARD_WORKDIR>/run_at_fps.sh"

# 拉取监控结果
scp root@<IP>:<BOARD_WORKDIR>/ucp_monitor.txt ./
scp root@<IP>:<BOARD_WORKDIR>/ddr_bandwidth.csv ./
scp root@<IP>:<BOARD_WORKDIR>/inference.log ./
```

### 后台启动推理

```bash
TOTAL_FRAMES=$((TARGET_FPS * MONITOR_DURATION_SEC))
ssh root@<IP> "cd <BOARD_WORKDIR> && nohup sh run_at_fps.sh <model> <fps> $TOTAL_FRAMES <core_id> > inference.log 2>&1 &"
```

### 启动监控（两轮执行）

> ⚠️ `hrut_ddr` 和 `hrt_ucp_monitor` 不能同时运行（设备文件互斥），必须分两轮启动。

```bash
# ═══ 第一轮：BPU + 内存监控 + 推理 ═══
ssh root@<IP> "
  hrt_ucp_monitor -b -e bpu,memory -d 1000 -n $MONITOR_DURATION -f 500 > <BOARD_WORKDIR>/ucp_monitor.txt 2>&1 &
  sleep 2
  cd <BOARD_WORKDIR> && nohup sh run_at_fps.sh <model> <fps> $TOTAL_FRAMES <core_id> > inference_pass1.log 2>&1 &
"

# 等待第一轮完成后执行第二轮

# ═══ 第二轮：DDR 带宽监控 + 推理 ═══
# DDR 带宽监控 (J6E)
ssh root@<IP> "
  hrut_ddr -t bpu -p 1000000 -n $MONITOR_DURATION -c -f <BOARD_WORKDIR>/ddr_bandwidth.csv 2>&1 &
  sleep 2
  cd <BOARD_WORKDIR> && nohup sh run_at_fps.sh <model> <fps> $TOTAL_FRAMES <core_id> > inference_pass2.log 2>&1 &
"

# DDR 带宽监控 (J6P)
ssh root@<IP> "
  hrut_ddr -t bpu_p0 -p 1000000 -n $MONITOR_DURATION -c -f <BOARD_WORKDIR>/ddr_bandwidth.csv 2>&1 &
  sleep 2
  cd <BOARD_WORKDIR> && nohup sh run_at_fps.sh <model> <fps> $TOTAL_FRAMES <core_id> > inference_pass2.log 2>&1 &
"
```

### 等待完成

```bash
# 单次 SSH 等待（非轮询）
EXPECTED_SEC=$((MONITOR_DURATION + 10))
ssh root@<IP> "sleep $EXPECTED_SEC && echo 'Collection complete'"
```

---

## 带宽计算方法

### hrut_ddr CSV 解析

```python
import csv

total_read = 0
total_write = 0
count = 0

with open('ddr_bandwidth.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        total_read += float(row['read_MiB/s'])
        total_write += float(row['write_MiB/s'])
        count += 1

avg_read = total_read / count if count > 0 else 0
avg_write = total_write / count if count > 0 else 0
avg_total_gb = (avg_read + avg_write) / 1024  # MiB/s → GB/s
```

### hrt_ucp_monitor 输出解析

Batch 模式下每次刷新输出完整数据块，提取 DDR Bandwidth 段：

```python
import re

read_values = []
write_values = []

with open('ucp_monitor.txt') as f:
    for line in f:
        m_read = re.search(r'Read:\s+([\d.]+)\s+MiB/s', line)
        m_write = re.search(r'Write:\s+([\d.]+)\s+MiB/s', line)
        if m_read:
            read_values.append(float(m_read.group(1)))
        if m_write:
            write_values.append(float(m_write.group(1)))
```

### BPU 利用率解析

```python
import re

bpu_busy = []

with open('ucp_monitor.txt') as f:
    for line in f:
        m = re.search(r'Core\s+\d+:\s+busy=([\d.]+)%', line)
        if m:
            bpu_busy.append(float(m.group(1)))

avg_bpu = sum(bpu_busy) / len(bpu_busy) if bpu_busy else 0
peak_bpu = max(bpu_busy) if bpu_busy else 0
```

---

## 工具互斥说明

`hrut_ddr` 和 `hrt_ucp_monitor` 都需要独占访问 DDR 性能计数器设备文件（内核驱动通过互斥锁保护）。同时运行时，后启动的工具会因为无法获取设备文件而报 `Error: Open failed!`。

**影响范围**：
- 无论是否有推理负载在运行，两个监控工具之间都会互相阻塞
- 空闲板子上单独运行 `hrut_ddr` 可以正常工作（已通过实测验证）
- 在推理负载运行期间同时启动两者，`hrut_ddr` 几乎必定失败

**数据精度差异**：
- `hrut_ddr`：直接读取硬件性能计数器，DDR 带宽数据精确（典型推理负载下 ~11 GB/s）
- `hrt_ucp_monitor`：DDR 带宽数据在推理负载下可能不准确（实测仅 ~200 MiB/s，与实际差距极大），但 BPU 占用率和内存数据可靠

**解决方案**：分两轮执行，每轮搭配相同推理负载：
1. 第一轮：`hrt_ucp_monitor` + 推理 → BPU 占用率 + 内存使用
2. 第二轮：`hrut_ddr` + 推理 → DDR 带宽（精确值）

---

## 常见问题

| 问题 | 症状 | 原因 | 解决 |
|------|------|------|------|
| hrut_ddr 打开失败 | `Error: Open failed!` | J6P 上使用了 `-t bpu` | 改用 `-t bpu_p0` |
| hrut_ddr 打开失败（参数正确） | `Error: Open failed!`，`-t` 参数已正确 | 与 `hrt_ucp_monitor` 同时运行，争夺设备文件互斥锁 | 分两轮执行（见「工具互斥说明」） |
| gRPC 推理太慢 | ~6.8s/帧 | 通信开销 | 改用板端 `hrt_model_exec` |
| 监控数据全零 | BPU 0%, DDR ~0 | 没有推理负载在运行 | 确认推理进程正在运行：`ps aux \| grep hrt_model_exec` |
| DDR 带宽异常低 | <100 MiB/s | 采样周期太短，数据不稳定 | 增大 `-p` 到 1000000 (1s) |
| hrt_ucp_monitor 无输出 | 命令挂起 | 未指定 `-b` 批处理模式 | 加上 `-b` 参数 |
| usleep 不可用 | `usleep: command not found` | 部分板端缺少 usleep | fallback: `sleep $(echo "scale=6; $US / 1000000" \| bc)` |
| SSH 连接超时 | `Connection timed out` | 网络不通或板端关机 | 检查网络、板端电源、IP 地址 |
| 监控工具不存在 | `command not found` | OE 包未正确部署 | 检查 `/opt/horizon/` 路径，或从 OE 包 `samples/ucp_tutorial/tools/` 部署 |
| wrapper 帧率达不到目标 | 实际 FPS < 目标 FPS | 单帧推理时间 > 1/FPS 秒 | 降低目标帧率，或使用多核并行 (`--thread_num`) |
