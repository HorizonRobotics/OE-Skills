# UCP Perfetto Inference Setup Guide

## Dependencies

### Mandatory

- Python 3
- `perfetto` Python package
- Access to a Perfetto trace file such as `.pftrace`

Install the Python dependency with:

```bash
pip install perfetto
```

### Binary dependency

The bundled script depends on `trace_processor_shell`.

This setup guide is for the **UCP inference bottleneck analysis skill only**, not for general Perfetto workflows.

Use the tool in **dual mode**:

1. **Default mode**: do not pass `--trace-processor-bin`
   - the Perfetto Python package will auto-download or auto-discover a compatible `trace_processor_shell`
2. **Explicit local-binary mode**: pass `--trace-processor-bin /path/to/trace_processor_shell`
   - use this when a local binary is already available, or when automatic startup is unavailable

If default startup fails, first ask whether the user can provide a local usable `trace_processor_shell` path. Only if they cannot provide one should you suggest a manual download.

### Optional

- Python virtual environment
- `pandas` / `numpy` if users want to extend the bundled analysis script later

## Quick start

### Fastest path

```bash
pip install perfetto
python scripts/analyze_trace.py /path/to/trace.pftrace
```

### First-run note

If `--trace-processor-bin` is omitted, the first run may download a compatible `trace_processor_shell` binary. This can take longer than normal and requires network access.

## Full installation guide

### Option A: Default recommended setup

Use this when the machine can access the internet.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install perfetto
python scripts/analyze_trace.py /path/to/trace.pftrace
```

### Option B: Offline or restricted network setup

Use this when automatic binary download is unavailable or undesirable.

1. Install Python dependency:

```bash
pip install perfetto
```

2. Provision `trace_processor_shell` manually.

Recommended ways to obtain the binary:

- **Best option: copy from a machine that already ran Perfetto Python successfully**
  - common cache directory:
    - `~/.local/share/perfetto/prebuilts/trace_processor_shell`
- **Direct download using the official Perfetto helper URL**
  - recommended Unix-like command:

```bash
curl -L https://get.perfetto.dev/trace_processor -o ./trace_processor_shell
chmod +x ./trace_processor_shell
```

  - equivalent `wget` command:

```bash
wget -O ./trace_processor_shell https://get.perfetto.dev/trace_processor
chmod +x ./trace_processor_shell
```

  - on Windows PowerShell, download to a local file such as `trace_processor_shell.exe` and pass that path to `--trace-processor-bin`

Common platform guidance:

- macOS Apple Silicon: use an `arm64` binary
- macOS Intel: use an `amd64/x86_64` binary
- Linux x86_64: use an `amd64` binary
- Windows: use the corresponding `trace_processor_shell.exe`

If you are unsure which binary to fetch, first verify the Python/runtime architecture:

```bash
python3 -c 'import platform; print(platform.system(), platform.machine())'
```

After downloading:

- place the binary somewhere stable, for example `/opt/perfetto/trace_processor_shell` or `~/bin/trace_processor_shell`
- ensure it is executable on Unix-like systems:

```bash
chmod +x /path/to/trace_processor_shell
```

3. Run the script with an explicit binary path:

```bash
python scripts/analyze_trace.py /path/to/trace.pftrace --trace-processor-bin /path/to/trace_processor_shell
```

4. If the binary still fails to start, re-check:

- the binary architecture matches the machine
- the Python architecture matches the machine
- the file is executable
- the path passed to `--trace-processor-bin` is correct

## Platform notes

### macOS Apple Silicon

Prefer native `arm64` Python rather than running x86_64 Python via Rosetta.

Quick check:

```bash
python3 -c 'import platform; print(platform.machine())'
```

Expected on Apple Silicon: `arm64`

### Restricted or enterprise environments

If the machine cannot fetch the Perfetto prebuilt binary automatically, use the manual `--trace-processor-bin` fallback.

## Troubleshooting

### `trace_processor_shell not found`

- You passed `--trace-processor-bin` with an invalid path
- First ask the user to verify or provide the correct local binary path
- If the user cannot provide a local usable binary, then fall back to manual download guidance

### First run hangs or fails during startup

- auto-download may be blocked or interrupted
- retry once if the failure looks transient
- if it still fails, do not keep retrying silently
- instead, use this recovery order:
  1. first ask whether the user can provide a local usable `trace_processor_shell`
     path via `--trace-processor-bin`
  2. if the user cannot provide a local binary, provide platform-specific download
     instructions and then rerun with `--trace-processor-bin`

Suggested user-facing recovery prompt:

- `Automatic startup of trace_processor_shell failed. Can you provide a local usable trace_processor_shell path?`
- `trace_processor_shell 默认启动失败。你是否可以提供本地可用的 trace_processor_shell 路径？`

### Architecture / CPU compatibility issues

- verify Python architecture matches the machine
- on Apple Silicon, avoid Rosetta-based x86_64 Python if possible

### Trace file permission issues

- ensure the trace file is readable by the current user

### Result looks implausible

- do not trust it immediately
- re-check argument paths, flow semantics, and hardware-pool semantics before reporting
