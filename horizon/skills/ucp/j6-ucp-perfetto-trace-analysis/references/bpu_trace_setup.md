# BPU Trace 使能指南

BPU Trace 用于记录 BPU 硬件的调度与执行信息，配合 UCP Trace 可以完整还原从任务创建、提交、BPU 调度执行到任务完成释放的全链路。

BPU Trace 仅在 **system mode** 下支持采集。

## 使能步骤

### 1. 手动使能 BPU Trace 硬件开关

BPU Trace 不支持运行时动态使能，必须在应用启动前手动开启：

```bash
# 先确认 power_enable 为 0，若不为 0 则先关闭
cat /sys/devices/system/bpu/bpu0/power_enable
# 如果不为 0：
echo 0 > /sys/devices/system/bpu/bpu0/power_enable

# 使能 BPU trace
echo 1 > /sys/devices/system/bpu/bpu0/trace
```

### 2. 启动 Perfetto 后台服务

```bash
# 启动 trace service（只需启动一次，已运行则无需重复）
tracebox traced --background

# 启动数据采集服务（只需启动一次，已运行则无需重复）
tracebox traced_probes --background --reset-ftrace
```

### 3. 触发数据采集

使用包含 BPU trace 数据源的配置文件启动 perfetto：

```bash
# -c: 指定 Perfetto 配置文件（使用 BPU trace 专用配置）
# -o: 指定输出 trace 文件路径
tracebox perfetto --txt -c ucp_bpu_trace.cfg -o ucp.pftrace
```

### 4. 配置 UCP 环境变量

在另一个终端中：

```bash
# 指定 system mode 配置
export HB_UCP_PERFETTO_CONFIG_PATH=ucp_system.json

# 使能 Perfetto
export HB_UCP_ENABLE_PERFETTO=true
```

### 5. 运行 UCP 应用

```bash
./hrt_model_exec perf                        \
    --model_file resnet50_224x224_nv12.hbm   \
    --frame_count 50                         \
    --thread_num 1
```

确保 `perfetto` 进程在应用退出前不会退出，否则可能丢失数据。

## BPU Trace Perfetto 配置文件

BPU trace 数据源通过 `linux.sys_stats` 配置，`bputrace_period_ms` 设置读取 BPU Trace 的间隔。UCP 发布包中提供了参考配置文件 `ucp_bpu_trace.cfg`：

```bash title="ucp_bpu_trace.cfg"
data_sources: {
    config {
        name: "linux.sys_stats"
        sys_stats_config {
            bputrace_period_ms: 500
        }
    }
}
```

### bputrace_period_ms 调参建议

- 默认值为 500ms
- BPU 负载较高时，应适当缩短间隔，避免因读写速度不匹配导致 trace 数据被覆盖
- 间隔越短，采集越频繁，数据越完整，但系统开销也越大

## 完整配置文件模板

如果要同时采集 UCP Trace 和 BPU Trace，需将 BPU trace 数据源追加到 system mode 配置中：

```bash title="ucp_bpu_trace.cfg (完整)"
# UCP data source
data_sources: {
    config {
        name: "track_event"
        track_event_config {
           enabled_categories: "dnn"
        }
    }
}

# BPU trace data source
data_sources: {
    config {
        name: "linux.sys_stats"
        sys_stats_config {
            bputrace_period_ms: 500
        }
    }
}
```

对应的 UCP 配置文件使用 system mode：

```json title="ucp_system.json"
{
    "backend": "system"
}
```

## 可视化

BPU Trace 需要使用地平线定制的 `hbperfetto` 工具打开 `.pftrace` 文件，该工具支持 UCP Trace 与 BPU Trace 的关联展示。

- 如需查看原始 BPU trace 数据，可通过 SQL 查询：

```sql
select * from bpu_trace
```

- `hbperfetto` 工具需联系地平线系统软件技术支持获取

## 配置文件与工具位置

UCP Trace 工具和配置文件位于 `samples/ucp_tutorial/tools`：

```text
tools/
└── trace                          # trace 工具
  ├── catch_trace.sh               # chrome trace 采集脚本
  ├── configs                      # 参考配置文件
  │   ├── ucp_bpu_trace.cfg        # 使能 BPU trace 的 Perfetto 配置文件
  │   ├── ucp_dsp_trace.cfg        # 使能 DSP trace 的 Perfetto 配置文件
  │   ├── ucp_in_process.cfg       # in_process 模式 Perfetto 配置文件
  │   ├── ucp_in_process.json      # in_process 模式 UCP 配置文件
  │   ├── ucp_system.cfg           # system 模式 Perfetto 配置文件
  │   └── ucp_system.json          # system 模式 UCP 配置文件
```

## 常见问题

**Q: BPU Trace 数据为空？**
- 确认已执行 `echo 1 > /sys/devices/system/bpu/bpu0/trace`
- 确认执行前 `power_enable` 为 0
- 确认使用的是 system mode（in_process 模式不支持 BPU Trace）
- 确认 perfetto 进程先于应用启动且晚于应用退出

**Q: BPU Trace 数据不完整？**
- 缩小 `bputrace_period_ms` 的值，提高采集频率
- 增大 buffer size

**Q: 在哪里获取 hbperfetto？**
- 联系地平线系统软件技术支持获取
