---
name: oe-package-detection
description: OE 包环境检测 Skill。当任务涉及量化、编译、部署等工具链操作，且 .horizon/.env.oe-package 不存在时触发。自动完成 OE 包路径定位、版本采集、本地环境匹配检查、GPU/CPU Docker 判定，并将结果写入 .env 文件。
---

# OE 包环境检测

## 执行方式

> **本 Skill 应通过 subagent 执行。** 主 agent 在前置检查中发现 `.env.oe-package` 缺失或不完整时，应将本文件的完整内容作为 subagent prompt 派发执行。subagent 完成后汇报写入结果（OE 路径、版本、执行模式），主 agent 读取 `.env.oe-package` 继续后续流程。

## 目标

检测 OE 包路径、版本及本地环境匹配情况，写入 `.horizon/.env.oe-package`，供后续所有工具链任务直接使用。

## 触发条件

任何涉及量化、编译、部署、板端推理、性能/精度评估的任务进入 horizon-router 前，如果 `.horizon/.env.oe-package` 不存在，顶层 Skill 会**中断任务并提示用户**：

> 未检测到 OE 包环境配置（`.horizon/.env.oe-package`）。请提供 OE 包路径，或回复"跳过"暂不配置。

- **用户提供路径** → 进入本检测流程
- **用户回复"跳过"** → 记录跳过（仅当次对话有效，下次仍会提示），继续后续任务

## 检测流程

### 1. 检查 `.horizon/.env.oe-package` 是否存在

- 文件存在且内容完整（包含 `OE_DIR`、`OE_VERSION`、`EXECUTION_MODE` 等字段）→ 直接读取，跳过后续步骤
- 文件不存在或不完整 → 进入步骤 2

### 2. 定位 OE 包路径

按优先级查找：

1. **环境变量**：`OE_DIR`、`OPEN_EXPLORER_DIR`、`HORIZON_OE_DIR`
2. **项目配置文件**：`.env`、`.horizon/oe.env`、`CLAUDE.md` 中声明的路径
3. **常见路径探测**：`/open_explorer`、`~/open_explorer`、`/opt/openexplorer`
4. **以上都没有** → 询问用户 OE 包路径

找到路径后，验证目录中存在 OE 包的标志性文件（如 `run_docker.sh`、`samples/`、`docs/`、`toolchain/` 等至少两个），否则提示用户确认路径是否正确。

### 3. 采集 OE 版本信息

从 OE 包目录中提取以下信息：

**OE 包整体版本**：
- 检查 `version.txt`、`VERSION`、`release_notes.md` 或 `release_notes.txt`
- 从文件名推断（如 `OpenExplorer_v3.9.0_rc4`）
- 以上都无法确定时询问用户

**各组件版本**（通过 `pip show` 检查已安装版本，同时记录 OE 包内 whl 文件名中的版本）：

| 组件 | pip 包名 | 说明 |
|------|----------|------|
| `horizon_tc_ui` | `horizon-tc-ui` | 模型集成工具 |
| `hmct` | `hmct` | 模型转换/量化工具 |
| `horizon_plugin_pytorch` | `horizon-plugin-pytorch` | PyTorch 量化插件（QAT） |
| `hbdk4_compiler` | `hbdk4-compiler` | 编译器 |

**Docker 信息**：
- 检查 `run_docker.sh` 是否存在
- 从 `run_docker.sh` 内容或 OE 版本推断 Docker 镜像名称：
  - CPU：`openexplorer/ai_toolchain_ubuntu_22_j6_cpu:{version}`
  - GPU：`openexplorer/ai_toolchain_ubuntu_22_j6_gpu:{version}`

### 4. 本地环境匹配检查

在当前环境中逐项检测：

1. **Python 版本**：`python3 --version`，要求 >= 3.8
2. **pip 组件**：对每个组件执行 `pip show <包名>`，记录：
   - 是否安装
   - 版本号是否与 OE 包声明一致
3. **CLI 工具可用性**：检查以下命令是否可执行：
   - `hb_compile --version`（或 `which hb_compile`）
   - `hb_model_info --version`（或 `which hb_model_info`）
   - `hmct-debugger --version`（或 `which hmct-debugger`）

根据检查结果判定执行模式：

- **全部匹配** → `EXECUTION_MODE=local`
- **部分缺失或版本不匹配** → `EXECUTION_MODE=docker`，记录缺失项

### 5. Docker 模式下的 GPU/CPU 判定

当 `EXECUTION_MODE=docker` 时，需要确定使用 GPU 还是 CPU 镜像：

1. **启动 GPU Docker 容器并测试 GPU 可用性**（注意 GPU 镜像 Entrypoint 为 `/bin/bash`，必须用 `--entrypoint` + `-c` 传命令）：
   ```bash
   docker run --rm --gpus all --entrypoint /bin/bash \
     openexplorer/ai_toolchain_ubuntu_22_j6_gpu:{version} -c "nvidia-smi"
   ```

2. **检查 nvidia-smi 输出**：
   - 能正常输出 GPU 信息 → `DOCKER_TYPE=gpu`
   - 报错或无 GPU 设备 → `DOCKER_TYPE=cpu`

3. **采集 GPU 详细信息**（仅当 GPU 可用时）：
   ```bash
   docker run --rm --gpus all --entrypoint /bin/bash \
     openexplorer/ai_toolchain_ubuntu_22_j6_gpu:{version} -c "python3 -c \"
   import torch, json
   info = {'cuda_version': torch.version.cuda, 'gpu_count': torch.cuda.device_count(), 'gpus': []}
   for i in range(torch.cuda.device_count()):
       p = torch.cuda.get_device_properties(i)
       info['gpus'].append({'index': i, 'name': p.name, 'memory_gb': round(p.total_memory/1024**3,1), 'compute_capability': f'{p.major}.{p.minor}'})
   print(json.dumps(info))
   \""
   ```
   将返回的 JSON 写入 `GPU_INFO` 字段。如果 PyTorch 无法识别 GPU（`cuda.is_available()=False`），则 `GPU_INFO` 设为空。

4. **向用户提示判定结果**：
   - GPU 可用时：`检测到 N 张 <GPU型号>，默认使用 GPU Docker 镜像`
   - GPU 不可用时：`未检测到可用 GPU，将使用 CPU Docker 镜像。如需 GPU 加速，请检查 NVIDIA 驱动和 Docker GPU 支持`

### 6. 写入 `.horizon/.env.oe-package`

```bash
# OE 包环境信息（自动生成）
# 检测时间：<timestamp>

# === OE 包基本信息 ===
OE_DIR=<OE 包路径>
OE_VERSION=<OE 版本号，如 3.9.0_rc4>

# === 组件版本 ===
HORIZON_TC_UI_VERSION=<版本>
HMCT_VERSION=<版本>
HORIZON_PLUGIN_PYTORCH_VERSION=<版本>
HBDK_COMPILER_VERSION=<版本>

# === 执行模式 ===
EXECUTION_MODE=<local | docker>

# --- 以下仅在 EXECUTION_MODE=docker 时填写 ---
DOCKER_TYPE=<gpu | cpu>
DOCKER_IMAGE=openexplorer/ai_toolchain_ubuntu_22_j6_<gpu|cpu>:<version>
DOCKER_RUN_CMD=bash <OE_DIR>/run_docker.sh ./data
DOCKER_EXEC_PREFIX=docker run --rm [--gpus all] --entrypoint /bin/bash <DOCKER_IMAGE> -c
MISSING_COMPONENTS=<缺失或不匹配的组件列表，逗号分隔>

# --- 以下仅在 DOCKER_TYPE=gpu 时填写 ---
GPU_INFO=<JSON: {"cuda_version":"...","gpu_count":N,"gpus":[{"index":0,"name":"...","memory_gb":...,"compute_capability":"..."},...]}>
```

> **`DOCKER_EXEC_PREFIX` 说明**：GPU 镜像的 `Entrypoint` 为 `['/bin/bash']`，非交互式执行命令时如果直接 `docker run image cmd`，实际会执行 `/bin/bash cmd`（把 cmd 当脚本文件名），报 `cannot execute binary file`。必须用 `--entrypoint /bin/bash image -c "cmd"` 的方式。`DOCKER_EXEC_PREFIX` 已包含正确的 entrypoint 处理，子 Skill 直接拼接即可：`$DOCKER_EXEC_PREFIX "hb_compile ..."`。CPU 镜像无此问题，但统一使用 `DOCKER_EXEC_PREFIX` 可避免遗漏。

- 后续任务直接读取此文件，无需重复检测
- 如果 `EXECUTION_MODE=local`，不填写 Docker 相关字段

## 后续任务的使用方式

顶层 Skill 路由到子 Skill 后，子 Skill 在执行 CLI 命令前读取 `EXECUTION_MODE`：

- **`local`** → 直接在当前环境执行 CLI 命令
- **`docker`** → 读取 `DOCKER_EXEC_PREFIX`，拼接 CLI 命令：
  ```bash
  # 非交互式单命令（推荐，直接拼 DOCKER_EXEC_PREFIX）
  eval "$DOCKER_EXEC_PREFIX 'hb_compile -m model.onnx -o output.hbm'"

  # 交互式（通过 run_docker.sh 启动 shell）
  bash <OE_DIR>/run_docker.sh ./data

  # 手动 docker run
  docker run -it --rm \
    -v <OE_DIR>:/open_explorer \
    -v ./dataset:/data/horizon_j6/data \
    <DOCKER_IMAGE>
  ```

## 注意事项

- OE 包版本决定了各组件的兼容版本，混用不同版本可能导致量化或编译失败
- 如果用户更换了 OE 包或升级了组件，需要删除 `.horizon/.env.oe-package` 重新检测
- Docker 模式下，OE 包路径会自动挂载到容器内的 `/open_explorer`，命令中应使用容器内路径
