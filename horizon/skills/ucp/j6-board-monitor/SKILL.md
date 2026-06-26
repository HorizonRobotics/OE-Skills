---
name: j6-board-monitor
description: J6 开发板资源监控与推理期间资源采集。当用户需要监控 BPU 占用率、DDR 带宽、内存使用时触发。支持三种场景：(1) Scenario A：CV 模型在指定帧率（如 10Hz）推理期间同步采集 BPU/DDR/内存数据；(2) Scenario B：独立监控板端硬件资源（无推理负载）；(3) Scenario C：LLM 模型循环推理期间同步采集资源数据，使用 simple_demo_request 保持模型持续运行。关键词：BPU 监控、DDR 带宽、内存使用、资源监控、设定帧率推理、LLM 推理监控、hrt_ucp_monitor、hrut_ddr、simple_demo_request、板端资源评估。注意：不要用 hbm_infer/gRPC 做高频推理监控（通信开销太大）。
---

# Board Monitor

通过 SSH 在 J6 开发板上执行 BPU 占用率、DDR 带宽、内存使用的实时监控。支持三种场景：
- **Scenario A**：CV 模型在受控帧率推理期间同步采集资源数据（使用 `hrt_model_exec`）
- **Scenario B**：独立监控板端硬件资源（无推理负载）
- **Scenario C**：LLM 模型在循环推理期间同步采集资源数据（使用 `simple_demo_request`）

## 适用场景

- 在指定帧率（如 10Hz）推理时监控 BPU 占用率、DDR 带宽、内存使用
- 独立监控板端硬件资源（无推理负载）
- **LLM 模型板端推理期间的 BPU/DDR/内存监控**（循环推理 + 同步采集）
- 评估模型在实车设计帧率下的资源消耗
- 对比不同模型/配置的板端资源占用

触发关键词：BPU 监控、DDR 带宽、内存使用、资源监控、设定帧率、10Hz 推理、LLM 推理监控、LLM 资源、simple_demo_request、hrt_ucp_monitor、hrut_ddr

> **部署前预检**：部署模型到板端前，先阅读 `board-preflight.md` 检查 ION 内存容量、L2M 配置和模型-板端兼容性。

## 工作流程

严格按照以下 8 步顺序执行，不可跳步。

### 前置条件

开始工作流之前，确认以下条件满足：

1. **`.horizon/.env.board` 必须存在**：读取该文件获取 `BOARD_IP`、`BOARD_TYPE`、`BOARD_WORKDIR`。如果文件不存在或不完整，**先触发 `board-detection` skill 完成板卡检测**，再继续。
2. **SSH 免密登录**：本 skill 的所有 SSH/SCP 命令假设已配置免密登录（密钥认证）。如果 SSH 连接要求输入密码，提示用户先配置密钥认证或提供密码，然后在所有 `ssh`/`scp` 命令中通过 `sshpass -p <password>` 前缀传递。
3. **OE 工具链可用**：`hrt_ucp_monitor`、`hrut_ddr`、`hrt_model_exec` 须已部署到板端。Step 2 会验证这一点。

### Step 1：收集信息

从 `.env.board` 和用户输入收集以下信息。**优先从 `.env.board` 读取，仅在文件中缺少时才询问用户。**

| 项目 | 必填 | 默认值/来源 | 说明 |
|------|------|-------------|------|
| 板端 IP | 是 | `.env.board` → `BOARD_IP` | 优先从文件读取 |
| SSH 用户名 | 是 | `root` | |
| 认证方式 | 是 | 密钥（免密） | 见前置条件第 2 条 |
| 板端工作目录 | 是 | `.env.board` → `BOARD_WORKDIR` | 优先从文件读取 |
| 模型文件路径 | Scenario A 必填 | - | 板端路径或本地路径（本地路径需 SCP 上传） |
| 目标帧率 (FPS) | Scenario A 必填 | - | 如 10Hz、30Hz |
| 监控时长 (秒) | 否 | 30 | 采集持续时间 |
| 监控目标 | 否 | bpu,ddr,memory | 选择监控项 |

**场景自动检测**：
- 用户提供了 CV 模型（.hbm 较小、有明确 FPS 需求） → **Scenario A**（受控推理 + 同步监控）
- 用户仅提供监控需求 → **Scenario B**（独立监控，无推理负载）
- 用户提供了 LLM/VLM 模型（.hbm 较大、无 FPS 控制需求） → **Scenario C**（循环推理 + 同步监控）

**Scenario A vs C 判断依据**：
- 模型文件 > 500MB 或用户明确提到 LLM/VLM → Scenario C
- 模型文件 < 500MB 且有明确帧率要求（如 10Hz） → Scenario A

### Step 2：检查板卡连通性与平台

1. 读取 `.horizon/.env.board`，获取 `BOARD_TYPE`、`BOARD_IP`、`BOARD_WORKDIR`
2. SSH 连通性检查：`ssh -o ConnectTimeout=5 root@<IP> "echo ok"`
3. **平台检测**（决定 hrut_ddr 参数）：

```bash
# 读取平台类型
BOARD_TYPE=$(grep '^BOARD_TYPE=' .horizon/.env.board | head -1 | cut -d= -f2)

if echo "$BOARD_TYPE" | grep -q "nash-p"; then
  # J6P: 4 BPU cores, hrut_ddr 需要 per-core 参数
  DDR_TYPE="bpu_p0"
  BPU_CORES=4
else
  # J6E: 1 BPU core, hrut_ddr 使用统一参数
  DDR_TYPE="bpu"
  BPU_CORES=1
fi
```

4. 验证监控工具存在：

```bash
ssh root@<IP> "which hrt_ucp_monitor && which hrut_ddr && which hrt_model_exec"
```

- 如果工具不存在，提示用户检查 OE 包部署或从 `/opt/horizon/` 路径查找

5. **LD_LIBRARY_PATH 确认**：`hrt_model_exec` 依赖的 `.so` 库路径因部署方式不同而异。在板端检查实际路径：

```bash
ssh root@<IP> "ldd \$(which hrt_model_exec) 2>/dev/null | grep 'not found' || echo 'all libs found'"
```

- 默认路径：`/opt/horizon/lib:/opt/horizon/hbrt/lib`
- 自定义部署路径（如 `/map/.../output_shared_J6_aarch64/aarch64/lib`）：根据 `ldd` 输出确定
- Step 4 的 wrapper 脚本中 `LD_LIBRARY_PATH` 需与此处确认的路径一致

### Step 3：部署工具到板端

**Scenario A**（CV 推理 + 监控）：

1. 将模型文件部署到板端（如果模型在本地）：

```bash
scp <local_model_path> root@<IP>:<BOARD_WORKDIR>/
```

2. 生成 `run_at_fps.sh` wrapper 脚本并上传到板端（见 Step 4）

**Scenario C**（LLM 推理 + 监控）：

1. 将 LLM 模型文件（.hbm、embed_tokens.bin、tokenizer 文件）和推理配置文件（config.json）部署到板端：

```bash
scp <local_model_dir>/*.hbm root@<IP>:<BOARD_WORKDIR>/
scp <local_model_dir>/embed_tokens.bin root@<IP>:<BOARD_WORKDIR>/
scp <local_model_dir>/tokenizer* root@<IP>:<BOARD_WORKDIR>/
scp <config_json_path> root@<IP>:<BOARD_WORKDIR>/config.json
```

2. 部署 `simple_demo_request` 推理程序和测试图片到板端：

```bash
scp <simple_demo_request_path> root@<IP>:<BOARD_WORKDIR>/
scp <test_image_path> root@<IP>:<BOARD_WORKDIR>/test.jpg
ssh root@<IP> "chmod +x <BOARD_WORKDIR>/simple_demo_request"
```

3. 生成 `llm_loop_infer.sh` 循环推理脚本并上传到板端（见 Step 4 Scenario C 部分）

**Scenario B**（独立监控）：

- 跳过部署，直接进入 Step 5

### Step 4：启动推理脚本准备（Scenario A / C）

> **严禁使用 hbm_infer / gRPC 进行推理监控。** gRPC 通信开销约 6.8s/帧，无法达到 >0.15Hz 的实际帧率。必须在板端直接用 hrt_model_exec 执行。

生成 `run_at_fps.sh` wrapper 脚本，通过 `usleep` 控制帧间隔：

```bash
cat > /tmp/run_at_fps.sh << 'WRAPPER'
#!/bin/sh
# 受控帧率推理 wrapper
# 用法: run_at_fps.sh <model_path> <target_fps> <frame_count> <core_id>
MODEL=$1
TARGET_FPS=$2
FRAME_COUNT=$3
CORE_ID=${4:-0}
INTERVAL_US=$((1000000 / TARGET_FPS))

# 设置 LD_LIBRARY_PATH — hrt_model_exec 依赖的 .so 在板端 /opt/horizon/ 下
export LD_LIBRARY_PATH=/opt/horizon/lib:/opt/horizon/hbrt/lib:$LD_LIBRARY_PATH

i=0
while [ $i -lt $FRAME_COUNT ]; do
  START_NS=$(date +%s%N)
  hrt_model_exec perf --model_file="$MODEL" --frame_count=1 \
    --core_id=$CORE_ID --thread_num=1 2>/dev/null
  END_NS=$(date +%s%N)
  ELAPSED_US=$(( (END_NS - START_NS) / 1000 ))
  SLEEP_US=$((INTERVAL_US - ELAPSED_US))
  if [ $SLEEP_US -gt 0 ]; then usleep $SLEEP_US 2>/dev/null || sleep $(echo "scale=6; $SLEEP_US / 1000000" | bc); fi
  i=$((i + 1))
done
WRAPPER

# 上传到板端
scp /tmp/run_at_fps.sh root@<IP>:<BOARD_WORKDIR>/
ssh root@<IP> "chmod +x <BOARD_WORKDIR>/run_at_fps.sh"
```

**注意**：先不要启动推理。推理在 Step 5 启动监控之后再启动（见 Step 5 的执行顺序说明）。

#### 大模型加载开销处理

上述 `run_at_fps.sh` 模板假设每次 `hrt_model_exec` 调用的加载开销可忽略（`usleep` 可补偿帧间隔）。但**大模型**（如 >100MB 的 hbm 文件）每次加载需数秒（实测可达 3-5s），逐帧调用方案完全不可行。

**判断标准**：在 Step 2 连通性检查后，先做一次单帧推理测试：

```bash
ssh root@<IP> "cd ${BOARD_WORKDIR} && hrt_model_exec perf --model_file=${MODEL_PATH} --frame_count=1 --core_id=0 --thread_num=1 2>&1 | grep 'Load model'"
```

- 如果 `Load model to DDR cost` > 1000ms → **必须使用批量方案**
- 如果 < 500ms → 使用上述逐帧方案即可

**批量方案：单次加载 + 帧间 sleep**

模型只加载一次（`--frame_count=N`），根据单帧延时和目标帧率计算帧间 sleep 时间：

```bash
# 参数说明:
#   frame_latency_ms: 从单帧测试获取的推理延时（不含加载）
#   target_fps: 目标帧率
#   sleep_ms = (1000 / target_fps) - frame_latency_ms

cat > /tmp/run_at_fps_batch.sh << 'WRAPPER'
#!/bin/sh
# 批量受控帧率推理 — 适用于大模型（加载时间 >1s）
# 用法: run_at_fps_batch.sh <model_path> <target_fps> <frame_count> <core_id>
MODEL=$1
TARGET_FPS=$2
FRAME_COUNT=$3
CORE_ID=${4:-0}

export LD_LIBRARY_PATH=/opt/horizon/lib:/opt/horizon/hbrt/lib:$LD_LIBRARY_PATH

# Step 1: 先跑 1 帧测量单帧延时（含加载）
MEASURE_OUTPUT=$(hrt_model_exec perf --model_file="$MODEL" --frame_count=1 \
  --core_id=$CORE_ID --thread_num=1 2>&1)
echo "$MEASURE_OUTPUT"

# 从输出提取单帧延时（ms）— 根据实际输出格式调整
FRAME_LATENCY_MS=$(echo "$MEASURE_OUTPUT" | grep -oP 'avg.*?(\d+\.?\d*)' | grep -oP '\d+\.?\d*' | head -1)
FRAME_LATENCY_MS=${FRAME_LATENCY_MS:-80}  # 默认 80ms

# 计算帧间 sleep（微秒）
TARGET_INTERVAL_US=$((1000000 / TARGET_FPS))
FRAME_LATENCY_US=$((FRAME_LATENCY_MS * 1000))
SLEEP_US=$((TARGET_INTERVAL_US - FRAME_LATENCY_US))

echo "单帧延时: ${FRAME_LATENCY_MS}ms, 目标间隔: $((TARGET_INTERVAL_US / 1000))ms, 帧间 sleep: $((SLEEP_US / 1000))ms"

# Step 2: 分批推理 + 帧间 sleep
BATCH_SIZE=$((TARGET_FPS * 5))  # 每批 5 秒的帧数，摊薄加载开销
if [ $BATCH_SIZE -gt $FRAME_COUNT ]; then BATCH_SIZE=$FRAME_COUNT; fi

DONE=0
while [ $DONE -lt $FRAME_COUNT ]; do
  REMAINING=$((FRAME_COUNT - DONE))
  if [ $REMAINING -lt $BATCH_SIZE ]; then BATCH_SIZE=$REMAINING; fi

  hrt_model_exec perf --model_file="$MODEL" --frame_count=$BATCH_SIZE \
    --core_id=$CORE_ID --thread_num=1 2>/dev/null

  DONE=$((DONE + BATCH_SIZE))

  # batch 间 sleep 控制有效帧率
  BATCH_DURATION_US=$((BATCH_SIZE * FRAME_LATENCY_US))
  TARGET_BATCH_US=$((BATCH_SIZE * TARGET_INTERVAL_US))
  BATCH_SLEEP_US=$((TARGET_BATCH_US - BATCH_DURATION_US))
  if [ $BATCH_SLEEP_US -gt 0 ]; then
    usleep $BATCH_SLEEP_US 2>/dev/null || sleep $(echo "scale=6; $BATCH_SLEEP_US / 1000000" | bc)
  fi
done
WRAPPER

scp /tmp/run_at_fps_batch.sh root@<IP>:<BOARD_WORKDIR>/
ssh root@<IP> "chmod +x <BOARD_WORKDIR>/run_at_fps_batch.sh"
```

在 Step 5 中将 `run_at_fps.sh` 替换为 `run_at_fps_batch.sh` 即可。

#### Scenario C — LLM 循环推理脚本

LLM 模型无法像 CV 模型那样用 `hrt_model_exec perf --frame_count=N` 控制帧率——模型加载开销大（3-5s/次），逐帧调用完全不可行。必须使用常驻进程方案：模型加载一次后持续推理，监控工具在推理期间同步采集数据。

**与 Scenario A 的区别**：

| 维度 | Scenario A (CV) | Scenario C (LLM) |
|------|-----------------|------------------|
| 推理工具 | `hrt_model_exec perf` | `simple_demo_request` / `oellm_batch_request` |
| 帧率控制 | `--frame_count` + `usleep` | `while true` 循环（持续推理，不限帧率） |
| 模型加载 | 每帧/每批重新加载（可接受） | 进程常驻，加载一次后不重新加载 |
| 适用模型 | CV 检测/分割模型（<500MB） | LLM/VLM 大模型（>500MB） |
| 监控指标 | 同 Scenario A | 同 Scenario A + 取监控期间最大值作为最终结果 |

生成 `llm_loop_infer.sh` 并上传到板端：

```bash
cat > /tmp/llm_loop_infer.sh << 'WRAPPER'
#!/bin/sh
# LLM 循环推理 — 用于资源监控期间保持模型持续运行
# 用法: llm_loop_infer.sh <config_path> <image_path> <duration_sec>
CONFIG=$1
IMAGE=$2
DURATION=$3

export LD_LIBRARY_PATH=/opt/horizon/lib:/opt/horizon/hbrt/lib:$LD_LIBRARY_PATH

END_TIME=$(($(date +%s) + DURATION))
COUNT=0
while [ $(date +%s) -lt $END_TIME ]; do
  ./simple_demo_request --config_path "$CONFIG" --image_path "$IMAGE" 2>/dev/null
  COUNT=$((COUNT + 1))
done
echo "LLM inference completed: $COUNT iterations in ${DURATION}s"
WRAPPER

scp /tmp/llm_loop_infer.sh root@<IP>:<BOARD_WORKDIR>/
ssh root@<IP> "chmod +x <BOARD_WORKDIR>/llm_loop_infer.sh"
```

在 Step 5 中将 Scenario A 的 `run_at_fps.sh` 替换为 `llm_loop_infer.sh`。

### Step 5：启动监控与推理

在板端启动监控工具，**所有命令必须使用 `-n` 参数限定采集次数**。

**⚠️ 工具互斥约束**：`hrut_ddr` 和 `hrt_ucp_monitor` 不能同时运行——两者都需要独占访问 DDR 性能计数器设备文件（`/dev/hobot_ddr_perf`），同时运行会导致 `hrut_ddr` 报 `Error: Open failed!`。必须分两轮执行。

**⚠️ `hrt_ucp_monitor -e` 参数**：`-e` 参数仅接受硬件 IP 名称（`bpu`、`dsp`、`gdc`、`stitch`、`pym`、`isp`、`jpu`、`vpu`），**不支持 `memory`**。ION 内存和进程内存数据由工具默认采集，无需通过 `-e` 显式指定。如果传入 `-e bpu,memory` 会报 `memory is invalid` 错误。

**Scenario A — 两轮执行**：

每轮均启动相同的推理负载（同模型、同帧率），保证 DDR 带宽数据在相同负载条件下采集。

```bash
TOTAL_FRAMES=$((TARGET_FPS * MONITOR_DURATION))

# ═══════════════════════════════════════════════════════════
# 第一轮：BPU 占用率 + 内存（hrt_ucp_monitor + 推理）
# ═══════════════════════════════════════════════════════════
ssh root@<IP> "
  # 1. 启动 hrt_ucp_monitor（后台）
  hrt_ucp_monitor -b -e bpu -d 1000 -n $MONITOR_DURATION -f 500 > ${BOARD_WORKDIR}/ucp_monitor.txt 2>&1 &

  # 2. 等 2 秒让监控工具初始化
  sleep 2

  # 3. 启动推理（后台）
  cd ${BOARD_WORKDIR} && nohup sh run_at_fps.sh ${MODEL_PATH} ${TARGET_FPS} ${TOTAL_FRAMES} ${CORE_ID} > inference_pass1.log 2>&1 &
"

# 等待第一轮完成
EXPECTED_SEC=$((MONITOR_DURATION + 10))
ssh root@<IP> "sleep $EXPECTED_SEC && echo 'Pass 1 complete'"

# 拉取第一轮数据
scp root@<IP>:<BOARD_WORKDIR>/ucp_monitor.txt ./
scp root@<IP>:<BOARD_WORKDIR>/inference_pass1.log ./

# ═══════════════════════════════════════════════════════════
# 第二轮：DDR 带宽（hrut_ddr + 推理）
# 原因：hrut_ddr 和 hrt_ucp_monitor 争夺同一设备文件，必须单独运行
# ═══════════════════════════════════════════════════════════
ssh root@<IP> "
  # 1. 启动 hrut_ddr（后台）
  hrut_ddr -t ${DDR_TYPE} -p 1000000 -n $MONITOR_DURATION -c -f ${BOARD_WORKDIR}/ddr_bandwidth.csv 2>&1 &

  # 2. 等 2 秒让 hrut_ddr 初始化
  sleep 2

  # 3. 启动推理（后台，与第一轮相同参数）
  cd ${BOARD_WORKDIR} && nohup sh run_at_fps.sh ${MODEL_PATH} ${TARGET_FPS} ${TOTAL_FRAMES} ${CORE_ID} > inference_pass2.log 2>&1 &
"

# 等待第二轮完成
ssh root@<IP> "sleep $EXPECTED_SEC && echo 'Pass 2 complete'"

# 拉取第二轮数据
scp root@<IP>:<BOARD_WORKDIR>/ddr_bandwidth.csv ./
scp root@<IP>:<BOARD_WORKDIR>/inference_pass2.log ./
```

**Scenario B — 顺序执行（无推理负载）**：

即使没有推理负载，`hrut_ddr` 和 `hrt_ucp_monitor` 仍然不能同时运行。分开启动：

```bash
# 先运行 hrt_ucp_monitor（BPU + 内存）
ssh root@<IP> "hrt_ucp_monitor -b -e bpu -d 1000 -n $MONITOR_DURATION -f 500 > ${BOARD_WORKDIR}/ucp_monitor.txt 2>&1"

# 等 ucp_monitor 完成后再运行 hrut_ddr（DDR 带宽）
ssh root@<IP> "hrut_ddr -t ${DDR_TYPE} -p 1000000 -n $MONITOR_DURATION -c -f ${BOARD_WORKDIR}/ddr_bandwidth.csv"
```

> **注意**：Scenario B 不需要推理，两轮之间无需等待，顺序执行即可。

**Scenario C — 两轮执行（LLM 循环推理）**：

与 Scenario A 结构相同（两轮分步执行），但将 `run_at_fps.sh` 替换为 `llm_loop_infer.sh`：

```bash
# ═══════════════════════════════════════════════════════════
# 第一轮：BPU 占用率 + 内存（hrt_ucp_monitor + LLM 循环推理）
# ═══════════════════════════════════════════════════════════
ssh root@<IP> "
  # 1. 启动 hrt_ucp_monitor（后台）
  hrt_ucp_monitor -b -e bpu -d 1000 -n $MONITOR_DURATION -f 500 > ${BOARD_WORKDIR}/ucp_monitor.txt 2>&1 &

  # 2. 等 2 秒让监控工具初始化
  sleep 2

  # 3. 启动 LLM 循环推理（后台）
  cd ${BOARD_WORKDIR} && nohup sh llm_loop_infer.sh config.json test.jpg $MONITOR_DURATION > inference_pass1.log 2>&1 &
"

# 等待第一轮完成
EXPECTED_SEC=$((MONITOR_DURATION + 15))  # LLM 启动开销大，多等 5 秒
ssh root@<IP> "sleep $EXPECTED_SEC && echo 'Pass 1 complete'"

# 拉取第一轮数据
scp root@<IP>:<BOARD_WORKDIR>/ucp_monitor.txt ./
scp root@<IP>:<BOARD_WORKDIR>/inference_pass1.log ./

# ═══════════════════════════════════════════════════════════
# 第二轮：DDR 带宽（hrut_ddr + LLM 循环推理）
# ═══════════════════════════════════════════════════════════
ssh root@<IP> "
  # 1. 启动 hrut_ddr（后台）
  hrut_ddr -t ${DDR_TYPE} -p 1000000 -n $MONITOR_DURATION -c -f ${BOARD_WORKDIR}/ddr_bandwidth.csv 2>&1 &

  # 2. 等 2 秒让 hrut_ddr 初始化
  sleep 2

  # 3. 启动 LLM 循环推理（后台，与第一轮相同参数）
  cd ${BOARD_WORKDIR} && nohup sh llm_loop_infer.sh config.json test.jpg $MONITOR_DURATION > inference_pass2.log 2>&1 &
"

# 等待第二轮完成
ssh root@<IP> "sleep $EXPECTED_SEC && echo 'Pass 2 complete'"

# 拉取第二轮数据
scp root@<IP>:<BOARD_WORKDIR>/ddr_bandwidth.csv ./
scp root@<IP>:<BOARD_WORKDIR>/inference_pass2.log ./
```

> **Scenario C 结果取值规则**：LLM 推理期间资源波动较大（prefill vs decode 阶段差异显著），报告中 BPU/DDR/内存指标应取**监控期间所有采样点的最大值**，而非平均值。

**hrut_ddr `-t` 参数**：使用 Step 2 平台检测得到的 `DDR_TYPE`（J6E: `bpu`，J6P: `bpu_p0`）。

> **关键**：监控工具必须在推理**之前**启动（上方案例中通过同一条 SSH 命令保证顺序），确保捕获到完整的推理期间数据。

### Step 6：等待采集完成

两轮的等待和数据拉取均在 Step 5 中完成（每轮结束后立即等待并 SCP 拉取）。此步骤仅做最终确认：

```bash
# 确认板端无残留后台进程
ssh root@<IP> "ps aux | grep -E 'hrt_ucp_monitor|hrut_ddr|run_at_fps|llm_loop_infer|simple_demo_request' | grep -v grep"
```

- 如果有残留进程，等待其结束或手动 kill
- 确认本地已获取三个数据文件：`ucp_monitor.txt`、`ddr_bandwidth.csv`、`inference_pass1.log`（Scenario A / C）

### Step 7：解析结果

解析来自两轮采集的数据：

**第一轮数据 — `ucp_monitor.txt`**：
- BPU Utilization: 各核心 busy% / idle%
- ION Memory: uncache 分配量 (MB)
- Process Memory: 各进程 RSS (MB)
- DDR Bandwidth: 仅供参考（`hrt_ucp_monitor` 的 DDR 数据在推理负载下可能不准确，以第二轮 `hrut_ddr` 为准）

**第二轮数据 — `ddr_bandwidth.csv`**（DDR 带宽权威数据源）：
- 每行一条采样：timestamp, read_MiB/s, write_MiB/s
- 计算平均带宽：`sum(read + write) / count`
- 报告中 DDR 带宽数据**必须使用 hrut_ddr 的结果**

**推理日志 — `inference_pass1.log` / `inference_pass2.log`**（Scenario A / C）：

Scenario A：
- 总帧数、总耗时、实际 FPS
- 单帧平均/最小/最大延时
- 两轮推理性能应基本一致，取第一轮数据即可

Scenario C：
- 总迭代次数（`COUNT`）、总耗时
- 平均每次推理耗时（≈ 总耗时 / COUNT）
- 两轮迭代次数应基本一致
- **资源指标取最大值**：LLM 推理期间 prefill 和 decode 阶段资源占用差异大，报告中 BPU/DDR/内存应取监控期间所有采样点的最大值

### Step 8：生成报告 & 保存

生成 Markdown 格式报告，保存到 outputs/ 目录。报告模板见下方「输出格式」。

### Step 9：清理板端残留

数据采集和报告生成完成后，清理板端上的部署文件和残留进程：

```bash
# 停止残留进程（含 Scenario C 的 LLM 推理进程）
ssh root@<IP> "pkill -f hrt_model_exec; pkill -f run_at_fps; pkill -f llm_loop_infer; pkill -f simple_demo_request; pkill -f hrt_ucp_monitor; pkill -f hrut_ddr"

# 清理 BOARD_WORKDIR 下的文件（模型、脚本、日志、监控数据）
ssh root@<IP> "rm -rf ${BOARD_WORKDIR}/*.hbm ${BOARD_WORKDIR}/*.log ${BOARD_WORKDIR}/*.csv ${BOARD_WORKDIR}/*.txt ${BOARD_WORKDIR}/*.sh ${BOARD_WORKDIR}/hrt_model_exec*"

# 清理 /tmp 下的部署残留
ssh root@<IP> "rm -rf /tmp/remote_bpu /tmp/hrt_lib /tmp/board_inputs /tmp/board_outputs"
```

> 清理失败不阻塞任务（板端可能已断连），但应在报告中注明清理状态。

## 输出格式

```markdown
# 板端资源监控报告

## 基本信息
- 开发板: <BOARD_TYPE> (<BOARD_IP>)
- 模型: <model_name> (Scenario A/C) / N/A (Scenario B)
- 场景: Scenario A (CV 受控帧率) / Scenario B (独立监控) / Scenario C (LLM 循环推理)
- 目标帧率: <target_fps> Hz (Scenario A) / N/A (Scenario B/C)
- 实际帧率: <actual_fps> Hz (Scenario A) / <iteration_count> 次迭代 (Scenario C)
- 监控时长: <duration> 秒
- 采样次数: <count>

## BPU 占用率
- 平均: <avg_bpu>%
- 峰值: <peak_bpu>%
- (J6P) 各核心: Core0=<c0>%, Core1=<c1>%, Core2=<c2>%, Core3=<c3>%

## DDR 带宽
| 指标 | hrut_ddr | hrt_ucp_monitor |
|------|----------|-----------------|
| 平均读 (MiB/s) | <r1> | <r2> |
| 平均写 (MiB/s) | <w1> | <w2> |
| 平均总带宽 (GB/s) | <total> | - |
| 峰值读 (MiB/s) | <pr> | - |
| 峰值写 (MiB/s) | <pw> | - |

## 内存使用
| 指标 | 推理前 | 推理中 | 推理后 |
|------|--------|--------|--------|
| 系统总量 (MB) | <t1> | <t2> | <t3> |
| 已用 (MB) | <u1> | <u2> | <u3> |
| ION uncache (MB) | <i1> | <i2> | <i3> |

## 推理性能 (Scenario A)
- 总帧数: <frames>
- 总耗时: <total_time> s
- 平均延时: <avg_latency> ms
- 实际 FPS: <actual_fps>

## 资源消耗评估
<summary: 模型在目标帧率下的资源消耗是否可接受，
BPU 是否有余量，DDR 带宽是否接近上限，内存是否充足>
```

## 约束

1. **严禁使用 hbm_infer / gRPC 进行推理监控** — gRPC 通信开销约 6.8s/帧（ana-002 实测数据：目标 10Hz，实际仅 0.148Hz），必须在板端直接用 `hrt_model_exec`
2. **严禁轮询循环** — 所有监控命令必须使用 `-n` 有界参数。禁止 `while true; do ...; sleep N; done` 或 `sleep+tail` 模式
3. **平台参数必须适配** — hrut_ddr 的 `-t` 参数：J6E 用 `bpu`，J6P 用 `bpu_p0`。错误参数会导致 `Error: Open failed!`
4. **hrut_ddr 与 hrt_ucp_monitor 互斥** — 两者都独占访问 DDR 性能计数器设备文件，同时运行会导致 `hrut_ddr` 报 `Error: Open failed!`。**必须分两轮执行**：第一轮 `hrt_ucp_monitor` + 推理（BPU + 内存），第二轮 `hrut_ddr` + 推理（DDR 带宽）。两轮使用相同推理参数以保证数据一致性
5. **监控先于推理启动** — 每轮内监控工具必须在推理之前启动，确保捕获完整的推理期间数据
6. **SSH 失败时明确报错** — 不要静默跳过，提示用户检查网络和板卡状态
7. **报告必须保存到本地文件** — 不可仅输出到终端
