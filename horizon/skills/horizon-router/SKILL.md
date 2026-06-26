---
name: horizon-router
description: OpenExplorer 工具链入口 Skill，处理 PTQ/QAT 量化编译、板端部署、性能精度评估等请求，并将任务路由到对应的 Horizon 子 Skill。
---

# Horizon Router

OpenExplorer / Horizon 工具链的顶层路由入口。

当请求涉及量化、编译、部署、板端推理、性能/精度评估，或用户提供了 `.onnx`、`.bc`、`.hbm`、`.pt` 等模型文件时，从本 Skill 进入。

**路由前必须先读取 `.horizon/skill-index.json`**，通过其中每个 Skill 的 `description` 字段理解能力边界，再决定路由到哪个子 Skill。不要凭名字猜测。

---

## ⛔ 关键规则（最高优先级）

### 全链路部署规范优先于子 Skill

当用户需求涉及「量化 → 编译 → 部署」完整链路时，`references/deployment-workflow.md` 中的全链路部署规范是**最高权威**。如果子 Skill 的默认行为与全链路规范冲突，**以全链路规范为准**。常见冲突场景：

| 全链路规范要求 | 子 Skill 默认值 | 处理方式 |
|--------------|---------------|---------|
| `calibration_type: histogram` | HMCT 默认 `max` | 按全链路规范，使用 histogram |
| `all_node_type: float16`（nash-p） | HMCT 默认 `int8` | 按全链路规范，使用 fp16 + conv int8 |
| `remove_node_type: [Quantize, Dequantize]` | hbdk-compile 默认 `[Quantize]` | 按全链路规范，同时删除两者 |
| 部署交付物 = UCP 推理代码 | hbm_infer SDK 即可完成验证 | 按全链路规范，UCP 代码才是部署交付物 |

> **原则**：子 Skill 服务于单步操作，全链路规范服务于端到端目标。端到端任务中，单步的"合理默认"可能不符合全链路要求。

### 量化配置默认原则

除非用户明确要求混合精度调优，或当前任务已通过评测确认全 int8 精度不达标，否则涉及量化配置的任务（QAT 适配、导出、全流程代码生成）应默认使用全 int8 配置。

- **禁止**在没有精度不达标证据的情况下，主动将算子升高到 int16 或 fp16
- 如果全 int8 精度不达标，应先路由到 `j6-plugin-precision-tuning`，按敏感度分析结果决定哪些算子需要升高精度，而不是凭经验预设混合精度
- 用户明确说"用混合精度"或"int8 不够"时，才跳过全 int8 默认

### 长时间任务的等待策略

当 agent 启动了耗时较长的后台任务（敏感度分析、HBDK 编译、QAT 训练等，通常 >3 分钟）时，**必须使用以下策略之一**等待完成，禁止反复轮询：

#### 策略 A：后台启动 + 等待通知（推荐）

```
1. 编写包含完整处理逻辑的脚本（脚本自身负责生成最终结果文件）
2. 使用 Bash run_in_background: true 启动脚本
3. 回复"任务已在后台运行，等待完成通知"，然后停止——不执行任何进度检查
4. 收到系统自动通知后，读取脚本输出的结果文件
```

#### 策略 B：单次超时等待

如果必须用 `wait` 或前台运行，设置足够长的 `timeout`（如 600000ms），**一次等到结束**：

```bash
# 一次等到完成，不中途检查
python3 long_running_script.py  # timeout: 600000
```

#### ⛔ 禁止行为（会导致 API 崩溃）

```
# ❌ 以下模式会触发重复调用检测，导致 400 错误终止：
Bash: tail -c 1000 tuning_run.log   # 第1次
Bash: tail -c 1000 tuning_run.log   # 第2次
Bash: tail -c 1000 tuning_run.log   # 第3次 → 崩溃！

# ❌ 即使参数微调也会被检测：
Bash: tail -n 5 tuning_run.log
Bash: tail -n 10 tuning_run.log
Bash: wc -l tuning_run.log          # 仍然可能触发
```

**原因**：API 层面会检测短时间内相似的工具调用。连续 3 次语义相近的命令即可能触发保护机制。后台任务完成时系统会自动通知，无需主动检查。

### 连续失败时的策略切换

当同一操作连续失败 2 次时，**必须切换策略**，禁止继续重试同一方法：

1. **第 1 次失败** → 分析错误信息，微调参数后重试
2. **第 2 次失败（同一方法）** → ⛔ **STOP**。必须：
   - 明确声明"当前方法已失败 2 次，切换策略"
   - 从以下方向选择新策略：换工具/脚本、查阅文档（oe-mcp）、检查环境兼容性、向用户报告阻塞
3. **第 3 次失败（换了方法仍失败）** → 向用户报告阻塞原因，不再盲目重试

**原因**：API 会检测短时间内的相似工具调用，连续 3 次语义相近的命令可能触发 400 错误终止。常见触发场景：反复用相同参数调用编译命令、反复读取同一个日志文件的尾部、反复尝试相同的 Docker 启动命令。

### 批量任务处理策略

当任务涉及对 **多个模型（>3个）** 执行相同操作时，**必须**按 `references/batch-task-strategy.md` 中的策略执行。核心原则：有 Agent 工具时拆分并行 sub-agent（策略 A），无 Agent 工具时写脚本 + 等待通知（策略 B）。**⛔ 禁止轮询进度**，连续 3 次相似命令会触发 API 重复调用检测导致崩溃。

### 大文件数据提取规则

当需要从大型数据文件（CSV、日志等，通常 >100 行）中提取特定条目时，**禁止**使用 Read 工具全文读取——Read 只返回文件开头部分，会遗漏后部数据。

**必须**使用 Bash + `grep` 定向提取：

```bash
grep "<关键词>" large_file.csv
```

典型场景：
- 从逐层对比 CSV（如 `compare_per_layer_out.csv`）中提取特定算子数据
- 从日志中提取特定层或模块的记录
- 从敏感度文件中提取特定算子的排名

### 多步骤任务的中间产出保存

当任务包含多个有意义的步骤时，**每完成一个步骤就立即将结果写入 `outputs/` 目录**，不要等到所有步骤全部完成才输出。这样即使后续步骤失败或超时，已完成的工作成果仍然可见。

**规则：**
- 完成数据准备/重组后 → 立即写入数据处理报告到 `outputs/`
- 完成分析/评估后 → 立即写入分析报告到 `outputs/`
- 每个中间产出文件应包含足够信息（原始数据格式、处理策略、结果路径），使其可独立使用

**示例：**
```
# ✅ 正确：数据重组完成后立即记录
1. 重组 flat → nested 格式
2. 验证重组结果
3. 写入 outputs/data_processing.md  ← 记录原始格式、重组策略、输出目录
4. 继续下一步（如敏感度分析）     ← 即使此步失败，数据处理报告仍在

# ❌ 错误：等到最后才输出
1. 重组 flat → nested 格式
2. 运行敏感度分析（3小时，超时崩溃）
3. 未写入任何输出                  ← 数据重组工作全部丢失
```

### 工具调用前的数据格式预检

当用户提供的数据（校准数据、评测数据、配置文件等）需要传递给下游工具时，**必须先检查数据格式是否符合目标工具的要求**，再调用工具。如果格式不符，应先自动转换或告知用户，避免工具调用失败后才发现问题。

常见场景：
- HMCT 校准数据：需要嵌套目录格式，详见 `references/hmct-workflow-guide.md`「校准数据格式规范」
- 评测数据集：需要与模型输入名一一对应

### 批量 HBM 性能评估

详见 `references/routing-tables.md`「批量 HBM 性能评估」章节。禁止自写脚本替代，禁止路由到 `hb-analyzer-performance`。报告必须包含 debug 编译分析。

### 板端缓存清理

任何涉及板端部署的任务完成后，**必须**按 `references/board-cleanup.md` 清理板端残留文件（停进程 + 清 WORKDIR + 清 /tmp），防止磁盘耗尽。批量任务在所有模型评测完毕后统一清理。

---

## 前置检查

### OE 包检查

任何量化、编译、部署任务进入前，先检查 `.horizon/.env.oe-package` 是否存在且内容完整（含 `OE_DIR`、`OE_VERSION`、`EXECUTION_MODE`）：

- **存在且完整** → 直接读取，根据 `EXECUTION_MODE` 决定后续命令执行方式（local / docker）；docker 模式下必须使用 `DOCKER_EXEC_PREFIX` 拼接命令；local 模式下先 `source $VENV_ACTIVATE_CMD` 激活 venv
- **不存在或不完整** → **中断当前任务**，向用户提示：
  > 未检测到 OE 包环境配置（`.horizon/.env.oe-package`）。请提供 OE 包路径，或回复"跳过"暂不配置。

  根据用户回复处理：
  1. **用户提供路径** → 派发给 subagent 执行检测（将 `.horizon/skills/horizon-router/oe-package-detection/SKILL.md` 的完整内容作为 subagent 的 prompt），检测完成后询问是否本地安装，选择安装则派发 `oe-package-install` Skill
  2. **用户回复"跳过"或明确不配置** → 在当次对话中记录用户已跳过 OE 包检查，继续后续任务。后续涉及 OE 包的工具链命令可能因环境缺失而失败，需在回答中提示风险
  3. **不持久化跳过标记**：下次新任务仍会再次提示，确保用户不会因一次跳过而永久忽略环境配置

### OE-LLM 包检查

LLM 相关任务（LLM 量化/压缩/编译/板端 LLM 推理）进入前，先检查 `.horizon/.env.oe-llm-package` 是否存在且内容完整（含 `OE_LLM_DIR`、`OE_LLM_VERSION`、`EXECUTION_MODE`）：

- **存在且完整** → 直接读取，根据 `EXECUTION_MODE` 决定后续命令执行方式（local / docker）；docker 模式下必须使用 `DOCKER_EXEC_PREFIX` 拼接命令；local 模式下先 `source $VENV_ACTIVATE_CMD` 激活 venv
- **不存在或不完整** → **中断当前任务**，向用户提示：
  > 未检测到 OE-LLM 包环境配置（`.horizon/.env.oe-llm-package`）。请提供 OE-LLM 包路径，或回复"跳过"暂不配置。

  根据用户回复处理：
  1. **用户提供路径** → 派发给 subagent 执行检测（将 `.horizon/skills/horizon-router/oe-llm-package-detection/SKILL.md` 的完整内容作为 subagent 的 prompt），检测完成后询问是否本地安装，选择安装则派发 `oe-llm-package-install` Skill
  2. **用户回复"跳过"或明确不配置** → 在当次对话中记录用户已跳过 OE-LLM 包检查，继续后续任务。后续涉及 OE-LLM 包的工具链命令可能因环境缺失而失败，需在回答中提示风险
  3. **不持久化跳过标记**：下次新任务仍会再次提示，确保用户不会因一次跳过而永久忽略环境配置

### 板卡检测

涉及板端运行、板端推理、远端 HBM、性能压测或 BPU 实测的任务，先检查 `.horizon/.env.board` 是否存在且内容完整（含 `BOARD_TYPE`、`BOARD_IP`、`BPU_ARCH`、`BOARD_WORKDIR`）：

- **存在且完整** → 直接读取，继续后续任务
- **不存在或不完整** → 按以下顺序处理：
  1. **先向用户询问**：是否有可用板卡？IP 是什么？
  2. **派发给 subagent 执行检测**：将 `.horizon/skills/horizon-router/board-detection/SKILL.md` 的完整内容作为 subagent 的 prompt
  3. **检测完成后**：主 agent 读取 `.env.board` 确认结果，继续后续任务

### 文档检索规则（oe-mcp）— 强制

> 涉及工具链的命令、参数、API、配置项、流程顺序、报错信息等，只要存在不确定，**必须**用 `oe-mcp` 检索后才能回答。

1. **先查本地 Skill**：进入对应子 Skill 的 `SKILL.md` 及相关文件
2. **再查 `oe-mcp`**：本地无法回答时，使用 `search_doc` 检索
3. **复杂问题多轮检索**：至少 3–5 轮，每轮换角度（工具名 → 参数名 → 报错信息），直到信息充分

**禁止**：跳过检索直接回答 / 只查一轮就下结论 / 检索不足时凭经验推测

---

## 路由流程（最高优先级，必须按顺序执行）

收到用户请求后，按以下顺序完成路由：

1. **读取 Skill 索引**：先读 `.horizon/skill-index.json`，通过每个 Skill 的 `description` 字段理解各 Skill 的能力边界和触发条件
2. **判断是否批量任务**：如果用户请求涉及多个模型（>3个）的相同操作，先执行上方「⛔ 关键规则」中的 STOP-CHECK 门禁，输出执行计划后再继续
3. **匹配用户意图**：根据用户请求中的关键词、文件类型、操作意图，在索引中找到最匹配的 Skill
4. **加载目标 Skill**：读取匹配 Skill 的 `skillFile`（即 `SKILL.md`），获取详细的执行指导
5. **不要跳过索引**：即使你觉得已经知道该用哪个 Skill，也要先查索引确认——索引中的 description 可能已更新

> **禁止**：凭记忆或 Skill 名字猜测用途而不读索引。

### ⛔ 路由后强制读取门禁

完成路由匹配后，**必须**在开始任何执行操作之前读取目标 Skill 的 `SKILL.md`。

**禁止**：在路由确定后直接开始读取数据文件、执行工具链命令或编写分析报告。
SKILL.md 中可能包含特定场景的执行框架、参考文档加载指令和分析流程要求——
跳过 SKILL.md 将导致分析不完整或遗漏关键步骤。

### 路由原则

- 用户请求通常落在流程中的某个阶段，先定位到阶段再路由到对应 Skill
- 跨多个连续阶段的需求，优先用编排型 Skill（`j6-plugin-hbdk-generating`、`j6-plugin-adaptation`），不要拆成多个零散 Skill
- 能明确命中具体 Skill 时，尽快切换，不要停留在本 Skill 中重复解释

### ⚠️ 易混淆路由对照表

以下场景容易路由错误，**必须**在路由前仔细区分用户意图：

| 用户请求特征 | 正确路由 | 错误路由 | 区分要点 |
|-------------|---------|---------|---------|
| 解读 `floatvscalib/` 目录的 debug 结果（量化误差分析、截断/舍入误差分类、fix-scale 建议） | **`j6-plugin-precision-tuning`** | ~~`j6-plugin-consistency-debug`~~ | floatvscalib 是 calibration/QAT 训练侧产出，属于精度调优范畴 |
| 解读 `compare_per_layer_out.csv`、`sensitive_ops.txt`、`abnormal_layer_advisor.csv` | **`j6-plugin-precision-tuning`** | ~~`j6-plugin-consistency-debug`~~ | 这些文件来自 QuantAnalysis 的精度分析，用于量化误差分类 |
| 训练侧精度正常，但 export/convert/compile/HBM 板端出现精度下降 | **`j6-plugin-consistency-debug`** | ~~`j6-plugin-precision-tuning`~~ | 关键是训练侧精度正常 + 部署阶段才掉点 |
| calibration 后精度不达标、QAT 训练 loss 不收敛 | **`j6-plugin-precision-tuning`** | ~~`j6-plugin-consistency-debug`~~ | 问题在训练/校准阶段，非部署一致性 |

> **快速判定规则**：如果用户提到了 `floatvscalib`、`debug 结果解读`、`截断误差`、`舍入误差`、`fixscale`、`compare_per_layer_out`，**一律路由到 `j6-plugin-precision-tuning`**。只有当用户明确说"训练侧正常但部署侧掉点"时，才路由到 `j6-plugin-consistency-debug`。

### 量化路径判定门禁（必须执行）

当用户需求涉及量化或部署时，在加载任何子 Skill 之前，**必须**完成以下判定并输出结论：

```
量化路径判定：
1. 用户输入类型：ONNX / PyTorch / 未明确？
   → [填写]
2. 用户是否明确说"导出 ONNX 再量化"？
   → [填写]
3. 判定结果：PTQ 路径 / QAT 路径
   → [填写]
4. 如果判定为 PTQ 路径且用户输入是 PyTorch：
   → 必须有用户明确指示才能走 PTQ，否则 STOP 并向用户确认
```

**判定规则**：
- 用户提供 `.onnx` 文件 → PTQ
- 用户提供 `.pt/.pth` + 模型代码，且未说"导出 ONNX" → QAT
- 用户提供 `.pt/.pth` 但明确说"导出 ONNX 再量化" → PTQ（需引用用户原话）
- 不确定 → 向用户询问，不要自行决定

**⛔ 不可绕过的硬门禁**：当判定为 QAT 时，**禁止**因为以下原因降级为 PTQ：
- GPU 不可用 → 应路由到 GPU docker 容器方案（见 `references/deployment-workflow.md` §5）
- 模型复杂度高 → 应尝试 QAT，遇到困难时向用户报告阻塞原因
- 已有 ONNX 导出 → 仍需走 QAT 链路的 `.bc` 导出
- HMCT histogram 校准崩溃 → 应修复或报告，不应改用其他校准方法 + PTQ

### ⛔ 路由后强制读取门禁

完成路由匹配后，**必须**在开始任何执行操作之前读取目标 Skill 的 `SKILL.md`。

**禁止**：在路由确定后直接开始读取数据文件或执行工具链命令。SKILL.md 中可能包含特定场景的执行框架、参考文档加载指令和分析流程要求——跳过 SKILL.md 将导致分析不完整或遗漏关键步骤。

### 大文件数据提取规则

当需要从大型数据文件（CSV、日志等，通常 >100 行）中提取特定条目时，**禁止**使用 Read 工具全文读取——Read 只返回文件开头部分，会遗漏后部数据。

**必须**使用 Bash + `grep` 定向提取：

```bash
grep "<关键词>" large_file.csv
```

典型场景：从逐层对比 CSV 中提取特定算子数据、从日志中提取特定层或模块的记录。

---

## LLM 量化实验（LightCompress）

LightCompress 是 LLM 量化实验工具集，属于 `llm` 模块，依赖 OE-LLM 包环境。

| 场景 | Skill | 说明 |
|------|-------|------|
| 单个模型 + 单种量化方法的实验 | `lightcompress-quant-explore` | 执行单次量化实验，生成 PPL 精度报告 |
| 多模型 / 多方法 / 多配置的批量实验 | `lightcompress-batch-quantize` | 编排型 Skill，循环调用 `lightcompress-quant-explore` 并汇总对比表 |

**前置依赖**：LightCompress 任务需要 OE-LLM 包环境（`.horizon/.env.oe-llm-package`），触发前应先完成上方的「OE-LLM 包检查」。

---

## LLM Compression（独立包，非 OE 体系）

> **⚠️ 重要**：`llm_compression` 是**独立于 OE / OE-LLM 的工具包**，有自己的代码仓库和 conda 环境。不属于 Horizon OpenExplorer 工具链，不走 OE 包检查流程。

| 场景 | Skill | 说明 |
|------|-------|------|
| 在 llm_compression 框架中接入新 LLM/VLM 模型 | `llmcompression-add-model` | 编写 blocks/、model.py、process_utils.py 等，注册并验证新模型 |
| LLM 校准/评测/编译/板端推理等日常操作 | `llmcompression-operations` | 标准 shell 脚本 + YAML 配置驱动，覆盖 calib.sh、torch_eval.sh、compile.sh、hbm_rpc_eval.sh、quant_analysis.sh |

**环境要求**：
- `llm_compression` 使用**独立的 conda 环境**，不依赖 `.horizon/.env.oe-package` 或 `.horizon/.env.oe-llm-package`
- 路由到此 Skill 时，**跳过 OE 包检查和 OE-LLM 包检查**，直接进入 Skill 执行
- 如果用户尚未配置 llm_compression 环境，应在执行前确认 conda 环境和 `llm_compression` 代码仓库路径

---

## 按需加载参考文档

以下文档**只在相关任务时才需要读取**，不必在每次进入本 Skill 时全部加载：

| 文档 | 路径 | 何时读取 |
|------|------|----------|
| 工作原则 | `references/work-principles.md` | 开始执行任何工具链任务前，了解通用行为准则 |
| 部署工作流 | `references/deployment-workflow.md` | 用户需求涉及量化/编译/部署完整链路时（PTQ/QAT 流程、全链路规范） |
| 路由参考表 | `references/routing-tables.md` | 需要查阅阶段路由或场景路由的意图-Skill 映射表时；涉及批量 HBM 性能评估时 |
| HMCT 工作流补充 | `references/hmct-workflow-guide.md` | 任务涉及 HMCT 量化构建、精度调优、敏感度分析、校准数据处理时 |
| 批量任务策略 | `references/batch-task-strategy.md` | 任务涉及多个模型（>3个）的相同操作时（批量评测、批量编译等） |
| 板端缓存清理 | `references/board-cleanup.md` | 涉及板端部署的任务完成后，清理板端残留文件时 |
| 板端部署预检 | `../ucp/j6-board-monitor/board-preflight.md` | 部署模型到板端前，检查 ION 内存、L2M 配置、模型-板端兼容性时 |
| LLM Compression 日常操作 | `references/llmcompression-operations.md` | 涉及 llm_compression 独立包的校准/评测/编译/板端推理等日常操作时 |
