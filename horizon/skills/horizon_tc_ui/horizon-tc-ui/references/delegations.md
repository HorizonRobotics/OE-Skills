# Delegate 规则

本文件定义 horizon-tc-ui Skill 何时将请求 delegate 到外部同源 Skill。

## Delegate 规则清单

### 1. 精度分析 → `horizon-model-cosine-analyzer`

**触发关键词**：精度分析、cosine 掉点、consistency 不达标、逐层对比、定位精度问题、哪一层精度有问题

**判定条件**：
- 用户已完成 hb_verifier 运行，拿到了 cosine/consistency 结果，想进一步分析**根因**
- 用户询问「为什么精度掉点」「哪一层导致掉点」「如何修复精度问题」
- 需要进行逐层 cosine 对比、tensor 级别的数据分析

**不 delegate 的情况**：
- 用户只是需要运行 hb_verifier 命令 → 留在本 Skill 的 [task-board-deploy-verify.md](tasks/task-board-deploy-verify.md)
- 用户需要调整 calibration 参数来改善精度 → 留在本 Skill 的 [task-calibration-tuning.md](tasks/task-calibration-tuning.md)

**应保持的上下文**：
- hb_verifier 输出日志或 cosine/consistency 结果
- 使用的 YAML 配置（特别是 calibration_parameters）
- 模型类型和 march

---

### 2. 性能分析 → `hb-analyzer-performance`

**触发关键词**：性能瓶颈、算子耗时、BPU 利用率、内存占用优化、性能调优、perf 分析

**判定条件**：
- 用户已有编译产出的 HBM 和 perf.json，想分析性能瓶颈
- 用户询问「哪里是性能瓶颈」「如何优化性能」「BPU 利用率低怎么办」
- 需要算子级别的耗时分析、内存布局优化建议

**不 delegate 的情况**：
- 用户只是想运行 hb_compile --fast-perf 做快速性能估算 → 留在本 Skill 的 [task-fast-perf.md](tasks/task-fast-perf.md)
- 用户只是想运行 hb_analyzer analyze 命令 → 留在本 Skill 的 [tools/hb_analyzer.md](tools/hb_analyzer.md)

**应保持的上下文**：
- HBM 模型路径
- perf.json 文件路径
- march 和 core_num 配置
- hb_analyzer_report.html（如果已生成）

---

## 模糊场景处理原则

### 编译 + 性能

用户同时提到编译和性能问题时：
1. **先确认编译是否成功**：检查是否已产出 .hbm 文件
2. 如果编译未完成 → 先走编译流程 [task-float-to-hbm.md](tasks/task-float-to-hbm.md)
3. 编译完成后 → 如需深度性能分析，delegate 到 `hb-analyzer-performance`

### 精度 + 性能

用户同时关心精度和性能时：
1. **先确认精度是否达标**：精度是前提条件
2. 精度未达标 → 先走精度调优 [task-calibration-tuning.md](tasks/task-calibration-tuning.md) 或 delegate 到 `horizon-model-cosine-analyzer`
3. 精度达标后 → 再分析性能

### 编译失败 + 精度问题

用户报告编译失败且提到精度：
1. **先解决编译问题**：编译失败时精度无从谈起
2. 走编译排查流程 [task-compile-debug.md](tasks/task-compile-debug.md)
3. 编译成功后再处理精度问题

### YAML 配置 + 其他

用户需要写 YAML 配置同时提到其他需求：
1. 先帮助生成/完善 YAML 配置 → [task-yaml-authoring.md](tasks/task-yaml-authoring.md)
2. 配置完成后根据其他需求路由到对应任务

---

## Delegate 执行要点

1. **保留上下文**：delegate 时传递已有的命令输出、文件路径、配置信息
2. **明确边界**：告诉用户本 Skill 已完成了什么，接下来交给哪个 Skill 做什么
3. **可回退**：delegate 后如果需要回到本 Skill 继续（如精度分析后需要改 YAML），明确说明
