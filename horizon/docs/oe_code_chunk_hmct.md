# oe_code_chunk_hmct

## 仓库概述

- **名称**: hmct (Horizon Model Convert Tool) v2.8.3
- **Python 包**: `hmct-2.8.3-cp310`，已安装 pip 包（非 git 仓库）
- **用途**: 将 ONNX/Caffe 浮点模型转换为量化模型，部署到 Horizon BPU (AI 加速器) 芯片
- **角色**: J6 Open Explorer 工具链核心组件，位于 `package/host/ai_toolchain/code/` 下
- **关联包**: `horizon_nn`（轻量 wrapper，仅 `__init__.py`）
- **原生扩展**: 包含 `pyquant.so`、`pyquantizer.so`、`onnxruntime_pybind11_state.so`、`horizon_operators.so` 等 C++ .so 文件
- **支持架构**: nash/nash-b/nash-e/nash-m/nash-h/nash-p/bayes/bayes-e/bernoulli2/bernoulli/expt
- **量化后端**: hbdk4（v2.x 默认）、expt、hbdk3（v1.x 旧版）、trt

## 目录结构

```
hmct-2.8.3-cp310/
  CLAUDE.md                          # 仓库级说明文件 (含完整架构文档)
  hmct/                              # 主包 (api.py, version.py, __init__.py)
    builder/                         # 模型构建入口: build_onnx(), check_onnx(), ModelBuilder
    ir/                              # 中间表示 (IR): OnnxModel/Graph/Node/Variable/CalibrationNode
      horizon_onnx/                  #   C++ 扩展: 自定义 ONNX 算子、shape 推理、global_attributes
    common/                          # 公共模块: data/, misc/, modifier/, parser/, quant/
    converter/                       # 转换流水线
      parser/                        #   模型解析 (onnx_parser, caffe_parser, torch_parser)
      preparer/                      #   模型准备 (验证、shape 设置、opset 转换)
      optimizer/                     #   图优化 pass 系统
        adapt/                       #     40+ 算子适配器 | fuse/ — 算子融合
        eliminate/                   #     冗余消除 | split/ — 复杂算子分解
        replace/                     #     算子替换 | move/ — 节点位置调整
        insert/                      #     必要节点插入 | qat/ — QAT 模型适配
    quantizer/                       # 量化系统
      calibrater/                    #   校准: activation/, weight/, post/, search_methods/
      backend/                       #   后端量化: hbdk4/, expt/, hbdk3/, trt/, lut/
      debugger/                      #   量化调试器 (敏感度/张量/累积误差分析)
    executor/                        # ONNX Runtime 推理执行器 (ORTExecutor)
    custom/                          # 自定义算子注册 | plugin/ — BEVPoolingV2/DeformConv2D
    reporter/                        # 报告: 相似度计算、量化类型统计、模型信息
    skills/                          # reference/ (一键构建) + j6-hmct-cosine-similarity-tuning/
    tools/                           # CLI: simplify, profiler, convert, debug, compatibility, compare_*
    utility/                         # 工具函数 (random_data, tempdir)
  horizon_nn/                        # 轻量辅助包 | hmct-2.8.3.dist-info/ — pip 元数据
```

## 关键模块与 API

### 顶层 API (`hmct/api.py` — `__all__`)
| 导出名 | 说明 |
|--------|------|
| `build_model` | 完整量化构建 (解析→准备→优化→校准→量化→编译) |
| `check_model` | 快速验证 (使用随机数据, 跳过真实校准) |
| `load_model` | 加载 ONNX 模型文件 |
| `export_onnx` | 从 PyTorch 模型导出 ONNX |
| `infer_shapes` | 修改模型并执行 shape inference |
| `register_pass` | 注册自定义优化 pass |
| `PredicateBasedPass` | 自定义 pass 基类 |
| `ORTExecutor` | ONNX Runtime 推理执行器 |
| `version` | 版本号字符串 |

### ModelBuilder 构造参数 (`builder/model_builder.py`)
```python
ModelBuilder(onnx_model, march, check_mode=False, save_model=False, name_prefix="",
    output_nodes=None, debug_mode=None, optimization=None,
    skip_step=None,           # 跳过阶段: skip_optimizer/skip_calibrater/skip_quantizer/skip_compiler
    cali_dict=None,           # 校准数据 {"input_name": [np.array(...)]}
    node_dict=None, hbdk_dict=None, input_dict=None,
    user_quant_config=None)   # quant_config.json 路径或 dict
```

### QuantConfig 核心结构 (`common/quant/quant_config.py`)
- `model_config` — 全局量化设置: `all_node_type`, `model_output_type`, `activation`, `weight`, `search`
- `op_config` — 按算子类型配置量化: `{"Conv": {"qtype": "int16"}}`
- `node_config` — 按节点名配置量化: `{"node_name": {"qtype": "int16", "input0": "int16"}}`
- `subgraph_config` — 按子图配置量化: `{"subgraph": {"inputs": [...], "outputs": [...], "qtype": "int16"}}`
- 支持量化类型: `int4`, `int8`, `int16`, `float16`, `float32`, `mxint16`, `mxint8`, `mxfp8`, `mxfp4`, `mxint4`, `nvfp4`, `dual-int16`, `int16-ec`

### 优化 Pass 系统 (`converter/optimizer/`)
- 基类: `PassBase` → `FullGraphBasedPass` / `PredicateBasedPass`
- `PredicateBasedPass` 需实现: `match_pattern(OnnxNode) -> bool` + `apply_transform() -> bool`
- `run_passes(model, passes, iterate=True)` — 不动点迭代执行
- 执行顺序: ConstantFolding → AdaptNode → AdaptQatModel → FuseNode → EliminateNode → MoveNode → SplitNode → ReplaceNode → InsertNode
- 用户 pass: `@register_pass("start"|"end")` 装饰器

### 校准系统 (`quantizer/calibrater/`)
- 激活校准方法: max, kl, min-max, percentile, per-channel, mix, equalization
- 权重校准: max, bias_correction, compensation
- 后校准: pow_of_two, refine_threshold, adjust_conv_quant_params
- 搜索: modelwise_search (全局最优), weightwise_search (逐层最优)

### 调试器 (`quantizer/debugger/debug_api.py`)
- `get_sensitivity_of_nodes()` — 节点敏感度分析
- `sensitivity_analysis()` — 敏感度分析 (带数据分布)
- `tensor_analysis()` — 张量分析
- `AccumulationError` — 累积误差计算
- `ParameterDistribution` — 参数分布统计

### CLI 入口
`hmct-debugger runall|get_sensitivity_of_nodes|sensitivity_analysis|tensor_analysis`
`python -m hmct.tools.simplify | profiler | convert | debug | compatibility`

## 常用查询映射

| 用户意图 | 推荐搜索关键词 | 说明 |
|---------|--------------|------|
| 模型量化主入口 | `build_model`, `build_onnx`, `ModelBuilder.build` | 完整量化构建流程 |
| 快速验证模型 | `check_model`, `check_onnx`, `check_mode` | 随机数据快速验证 |
| 量化配置 JSON | `quant_config`, `QuantConfig`, `node_config`, `op_config` | 混精度/量化参数配置 |
| 校准数据 | `calibration`, `cali_data`, `cali_dict`, `Dataset` | 校准数据加载与使用 |
| 激活校准方法 | `activation_calibration`, `max_calibrater`, `kl_calibrater` | max/KL/percentile 等方法 |
| 权重量化校准 | `weight_calibration`, `bias_correction`, `weight_max` | 权重校准与偏置修正 |
| 后校准处理 | `post_calibration`, `pow_of_two`, `refine_threshold` | 阈值精调与缩放处理 |
| 搜索最优参数 | `modelwise_search`, `weightwise_search`, `layerwise_search` | 全局/逐层搜索最优校准参数 |
| 混精度量化 | `mixed precision`, `node_config`, `qtype`, `int16`, `dual-int16` | 按节点/op 设置不同量化精度 |
| 图优化 pass | `optimize`, `run_passes`, `PredicateBasedPass`, `register_pass` | 自定义/内置优化 pass |
| 算子适配 | `adapt_`, `AdaptNode`, `adapt_conv_like_ops` | ONNX→Horizon 算子适配 |
| 算子融合 | `fuse_`, `FuseNode`, `fuse_bn_into_prev_conv` | BN 融合、连续算子融合 |
| 冗余消除 | `eliminate_`, `EliminateNode`, `eliminate_unused` | 消除冗余节点/变量 |
| 算子替换 | `replace_`, `ReplaceNode`, `replace_gemm_with_conv` | Gemm→Conv、Flatten→Reshape |
| 算子分解 | `split_`, `SplitNode`, `split_bn`, `split_lstm` | BN/InstanceNorm/GRU 分解 |
| 节点敏感度 | `node_sensitivity`, `get_sensitivity_of_nodes`, `hmct-debugger` | 量化敏感度分析 |
| 精度调优 | `cosine_similarity_tuning`, `precision_tuning`, `sensitivity_analysis` | 量化精度调优工作流 |
| 累积误差 | `accumulation_error`, `AccumulationError` | 量化累积误差分析 |
| 张量分析 | `tensor_analysis` | 张量数据分布分析 |
| BPU 架构 | `march`, `nash-e`, `nash-b`, `bayes`, `bernoulli` | 目标芯片架构选择 |
| 量化后端选择 | `backend`, `hbdk4`, `expt`, `hbdk3`, `trt` | 量化后端自动选择 |
| QDQ 替换 | `replace_calibration_with_qdq`, `QDQ`, `quantize_dequantize` | 校准节点→QDQ 量化对 |
| QAT 模型 | `adapt_qat_model`, `qat`, `HzQuantize`, `QuantizeLinear` | QAT 量化感知训练模型处理 |
| 自定义算子 | `op_register`, `op_implement_register`, `op_shape_infer_register` | 注册自定义 ONNX 算子 |
| ONNX 模型加载 | `load_model`, `OnnxModel`, `parse` | 加载/解析 ONNX 模型 |
| shape 推理 | `infer_shapes`, `shape_inference`, `shape_modifier` | 模型 shape 推导 |
| 模型简化 | `simplify`, `hmct.tools.simplify` | 独立 ONNX 图优化器 |
| FP16 转换 | `convert_to`, `fp16`, `float16`, `convert` | FP32→FP16 模型转换 |
| 模型信息打印 | `print_model_info`, `hmct-info`, `calculate_quant_type` | 打印量化信息/算子约束 |
| 量化类型 | `qtype`, `int8`, `int16`, `float16`, `dual-int16`, `int16-ec` | 各精度类型含义 |
| global_attributes | `global_attributes`, `init_global_configs`, `quantizer` | 全局配置单例 |
| ONNX Runtime 推理 | `ORTExecutor`, `onnxruntime`, `session` | 校准/调试用推理引擎 |
| Caffe 模型转换 | `caffe_parser`, `parse_caffe`, `caffe_to_onnx` | Caffe→ONNX 转换 |
| 中间模型保存 | `save_model`, `original_float_model`, `calibrated_model` | 各阶段中间产物 |
| 跳过流水线阶段 | `skip_step`, `skip_optimizer`, `skip_calibrater` | 跳过特定构建阶段 |
| 校准数据目录 | `cali_data_dir`, `calibration_data`, `Dataset` | 校准数据目录格式 |
| 算子约束列表 | `onnx_operator_constraints`, `onnx_operator_support` | 各架构算子支持列表 (.mdx) |
| LUT 量化 | `lut`, `fuse_to_b30_lut`, `quantize_fplut` | Look-Up-Table 非线性函数量化 |
| subgraph 配置 | `subgraph_config`, `extract_submodel` | 子图级量化配置 |
| 模型兼容性 | `compatibility`, `handle_user_quant_config_legacy` | 旧版模型/配置兼容 |

## 规则与约定

- **语言约定**: 所有 docstring 和代码注释使用简体中文
- **链式调用**: `OnnxModel` 方法支持链式: `model.infer_shapes().check_validity()`
- **全局单例**: `global_attributes`（`ir/horizon_onnx/`）存储 march、量化模式等，通过 `ModelBuilder.init_global_configs()` 初始化
- **量化配置优先级**: `node_config` > `op_config` > `model_config.all_node_type` > 默认值 (int8)
- **skip_step 机制**: 跳过某阶段会同时跳过所有后续阶段 (optimizer → calibrater → quantizer → compiler)
- **check_mode**: `True` 时使用随机数据快速验证，无需真实校准数据
- **不动点迭代**: `run_passes()` 反复执行 pass 直到图不再变化
- **量化类型约定**: `dual-int16` 和 `int16-ec` 仅支持 Conv/MatMul/Gemm/ConvTranspose 四类算子
- **num_bin 约束**: 校准 bin 数量最小值 129，`max_num_bin` 最小值 258
- **max_percentile 范围**: 必须在 [0.5, 1.0] 范围内
- **构建产物命名**: `*_original_float_model.onnx` → `*_optimized_float_model.onnx` → `*_calibrated_model.onnx` → `*_quantized_model.onnx`
- **后端自动选择**: march 为 nash 系列 → hbdk4; march="expt" → expt; v1.x → hbdk3
- **常见陷阱**: 未提供 `input_dict` 时模型输入 shape 可能无法自动推断；`cali_dict` 需为 `{"input_name": [np.array(...)]}` 格式
