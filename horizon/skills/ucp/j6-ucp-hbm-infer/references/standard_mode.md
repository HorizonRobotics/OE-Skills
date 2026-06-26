# Standard Mode — Full API Reference

Module: `hbm_infer.hbm_rpc_session`

## HbmRpcSession.__init__

```python
def __init__(
    self,
    host: str,
    local_hbm_path: Union[str, List[str]],
    username: str = "root",
    password: Optional[str] = None,
    ssh_port: int = 22,
    remote_root: str = "/map/hbm_infer/",
    frame_timeout: int = 90,
    server_timeout: int = 5,
    with_profile: bool = False,
    debug: bool = False,
    compress_option: str = "NONE",
    core_id: Union[int, List[int]] = -1,
    remote_environment: Dict[str, Any] = {},
) -> None:
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `host` | `str` | required | Board IP address |
| `local_hbm_path` | `Union[str, List[str]]` | required | Local HBM file path(s). Multiple paths for multi-model sessions. |
| `username` | `str` | `"root"` | Board SSH username |
| `password` | `Optional[str]` | `None` | Board SSH password. None means no password. If set, requires `sshpass` on x86. |
| `ssh_port` | `int` | `22` | SSH target port |
| `remote_root` | `str` | `"/map/hbm_infer/"` | Board-side temp file root directory |
| `frame_timeout` | `int` | `90` | gRPC per-frame timeout in seconds |
| `server_timeout` | `int` | `5` | Server auto-shutdown timeout in minutes. After timeout, server exits and cleans all files **except logs**. |
| `with_profile` | `bool` | `False` | Enable per-stage timing statistics |
| `debug` | `bool` | `False` | Debug mode — preserves more log information |
| `compress_option` | `str` | `"NONE"` | gRPC compression. Options: `"NONE"` (no compression), `"IN"` (compress request frames only), `"INOUT"` (compress both request and response frames). Compression is software-level and increases latency; use for reducing network load, not for reducing latency. Avoid for float I/O. |
| `core_id` | `Union[int, List[int]]` | `-1` | BPU core ID(s). 0=CORE_0, 1=CORE_1, -1=CORE_ANY. List for multiple cores. |
| `remote_environment` | `Dict[str, Any]` | `{}` | Board-side environment variables. Keys are variable names, values are variable values. Required for L2M models. |

## HbmRpcSession.get_model_names

```python
def get_model_names(self) -> List[str]:
```

Returns the list of model names in the current session. Model names are not the same as HBM file names.

## HbmRpcSession.get_input_info

```python
def get_input_info(self, model_name: Optional[str] = None) -> Dict[str, Dict]:
```

Returns model input information as a dictionary. For multi-model sessions, `model_name` is required.

Example return value:
```json
{
    "input_name0": {
        "valid_shape": [1, 3, 224, 224],
        "tensor_type": "DATA_TYPE_S8",
        "quanti_type": "QUANTI_TYPE_SCALE",
        "quantizeAxis": 0,
        "scale_data": [0.006861070170998573],
        "zero_point_data": [0]
    }
}
```

## HbmRpcSession.get_output_info

```python
def get_output_info(self, model_name: Optional[str] = None) -> Dict[str, Dict]:
```

Returns model output information. Format is identical to `get_input_info`. For multi-model sessions, `model_name` is required.

## HbmRpcSession.show_input_output_info

```python
def show_input_output_info(self, model_name: Optional[str] = None) -> None:
```

Prints model input and output information. For multi-model sessions, `model_name` is required.

## HbmRpcSession.__call__

```python
def __call__(
    self,
    data: Dict[str, Union[np.ndarray, torch.Tensor, HTensor]],
    output_config: Optional[Dict[str, Dict]] = None,
    model_name: Optional[str] = None,
) -> Dict[str, Union[np.ndarray, torch.Tensor, HTensor]]:
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `data` | `Dict[str, Union[np.ndarray, torch.Tensor, HTensor]]` | Model input. Keys are input tensor names, values are input tensors. Input names, count, shapes, and element types must match model specs. Cannot mix `torch.Tensor` and `np.ndarray`. All `torch.Tensor` must have the same device. |
| `output_config` | `Optional[Dict[str, Dict]]` | Output transmission configuration. See Transmission Optimization reference. |
| `model_name` | `Optional[str]` | Model name. Required for multi-model sessions. |

Returns: Model output dictionary. Keys are output tensor names, values are output tensors. Output type matches input type (torch in → torch out, numpy in → numpy out). Outputs configured in `output_config` return as `HTensor`.

## HbmRpcSession.close_server

```python
def close_server(self) -> None:
```

Closes the server and cleans up board-side resources. **Must be called explicitly** — do not rely on `__del__`.

## HbmRpcSession.get_profile

```python
def get_profile(self, model_name: Optional[str] = None) -> Dict[str, Dict]:
```

Returns cumulative per-stage timing statistics (avg/min/max in ms). Requires `with_profile=True`. For multi-model sessions, `model_name` is required.

Return format:
```json
{
    "frame_duration": {"avg": 6, "min": 6, "max": 6},
    "sd2rv_duration": {"avg": 5, "min": 5, "max": 5},
    "commu_duration": {"avg": 4, "min": 4, "max": 4},
    "board_duration": {"avg": 1, "min": 1, "max": 1},
    "infer_duration": {"avg": 0.5, "min": 0.5, "max": 0.5},
    "prepr_duration": {"avg": 0.3, "min": 0.3, "max": 0.3},
    "pospr_duration": {"avg": 0.2, "min": 0.2, "max": 0.2}
}
```

## HbmRpcSession.get_profile_last_frame

```python
def get_profile_last_frame(self, model_name: Optional[str] = None) -> Dict[str, Dict]:
```

Returns last-frame timing statistics (ms). Requires `with_profile=True`.

Return format:
```json
{
    "frame_duration": 12,
    "sd2rv_duration": 10,
    "commu_duration": 6,
    "board_duration": 4,
    "infer_duration": 2,
    "prepr_duration": 0.5,
    "pospr_duration": 0.5
}
```

## Complete Example

```python
import time
import torch
from hbm_infer.hbm_rpc_session import HbmRpcSession

def run_hbm_infer(run_epoch=10):
    # Create session
    sess = HbmRpcSession(
        host=<available_ip>,
        local_hbm_path=<local_hbm_path>
    )
    try:
        # Print model input/output info
        sess.show_input_output_info()
        # Prepare input data
        input_data = {
            'img': torch.ones((1, 3, 224, 224), dtype=torch.int8)
        }
        # Run inference
        for i in range(run_epoch):
            output_data = sess(input_data)
            print([output_data[k].shape for k in output_data])
    finally:
        # Always close server
        sess.close_server()

if __name__ == '__main__':
    run_hbm_infer()
```
