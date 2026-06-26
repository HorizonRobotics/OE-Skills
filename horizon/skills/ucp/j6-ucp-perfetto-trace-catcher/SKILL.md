---
name: j6-ucp-perfetto-trace-catcher
description: Capture UCP (Horizon Robotics inference SDK) Perfetto traces from a J6 development board. Use this skill whenever the user wants to grab UCP traces, capture Perfetto traces on a Horizon dev board, debug UCP scheduling issues with trace data, or pull .pftrace files from a remote board. Also trigger when the user mentions UCP performance analysis, UCP trace, hrt_model_exec tracing, or BPU trace capture on J6/S1000 platforms. Do NOT use for DSP trace or Chrome trace.
---

# UCP Trace Catcher

Capture Perfetto-based UCP traces from a remote J6 development board and bring them back to the X86 host for analysis.

## What this skill does

Automates the full lifecycle of UCP Perfetto trace capture:

1. Transfer config files to the dev board
2. Set up the trace environment and run the application
3. Pull the captured trace back to the host
4. Tell the user what to do next

Only Perfetto trace is in scope — ignore DSP trace and Chrome trace.

**Never modify original files in this skill's directory.** Copy config files to a temp location under the **local current workspace** (`pwd`), edit the copy there, then transfer.

## Before starting

You need the following information from the user. Ask for anything not provided:

| Parameter | Description | Example |
|---|---|---|
| `board_ip` | IP address or hostname of the dev board | `192.168.1.100` |
| `board_user` | SSH username for the board (default: `root` if not specified, do not use local username) | `root` |
| `work_dir` | Directory on the board where the UCP app runs | `/userdata/ucp_test` |
| `mode` | `in_process` or `system` | `system` |
| `enable_bpu` | Whether to capture BPU trace (system mode only, default: `false`) | `false` |
| `output_name` | Desired trace filename (default: `ucp.pftrace`) | `my_trace.pftrace` |
| `app_command` | The UCP application command to run | `./hrt_model_exec perf --model_file model.hbm --frame_count 1000 --thread_num 8` |

If `mode` is not specified, ask the user:
- **in_process**: captures only UCP process-internal trace (track_event). **Does NOT** support thread scheduling states, ftrace, memory stats, process stats, or BPU trace. No daemon needed. Good for UCP scheduling logic analysis.
- **system**: captures UCP trace + thread scheduling states (ftrace), memory stats, and process stats by default (uses `ucp_system.cfg`). When BPU trace is enabled, the same `ucp_system.cfg` is used but BPU trace is additionally turned on via sysfs commands; BPU trace data will appear alongside ftrace data. Needs tracebox daemons. Use system mode when you need system-level visibility beyond UCP internals.

**Important**: The pre-built config files in `reference/` cover all modes. Select the right one by mode — do NOT modify config files unless you have a specific reason (e.g., adjusting buffer size or duration).

## Step 1: Transfer config files to the board

Config files are in this skill's `reference/` directory. Select the right cfg file based on mode:

| Mode | cfg file | json file |
|---|---|---|
| in_process | `ucp_in_process.cfg` | `ucp_in_process.json` |
| system | `ucp_system.cfg` | `ucp_system.json` |

All system mode configs share the same `ucp_system.json` (it just sets `"backend": "system"`). System mode always uses `ucp_system.cfg` regardless of BPU trace — BPU trace is controlled by sysfs commands, not the cfg file.

Transfer via scp:

### For in_process mode

```bash
scp reference/ucp_in_process.cfg reference/ucp_in_process.json <board_user>@<board_ip>:<work_dir>/
```

### For system mode

```bash
scp reference/ucp_system.cfg reference/ucp_system.json <board_user>@<board_ip>:<work_dir>/
```

If you edited a config copy (e.g., adjusting `duration_ms` or `output_path`), scp the copy instead of the original `reference/` file.

## Step 2: Set up environment and run the application

Environment variables and the app must run in the **same SSH session**, otherwise the variables are lost. Always combine setup and app execution into a single SSH heredoc.

### For in_process mode

```bash
ssh <board_user>@<board_ip> << 'EOF'
cd <work_dir>

# Remove old trace file if it exists (Perfetto cannot overwrite)
rm -f <output_name>

# Set environment variables
export HB_UCP_PERFETTO_CONFIG_PATH=ucp_in_process.json
export HB_UCP_ENABLE_PERFETTO=true

# Run the UCP application
<App command>
EOF
```

### For system mode

```bash
ssh <board_user>@<board_ip> << 'EOF'
cd <work_dir>

# Remove old trace file if it exists
rm -f <output_name>

# Kill existing tracebox processes to avoid interference
pkill -f "tracebox" 2>/dev/null || true
sleep 1

# Start Perfetto daemons
tracebox traced --background
tracebox traced_probes --background --reset-ftrace

# If BPU trace is enabled, query BPU core count and turn on BPU trace on ALL cores
if <enable_bpu>; then
    BPU_CORE_NUM=$(cat /sys/devices/system/bpu/core_num)
    for i in $(seq 0 $(expr $BPU_CORE_NUM - 1)); do
        echo 0 > /sys/devices/system/bpu/bpu${i}/power_enable 2>/dev/null || true
        echo 1 > /sys/devices/system/bpu/bpu${i}/trace
    done
fi

# Start trace capture in background and record its PID
tracebox perfetto --txt -c <cfg_file_from_step1> -o <output_name> &
PERFETTO_PID=$!

# Set UCP environment variables
export HB_UCP_PERFETTO_CONFIG_PATH=ucp_system.json
export HB_UCP_ENABLE_PERFETTO=true

# Run the UCP application
<App command>

# Wait for the background perfetto process to finish writing trace data
wait $PERFETTO_PID

# If BPU trace was enabled, disable it on ALL cores
if <enable_bpu>; then
    BPU_CORE_NUM=$(cat /sys/devices/system/bpu/core_num)
    for i in $(seq 0 $(expr $BPU_CORE_NUM - 1)); do
        echo 0 > /sys/devices/system/bpu/bpu${i}/trace
    done
fi
EOF
```

Important: in system mode, the `tracebox perfetto` process must remain running for the entire duration of the UCP application. If it exits before the app, the trace will be incomplete. After the app finishes, `wait $PERFETTO_PID` ensures the perfetto process completes writing all trace data before cleanup.

## Step 3: Pull the trace file back to the host

After the application finishes:

```bash
scp <board_user>@<board_ip>:<work_dir>/<output_name> ./
```

Verify the file was transferred and has reasonable size (should be > 0 bytes).

## Step 4: Tell the user what to do next

Inform the user:

- The trace file is saved at `<local_path>/<output_name>`
- They can open it in [Perfetto UI](https://ui.perfetto.dev/) for visualization
- If BPU trace was captured, they need the `hbperfetto` tool (contact Horizon support) to view BPU-specific data
- Key Perfetto UI shortcuts: `w`/`s` to zoom in/out, `a`/`d` to pan left/right, `?` for help

## Handling common issues

| Problem | Solution |
|---|---|
| Trace file already exists | Delete it with `rm -f ucp.pftrace` before capture. Perfetto cannot overwrite. |
| `tracebox: command not found` | The tracebox binary may not be in PATH. Ask the user where it's located. |
| Trace is empty or 0 bytes | Likely env vars weren't set in the same shell as the app, or perfetto process crashed. Check with `wait $PERFETTO_PID` — if it returns a non-zero exit code, perfetto exited abnormally. |
| BPU trace not showing | Verify BPU trace was enabled on ALL cores: query `cat /sys/devices/system/bpu/core_num` for the core count, then check `echo 1 > /sys/devices/system/bpu/bpu${i}/trace` was executed for each core `i` from 0 to `core_num - 1` before starting the capture. Also verify `power_enable` was 0 on each core. |
| Old perfetto processes interfere | Kill existing `tracebox perfetto` and `tracebox traced` processes before starting a new capture. |
| BPU trace not cleaned up | After capture, disable BPU trace on ALL cores: loop through `echo 0 > /sys/devices/system/bpu/bpu${i}/trace` for each core `i` from 0 to `core_num - 1`. Leaving it on may affect subsequent runs. |
| Config file not found on board | The config files use relative paths — they must be in the same directory as the running program. |

## Config file reference

All config files are in this skill's `reference/` directory. Read them when you need to inspect or modify the configurations before transfer.

| File | Mode | Trace modules | Buffers |
|---|---|---|---|
| `ucp_in_process.json` + `ucp_in_process.cfg` | in_process | UCP | 1 |
| `ucp_system.json` + `ucp_system.cfg` | system | UCP + ftrace + BPU trace (BPU data requires sysfs enable) | 2 |

Key parameters you might want to adjust:

| Parameter | File | Default | Purpose |
|---|---|---|---|
| `duration_ms` | all `.cfg` | 10000 (10s) | How long Perfetto captures. For in_process mode, trace data after this duration is discarded — increase this value if the app runs longer than 10s. For system mode, the perfetto process exits after this duration regardless of whether the app has finished. |
| `size_kb` | `ucp_in_process.cfg` | 65535 | Buffer size for in_process mode. |
| `size_kb` | `ucp_system.cfg` | 131072 | Buffer size per buffer for system mode (2 buffers). |
| `file_write_period_ms` | `ucp_in_process.cfg` | 2500 | How often buffer is flushed to file. |
| `write_into_file` | `ucp_in_process.cfg` | true | Periodic flush to file. Keep true for reliability. |
| `bputrace_period_ms` | `ucp_system.cfg` | 500 | BPU trace sampling period. Decrease under heavy BPU load. Data appears only when BPU trace is enabled via sysfs. |
| `output_path` | `ucp_in_process.cfg` | `ucp.pftrace` | Trace output path on the board. |
