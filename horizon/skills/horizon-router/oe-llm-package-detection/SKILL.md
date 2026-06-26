---
name: oe-llm-package-detection
description: OE-LLM 包环境检测 Skill。当任务涉及 LLM 量化、LLM 压缩、LLM 编译、板端 LLM 推理等 LLM 工具链操作，且 .horizon/.env.oe-llm-package 不存在时触发。自动完成 OE-LLM 包路径定位、版本采集、本地环境匹配检查、GPU Docker 判定，并将结果写入 .env 文件。
---

# OE-LLM 包环境检测

## 执行方式

> **本 Skill 应通过 subagent 执行。** 主 agent 在前置检查中发现 `.env.oe-llm-package` 缺失或不完整时，应将本文件的完整内容作为 subagent prompt 派发执行。subagent 完成后汇报写入结果（OE-LLM 路径、版本、执行模式），主 agent 读取 `.env.oe-llm-package` 继续后续流程。

## 目标

检测 OE-LLM 包路径、版本及本地环境匹配情况，写入 `.horizon/.env.oe-llm-package`，供后续所有 LLM 工具链任务直接使用。

## 触发条件

任何涉及 LLM 量化、LLM 压缩、LLM 编译、板端 LLM 推理、LLM 精度评估的任务进入 horizon-router 前，如果 `.horizon/.env.oe-llm-package` 不存在，顶层 Skill 会**中断任务并提示用户**：

> 未检测到 OE-LLM 包环境配置（`.horizon/.env.oe-llm-package`）。请提供 OE-LLM 包路径，或回复"跳过"暂不配置。

- **用户提供路径** → 进入本检测流程
- **用户回复"跳过"** → 记录跳过（仅当次对话有效，下次仍会提示），继续后续任务

**LLM 任务的识别关键词**：LLM、大语言模型、VLM、视觉语言模型、llm_compression、AWQ、GPTQ、RTN、SmoothQuant、LLM 量化、LLM 编译、LLM 推理、oellm、InternVL、Qwen-VL、LLaMA 等。

## 检测流程

### 1. 检查 `.horizon/.env.oe-llm-package` 是否存在

- 文件存在且内容完整（包含 `OE_LLM_DIR`、`OE_LLM_VERSION`、`EXECUTION_MODE` 等字段）→ 直接读取，跳过后续步骤
- 文件不存在或不完整 → 进入步骤 2

### 2. 定位 OE-LLM 包路径

按优先级查找：

1. **环境变量**：`OE_LLM_DIR`、`OPEN_EXPLORER_LLM_DIR`、`HORIZON_OE_LLM_DIR`
2. **项目配置文件**：`.env`、`.horizon/oe-llm.env`、`CLAUDE.md` 中声明的路径
3. **常见路径探测**：`/open_explorer_llm`、`~/open_explorer_llm`、`/opt/openexplorer_llm`，以及 `/mnt/oe-cli-test/` 下以 `horizon_j6_open_explorer_llm` 开头的目录
4. **以上都没有** → 询问用户 OE-LLM 包路径

找到路径后，验证目录中存在 OE-LLM 包的标志性文件（以下至少两个）：

- `run_docker.sh`
- `llm_compression/` 目录
- `runtime/` 目录

注意：OE-LLM 包**没有**标准 OE 包的 `samples/`、`docs/`、`toolchain/` 目录，也没有 `package/host/ai_toolchain/` 子目录。

### 3. 采集 OE-LLM 版本信息

从 OE-LLM 包目录中提取以下信息：

**OE-LLM 包整体版本**：
- 从目录名提取（如 `horizon_j6_open_explorer_llm_v2.0.0_rc3-py310_20260615` → `v2.0.0_rc3`）
- 检查 `README-CN`、`README-EN` 中的版本信息
- 以上都无法确定时询问用户

**组件版本**（从 `llm_compression/deps_version.conf` 解析）：

| 字段 | 含义 | 示例值 |
|------|------|--------|
| `HBDK_VERSION` | HBDK4 编译器版本 | 4.11.2 |
| `HORIZON_PLUGIN_PYTORCH_VERSION` | PyTorch 量化插件版本 | 3.3.4 |
| `HBM_INFER_VERSION` | HBM 推理引擎版本 | 3.15.3 |
| `LLM_COMPRESSION_VERSION` | LLM 压缩工具版本 | 2.0.2 |
| `TORCH_VERSION` | 配套 PyTorch 版本（含 CUDA） | 2.8.0+cu128 |
| `PYTHON_VERSION` | 配套 Python 版本 | py310 |

同时通过 `pip show` 检查已安装版本，并记录 OE-LLM 包内 whl 文件名中的版本：

| 组件 | pip 包名 | 说明 |
|------|----------|------|
| `hbdk4_compiler` | `hbdk4-compiler` | BPU 编译器 |
| `hbdk4_march` | `hbdk4-march` | BPU 架构定义 |
| `hbm_infer` | `hbm-infer` | HBM 推理引擎 |
| `horizon_plugin_profiler` | `horizon-plugin-profiler` | 性能分析插件 |
| `horizon_plugin_pytorch` | `horizon-plugin-pytorch` | PyTorch 量化插件（QAT） |

**Docker 信息**：
- 从 `run_docker.sh` 内容提取 Docker 镜像名称和版本号：
  - GPU（仅 GPU 镜像）：`openexplorer/ai_toolchain_ubuntu_22_llm_j6_gpu:{version}`
- 从 `run_docker.sh` 提取容器内挂载路径：`/open_explorer_llm`

### 4. 本地环境匹配检查

在当前环境中逐项检测：

1. **Python 版本**：`python3 --version`，要求 3.10 或 3.11
2. **pip 组件**：对每个组件执行 `pip show <包名>`，记录：
   - 是否安装
   - 版本号是否与 OE-LLM 包声明一致
3. **Python 模块导入检查**：
   - `import hbdk4`
   - `import hbm_infer`

根据检查结果判定执行模式：

- **全部匹配** → `EXECUTION_MODE=local`
- **部分缺失或版本不匹配** → `EXECUTION_MODE=docker`，记录缺失项

### 5. Docker 模式下的 GPU 判定

OE-LLM 包**仅提供 GPU Docker 镜像**（`openexplorer/ai_toolchain_ubuntu_22_llm_j6_gpu`），无 CPU 镜像。

当 `EXECUTION_MODE=docker` 时：

1. **启动 GPU Docker 容器并测试 GPU 可用性**（注意 GPU 镜像 Entrypoint 为 `/bin/bash`，必须用 `--entrypoint` + `-c` 传命令）：
   ```bash
   docker run --rm --gpus all --entrypoint /bin/bash \
     openexplorer/ai_toolchain_ubuntu_22_llm_j6_gpu:{version} -c "nvidia-smi"
   ```

2. **检查 nvidia-smi 输出**：
   - 能正常输出 GPU 信息 → `DOCKER_TYPE=gpu`
   - 报错或无 GPU 设备 → 提示用户 OE-LLM 包需要 GPU 环境，无法使用 CPU Docker

3. **采集 GPU 详细信息**（仅当 GPU 可用时）：
   ```bash
   docker run --rm --gpus all --entrypoint /bin/bash \
     openexplorer/ai_toolchain_ubuntu_22_llm_j6_gpu:{version} -c "python3 -c \"
   import torch, json
   info = {'cuda_version': torch.version.cuda, 'gpu_count': torch.cuda.device_count(), 'gpus': []}
   for i in range(torch.cuda.device_count()):
       p = torch.cuda.get_device_properties(i)
       info['gpus'].append({'index': i, 'name': p.name, 'memory_gb': round(p.total_memory/1024**3,1), 'compute_capability': f'{p.major}.{p.minor}'}  )
   print(json.dumps(info))
   \""
   ```
   将返回的 JSON 写入 `GPU_INFO` 字段。

4. **向用户提示判定结果**：
   - GPU 可用时：`检测到 N 张 <GPU型号>，使用 GPU Docker 镜像`
   - GPU 不可用时：`未检测到可用 GPU，OE-LLM 包需要 GPU 环境才能运行`

### 6. 写入 `.horizon/.env.oe-llm-package`

```bash
# OE-LLM 包环境信息（自动生成）
# 检测时间：<timestamp>

# === OE-LLM 包基本信息 ===
OE_LLM_DIR=<OE-LLM 包路径>
OE_LLM_VERSION=<OE-LLM 版本号，如 v2.0.0_rc3>

# === 组件版本 ===
HBDK_COMPILER_VERSION=<版本>
HBDK_MARCH_VERSION=<版本>
HBM_INFER_VERSION=<版本>
HORIZON_PLUGIN_PROFILER_VERSION=<版本>
HORIZON_PLUGIN_PYTORCH_VERSION=<版本>
LLM_COMPRESSION_VERSION=<版本>

# === 配套环境 ===
TORCH_VERSION=<版本，如 2.8.0+cu128>
PYTHON_VERSION=<版本，如 py310>

# === 执行模式 ===
EXECUTION_MODE=<local | docker>

# --- 以下仅在 EXECUTION_MODE=docker 时填写 ---
DOCKER_TYPE=gpu
DOCKER_IMAGE=openexplorer/ai_toolchain_ubuntu_22_llm_j6_gpu:<version>
DOCKER_RUN_CMD=bash <OE_LLM_DIR>/run_docker.sh <dataset_path>
DOCKER_EXEC_PREFIX=docker run --rm --gpus all --entrypoint /bin/bash <DOCKER_IMAGE> -c
MISSING_COMPONENTS=<缺失或不匹配的组件列表，逗号分隔>

# --- 以下仅在 DOCKER_TYPE=gpu 时填写 ---
GPU_INFO=<JSON: {"cuda_version":"...","gpu_count":N,"gpus":[{"index":0,"name":"...","memory_gb":...,"compute_capability":"..."},...]}>
```

> **`DOCKER_EXEC_PREFIX` 说明**：GPU 镜像的 `Entrypoint` 为 `['/bin/bash']`，非交互式执行命令时如果直接 `docker run image cmd`，实际会执行 `/bin/bash cmd`（把 cmd 当脚本文件名），报 `cannot execute binary file`。必须用 `--entrypoint /bin/bash image -c "cmd"` 的方式。`DOCKER_EXEC_PREFIX` 已包含正确的 entrypoint 处理，子 Skill 直接拼接即可：`$DOCKER_EXEC_PREFIX "python3 ..."`。

- 后续任务直接读取此文件，无需重复检测
- 如果 `EXECUTION_MODE=local`，不填写 Docker 相关字段

## 后续任务的使用方式

顶层 Skill 路由到子 Skill 后，子 Skill 在执行 CLI 命令前读取 `EXECUTION_MODE`：

- **`local`** → 先激活 venv，再直接执行：
  ```bash
  source .horizon/venv-llm/bin/activate
  cd $OE_LLM_DIR/llm_compression && bash scripts/calib.sh ...
  ```
- **`docker`** → 读取 `DOCKER_EXEC_PREFIX`，拼接 CLI 命令：
  ```bash
  # 非交互式单命令（推荐，直接拼 DOCKER_EXEC_PREFIX）
  eval "$DOCKER_EXEC_PREFIX 'cd /open_explorer_llm/llm_compression && bash scripts/calib.sh ...'"

  # 交互式（通过 run_docker.sh 启动 shell）
  bash <OE_LLM_DIR>/run_docker.sh <dataset_path>

  # 手动 docker run
  docker run -it --rm \
    --gpus all \
    --shm-size="15g" \
    -v <OE_LLM_DIR>:/open_explorer_llm \
    -v <dataset_path>:/jfs-public \
    <DOCKER_IMAGE>
  ```

## OE-LLM 包与标准 OE 包的区别

| 方面 | 标准 OE 包 | OE-LLM 包 |
|------|-----------|-----------|
| whl 目录 | `package/host/ai_toolchain/` | `package/host/`（无子目录） |
| 标志性目录 | `samples/`、`docs/`、`toolchain/` | `llm_compression/`、`runtime/` |
| 版本来源 | `version.txt`、`VERSION`、`release_notes.md` | `llm_compression/deps_version.conf` |
| 核心组件 | horizon_tc_ui, hmct, horizon_plugin_pytorch, hbdk4_compiler | hbdk4_compiler, hbm_infer, horizon_plugin_profiler, horizon_plugin_pytorch |
| CLI 工具 | hb_compile, hb_model_info, hmct-debugger | llm_compression/scripts/ 下的脚本 |
| Docker 镜像 | ai_toolchain_ubuntu_22_j6_gpu/cpu | ai_toolchain_ubuntu_22_llm_j6_gpu（仅 GPU） |
| Docker 挂载 | `/open_explorer` | `/open_explorer_llm` |
| 交叉编译器 | 无 | `aarch64-linux-hb-gcc` .deb 包 |

## 注意事项

- OE-LLM 包版本决定了各组件的兼容版本，混用不同版本可能导致量化或编译失败
- OE-LLM 包与标准 OE 包的组件版本可能不同，不可混用
- 如果用户更换了 OE-LLM 包或升级了组件，需要删除 `.horizon/.env.oe-llm-package` 重新检测
- Docker 模式下，OE-LLM 包路径会自动挂载到容器内的 `/open_explorer_llm`，命令中应使用容器内路径
- Docker 模式下需要 `--shm-size="15g"` 参数（共享内存），否则 LLM 推理可能 OOM
