# oe_code_chunk_hmct_gpu

## 仓库概述

- **名称**: hmct-gpu (Horizon Model Convert Tool — GPU 加速版) v2.8.3+cu128
- **Python 包**: `hmct_gpu-2.8.3+cu128-cp310`，已安装 pip 包（CUDA 12.8 / Python 3.10）
- **用途**: 与 `hmct` 包代码结构一致，但链接 `onnxruntime-gpu` 与 CUDA 版 `pyquantizer`/`onnxruntime_pybind11_state`，在 GPU 上执行校准推理（calibration）和 shape inference，显著加速大批量校准数据的处理
- **角色**: J6 Open Explorer 工具链 GPU 加速变体；与 CPU 版 `hmct` 共享 Python API 接口
- **关键依赖差异**: `onnxruntime-gpu`（替代 CPU 版 `onnxruntime`）、`onnxruntime-extensions == 0.10.1`、`numpy == 1.23.0`、`onnx == 1.15.0`、`protobuf == 3.20.3`
- **支持架构 / 后端 / 流水线**: 与 CPU 版完全相同（nash*、hbdk3/hbdk4/expt/trt/lut）
- **安装位置**: `package/host/ai_toolchain/code/hmct_gpu-2.8.3+cu128-cp310/`
- **关联**: 同目录下的 `hmct-2.8.3-cp310` 是 CPU 版本（oe_code_chunk_hmct）

## 目录结构

```
hmct_gpu-2.8.3+cu128-cp310/
  CLAUDE.md                          # 仓库级说明 (与 CPU 版相同)
  hmct/                              # 主包
    api.py                           # 顶层公共 API (build_model / check_model / ORTExecutor / ...)
    version.py                       # __version__ = "2.8.3"
    __init__.py                      # set_library_path: 把 compiler / ir/horizon_onnx / horizon_onnxruntime 加入 LD_LIBRARY_PATH
    builder/                         # build_onnx / build_caffe / build_model / check_model / check_onnx / ModelBuilder
    ir/                              # OnnxModel/Graph/Node/Variable/CalibrationNode + horizon_onnx C++ 后端 (.so)
    common/                          # data/ (Dataset, ColorConvert), misc/, modifier/, parser/, quant/ (QuantConfig)
    converter/                       # parse → prepare → optimize 流水线
      parser/{onnx,caffe,torch}_parser/
      preparer/                      # check_model, display_model, prepare, preprocess_model
      optimizer/                     # adapt/ fuse/ eliminate/ split/ replace/ move/ insert/ qat/
    quantizer/                       # 量化核心
      calibrater/                    #   activation/ weight/ post/ search_methods/ (GPU 加速关键路径)
      backend/{hbdk4,hbdk3,expt,trt,lut}/
      debugger/                      #   node_sensitivity, sensitivity_analysis, accumulation_error, tensor_analysis, parameter_distribution
    executor/                        # ORTExecutor (onnxruntime-gpu pybind, 使用 CUDA EP)
    custom/ + plugin/                # op_register / op_registration / BEVPoolingV2 / DeformConv2D
    reporter/                        # calculate_similarity, calculate_quant_type, calculate_hybrid_type, print_model_info
    tools/                           # debug.py (hmct-debugger CLI), convert, profiler, visualizer, simplify, compatibility
    skills/                          # SKILL.md 路由 + reference/ + j6-hmct-cosine-similarity-tuning/
    utility/                         # random_data, tempdir
  horizon_nn/                        # 轻量辅助包 (仅 __init__.py)
  hmct_gpu-2.8.3+cu128.dist-info/   # pip 元数据 (METADATA 列出 onnxruntime-gpu 等)
```

## 关键模块与 API

### 顶层 API (`hmct/api.py` — `__all__`)
| 导出名 | 说明 |
|--------|------|
| `build_model` | 完整量化构建（解析→准备→优化→校准→量化→可选编译） |
| `check_model` | 快速验证（随机数据，`check_mode=True`） |
| `load_model` | 加载 ONNX 模型（`hmct.ir.onnx_utils`） |
| `export_onnx` | 从 PyTorch 导出 ONNX（`hmct.converter.parser.torch_parser`） |
| `infer_shapes` | 修改模型并执行 shape inference |
| `register_pass` | 注册自定义图优化 pass |
| `PredicateBasedPass` | 自定义 pass 基类 |
| `ORTExecutor` | ONNX Runtime GPU 推理封装（CUDA ExecutionProvider） |
| `version` | `"2.8.3"` |

### `build_model` 签名 (`hmct/builder/build.py`)
```python
def build_model(
    onnx_model=None, march="nash",
    cali_data=None,               # np.ndarray | Dict[str, Sequence[np.ndarray]]
    quant_config=None,            # JSON 路径或 dict (model_config + node_config)
    input_dict=None,              # {input_name: {input_shape, transformer, color_convert}}
    name_prefix=None, verbose=True,
    # kwargs: onnx_file, prototxt_file, caffemodel_file, cali_dict, output_nodes,
    #         node_dict, hbdk_dict, debug_methods, optimization_methods,
    #         skip_step, save_model, return_builder, check_mode
) -> Union[ModelBuilder, "ModelProto", None]
```

### `ModelBuilder.build()` 流水线 (`hmct/builder/model_builder.py`)
1. **prepare** — `converter/parser` + `converter/preparer`（解析 ONNX/Caffe，应用 input_dict、opset 转换）
2. **optimize** — `converter/optimizer`（图优化、算子融合，`fuse_ln` 开关）
3. **calibrate** — `quantizer/calibrater`（**GPU 加速点**：使用 ORT CUDA EP 跑校准数据；方法 `max`/`kl`/`load`；per-channel/asymmetric/bias_correction）
4. **quantize** — `quantizer/backend/{hbdk4,hbdk3,expt,trt,lut}`
5. **compile**（可选，仅 hbdk3）→ hybrid 模型
6. **report** — `reporter/` 输出 cosine similarity / 量化类型 / quant_info.json

### `hmct-debugger` CLI 子命令 (`hmct/tools/debug.py`)
| 子命令 | 作用 |
|--------|------|
| `runall` | 一键运行全部分析 |
| `get-sensitivity-of-nodes` | 节点灵敏度排序 |
| `sensitivity-analysis` | 敏感节点深入分析 |
| `plot-distribution` | 量化前后数据分布对比 |
| `get-channelwise-data-distribution` | 逐通道分布 |
| `plot-acc-error` | 逐层累积误差 |
| `tensor-analysis` | 张量级分析 |

### Skills 入口 (`hmct/skills/SKILL.md`)
路由 A=build / B=check / C=精度调优（转交 `j6-hmct-cosine-similarity-tuning`）/ D=单项 debug。

## 常用查询映射

| 用户意图 | 推荐搜索关键词 | 说明 |
|----------|----------------|------|
| GPU 版量化构建 | `build_model`, `build_onnx`, `ModelBuilder` | 入口在 `hmct/builder/build.py` |
| GPU 校准推理 | `calibrate`, `create_pipeline`, `ORTExecutor` | 使用 CUDA EP 跑 calibrater 流水线 |
| CUDA execution provider | `ORTExecutor`, `onnxruntime-gpu`, `CUDAExecutionProvider` | `hmct/executor/ort*.py` |
| 校准方法选择 | `calibration_method`, `max`, `kl`, `load` | `quantizer/calibrater/calibration_method.py` |
| per-channel / asymmetric 量化 | `per_channel`, `asymmetric`, `QuantConfig` | `common/quant/quant_config.py` |
| 权重 bias correction | `bias_correction`, `bias_correction_num_sample` | 写入 `model_config.weight.bias_correction` |
| float16 上溢/下溢 | `resolve_float16_overflow`, `resolve_float16_underflow` | `quantizer/calibrater/` |
| 混合精度 / INT16 回退 | `node_config`, `quant_config`, `j6-hmct-cosine-similarity-tuning` | 调优 Skill 脚本 `hmct_precision_tuning.py` |
| 节点灵敏度 | `get-sensitivity-of-nodes`, `node_sensitivity` | `hmct-debugger` 子命令 |
| 数据分布 | `plot-distribution`, `parameter_distribution` | debugger 工具 |
| 累积误差 | `plot-acc-error`, `accumulation_error` | debugger 工具 |
| 张量分析 | `tensor-analysis`, `tensor_analysis` | debugger 工具 |
| cosine similarity 报告 | `calculate_similarity`, `save_quant_info` | `hmct/reporter/` |
| 图优化 pass | `register_pass`, `PredicateBasedPass`, `optimize` | `converter/optimizer/` |
| 算子融合 / LayerNorm 融合 | `fuse/`, `fuse_ln` | `converter/optimizer/fuse/` |
| 算子适配 / opset 转换 | `adapt/`, `op_convert` | `converter/optimizer/adapt/`, `preparer` |
| ONNX 模型解析 | `parse`, `parse_onnx`, `load_model` | `converter/parser/onnx_parser/` |
| Caffe 模型解析 | `parse_caffe`, `build_caffe`, `check_caffe` | `converter/parser/caffe_parser/` |
| PyTorch 导出 ONNX | `export_onnx`, `parse_torch` | `converter/parser/torch_parser/` |
| BPU 架构 march | `march`, `nash`, `nash-p`, `nash-e`, `hbdk4`, `hbdk3` | 决定后端选择 |
| 后端量化 hbdk4 | `quantize_for_hbdk4` | `quantizer/backend/hbdk4/` |
| 后端量化 hbdk3 (hybrid) | `quantize_for_hbdk3`, `compile` | v1.x 含 compile 阶段 |
| TRT 后端 | `quantize_for_trt`, `replace_calibration_with_onnx_qdq` | `quantizer/backend/trt/` |
| LUT 量化 | `quantize_fplut`, `fuse_to_b30_lut` | `quantizer/backend/lut/` |
| 自定义算子 | `op_register`, `op_registration`, `BEVPoolingV2`, `DeformConv2D` | `hmct/custom/`, `hmct/plugin/` |
| input_dict 配置 | `InputDictParser`, `input_shape`, `transformer`, `color_convert` | `common/parser/input_dict_parser.py` |
| hbdk_dict 编译参数 | `HbdkDictParser` | `common/parser/hbdk_dict_parser.py` |
| 动态 batch | `set_dynamic_batch` | `common/modifier/` |
| shape inference | `infer_shapes`, `shape_modifier` | `common/modifier/` |
| 添加中间输出 | `add_model_outputs` | `common/modifier/` |
| 校准数据目录结构 | `cali_data_dir`, `cali_dict`, `calibration_data` | 子目录名=输入节点名 |
| Dataset / 颜色转换 | `Dataset`, `ColorConvert` | `common/data/` |
| 模型简化 | `simplify` | `hmct/tools/simplify.py` |
| 模型性能分析 | `profiler` | `hmct/tools/profiler.py` |
| 量化前后对比 | `compare_original_and_optimized_model` | `hmct/tools/` |
| 校准前后对比 | `compare_calibrated_and_quantized_model` | `hmct/tools/` |
| 兼容性检查 | `compatibility` | `hmct/tools/compatibility.py` |
| 模型信息打印 | `hmct-info`, `print_model_info`, `print_info_dict` | `hmct/tools/print_calibration_info.py`, `reporter/` |
| 量化类型统计 | `calculate_quant_type`, `calculate_hybrid_type` | `hmct/reporter/` |
| 子模型提取 | `extract_submodel` | `hmct/ir/` |
| 随机数据生成 | `random_data` | `hmct/utility/` |
| 临时目录 | `tempdir` | `hmct/utility/` |
| 一键构建脚本 | `run_build.py build`, `run_build.py check` | `hmct/skills/reference/` |
| 精度调优脚本 | `hmct_precision_tuning.py`, `get_sensitivity_of_nodes.py` | `skills/j6-hmct-cosine-similarity-tuning/script/` |

## 规则与约定

- **包名区分**: GPU 版 pip 包名 `hmct-gpu`，导入名仍是 `import hmct`；代码结构与 CPU 版 `hmct` 完全一致，差异仅在链接的 `.so`（onnxruntime-gpu 的 CUDA EP）
- **版本号**: `__version__ = "2.8.3"`（`hmct/version.py`），dist-info 版本 `2.8.3+cu128`
- **LD_LIBRARY_PATH**: `hmct/__init__.py` 的 `set_library_path()` 自动把 `compiler/`、`ir/horizon_onnx/`、`horizon_onnxruntime/` 注入环境变量，确保 C++ .so 可被加载
- **march 与后端映射**: `nash*`/`expt` → hbdk4（v2.x 仅生成 PTQ 模型）；`bayes`/`bernoulli*` → hbdk3（含 compile → hybrid）；`trt`/`lut` 走各自后端
- **build_model 输入**: 优先 `onnx_model` 对象；否则 `onnx_file`；最后 `prototxt_file + caffemodel_file`；三者至少指定一种
- **cali_data 格式**: 单输入模型可传 `Sequence[np.ndarray]`；多输入必须传 `Dict[str, Sequence[np.ndarray]]`
- **quant_config**: JSON 含 `model_config`（全局：`all_node_type`、`activation.calibration_type`/`per_channel`/`asymmetric`、`weight.bias_correction`）+ `node_config`（逐节点覆盖，如 `{"sensitive_conv": {"ON": "int16"}}`）
- **校准数据目录约定**: `cali_data_dir/<input_node_name>/*.npy`，子目录名必须与模型输入节点名严格一致
- **阶段隔离**: `ModelBuilder` 每个阶段接收 `OnnxModel` 的深拷贝，阶段间不共享状态
- **`check_mode=True`**: `check_model` 用 fake 校准方法 + 随机数据，比 `build_model` 快得多，用于快速验证
- **CLI 入口**: `hmct-debugger`（`tools/debug.py`）、`hmct-info`（`tools/print_calibration_info.py`）、`python -m hmct.skills.reference.run_build {build,check}`
- **固定依赖版本**: `onnx==1.15.0`、`numpy==1.23.0`（py3.10）、`protobuf==3.20.3`；升级这些包极易破坏兼容性
- **GPU 加速范围**: 仅**校准推理**和 **shape inference** 跑在 GPU；量化参数计算、图优化、编译仍在 CPU
- **常见坑**: 同时安装 `hmct` 与 `hmct-gpu` 会冲突（导入名均为 `hmct`）；`enable_int16` 参数已废弃，需用 `node_dict`；`onnxruntime-gpu` 版本必须与 CUDA 12.8 匹配
