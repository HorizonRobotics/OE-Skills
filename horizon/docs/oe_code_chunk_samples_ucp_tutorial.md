# oe_code_chunk_samples_ucp_tutorial

## 仓库概述

- **名称**: UCP Tutorial Samples (ucp_tutorial)
- **版本**: Horizon J6 Open Explorer SDK v3.9.0 RC4
- **路径**: `samples/ucp_tutorial/`
- **用途**: 提供 C++ 示例程序，演示如何在 J6 (Journey 6) BPU SoC 上使用 Horizon UCP (Unified Computing Platform) 系列 API
- **角色**: AI 工具链中的端侧部署参考实现，覆盖 DNN 推理、视觉处理 (VP)、高性能库 (HPL)、DSP/GPU 自定义算子、端到端感知流水线及模型执行工具
- **目标平台**: aarch64 Linux / QNX / Android (J6 开发板)，x86 主机仿真

## 目录结构

```
ucp_tutorial/
├── all-round/                  # 端到端感知流水线: 摄像头→推理→后处理→编解码→Web展示
│   ├── src/main.cc             # 流水线主入口，模块创建与链接
│   ├── src/modules/            # BaseModule 子类: camera_input, inference, postprocess, codec, web_display
│   ├── include/                # 头文件: base_module.h, message/, utils/
│   ├── deploy/script/          # 板上部署脚本、configs (JSON)、webservice
│   └── protocol/               # protobuf 定义 (frame.proto)
├── dnn/
│   ├── basic_samples/code/     # DNN API 教程
│   │   ├── 00_quick_start/     # resnet_nv12, resnet_rgb — 最简推理示例
│   │   ├── 01_api_tutorial/    # mem/model/padding/quanti — 各 API 用法
│   │   └── 02_advanced_samples/# crop/multi_model_batch/roi_infer — 进阶用法
│   └── ai_benchmark/code/      # AI Benchmark: 分类/检测/分割模型精度&性能评测
├── custom_operator/
│   ├── dsp_sample/             # DSP 自定义算子 (quantize, dequantize, softmax, demosaicing, CenterPoint, PointPillar, SLAM)
│   │   ├── arm_code/           # ARM 侧 RPC 调度代码
│   │   └── dsp_code/           # DSP 固件侧算子实现 (IVP intrinsics)
│   └── gpu_sample/             # GPU (OpenCL 3.0) 自定义算子 (图像阈值 threshold.cl)
├── vp/code/                    # VP 视觉处理示例
│   ├── 01_basic_processing/    # 滤波 (bilateral/box/gaussian/median)、形态学 (dilate/erode/open/close/edge)
│   ├── 02_transformation/      # resize, flip, rotate, transpose, warp_affine, warp_perspective, pyr_up/down
│   ├── 03_feature_extraction/  # Canny, Sobel, 形态学边缘检测
│   ├── 04_optical_flow/        # Harris 角点 + Lucas-Kanade 光流
│   ├── 05_avm/                 # 环视 AVM (GDC map + stitch LUT)
│   └── 06_codec/               # H.264/H.265 编解码
├── hpl/code/                   # HPL 高性能库: FFT/IFFT (1D/2D, float32)
├── tools/
│   ├── hrt_model_exec/         # CLI 工具: model_info / infer / perf 子命令
│   ├── monitor/                # UCP 监控二进制
│   ├── trace/                  # ftrace 配置: BPU/DSP/system 追踪
│   └── deb/                    # 预编译 UCP .deb 包
├── deps_aarch64/               # aarch64-linux 预编译依赖 (ucp, opencv, gflags, hlog, fmt, zlib...)
├── deps_qnx/                   # aarch64-qnx 预编译依赖
├── deps_android/               # aarch64-android 预编译依赖
└── deps_x86/                   # x86 仿真预编译依赖
```

## 关键模块与 API

### DNN 推理核心 API (hb_dnn.h + hb_ucp.h)

所有 DNN 示例遵循 **6 步标准流程**:

```
Step1: hbDNNInitializeFromFiles(&packed_handle, &modelFile, 1)
       → hbDNNGetModelNameList → hbDNNGetModelHandle(&dnn_handle, ...)
Step2: hbDNNGetInputCount / hbDNNGetOutputCount
       → hbDNNGetInputTensorProperties / hbDNNGetOutputTensorProperties
       → hbUCPMallocCached(&tensor.sysMem, size, 0)  // 分配缓存一致内存
Step3: 填充输入数据 (注意 stride 对齐: J6=32字节, J6P=64字节)
       → hbUCPMemFlush(&sysMem, HB_SYS_MEM_CACHE_CLEAN)  // 写回缓存
Step4: hbDNNInferV2(&task_handle, output, input, dnn_handle)
       → hbUCPSubmitTask(task_handle, &ctrl_param)  // ctrl_param.backend = HB_UCP_BPU_CORE_ANY
       → hbUCPWaitTaskDone(task_handle, 0)
Step5: hbUCPMemFlush(&sysMem, HB_SYS_MEM_CACHE_INVALIDATE)  // 失效缓存后读取输出
Step6: hbUCPReleaseTask → hbUCPFree → hbDNNRelease
```

关键头文件: `hobot/dnn/hb_dnn.h`, `hobot/hb_ucp.h`, `hobot/hb_ucp_sys.h`

### VP 视觉处理 API (hb_vp.h)

- 核心类型: `hbVPImage` (含 format, type, width, height, stride, virAddr, sysMem)
- 内存分配: `hbUCPMallocCached` + `hbUCPMemFlush(HB_SYS_MEM_CACHE_CLEAN)`
- API 示例: `hbVPBilateralFilter`, `hbVPBoxFilter`, `hbVPGaussianBlur`, `hbVPMedianBlur`
- 形态学: `hbVPDilate`, `hbVPErode`, `hbVPMorphologyEx` (OPEN/CLOSE/EDGE)
- 变换: `hbVPResize`, `hbVPFlip`, `hbVPRotate`, `hbVPTranspose`, `hbVPWarpAffine`, `hbVPWarpPerspective`
- 特征: `hbVPCanny`, `hbVPSobel`, `hbVPHarrisCorner`
- 光流: `hbVPOpticalFlowPyrLK`
- 编解码: `hbVPDecode`, `hbVPEncode`

### HPL 高性能库 API (hb_fft.h, hb_ifft.h)

- FFT: `hbFFT1D(task_handle, &dst, &src, &param)` — task_handle=nullptr 立即执行
- IFFT: `hbIFFT1D(task_handle, &dst, &src, &param)`
- 数据类型: `hbHPLImaginaryData`, `hbFFTParam`, `hbFFTPointSize`

### DSP 自定义算子 (hb_dsp.h)

- DSP 固件入口: `hb_dsp_env_init_ex` → `hb_dsp_init_global_tm` → `hb_dsp_register_fn(id, func, 0)` → `hb_dsp_start()`
- ARM 侧通过 RPC 调用 DSP 函数，DSP 侧使用 IVP (Image/Vector Processing) intrinsics
- 算子注册 ID: 0x1400(quantize), 0x1401(dequantize), 0x1402(softmax), 0x1403(centerpoint), 0x1404(pointpillar), 0x1405(slam)

### GPU 自定义算子 (OpenCL 3.0)

- 标准 OpenCL 流程: `clGetPlatformIDs` → `clGetDeviceIDs` → `clCreateContext` → `clCreateCommandQueueWithProperties` → `clBuildProgram` / `clCreateKernel`
- 支持源码编译 (.cl) 和二进制缓存 (.bin)

### all-round 流水线架构

- `BaseModule`: 线程化执行单元，`SlotQueue` (mutex+condvar) 消息传递
- `LinkTo()` 连接模块，`ModuleRun()` 循环接收消息并 `Feed()` 下游
- 管线: `CameraInputModule → InferenceModule → PostProcessModule → WebDisplayModule`
- 配置: JSON (`JsonConfigWrapper`), 位于 `configs/` 目录

### hrt_model_exec 工具

- 子命令: `model_info` (查看模型信息), `infer` (执行推理), `perf` (性能测试)
- 参数: `--model_file`, `--input_file`, `--core_id`, `--input_img_properties`, `--input_valid_shape`, `--frame_count`

## 常用查询映射

| 用户意图 | 推荐搜索关键词 | 说明 |
|---------|-------------|------|
| DNN 推理完整流程 | `hbDNNInferV2`, `hbUCPSubmitTask`, `hbUCPWaitTaskDone` | quick_start/resnet_nv12/src/main.cc 是最佳入门参考 |
| 模型加载与初始化 | `hbDNNInitializeFromFiles`, `hbDNNGetModelHandle` | 从 .hbm 文件加载模型 |
| Tensor 内存分配 | `hbUCPMallocCached`, `hbDNNTensor`, `alignedByteSize` | 分配缓存一致的物理内存 |
| Cache 一致性/刷新 | `hbUCPMemFlush`, `HB_SYS_MEM_CACHE_CLEAN`, `HB_SYS_MEM_CACHE_INVALIDATE` | 推理前 CLEAN, 推理后 INVALIDATE |
| 任务提交与等待 | `hbUCPSubmitTask`, `hbUCPWaitTaskDone`, `hbUCPSchedParam` | ctrl_param.backend 可选 HB_UCP_BPU_CORE_ANY |
| 资源释放 | `hbUCPReleaseTask`, `hbUCPFree`, `hbDNNRelease` | 按 task→mem→model 顺序释放 |
| Stride 对齐 | `ALIGN_32`, `ALIGN_64`, `BPU_ALIGN`, `PLATFORM_J6P` | J6 对齐 32 字节, J6P 对齐 64 字节 |
| 多模型/批量推理 | `multi_model_batch`, `hbDNNInferV2` | 02_advanced_samples/multi_model_batch |
| ROI 推理 | `roi_infer`, `validShape` | 02_advanced_samples/roi_infer |
| 量化参数查询 | `quanti_example`, `hbDNNGetInputTensorProperties` | 01_api_tutorial/quanti |
| AI Benchmark 评测 | `ai_benchmark`, `ptq_classification`, `ptq_yolo` | 分类/检测/分割精度&性能评测框架 |
| DSP 自定义算子 | `hb_dsp_register_fn`, `hb_dsp_start`, `IVP` | dsp_code/custom_operator/main.cc |
| DSP 固件部署 | `dsp_deploy.sh`, `hb_dsp_env_init_ex` | 需先在板上执行部署脚本 |
| GPU OpenCL 算子 | `clCreateKernel`, `clBuildProgram`, `threshold.cl` | gpu_sample 图像阈值示例 |
| VP 图像处理 | `hbVPBilateralFilter`, `hbVPResize`, `hbVPDilate` | vp/code/01~06 各子目录 |
| VP 编解码 | `hbVPDecode`, `hbVPEncode`, H.264, H.265 | vp/code/06_codec |
| VP AVM 环视 | `gdc_map_helper`, `stitch_lut_helper` | vp/code/05_avm |
| VP 光流 | `hbVPOpticalFlowPyrLK`, `hbVPHarrisCorner` | vp/code/04_optical_flow |
| HPL FFT/IFFT | `hbFFT1D`, `hbIFFT1D`, `hbHPLImaginaryData` | hpl/code/01_fft_ifft_transform |
| 端到端流水线 | `BaseModule`, `SlotQueue`, `LinkTo`, `ModuleRun` | all-round 目录 |
| 模型信息查看 | `hrt_model_exec model_info` | tools/hrt_model_exec |
| 推理性能测试 | `hrt_model_exec perf`, `--frame_count` | tools/hrt_model_exec |
| BPU/DSP 性能追踪 | `ftrace`, `ucp_bpu_trace.cfg`, `catch_trace.sh` | tools/trace |
| 交叉编译 | `build_aarch64.sh`, `LINARO_GCC_ROOT` | 各子目录下的 build 脚本 |
| QNX 构建 | `build_qnx.sh`, `_QNX_SOURCE` | 添加 QNX 特定编译标志 |
| protobuf 通信 | `frame.proto`, `uws_server` | all-round WebSocket 服务 |
| 摄像头输入 | `CameraInputModule`, `cam_module_config.json` | all-round 流水线起始模块 |

## 规则与约定

### 命名空间与代码风格
- 命名空间: `hobot::sample` (all-round), `hobot` (其余模块)
- 头文件保护: `PROJECT_PATH_FILE_H_` 模式 (如 `ALL_ROUND_INCLUDE_MODULES_BASE_MODULE_H_`)
- 源文件扩展名: `.cc` (DNN/all-round/ai_benchmark), `.cpp` (VP/HPL/hrt_model_exec/GPU)
- 日志宏: `LOGI`, `LOGD`, `LOGW`, `LOGE` (来自 `hobot/hlog` 或本地 `log_util.h`)
- 错误检查宏: `HB_CHECK_SUCCESS`, `LOGE_AND_RETURN_IF`

### 构建系统
- CMake (2.8~3.0) + 平台构建脚本 (`build_aarch64.sh`, `build_qnx.sh`, `build_x86.sh`)
- 交叉编译器: ARM GCC 12.2, 默认路径 `/arm-gnu-toolchain-12.2.rel1-x86_64-aarch64-none-linux-gnu`
- C++ 标准: C++11 (多数项目), C++17 (gpu_sample, hrt_model_exec)
- 依赖: 预编译在 `deps_<platform>/` 目录，CMakeLists.txt 通过 `DEPS_ROOT` 引用

### 常见陷阱
- **必须保留** `-Wl,-unresolved-symbols=ignore-in-shared-libs` 链接标志 (UCP 共享库依赖板上系统库)
- **Stride 对齐**: J6 用 32 字节, J6P 用 64 字节，不对齐会导致 BPU 推理结果错误
- **Cache 一致性**: 推理前必须 `HB_SYS_MEM_CACHE_CLEAN`, 推理后必须 `HB_SYS_MEM_CACHE_INVALIDATE`
- **DSP 固件**: 执行 DSP 算子测试前必须先运行 `dsp_deploy.sh` 加载固件；DSP 挂起需重启固件
- **模型文件**: `.hbm` 文件不包含在 tutorial 包中，需从 OE 工具包单独获取
- **x86 构建**: 添加 `-DUCP_X86` 或 `-DTOOLS_X86` 宏定义用于主机仿真
- **板上运行**: 需设置 `export LD_LIBRARY_PATH=./lib:${LD_LIBRARY_PATH}`
