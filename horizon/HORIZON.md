# Horizon 工作区

## 1. 工作区概览

当前项目由 `oe-cli init` 初始化生成。

- 工作区根目录：`.horizon/`
- 版本文件：`.horizon/VERSION`
- Skill 索引：`.horizon/skill-index.json`
- 文档目录：`.horizon/docs/`
- Skill 目录：`.horizon/skills/`
- 当前 release 版本：`0.1.11`

## 2. 使用规则

- 遇到 Horizon 相关请求时，优先遵循本文件。
- 当请求属于 Horizon 范畴，但还不能明确落到某个具体 skill 时，先使用 `.horizon/skills/horizon-router/SKILL.md` 作为顶层路由 skill。
- 业务 skill 按模块放在 `.horizon/skills/<module>/<slug>/`；具体路径以 `.horizon/skill-index.json` 和下方模块清单为准。
- 未经检索，不要猜测 Horizon 工具链命令、参数或流程细节。
- 本地文档统一放在 `.horizon/docs/` 下，文档目录名固定不带版本号。

## 3. 执行前检查

- 开始 Horizon 工具链任务前，先检查用户是否提供了可用板卡信息。
- 板卡类型按三类处理：`nash-e/m`、`nash-p` 与 `nash-b`（J6B/QNX 平台）。
- 优先从环境变量中查找板卡信息，例如 `HORIZON_BOARD_TYPE`、`OE_BOARD_TYPE`、`BOARD_TYPE`、`BOARD`、`NASH_BOARD`。
- 如果环境变量没有提供，再检查项目内相关配置文件，例如 `.env`、`.env.local`、`.horizon/board.env`、`.horizon/board.json`、`AGENTS.md`、`CLAUDE.md`。
- 如果任务涉及板端运行、板端推理、远端 HBM、性能压测或 BPU 实测，但没有找到板卡信息，必须先向用户确认是否有可用板卡。
- 如果用户明确没有可用板卡，涉及板端的任务应回退到 X86 评测、仿真、静态检查或可离线执行的分析工具，并说明该结果不能替代真实板端验证。

## 4. 配置与验证规则

- 修改模型相关配置后，必须使用对应工具做最小可运行验证；模型相关配置包括量化配置、编译配置、导出配置、推理配置、输入预处理配置和精度/性能评测配置。
- 验证失败时，先说明失败命令、关键报错和判断出的原因，再基于错误原因修改配置并重试。**同一方法最多重试 1 次**（总计 2 次尝试）。第 2 次仍失败则必须切换策略（换工具、查文档、检查环境）或向用户报告阻塞，禁止继续用相同方法重试。
- 不要在未验证的情况下声称配置可用；如果环境、数据或板卡缺失导致无法验证，必须明确说明缺失项和剩余风险。
- 默认量化配置按板卡类型选择：`nash-p` / J6P 使用 `fp16+int8`，`nash-e/m` / J6E/J6M 与 `nash-b` / J6B 使用 `int8`。

## 5. MCP 规则

- 处理 Horizon 相关请求时，先根据 `.horizon/skill-index.json` 和下方模块清单找到对应 skill。
- 进入对应 skill 后，优先阅读该 skill 的 `SKILL.md`、本地 references、examples 或 scripts。
- 只要模型相关参数、函数、API、配置项、命令参数、流程顺序或默认行为存在不确定性，必须使用 `oe-mcp` 检索对应文档，直到弄懂后再继续。
- 如果查询对应 skill 后仍有不理解的问题，或者需要进一步确认官方流程、参数说明、API 行为、版本差异或报错含义，必须使用 `oe-mcp` 做文档检索。
- `oe-mcp` 用于补充和确认，不替代当前 release 包内的 skill 路由；最终回答应尽量基于已查看的 skill 内容、MCP 文档或代码证据。
- 当本地 skill 与 `oe-mcp` 检索结果不一致时，先说明差异，再给出保守建议。

## 6. 内置 Skills

- `horizon-router@0.1.11` -> `.horizon/skills/horizon-router/SKILL.md`: Horizon 顶层路由 skill，用于在具体 skill 之间做渐进式任务分流。

### OE 包环境

- `oe-package-detection@1.0.0` -> `.horizon/skills/horizon-router/oe-package-detection/SKILL.md`
- `oe-package-install@1.0.0` -> `.horizon/skills/horizon-router/oe-package-install/SKILL.md`
- `board-detection@1.0.0` -> `.horizon/skills/horizon-router/board-detection/SKILL.md`

### OE-LLM 包环境

- `oe-llm-package-detection@1.0.0` -> `.horizon/skills/horizon-router/oe-llm-package-detection/SKILL.md`
- `oe-llm-package-install@1.0.0` -> `.horizon/skills/horizon-router/oe-llm-package-install/SKILL.md`

### HBDK (hbdk)

- `j6-hbdk-compile@1.1.8` -> `.horizon/skills/hbdk/j6-hbdk-compile/SKILL.md`
- `hbdk-manual@1.0.0` -> `.horizon/skills/hbdk/hbdk-manual/SKILL.md`

### Horizon Plugin (plugin)

- `j6-plugin-adaptation@1.0.0` -> `.horizon/skills/plugin/j6-plugin-adaptation/SKILL.md`
- `j6-plugin-export@1.0.1` -> `.horizon/skills/plugin/j6-plugin-export/SKILL.md`
- `j6-plugin-model-check-result@1.0.0` -> `.horizon/skills/plugin/j6-plugin-model-check-result/SKILL.md`
- `j6-plugin-graph-diff@1.0.0` -> `.horizon/skills/plugin/j6-plugin-graph-diff/SKILL.md`
- `j6-plugin-hbdk-generating@1.2.0` -> `.horizon/skills/plugin/j6-plugin-hbdk-generating/SKILL.md`
- `j6-plugin-consistency-debug@1.0.0` -> `.horizon/skills/plugin/j6-plugin-consistency-debug/SKILL.md`
- `j6-plugin-precision-tuning@1.0.0` -> `.horizon/skills/plugin/j6-plugin-precision-tuning/SKILL.md`

### HMCT / Quantization (hmct)

- `hmct-workflow@1.0.0` -> `.horizon/skills/hmct/SKILL.md`

### UCP / Runtime (ucp)

- `j6-ucp-infer-generating@1.1.1` -> `.horizon/skills/ucp/j6-ucp-infer-generating/SKILL.md`
- `j6-ucp-hbm-infer@1.1.0` -> `.horizon/skills/ucp/j6-ucp-hbm-infer/SKILL.md`
- `j6-ucp-model-perf-eval@1.0.0` -> `.horizon/skills/ucp/j6-ucp-model-perf-eval/SKILL.md`
- `j6-ucp-perfetto-trace-analysis@1.1.0` -> `.horizon/skills/ucp/j6-ucp-perfetto-trace-analysis/SKILL.md`
- `j6-ucp-perfetto-trace-catcher@1.0.0` -> `.horizon/skills/ucp/j6-ucp-perfetto-trace-catcher/SKILL.md`
- `j6-board-monitor@1.0.0` -> `.horizon/skills/ucp/j6-board-monitor/SKILL.md`

### Horizon TC UI / Analyzer (horizon_tc_ui)

- `hb-analyzer-performance@1.0.0` -> `.horizon/skills/horizon_tc_ui/hb-analyzer-performance/SKILL.md`
- `horizon-tc-ui@1.0.0` -> `.horizon/skills/horizon_tc_ui/horizon-tc-ui/SKILL.md`
