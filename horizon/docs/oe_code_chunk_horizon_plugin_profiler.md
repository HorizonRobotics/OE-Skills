# oe_code_chunk_horizon_plugin_profiler

## 仓库概述

- **Name**: `horizon_plugin_profiler` (v3.3.4)
- **Package**: `horizon-plugin-profiler` (pip), depends on `horizon_plugin_pytorch`
- **Purpose**: PyTorch model profiling & quantization debug toolkit for Horizon Robotics BPU (Brain Processing Unit)
- **Role in toolchain**: Provides layer-by-layer comparison, sensitivity analysis, bad-case finding, and HTML reporting across the float -> fused -> calibration -> QAT -> quantized -> HBIR conversion pipeline. Diagnoses quantization accuracy loss and identifies sensitive operators.
- **Author**: Horizon DeepLearning Platform
- **Key deps**: numpy, tabulate, plotly, Jinja2, termcolor, tqdm, matplotlib, scipy; optional: `hbdk4` (compiler), `hbm_infer` (remote inference)

## 目录结构

```
horizon_plugin_profiler-3.3.4-py3/
  CLAUDE.md                                # Project guidance for Claude Code
  horizon_plugin_profiler-3.3.4.dist-info/ # Wheel metadata (METADATA, RECORD, WHEEL)
  horizon_plugin_profiler/
    __init__.py                            # Public API exports (try/except per symbol)
    version.py                             # __version__ = "3.3.4"
    _similarity.py                         # Internal similarity computation engine
    model_profiler.py                      # v1 functional API: model_profiler()
    model_profilerv2.py                    # v2 class API: ModelProfiler, QuantAnalysis
    hbir_model_profiler.py                 # HbirModelProfiler for HBIR bytecode models
    consistency_profiler.py               # ConsistencyAnalyzer for cross-stage consistency
    featuremap_similarity.py              # Per-layer featuremap similarity comparison
    compare_weights.py                     # Weight comparison between float/qat/quantized
    check_qconfig.py                       # Validate qconfig on QAT models
    check_unfused_operations.py            # Detect unfused (un-fusable) modules
    check_deploy_device.py                # Check BPU vs CPU deployment for hybrid models
    get_raw_features.py                    # Hook-based raw feature extraction
    get_module_called_count.py             # Count leaf module invocation frequency
    profile_featuremap.py                  # Statistical profiling (min/max/mean/var/scale)
    profile_module_constraints.py          # Operator constraint checking per BPU march
    find_bad_case.py                       # Automated bad-case input discovery
    show_cuda_memory_consumption.py        # CUDA memory profiling per layer
    inference.py                           # HbmServerSession, InferenceEngine (remote HBM)
    sensitivity/
      model.py                             # Sensitivity analysis (per-layer quant impact)
      single_bc_model.py                   # Single-bitcode model error computation
      tracer.py                            # CalibOpTracer, FloatOpTracer, FloatOpLoader
    bc_editor/
      bc_editor.py                         # QatBcEditor: HBIR .bc file manipulation
      config_template.json                 # BC editor config template
    profiler_templates/                    # Jinja2 HTML templates + ECharts for reports
    utils/
      model_helper.py                      # HookAndTorchFunctionHelper, _as_tuple, ModelStage
      profiler_tracer.py                   # OpInfoRecorder, OpInfoRecorderWithSinglebc
      op_running_info.py                   # OpRunningInfo, OpRunningInfoManager
      entities.py                          # Metric, BadCase, ComparePerLayerTable, SensitivityTable
      location_info.py                     # TorchLocationInfo, LocationManager
      cal_ops.py                           # FLOPs calculation
      plot_statistics.py                   # PlotStatistic (bar3d, histograms)
      logger.py                            # Logging setup, format_msg
      hbdk4_optional.py                   # HbirModule fallback when hbdk4 unavailable
      typeguard.py                         # Vendored typeguard 2.13.3 with QTensor patches
      version_helper.py                    # Torch/numpy version checking
      deprecate.py                         # Deprecation warning utilities
```

## 关键模块与 API

### v1 Functional API (top-level imports)
- `model_profiler(model1, model2, inputs, mode, out_dir, kwargs_dict)` - One-shot profiling, generates `profiler.html`. mode: `"FvsQ"` (float vs qat) or `"QvsQ"` (qat vs quantized)
- `featuremap_similarity(model1, model2, inputs, similarity_func, threshold, devices, out_dir)` - Per-layer similarity (Cosine/MSE/L1/KL/SQNR or custom Callable)
- `compare_weights(float_model, qat_model, similarity_func, ...)` - Weight diff between stages
- `check_qconfig(model, inputs, ...)` - Validate quantization config on QAT model
- `check_unfused_operations(model, inputs, ...)` - Find modules not properly fused
- `check_deploy_device(model, ...)` - Check BPU/CPU deployment for hybrid quantized model
- `get_raw_features(model, inputs, prefixes, types, ...)` - Extract raw features via hooks
- `profile_featuremap(featuremap, with_tensorboard, ...)` - Statistical profiling (min/max/mean/var)
- `get_module_called_count(model, inputs, ...)` - Count module invocation frequency
- `show_cuda_memory_consumption(model, inputs, device, ...)` - CUDA memory analysis per layer

### v2 Class API
- `ModelProfiler(model, out_dir)` - Context manager for tracing; use `with ModelProfiler(net, path) as p: net(data)` then `p.get_info_manager().table()`
- `QuantAnalysis(baseline, analysis, type, device_ids, post_process, out_dir)` - Full quantization debug workflow:
  - `.auto_find_bad_case(dataloader, num_steps, topk)` -> find worst inputs
  - `.run()` -> trace both models with bad-case input
  - `.compare_per_layer(prefixes, types)` -> layer-by-layer diff, generates `profiler.html` + advisor
  - `.sensitivity(metric, prefixes, types, use_sensitivity_v2)` -> identify quantization-sensitive ops
  - `.tune_bad_case(outputs_config, skip_prefix)` -> iteratively set int16 to fix bad case
  - `.plot_opinfo()`, `.plot_opinfo_bar3d()` -> visualize op statistics
- `HbirModelProfiler(model, work_dir)` - Profiler for HBIR bytecode models via callback
- `ConsistencyAnalyzer(models, example_inputs, infer_func, mode, metric)` - Cross-stage consistency:
  - mode: `"pre_export"`, `"export"`, `"convert"`
  - `.auto_find_bad_case(data_generator)` -> `.compare_per_layer()` -> `.sensitivity()`
- `HbmServerSession(local_hbm_path, host, ...)` - Remote HBM inference session
- `InferenceEngine` - Remote inference engine wrapper

### Internal Key Classes
- `OpInfoRecorder` (utils/profiler_tracer.py) - Hook + `__torch_function__` tracing infrastructure
- `HookAndTorchFunctionHelper` (utils/model_helper.py) - Base class for hook registration
- `OpRunningInfo` / `OpRunningInfoManager` (utils/op_running_info.py) - Per-op data containers
- `TorchLocationInfo` (utils/location_info.py) - Source location tracking for operators
- `Sensitivity` (sensitivity/model.py) - Per-layer sensitivity analysis engine
- `QatBcEditor` (bc_editor/bc_editor.py) - HBIR bytecode post-quantization editing

## 常用查询映射

| 用户意图 | 推荐搜索关键词 | 说明 |
|---------|--------------|------|
| 模型量化精度分析全流程 | `QuantAnalysis`, `auto_find_bad_case`, `compare_per_layer`, `sensitivity` | v2 完整工作流：找 bad case -> run -> 逐层对比 -> 敏感度 |
| 逐层 featuremap 相似度 | `featuremap_similarity`, `Cosine`, `similarity_func` | 支持 Cosine/MSE/L1/KL/SQNR，输出 similarity.txt + similarity.html |
| 一键式模型对比报告 | `model_profiler`, `profiler.html`, `FvsQ`, `QvsQ` | v1 函数式 API，一次生成包含所有对比的 HTML 报告 |
| 查找量化 bad case 输入 | `find_bad_case`, `BadCaseReport`, `auto_find_bad_case`, `topk` | 遍历 dataloader 找最大误差输入，支持 topk |
| 量化敏感度分析（找敏感层） | `sensitivity`, `SensitivityTable`, `sensitive_ops`, `use_sensitivity_v2` | 逐层关闭 fake quant 测影响，输出 sensitive_ops.txt/pt |
| 设置 int16 混精度调优 | `tune_bad_case`, `outputs_config`, `max_tuned_stubs` | 基于敏感度结果迭代设 int16 直到误差达标 |
| 权重对比（float vs quantized） | `compare_weights`, `weight_comparison.txt` | 按层比较权重 cosine/atol |
| 检查 qconfig 配置 | `check_qconfig`, `unusual_map`, `out_info_map` | 验证 QAT 模型量化配置正确性 |
| 检查未融合算子 | `check_unfused_operations`, `module_to_fuse` | 发现未正确 fuse 的模块 |
| 检查混合部署设备 | `check_deploy_device`, `BPU`, `CPU`, `hybrid` | 查看混合精度模型各层部署在 BPU 还是 CPU |
| 特征统计（min/max/mean/var） | `profile_featuremap`, `get_raw_features`, `PlotStatistic` | 提取并统计每层特征分布 |
| 模块调用次数统计 | `get_module_called_count`, `called_count` | 统计每个 leaf module 被调用次数 |
| CUDA 显存分析 | `show_cuda_memory_consumption`, `memory` | 逐层 CUDA 显存消耗分析，输出 HTML |
| HBIR 模型 profiling | `HbirModelProfiler`, `HbirModuleWrapper`, `hbdk4` | HBIR bytecode 模型的 tracing 和 profiling |
| 量化一致性分析 | `ConsistencyAnalyzer`, `pre_export`, `export`, `convert` | 对比 pre_export/export/convert 各阶段一致性 |
| 远程 HBM 推理 | `HbmServerSession`, `InferenceEngine`, `hbm_infer` | 连接远程 HBM 服务器进行推理 |
| HBIR 字节码编辑 | `QatBcEditor`, `remove_fake_quant`, `bc_editor` | 加载 .bc 文件，按 JSON 配置移除 fake quant 等 |
| 模型阶段判断 | `get_model_stage`, `ModelStage`, `FLOAT`, `QAT`, `quantized` | 判断模型处于 float/fused/calibration/QAT/quantized 哪个阶段 |
| 算子 FLOPs 计算 | `cal_flops`, `op_flops_mapping`, `cal_ops` | 计算每个算子的 FLOPs |
| 数据分布可视化 | `plot_opinfo`, `plot_opinfo_bar3d`, `plot_single_op_bar3d` | 3D 柱状图、直方图、箱线图可视化算子数据 |
| QTensor 反量化处理 | `QTensor`, `dequantize`, `q_scale`, `q_per_channel_axis` | 量化 tensor 的特殊处理和数值提取 |
| fake quant 状态管理 | `FakeQuantState`, `set_fake_quantize`, `VALIDATION` | 控制 fake quantize 开关状态 |
| hook 追踪基础设施 | `HookAndTorchFunctionHelper`, `OpInfoRecorder`, `TracerTensor` | 基于 forward hook + `__torch_function__` 的 tracing |
| 算子位置追踪 | `TorchLocationInfo`, `LocationManager`, `mod_name` | 追踪每个算子的 Python 源码调用位置 |
| 分布式 profiling | `dist.is_initialized`, `world_size`, `rank`, `all_gather_object` | 多 GPU 分布式场景下的 profiling 支持 |
| HTML 报告生成 | `profiler_template`, `Jinja2`, `echarts`, `badcase_report_template` | Jinja2 + ECharts 生成交互式 HTML 报告 |
| 类型检查（vendored typeguard） | `typeguard`, `typechecked`, `QTensor` 适配 | 基于 typeguard 2.13.3 vendored 副本的运行时类型检查 |
| 确定性推理设置 | `cudnn.deterministic`, `cudnn.benchmark` | QuantAnalysis 初始化时设置确保可复现 |
| 输入归一化处理 | `_as_tuple`, `apply_to_collection`, `tree_flatten` | 将任意结构输入归一化为平铺 tuple |
| SegmentLUT 特殊处理 | `SegmentLUT`, `QuantizedQATSegmentLUT`, `is_leaf_lut` | LUT（查找表）算子在敏感度分析中的特殊逻辑 |

## 规则与约定

- **包是 wheel 解压目录**，非源码仓库，无构建系统/测试/lint 配置
- **所有公开 API 使用 `@typechecked` 装饰器**（来自 vendored typeguard 2.13.3），不要升级或替换此 vendored 副本
- **导入容错**：`__init__.py` 中每个符号在独立 `try/except ImportError` 中导入，失败时替换为桩函数
- **模型阶段检测**：`get_model_stage()` 通过检查 `QuantStub`/`FakeQuantize` 等模块类型判断模型所处阶段，许多 API 据此分支
- **QTensor 处理**：数值对比前需 `.dequantize()`；`_as_tuple` / `apply_to_collection` 用于归一化嵌套输入
- **`set_fake_quantize(model, FakeQuantState.VALIDATION)`**：profiling 前务必设置正确的 fake quant 状态
- **`pt_lut` mode 已弃用**，等价于 `pre_export`，代码中有 deprecation warning
- **确定性**：`QuantAnalysis.__init__` 设置 `cudnn.deterministic=True` 和 `cudnn.benchmark=False`
- **报告输出**：默认保存在 `./horizon_quant_debug`、`./horizon_quant_analysis`、`./horizon_consistency_analysis` 等目录
- **可选依赖降级**：缺少 `hbdk4` 时 `HbirModule` 退化为空类；缺少 `hbm_infer` 时远程推理不可用
- **v1 vs v2**：`model_profiler()` 是一次性函数式调用；`QuantAnalysis` 是完整的分步工作流类，推荐使用 v2
- **分布式支持**：`QuantAnalysis` 支持 `torch.distributed`，在 rank 0 上执行 dump/plot，多 rank 用 `all_gather_object` 聚合
