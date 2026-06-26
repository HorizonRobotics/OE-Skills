# Changelog

## [1.1.0]

### Changed

- 将路由文件拆分为 `SKILL.md`（路由表与算法）和 `ROUTING_OPS.md`（注册/移除流程规范），减少单文件体积，提升可维护性。

## [1.0.0]

### Added

- 新增 `j6-ucp-model-perf-eval` skill：自动化 hrt_model_exec perf 板端性能评测，支持 thread_num/core_id 参数扫描、BPU/CPU 段级耗时分析、结构化报告生成。
- 新增 `j6-ucp-hbm-infer` skill：hbm_infer 远程推理代码生成，支持 L2M 模型推理。
- 新增 `j6-ucp-infer-generating` skill：UCP C++ 推理代码生成，覆盖模型加载、张量准备、预处理、推理执行、输出解析、资源释放全流程。
- 新增 `j6-ucp-perfetto-trace-catcher` skill：从 J6 开发板远程抓取 UCP Perfetto Trace，支持 in_process 和 system 两种模式。
- 新增 `j6-ucp-perfetto-trace-analysis` skill：UCP 推理 Perfetto Trace 分析，支持四个方向的分析报告，内嵌 `analyze_trace.py` 分析脚本。
- 新增 Skill Router 路由机制（`SKILL.md`）：基于关键词和正则的意图路由，按 priority 排序加载命中 skill，避免未使用 skill 占用上下文。
