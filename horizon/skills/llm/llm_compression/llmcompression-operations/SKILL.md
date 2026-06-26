---
name: llmcompression-operations
version: 2.0.4
description: llm_compression 日常操作 Skill。覆盖校准(calib.sh)、GPU精度评测(torch_eval.sh)、HBM编译(compile.sh)、板端精度评测(hbm_rpc_eval.sh)、量化分析(quant_analysis.sh)的标准用法。触发关键词：校准、calib、torch_eval、compile、hbm_rpc_eval、quant_analysis、LLM编译、LLM量化评测、板端推理评测。注意：llm_compression 是独立于 OE 的工具包，不走 OE/OE-LLM 包检查流程。新增模型支持请路由到 llmcompression-add-model。
---

# LLM Compression 日常操作

llm_compression 是独立于 OE / OE-LLM 的 LLM 工具链包，提供校准、评测、编译、板端推理等标准脚本。

> **与 llmcompression-add-model 的区分**：新增模型架构支持（编写 blocks/、model.py 等）请路由到 `llmcompression-add-model`；运行校准/评测/编译/板端推理等日常操作使用本 Skill。

---

## ⛔ 关键规则

### ⛔⛔ 执行目录：必须从项目根目录运行（禁止 cd 进 llm_compression/）

> **这是最常见的致命错误。** `cd` 进 `llm_compression/` 会导致 Python 循环引用，所有脚本在 import 阶段即崩溃。

`llm_compression/` 目录下有一个 `datasets/` 子包，与第三方库 `datasets`（HuggingFace）同名。当 CWD 为 `llm_compression/` 时，Python 的 `sys.path[0]=''`（CWD）会优先搜索到本地 `datasets/` 子包，遮蔽第三方库，触发：

```
ImportError: cannot import name 'load_dataset' from partially initialized module 'datasets'
(most likely due to a circular import)
```

**正确做法** — 从 OE LLM 包根目录（`llm_compression/` 的父目录）执行脚本：

```bash
# ✅ 正确：CWD = 项目根目录
cd ${OE_LLM_DIR}   # 即 /open_explorer_llm
bash llm_compression/scripts/calib.sh --config_path llm_compression/configs/qwen3_vl.yml

# ❌ 错误：CWD = llm_compression/ → circular import
cd ${OE_LLM_DIR}/llm_compression
bash scripts/calib.sh --config_path configs/qwen3_vl.yml
```

**所有标准脚本的路径和配置路径都必须从项目根目录相对书写：**

| 操作 | ✅ 正确命令（CWD = 项目根目录） |
|------|-------------------------------|
| 校准 | `bash llm_compression/scripts/calib.sh --config_path llm_compression/configs/<model>.yml` |
| GPU 精度评测 | `bash llm_compression/scripts/torch_eval.sh --config_path llm_compression/configs/<model>.yml` |
| HBM 编译 | `bash llm_compression/scripts/compile.sh --config_path llm_compression/configs/<model>.yml` |
| 板端精度评测 | `bash llm_compression/scripts/hbm_rpc_eval.sh --config_path llm_compression/configs/<model>.yml` |
| 量化误差分析 | `bash llm_compression/scripts/quant_analysis.sh --config_path llm_compression/configs/<model>.yml` |

### ⛔ 必须通过 scripts/*.sh 入口执行（禁止直接调用 tools/*.py）

> **即使你已经理解了 shell 脚本的内部实现，也禁止绕过它。** 标准脚本会自动处理 PYTHONPATH、环境变量、CWD 和日志，直接调用 Python 可能触发不可预见的问题（如循环引用、路径错误）。

| 操作 | ✅ 正确（通过 shell 入口） | ❌ 禁止（直接调 Python） |
|------|--------------------------|------------------------|
| 校准 | `bash llm_compression/scripts/calib.sh --config_path <yml>` | `python3 llm_compression/tools/calib.py ...` |
| GPU 评测 | `bash llm_compression/scripts/torch_eval.sh --config_path <yml>` | `python3 llm_compression/tools/torch_eval.py ...` |
| 编译 | `bash llm_compression/scripts/compile.sh --config_path <yml>` | `python3 llm_compression/tools/compile.py ...` |
| 板端评测 | `bash llm_compression/scripts/hbm_rpc_eval.sh --config_path <yml>` | `python3 llm_compression/tools/hbm_rpc_eval.py ...` |
| 量化分析 | `bash llm_compression/scripts/quant_analysis.sh --config_path <yml>` | `python3 llm_compression/tools/quant_analysis.py ...` |

**同时禁止**：
- 自写 shell 包装器（如 `run_eval.sh`）来替代标准脚本
- 自写 Python 包装器调用底层 `tools/*.py`
- 修改标准脚本内容

如果标准脚本不满足需求（如需要额外的 Docker 挂载参数），应在 **`docker run -c` 内调用标准脚本**，而非替换它：

```bash
# ✅ 正确：Docker 内调用标准脚本
docker run --rm --gpus all --shm-size=15g \
  -v "${OE_LLM_DIR}:/open_explorer_llm" \
  -v "${RUN_DIR}:/workspace" \
  --entrypoint /bin/bash ${DOCKER_IMAGE} \
  -c "cd /open_explorer_llm && bash llm_compression/scripts/hbm_rpc_eval.sh --config_path /workspace/config.yml"

# ❌ 禁止：Docker 内直接调 Python
docker run ... -c "python3 llm_compression/tools/hbm_rpc_eval.py --config_path ..."
```

### 标准脚本速查

| 操作 | 标准脚本 | 产出 |
|------|---------|------|
| 校准（float→量化） | `bash llm_compression/scripts/calib.sh --config_path <yml>` | `*_calibration.pth.tar` |
| GPU 精度评测 | `bash llm_compression/scripts/torch_eval.sh --config_path <yml>` | `eval_results/` |
| HBM 编译 | `bash llm_compression/scripts/compile.sh --config_path <yml>` | `*.hbm` + `embed_tokens.bin` |
| 板端精度评测 | `bash llm_compression/scripts/hbm_rpc_eval.sh --config_path <yml>` | `hbm_rpc_eval_results/` |
| 量化误差分析 | `bash llm_compression/scripts/quant_analysis.sh --config_path <yml>` | `quant_analysis_results/` |

### GPU 编译预检（compile.sh 前必检）

2B+ 参数模型的 compile 阶段需要 GPU（HBDK LLVM 后端依赖 CUDA）。执行前**必须**检查：

1. **Docker 模式**：确认 `DOCKER_TYPE=gpu`
2. **测试 GPU**：
   ```bash
   eval "$DOCKER_EXEC_PREFIX 'nvidia-smi'"
   ```
3. **GPU 不可用** → 向用户报告阻塞，**不要尝试在无 GPU 环境编译**

### VLM 已知限制

部分 VLM 模型（如 Qwen3-VL）在校准阶段可能遇到 `tensor_dispatch_wrapper` 动态控制流问题。详见 `vlm_known_limitations.md`。

---

## 标准流水线

```
1. calib.sh      → 校准产出 *_calibration.pth.tar
2. torch_eval.sh  → (可选) GPU 上精度评测
3. compile.sh     → 将校准产物编译为 .hbm
4. hbm_rpc_eval.sh → (可选) 板端精度评测
5. quant_analysis.sh → (可选) 逐层量化误差分析
```

每步通过 YAML config 中的路径字段串联前后步骤的输入输出。

---

## YAML 配置结构

配置文件包含以下主要段落，详细字段说明见 `.horizon/skills/horizon-router/references/llmcompression-operations.md`：

- **model 段**（必填）：`march`、`model_name`、`model_path`、`model_list`、`max_kvcache_len` 等
- **calibration 段**：`dataset_type`、`data_path`、`calib_ckpt_save_path`
- **evaluation 段**：`calib_ckpt_load_path`、`result_path`
- **compile 段**：`calib_ckpt_load_path`、`hbm_save_path`、`core_num`
- **hbm_rpc_eval 段**：`host`、`hbm_load_path`、`remote_environment.HB_DNN_USER_DEFINED_L2M_SIZES`
- **quant_analysis 段**：`baseline_model_load_path`、`analysis_model_load_path`

### 可用配置模板

`configs/` 目录下提供预置模板：`qwen2_5_vl.yml`、`qwen3_vl.yml`、`internvl_1b.yml`、`internvl_2b.yml`、`internvl3_5_1b.yml`

### 模型间配置差异

| 配置项 | Qwen 系列 | InternVL 系列 |
|--------|----------|-------------|
| 视觉组件名 | `visual` | `vision_model` |
| 文本配置键 | `text_config` | `llm_config` |
| 图像尺寸键 | `image_height` + `image_width` | `image_size`（单值） |

---

## 执行环境

### Docker 模式（EXECUTION_MODE=docker）

#### ⛔ Docker 命令预检（每次 docker run 前必检）

执行任何 Docker 命令前，**必须**检查以下 3 项全部到位。缺少任一项 → 命令必定失败：

| # | 检查项 | 缺失后果 | 参数 |
|---|--------|---------|------|
| 1 | GPU 访问 | 无 CUDA，编译/推理报错 | `--gpus all` |
| 2 | 共享内存 | LLM DataLoader 多进程 OOM | `--shm-size=15g` |
| 3 | 目录挂载 | 容器内找不到数据/配置/输出 | `-v ${OE_LLM_DIR}:/open_explorer_llm` + 数据目录 |

> **`DOCKER_EXEC_PREFIX` 陷阱**：`.env.oe-llm-package` 中的 `DOCKER_EXEC_PREFIX` **仅包含 `--gpus all`，不含 `--shm-size` 和 `-v` 挂载。** 直接使用 `$DOCKER_EXEC_PREFIX 'cmd'` 会因缺少挂载和共享内存而失败。**必须**使用下方完整模板替代。

**完整 Docker 命令模板**：

```bash
docker run --rm --gpus all \
  --shm-size=15g \
  -v "${OE_LLM_DIR}:/open_explorer_llm" \
  -v "${DATA_DIR}:/data" \
  -v "${RUN_DIR}:/workspace" \
  --entrypoint /bin/bash \
  ${DOCKER_IMAGE} \
  -c "cd /open_explorer_llm && bash llm_compression/scripts/calib.sh --config_path /workspace/config.yml"
```

**⛔ Docker 挂载约束**：

1. **禁止嵌套挂载**：不能在已挂载的目录上再叠加文件级 bind mount。以下写法会导致 `OCI runtime create failed: not a directory`：
   ```bash
   # ❌ 错误：先挂目录，再在子路径上叠加挂文件
   -v ${OE_LLM_DIR}:/open_explorer_llm \
   -v /tmp/my_config.yml:/open_explorer_llm/llm_compression/configs/qwen3_vl.yml
   ```
   **正确做法**：将修改后的配置文件放到独立的工作目录，单独挂载该目录：
   ```bash
   # ✅ 正确：配置文件和输出放在独立挂载点
   -v ${OE_LLM_DIR}:/open_explorer_llm \
   -v ${RUN_DIR}:/workspace \
   # 容器内引用 /workspace/config.yml
   ```

2. **必须加 `--shm-size=15g`**：LLM 模型的 DataLoader 多进程共享内存需求大，默认 64MB 会直接 OOM。

3. **YAML 配置中的路径必须用容器内路径**：`model_path`、`data_path`、`calib_ckpt_save_path` 等字段必须写 Docker 内的挂载路径（如 `/open_explorer_llm/...` 或 `/workspace/...`），不是宿主机路径。

### Local 模式（EXECUTION_MODE=local）

```bash
source .horizon/venv-llm/bin/activate
cd $OE_LLM_DIR    # 项目根目录，不要 cd 进 llm_compression/
bash llm_compression/scripts/calib.sh --config_path llm_compression/configs/qwen3_vl.yml
```

---

## 注意事项

- `model_list` 中的部件名必须与 `MODEL_REGISTRY` 中注册的一致
- `max_lm_input_len` 必须严格小于 `max_kvcache_len`
- `core_num` 必须与板端实际 BPU 核心数匹配
- `hbm_rpc_eval` 的 `HB_DNN_USER_DEFINED_L2M_SIZES` 必须与 `core_num` 匹配：单核 `24:0:0:0`，四核 `6:6:6:6`
- 校准数据集路径必须是真实路径，不能使用随机数据

---

## 参考资料

详细字段说明、完整示例配置、常见错误处理见：
- `.horizon/skills/horizon-router/references/llmcompression-operations.md`
- VLM 已知限制：`.horizon/skills/llm/llm_compression/llmcompression-add-model/vlm_known_limitations.md`
