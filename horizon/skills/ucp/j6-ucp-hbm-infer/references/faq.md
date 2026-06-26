# FAQ & Troubleshooting

## General Debugging

When errors occur, first check the error message's log hints. If x86-side logs cannot pinpoint the issue, check board-side logs at:

```
${remote_root}/${session_token}/log/s.log
```

- `${remote_root}` defaults to `/map/hbm_infer`
- `${session_token}` is printed in the error log

## SSH Errors

1. **Verify network connectivity** between x86 and the board
2. **Non-standard SSH port**: Use the `ssh_port` parameter
3. **Non-root username**: Set the `username` parameter correctly
4. **Password authentication**: Set the `password` parameter and install `sshpass` on x86

```bash
# Install sshpass if using password authentication
sudo apt-get install sshpass
```

## InactiveRpcError

### First-frame inference failure (no board-side errors or server has timed out)

Test gRPC connectivity:

1. **Board-side**: Run the test server from the hbm_infer package's `grpctest` directory

```bash
# Auto-assign port
./test_grpc_server_linux
# Output: Server is running on port: 35017

# Or specify port
./test_grpc_server_linux 33333
# Output: Server is running on port: 33333
```

For QNX boards, use `test_grpc_server_qnx` instead.

2. **X86-side**: Run the test client

```bash
# IP is board IP, PORT is the port printed by the server
python3 -m hbm_infer.grpctest.test_grpc_client IP:PORT
```

3. If connection fails, check if the board's gRPC port is open. If only some ports are available, use the `grpc_port` parameter in `HbmRpcSession`. **Important**: Different sessions on the same board must use different `grpc_port` values to prevent data mixing.

### Mid-inference InactiveRpcError (after several frames)

Investigate:
- Network stability
- Board-side process health

## Resource Cleanup

- **Always call `close_server()`**, `deinit_hbm()`, and `deinit_server()` explicitly
- Do NOT rely on `__del__` for cleanup — garbage collection timing is unpredictable
- Use `try/finally` to guarantee cleanup

```python
session = HbmRpcSession(host=..., local_hbm_path=...)
try:
    # ... inference code ...
finally:
    session.close_server()
```

- If debugging fails multiple times, board processes and storage may accumulate — manually clean up on the board

## Multi-Model Constraints

- Model file names and model graph names must be unique within a session
- Duplicate names can cause model files to be overwritten
- Use `session.get_model_names()` to list actual model names (which differ from HBM file names)

## L2M Model Inference

When inferring L2M models:
- Set environment variables via `remote_environment` parameter
- Set BPU core via `core_id` parameter

```python
session = HbmRpcSession(
    host="...",
    local_hbm_path="...",
    core_id=0,
    remote_environment={"ENV_VAR_NAME": "value"}
)
```

## Performance Testing

Quick performance benchmark command:

```bash
python3 -m hbm_infer.perftest.test_performance \
    --device xx.xx.xx.xx \
    --model_dir xx/xx \
    --log_path perf.log \
    --epoch 100
```

## Compression Guidelines

- Compression is **software-level** — it increases per-frame latency
- Use compression to reduce network load and increase throughput, not to reduce latency
- Avoid compression for float-type inputs/outputs (poor compression ratio)
- Try compression for image inputs or segmentation outputs (better compression ratio)

| Scenario | compress_option |
|----------|----------------|
| Float I/O, low latency priority | `"NONE"` |
| Image input, network bandwidth limited | `"IN"` |
| Segmentation output, bandwidth limited | `"INOUT"` |
