# oe_code_chunk_llm_compression

## 仓库概述

- **名称**: llm_compression (Horizon LLM/VLM PTQ 量化 & 编译工具包) v2.0.2
- **Python 包**: `llm_compression`，源码分发包（非 wheel，包含完整 Python 源码）
- **用途**: 将 HuggingFace 浮点大语言模型 / 视觉语言模型经过 PTQ 校准 → 编译 → 板端评估流水线，产出 HBM（Horizon Binary Model）制品，部署到 Horizon BPU 硬件
- **角色**: J6 Open Explorer (OE) LLM v2.0.0 RC3 工具链的核心量化编译组件，位于 LLM 包根目录下
- **核心依赖**: `hbdk4`（4.11.2，编译后端）、`horizon-plugin-pytorch`（3.3.4，量化插桩）、`hbm-infer`（3.15.3，板端 RPC 推理）、`torch`（2.8.0+cu128）、`transformers`（4.57.6）
- **流水线产物**: 校准检查点（`.pth.tar`）→ 假量化 HBIR（`.bc`）→ HBO（`.hbo`）→ HBM（`.hbm`）+ embed_tokens（`.bin`）+ tokenizer 文件
- **运行环境**: x86-64 主机侧，需 CUDA GPU；板端评估通过 SSH + HBM RPC 远程执行

## 目录结构

```
llm_compression/
  __init__.py                          # 包入口，导出 __version__
  version.py                           # 版本号定义（__version__ = "2.0.2"）
  registry_factory.py                  # Register 注册表：MODEL_REGISTRY / DATASET_REGISTRY
  requirements.txt                     # Python 依赖（transformers, easydict, tensorboard）
  deps_version.conf                    # 外部依赖版本约束（HBDK4, plugin, hbm_infer, torch）
  build_env.sh                         # 环境构建脚本（安装 torch, plugin, hbdk4, hbm-infer, VLMEvalKit）
  CLAUDE.md                            # Claude Code 工作指引文档

  configs/                             # YAML 模型配置文件（每模型一个）
    qwen3_vl.yml                       #   Qwen3-VL-2B 配置
    qwen2_5_vl.yml                     #   Qwen2.5-VL-7B 配置
    internvl3_5_1b.yml                 #   InternVL3.5-1B 配置
    internvl_1b.yml                    #   InternVL-1B 配置
    internvl_2b.yml                    #   InternVL-2B 配置

  scripts/                             # Shell 流水线入口脚本
    common.sh                          #   公共函数（环境设置、运行时配置、日志）
    calib.sh                           #   PTQ 校准入口
    compile.sh                         #   编译入口（校准模型 → HBM）
    torch_eval.sh                      #   PyTorch 侧精度评估
    hbm_rpc_eval.sh                    #   板端 BPU 远程评估
    quant_analysis.sh                  #   量化敏感度分析

  tools/                               # Python 流水线工具（每阶段一个入口脚本）
    calib.py                           #   校准主流程：Float2Calibration → 数据前向 → 保存检查点
    compile.py                         #   编译主流程：加载校准检查点 → Calibration2Hbm → hbo2hbm
    torch_eval.py                      #   PyTorch 侧精度评估
    hbm_rpc_eval.py                    #   HBM RPC 板端评估
    quant_analysis.py                  #   量化敏感度分析
    create_mixed_calib.py              #   混合精度校准数据生成
    moe_expert_coverage.py             #   MoE 专家覆盖率分析
    utils.py                           #   配置解析（parse_config）、ConfigValidator 校验
    version_check.py                   #   依赖版本检查

  converters/                          # 核心转换器模块
    __init__.py                        #   导出所有转换器
    calib_converter.py                 #   Float2Calibration：浮点模型 → 校准模型（JIT trace + qconfig + 校准）
    compile_converter.py               #   Calibration2Hbm：校准模型 → HBM（export → llm_convert → convert → compile → link）
    hbm_rpc_eval_converter.py         #   HBM RPC 评估转换器
    quant_analysis_converter.py        #   量化分析转换器

  models/                              # 模型注册与实现
    __init__.py                        #   导入所有模型（触发 @MODEL_REGISTRY 注册）
    base_qmodel.py                     #   BaseQModel 抽象基类（定义量化接口）
    generate_utils.py                  #   生成辅助工具
    logits_process.py                  #   Logits 处理器
    horizon_modules/                   #   Horizon 自定义模块（FlashAttention 等）
    internvl_1b/                       #   InternVL-1B 模型实现
    internvl_2b/                       #   InternVL-2B 模型实现
    internvl3_5_1b/                    #   InternVL3.5-1B 模型实现
    qwen2_5_vl/                        #   Qwen2.5-VL-7B 模型实现
    qwen3_vl/                          #   Qwen3-VL-2B 模型实现

  datasets/                            # 数据集注册与实现
    __init__.py                        #   导入所有数据集（触发 @DATASET_REGISTRY 注册）
    llm/                               #   LLM 数据集
      mmlu.py                          #     MMLU 基准数据集
      ppl_dataset.py                   #     Perplexity 数据集
    vlm/                               #   VLM 数据集
      mmbench.py                       #     MMBench 基准数据集（需 VLMEvalKit）
      vlm_json.py                      #     JSON 格式 VLM 数据集

  ir_modules/                          # 中间表示运行时模块
    __init__.py                        #   导出 IrModule、PipelineHbmModule
    ir_module.py                       #   IrModule 基类（输入/输出 reformat 钩子）
    hbir_module.py                     #   HBIR 模块
    hbm_module.py                      #   PipelineHbmModule（hbm_infer RPC 封装）

  utils/                               # 工具模块
    __init__.py                        #   导出 AttentionManager
    attention_manager.py               #   AttentionManager（eager/flash 注意力切换）
    device_manager.py                  #   DeviceManager（GPU round-robin 分配 + 内存感知选择）
    logger.py                          #   日志工具
    trace_utils.py                     #   JIT trace 辅助（trace_all_branches 上下文管理器）

  lightcompress/                       # 内嵌 LLM 压缩子工具包
    llmc/                              #   LLMC 主模块（compression, data, eval, models）
      __main__.py                      #     入口点
    scripts/                           #   脚本（convert_mmlu_to_calib, run_llmc, run_lm_eval）
    tools/                             #   工具（attention_vis, download_calib_dataset, llm_eval 等）
    tests/                             #   测试（test_auto_clip_mix_bits）
    requirements/                      #   依赖列表
    LICENSE                            #   许可证
```

## 核心流水线

### 端到端流程

```
Float Model (HuggingFace)
  ↓ bash scripts/calib.sh
  Float2Calibration (converters/calib_converter.py)
    → set_march + QconfigSetter 应用量化模板
    → horizon.quantization.prepare (JIT_STRIP 方法)
    → 校准数据前向传播（DataLoader 遍历）
    → sync_kvcache_scales（统一 prefill/decode KV-cache 量化 scale）
    → 保存校准检查点 (.pth.tar)
  ↓ bash scripts/compile.sh
  Calibration2Hbm (converters/compile_converter.py)
    → 加载校准检查点
    → horizon.quantization.export（假量化 HBIR，.bc 文件）
    → llm_convert（nash-p 专用：rmsnorm/softmax 替换）
    → hbdk4.compiler.convert（量化模型转换）
    → hbdk4.compiler.compile（HBO 编译，多线程并行）
    → hbo2hbm（link：prefill+decode → language.hbm，visual → visual.hbm）
    → 保存 embed_tokens.bin + tokenizer 文件
  ↓ bash scripts/hbm_rpc_eval.sh
  PipelineHbmModule (ir_modules/hbm_module.py)
    → HbmRpcServer SSH 连接远端板卡
    → HbmRpcSessionFlexible 推理
    → quant_input / dequant_output 量化/反量化
```

### Registry 注册机制

`registry_factory.py` 定义 `Register`（dict 子类），通过 `@MODEL_REGISTRY` / `@DATASET_REGISTRY` 装饰器注册。`models/__init__.py` 和 `datasets/__init__.py` 在 import 时触发所有模型和数据集的注册。

```python
# 注册示例（models/qwen3_vl/qwen3_vl_model.py）
@MODEL_REGISTRY
class Qwen3_VL(BaseQModel):
    ...

# 使用
q_model = MODEL_REGISTRY["Qwen3_VL"](model_path, custom_config)
```

## 关键模块与 API

### BaseQModel 抽象基类 (`models/base_qmodel.py`)

| 方法 | 说明 |
|------|------|
| `__init__(model_dir, custom_config)` | 初始化：调用 `build_model`、`_apply_vocab_compression`、创建 `DeviceManager` |
| `build_model(model_dir)` | **[抽象]** 从 HuggingFace 目录加载模型权重，构建自定义模型图 |
| `get_model_trace_dummy_input(model_part)` | **[抽象]** 获取 JIT trace 用的 dummy 输入 |
| `get_generated_model()` | **[抽象]** 返回带 `.generate()` 方法的模型（用于校准推理） |
| `get_qconfig_setting(model_part)` | 获取量化配置模板列表（按 march 分 nash-p / nash-e 两套默认模板） |
| `get_kvcache_names(model_name)` | 返回 KV-cache fake-quant stub 名称列表（用于 scale 同步） |
| `get_model_input_output_name(model_part)` | 获取模型部分的输入输出名称 |
| `input_preprocess(message)` | 消息预处理（模型可覆盖） |
| `is_shared_lm_mode()` | 判断是否共享 LM 模式（model_list 含 "lm"） |
| `setup_decode_model(decode_model)` | 编译阶段 deepcopy 后的 decode 模型后处理钩子 |
| `_apply_vocab_compression()` | 按 `kept_tokens_file` 裁剪 lm_head 词表大小 |

### Float2Calibration (`converters/calib_converter.py`)

| 方法/函数 | 说明 |
|----------|------|
| `Float2Calibration.__init__(q_model, model_part, custom_config, observer)` | 初始化校准器：set_march、QconfigSetter、加载 weight qparams |
| `Float2Calibration.__call__(model, calib_ckpt_path)` | 执行校准：`horizon.quantization.prepare` (JIT_STRIP) → 加载/进入校准模式 |
| `sync_kvcache_scales(q_model, prefill_model, decode_model)` | 统一 prefill/decode 的 INT8 KV-cache scale |
| `load_weight_qparams(model_dir)` | 从 safetensors 提取预量化权重参数（threshold、dtype） |

### Calibration2Hbm (`converters/compile_converter.py`)

| 方法/函数 | 说明 |
|----------|------|
| `Calibration2Hbm.__init__(q_model, model_part, custom_config)` | 初始化编译器：自动从 q_model 获取 example_inputs / input_names / output_names |
| `Calibration2Hbm.__call__(model)` | 完整编译流水线：export → llm_convert → convert → compile → HBO |
| `hbo2hbm(compiled_hbos, save_path, hbm_desc, hbm_names)` | 链接 HBO → HBM（prefill+decode 合并为 language.hbm） |
| `get_hbm_desc(q_model)` | 构建 HBM 元数据描述（HF configs + horizon 字段） |
| `get_hbm_name(q_model, model_name, custom_config)` | 生成 HBM 文件名（含分辨率、chunk_size、cache_len、march、core_num） |
| `save_embed_tokens(model_name, embedding, output_path)` | 保存词嵌入权重为 .bin 文件 |
| `save_tokenizer_files(model_path, output_path)` | 复制/生成 tokenizer 文件 |

### PipelineHbmModule (`ir_modules/hbm_module.py`)

| 方法 | 说明 |
|------|------|
| `PipelineHbmModule.__init__(host, hbm_path, ...)` | 初始化 HBM RPC 推理模块（SSH 连接、创建 session） |
| `forward_impl(data)` | 执行远端 BPU 推理（支持 tensor dump） |
| `quant_input_data(data)` | 根据 HBM 输入量化信息对输入数据进行量化 |
| `dequant_output_data(data)` | 根据 HBM 输出量化信息对输出数据进行反量化 |
| `PipelineHbmServer.__init__(host, hbm_path, ...)` | HBM RPC 服务器封装（HbmRpcServer + HbmHandle + HbmRpcSessionFlexible） |

### DeviceManager (`utils/device_manager.py`)

| 方法 | 说明 |
|------|------|
| `DeviceManager.__init__(model, model_list)` | 初始化：round-robin 分配模型部分到 GPU |
| `DeviceManager._assign()` | 将模型子模块按 round-robin 分配到 CUDA 设备 |
| `DeviceManager.select_device(module, num_copies)` | 内存感知设备选择：检查 GPU 能否同时容纳 num_copies 份模块，不够则返回 None（CPU 回退） |

### AttentionManager (`utils/attention_manager.py`)

| 方法 | 说明 |
|------|------|
| `AttentionManager.set(config)` | 根据 flash_attention 配置设置注意力类型（eager / flash） |
| `AttentionManager.is_flash_attn()` | 判断是否使用 flash attention |
| `AttentionManager.get_flash_block_size()` | 获取 flash attention block size |

### ConfigValidator (`tools/utils.py`)

| 方法 | 说明 |
|------|------|
| `ConfigValidator.validate(config, stage)` | 按阶段校验配置（总是校验 model 部分，仅校验当前活跃阶段的 section） |
| `parse_config(stage)` | 解析命令行参数 + 加载 YAML 配置 + 版本检查 + 校验 + 日志重定向 |
| `build_dataset_kwargs(dataset_type, section_config, q_model)` | 构建数据集构造函数参数（**kwargs 模式，未识别的 key 被忽略） |
| `validate_model_parts(model, model_list, model_name)` | 验证 model_list 中的所有 part 在 model 上存在 |

## 配置系统

### YAML 配置结构

```yaml
model:
  march: nash-p                    # BPU 架构（nash-p / nash-e / nash-m）
  model_name: Qwen3_VL             # 注册表中的模型名称
  model_path: /path/to/hf_model    # HuggingFace 模型目录
  model_list: [visual, prefill, decode]  # 模型部分列表（或 [visual, lm] 共享模式）
  model_dtype: float32
  do_sample: false
  chunk_prefill: true
  vision_config:
    image_height: 448
    image_width: 448
  text_config:
    max_kvcache_len: 1024          # KV cache 最大长度
    max_lm_input_len: 512          # prefill 最大输入长度

calibration:
  dataset_type: mmbench            # 校准数据集类型
  data_path: /path/to/data
  calib_ckpt_save_path: ./output
  calibration_step: 50

compile:
  hbm_save_path: ./output
  calib_ckpt_load_path: ./calib_output
  rmsnorm_version: cuda_hp         # rmsnorm 实现版本
  opt_level: 2                     # 编译优化级别
  jobs: 120                        # 编译并行任务数
  cache_mode: enable               # 编译缓存模式
  core_num: 4                      # BPU 核心数
  visual:                          # 模型部分特定配置（覆盖通用配置）
    rmsnorm_version: cuda

hbm_rpc_eval:
  host: 10.103.110.34
  username: root
  core_id: [0, 1, 2, 3]
  hbm_load_path: ./compile_output
```

### Shared LM vs Separate Prefill/Decode

- `[visual, prefill, decode]`：分别校准 prefill 和 decode，更高内存占用
- `[visual, lm]`：共享 LM 实例（校准内存减少 ~50%），编译阶段 `_split_shared_lm()` 做 deepcopy 拆分

### BPU 架构支持

| 架构 | 默认激活 dtype | Dynamic Quant | rmsnorm |
|------|---------------|---------------|---------|
| nash-p | INT8 | 支持（nn.Linear, block_size=full） | cuda_hp |
| nash-e / nash-m | INT16 | 不支持 | cuda |

## 支持的模型

| 模型 | 注册名 | 配置文件 | 模型文件 |
|------|--------|---------|---------|
| Qwen3-VL-2B | `Qwen3_VL` | `configs/qwen3_vl.yml` | `models/qwen3_vl/` (qwen3_vl_model.py, model.py, blocks/, process_utils.py) |
| Qwen2.5-VL-7B | `Qwen2_5_VL` | `configs/qwen2_5_vl.yml` | `models/qwen2_5_vl/` (qwen2_5_vl_model.py, model.py, blocks/, vision_embedding.py) |
| InternVL3.5-1B | `InternVL3_5` | `configs/internvl3_5_1b.yml` | `models/internvl3_5_1b/` (internvl3_5_model.py, model.py, blocks/) |
| InternVL-1B | `InternVL_1B` | `configs/internvl_1b.yml` | `models/internvl_1b/` (internvl_1b_model.py, model.py, blocks/) |
| InternVL-2B | `InternVL_2B` | `configs/internvl_2b.yml` | `models/internvl_2b/` (internvl_2b_model.py, model.py, blocks/) |

每个模型目录结构统一：`<model>_model.py`（BaseQModel 子类）+ `model.py`（模型图）+ `blocks/`（attention/mlp/transformer_block）+ `process_utils.py`（图像/文本预处理）。

## 支持的数据集

| 数据集 | 注册名 | 类型 | 说明 |
|--------|--------|------|------|
| MMBench | `mmbench` | VLM | 需 VLMEvalKit |
| VLM JSON | `vlm_json` | VLM | JSON 格式自定义数据集 |
| MMLU | `mmlu` | LLM | 需 opencompass |
| PPL | `ppl` | LLM | Perplexity 评估数据集 |

## 常用查询映射

| 用户意图 | 推荐搜索关键词 | 说明 |
|---|---|---|
| PTQ 校准流程 | `Float2Calibration`, `calib.py`, `calib.sh` | 浮点模型 → 校准模型 |
| 编译流程 | `Calibration2Hbm`, `compile.py`, `compile.sh` | 校准模型 → HBM |
| 量化配置 | `QconfigSetter`, `qconfig_setting`, `nashp_default_qconfig_template` | 量化模板与 dtype 设置 |
| KV-cache 同步 | `sync_kvcache_scales`, `get_kvcache_names` | prefill/decode scale 统一 |
| HBM RPC 评估 | `PipelineHbmModule`, `HbmRpcSession`, `hbm_rpc_eval` | 板端远程推理评估 |
| 模型注册 | `MODEL_REGISTRY`, `@MODEL_REGISTRY`, `Register` | 模型注册表机制 |
| 数据集注册 | `DATASET_REGISTRY`, `@DATASET_REGISTRY` | 数据集注册表机制 |
| BaseQModel 接口 | `BaseQModel`, `build_model`, `get_model_trace_dummy_input` | 模型抽象接口 |
| YAML 配置解析 | `parse_config`, `ConfigValidator`, `EasyDict` | 配置加载与校验 |
| 共享 LM 模式 | `_split_shared_lm`, `is_shared_lm_mode`, `lm` | prefill/decode 共享 LM |
| GPU 设备管理 | `DeviceManager`, `select_device`, `round-robin` | 多 GPU 分配 |
| Flash Attention | `AttentionManager`, `is_flash_attn`, `flash_block_size` | 注意力类型切换 |
| JIT trace | `trace_all_branches`, `JIT_STRIP`, `example_inputs` | 模型图捕获 |
| HBIR 导出 | `export`, `llm_convert`, `convert`, `compile`, `link` | 编译管线各步骤 |
| 词表压缩 | `_apply_vocab_compression`, `kept_tokens_file`, `lm_head` | 输出词表裁剪 |
| HBM 文件命名 | `get_hbm_name`, `chunk_size`, `cache_len`, `core_num` | HBM 文件名规则 |
| HBM 元数据 | `get_hbm_desc`, `hbm_desc`, `horizon_desc` | HBM 描述信息构建 |
| embed 保存 | `save_embed_tokens`, `embed_tokens.bin` | 词嵌入权重导出 |
| 量化敏感度 | `quant_analysis`, `quant_analysis_converter` | 量化精度分析 |
| 权重预量化 | `load_weight_qparams`, `safetensors`, `qint4`, `qint8` | 从 safetensors 提取量化参数 |
| lightcompress | `lightcompress`, `llmc`, `__main__.py` | 内嵌 LLM 压缩子工具 |
| 依赖版本 | `deps_version.conf`, `version_check`, `check_deps_version` | 外部依赖版本约束 |
| Dynamic Quant | `SetDynamicQuantTemplate`, `nn.Linear`, `block_size` | nash-p 动态量化 |
| 编译参数 | `opt_level`, `jobs`, `cache_mode`, `enable_hpc`, `core_num` | 编译配置参数 |
| rmsnorm 版本 | `rmsnorm_version`, `cuda_hp`, `cuda` | RMSNorm 实现选择 |

## 规则与约定

- **Pipeline 阶段隔离**：每个 shell 脚本只执行一个阶段（calib / compile / eval），通过 `--config_path` 指定 YAML 配置
- **ConfigValidator 按阶段校验**：只校验当前活跃阶段的配置 section，避免其他阶段的缺失路径报错
- **模型注册时机**：`models/__init__.py` 在 import 时触发所有模型类的 import，`@MODEL_REGISTRY` 装饰器自动注册
- **Shared LM deepcopy**：编译阶段 `_split_shared_lm()` 做 `copy.deepcopy`，内存不够时回退到 CPU 再搬回 GPU
- **KV-cache scale 统一**：prefill 和 decode 的 KV-cache INT8 scale 取绝对值较大的那个，确保运行时共享内存时数值一致
- **Qconfig 模板继承**：nash-p 默认 INT8 激活 + FP16 VAE + Dynamic Quant；nash-e 默认 INT16 激活 + INT16 VAE
- **编译产物命名**：`{model_name}_vision_{W}x{H}_w{bits}_{march}_corenum_{N}.hbm` / `{model_name}_language_chunk_{chunk}_cache_{cache}_w{bits}_{march}_corenum_{N1}_{N2}.hbm`
- **日志重定向**：`_setup_local_logging` 通过 `tee` 子进程重定向 stdout/stderr 到阶段输出目录的日志文件
- **环境构建**：`build_env.sh` 安装 torch 2.8.0+cu128、horizon-plugin-pytorch、hbdk4、hbm-infer、VLMEvalKit
- **lightcompress 子工具包**：独立的 LLM 压缩框架（llmc），有自己的 compression/data/eval/models 模块，入口为 `llmc/__main__.py`
- **板端评估**：`hbm_rpc_eval` 通过 SSH 连接远端 J6 板卡，使用 `HbmRpcSessionFlexible` 执行 BPU 推理，支持 core_id 指定和 remote_environment 环境变量注入
