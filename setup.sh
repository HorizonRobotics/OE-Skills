#!/usr/bin/env bash
#
# Horizon Workspace 初始化脚本
#
# 用法: bash setup.sh <project-root>
#
# 将本脚本同级的 horizon/ 目录中的资源铺设到 <project-root>/.horizon/，
# 并向 CLAUDE.md / AGENTS.md 注入路由规则。
#
set -euo pipefail

RESOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -z "${1:-}" ]; then
  echo "ERROR: 缺少参数" >&2
  echo "用法: bash setup.sh <project-root>" >&2
  exit 1
fi

if ! PROJECT_ROOT="$(cd "$1" 2>/dev/null && pwd)"; then
  echo "ERROR: 项目目录不存在或无法访问: $1" >&2
  exit 1
fi
HORIZON_SRC="$RESOURCE_DIR/horizon"
HORIZON_DST="$PROJECT_ROOT/.horizon"

if [ ! -d "$HORIZON_SRC" ]; then
  echo "ERROR: 找不到资源目录 $HORIZON_SRC" >&2
  exit 1
fi

echo "==> Resource:  $RESOURCE_DIR"
echo "==> Project:   $PROJECT_ROOT"
echo "==> Target:    $HORIZON_DST"

# ── 1. 铺设 .horizon/ ──────────────────────────────────────────────
mkdir -p "$HORIZON_DST"

# docs
if [ -d "$HORIZON_SRC/docs" ]; then
  mkdir -p "$HORIZON_DST/docs"
  cp -r "$HORIZON_SRC/docs/"* "$HORIZON_DST/docs/"
  echo "  [ok] docs/    ($(ls "$HORIZON_DST/docs" | wc -l) files)"
else
  echo "  [WARN] docs/ 资源目录不存在，跳过" >&2
fi

# skills
if [ -d "$HORIZON_SRC/skills" ]; then
  mkdir -p "$HORIZON_DST/skills"
  cp -r "$HORIZON_SRC/skills/"* "$HORIZON_DST/skills/"
  # 跳过含 eval.json 的 test/ 目录（评测用例，不属于用户工作区）
  TEST_REMOVED=0
  while IFS= read -r eval_file; do
    rm -rf "$(dirname "$eval_file")"
    TEST_REMOVED=$((TEST_REMOVED + 1))
  done < <(find "$HORIZON_DST/skills" -path "*/test/eval.json" 2>/dev/null)
  SKILL_COUNT=$(find "$HORIZON_DST/skills" -name "SKILL.md" | wc -l)
  echo "  [ok] skills/  ($SKILL_COUNT skills, $TEST_REMOVED test dirs skipped)"
else
  echo "  [WARN] skills/ 资源目录不存在，跳过" >&2
fi

# HORIZON.md
if [ -f "$HORIZON_SRC/HORIZON.md" ]; then
  cp "$HORIZON_SRC/HORIZON.md" "$HORIZON_DST/HORIZON.md"
  echo "  [ok] HORIZON.md"
else
  echo "  [WARN] HORIZON.md 不存在，跳过" >&2
fi

# skill-index.json
if [ -f "$HORIZON_SRC/skill-index.json" ]; then
  cp "$HORIZON_SRC/skill-index.json" "$HORIZON_DST/skill-index.json"
  echo "  [ok] skill-index.json"
else
  echo "  [WARN] skill-index.json 不存在，跳过" >&2
fi

# VERSION
if [ -f "$HORIZON_SRC/VERSION" ]; then
  cp "$HORIZON_SRC/VERSION" "$HORIZON_DST/VERSION"
  VERSION=$(cat "$HORIZON_SRC/VERSION")
  echo "  [ok] VERSION ($VERSION)"
else
  echo "  [WARN] VERSION 不存在，跳过" >&2
fi

# ── 2. 注入路由规则到 CLAUDE.md / AGENTS.md ────────────────────────
MARKER='# Horizon Workspace Rules'

ROUTING_RULES="$MARKER

If the user request involves Horizon toolchain related topics
(quantization, compile, deploy, evaluation, training, CLI usage, version issues),
you MUST follow the project rules defined in .horizon/HORIZON.md.

For Horizon toolchain related tasks:
- Do NOT guess toolchain APIs or CLI parameters based on general LLM knowledge.
- If uncertain, you MUST retrieve documentation before answering."

INJECTED=0
for f in CLAUDE.md AGENTS.md; do
  target="$PROJECT_ROOT/$f"
  if [ -f "$target" ]; then
    if grep -q "$MARKER" "$target"; then
      echo "  [skip] $f (already injected)"
    else
      printf '%s\n\n%s\n' "$ROUTING_RULES" "$(cat "$target")" > "$target"
      echo "  [ok] $f (injected)"
    fi
    INJECTED=$((INJECTED + 1))
  fi
done
if [ "$INJECTED" -eq 0 ]; then
  echo "  [WARN] CLAUDE.md 和 AGENTS.md 都不存在，路由规则未注入" >&2
  echo "         请先创建对应文件后重新执行 setup.sh" >&2
fi

# ── 3. 最终检查 ────────────────────────────────────────────────────
ERRORS=0
for f in HORIZON.md skill-index.json VERSION; do
  if [ ! -f "$HORIZON_DST/$f" ]; then
    echo "  [FAIL] 缺少 $f" >&2
    ERRORS=$((ERRORS + 1))
  fi
done
if [ ! -d "$HORIZON_DST/skills" ] || [ "$(find "$HORIZON_DST/skills" -name 'SKILL.md' 2>/dev/null | wc -l)" -eq 0 ]; then
  echo "  [FAIL] skills/ 目录为空" >&2
  ERRORS=$((ERRORS + 1))
fi

echo ""
if [ "$ERRORS" -gt 0 ]; then
  echo "==> 安装完成，但有 $ERRORS 个问题，请检查上方输出。" >&2
  exit 1
else
  echo "==> Done. .horizon/ initialized at $HORIZON_DST"
fi
