# OpenExplorer 代码仓库索引 (oe-mcp)

> 本文件为 oe-mcp `search_code` 的路由入口。根据用户意图中的关键词，定位到对应仓库的详细索引文件。
> 版本: J6 OpenExplorer v3.9.0 RC4 | BPU: Nash 系列 (NASH_B / NASH_P / NASH_E)

## 仓库总览

| 仓库索引文件 | 包名 | 版本 | 一句话说明 |
|-------------|------|------|-----------|
| [hbdk4_compiler](oe_code_chunk_hbdk4_compiler.md) | hbdk4-compiler | 4.11.2 | BPU 模型编译器：ONNX → HBIR → HBDK → .hbm |
| [hbdk4_march](oe_code_chunk_hbdk4_march.md) | hbdk4-march | 4.11.2 | BPU 架构描述：march 枚举、核心数、平台映射 |
| [hbdnn](oe_code_chunk_hbdnn.md) | hbdnn | 1.0.3 | DNN 推理运行时：C++ API，模型加载、推理执行 |
| [hbm_infer](oe_code_chunk_hbm_infer.md) | hbm-infer | 3.15.3 | Python 推理服务：gRPC 远程推理、模型管理 |
| [hmct](oe_code_chunk_hmct.md) | hmct | 2.8.3 | 模型转换 & PTQ 量化工具（CPU 版） |
| [hmct_gpu](oe_code_chunk_hmct_gpu.md) | hmct-gpu | 2.8.3+cu128 | 模型转换 & PTQ 量化工具（GPU/CUDA 加速版） |
| [horizon_plugin_profiler](oe_code_chunk_horizon_plugin_profiler.md) | horizon-plugin-profiler | 3.3.4 | QAT 分析插件：profiling、相似度、敏感度分析 |
| [horizon_plugin_pytorch](oe_code_chunk_horizon_plugin_pytorch.md) | horizon-plugin-pytorch | 3.3.4 | PyTorch QAT 插件：量化训练、FX/Eager 模式 |
| [horizon_tc_ui](oe_code_chunk_horizon_tc_ui.md) | horizon-tc-ui | 3.5.16 | 工具链 CLI & UI：hb_compile、可视化、报告 |
| [ucp_tutorial](oe_code_chunk_samples_ucp_tutorial.md) | samples/ucp_tutorial | — | UCP C++ 教程：DNN/VP/HPL/DSP/GPU 推理示例 |
| [llm_compression](oe_code_chunk_llm_compression.md) | llm_compression | 2.0.2 | LLM/VLM PTQ 量化 & 编译工具：校准 → 编译 → HBM |
| [oellm_runtime](oe_code_chunk_oellm_runtime.md) | oellm_runtime | 2.0.2 | OE LLM 运行时 SDK：板端 VLM 推理（C++ API） |

## 关键词路由表

### 模型编译 & IR

| 关键词 | 路由仓库 | 说明 |
|--------|---------|------|
| hb_compile, compile_model, 编译 | horizon_tc_ui, hbdk4_compiler | 编译入口 & 底层编译器 |
| ONNX, IR, HBIR, HBDK, .hbm, .hbo | hbdk4_compiler | 编译管线中间表示与产物 |
| march, NASH_B, NASH_P, NASH_E, 架构 | hbdk4_march | BPU 目标架构配置 |
| custom_op, 自定义算子, plugin | hbdk4_compiler | 编译期自定义算子注册 |
| overlay, link, 链接 | hbdk4_compiler | IR 层叠加与链接 |
| LLM 编译, leap, triton, numba | hbdk4_compiler | LLM/高级前端编译子系统 |

### 量化 & PTQ

| 关键词 | 路由仓库 | 说明 |
|--------|---------|------|
| PTQ, 量化, quantization, calibrate | hmct, hmct_gpu | CPU/GPU 量化工具 |
| quant_config, node_config, op_config | hmct | 量化配置层级体系 |
| 混精度, mixed precision, INT16, FP16, dual-int16 | hmct | 混精度策略与回退 |
| node_sensitivity, 敏感度分析 | hmct | hmct-debugger 敏感度工具 |
| GPU 量化, CUDA 校准, cu128 | hmct_gpu | GPU 加速量化流水线 |
| calibration, KL, max, percentile, 校准算法 | hmct, hmct_gpu | 校准方法与参数 |
| YAML 配置, compile config | horizon_tc_ui, hmct | 编译配置生成 |

### QAT 量化训练

| 关键词 | 路由仓库 | 说明 |
|--------|---------|------|
| QAT, 量化训练, quantization aware training | horizon_plugin_pytorch | 插件 API |
| FX 模式, fx_mode, FxQATReady | horizon_plugin_pytorch | FX 图捕获模式 |
| Eager 模式, QuantStub, DeQuantStub | horizon_plugin_pytorch | 手动插桩模式 |
| prepare, prepare_qat, fuse_modules | horizon_plugin_pytorch | QAT 准备与融合 API |
| QconfigSetter, qconfig, observer | horizon_plugin_pytorch | 量化配置与观测器 |
| FakeQuantize, fake_quant, calibration | horizon_plugin_pytorch | 伪量化与校准 |
| set_march, QTensor, HBIR 导出 | horizon_plugin_pytorch | 平台设置与导出 |

### 推理 & 部署

| 关键词 | 路由仓库 | 说明 |
|--------|---------|------|
| 推理, inference, 模型加载 | hbdnn, hbm_infer | C++ 运行时 & Python 远程推理 |
| hbDNNInitialize, hbDNNInference | hbdnn | C++ DNN 推理 API |
| HbmRpcSession, gRPC, 远程推理 | hbm_infer | Python gRPC 推理客户端 |
| HTensor, BPU 张量, 输入输出 | hbdnn, hbm_infer | 张量数据结构 |
| UCP, hbUCPMemFlush, cache 同步 | ucp_tutorial | UCP C++ 推理 & Cache 一致性 |
| DNN 示例, basic_samples | ucp_tutorial | DNN 推理 C++ 示例代码 |
| VP, 视觉处理, HPL, FFT | ucp_tutorial | VP/HPL 硬件加速模块 |
| DSP 算子, GPU OpenCL, custom_operator | ucp_tutorial | 自定义算子开发 |
| all-round, pipeline, 端到端 | ucp_tutorial | 端到端推理流水线 |
| stride, 步长对齐, 32字节, 64字节 | ucp_tutorial, hbdnn | 内存对齐要求 |

### 分析 & 可视化

| 关键词 | 路由仓库 | 说明 |
|--------|---------|------|
| profiler, profiling, 性能分析 | horizon_plugin_profiler | 逐层耗时分析 |
| cosine similarity, 余弦相似度 | horizon_plugin_profiler | 量化精度对比 |
| bad_case, 坏例分析 | horizon_plugin_profiler | 精度劣化定位 |
| sensitivity, 敏感度 | horizon_plugin_profiler, hmct | 节点敏感度分析 |
| Netron, 可视化, visualize, 模型图 | horizon_tc_ui | 模型结构可视化 |
| report, 报告, dashboard | horizon_tc_ui | 报告生成与展示 |

### LLM/VLM 量化 & 板端推理

| 关键词 | 路由仓库 | 说明 |
|--------|---------|------|
| LLM 量化, VLM PTQ, 大模型量化 | llm_compression | LLM/VLM PTQ 校准 & 编译流水线 |
| Float2Calibration, Calibration2Hbm | llm_compression | 校准/编译转换器 |
| BaseQModel, MODEL_REGISTRY, qconfig | llm_compression | 模型抽象接口 & 注册机制 |
| HBM, hbm 文件, embed_tokens | llm_compression, oellm_runtime | HBM 编译产物 & 板端加载 |
| OellmRuntime, oellm, LLM 推理 | oellm_runtime | 板端 VLM C++ 推理 SDK |
| InferAsync, ResponseCallBack, 流式输出 | oellm_runtime | 异步推理 & 流式回调 |
| OellmImageData, OellmPrompt, 图片推理 | oellm_runtime | VLM 多模态输入 |
| oellm_serving, HTTP 服务, VLM 服务 | oellm_runtime | HTTP 推理服务端点 |
| oellm_config.json, work_dir, backends | oellm_runtime | 板端模型配置 |
| InternVL, Qwen-VL, VLM 模型 | llm_compression, oellm_runtime | 支持的 VLM 模型族 |
| sync_kvcache_scales, KV-cache, kvcache | llm_compression, oellm_runtime | KV-cache 量化 & 管理 |
| max_batch_size, max_image_cnt | oellm_runtime | 推理批处理配置 |
| sampler_config, TopK, TopP, Temperature | oellm_runtime | 采样参数配置 |
| GetOellmInferMetric, ttft, tpot, prefill_tps | oellm_runtime | 推理性能指标 |
| mmbench, mmlu, VLM 评估 | llm_compression | VLM/LLM 精度评估数据集 |
| PipelineHbmModule, HbmRpcSession | llm_compression | 板端远程 RPC 推理评估 |
| lightcompress, llmc | llm_compression | 内嵌 LLM 压缩子工具包 |

### 工具 & 配置

| 关键词 | 路由仓库 | 说明 |
|--------|---------|------|
| hb_compile CLI, 命令行 | horizon_tc_ui | 编译命令行工具 |
| SSH, 远程连接, 板端部署 | hbm_infer, ucp_tutorial | 远程推理 & 板端运行 |
| CMake, 交叉编译, build_aarch64 | ucp_tutorial | C++ 示例构建 |
| AI benchmark, 性能基准 | ucp_tutorial | BPU 性能测试 |

## 无本地代码的仓库

以下仓库在 oe-mcp 中有索引，但本地 SDK 包中未包含代码：

| 仓库 | 说明 |
|------|------|
| `oe_code_chunk_leap_llm` | LLM 推理引擎（独立发布） |
