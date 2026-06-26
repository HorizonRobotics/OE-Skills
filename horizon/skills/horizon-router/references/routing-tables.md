# 路由参考表

> 本文档从 horizon-router SKILL.md 拆出，按需加载。路由的**唯一权威来源**是 `skill-index.json`，本文档仅供参考。

## 阶段路由

### 1. 浮点模型校验

在量化前确认模型合法性。

| 意图 | Skill | 说明 |
|------|-------|------|
| 查看模型信息 / IO / 依赖（命令行输出，**默认**） | `horizon-tc-ui` | `hb_model_info model.onnx` |
| 快速验证 ONNX 能否走通转换流程 | `hmct-workflow` | 路由 B：check，使用随机数据 |
| 可视化模型结构（需浏览器） | `horizon-tc-ui` | `hb_model_info -v`，**无 GUI 环境下不要用** |

### 2. 校准数据准备（PTQ）

| 意图 | Skill | 说明 |
|------|-------|------|
| 评估数据预处理 | `horizon-tc-ui` | `hb_eval_preprocess` |

### 3. 量化

**PTQ：**

| 意图 | Skill | 说明 |
|------|-------|------|
| 完整量化构建 | `hmct-workflow` | 路由 A：build，需校准数据 |
| 快速验证（无校准数据） | `hmct-workflow` | 路由 B：check，使用随机数据 |

**QAT：**

| 意图 | Skill | 说明 |
|------|-------|------|
| 浮点模型 → QAT 适配（set_march、QDQ、prepare、fake quant） | `j6-plugin-adaptation` | |
| 导出 HBIR / BC | `j6-plugin-export` | |
| 量化 → 导出 → 编译全流程代码生成 | `j6-plugin-hbdk-generating` | 编排型 Skill |

> **量化配置默认**：QAT 导出和全流程代码生成中，量化配置默认使用全 int8。如果用户未指定混合精度，不要主动升高算子精度。全 int8 精度不达标时，先路由到 `j6-plugin-precision-tuning` 做诊断，再根据敏感度结果决定混合精度策略。

### 4. 精度调优

量化后精度不达标时进入。

**路由判断：训练侧问题 vs 部署侧问题**

| 问题类型 | 典型现象 | 路由 |
|---------|---------|------|
| 训练侧精度问题 | calibration 掉点、QAT loss 不收敛、混合精度调优 | `j6-plugin-precision-tuning` |
| 部署侧一致性问题 | 训练侧精度正常，export/convert/compile/HBM 掉点 | `j6-plugin-consistency-debug` |

| 意图 | Skill | 说明 |
|------|-------|------|
| PTQ cosine similarity 不达标 | `hmct-workflow` | 路由 C：节点敏感度 → 混精度回退 → 渐进阈值调优 |
| PTQ 单项 debug（灵敏度 / 数据分布 / 累积误差） | `hmct-workflow` | 路由 D：`hmct-debugger` CLI |
| floatvscalib debug 结果解读（量化误差分析、截断/舍入误差分类、优化建议） | `j6-plugin-precision-tuning` | 分析 floatvscalib/ 目录中的逐层对比数据，分类误差类型并提供修复方案 |
| Calibration 精度不达标 / QAT 精度崩溃 / 混合精度调优 | `j6-plugin-precision-tuning` | PyTorch 侧 calibration/QAT 精度调优，含 int8/int16/fp16 混合精度 |
| QAT 训练 loss 不收敛 | `j6-plugin-precision-tuning` | 排查训练 pipeline、fake quant 使用方式、float finetune |
| 训练正常但 export/convert/compile/HBM 掉点 | `j6-plugin-consistency-debug` | 按 qat.pt → qat.export.pt → qat.bc → quantized.bc → hbm 分段定位 |
| 板端推理精度（量化后 vs 板端输出） | `j6-ucp-hbm-infer` | HBM 精度评测 |

**精度调优前置检查（必须执行）**：

当任务涉及"精度调优"或"精度不达标"时，在进入调优流程前**必须**完成以下检查：

```
精度调优前置检查：
□ 1. 当前精度基线是否已测量？ → [是/否，如果否，先测量]
□ 2. 敏感度分析是否已完成？ → [是/否，如果否，先路由到敏感度分析]
□ 3. 如果已有 QAT checkpoint：
   → checkpoint 的量化配置是否与当前目标一致？
   → 是否存在已知的配置缺陷（如错误的 dtype、缺失的 EMA、不合理的学习率）？
```

**⛔ 禁止在没有敏感度分析结果的情况下，仅凭经验或已有 checkpoint 进行精度调优。**
已有 checkpoint 可能使用过时的量化配置，必须验证其与当前目标的兼容性。

### 5. 编译

| 链路 | 编译工具 | 说明 |
|------|---------|------|
| **PTQ**（量化后 ONNX → HBM） | `horizon-tc-ui` | `hb_compile` CLI |
| **QAT**（BC → HBM） | `j6-hbdk-compile` | YAML 配置驱动，有用户确认门禁 |
| HBDK API 级别（细粒度控制） | `hbdk-manual` | `hbdk4.compiler.compile()` |
| 从 PTQ 配置导入编译参数 | `j6-hbdk-compile` | `--ptq-config` |
| 仅生成/补全配置（不编译） | `horizon-tc-ui` | `hb_config_generator` |

**判断方法**：看用户手里有什么文件。PTQ `.onnx` → `horizon-tc-ui`；QAT `.bc` → `j6-hbdk-compile`。不确定时先确认来源。

### 6. 数学等价性能优化（可选）

编译后对 HBM 做数学等价变换以提升性能，按需使用，功能开发中，暂不考虑。

### 7. HBM 精度验证

| 意图 | Skill | 说明 |
|------|-------|------|
| 量化前后一致性验证（cosine / MSE） | `horizon-tc-ui` | `hb_verifier` |
| 训练侧精度正常但编译/板端掉点 | `j6-plugin-consistency-debug` | 分段定位 export/convert/compile 一致性问题 |
| 板端推理精度验证 | `j6-ucp-hbm-infer` | HBM 在目标设备上评测 |
| QAT model_check_result.txt 分析 | `j6-plugin-model-check-result` | |

### 8. UCP 部署

| 意图 | Skill | 说明 |
|------|-------|------|
| UCP/DNN C++ 推理代码生成 | `j6-ucp-infer-generating` | |
| Python SDK / hbm_infer / 板端精度评测 | `j6-ucp-hbm-infer` | |

### 9. 性能分析

贯穿多个阶段，按需使用。

| 意图 | Skill | 说明 |
|------|-------|------|
| `hb_analyzer` 单模型性能分析（带宽、计算量、利用率） | `hb-analyzer-performance` | 默认"性能分析"走这里。**例外**：用户要求批量评估目录下多个 HBM 模型时，不走这里，见下方「批量 HBM 性能评估」 |
| `hbm_perf` 实测（板端实际延时） | `hbdk-manual` | 用户说"实测 perf"时走这里 |
| 板端性能评测 / benchmark / hrt_model_exec perf | `j6-ucp-model-perf-eval` | |
| 推理 trace / perfetto 分析 | `j6-ucp-perfetto-trace-analysis` | `.pftrace` 定位推理管线瓶颈 |
| Perfetto trace 采集 / 抓 trace | `j6-ucp-perfetto-trace-catcher` | 板端 trace 采集与拉取 |

### 10. 板端资源监控

涉及板端 BPU 占用率、DDR 带宽、内存使用等实时监控场景。**路由到 `j6-board-monitor` skill**。

| 意图 | Skill | 说明 |
|------|-------|------|
| BPU 占用率监控 | `j6-board-monitor` | Scenario B: 独立监控 |
| DDR 带宽监控 | `j6-board-monitor` | 注意 J6P 需 `-t bpu_p0` |
| 内存使用监控 | `j6-board-monitor` | ION + 系统内存 |
| 设定帧率推理 + 监控 | `j6-board-monitor` | Scenario A: 受控推理 + 同步监控 |
| 部署前板端硬件兼容性检查 | `j6-board-monitor` | 检查 ION 内存、L2M 配置、模型-板端兼容性，见 `board-preflight.md` |
| LLM 模型板端推理期间资源监控 | `j6-board-monitor` | Scenario C: simple_demo_request 循环推理 + 同步监控 |
| 推理性能评测（无监控） | `j6-ucp-model-perf-eval` | 纯性能 benchmark，非监控场景 |

> **重要区分**：
> - 用户要求"监控 BPU/DDR/内存" → `j6-board-monitor`
> - 用户要求"评测模型延时/FPS"（无监控需求） → `j6-ucp-model-perf-eval`
> - 用户要求"推理时监控资源" → `j6-board-monitor`（Scenario A）
>
> **禁止**：使用 `hbm_infer`/gRPC 进行高频推理监控。gRPC 通信开销约 6.8s/帧，无法达到 >0.15Hz 的实际帧率。

### 11. LLM 量化实验（LightCompress）

LightCompress 是 LLM 量化实验工具，支持 RTN/GPTQ/SmoothQuant/AWQ 等方法，产出 PPL 精度报告。依赖 OE-LLM 包环境。

| 意图 | Skill | 说明 |
|------|-------|------|
| 单模型 + 单方法量化实验 | `lightcompress-quant-explore` | 生成 YAML 配置 → 用户确认 → 执行实验 → PPL 报告 |
| 多模型 / 多方法批量实验 | `lightcompress-batch-quantize` | 编排型 Skill，循环调用 `lightcompress-quant-explore`，汇总对比表 |
| 量化精度缓存查询 | `quant-accuracy-cache` | 实验前查缓存跳过重复，实验后保存结果 |

> **触发关键词**：LightCompress、量化实验、PPL 评估、RTN、GPTQ、SmoothQuant、AWQ、批量量化、量化对比

---

## 批量 HBM 性能评估

> **⛔ 本节优先于上方路由表**：当用户要求评估目录下多个 HBM 模型的延时、计算量、带宽时，必须按本节执行，不要路由到 `hb-analyzer-performance`。

必须严格遵守 SKILL.md 中的「批量任务处理策略」——有 Agent 工具时拆分并行 sub-agent（策略 A），无 Agent 工具时写脚本 + 等待通知（策略 B）。禁止轮询进度。

> **⛔ 执行前必须自检**：在开始任何操作之前，先输出以下检查清单：
> 1. 目录下共有 N 个 HBM 模型
> 2. 我是否有 Agent 工具？→ 有则用策略 A（拆分并行），无则用策略 B（脚本 + 等待通知）
> 3. 确认：我不会反复轮询进度
>
> 如果你的计划是写单个脚本 + 反复检查进度 → **STOP，重新规划**。

| 指标 | Skill | 命令 | 需 HPM |
|------|-------|------|--------|
| 实测延时 / FPS | `j6-ucp-model-perf-eval` | `hrt_model_exec perf --profile_path` | 否 |
| 计算量 / 带宽 / debug 编译标志 | `hbdk-manual` → `hbm-perf.md` | `hbm_perf(model)` 静态模式（不传 `remote_ip`） | 否 |

> hwperf 失败（无 `/dev/hpm`）时，上述两个工具仍可正常工作。`hbm_perf()` 静态模式返回的 JSON 中 `compiling options` 字段可检查模型是否开启了 debug 编译。

**报告要求**：批量评估报告不仅要汇总性能指标，还必须分析每个模型的编译配置（`compiling options` / `compile opt option`），标注哪些模型编译时未开启 debug（debug 模式下才能获取完整的 hwperf 逐层数据）。

---

## 场景路由

以下场景中，用户请求可能同时涉及多个阶段。先明确意图，再路由。

### 场景 1：模型可视化

| 意图 | Skill | 说明 |
|------|-------|------|
| 查看模型信息（命令行输出，**默认**） | `horizon-tc-ui` | `hb_model_info` |
| 交互式可视化（需浏览器） | `horizon-tc-ui` | `hb_model_info -v`，**无 GUI 环境不要用** |
| 对比两个计算图差异 | `j6-plugin-graph-diff` | FX Graph diff 报告 |
| 查看编译中间阶段结构 | `j6-hbdk-compile` | 副产物 `*_converted.onnx`、`*_removed.onnx` |

### 场景 2：精度调优

**Plugin 链路（QAT）精度问题路由决策树：**

```
精度不达标
├── 用户提供了 floatvscalib/ 目录要求解读？
│   └── 是 → j6-plugin-precision-tuning（floatvscalib debug 结果解读，含截断/舍入误差分类）
├── calibration / QAT 阶段精度就不达标？
│   ├── 是 → j6-plugin-precision-tuning（PyTorch 侧精度调优）
│   └── 否（训练侧精度正常）
│       ├── export/pre_export 掉点？ → j6-plugin-consistency-debug（阶段 1）
│       ├── convert 掉点？          → j6-plugin-consistency-debug（阶段 2）
│       ├── compile/HBM 掉点？      → j6-plugin-consistency-debug（阶段 3）
│       └── 不确定从哪开始？        → j6-plugin-consistency-debug（先做基线确认）
```

**PTQ 链路精度问题**仍路由到 `hmct-workflow`。

见阶段路由中的「4. 精度调优」。

### 场景 3：编译配置

| 意图 | Skill | 说明 |
|------|-------|------|
| 生成/补全/校验配置（不编译） | `horizon-tc-ui` | `hb_config_generator` |
| 生成配置并执行编译 | 按链路区分 | 见阶段路由中的「5. 编译」 |
| 从 PTQ 配置导入编译参数 | `j6-hbdk-compile` | `--ptq-config` |

### 场景 4：模型验证

| 意图 | Skill | 说明 |
|------|-------|------|
| 量化前后一致性验证 | `horizon-tc-ui` | `hb_verifier` |
| 快速验证能否走通转换 | `hmct-workflow` | check，随机数据 |
| 板端推理验证 | `j6-ucp-hbm-infer` | |
| 编译阶段合法性检查 | `j6-hbdk-compile` | HzCalibration / bc 阶段门禁 |
| 检查模型是否有 CPU 算子 | `horizon-tc-ui` | `hb_model_info` 查看算子列表，或查看编译 HTML 报告中的算子分布；关注 Gather、ScatterElements、Cast 等常见 CPU fallback 算子 |

### 场景 5：LLM 模型接入（llm_compression）

> **⚠️ llm_compression 是独立于 OE 的工具包**，有自己的代码仓库和 conda 环境，不走 OE / OE-LLM 包检查流程。

> **LLM vs 非 LLM 包路由区分**：
> - 涉及 `llm_compression` 框架操作（校准/编译/板端推理/量化分析）→ `llmcompression-*` skills，**不走 OE 包检查**
> - 涉及 LightCompress 量化实验（RTN/GPTQ/AWQ/SmoothQuant PPL 评测）→ `lightcompress-*` skills，走 OE-LLM 包检查
> - 涉及普通 PTQ/QAT 量化编译（.onnx/.bc → .hbm）→ `hmct-workflow` / `horizon-tc-ui` / `j6-hbdk-compile`，走 OE 包检查
> - **判断依据**：看用户使用的工具和数据。llm_compression 有自己的 scripts/ 目录和 YAML 配置；LightCompress 有 PPL 报告；普通量化走 hb_compile/hmct。

| 意图 | Skill | 说明 |
|------|-------|------|
| 在 llm_compression 中新增 LLM 模型支持 | `llmcompression-add-model` | 编写 blocks/、model.py、process_utils.py、注册并验证 |
| 在 llm_compression 中新增 VLM 模型支持 | `llmcompression-add-model` | 同上，额外处理 vision encoder 和 mRoPE |
| 对齐 transformers 新模型结构 | `llmcompression-add-model` | 从 transformers 源码提取模型结构并适配 |
| LLM 校准/评测/编译/板端推理等日常操作 | `llmcompression-operations` | 覆盖 calib.sh、torch_eval.sh、compile.sh、hbm_rpc_eval.sh、quant_analysis.sh |
| LLM 编译 GPU 预检要求 | `llmcompression-operations` | compile 阶段需要 GPU 环境 |
| LLM 板端推理期间监控 BPU/内存 | `j6-board-monitor` | 需要先部署模型并启动循环推理，再启动监控 |

> **触发关键词**：新增模型、接入模型、add model、llm_compression 模型适配、模型注册、模型集成、校准、calib、torch_eval、compile、hbm_rpc_eval、quant_analysis、LLM 编译
