---
name: j6-ucp-model-perf-eval
description: 自动化 hrt_model_exec perf 板端性能评测。触发条件：模型性能测试、benchmark、性能评估、板端测试、thread_num/core_id 参数扫描、吞吐量/延迟对比、远程部署 hrt_model_exec 运行 perf。
---

# Model Perf Eval

通过 SSH/SCP 将 `hrt_model_exec` 部署到远程 J6 aarch64 开发板，遍历用户指定的 thread_num 和 core_id 参数组合运行 perf 评测，收集 `--profile_path` 结构化输出与 BPU/CPU 段级性能数据，生成性能汇总报告与最优配置推荐，并将报告保存到本地文件。

## 适用场景

- 在 J6 实板上评测 .hbm 模型推理性能（延迟、FPS）
- 扫描不同 thread_num / core_id 组合，探索最佳性能配置
- 远程部署 hrt_model_exec 到 aarch64 板端并执行 benchmark
- 对比不同配置的性能差异，生成结构化报告
- 分析模型 BPU/CPU 段的执行耗时占比

触发关键词：性能测试、perf、benchmark、性能评估、板端测试、模型吞吐量、参数扫描

## 工作流程

严格按照以下 6 步顺序执行，不可跳步。

### Step 1：收集信息

向用户收集以下信息。**缺少必填项时，必须逐一询问，全部收集完毕后方可进入 Step 2。**

| 项目 | 必填 | 默认值 | 示例 |
|------|------|--------|------|
| 板端 IP 地址 | 是 | - | `192.168.1.100` |
| SSH 用户名 | 是 | `root` | `root` |
| SSH 端口 | 否 | 22 | |
| 认证方式 | 是 | - | 密码 或 密钥路径（如 `~/.ssh/id_rsa`） |
| 模型文件路径 | 是 | - | `/data/models/resnet50.hbm`（板端）或本地路径 |
| model_name | 否 | 自动检测 | `resnet50` |
| thread_num 范围 | 是 | `1,2,4,8` | `1-8` 或 `1,2,4,8,16` |
| core_id 选项 | 是 | `0` | `0,1` |
| frame_count | 否 | 200 | 500 |
| 板端部署目录 | 是 | `/tmp/hrt_model_exec` | |
| enable_warmup | 否 | true | |
| enable_mem_lru | 否 | true | |

**必须明确确认的信息**：
1. 板端 IP 地址 — 若用户未提供，直接询问："请提供开发板的 IP 地址"
2. SSH 用户名 — 若用户未提供，询问："SSH 登录用户名是什么？（默认 root）"
3. 认证方式 — 若用户未提供，询问："SSH 认证方式？密码或密钥路径"
4. 模型文件路径 — 若用户未提供，询问："请提供 .hbm 模型文件路径（板端路径或本地路径）"
5. 模型文件位置 — 若用户只给了路径但未说明位置，询问："该模型文件在本地还是已在板端？"
6. 板端部署目录 — 若用户未指定，使用默认值 `/tmp/hrt_model_exec`，但需确认

**thread_num 范围解析规则**：
- 范围写法 `1-8`：展开为 1,2,3,4,5,6,7,8
- 列表写法 `1,2,4,8`：直接使用
- 展开后所有值必须在 [1, 32] 范围内

**core_id 说明**：
- `0` = 任意核心（运行时自动选择）
- `1` = BPU Core 0
- `2` = BPU Core 1
- `1,2` = 双核并行
- J6 有 2 个 BPU 核心，有效值：0, 1, 2, "1,2"

**模型文件位置判断**：
- 用户说明在板端：直接使用板端路径
- 用户提供本地路径：通过 SCP 上传到板端部署目录

### Step 2：检查/构建 hrt_model_exec

1. 检查本地 `tools/hrt_model_exec/output_shared_J6_aarch64/` 目录是否存在且完整：
   - 必须存在：`aarch64/bin/hrt_model_exec`
   - 必须存在：`aarch64/lib/` 下的 .so 文件
2. 若目录不存在或不完整，执行构建：
   ```bash
   cd tools/hrt_model_exec && bash build_aarch64.sh
   ```
3. 构建依赖 `LINARO_GCC_ROOT` 环境变量指向交叉编译工具链。若构建失败，提示用户检查工具链配置。

### Step 3：部署到远程板端

1. SCP 部署 hrt_model_exec 工具目录：
   ```bash
   scp -P <port> -r tools/hrt_model_exec/output_shared_J6_aarch64/ <user>@<ip>:<deploy_dir>/
   ```
2. 若模型文件在本地，SCP 上传：
   ```bash
   scp -P <port> <local_model_path> <user>@<ip>:<deploy_dir>/model.hbm
   ```
3. 通过 SSH 验证部署：
   ```bash
   ssh -p <port> <user>@<ip> "ls <deploy_dir>/aarch64/bin/hrt_model_exec && ls <deploy_dir>/aarch64/lib/"
   ```
4. 运行 `model_info` 检查模型信息，确认编译核数：
   ```bash
   ssh -p <port> <user>@<ip> "cd <deploy_dir>/script && \
     export LD_LIBRARY_PATH=../aarch64/lib/:\$LD_LIBRARY_PATH && \
     ../aarch64/bin/hrt_model_exec model_info --model_file=<model_path>"
   ```
   若用户配置了多核 core_id 但模型仅编译为单核，给出警告提示。

### Step 4：遍历参数组合运行 perf 并收集数据

对每个 (thread_num, core_id) 组合，顺序执行 perf 评测：

```bash
ssh -p <port> <user>@<ip> "cd <deploy_dir>/script && \
  export LD_LIBRARY_PATH=../aarch64/lib/:\$LD_LIBRARY_PATH && \
  mkdir -p ../profiler_results && \
  ../aarch64/bin/hrt_model_exec perf \
  --model_file=<model_path> \
  --model_name=<model_name> \
  --core_id=<core_id> \
  --thread_num=<thread_num> \
  --frame_count=<frame_count> \
  --profile_path=../profiler_results/t<thread_num>_c<core_id_str> \
  --enable_warmup=<warmup> \
  --enable_mem_lru=<mem_lru>"
```

**关键规则**：
- **必须使用 `--profile_path`**：每个组合使用独立子目录 `profiler_results/t{thread_num}_c{core_id_str}`（如 `t1_c0`、`t4_c1,2`）
- **顺序执行**：一次只运行一个配置，避免 BPU 资源争抢影响测量准确性
- **错误处理**：若某配置运行失败，记录错误信息，继续执行下一个配置

**所有配置遍历完成后，统一通过 SSH 收集 profiling 产出**（避免执行上下文过长导致信息遗漏）：

```bash
# 遍历所有成功的配置目录，逐个拉取 profiler.log
ssh -p <port> <user>@<ip> "cat <deploy_dir>/profiler_results/t<thread_num>_c<core_id_str>/profiler.log"
```

**BPU/CPU 段级性能数据**：

profiler.log 中 `***` 分隔符之后的第二个 JSON 块已包含 BPU/CPU 段级耗时，无需额外配置。

段级数据结构（来自 profiler.log 第二个 JSON 块）：

1. `processor_latency` — BPU/CPU 整体耗时：
   - `BPU_inference_time_cost`：BPU 推理总耗时（avg_time / max_time / min_time，单位 ms）
   - `CPU_inference_time_cost`：CPU 推理总耗时（avg_time / max_time / min_time，单位 ms）

2. `model_latency` — 各 BPU segment 耗时明细：
   - 每个 `Node-N-BPU-<name>_bpu_segment_<M>` 包含：
     - `Stage1-GenerateBpuTask`：BPU 任务生成耗时
     - `Stage2-BpuCoreProcess`：BPU 核心计算耗时
     - `Total`：该段总耗时

3. `task_latency` — 任务整体耗时：
   - `TaskRunningTime`：任务运行总耗时

**分析维度**：
- BPU 占比 = BPU_inference_time_cost.avg_time / TaskRunningTime.avg_time × 100%
- CPU 占比 = CPU_inference_time_cost.avg_time / TaskRunningTime.avg_time × 100%
- BPU 核心计算占比 = Σ(Stage2-BpuCoreProcess.avg_time) / BPU_inference_time_cost.avg_time × 100%
- 各 BPU segment 耗时排名

### Step 5：解析结果并生成汇总报告

profiler.log 包含两个 JSON 块，以 `***` 分隔，分别解析：

**第一个 JSON 块**（`{` 到 `***`）— 整体性能：

- `running_condition.thread_num`
- `running_condition.core_id`
- `running_condition.frame_count`
- `running_condition.run_time`（ms）
- `running_condition.model_name`
- `perf_result.average_latency`（ms）
- `perf_result.FPS`

**第二个 JSON 块**（`***` 之后）— BPU/CPU 段级耗时：

- `processor_latency.BPU_inference_time_cost.avg_time / max_time / min_time`
- `processor_latency.CPU_inference_time_cost.avg_time / max_time / min_time`
- `task_latency.TaskRunningTime.avg_time / max_time / min_time`
- `model_latency` 中各 BPU segment 的 Stage1/Stage2/Total 耗时

按 FPS 降序排列所有成功配置，分析线程扩展性、核心利用率、段级耗时占比，给出最优配置推荐。报告结构见下方输出格式。

### Step 6：保存报告到本地文件

1. 保存路径：`tools/hrt_model_exec/perf_reports/perf_report_<model_name>_<timestamp>.md`
   ```bash
   mkdir -p tools/hrt_model_exec/perf_reports
   ```
2. 将报告写入文件，同时在终端输出
3. 段级数据额外保存为 `perf_report_<model_name>_<timestamp>_segments.csv`
4. 报告末尾注明文件保存路径

### Step 7：清理板端残留

报告生成并保存后，清理板端上的部署文件和残留进程：

```bash
# 停止残留进程
ssh root@<IP> "pkill -f hrt_model_exec"

# 清理板端工作目录下的部署文件（模型、profile 数据、库文件等）
ssh root@<IP> "rm -rf <BOARD_WORKDIR>/*.hbm <BOARD_WORKDIR>/hrt_model_exec* <BOARD_WORKDIR>/profiler.log <BOARD_WORKDIR>/lib"

# 清理 /tmp 下的部署残留
ssh root@<IP> "rm -rf /tmp/remote_bpu /tmp/hrt_lib"
```

> 清理失败不阻塞任务（板端可能已断连），但应在报告中注明清理状态。批量评测时，在所有模型评测完毕后再统一清理。

## 输出格式

每次评测必须输出以下结构的 markdown 报告：

```markdown
## Model Performance Evaluation Report

### 基本信息
| 项目 | 值 |
|------|-----|
| 模型文件 | ... |
| 模型名称 | ... |
| 测试板端 | user@ip |
| UCP 版本 | ... |
| 测试帧数 | ... |
| 总测试组合数 | ... |
| 报告生成时间 | YYYY-MM-DD HH:MM:SS |

### 性能汇总表

| # | thread_num | core_id | average_latency (ms) | FPS | frame_count | run_time (ms) |
|---|-----------|---------|---------------------|-----|-------------|---------------|
| 1 | ... | ... | ... | ... | ... | ... |

（按 FPS 降序排列）

### BPU/CPU 段耗时分析（最优配置）

| 处理器 | 平均耗时 (ms) | 最大耗时 (ms) | 最小耗时 (ms) | 占比 |
|--------|-------------|-------------|-------------|------|
| BPU | ... | ... | ... | ...% |
| CPU | ... | ... | ... | ...% |
| **任务总耗时** | **...** | **...** | **...** | **100%** |

#### BPU Segment 明细

| 节点 | Stage1-GenerateBpuTask (ms) | Stage2-BpuCoreProcess (ms) | Total (ms) |
|------|---------------------------|--------------------------|------------|
| Node-0-BPU-... | ... | ... | ... |

- BPU 占总任务耗时: ...%
- CPU 占总任务耗时: ...%
- BPU 核心计算占比: ...%（Stage2-BpuCoreProcess / BPU_total）

（如有多组配置的段级数据，可额外列出 BPU/CPU 耗时对比表）

### 延迟-线程扩展性分析
- 单线程延迟基线: X ms
- N线程扩展比: ...x（延迟降至 X ms）
- 扩展效率: ...

### BPU Core 利用分析
- Core0 单核 (thread_num=1): ... FPS
- Core1 单核 (thread_num=1): ... FPS
- 双核 (thread_num=1): ... FPS
- 双核扩展比: ...

### 最优配置推荐
- **最低延迟**: thread_num=X, core_id=Y (average_latency=X ms)
- **最大吞吐**: thread_num=X, core_id=Y (FPS=X)
- **性价比推荐**: thread_num=X, core_id=Y (综合考量延迟与吞吐)

### 失败配置（如有）
| thread_num | core_id | 错误信息 |
|-----------|---------|---------|
| ... | ... | ... |
```

## 约束

- 仅支持 aarch64 实板评测，不支持 x86 模拟器或 QNX
- 远程连接仅通过 SSH/SCP，不支持其他方式
- 所有参数组合必须顺序执行，不可并行
- 不可修改仓库中任何源代码
- 必须使用 `--profile_path` 获取结构化输出，不依赖 stdout 解析
- thread_num 范围 [1, 32]，task_priority 范围 [0, 255]
- 多核 core_id（如 `1,2`）仅对多核编译模型有效，运行前需通过 model_info 确认
- SSH 连接失败时报告错误，建议用户手动检查连通性
- 构建失败时报告错误，建议检查 LINARO_GCC_ROOT 环境变量
- 报告必须保存到本地文件，不可仅输出到终端
