# Bypass 模式执行指南

> 本文件是 `j6-plugin-consistency-debug` 的补充。当工作区处于 bypass 模式（自动确认 / 最少交互）时，与 SKILL.md 配合使用。

## 可自动确认 / 自动执行的步骤

| 步骤 | 自动执行方式 | 信息来源 |
| --- | --- | --- |
| 获取平台 / march | 从 `.horizon/.env.board` 的 `BOARD_TYPE` 推断（`nash-e/m` → J6E/M，`nash-p` → J6P） | 环境变量 / `.env.board` |
| 获取 plugin / hbdk 版本 | 运行 `pip show horizon-plugin-pytorch hbdk4-compiler horizon-plugin-profiler` 自动采集 | 包管理器 |
| 选择排查阶段 | 根据用户提供的产物可用性自动判断（有 `qat.bc` 无 `quantized.bc` → 先看 export；有 `quantized.bc` → 先看 convert） | 文件系统探测 |
| 运行 QuantAnalysis | 如果 `badcase`、`dataloader`、基线和分析模型都已就绪，直接运行 `auto_find_bad_case → run → compare_per_layer → sensitivity`，不逐步确认 | 已有产物 |
| 读取分析产出物 | 自动读取 `compare_per_layer_out.csv`、`output_xxx_sensitive_ops.txt`、`badcase.txt` 并汇总 | 产出目录 |
| 部署侧排查清单 | 逐项检查预处理/layout/scale 脚本时，自动读取配置文件并列举差异，不逐项询问 | 用户代码 |
| 输出报告 | 分析完成后直接按模板输出报告，不询问是否生成 | — |

## 仍需用户确认的步骤

| 步骤 | 为什么不能自动 |
| --- | --- |
| 确认异常现象是否真实存在 | 单帧数值差异不等于精度问题，需要用户确认是稳定可复现的掉点 |
| 指定 badcase 或评测数据集 | 如果用户未提供且无法从工作区自动发现，必须询问 |
| 修改 QAT 训练脚本（如 ConsistencyStrategy） | 涉及重新训练，代价大，必须确认 |
| 判断根因是否明确 | 证据不足时应报告"暂不能判断"而非强行归因 |
| bc_editor 删除 fake quant | 结构性改动，删除范围需用户确认 |

## 环境信息自动采集优先级

```
1. .horizon/.env.board → BOARD_TYPE, BOARD_IP
2. 环境变量 → HORIZON_BOARD_TYPE, OE_BOARD_TYPE, BOARD_TYPE
3. AGENTS.md / CLAUDE.md 中的板卡描述
4. pip show → horizon-plugin-pytorch, hbdk4-compiler, horizon-plugin-profiler 版本
5. 项目文件 → model_check_result.txt, fx_graph.txt 存在性
```

如果以上信息足够定位阶段且有可用产物，bypass 模式下应直接开始分析，不逐步反问。
