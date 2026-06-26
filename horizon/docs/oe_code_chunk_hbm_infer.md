# oe_code_chunk_hbm_infer

## 仓库概述

- **Name**: hbm_infer (v3.15.3)
- **Purpose**: Python client for remote HBM model inference on Horizon J6 development boards via gRPC
- **Role**: Host-side component in the AI toolchain; uploads models to the board, sends input tensors, receives inference results
- **Architecture**: Client-server model — Python client on PC, native C++ gRPC server (`hbm_rpc_service`) on the J6 board running UCP inference
- **Dependencies**: grpcio 1.66.1, protobuf >=3.20.3 <=4.23.0, paramiko >=3.1.0, scp >=0.12.0, typeguard >=2.13.3, numpy, torch

## 目录结构

```
hbm_infer-3.15.3-py3/
  CLAUDE.md                                    # 项目说明文档
  hbm_infer/
    __init__.py                                # 包入口，仅导出 HbmRpcSession
    hbm_rpc_session.py                         # 主接口层（带 typeguard 类型检查），组合 HbmRpcServer + HbmHandle + base session
    hbm_rpc_session_flexible.py                # 核心实现层：HbmRpcServer, HbmHandle, HbmRpcSession(base)
    utils.py                                   # SSH/SCP 工具函数, HTensor, Logger, ProfileMeters, AverageMeter
    frame_pb2.py                               # protobuf 自动生成的消息定义（Frame, Tensor, ModelInferInfo 等）
    frame_pb2_grpc.py                          # protobuf 自动生成的 gRPC stub（GrpcCommu service）
    grpctest/
      __init__.py
      test_grpc_client.py                      # gRPC 连通性测试客户端
      test_grpc_server_linux                   # Linux 测试服务器二进制
      test_grpc_server_qnx                     # QNX 测试服务器二进制
    perftest/
      __init__.py
      test_performance.py                      # 性能基准测试工具（PerfStat 类，iperf3 带宽测试）
    server_linux/
      bin/hbm_rpc_service                      # Linux 板端 gRPC 推理服务二进制
      lib/*.so                                 # 依赖库（libdnn, libhbucp, libhbrt4 等）
    server_qnx/
      bin/hbm_rpc_service                      # QNX 板端 gRPC 推理服务二进制
      lib/*.so                                 # QNX 依赖库
  hbm_infer-3.15.3.dist-info/                  # 包元数据（METADATA, WHEEL, RECORD）
```

## 关键模块与 API

### HbmRpcSession（主入口）
- `from hbm_infer import HbmRpcSession`
- 支持上下文管理器 (`with ... as session`)，自动调用 `close_server()`
- 构造函数签名：
  ```python
  HbmRpcSession(
      host: str,                          # 开发板 IP
      local_hbm_path: Union[str, List[str]],  # HBM 模型文件路径（支持多模型）
      username: str = "root",
      password: Optional[str] = None,
      ssh_port: int = 22,
      remote_root: str = "/map/hbm_infer/",
      frame_timeout: int = 90,            # 单帧 gRPC 超时（秒）
      server_timeout: int = 5,            # 服务端超时（分钟），超时自动清理
      with_profile: bool = False,         # 启用各阶段耗时统计
      debug: bool = False,
      compress_option: str = "NONE",      # "NONE" | "IN" | "INOUT"
      core_id: Union[int, List[int]] = -1,  # BPU core ID，-1=CORE_ANY
      remote_environment: Dict[str, Any] = {},  # 板端环境变量
  )
  ```
- 推理调用：`session(data: Dict[str, ndarray|Tensor|HTensor], output_config=None, model_name=None) -> Dict`
- 模型信息：`get_model_names()`, `get_input_info(model_name)`, `get_output_info(model_name)`, `show_input_output_info(model_name)`
- 性能统计：`get_profile(model_name)`, `get_profile_last_frame(model_name)`
- 清理：`close_server()` — 发送 MODEL_RELEASE，删除远程目录，关闭 gRPC channel

### HbmRpcServer / HbmHandle（flexible 层）
- `HbmRpcServer(host, username, password, ssh_port, remote_root)` — 检测板端 OS(Linux/QNX)，上传 server 二进制，管理 token 隔离目录
- `HbmHandle(local_hbm_path, hbm_rpc_server)` — 上传 HBM 文件，MD5 token 去重
- `init_server()` / `deinit_server()` / `init_hbm()` / `deinit_hbm()` — 便捷工厂函数

### HTensor（utils.py）
- `HTensor(data: ndarray|Tensor|None, device: str|List[str]|None, key: Optional[str])`
- device 取值：`"cpu"`, `"bpu"`, `["cpu","bpu"]`；BPU tensor 必须提供唯一 `key`
- `device` 和 `key` 构造后不可变；`data` 可更新但类型必须一致

### Protobuf Frame 消息类型
- `MODEL_LOAD` (0), `MODEL_INFERENCE` (1), `MODEL_RELEASE` (2), `TENSOR_RELEASE` (3), `HEARTBEAT` (4)
- 通信服务：`GrpcCommu.Communicate(Frame) -> Frame`

### 性能测试工具
- `python -m hbm_infer.perftest.test_performance --device <ip> --model_file <hbm> --epoch 200`

## 常用查询映射

| 用户意图 | 推荐搜索关键词 | 说明 |
|---------|--------------|------|
| 模型推理 / model inference | `HbmRpcSession`, `__call__`, `_sync_infer`, `MODEL_INFERENCE` | 推理入口是 session(data) 调用 |
| 加载 HBM 模型 | `HbmHandle`, `_send_model_frame`, `MODEL_LOAD`, `remote_upload` | 模型通过 SCP 上传后发 MODEL_LOAD 帧 |
| 释放模型 / 关闭会话 | `close_server`, `MODEL_RELEASE`, `deinit`, `__exit__` | 必须显式调用 close_server 或用 with |
| 多模型推理 | `local_hbm_path: List[str]`, `model_name`, `get_model_names` | 多模型需每次指定 model_name |
| 获取模型输入输出信息 | `get_input_info`, `get_output_info`, `show_input_output_info`, `model_info` | 返回 name, valid_shape, tensor_type, quanti_type 等 |
| 性能统计 / profiling | `with_profile`, `get_profile`, `ProfileMeters`, `AverageMeter` | 统计 frame/sd2rv/commu/board/infer/prepr/pospr 各阶段耗时 |
| 性能基准测试 | `PerfStat`, `test_performance`, `test_bandwidth`, `iperf3` | 命令行工具，支持批量 .hbm 文件测试 |
| SSH 连接 / 文件上传 | `get_ssh_channel`, `remote_upload`, `remote_execute`, `paramiko`, `scp` | SSH 信号量限制 4 并发，重试 5 次 |
| gRPC 通道配置 | `_init_grpc`, `grpc.insecure_channel`, `service_config`, `retryPolicy` | 内置重试策略，最大消息 2GB |
| gRPC 连通性测试 | `TestClient`, `test_grpc_client`, `GrpcCommuStub` | 基础 echo 测试 |
| 板端 OS 检测 | `uname -s`, `remote_os`, `server_linux`, `server_qnx` | 自动选择 Linux/QNX 二进制包 |
| BPU core 指定 | `core_id`, `CORE_ANY`, `compile_bpu_core_num` | 多核模型自动校验 core 数量 |
| tensor 包装 / HTensor | `HTensor`, `device`, `key`, `TENSOR_TAG_HOLDER`, `TENSOR_TAG_FILTER` | BPU tensor 用于板端数据复用 |
| 输出控制 / output_config | `output_config`, `tensor_tag`, `TENSOR_TAG_FILTER`, `_valid_output_config` | 控制输出是否回传或在板端保留 |
| 心跳机制 | `heartbeat_thread`, `HEARTBEAT`, `heartbeat_interval`, `heartbeat_timeout` | 守护线程默认 20s 间隔，10s 超时 |
| 数据类型映射 | `hbm_map_torch`, `hbm_map_numpy`, `hbm_map_bits`, `DataType` | S8/U8/S16/S32/F16/F32/F64 等 |
| 动态输入形状 | `valid_shape`, `-1`, `_check_input_types` | shape 中 -1 表示动态维度 |
| 压缩传输 | `compress_option`, `IN`, `INOUT`, `grpc.Compression.Gzip` | INOUT 启用双向 gRPC gzip 压缩 |
| 资源清理 / 远程目录 | `remote_root`, `token`, `_remove_remote_folder`, `deinit` | 每个组件生成唯一 token 隔离目录 |
| 会话令牌 | `token`, `os.getpid()`, `threading.current_thread().ident`, `time.time_ns()` | pid+tid+ns 时间戳组合 |
| 错误处理 / 超时 | `RemoteHbmInferTimeoutError`, `RemoteHbmInferStatusError`, `DEADLINE_EXCEEDED` | gRPC 超时和状态错误异常类 |
| 日志系统 | `Logger`, `SafeLog`, `logger` | 自定义 formatter，SafeLog 异常安全 |
| 板端服务器启动 | `_start_server`, `hbm_rpc_service`, `run_server.sh`, `nohup` | 远程生成启动脚本，nohup 后台运行 |
| gRPC 端口分配 | `custom_grpc_port`, `available_port.txt`, `AvailablePort` | 服务端动态分配端口，客户端读取 |
| 输入类型校验 | `_check_input_types`, `_determine_return_types` | 不允许 numpy/torch 混用，torch 须同 device |
| 量化信息 | `quanti_type`, `QUANTI_TYPE_SCALE`, `QuantiScaleInfo`, `quantizeAxis` | 支持 scale 量化，含 axis/scale/zero_point |

## 规则与约定

- **必须显式清理**: 始终使用 `with` 语句或显式调用 `close_server()`，`__del__` 仅发出警告不保证清理
- **输入一致性**: 单次推理不可混合 `numpy.ndarray` 和 `torch.Tensor`；所有 torch tensor 必须在同一 device 上
- **多模型会话**: 传入多个 HBM 路径时，每次推理必须指定 `model_name` 参数
- **BPU tensor 规则**: device 含 `"bpu"` 的 HTensor 必须指定唯一 `key`，且不能包含主机端数据
- **HTensor 不可变属性**: `device` 和 `key` 构造后不可修改，`shape` 也不允许用户自定义设置
- **SSH 并发限制**: 全局信号量限制最多 4 个并发 SSH 连接
- **重试机制**: SSH/SCP 操作默认最多重试 5 次，间隔 2 秒；gRPC 内置 5 次重试（20s 间隔）
- **服务端超时**: `server_timeout` 以分钟为单位，超时后服务端自动终止并清理非日志文件
- **日志格式**: `[级别首字母][时间][hbm_infer][文件:行号] 消息`
- **性能统计单位**: 所有 profile 数据以微秒(us)采集，以毫秒(ms)展示
- **服务端目录结构**: `{remote_root}/{token}/` 下含 `aarch64/bin`, `aarch64/lib`, `log/`, `script/` 子目录
