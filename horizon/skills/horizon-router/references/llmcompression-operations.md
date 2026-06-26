# LLM Compression 日常操作

llm_compression 是独立于 OE / OE-LLM 的 LLM 工具链包，提供校准、评测、编译、板端推理等标准脚本。本文档覆盖日常操作的标准用法。

> **与 llmcompression-add-model 的区分**：新增模型架构支持（编写 blocks/、model.py 等）请路由到 `llmcompression-add-model`；运行校准/评测/编译/板端推理等日常操作参见本文档。

## ⛔ 标准脚本优先

**必须使用 llm_compression 提供的标准 shell 脚本**，禁止自写 Python 包装器或自定义配置文件。标准脚本封装了环境初始化、配置解析、日志采集等逻辑。

| 操作 | 标准脚本 | Python 后端 | 产出 |
|------|---------|------------|------|
| 校准（float→量化） | `bash scripts/calib.sh --config_path <yml>` | calib.py | `*_calibration.pth.tar`（每个 model_list 部件一个） |
| GPU 精度评测 | `bash scripts/torch_eval.sh --config_path <yml>` | torch_eval.py | `eval_results/` 目录 |
| HBM 编译 | `bash scripts/compile.sh --config_path <yml>` | compile.py | `*.hbm` + `embed_tokens.bin` + tokenizer 文件 |
| 板端精度评测 | `bash scripts/hbm_rpc_eval.sh --config_path <yml>` | hbm_rpc_eval.py | `hbm_rpc_eval_results/` 目录 |
| 量化误差分析 | `bash scripts/quant_analysis.sh --config_path <yml>` | quant_analysis.py | `quant_analysis_results/` 目录 |

所有脚本使用统一的调用模式：

```bash
bash scripts/<name>.sh --config_path <yaml>
```

## 标准流水线

```
1. calib.sh      → 校准产出 *_calibration.pth.tar
2. torch_eval.sh  → (可选) GPU 上精度评测，验证校准质量
3. compile.sh     → 将校准产物编译为 .hbm 文件
4. hbm_rpc_eval.sh → (可选) 板端精度评测
5. quant_analysis.sh → (可选) 逐层量化误差分析
```

每步通过 YAML config 中的路径字段串联：

| 步骤 | 读取路径字段 | 写入路径字段 |
|------|------------|------------|
| calib | - | `calibration.calib_ckpt_save_path` |
| torch_eval | `evaluation.calib_ckpt_load_path` | `evaluation.result_path` |
| compile | `compile.calib_ckpt_load_path` | `compile.hbm_save_path` |
| hbm_rpc_eval | `hbm_rpc_eval.hbm_load_path` | `hbm_rpc_eval.result_path` |
| quant_analysis | `quant_analysis.baseline_model_load_path` | `quant_analysis.result_path` |

## YAML 配置结构

配置文件包含以下主要段落：

### model 段（必填）

```yaml
model:
  march: nash-p                    # BPU 架构：nash-p (J6P) 或 nash-e (J6E/J6M)
  model_name: Qwen3_VL            # 必须匹配 MODEL_REGISTRY 注册名
  model_path: /path/to/checkpoint # HuggingFace 模型目录
  model_list: [visual, prefill, decode]  # 模型部件列表
  # 或 [visual, lm] — 共享 LM 模式，节省约 50% LM 内存
  model_dtype: float32
  do_sample: false                 # false=greedy, true=multinomial
  chunk_prefill: true              # 分块预填充
  enable_thinking: false           # 仅 Qwen3 支持
  vision_config:
    image_height: 448
    image_width: 448
  text_config:
    max_kvcache_len: 1024          # KV cache 总容量（token 数）
    max_lm_input_len: 512          # 预填充输入长度（必须 < max_kvcache_len）
```

### calibration 段

```yaml
calibration:
  dataset_type: mmbench            # 注册的数据集名
  data_path: /path/to/MMBench.tsv
  log_path: ./qconfig_setting
  calib_ckpt_save_path: ./output_calib
  calibration_step: 50
```

### evaluation 段

```yaml
evaluation:
  dataset_type: mmbench
  data_path: /path/to/MMBench.tsv
  eval_step: 1500
  calib_ckpt_load_path: ./output_calib
  result_path: ./eval_results
  direct_answer: true
```

### compile 段

```yaml
compile:
  hbm_save_path: ./compile_output
  calib_ckpt_load_path: ./output_calib
  rmsnorm_version: cuda_hp         # cuda | triton | cuda_hp
  opt_level: 2
  jobs: 120
  cache_path: ./llm_cache
  core_num: 4                      # BPU 核心数
  enable_hpc: true
  max_l2m_size: 25165824
```

### hbm_rpc_eval 段

```yaml
hbm_rpc_eval:
  host: 10.103.53.154              # 板端 IP
  username: root
  password: null                   # null = 密钥认证
  remote_root: /map/hbm_infer
  core_id: [0, 1, 2, 3]
  remote_environment:
    HB_DNN_USER_DEFINED_L2M_SIZES: "6:6:6:6"
  hbm_load_path: ./compile_output
  result_path: ./hbm_rpc_eval_results
```

### quant_analysis 段

```yaml
quant_analysis:
  stage: fake_quant                # 目前仅支持 fake_quant
  dataset_type: mmbench
  data_path: /path/to/MMBench.tsv
  steps: 1
  metrics: [L1]                    # ATOL | COSINE | L1
  baseline_model_load_path: ./output_calib
  analysis_model_load_path: ./output_calib
  result_path: ./quant_analysis_results
```

## 可用配置模板

`configs/` 目录下提供以下预置模板：

| 模板文件 | 模型 | 视觉组件名 |
|---------|------|-----------|
| `qwen2_5_vl.yml` | Qwen2.5-VL-3B-Instruct | `visual` |
| `qwen3_vl.yml` | Qwen3-VL-2B-Instruct | `visual` |
| `internvl_1b.yml` | InternVL2_5-1B | `vision_model` |
| `internvl_2b.yml` | InternVL2-2B | `vision_model` |
| `internvl3_5_1b.yml` | InternVL3_5-1B-Instruct | `vision_model` |

### 模型间配置差异

| 配置项 | Qwen 系列 | InternVL 系列 |
|--------|----------|-------------|
| 视觉组件名 | `visual` | `vision_model` |
| 文本配置键 | `text_config` | `llm_config` |
| 图像尺寸键 | `image_height` + `image_width` | `image_size`（单值） |
| `enable_thinking` | 仅 Qwen3 支持 | 不支持 |
| `softmax_version` | 不设置 | `vae`（InternVL 1B/2B） |

## 执行环境

### Docker 模式（EXECUTION_MODE=docker）

读取 `.horizon/.env.oe-llm-package` 中的 `DOCKER_EXEC_PREFIX`，拼接命令执行：

```bash
# 校准示例
eval "$DOCKER_EXEC_PREFIX 'cd /open_explorer_llm/llm_compression && bash scripts/calib.sh --config_path configs/qwen3_vl.yml'"

# 编译示例
eval "$DOCKER_EXEC_PREFIX 'cd /open_explorer_llm/llm_compression && bash scripts/compile.sh --config_path configs/qwen3_vl.yml'"
```

> **注意**：Docker 内 OE-LLM 包自动挂载到 `/open_explorer_llm`，脚本中应使用容器内路径。

### Local 模式（EXECUTION_MODE=local）

```bash
source .horizon/venv-llm/bin/activate
cd $OE_LLM_DIR/llm_compression
bash scripts/calib.sh --config_path configs/qwen3_vl.yml
```

## ⛔ GPU 编译预检（compile.sh 前必检）

2B+ 参数模型的 compile 阶段需要 GPU（HBDK LLVM 后端依赖 CUDA）。在执行 `compile.sh` 之前**必须**检查 GPU 可用性：

1. **检查 EXECUTION_MODE**：docker 模式下确认 `DOCKER_TYPE=gpu`
2. **测试 GPU 可用性**：
   ```bash
   eval "$DOCKER_EXEC_PREFIX 'nvidia-smi'"
   ```
3. **GPU 不可用** → 向用户报告阻塞：`"LLM 模型编译需要 GPU 环境，当前环境无可用 GPU"`，**不要尝试在无 GPU 环境编译**

常见 GPU 不可用场景：
- CPU Docker 镜像（OE-LLM 包仅提供 GPU 镜像）
- Docker 嵌套环境（容器内再启容器，NVML 初始化失败）
- 无 CUDA 驱动的宿主机

## VLM 已知限制

部分 VLM 模型（如 Qwen3-VL）在校准阶段可能遇到 `tensor_dispatch_wrapper` 动态控制流问题。详见 `.horizon/skills/llm/llm_compression/llmcompression-add-model/vlm_known_limitations.md`。

## 注意事项

- `model_list` 中的部件名必须与 `MODEL_REGISTRY` 中注册的一致，否则 calib 阶段会报 KeyError
- `max_lm_input_len` 必须严格小于 `max_kvcache_len`，否则编译阶段会报错
- `core_num` 影响编译产物的核心绑定方式，必须与板端实际 BPU 核心数匹配
- `hbm_rpc_eval` 段的 `remote_environment.HB_DNN_USER_DEFINED_L2M_SIZES` 必须与 `core_num` 匹配：单核 `24:0:0:0`，四核 `6:6:6:6`
- 校准数据集路径必须是真实路径，不能使用随机数据（与 HMCT 的 check 模式不同）
