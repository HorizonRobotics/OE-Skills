# Model Perf Eval — 技术参考

## hrt_model_exec perf 命令参数

| 参数 | 类型 | 默认值 | 范围 | 说明 |
|------|------|--------|------|------|
| `--model_file` | string | (必填) | - | .hbm 模型文件路径 |
| `--model_name` | string | "" | - | 模型名称（.hbm 含多模型时必填） |
| `--core_id` | string | "0" | 0-N | 0=任意核心，1=core0，2=core1，逗号分隔多核（如 "1,2"） |
| `--thread_num` | int | 1 | [1,32] | 并发推理线程数 |
| `--frame_count` | int | 200 | >0 | 推理总帧数（perf_time=0 时生效） |
| `--perf_time` | int | 0 | >=0 | 运行时长（分钟），优先于 frame_count 和 perf_time_in_seconds |
| `--perf_time_in_seconds` | int | 0 | >=0 | 运行时长（秒），perf_time=0 时生效 |
| `--profile_path` | string | "" | - | profiler 输出目录，生成 profiler.log 和 profiler.csv |
| `--enable_warmup` | bool | true | - | 跳过首帧统计 |
| `--enable_mem_lru` | bool | true | - | 启用 BPU 内存 LRU 缓存 |
| `--task_priority` | int | 0 | [0,255] | 任务调度优先级 |
| `--task_timeout` | int | 0 | >=0 | 任务等待超时（毫秒），0=无限等待 |
| `--input_file` | string | "" | - | 输入数据文件（perf 可选，不提供时使用随机数据） |
| `--input_valid_shape` | string | "" | - | 动态输入 valid_shape，分号分隔不同输入 |
| `--input_stride` | string | "" | - | 动态输入 stride，分号分隔不同输入 |
| `--input_img_properties` | string | "" | - | 图像色彩空间转换 |
| `--log_level` | int | 2 | [0,4] | 日志级别（0=trace, 1=debug, 2=info, 3=warning, 4=error） |
| `--statistic_cycle` | int | 0 | >=0 | 统计周期（帧），0=全生命周期 |

## core_id 与 BPU Core 映射

```
core_id 0   → core_mask 0  (CORE_ANY，运行时自动选择)
core_id 1   → core_mask 1  (CORE_0)
core_id 2   → core_mask 2  (CORE_1)
core_id 1,2 → core_mask 3  (CORE_0 + CORE_1，双核并行)
```

转换公式：`core_id == 0 ? 0 : 1ULL << (core_id - 1)`

J6 有 2 个 BPU 核心。`GetBpuCoreNum()` 在 aarch64 上读取 `/sys/devices/system/bpu/core_num`。

注意：多核 core_id（如 `1,2`）仅对多核编译模型有效。单核编译模型使用多核 core_id 可能导致运行失败或结果不准确。

## profiler.log 输出格式

profiler.log 包含两个 JSON 块，以 `***` 分隔：

```
ucp_version: <version_string>
{
  "perf_result": {
    "FPS": <float>,
    "average_latency": <float>
  },
  "running_condition": {
    "core_id": "<string>",
    "frame_count": <int>,
    "model_name": "<string>",
    "run_time": <float>,
    "thread_num": <int>
  }
}
***
{
  "model_latency": {
    "Node-0-BPU-<name>_bpu_segment_0": {
      "Stage1-GenerateBpuTask": {
        "avg_time": <float>,
        "max_time": <float>,
        "min_time": <float>
      },
      "Stage2-BpuCoreProcess": {
        "avg_time": <float>,
        "max_time": <float>,
        "min_time": <float>
      },
      "Total": {
        "avg_time": <float>,
        "max_time": <float>,
        "min_time": <float>
      }
    }
  },
  "processor_latency": {
    "BPU_inference_time_cost": {
      "avg_time": <float>,
      "max_time": <float>,
      "min_time": <float>
    },
    "CPU_inference_time_cost": {
      "avg_time": <float>,
      "max_time": <float>,
      "min_time": <float>
    }
  },
  "task_latency": {
    "TaskRunningTime": {
      "avg_time": <float>,
      "max_time": <float>,
      "min_time": <float>
    }
  }
}
```

所有时间单位均为毫秒。

**解析方法**：
1. 读取文件全部内容
2. 找到 `***` 分隔符位置
3. 第一个 JSON 块（`{` 到 `***` 之间）：整体性能数据
4. 第二个 JSON 块（`***` 之后到文件末尾）：BPU/CPU 段级耗时数据
5. 分别使用 JSON 解析器解析两个块

**第一个 JSON 块字段说明**：
- `run_time`：总运行时间（ms）
- `average_latency`：平均推理延迟（ms）
- `FPS`：每秒推理帧数
- `frame_count`：实际完成帧数

**第二个 JSON 块字段说明**：
- `processor_latency.BPU_inference_time_cost`：BPU 推理总耗时
- `processor_latency.CPU_inference_time_cost`：CPU 推理总耗时
- `task_latency.TaskRunningTime`：任务运行总耗时
- `model_latency`：各 BPU segment 耗时明细
  - `Stage1-GenerateBpuTask`：BPU 任务生成阶段耗时
  - `Stage2-BpuCoreProcess`：BPU 核心计算阶段耗时
  - `Total`：该段总耗时

## profiler.csv 输出格式

```
ucp_version,<version_string>
running_condition
thread_num,<int>
core_id,<string>
frame_count,<int>
run_time,<float>
model_name,<string>

perf_result
average_latency,<float>
FPS,<float>

```

## 构建与部署

### 构建 aarch64 版本

```bash
cd tools/hrt_model_exec
bash build_aarch64.sh
```

构建依赖 `LINARO_GCC_ROOT` 环境变量指向交叉编译工具链。

构建产物：
```
output_shared_J6_aarch64/
  aarch64/
    bin/hrt_model_exec
    lib/
      libdnn.so
      libhbucp.so
      libhbrt4.so
      libhbtl.so
      libhlog_wrapper.so
      libhb_arm_rpc.so
      libperfetto_sdk.so
  script/
    run_hrt_model_exec.sh
```

### SCP 部署

```bash
# 部署工具目录
scp -P <port> -r tools/hrt_model_exec/output_shared_J6_aarch64/ <user>@<ip>:<deploy_dir>/

# 部署本地模型文件（如需要）
scp -P <port> <local_model_path> <user>@<ip>:<deploy_dir>/model.hbm
```

### SSH 远程执行

```bash
# model_info 检查
ssh -p <port> <user>@<ip> "cd <deploy_dir>/script && \
  export LD_LIBRARY_PATH=../aarch64/lib/:\$LD_LIBRARY_PATH && \
  ../aarch64/bin/hrt_model_exec model_info --model_file=<model_path>"

# perf 评测
ssh -p <port> <user>@<ip> "cd <deploy_dir>/script && \
  export LD_LIBRARY_PATH=../aarch64/lib/:\$LD_LIBRARY_PATH && \
  mkdir -p ../profiler_results && \
  ../aarch64/bin/hrt_model_exec perf \
  --model_file=<model_path> \
  --core_id=<core_id> \
  --thread_num=<thread_num> \
  --frame_count=<frame_count> \
  --profile_path=../profiler_results/t<thread_num>_c<core_id_str>"

# 读取 profiler 结果
ssh -p <port> <user>@<ip> "cat <deploy_dir>/profiler_results/t<thread_num>_c<core_id_str>/profiler.log"
```

## 评测产出文件结构

完成全部参数组合后，板端目录结构：

```
<deploy_dir>/
  aarch64/
    bin/hrt_model_exec
    lib/*.so
  script/
    run_hrt_model_exec.sh
  profiler_results/
    t1_c0/
      profiler.log
      profiler.csv
    t2_c0/
      profiler.log
      profiler.csv
    ...
```

## SSH/SCP 常见问题

| 问题 | 症状 | 解决方法 |
|------|------|---------|
| 连接拒绝 | `ssh: connect to host ... port 22: Connection refused` | 检查板端 IP、确保 SSH 服务已启动 |
| 认证失败 | `Permission denied` | 确认用户名/密码/密钥正确 |
| 板端空间不足 | `No space left on device` | 清理板端部署目录或更换路径 |
| 二进制无执行权限 | `Permission denied` (运行 hrt_model_exec) | 在板端执行 `chmod +x <deploy_dir>/aarch64/bin/hrt_model_exec` |
| 动态库找不到 | `error while loading shared libraries` | 确保运行前设置 `export LD_LIBRARY_PATH=../aarch64/lib/:$LD_LIBRARY_PATH` |
| 交叉编译工具链缺失 | `build_aarch64.sh` 失败 | 检查 `LINARO_GCC_ROOT` 环境变量 |

## perf 输出指标说明

| 指标 | 含义 | 计算方式 |
|------|------|---------|
| average_latency | 平均单帧推理延迟 | 各线程平均延迟的均值（ms） |
| FPS | 每秒推理帧数 | finished_frame × 1000000 / (end_ts - start_ts) |
| run_time | 总运行时间 | 从首帧开始到末帧结束（ms） |
| frame_count | 实际完成帧数 | 所有线程完成的推理次数之和 |

**性能分析要点**：
- thread_num 增加 → 延迟降低、FPS 提升，但存在饱和点
- core_id=0（任意核心）vs core_id=1/2（绑核）：绑核可能减少调度开销
- 双核 core_id=1,2：对于多核编译模型，FPS 接近单核的 2 倍
- enable_warmup=true 时首帧不计入统计，结果更稳定
- enable_mem_lru=true 启用内存缓存，减少内存分配开销

## BPU/CPU 段级性能数据

### 数据来源

profiler.log 的第二个 JSON 块（`***` 分隔符之后）已包含完整的 BPU/CPU 段级耗时，无需额外配置。

### processor_latency 分析

| 字段 | 含义 | 单位 |
|------|------|------|
| `BPU_inference_time_cost.avg_time` | BPU 推理平均耗时 | ms |
| `BPU_inference_time_cost.max_time` | BPU 推理最大耗时 | ms |
| `BPU_inference_time_cost.min_time` | BPU 推理最小耗时 | ms |
| `CPU_inference_time_cost.avg_time` | CPU 推理平均耗时 | ms |
| `CPU_inference_time_cost.max_time` | CPU 推理最大耗时 | ms |
| `CPU_inference_time_cost.min_time` | CPU 推理最小耗时 | ms |

**关键指标计算**：
- BPU 占比 = `BPU_inference_time_cost.avg_time` / `TaskRunningTime.avg_time` × 100%
- CPU 占比 = `CPU_inference_time_cost.avg_time` / `TaskRunningTime.avg_time` × 100%
- BPU 核心计算占比 = Σ(`Stage2-BpuCoreProcess.avg_time`) / `BPU_inference_time_cost.avg_time` × 100%

### model_latency 分析

| 阶段 | 含义 |
|------|------|
| `Stage1-GenerateBpuTask` | BPU 任务生成阶段（驱动层开销） |
| `Stage2-BpuCoreProcess` | BPU 核心计算阶段（实际硬件执行） |
| `Total` | 该段总耗时（Stage1 + Stage2） |

节点命名格式：`Node-<N>-BPU-<op_name>_bpu_segment_<M>`

### 段级数据 CSV 保存格式

保存为 `perf_report_<model_name>_<timestamp>_segments.csv`：

```
thread_num,core_id,processor,avg_time_ms,max_time_ms,min_time_ms
2,0,BPU,2.023,11.623,1.099
2,0,CPU,0.000,0.000,0.000
2,0,TaskRunningTime,2.046,11.647,1.139
```

## 报告本地保存

### 保存路径

```
tools/hrt_model_exec/perf_reports/
  perf_report_<model_name>_<YYYYMMDD_HHMMSS>.md
  perf_report_<model_name>_<YYYYMMDD_HHMMSS>_segments.csv
```

### 保存方式

1. 评测完成后，将报告 markdown 内容写入 `.md` 文件
2. 同时在终端输出报告内容
3. 段级数据额外保存为 `_segments.csv` 文件
4. 报告末尾注明文件保存路径
