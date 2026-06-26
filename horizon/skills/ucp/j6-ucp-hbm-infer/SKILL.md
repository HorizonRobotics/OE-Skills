---
name: j6-ucp-hbm-infer
description: Generate X86-side Python client code for hbm_infer, the Python SDK that connects to BPU boards via gRPC to deploy and run HBM model inference. Use this skill when the user wants to write Python code using hbm_infer client APIs — including HbmRpcSession (standard/flexible mode), HTensor for transmission optimization, output_config for output filtering, and related utilities like get_input_info, get_output_info, get_profile, compress_option, core_id. Triggers on writing or debugging Python inference scripts, optimizing data transfer between X86 and board, or any question about the hbm_infer Python client API.
---

# hbm_infer X86 Python Client Code Generation

Generate production-ready **X86-side Python client code** for hbm_infer — the Python SDK that connects to a BPU board via gRPC, deploys HBM models over SSH, runs inference, and manages board resources.

## Quick Decision: Which Mode?

| Scenario | Mode | Module |
|----------|------|--------|
| Single model, single process | Standard | `hbm_infer.hbm_rpc_session` |
| Multi-process inference sharing one server | Flexible | `hbm_infer.hbm_rpc_session_flexible` |
| Multi-model pipeline with shared board resources | Flexible | `hbm_infer.hbm_rpc_session_flexible` |

## Standard Mode — Quick Reference

```python
from hbm_infer.hbm_rpc_session import HbmRpcSession

session = HbmRpcSession(
    host="<board_ip>",
    local_hbm_path="<hbm_file_path>",
)
# Use session, then always close
session.close_server()
```

**HbmRpcSession.__init__ parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `host` | `str` | required | Board IP address |
| `local_hbm_path` | `Union[str, List[str]]` | required | Local HBM file path(s) |
| `username` | `str` | `"root"` | Board SSH username |
| `password` | `Optional[str]` | `None` | Board SSH password |
| `ssh_port` | `int` | `22` | SSH port |
| `remote_root` | `str` | `"/map/hbm_infer/"` | Board-side temp directory |
| `frame_timeout` | `int` | `90` | gRPC per-frame timeout (seconds) |
| `server_timeout` | `int` | `5` | Server auto-shutdown timeout (minutes) |
| `with_profile` | `bool` | `False` | Enable per-stage timing stats |
| `debug` | `bool` | `False` | Debug mode with extra logging |
| `compress_option` | `str` | `"NONE"` | gRPC compression: `"NONE"`, `"IN"`, `"INOUT"` |
| `core_id` | `Union[int, List[int]]` | `-1` | BPU core ID(s), -1=CORE_ANY |
| `remote_environment` | `Dict[str, Any]` | `{}` | Board-side environment variables |

**Key methods:**
- `session(data, output_config=None, model_name=None)` — Run inference
- `session.get_model_names()` → `List[str]`
- `session.get_input_info(model_name=None)` → `Dict[str, Dict]`
- `session.get_output_info(model_name=None)` → `Dict[str, Dict]`
- `session.show_input_output_info(model_name=None)` — Print model I/O info
- `session.get_profile(model_name=None)` → Cumulative timing stats (avg/min/max in ms)
- `session.get_profile_last_frame(model_name=None)` → Last-frame timing stats (ms)
- `session.close_server()` — **Must call explicitly** to release board resources

## Flexible Mode — Quick Reference

```python
from hbm_infer.hbm_rpc_session_flexible import (
    HbmRpcSession, init_server, deinit_server, init_hbm, deinit_hbm
)

server = init_server(host="<board_ip>")
handle = init_hbm(local_hbm_path="<hbm_file_path>", hbm_rpc_server=server)
session = HbmRpcSession(hbm_handle=handle, hbm_rpc_server=server)
# Use session...
session.close_server()
deinit_hbm(handle)
deinit_server(server)
```

**Flexible mode separates lifecycle into three levels:**

1. **Server** (`init_server` / `deinit_server`) — Board connection and file deployment
2. **HBM Handle** (`init_hbm` / `deinit_hbm`) — Model file on board
3. **Session** (`HbmRpcSession.__init__` / `close_server`) — Inference session

`init_server` parameters: `host`, `username="root"`, `password=None`, `ssh_port=22`, `remote_root="/map/hbm_infer/"`
`init_hbm` parameters: `local_hbm_path`, `hbm_rpc_server`

Flexible mode `HbmRpcSession.__init__` takes `hbm_handle` and `hbm_rpc_server` instead of `host` and `local_hbm_path`. All other parameters (`frame_timeout`, `with_profile`, etc.) are identical to standard mode.

## Transmission Optimization with HTensor

HTensor reduces data transfer between X86 and board. Three optimization scenarios:

### 1. Fixed/Periodic Input — Cache on Board

```python
from hbm_infer.hbm_rpc_session import HbmRpcSession, HTensor

fixed_input = HTensor(
    data=torch.ones((1, 3, 224, 224), dtype=torch.int8),
    device=["cpu", "bpu"],  # "cpu" = X86, "bpu" = board copy
    key="model.input_0",    # Unique board-side identifier
)
# Update data periodically — only changed frames get transferred
fixed_input.data = torch.ones((1, 3, 224, 224), dtype=torch.int8) * 2
```

**HTensor.__init__ parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `data` | `Union[np.ndarray, torch.Tensor, None]` | Tensor data |
| `device` | `Union[str, List[str], None]` | Storage: `None`, `"cpu"`, `"bpu"`, or `["cpu", "bpu"]` |
| `key` | `Optional[str]` | Board-side unique key (required when device includes `"bpu"`) |

**HTensor properties:** `data` (get/set), `device` (get only), `key` (get only), `shape` (get only, auto-maintained)

### 2. Output Filtering — Skip Unused Outputs

```python
output_config = {
    "unused_output": {"device": None}  # Don't transfer back
}
result = session(data=input, output_config=output_config)
# result["unused_output"] is HTensor with data=None, but shape is available
```

### 3. Model Chaining — Board-Side Passthrough

```python
# Model0 output stays on board
model0_output_config = {
    "output_0": {"device": "bpu", "key": "model0.output_0"}
}
model0_output = session(data=model0_input, output_config=model0_output_config, model_name="model0")

# model0_output["output_0"] is HTensor — use directly as model1 input
model1_input = {"input_0": model0_output["output_0"]}
model1_output = session(data=model1_input, model_name="model1")
```

### output_config Format

`Dict[str, Dict[str, Any]]` — first-level keys are output names, second-level keys:

| Key | Value | Meaning |
|-----|-------|---------|
| `"device"` | `None` / `"cpu"` / `"bpu"` / `["bpu", "cpu"]` | Where to store the output |
| `"key"` | `str` | Board-side unique key (required when device includes `"bpu"`) |

Outputs in `output_config` return as `HTensor`; others return as `np.ndarray` or `torch.Tensor`.

## Inference Input/Output Rules

- **Input** `data`: `Dict[str, Union[np.ndarray, torch.Tensor, HTensor]]`
- **Output**: Same type as input (torch in → torch out, numpy in → numpy out)
- **No mixing** `torch.Tensor` and `np.ndarray` in the same `data` dict
- All `torch.Tensor` inputs must have the same device
- Input names, shapes, and element types must match model specs

## Model I/O Info Fields

`get_input_info()` / `get_output_info()` return `Dict[str, Dict]` — first-level keys are tensor names, second-level values contain:

| Field | Always | Type | Description |
|-------|--------|------|-------------|
| `valid_shape` | Yes | `List[int]` | Tensor shape. `-1` in a dimension indicates a dynamic dimension |
| `tensor_type` | Yes | `str` | Data type enum name (see below) |
| `quanti_type` | Yes | `str` | Quantization type enum name (see below) |
| `quantizeAxis` | No | `int` | Per-channel quantization axis. Only when `quanti_type != QUANTI_TYPE_NONE` |
| `scale_data` | No | `List[float]` | Quantization scales. Only when `quanti_type != QUANTI_TYPE_NONE` |
| `zero_point_data` | No | `List[int]` | Quantization zero points. Only when `quanti_type != QUANTI_TYPE_NONE` |

**`tensor_type` values:** `DATA_TYPE_S4`, `DATA_TYPE_U4`, `DATA_TYPE_S8`, `DATA_TYPE_U8`, `DATA_TYPE_F16`, `DATA_TYPE_S16`, `DATA_TYPE_U16`, `DATA_TYPE_F32`, `DATA_TYPE_S32`, `DATA_TYPE_U32`, `DATA_TYPE_F64`, `DATA_TYPE_S64`, `DATA_TYPE_U64`, `DATA_TYPE_BOOL8`

**`quanti_type` values:** `QUANTI_TYPE_NONE`, `QUANTI_TYPE_SCALE`

## Multi-Model Session

When `local_hbm_path` contains multiple models:
- Model names ≠ HBM file names — call `session.get_model_names()` to list them
- Must specify `model_name` in `get_input_info`, `get_output_info`, `__call__`, `get_profile`
- Model file names and graph names must be unique across the session

## Profile Data Structure

When `with_profile=True`, `get_profile()` returns cumulative stats (avg/min/max in ms):

| Key | Meaning |
|-----|---------|
| `frame_duration` | Total frame latency |
| `sd2rv_duration` | gRPC send-to-receive latency |
| `commu_duration` | Network communication time |
| `board_duration` | Total board-side time |
| `infer_duration` | Pure inference time on board |
| `prepr_duration` | Board-side pre-processing time |
| `pospr_duration` | Board-side post-processing time |

`get_profile_last_frame()` returns the same keys with single-frame values (ms).

## Critical Rules

1. **Always call `close_server()`** — Board processes and storage will leak otherwise. Do NOT rely on `__del__`.
2. **Always call `deinit_hbm()` and `deinit_server()`** in flexible mode — same reason.
3. **Use try/finally** to guarantee cleanup even on exceptions.
4. **Compression is software-level** — Increases latency, only use to reduce network load / increase throughput. Avoid for float I/O; try for image input / segmentation output.
5. **Board-side logs**: `${remote_root}/${session_token}/log/s.log` for debugging.
6. **Multi-model session: user must guarantee unique names** — Model file names and internal graph names must not duplicate across the session; duplicates silently overwrite files on the board.
7. **Model chaining must use the same session** — One session maps to one board-side process; board-side data (HTensor with `device="bpu"`) can only be reused within the same process.
8. **L2M model inference requires `remote_environment` and `core_id`** — Set `HB_DNN_USER_DEFINED_L2M_SIZES` via `remote_environment` to allocate L2 memory per BPU core (e.g. `{"HB_DNN_USER_DEFINED_L2M_SIZES": "6:6:6:6"}` for 4-core, 6MB each). Set `core_id` to match the cores in the env var. If the user needs L2M inference but hasn't specified this env var, ask for the L2M size requirement.

## Code Generation Workflow

When generating hbm_infer code:

1. **Ensure hbm_infer is installed**: Check with `pip3 list | grep hbm_infer`. If not installed, run:
   ```bash
   pip3 install hbm_infer -i https://pypi.hobot.cc/hobot-local/simple
   ```
2. **Determine mode**: Ask or infer standard vs. flexible based on use case
2. **Read model info**: Generate code that calls `show_input_output_info()` or `get_input_info()` / `get_output_info()` to discover shapes and types
3. **Prepare inputs**: Match model input names, shapes, and dtypes exactly
4. **Apply optimizations**: Use HTensor for fixed/periodic inputs, output_config for filtering/chaining
5. **Add cleanup**: Always wrap in try/finally with `close_server()` (and `deinit_*` for flexible mode)
6. **Add profiling if needed**: Set `with_profile=True` and call `get_profile()` or `get_profile_last_frame()`
7. **Consult FAQ when in doubt**: If uncertain about API usage, error handling, or edge cases, read [references/faq.md](references/faq.md) for troubleshooting guidance

For detailed API signatures, complete examples, and troubleshooting, read the reference files:
- [references/standard_mode.md](references/standard_mode.md) — Standard mode full API and examples
- [references/flexible_mode.md](references/flexible_mode.md) — Flexible mode full API and examples
- [references/trans_optimization.md](references/trans_optimization.md) — HTensor and transmission optimization details
- [references/faq.md](references/faq.md) — Troubleshooting and FAQ
