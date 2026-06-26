# Flexible Mode — Full API Reference

Module: `hbm_infer.hbm_rpc_session_flexible`

Flexible mode separates the lifecycle into three independent levels, allowing multiple sessions (including multi-process) to share the same server and model files on the board.

## Global Functions

### init_server

```python
def init_server(
    host: str,
    username: str = "root",
    password: Optional[str] = None,
    ssh_port: int = 22,
    remote_root: str = "/map/hbm_infer/",
) -> HbmRpcServer:
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `host` | `str` | required | Board IP address |
| `username` | `str` | `"root"` | Board SSH username |
| `password` | `Optional[str]` | `None` | Board SSH password |
| `ssh_port` | `int` | `22` | SSH target port |
| `remote_root` | `str` | `"/map/hbm_infer/"` | Board-side temp file root directory |

Returns: `HbmRpcServer` object instance.

### deinit_server

```python
def deinit_server(hbm_rpc_server: HbmRpcServer) -> None:
```

Cleans up board-side server files. **Must be called explicitly** to release board storage resources.

### init_hbm

```python
def init_hbm(
    local_hbm_path: Union[str, List[str]],
    hbm_rpc_server: HbmRpcServer,
) -> HbmHandle:
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `local_hbm_path` | `Union[str, List[str]]` | Local HBM file path(s) |
| `hbm_rpc_server` | `HbmRpcServer` | Server object from `init_server` |

Returns: `HbmHandle` object instance.

### deinit_hbm

```python
def deinit_hbm(hbm_handle: HbmHandle) -> None:
```

Cleans up board-side HBM files. **Must be called explicitly** to release board storage resources.

## HbmRpcSession.__init__ (Flexible Mode)

```python
def __init__(
    self,
    hbm_handle: HbmHandle,
    hbm_rpc_server: HbmRpcServer,
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
| `hbm_handle` | `HbmHandle` | required | Handle from `init_hbm` |
| `hbm_rpc_server` | `HbmRpcServer` | required | Server from `init_server` |
| `frame_timeout` | `int` | `90` | gRPC per-frame timeout (seconds) |
| `server_timeout` | `int` | `5` | Server auto-shutdown timeout (minutes) |
| `with_profile` | `bool` | `False` | Enable per-stage timing stats |
| `debug` | `bool` | `False` | Debug mode |
| `compress_option` | `str` | `"NONE"` | gRPC compression: `"NONE"`, `"IN"`, `"INOUT"` |
| `core_id` | `Union[int, List[int]]` | `-1` | BPU core ID(s), -1=CORE_ANY |
| `remote_environment` | `Dict[str, Any]` | `{}` | Board-side environment variables |

All other HbmRpcSession methods (`get_model_names`, `get_input_info`, `get_output_info`, `show_input_output_info`, `__call__`, `close_server`, `get_profile`, `get_profile_last_frame`) are identical to Standard Mode. See [standard_mode.md](standard_mode.md).

## Lifecycle Management

```
init_server()  ──►  HbmRpcServer  ──►  deinit_server()
                        │
init_hbm()    ──►  HbmHandle      ──►  deinit_hbm()
                        │
HbmRpcSession ──►  session        ──►  session.close_server()
```

**Cleanup order**: session.close_server() → deinit_hbm() → deinit_server()

All three cleanup calls must be made explicitly. Do NOT rely on `__del__`.

## Multi-Process Example

```python
import torch
import multiprocessing as mp
from hbm_infer.hbm_rpc_session_flexible import (
    HbmRpcSession, init_server, deinit_server, init_hbm, deinit_hbm
)

def single_session_entry(rpc_server, hbm_handle, run_epoch):
    sess = HbmRpcSession(
        hbm_rpc_server=rpc_server,
        hbm_handle=hbm_handle
    )
    try:
        sess.show_input_output_info()
        input_data = {
            'img': torch.ones((1, 3, 224, 224), dtype=torch.int8)
        }
        for i in range(run_epoch):
            output_data = sess(input_data)
            print([output_data[k].shape for k in output_data])
    finally:
        sess.close_server()

def run_hbm_infer(num_process=8, run_epoch=20):
    rpc_server = init_server(host=<available_ip>)
    hbm_handle = init_hbm(
        hbm_rpc_server=rpc_server,
        local_hbm_path=<local_hbm_path>
    )
    try:
        processes = list()
        for i in range(num_process):
            p = mp.Process(
                target=single_session_entry,
                args=(rpc_server, hbm_handle, run_epoch)
            )
            processes.append(p)
            p.start()
        for p in processes:
            p.join()
    finally:
        deinit_hbm(hbm_handle)
        deinit_server(rpc_server)

if __name__ == "__main__":
    run_hbm_infer()
```
