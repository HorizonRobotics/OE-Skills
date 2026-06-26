# oe_code_chunk_horizon_plugin_pytorch

## 仓库概述
- **Name**: `horizon_plugin_pytorch` v3.3.4+cu128.torch2100
- **Purpose**: 面向地平线 BPU（Journey 6 系列）的量化感知训练 (QAT) 与模型导出插件
- **Role**: 在 PyTorch 2.10.0 + CUDA 12.8 之上扩展 BPU 专有量化 dtype、算子实现及 hbdk3/hbdk4 编译导出流水线
- **Type**: 已安装的 Python wheel（非源码仓库），含 native extension `libhorizon_ops.so`
- **Python**: cp39 (Python ≥3.9)
- **核心依赖**: PyTorch 2.10.0（严格版本校验）；hbdk4（可选，导出路径需要）；hbdk3（回退）

## 目录结构
```
horizon_plugin_pytorch/
├── __init__.py            # 入口：import extension, jit, nn, quantization
├── dtype.py               # QuantDType: qint4/qint8/qint16, qinfo()
├── qtensor.py             # QTensor: torch.Tensor 子类, __torch_function__/dispatch
├── march.py               # March 枚举 (BERNOULLI/BAYES/NASH系列), set_march/get_march
├── functional.py          # QTensor 分发算子 (NMS, 色彩空间, BEV 等)
├── jit.py                 # JIT script 辅助, @with_march 装饰器
├── qat_mode.py            # QAT 模式/一致性策略
├── torch_patch.py         # PyTorch 猴子补丁
├── nn/                    # BPU 兼容算子 nn.Module 封装 (80+ 算子)
│   ├── qat/               # QAT 封装：带 FakeQuantize observer 的算子
│   ├── quantized/         # 导出时量化实现 + functional 风格算子
│   └── intrinsic/         # 融合模块 (ConvBn2d, ConvTranspose3d 融合)
├── quantization/          # 量化流水线核心
│   ├── prepare.py         # prepare() 统一入口 (EAGER/SYMBOLIC/JIT)
│   ├── quantize.py        # prepare_qat (eager 模式)
│   ├── quantize_fx.py     # prepare_qat_fx + fuse_fx (FX 图模式，推荐)
│   ├── qconfig.py         # QConfig 工厂函数
│   ├── qconfig_setter/    # 基于模板的量化规则系统 (QconfigSetter)
│   ├── observer.py        # MinMax/MovingAvg/PerChannel/Clip/FixedScale Observer
│   ├── fake_quantize.py   # FakeQuantize, set_fake_quantize, FakeQuantState
│   ├── stubs.py           # QuantStub / DeQuantStub
│   ├── auto_calibration.py# auto_calibrate 自动校准
│   ├── fx/                # FX 图重写: fusion_patterns, split_compilable_model
│   ├── hbdk3/             # hbdk3 导出: export_hbir, compile_model, check_model
│   └── hbdk4/             # hbdk4 导出: export_hbir, checker, registry
├── fx/                    # FX tracing 辅助, JIT scheme, HTML diff/可视化
├── prune/                 # 结构化剪枝: pruner, mask_generator, permutation
├── utils/                 # auto_cast, check_model, onnx_helper, quant_profiler 等
└── _torchvision_wrapper/  # torchvision 算子薄封装
```

## 关键模块与 API

### 平台与类型
- `set_march(march: str)` — 设置目标 BPU 平台（如 `"nash-e"`, `"bayes"`）
- `get_march() -> str` — 获取当前 march
- `qinfo(dtype) -> (min, max)` — 查询量化 dtype 数值范围
- `QuantDType`: `qint4`, `qint8`, `qint16`

### QAT 主流水线
- `prepare(model, example_inputs, qconfig_setter, ...)` — 统一 QAT 准备（支持 EAGER/SYMBOLIC/JIT）
- `prepare_qat(model, qconfig)` — eager 模式 QAT 准备
- `prepare_qat_fx(model, example_inputs, qconfig_setter, fuse_mode, ...)` — FX 图模式 QAT（推荐）
- `fuse_fx(graph_module, fuse_mode=FuseMode.BNAddReLU)` — FX 模块融合
- `PrepareMethod` 枚举: `EAGER`, `SYMBOLIC`, `JIT`, `JIT_STRIP`
- `FuseMode` 枚举: `BNAddReLU`, `NoFuse`

### QConfig & Observer
- `QConfig` — 量化配置（per-tensor / per-channel observer + fake-quant）
- `get_default_qat_qconfig()`, `per_channel_qat_8bit_qconfig()`
- `QconfigSetter` — 基于模板的规则应用（`get_common_templates()`, `get_compat_templates()`）
- `MinMaxObserver`, `MovingAverageMinMaxObserver`, `PerChannelMinMaxObserver`, `ClipObserver`, `FixedScaleObserver`
- `FakeQuantize`, `PACTFakeQuantize`, `DynamicFakeQuantize`, `FakeCast`（FP16 fake cast）

### Stub & 校准
- `QuantStub(scale, zero_point, qconfig)` — 量化入口 stub
- `DeQuantStub()` — 反量化 stub
- `auto_calibrate(model, data_loader)` — 自动校准
- `set_fake_quantize(model, state: FakeQuantState)` — 切换量化状态
- `load_calib_state_dict(model, state_dict)` — 加载校准参数

### 导出 (hbdk3/hbdk4)
- `export_hbir(model, inputs, output_dir)` — 导出 HBIR 中间表示
- `compile_model(model, ...)` — 编译为 BPU 可执行模型
- `check_model(model, ...)` — 模型兼容性检查
- `perf_model(model, ...)` — 性能分析
- `visualize_model(model, ...)` — 可视化模型结构

### NN 算子 (80+)
- 基础: `Interpolate`, `GridSample`, `Softmax`, `LayerNorm`, `GroupNorm`, `RMSNorm`
- 注意力: `MultiheadAttention`, `MultiScaleDeformableAttention`, `TransformerEncoder/Decoder`
- 检测: `DetectionPostProcess`, `AnchorGenerator`, `MultiScaleRoIAlign`, `RcnnPostProcess`
- BEV: `BevPoolV2`
- RNN: `LSTM`, `LSTMCell`, `GRU`, `GRUCell`

## 常用查询映射

| 用户意图 | 推荐搜索关键词 | 说明 |
|---------|--------------|------|
| QAT 训练完整流程 | `prepare_qat_fx`, `fuse_fx`, `set_march` | FX 模式推荐路径：fuse → prepare → train → export |
| eager mode QAT | `prepare_qat`, `PrepareMethod.EAGER` | 不经过 FX tracing 的传统 eager 模式 |
| FX mode QAT | `prepare_qat_fx`, `fuse_fx`, `quantize_fx` | 基于 torch.fx 的图模式（推荐） |
| QuantStub 使用 | `QuantStub`, `DeQuantStub`, `stubs.py` | 模型输入/输出量化标注 |
| 量化配置 | `QConfig`, `get_default_qat_qconfig`, `per_channel_qat_8bit_qconfig` | per-tensor / per-channel 配置 |
| QconfigSetter 模板 | `QconfigSetter`, `get_common_templates`, `canonicalize_rules` | 基于模板的量化规则系统 |
| calibration 校准 | `auto_calibrate`, `FakeQuantState.CALIBRATION`, `load_calib_state_dict` | 校准数据采集与加载 |
| Observer 观察者 | `MinMaxObserver`, `MovingAverageMinMaxObserver`, `PerChannelMinMaxObserver` | 统计 min/max 的观察者 |
| FakeQuantize 伪量化 | `FakeQuantize`, `PACTFakeQuantize`, `_LearnableFakeQuantize`, `AdaRound` | 各种伪量化实现 |
| FP16 fake cast | `FakeCast`, `default_fp16_fake_cast` | FP16 精度模拟 |
| 模型导出 HBIR | `export_hbir`, `hbdk3`, `hbdk4` | 导出为 BPU 中间表示 |
| 编译 BPU 模型 | `compile_model`, `check_model`, `perf_model` | 编译/检查/性能分析 |
| 设置目标平台 | `set_march`, `March.NASH_E`, `March.BAYES` | 目标 BPU 平台枚举 |
| 量化 dtype | `qint8`, `qint16`, `qint4`, `qinfo`, `QuantDType` | 量化数据类型与范围查询 |
| QTensor 量化张量 | `QTensor`, `q_scale`, `q_zero_point`, `dequantize` | 携带量化元数据的 Tensor 子类 |
| 模块融合 | `fuse_modules`, `fuse_known_modules`, `FuseMode`, `ConvBn2d` | Conv+BN 等算子融合 |
| FX 图分割 | `split_compilable_model` | 将模型切分为可编译/不可编译子图 |
| 结构化剪枝 | `pruner`, `mask_generator`, `permutation` | 结构化剪枝与敏感度分析 |
| ONNX 导出 | `onnx_helper`, `_register_onnx_ops` | ONNX symbolic 注册与辅助 |
| Interpolate 插值 | `Interpolate`, `nn.interpolate` | BPU 兼容插值算子 |
| GridSample 网格采样 | `GridSample`, `grid_sample` | BPU 兼容 grid_sample |
| Transformer 算子 | `TransformerEncoder`, `MultiheadAttention`, `MultiScaleDeformableAttention` | 注意力机制相关 |
| 检测后处理 | `DetectionPostProcess`, `AnchorGenerator`, `RcnnPostProcess` | 目标检测后处理算子 |
| BEV 算子 | `BevPoolV2`, `bev_pool_v2` | BEV 感知专用算子 |
| NMS 非极大值抑制 | `functional.py`, `batched_nms` | QTensor 分发的 NMS 实现 |
| 猴子补丁 | `replace_torch_op`, `fx_helper`, `torch_patch` | import 时自动替换 torch 原生算子 |
| JIT script | `jit.py`, `@with_march`, `script_qat_mod` | JIT scripting 辅助 |
| QAT 状态切换 | `set_fake_quantize`, `FakeQuantState`, `freeze_qat_module` | 校准/QAT/验证状态管理 |
| 权重重建 | `weight_reconstruction` | 量化权重重建 |
| 自动混合精度 | `auto_cast`, `autocast` | autocast 感知算子 |
| 日志配置 | `set_logger`, `logger` | 插件日志系统 |

## 规则与约定

- **import 顺序**: `import horizon_plugin_pytorch` 会自动触发猴子补丁，替换 `nn.ReLU`, `nn.PReLU`, `nn.AdaptiveAvgPool1d/2d`, `nn.LogSoftmax`, `nn.Threshold`
- **march 必须**: 使用任何 BPU 算子前必须调用 `set_march()`；`@with_march` 装饰器会自动注入 march 参数
- **QTensor 分发**: 新算子需在 `nn/`(float) → `nn/qat/`(QAT) → `nn/quantized/`(量化) 三层实现，并在 `qtensor.py`/`functional.py` 注册 dispatch 分支
- **版本严格校验**: PyTorch 必须精确 2.10.0，CUDA 必须匹配 12.8（HIP/ROCm 跳过检查）
- **Native 库**: `libhorizon_ops.so` 在 import 时通过 `torch.ops.load_library` 加载
- **hbdk 可选**: hbdk4/hbdk3 缺失不阻止 import，仅导出时按需加载
- **Qconfig 模板组合**: `QconfigSetter` 叠加多个模板，新增策略应添加新模板而非修改已有
- **FX 推荐路径**: `fuse_fx()` → `prepare_qat_fx()` → 训练 → `export_hbir()`，eager 模式仅用于简单场景
- **无构建脚本**: 此为已安装 wheel，无法从此处重新构建或安装
