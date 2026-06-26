#!/bin/bash
# OE-LLM 包本地安装脚本
# 用法: bash .horizon/skills/horizon-router/oe-llm-package-install/install.sh <OE_LLM_DIR>
# 示例: bash .horizon/skills/horizon-router/oe-llm-package-install/install.sh /mnt/oe-cli-test/horizon_j6_open_explorer_llm_v2.0.0_rc3-py310_20260615
set -euo pipefail

# ============================================================
# 固定规则（勿改）
# 1. 始终用 python3 -m pip，不用裸 pip（避免 --without-pip venv 路径回退）
# 2. 必须 --system-site-packages 继承系统 torch
# 3. 用 constraints.txt 锁 torch 版本
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
VENV_DIR="$WORKSPACE_ROOT/.horizon/venv-llm"
ENV_FILE="$WORKSPACE_ROOT/.horizon/.env.oe-llm-package"

OE_LLM_DIR="${1:?用法: bash install.sh <OE_LLM_DIR>}"
WHL_DIR="$OE_LLM_DIR/package/host"

if [ ! -d "$WHL_DIR" ]; then
    echo "✗ 找不到 wheel 目录: $WHL_DIR"
    exit 1
fi

# ============================================================
# Step 1: 环境检测
# ============================================================
echo "=============================="
echo "  OE-LLM 包本地安装"
echo "=============================="
echo ""
echo "=== 环境检测 ==="

PYTHON_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_FULL=$(python3 --version | awk '{print $2}')
echo "Python: $PYTHON_FULL"
if [[ "$PYTHON_VER" != "3.10" && "$PYTHON_VER" != "3.11" ]]; then
    echo "✗ Python 版本必须为 3.10 或 3.11，当前: $PYTHON_VER"
    exit 1
fi
CP="cp${PYTHON_VER//./}"
echo "  → tag: $CP ✓"

CUDA_VER=""
if command -v nvidia-smi &>/dev/null; then
    CUDA_VER=$(nvidia-smi | grep "CUDA Version" | grep -oP 'CUDA Version:\s*\K[\d.]+')
    echo "CUDA: $CUDA_VER"
    echo "  → ✓"
else
    echo "CUDA: nvidia-smi 不可用，跳过版本检测"
fi

TORCH_VER=""
TORCH_CUDA=""
if python3 -c "import torch" 2>/dev/null; then
    TORCH_VER=$(python3 -c "import torch; print(torch.__version__)")
    TORCH_CUDA=$(python3 -c "import torch; print(torch.version.cuda)")
    echo "PyTorch: $TORCH_VER (CUDA: $TORCH_CUDA)"
    echo "  → ✓"
else
    echo "PyTorch: 未安装"
    echo "✗ 系统 PyTorch 未安装，无法创建 local 环境"
    exit 1
fi

# 从 torch 版本提取约束值（去掉 +cuXXX 后缀）
TORCH_CONSTRAINT=$(echo "$TORCH_VER" | sed 's/+.*//')

# ============================================================
# Step 2: 创建 venv
# ============================================================
echo ""
echo "=== 创建 venv ==="

if [ -d "$VENV_DIR" ]; then
    echo "venv 已存在，删除重建: $VENV_DIR"
    rm -rf "$VENV_DIR"
fi

# --without-pip: 避免 ensurepip 不可用时失败
# --system-site-packages: 继承系统 torch
python3 -m venv --without-pip --system-site-packages "$VENV_DIR"
echo "  venv 创建成功 (--without-pip --system-site-packages)"

# 激活
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# 验证继承的 torch
INHERITED_TORCH=$(python3 -c "import torch; print(torch.__version__)" 2>/dev/null || echo "MISSING")
if [ "$INHERITED_TORCH" != "$TORCH_VER" ]; then
    echo "✗ venv 未正确继承系统 torch (期望 $TORCH_VER，实际 $INHERITED_TORCH)"
    exit 1
fi
echo "  torch 继承验证: $INHERITED_TORCH ✓"

# 安装 pip 到 venv（用系统 pip3 装到 venv site-packages）
SYSTEM_PIP=""
for p in /bin/pip3 /usr/bin/pip3 /usr/local/bin/pip3; do
    if [ -x "$p" ]; then SYSTEM_PIP="$p"; break; fi
done

if [ -n "$SYSTEM_PIP" ]; then
    "$SYSTEM_PIP" install --quiet --target "$VENV_DIR/lib/python${PYTHON_VER}/site-packages/" pip
else
    echo "✗ 找不到系统 pip3"
    exit 1
fi

# 验证 pip 指向 venv
PIP_LOCATION=$(python3 -m pip --version | grep -oP 'from \K[^ ]+')
if [[ "$PIP_LOCATION" != *".horizon/venv-llm"* ]]; then
    echo "✗ pip 未指向 venv: $PIP_LOCATION"
    exit 1
fi
echo "  pip 路径验证: $PIP_LOCATION ✓"

# 约束文件
echo "torch==${TORCH_CONSTRAINT}" > "$VENV_DIR/constraints.txt"
CONSTRAINT="$VENV_DIR/constraints.txt"
echo "  约束文件: torch==${TORCH_CONSTRAINT}"

# ============================================================
# Step 3: 安装组件
# ============================================================
echo ""
echo "=== 安装组件 ==="

PIP="python3 -m pip"

# 3.1 基础运行时
echo "--- 3.1 基础运行时 ---"
$PIP install --quiet -c "$CONSTRAINT" "$WHL_DIR"/hbm_infer-*.whl
echo "  hbm_infer ✓"
$PIP install --quiet -c "$CONSTRAINT" "$WHL_DIR"/horizon_plugin_profiler-*.whl
echo "  horizon_plugin_profiler ✓"

# 3.2 编译器
echo "--- 3.2 编译器 ---"
HBDK_COMPILER_WHL=$(find "$WHL_DIR" -name "hbdk4_compiler-*-${CP}-${CP}-manylinux_2_28_x86_64.whl" | head -1)
if [ -n "$HBDK_COMPILER_WHL" ]; then
    $PIP install --quiet -c "$CONSTRAINT" "$HBDK_COMPILER_WHL"
    echo "  hbdk4_compiler ✓"
else
    # 尝试更宽泛的匹配
    HBDK_COMPILER_WHL=$(find "$WHL_DIR" -name "hbdk4_compiler-*.whl" | head -1)
    if [ -n "$HBDK_COMPILER_WHL" ]; then
        $PIP install --quiet -c "$CONSTRAINT" "$HBDK_COMPILER_WHL"
        echo "  hbdk4_compiler ✓ ($(basename "$HBDK_COMPILER_WHL"))"
    else
        echo "  ✗ 找不到 hbdk4_compiler wheel"
        exit 1
    fi
fi
$PIP install --quiet -c "$CONSTRAINT" "$WHL_DIR"/hbdk4_march-*.whl
echo "  hbdk4_march ✓"

# 3.3 QAT 插件（按 torch+cuda 版本匹配 wheel）
echo "--- 3.3 QAT 插件 ---"
# 从 TORCH_VER 提取 CUDA tag（如 cu128）
CU_TAG=$(echo "$TORCH_VER" | grep -oP 'cu\d+' || echo "")
# 从 TORCH_VER 提取短版本号，如 2.8.0+cu128 → 280
TORCH_SHORT=$(echo "$TORCH_CONSTRAINT" | sed 's/\.//g')

# OE-LLM 的 horizon_plugin_pytorch 可能使用 cp39-abi3 标签（而非 cp310-cp310）
# 先尝试精确匹配，再尝试 abi3 匹配
PLUGIN_WHL=""
if [ -n "$CU_TAG" ]; then
    # 尝试 1: cp-tagged + cu+torch 版本
    PLUGIN_PATTERN="horizon_plugin_pytorch-*+${CU_TAG}.torch${TORCH_SHORT}-${CP}-${CP}-linux_x86_64.whl"
    PLUGIN_WHL=$(find "$WHL_DIR" -name "$PLUGIN_PATTERN" 2>/dev/null | head -1)

    # 尝试 2: abi3 + cu+torch 版本
    if [ -z "$PLUGIN_WHL" ]; then
        PLUGIN_WHL=$(find "$WHL_DIR" -name "horizon_plugin_pytorch-*+${CU_TAG}.torch${TORCH_SHORT}-cp39-abi3-linux_x86_64.whl" 2>/dev/null | head -1)
    fi

    # 尝试 3: 更宽泛的匹配
    if [ -z "$PLUGIN_WHL" ]; then
        PLUGIN_WHL=$(find "$WHL_DIR" -name "horizon_plugin_pytorch-*${CU_TAG}*${TORCH_SHORT}*" 2>/dev/null | head -1)
    fi
fi

# 尝试 4: 任何 horizon_plugin_pytorch wheel
if [ -z "$PLUGIN_WHL" ]; then
    PLUGIN_WHL=$(find "$WHL_DIR" -name "horizon_plugin_pytorch-*.whl" 2>/dev/null | head -1)
fi

if [ -n "$PLUGIN_WHL" ]; then
    $PIP install --quiet -c "$CONSTRAINT" "$PLUGIN_WHL"
    echo "  horizon_plugin_pytorch ✓ ($(basename "$PLUGIN_WHL"))"
else
    echo "  ✗ 找不到匹配的 horizon_plugin_pytorch wheel"
    echo "    可用文件:"
    find "$WHL_DIR" -name "horizon_plugin_pytorch-*.whl" -exec basename {} \;
    exit 1
fi

# ============================================================
# Step 4: 验证
# ============================================================
echo ""
echo "=== 验证安装 ==="

FAIL=0
for mod in hbdk4 hbm_infer horizon_plugin_profiler horizon_plugin_pytorch; do
    if python3 -c "import $mod" 2>/dev/null; then
        echo "  ✓ $mod"
    else
        echo "  ✗ $mod"
        FAIL=$((FAIL + 1))
    fi
done

if [ $FAIL -gt 0 ]; then
    echo ""
    echo "✗ 安装验证失败 ($FAIL 项)，建议回退 Docker 模式"
    exit 1
fi

# ============================================================
# Step 5: 更新 .env.oe-llm-package
# ============================================================
echo ""
echo "=== 更新环境配置 ==="

# 读取当前文件中的版本信息（保留自动检测生成的字段）
OE_LLM_VERSION=$(grep '^OE_LLM_VERSION=' "$ENV_FILE" 2>/dev/null | cut -d= -f2 || echo "")
HBDK_VER=$(grep '^HBDK_COMPILER_VERSION=' "$ENV_FILE" 2>/dev/null | cut -d= -f2 || echo "")
HBDK_MARCH_VER=$(grep '^HBDK_MARCH_VERSION=' "$ENV_FILE" 2>/dev/null | cut -d= -f2 || echo "")
HBM_INFER_VER=$(grep '^HBM_INFER_VERSION=' "$ENV_FILE" 2>/dev/null | cut -d= -f2 || echo "")
PROFILER_VER=$(grep '^HORIZON_PLUGIN_PROFILER_VERSION=' "$ENV_FILE" 2>/dev/null | cut -d= -f2 || echo "")
PLUGIN_VER=$(grep '^HORIZON_PLUGIN_PYTORCH_VERSION=' "$ENV_FILE" 2>/dev/null | cut -d= -f2 || echo "")
LLM_COMP_VER=$(grep '^LLM_COMPRESSION_VERSION=' "$ENV_FILE" 2>/dev/null | cut -d= -f2 || echo "")
TORCH_VER_FIELD=$(grep '^TORCH_VERSION=' "$ENV_FILE" 2>/dev/null | cut -d= -f2 || echo "")
PY_VER_FIELD=$(grep '^PYTHON_VERSION=' "$ENV_FILE" 2>/dev/null | cut -d= -f2 || echo "")
GPU_INFO_LINE=$(grep '^GPU_INFO=' "$ENV_FILE" 2>/dev/null || echo "")

cat > "$ENV_FILE" <<EOF
# OE-LLM 包环境信息（自动生成）
# 检测时间：$(date '+%Y-%m-%d %H:%M:%S')

# === OE-LLM 包基本信息 ===
OE_LLM_DIR=$OE_LLM_DIR
OE_LLM_VERSION=$OE_LLM_VERSION

# === 组件版本 ===
HBDK_COMPILER_VERSION=$HBDK_VER
HBDK_MARCH_VERSION=$HBDK_MARCH_VER
HBM_INFER_VERSION=$HBM_INFER_VER
HORIZON_PLUGIN_PROFILER_VERSION=$PROFILER_VER
HORIZON_PLUGIN_PYTORCH_VERSION=$PLUGIN_VER
LLM_COMPRESSION_VERSION=$LLM_COMP_VER

# === 配套环境 ===
TORCH_VERSION=$TORCH_VER_FIELD
PYTHON_VERSION=$PY_VER_FIELD

# === 执行模式 ===
EXECUTION_MODE=local

# === venv 路径 ===
VENV_DIR=.horizon/venv-llm
VENV_ACTIVATE_CMD=source .horizon/venv-llm/bin/activate

# --- GPU 信息 ---
$GPU_INFO_LINE
EOF

echo "  .env.oe-llm-package 已更新: EXECUTION_MODE=local"
echo ""
echo "=============================="
echo "  ✓ 安装完成！"
echo "=============================="
echo ""
echo "使用方式:"
echo "  source .horizon/venv-llm/bin/activate"
echo "  cd $OE_LLM_DIR/llm_compression && bash scripts/calib.sh ..."
echo ""
echo "注意："
echo "  交叉编译工具链（可选）需手动安装:"
echo "  sudo dpkg -i $OE_LLM_DIR/package/host/aarch64-linux-hb-gcc_12.2.0_amd64.deb"
