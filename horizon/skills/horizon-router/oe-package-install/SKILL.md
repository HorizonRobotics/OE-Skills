---
name: oe-package-install
description: OE 包本地安装 Skill。在 oe-package-detection 完成后触发，询问用户是否本地安装。若用户同意，则检测本地 Python / CUDA / PyTorch 版本，匹配 OE 包内 whl，创建 venv 全量安装，更新 .env 为 EXECUTION_MODE=local。
---

# OE 包本地安装

## 执行方式

> **本 Skill 应通过 subagent 执行。** 主 agent 在用户确认本地安装后，应将本文件的完整内容作为 subagent prompt 派发执行。subagent 负责环境检测、venv 创建、组件安装和验证，完成后汇报安装结果，主 agent 读取更新后的 `.env.oe-package` 继续后续流程。

## 目标

在用户环境中创建 Python venv，将 OE 包内的所有组件 whl 安装到 venv 中，使后续工具链命令可以本地执行（无需 Docker）。

## 触发条件

`oe-package-detection` 完成后（`.horizon/.env.oe-package` 已生成），向用户询问是否本地安装：

- **用户选择本地安装** → 进入本 Skill
- **用户选择不安装** → 维持 `EXECUTION_MODE=docker`，继续后续任务

## 安装流程

### 1. 读取 OE 包信息

从 `.horizon/.env.oe-package` 读取 `OE_DIR`，扫描 `<OE_DIR>/package/host/ai_toolchain/` 下所有 `.whl` 文件。

### 2. 检测本地环境

逐项采集：

| 检测项 | 命令 | 要求 |
|--------|------|------|
| Python 版本 | `python3 --version` | 必须为 **3.10** 或 **3.11** |
| CUDA 版本 | `nvidia-smi`（右上角）或 `nvcc --version` | 必须为 11.8 / 12.6 / 12.8 之一 |
| PyTorch 版本 | `python3 -c "import torch; print(torch.__version__, torch.version.cuda)"` | 必须与 OE 包提供的组合匹配 |

### 3. 版本匹配

OE 包提供的版本组合由 `horizon_plugin_pytorch` 的 wheel 文件名决定硬性约束：

**匹配规则**：

1. 扫描 `<OE_DIR>/package/host/ai_toolchain/` 下所有 `horizon_plugin_pytorch-*.whl` 文件名
2. 从文件名提取 CUDA 版本（`cuXXX`）、PyTorch 版本（`torchXXX`）、Python 版本（`cpXXX`）
3. 对比本地环境的 CUDA / PyTorch / Python 版本，选择匹配的 wheel
4. 任一不匹配 → **终止**，输出当前环境和所需版本的对比表

**匹配失败时的提示模板**：

```
当前环境不满足 OE 包要求：

| 项目 | 当前版本 | 需要版本 |
|------|---------|---------|
| Python | 3.x | 3.10 或 3.11 |
| CUDA | x.x | 11.8 / 12.6 / 12.8 |
| PyTorch | x.x.x | 2.3 / 2.6 / 2.8（需与 CUDA 匹配） |

请先安装对应版本后重试。
```

### 4. 创建 venv 并安装

运行自动化脚本完成 venv 创建、组件安装、验证和 `.env.oe-package` 更新：

```bash
# 从 .horizon/.env.oe-package 读取 OE_DIR
OE_DIR=$(grep '^OE_DIR=' .horizon/.env.oe-package | cut -d= -f2)
bash .horizon/skills/horizon-router/oe-package-install/install.sh "$OE_DIR"
```

脚本内置的固定规则（已固化在 `install.sh` 中，无需手动处理）：

1. **`--without-pip --system-site-packages`** 创建 venv，继承系统 PyTorch，避免 ensurepip 不可用
2. **`python3 -m pip`** 而非裸 `pip`，避免 `--without-pip` venv 中 pip 路径回退到系统
3. **`constraints.txt` 锁 torch 版本** + **`--no-deps`** 安装 hmct/hmct_gpu，防止依赖解析拉入新版 torch
4. **`--no-deps`** 安装 horizon_torch_samples，避免 pycocotools 编译失败

> **安装失败处理**：脚本以非零退出码终止 → 查看输出定位失败组件，向用户展示报错信息并建议回退到 Docker 模式。

### 5. 验证安装

> 脚本（Step 4）已内置验证，安装成功即表示所有组件导入和 CLI 工具可用。如需手动验证：

```bash
source .horizon/venv/bin/activate

# 验证各组件
python3 -c "import horizon_tc_ui; print('horizon_tc_ui OK')"
python3 -c "import hmct; print('hmct OK')"
python3 -c "import horizon_plugin_pytorch; print('horizon_plugin_pytorch OK')"
python3 -c "import hbdk4; print('hbdk4 (compiler) OK')"
python3 -c "import hbdnn; print('hbdnn OK')"
python3 -c "import hbm_infer; print('hbm_infer OK')"

# 验证 CLI 工具
which hb_compile
which hb_model_info
which hmct-debugger
```

### 6. 更新 `.horizon/.env.oe-package`

> 脚本已自动更新，无需手动操作。如需手动修改：

```bash
# === 执行模式 ===
EXECUTION_MODE=local

# === venv 路径 ===
VENV_DIR=.horizon/venv
VENV_ACTIVATE_CMD=source .horizon/venv/bin/activate

# --- 以下字段在 local 模式下清空 ---
# DOCKER_TYPE、DOCKER_IMAGE、DOCKER_RUN_CMD、DOCKER_EXEC_PREFIX、MISSING_COMPONENTS 均删除或置空
```

> **注意**：`DOCKER_TYPE=gpu` 时的 `GPU_INFO` 保留不删，因为本地模式也可能用到 GPU 信息。

## 后续任务的使用方式

子 Skill 执行 CLI 命令前读取 `EXECUTION_MODE`：

- **`local`** → 先激活 venv，再直接执行：
  ```bash
  source .horizon/venv/bin/activate
  hb_compile -m model.onnx -o output.hbm
  ```
- **`docker`** → 按 `oe-package-detection` 中的 Docker 方式执行

## 卸载 / 重装

- **卸载**：`rm -rf .horizon/venv`，删除 `.env.oe-package` 中的 `VENV_DIR` 和 `VENV_ACTIVATE_CMD`，将 `EXECUTION_MODE` 改回 `docker`
- **重装**：删除 `.horizon/venv` 后重新执行本 Skill

## 常见问题与解决方案

### 1. `python3 -m venv` 失败：ensurepip 不可用

**现象**：
```
The virtual environment was not created successfully because ensurepip is not available.
apt install python3.10-venv
```

**原因**：系统缺少 `python3.10-venv` 包，且可能无 sudo 权限无法安装。

**解决**：脚本已用 `--without-pip` 规避此问题。如手动操作：
```bash
python3 -m venv --without-pip --system-site-packages .horizon/venv
source .horizon/venv/bin/activate
/bin/pip3 install --target .horizon/venv/lib/python3.10/site-packages/ pip
```

### 2. PyTorch 版本冲突：hmct 拉入不兼容的 torch 版本

**现象**：
```
RuntimeError: Please install torch == <required_version>, but get <wrong_version>
```

**原因**：`hmct` 的依赖声明包含 `torch`，pip 会自动安装最新版。而 `horizon_plugin_pytorch` 严格要求特定版本的 torch（通过 wheel 文件名中的 `torchXXX` 标识）。

**解决**（脚本已内置三层防护）：
1. **`--system-site-packages`**：创建 venv 时继承系统已安装的 torch
2. **约束文件**：`constraints.txt` 锁定 torch 版本，安装时加 `-c "$CONSTRAINT"`
3. **`--no-deps`**：对 `hmct` 和 `hmct_gpu` 跳过依赖解析

> **注意**：带 CUDA local version label 的 torch（如 `2.8.0+cu128`）通常只存在于 PyTorch 官方源，内部 PyPI 只有标准版。因此不能依赖 pip 重新下载，必须通过 `--system-site-packages` 继承系统已安装版本。

### 3. `hbdk4_compiler` 模块名错误

**现象**：`import hbdk4_compiler` 报 `ModuleNotFoundError`。

**原因**：pip 包名是 `hbdk4_compiler`，但 Python 导入名是 `hbdk4`（实际模块路径为 `hbdk4.compiler`）。

**正确用法**：
```python
import hbdk4               # OK
import hbdk4.compiler       # OK
from hbdk4 import compiler # OK
```

## 注意事项

- venv 内的组件版本与 Docker 镜像内完全一致（均来自同一 OE 包的 whl）
- 如果用户升级了系统 Python、CUDA 或 PyTorch，需要删除 `.horizon/venv` 和 `.horizon/.env.oe-package` 重新检测和安装
- `hmct_gpu` 仅在 CUDA 12.8 环境下可用；CUDA 11.8 / 12.6 环境只安装 CPU 版 `hmct`
- `horizon_plugin_pytorch` 的版本与 PyTorch 强绑定，不可混用
