# oe-skills

Horizon Workspace 技能包，为 AI Agent（Claude Code / Codex / Cursor 等）提供 Horizon 工具链的结构化知识和操作能力。

## 包结构

```text
oe-skills/
  setup.sh           安装脚本，将 horizon/ 资源铺设到目标项目的 .horizon/ 目录
  agent-setup.md     Agent 安装指引文档
  horizon/           资源目录（安装时复制到目标项目）
    HORIZON.md       工作区规则和使用说明
    VERSION          当前版本号
    skill-index.json Skill 索引（模块、路径、描述、触发条件）
    docs/            Horizon 工具链离线文档
    skills/          按模块组织的 Skill 集合
      horizon-router/    顶层路由 Skill
      hbdk/              HBDK 编译相关
      plugin/            Horizon Plugin（QAT 量化）
      hmct/              HMCT / PTQ 量化
      ucp/               UCP / 板端推理
      horizon_tc_ui/     可视化分析工具
      llm/               LLM 量化与压缩
```

## 安装方式

```bash
bash setup.sh <project-root>
```

脚本会在目标项目下：

1. 创建 `.horizon/` 目录，铺设 docs、skills、HORIZON.md、skill-index.json、VERSION
2. 向已有的 `CLAUDE.md` 或 `AGENTS.md` 注入路由规则（幂等）

安装后检查：

```bash
test -f "<project-root>/.horizon/HORIZON.md"
test -f "<project-root>/.horizon/VERSION"
test -f "<project-root>/.horizon/skill-index.json"
```

## 支持的 Skill 模块

| 模块 | 说明 | 代表 Skill |
|------|------|-----------|
| **HBDK** | 模型编译 | j6-hbdk-compile, hbdk-manual |
| **Plugin** | QAT 量化适配、导出、调试 | j6-plugin-adaptation, j6-plugin-export, j6-plugin-precision-tuning 等 |
| **HMCT** | PTQ 量化与精度调优 | hmct-workflow, j6-hmct-cosine-similarity-tuning |
| **UCP** | 板端推理、性能评测、Trace 分析 | j6-ucp-infer-generating, j6-ucp-hbm-infer, j6-ucp-perfetto-trace-analysis 等 |
| **TC UI** | 可视化分析工具 | hb-analyzer-performance, horizon-tc-ui |
| **LLM** | LLM 量化与压缩 | lightcompress-batch-quantize, llmcompression-operations 等 |
| **Router** | 顶层路由与环境检测 | horizon-router, oe-package-detection, board-detection 等 |

## 版本

当前版本：`0.1.11`
