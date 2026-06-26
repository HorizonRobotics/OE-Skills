# Bypass 模式执行指南

> 本文件是 `j6-plugin-precision-tuning` 的补充。当工作区处于 bypass 模式（自动确认 / 最少交互）时，与 SKILL.md 配合使用。

## 可自动确认 / 自动执行的步骤

| 步骤 | 自动执行方式 | 信息来源 |
| --- | --- | --- |
| 获取平台 / march | 从 `.horizon/.env.board` 的 `BOARD_TYPE` 推断（`nash-e/m` → J6E/M，`nash-p` → J6P） | 环境变量 / `.env.board` |
| 获取 plugin / profiler 版本 | 运行 `pip show horizon-plugin-pytorch horizon-plugin-profiler` 自动采集 | 包管理器 |
| 判断问题阶段（Calibration vs QAT） | 根据用户描述中的关键词自动归类（"校准掉点" → calibration，"loss 不收敛" → QAT） | 用户输入 |
| 运行 QuantAnalysis | 如果 `float_model`、`calibration_model`、`dataloader` 都已就绪，直接运行完整流程（`auto_find_bad_case → run → compare_per_layer → sensitivity`） | 已有产物 |
| 读取分析产出物 | 自动读取 `compare_per_layer_out.csv`、`output_xxx_sensitive_ops.txt` 并汇总 | 产出目录 |
| HistogramObserver.reset_scale | 用户指定 method 和 dtype 后直接执行，不逐步确认 | 用户指令 |
| 生成混合精度配置代码 | 根据平台自动选择默认模板（J6E/M: int8/int16 路线；J6P: fp16 + conv int8/16 路线） | `.env.board` |
| 输出报告 | 分析完成后直接按模板输出报告，不询问是否生成 | — |

## 仍需用户确认的步骤

| 步骤 | 为什么不能自动 |
| --- | --- |
| 指定评测指标和目标阈值 | "精度达标"的标准因任务而异，需要用户定义 |
| 提供 dataloader 和校准数据 | 如果工作区中无法自动发现，必须询问 |
| 混合精度的 topk_or_ratio 和 dtype 选择 | 直接影响推理性能，需用户根据业务需求决定 |
| 修改 QAT 训练超参（lr、weight decay、scheduler） | 训练参数高度依赖任务，不能盲目设置 |
| 是否重新训练 | QAT 重训代价大，必须确认 |
| 全 int16 仍不达标时的下一步方向 | 可能涉及模型结构改动或 pipeline 问题，不能自行决定 |

## 环境信息自动采集优先级

```
1. .horizon/.env.board → BOARD_TYPE（决定 J6E/M vs J6P 的默认混合精度路线）
2. 环境变量 → HORIZON_BOARD_TYPE, OE_BOARD_TYPE, BOARD_TYPE
3. AGENTS.md / CLAUDE.md 中的板卡描述
4. pip show → horizon-plugin-pytorch, horizon-plugin-profiler 版本
5. 项目文件 → model_check_result.txt, 已有 sensitivity 表
```

如果以上信息足够判断阶段归属和默认配置，bypass 模式下应直接开始分析或生成配置代码，不逐步反问。

## Bypass 模式下的平台默认配置

| 平台 | 默认混合精度起点 | 说明 |
| --- | --- | --- |
| J6E/M | 全 int16 → 全 int8 → int8/int16 混合 | 先确认 int16 上限，再逐步降精度 |
| J6P | fp16 默认 + Conv/Matmul int8 | 利用 J6P 更强的浮点能力，GEMM 算子从 int8 开始权衡 |
