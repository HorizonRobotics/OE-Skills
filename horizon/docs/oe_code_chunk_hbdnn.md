# oe_code_chunk_hbdnn

## 仓库概述

- **名称**: hbdnn (Horizon BPU DNN 算子库) v1.0.3
- **Python 包**: `hbdnn-1.0.3-py3`，预编译 wheel 分发包（非 git 仓库，无可构建源码）
- **用途**: HBDK4 编译器栈中 DNN 算子的 CUDA 参考实现库，供 x86-64 主机侧模拟和验证量化算子行为
- **角色**: J6 Open Explorer (OE) v3.9.0-rc4 工具链的底层依赖，位于 `package/host/ai_toolchain/code/` 下
- **核心产物**: `hbdnn/libhbdnn.so`（ELF x86-64，~9.5 MB，含 debug_info）
- **Python API**: 无（`__init__.py` 为空）；所有功能通过 C++ 共享库导出，由 HMCT/编译器在 C++ 层调用
- **运行时依赖**: libcudnn.so.9（卷积/池化）、libcublas.so.12（INT8 GEMM）、libgomp.so.1（OpenMP 并行）
- **加载方式**: 作为 UDE (User Defined Engine) 插件被 HBTL 框架动态加载（导出 `UDE_LIBRARY_MAIN` / `UDE_ABI_CHECK`）

## 目录结构

```
hbdnn-1.0.3-py3/
  CLAUDE.md                          # 仓库级说明（架构、依赖、算子列表、调用链）
  hbdnn/                             # 主包目录（pip top_level 注册）
    __init__.py                      #   空文件，无 Python API（仅占位使 pip 识别为包）
    libhbdnn.so                      #   核心产物：DNN 算子 CUDA 参考实现共享库（~9.5 MB）
  python/                            # 辅助 Python 包（pip top_level 注册）
    __init__.py                      #   空占位文件，无实际代码
  hbdnn-1.0.3.dist-info/             # wheel 分发元数据
    METADATA                         #   包元信息（name=hbdnn, version=1.0.3）
    WHEEL                            #   wheel 构建器与标签信息
    RECORD                           #   文件清单与 SHA256 校验和
    top_level.txt                    #   顶层包名列表：hbdnn, python
  .claude/
    settings.local.json              #   Claude Code 本地权限与行为配置
```

> **注意**：这是一个极简的 wheel 包——仅包含一个 .so 文件和两个空的 `__init__.py`。所有功能由 C++ 共享库提供，不通过 Python 层暴露。

## 关键模块与 API

### 命名空间分层

| 命名空间 | 职责 |
|---|---|
| `hbdnn::` | 核心算子实现层：`*OpCpu` / `*OpGpu` / `*Forward` 三种入口；`OpContext`（运行上下文）、`*Descriptor`（算子参数描述符）、`DLTensor`（张量载体） |
| `hbdnn::cuda::` | 底层 CUDA kernel 层（`__device_stub__` 入口）：`ForwardBias`、`CalcMinShift`、`ElementwiseAdd`、`QuantiBatchnormKernel`、`VecShiftInput`、`TransposeWeight` 等 |
| `hbtl::b30::` / `hbtl_gpu::b30::` | UDE 框架算子注册入口，面向 B30 芯片（J6），分发到 `hbdnn::` 实现 |
| `hbtl_gpu::hbir::` | UDE 框架数据变换入口（Reshape、Transpose） |

### HBTL UDE 入口函数（C++ 签名）

- `hbtl::b30::Conv2d(DLTensor&, input, weight, bias, shift, scale, groups, strides, pads, dilations, layout, relu, ...)`
- `hbtl::b30::MaxPool2d(DLTensor&, input, kernel, strides, pads, ceil_mode, ...)`
- `hbtl::b30::AvgPool2d(DLTensor&, input, kernel, strides, pads, ceil_mode, divisor, ...)`
- `hbtl::b30::HBDNNEltLut(DLTensor&, input, lut_table, ..., method, mode, ...)`
- `hbtl_gpu::b30::ComplexBinary(DLTensor&, input_a, input_b, bias, op_a, op_b, ...)`
- `hbtl_gpu::hbir::Reshape(DLTensor&, input, shape)`
- `hbtl_gpu::hbir::Transpose(DLTensor&, input, perm)`

### 核心算子实现函数

- `hbdnn::ForwardConvGpu<T>(OpContext, input, bias, weight, output, ...)` -- INT8/INT32 卷积前向
- `hbdnn::ScaleQuantiConvolutionDescriptor` -- Scale 量化卷积参数描述符
- `hbdnn::QuantiPoolingDescriptor` -- 量化池化参数描述符
- `hbdnn::Int8Gemm(OpContext, A, B, C, M, N, K)` -- INT8 矩阵乘法（cuBLAS 后端）
- `hbdnn::CublasInt8GemmWithoutPadding(...)` -- 无 padding 的 INT8 GEMM
- `hbdnn::ElementwiseAddGpu(OpContext, ...)` -- 逐元素加法
- `hbdnn::QuantiBatchnormGpu(OpContext, ...)` -- 量化批归一化
- `hbdnn::MaxPoolForwardInt8Kernel(OpContext, ...)` -- INT8 最大池化
- `hbdnn::ComputeComplexBinaryGpu<A,B,C>(OpContext, ...)` -- 二值运算（add/sub/mul 等组合）
- `hbdnn::ReshapeDescriptor` / `hbdnn::TransposeDescriptor` -- 数据变换描述符

### 基础设施类

- `hbdnn::OpContext` -- 算子运行上下文（含 CUDA stream、device id 等）
- `hbdnn::CudnnHandle::Get()` -- cuDNN 句柄单例
- `hbdnn::CublasHandle::Get()` -- cuBLAS 句柄单例
- `hbdnn::DeviceGuard(int)` -- CUDA 设备切换 RAII 守卫
- `hbdnn::CreateDLTensor<T, N>(data, shape, device, dtype)` -- 创建 DLTensor
- `hbdnn::GetTensorWithShape<device, N, T>(DLTensor, shape, stream)` -- 从 DLTensor 获取 mshadow Tensor
- `hbdnn::LayoutFlag` -- 布局枚举（NHWC / NCHW 等）
- `hbdnn::QuantiType` -- 量化类型枚举

## 常用查询映射

| 用户意图 | 推荐搜索关键词 | 说明 |
|---|---|---|
| DNN 算子库入口 | `UDE_LIBRARY_MAIN`, `libhbdnn` | UDE 插件加载入口点 |
| 卷积算子实现 | `ForwardConvGpu`, `ScaleQuantiConvolution` | INT8 量化卷积前向（含 NHWC 变体） |
| 矩阵乘法 / GEMM | `Int8Gemm`, `CublasInt8GemmWithoutPadding`, `cuBLAS` | INT8 GEMM 加速 |
| 池化算子 | `MaxPool2d`, `AvgPool2d`, `QuantiPooling`, `MaxPoolForwardInt8Kernel` | 最大/平均池化 |
| 批归一化 | `QuantiBatchnorm`, `QuantiBatchnormKernel` | 量化 BN 层 |
| 逐元素运算 | `ElementwiseAdd`, `ElementwiseAddGpu` | 张量逐元素加法 |
| 二值运算 | `ComplexBinary`, `ComputeComplexBinaryGpu` | 二值网络算子（XNOR 等） |
| 查表算子 | `HBDNNEltLut`, `HbtlEltLUT` | Element-wise LUT 查表 |
| 数据变形 | `Reshape`, `Transpose`, `ReshapeDescriptor`, `TransposeDescriptor` | 张量形状变换 |
| Bias 处理 | `ForwardBias`, `ForwardBiasGpu`, `InitIntBias`, `ScaleQuantiInitIntBias` | 偏置初始化与加法 |
| 量化位移 | `CalcMinShift`, `CalcMinShiftGpu`, `VecShiftInput` | 量化参数 shift 计算 |
| 张量创建 | `CreateDLTensor`, `DLTensor`, `GetTensorWithShape` | 张量分配与形状获取 |
| 运行上下文 | `OpContext` | 算子运行上下文（stream、device） |
| cuDNN 集成 | `CudnnHandle`, `cudnn` | cuDNN 句柄管理与调用 |
| cuBLAS 集成 | `CublasHandle`, `cublas` | cuBLAS 句柄管理与调用 |
| CUDA 设备管理 | `DeviceGuard`, `GetCudaNumBlocks` | GPU 设备切换、线程块计算 |
| 布局格式 | `LayoutFlag`, `NHWC`, `NCHW` | 张量内存布局枚举 |
| 量化类型 | `QuantiType` | 量化方式枚举 |
| B30 芯片算子 | `hbtl::b30::`, `hbtl_gpu::b30::` | 面向 J6/B30 的 UDE 算子注册 |
| HBTL 框架集成 | `hbtl`, `hbtl_gpu`, `UDE_ABI_CHECK` | HBTL 模板库分发层 |
| mshadow 张量库 | `mshadow::Shape`, `mshadow::Tensor`, `mshadow::cpu/gpu` | 底层张量运算库 |
| ReLU 激活 | `VecReluGpu`, `ReluActivication` | 向量 ReLU 激活 |
| 反向/反量化 | `VecReverseInt32Input` | INT32 反量化到浮点 |
| 主机侧算子仿真 | `*OpCpu`, `mshadow::cpu` | CPU 侧算子参考实现 |
| GPU 侧算子加速 | `*OpGpu`, `*Gpu`, `mshadow::gpu` | CUDA GPU 侧算子实现 |
| 算子参数描述 | `*Descriptor` (各算子描述符类) | 算子超参数配置结构体 |
| PTQ 量化精度校验 | `ScaleQuanti`, `Quanti`, `hbdnn` | PTQ 流程中主机侧算子校验 |
| HMCT 量化调试 | `hbdnn`, `libhbdnn`, `cuda` | HMCT 调试时 CPU/GPU 参考计算 |
| 模型编译仿真 | `ForwardConv`, `ForwardBias`, `hbdnn` | 编译阶段算子行为仿真 |
| DNN 推理示例 | `samples/ucp_tutorial/dnn/` | 基于 DNN API 的 C++ 推理示例（在 OE 包外部） |
| 权重转置 | `TransposeWeight` | 权重张量布局转换 |
| CUDA kernel 入口 | `__device_stub__`, `hbdnn::cuda::` | CUDA kernel 设备端函数 |

## 规则与约定

- **本目录是预编译分发包**：无源码、无构建脚本、无测试；不可编译或修改，仅作为运行时依赖被消费
- **无 Python API**：`import hbdnn` 不会报错但无任何可用函数；实际使用需通过 C++ 链接 `libhbdnn.so`
- **命名规范**：算子函数以 `*OpCpu` / `*OpGpu` / `*Forward` 后缀区分 CPU/GPU/前向实现；CUDA kernel 在 `hbdnn::cuda::` 命名空间
- **HBTL 调用链**：`HBTL (B30 dispatch) → UDE plugin loader → libhbdnn.so → hbdnn::*OpCpu/OpGpu → cuDNN/cuBLAS`
- **张量格式**：默认 NHWC 布局（BPU 原生），部分算子提供 NCHW 变体；通过 `LayoutFlag` 枚举切换
- **量化数据类型**：INT8 (`signed char`) 为主流量化精度，INT16 (`short`) 和 INT32 (`int`) 用于中间累加和高精度场景
- **模板实例化**：`ComputeComplexBinaryGpu`、`ForwardConvGpu`、`VecShiftInput` 等按输入/权重/输出数据类型组合进行模板实例化
- **环境要求**：主机需 CUDA 12.x + cuDNN 9，`LD_LIBRARY_PATH` 须包含 CUDA 库路径；缺少依赖会导致 `ImportError` 或 `dlopen` 失败
- **相关示例代码**：位于 OE 包的 `samples/ucp_tutorial/dnn/` 目录（`basic_samples/` 推理入门、`ai_benchmark/` 性能测试），通过 CMake + `build_x86.sh` / `build_aarch64.sh` 构建
- **调试提示**：`libhbdnn.so` 含 debug_info（未 strip），可用 `nm -D --defined-only | c++filt` 查看完整导出符号
- **符号可见性**：仅 UDE 入口函数和核心算子标记为 `T`（全局可见），大量辅助函数为 `W`（弱符号，模板实例化产生）
- **板端 vs 主机端**：hbdnn 不运行在 J6 板端（板端走 `hbdk4_runtime` + BPU 路径），仅用于主机侧编译/量化/校验流程
- **常见误区**：不要试图直接 `import hbdnn` 来使用算子功能；hbdnn 被 HMCT 编译器工具链在 C++ 层隐式调用，Python 用户无需直接交互
