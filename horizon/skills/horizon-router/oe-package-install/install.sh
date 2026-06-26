#!/bin/bash
# OE 包本地安装脚本
# 用法: bash .horizon/skills/horizon-router/oe-package-install/install.sh <OE_DIR>
# 示例: bash .horizon/skills/horizon-router/oe-package-install/install.sh /mnt/oe-cli-test/horizon_j6_open_explorer_v3.9.0_rc4-py310_20260326
set -euo pipefail

# ============================================================
# 固定规则（勿改）
# 1. 始终用 python3 -m pip，不用裸 pip（避免 --without-pip venv 路径回退）
# 2. 必须 --system-site-packages 继承系统 torch（hmct 会拉最新版 torch）
# 3. hmct / hmct_gpu / horizon_torch_samples 必须 --no-deps
# 4. 用 constraints.txt 锁 torch 版本
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
VENV_DIR="$WORKSPACE_ROOT/.horizon/venv"
ENV_FILE="$WORKSPACE_ROOT/.horizon/.env.oe-package"

OE_DIR="${1:?用法: bash install.sh <OE_DIR>}"
WHL_DIR="$OE_DIR/package/host/ai_toolchain"

if [ ! -d "$WHL_DIR" ]; then
    echo "✗ 找不到 wheel 目录: $WHL_DIR"
    exit 1
fi

# ============================================================
# Step 1: 环境检测
# ============================================================
echo "=============================="
echo "  OE 包本地安装"
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
    if [[ "$CUDA_VER" != "11.8" && "$CUDA_VER" != "12.6" && "$CUDA_VER" != "12.8" ]]; then
        echo "✗ CUDA 版本必须为 11.8 / 12.6 / 12.8，当前: $CUDA_VER"
        exit 1
    fi
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
if [[ "$PIP_LOCATION" != *".horizon/venv"* ]]; then
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

# 4.1 基础运行时
echo "--- 4.1 基础运行时 ---"
$PIP install --quiet -c "$CONSTRAINT" "$WHL_DIR"/horizon_tc_ui-*.whl
echo "  horizon_tc_ui ✓"
$PIP install --quiet -c "$CONSTRAINT" "$WHL_DIR"/hbdnn-*.whl
echo "  hbdnn ✓"
$PIP install --quiet -c "$CONSTRAINT" "$WHL_DIR"/hbm_infer-*.whl
echo "  hbm_infer ✓"
$PIP install --quiet -c "$CONSTRAINT" "$WHL_DIR"/horizon_plugin_profiler-*.whl
echo "  horizon_plugin_profiler ✓"
# horizon_torch_samples 依赖 pycocotools 可能编译失败，用 --no-deps
$PIP install --quiet -c "$CONSTRAINT" --no-deps "$WHL_DIR"/horizon_torch_samples-*.whl
$PIP install --quiet click packaging
echo "  horizon_torch_samples ✓"

# 4.2 编译器
echo "--- 4.2 编译器 ---"
$PIP install --quiet -c "$CONSTRAINT" "$WHL_DIR"/hbdk4_compiler-*-"$CP"-"$CP"-manylinux_2_28_x86_64.whl
echo "  hbdk4_compiler ✓"
$PIP install --quiet -c "$CONSTRAINT" "$WHL_DIR"/hbdk4_march-*.whl
echo "  hbdk4_march ✓"
$PIP install --quiet -c "$CONSTRAINT" "$WHL_DIR"/hbdk4_runtime_x86_64_unknown_linux_gnu_nash-*.whl
echo "  hbdk4_runtime_x86 ✓"
$PIP install --quiet -c "$CONSTRAINT" "$WHL_DIR"/hbdk4_runtime_aarch64_unknown_linux_gnu_nash-*.whl
echo "  hbdk4_runtime_aarch64_linux ✓"
$PIP install --quiet -c "$CONSTRAINT" "$WHL_DIR"/hbdk4_runtime_aarch64_unknown_nto_qnx800_nash-*.whl
echo "  hbdk4_runtime_aarch64_qnx ✓"

# 4.3 量化工具（--no-deps 防止拉入新版 torch）
echo "--- 4.3 量化工具 ---"
$PIP install --quiet -c "$CONSTRAINT" --no-deps "$WHL_DIR"/hmct-[0-9]*-"$CP"-"$CP"-linux_x86_64.whl
echo "  hmct ✓"

# 从系统 torch 提取 CUDA tag（如 cu128）
CU_TAG=$(echo "$TORCH_VER" | grep -oP 'cu\d+' || echo "")
if [ -n "$CU_TAG" ]; then
    HMCT_GPU_WHL=$(find "$WHL_DIR" -name "hmct_gpu-*+${CU_TAG}-${CP}-${CP}-linux_x86_64.whl" | head -1)
    if [ -n "$HMCT_GPU_WHL" ]; then
        $PIP install --quiet -c "$CONSTRAINT" --no-deps "$HMCT_GPU_WHL"
        echo "  hmct_gpu (${CU_TAG}) ✓"
    else
        echo "  hmct_gpu 跳过 (未找到匹配 ${CU_TAG} 的 wheel)"
    fi
else
    echo "  hmct_gpu 跳过 (未检测到 CUDA 环境)"
fi

# 4.4 QAT 插件（按 torch+cuda 版本匹配 wheel）
echo "--- 4.4 QAT 插件 ---"
# 从 TORCH_VER 提取短版本号，如 2.8.0+cu128 → cu128.torch280
TORCH_SHORT=$(echo "$TORCH_CONSTRAINT" | sed 's/\.//g')
PLUGIN_PATTERN="horizon_plugin_pytorch-*+${CU_TAG}.torch${TORCH_SHORT}-${CP}-${CP}-linux_x86_64.whl"
PLUGIN_WHL=$(find "$WHL_DIR" -name "$PLUGIN_PATTERN" 2>/dev/null | head -1)
if [ -z "$PLUGIN_WHL" ]; then
    # 尝试不带 local version 的匹配
    PLUGIN_WHL=$(find "$WHL_DIR" -name "horizon_plugin_pytorch-*${CU_TAG}*${TORCH_SHORT}*-${CP}-*-linux_x86_64.whl" 2>/dev/null | head -1)
fi
if [ -n "$PLUGIN_WHL" ]; then
    $PIP install --quiet -c "$CONSTRAINT" "$PLUGIN_WHL"
    echo "  horizon_plugin_pytorch ✓ ($(basename "$PLUGIN_WHL"))"
else
    echo "  ✗ 找不到匹配的 horizon_plugin_pytorch wheel"
    echo "    搜索模式: $PLUGIN_PATTERN"
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
for mod in horizon_tc_ui hmct horizon_plugin_pytorch hbdk4 hbdnn hbm_infer; do
    if python3 -c "import $mod" 2>/dev/null; then
        echo "  ✓ $mod"
    else
        echo "  ✗ $mod"
        FAIL=$((FAIL + 1))
    fi
done

echo ""
echo "=== 验证 CLI ==="
for cmd in hb_compile hb_model_info hmct-debugger; do
    loc=$(command -v "$cmd" 2>/dev/null || echo "")
    if [ -n "$loc" ]; then
        echo "  ✓ $cmd → $loc"
    else
        echo "  ✗ $cmd NOT FOUND"
        FAIL=$((FAIL + 1))
    fi
done

if [ $FAIL -gt 0 ]; then
    echo ""
    echo "✗ 安装验证失败 ($FAIL 项)，建议回退 Docker 模式"
    exit 1
fi

# ============================================================
# Step 5: 更新 .env.oe-package
# ============================================================
echo ""
echo "=== 更新环境配置 ==="

# 读取当前文件中的版本信息（保留自动检测生成的字段）
OE_VERSION=$(grep '^OE_VERSION=' "$ENV_FILE" 2>/dev/null | cut -d= -f2 || echo "")
HORIZON_TC_UI_VER=$(grep '^HORIZON_TC_UI_VERSION=' "$ENV_FILE" 2>/dev/null | cut -d= -f2 || echo "")
HMCT_VER=$(grep '^HMCT_VERSION=' "$ENV_FILE" 2>/dev/null | cut -d= -f2 || echo "")
PLUGIN_VER=$(grep '^HORIZON_PLUGIN_PYTORCH_VERSION=' "$ENV_FILE" 2>/dev/null | cut -d= -f2 || echo "")
HBDK_VER=$(grep '^HBDK_COMPILER_VERSION=' "$ENV_FILE" 2>/dev/null | cut -d= -f2 || echo "")
GPU_INFO_LINE=$(grep '^GPU_INFO=' "$ENV_FILE" 2>/dev/null || echo "")

cat > "$ENV_FILE" <<EOF
# OE 包环境信息（自动生成）
# 检测时间：$(date '+%Y-%m-%d %H:%M:%S')

# === OE 包基本信息 ===
OE_DIR=$OE_DIR
OE_VERSION=$OE_VERSION

# === 组件版本 ===
HORIZON_TC_UI_VERSION=$HORIZON_TC_UI_VER
HMCT_VERSION=$HMCT_VER
HORIZON_PLUGIN_PYTORCH_VERSION=$PLUGIN_VER
HBDK_COMPILER_VERSION=$HBDK_VER

# === 执行模式 ===
EXECUTION_MODE=local

# === venv 路径 ===
VENV_DIR=.horizon/venv
VENV_ACTIVATE_CMD=source .horizon/venv/bin/activate

# --- GPU 信息 ---
$GPU_INFO_LINE
EOF

echo "  .env.oe-package 已更新: EXECUTION_MODE=local"
echo ""
echo "=============================="
echo "  ✓ 安装完成！"
echo "=============================="
echo ""
echo "使用方式:"
echo "  source .horizon/venv/bin/activate"
echo "  hb_model_info <model.onnx>"
