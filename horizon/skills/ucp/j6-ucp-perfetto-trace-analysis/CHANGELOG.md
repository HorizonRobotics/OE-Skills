# Changelog

All notable changes to `j6-ucp-perfetto-trace-analysis` should be recorded in this file.

## v1.1.0

### Fixed

- `analyze_trace.py` 现在支持纯 BPU trace（无 CPU 算子）的正常分析，不再因 `debug.op_type` 值不含 "Cpu" 而抛出 `SystemExit`
  - `ProbeResult` 新增 `has_cpu_op_type` 字段，区分"key 不存在"与"key 存在但值不含 cpu"
  - `probe_trace()` 新增 `debug.op_type` key 存在性探测（不限制值包含 cpu），确保纯 BPU trace 中 `debug_op_type_flat_key` 仍被正确解析
  - `build_summary_sql()` / `build_slow_slice_sql()` 新增 `has_cpu_op_type` 参数，当无 CPU 算子时不生成 `NOT EXISTS` 排除子句
  - `run_all_directions_report()` 移除 `debug_op_type_flat_key is None` 的硬性报错；方向 2 在无 CPU 算子时生成 skipped 报告并明确说明原因
  - `main()` 单方向模式：`dnn_name` 传入 `has_cpu_op_type` 让 SQL 自适应；`opinfer_desc_flow` 在无 CPU 算子时输出 Info 提示并正常退出，不再报错

### Changed

- `build_dnn_direction_report()` 根据是否有 CPU 算子动态调整规则描述文案
- `output_probe()` 输出中增加 `has_cpu_op_type` 字段
- 报告元数据新增 `has_cpu_op_type` 标记

## v1.0.1

### Changed

- Renamed skill from `ucp_perfetto_trace_analysis` to `j6-ucp-perfetto-trace-analysis`
- Updated skill directory name and `name` field in SKILL.md frontmatter accordingly

### Added

- `references/bpu_trace_setup.md` — BPU Trace 使能指南，包含硬件开关操作、Perfetto 配置、完整采集流程、调参建议及常见问题排查
- SKILL.md Reference files 索引中增加 `bpu_trace_setup.md` 条目
- SKILL.md 新增 "When to read bpu_trace_setup.md" 段落，明确两个触发场景：
  - 分析时发现 `bpu_trace` 表为空，主动告知用户 BPU 数据缺失原因并提供使能步骤
  - 用户主动询问 BPU Trace 使能/采集方法时，读取并反馈该文档内容

## v1.0.0

Initial tracked version.

### Added

- fixed-scope UCP inference Perfetto analysis skill
- bundled analyzer at `scripts/analyze_trace.py`
- default four-direction Markdown report workflow
- reference docs for setup, output behavior, SQL patterns, and direction semantics
- standalone `USER_GUIDE.md` for end users

### Defined scope

- UCP Critical Path Slice Analysis (Excluding BPU and CPU Operators)
- UCP CPU Operator Slice Analysis
- BPU flow dispatch / response delay
- Corrected BPU effective occupancy

### Output and behavior

- default mode exports a single Markdown report and treats the task as complete
- default completion should not proactively ask for deeper follow-up analysis
- conclusion language can be Chinese or English

### Recovery behavior

- if default `trace_processor_shell` startup fails, first ask whether the user can provide a local usable binary path
- only if the user cannot provide a local path should the workflow suggest manual download guidance
