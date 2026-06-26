# Horizon Workspace Agent Setup

本文档给 agent 使用。用户把包含本文件的目录放到任意位置后，agent 按以下步骤完成项目初始化。

## 1. 定位资源目录

找到本文件（`agent-setup.md`）所在目录的绝对路径，记为 `RESOURCE_DIR`。

## 2. 确认项目根目录

按以下顺序确认 `PROJECT_ROOT`：

1. 检查用户当前工作目录及其逐级父目录，查找是否存在 `AGENTS.md` 或 `CLAUDE.md`
2. 如果找到，将包含该文件的目录作为候选 `PROJECT_ROOT`，**必须向用户确认**是否正确
3. 如果未找到，将用户当前工作目录作为候选 `PROJECT_ROOT`，**必须向用户确认**

未经用户确认，不得继续执行后续步骤。所有资源必须安装到此确认后的 `PROJECT_ROOT` 中。

## 3. 确保 AGENTS.md 或 CLAUDE.md 存在

检查 `PROJECT_ROOT` 下是否存在 `AGENTS.md` 或 `CLAUDE.md`：

- 如果已存在，直接使用，跳到下一步
- 如果都不存在，根据当前 agent 类型创建：
  - **Claude Code** → 创建 `CLAUDE.md`
  - **其他 agent**（Codex、Cursor 等） → 创建 `AGENTS.md`
- 创建空文件即可（`setup.sh` 会向其中注入路由规则）

## 4. 执行安装

```bash
bash "$RESOURCE_DIR/setup.sh" "$PROJECT_ROOT"
```

这条命令会：

- 在 `PROJECT_ROOT` 下创建 `.horizon/` 目录
- 铺设 docs、skills、HORIZON.md、skill-index.json、VERSION
- 跳过含 `eval.json` 的 `test/` 目录
- 向 `CLAUDE.md` / `AGENTS.md` 注入路由规则（幂等，不会重复注入）

## 5. 安装后检查

```bash
test -f "$PROJECT_ROOT/.horizon/HORIZON.md"
test -f "$PROJECT_ROOT/.horizon/VERSION"
test -f "$PROJECT_ROOT/.horizon/skill-index.json"
test -f "$PROJECT_ROOT/.horizon/skills/horizon-router/SKILL.md"
```

## 6. 初始化后如何使用

1. 先看 `.horizon/HORIZON.md` 了解工作区规则和内置 skill 清单
2. 查找具体 skill 路径时，以 `.horizon/skill-index.json` 为准
3. 当任务属于 Horizon 范畴但尚未明确落到某个具体 skill 时，先走 `.horizon/skills/horizon-router/SKILL.md` 做顶层路由
4. 再由 horizon-router 顶层 skill 分流到具体的子 skill

## 7. 配置 oe-mcp（按需）

`oe-mcp` 是 OpenExplorer 提供的 MCP 文档检索服务。当本地 skill 内容不足以回答时，agent 应使用 oe-mcp 补充检索。

### Claude Code

```bash
claude mcp add --transport http oe-mcp https://mcp.oe.horizon.auto/mcp
```

### Codex

```bash
codex mcp add oe-mcp --url https://mcp.oe.horizon.auto/mcp
```

### Cursor

编辑 `~/.cursor/mcp.json`，在已有配置中新增：

```json
{
  "mcpServers": {
    "oe-mcp": {
      "type": "http",
      "url": "https://mcp.oe.horizon.auto/mcp"
    }
  }
}
```

如果已有其他 MCP 配置，只合并 `oe-mcp` 这一段，不要覆盖现有内容。

## 8. 常见问题

- 如果 `setup.sh` 报找不到 `horizon/` 目录，确认资源目录结构完整
- 如果 `.horizon/` 已存在，`setup.sh` 会覆盖更新，不会丢失用户自己的文件（只覆盖 horizon 资源文件）
- `setup.sh` 只会向已有的 `CLAUDE.md` / `AGENTS.md` 注入路由规则；如果两个文件都不存在，必须先按第 3 步创建对应文件再执行安装
