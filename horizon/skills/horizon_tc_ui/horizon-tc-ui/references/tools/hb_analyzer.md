# hb_analyzer 工具参考

## 1. 概述

`hb_analyzer` 是性能分析与模型可视化工具，使用 `click.group` 提供两个子命令：`analyze`（分析模型性能）和 `visualize`（可视化模型结构）。它支持本地模型分析和远程板端性能数据采集。

**入口点**（`setup.py` 中的 `console_scripts`）：

```
hb_analyzer = horizon_tc_ui.hb_analyzer:hb_analyzer
```

## 2. 命令签名

### 子命令：analyze

```bash
hb_analyzer analyze [OPTIONS]
```

| 选项 | 类型 | 默认值 | 必填 | 说明 |
|------|------|--------|------|------|
| `-m, --model` | `str` | `None` | 条件必填 | 模型文件路径 |
| `--march` | `click.Choice(...)` | `None` | 条件必填 | 目标 BPU 架构，合法值见 march 列表 |
| `--perf` | `str` | `None` | 条件必填 | 已有的性能分析 JSON 文件路径 |
| `--ip` | `str` | `None` | 否 | 板端 IP 地址 |
| `--username` | `str` | `"root"` | 否 | 板端 SSH 用户名 |
| `--password` | `str` | `""` | 否 | 板端 SSH 密码 |
| `--port` | `int` | `22` | 否 | 板端 SSH 端口 |

**参数说明**：
- `-m/--model`、`--perf`、`--march` 三者中至少需要提供模型或 perf JSON 之一，且需要配合 `--march` 使用
- 提供 `--ip` 时，工具将连接远程板端获取性能数据

### 子命令：visualize

```bash
hb_analyzer visualize [OPTIONS]
```

| 选项 | 类型 | 默认值 | 必填 | 说明 |
|------|------|--------|------|------|
| `-m, --model` | `str` | 无 | 是 | 模型文件路径（`.hbm` / `.bc` / `.onnx`） |

> **⚠️ 严重警告：`visualize` 子命令会阻塞进程！**
>
> `visualize` 子命令会启动 HTTP 服务器进行可视化，**进程将永久挂起、不会自动退出**。
> - **必须**手动 `Ctrl+C` 终止，否则后续所有操作都会被卡住
> - **禁止**在自动化脚本/流水线中直接调用，除非在后台运行（`&`）或设置了超时机制
> - AI agent 调用此命令时，**必须**以后台方式运行或提醒用户手动关闭

## 3. 典型调用示例

### 最小调用（本地模型分析）

```bash
hb_analyzer analyze -m model.hbm --march nash-e
```

### 常用调用（使用已有 perf JSON 分析）

```bash
hb_analyzer analyze --perf model.json --march nash-e
```

### 全量调用（远程板端分析）

```bash
hb_analyzer analyze -m model.hbm --march nash-p \
  --ip 192.168.1.100 \
  --username root \
  --password password123 \
  --port 22
```

### 可视化（BC 模型）

```bash
hb_analyzer visualize -m quantized_model.bc
```

### 可视化（HBM 模型）

```bash
hb_analyzer visualize -m model.hbm
```

### 可视化（ONNX 模型）

```bash
hb_analyzer visualize -m model.onnx
```

## 4. 输入要求

### 文件格式

| 子命令 | 支持的模型格式 |
|--------|----------------|
| analyze | `.hbm`（配合 `--march`）、或已有的性能 JSON（配合 `--perf`） |
| visualize | `.hbm`、`.bc`、`.onnx` |

### march 合法值

```
nash-b-lite, nash-b, nash-b-plus, nash-e, nash-m, nash-p, nash-starry-p, nash-h
```

## 5. 输出产物

### analyze 子命令

| 产物 | 路径 | 说明 |
|------|------|------|
| Per-graph JSON | `.hb_analyzer/<graph_name>.json` | 单图性能数据（核心：FPS、latency、计算量、带宽等指标均在此文件） |
| 分析摘要 | `.hb_analyzer/analysis_summary.json` | 汇总分析数据（注意：`hbm_key_indicators` 是 `list[{title, value, unit}]`，不是 dict） |
| 分析报告 | `.hb_analyzer/hb_analyzer_report.html` | 可视化性能报告（HTML） |
| 日志 | `./hb_analyzer.log` | 执行日志 |

### visualize 子命令

| 产物 | 路径 | 说明 |
|------|------|------|
| HBM 可视化 | `.hb_analyzer/{name}.prototxt` | 由 `hbrt4-disas --netron` 生成 |
| BC 可视化 | `.hb_analyzer/{name}.onnx` | 由 HBIR 可视化转换生成 |
| ONNX 可视化 | 直接使用原始文件 | 不生成额外文件 |
| 日志 | `./hb_analyzer.log` | 执行日志 |

### 目录结构

```
.hb_analyzer/
├── <graph_name>.json          # 单图性能数据（核心数据源：FPS、latency、计算量等）
├── analysis_summary.json      # 汇总分析数据（hbm_key_indicators 为 list 结构）
├── {model_name}.prototxt      # HBM 可视化产物
├── {model_name}.onnx          # BC 可视化产物
└── hb_analyzer_report.html    # 性能分析报告
```

> **⚠️ 重要**：Per-graph JSON（如 `e2e_dt_3in1.json`）是提取延时和 FPS 的**主要数据源**。`analysis_summary.json` 中的 `hbm_key_indicators` 是 `list[{title, value, unit}]`，**不是** flat dict，提取时需做 list → dict 转换。

### 日志位置

- 日志文件：`./hb_analyzer.log`（当前工作目录）
- console 级别：`INFO`；file 级别：`DEBUG`

## 6. 退出码与错误约定

| 退出码 | 含义 |
|--------|------|
| `0` | 成功完成 |
| `-1` | 执行过程中发生异常（由 `@on_exception_exit` 装饰器处理） |

常见错误场景：
- 模型文件不存在 → 运行时错误
- `--march` 值不在合法列表中 → `click.BadParameter`
- 板端 SSH 连接失败 → `paramiko` 异常
- 模型格式不支持 → 分析或可视化阶段报错

## 7. 版本兼容性

| 依赖 | 最低版本 | 说明 |
|------|----------|------|
| hbdk4-compiler | 无特殊要求 | 性能分析需要 |
| hmct | 无特殊要求 | 无版本限制 |

## 8. 源码入口

| 模块 | 路径 | 说明 |
|------|------|------|
| CLI 入口 | `horizon_tc_ui/hb_analyzer.py` | `hb_analyzer()` click group |
| analyze 子命令 | `horizon_tc_ui/hb_analyzer.py` | `analyze()` 函数 |
| visualize 子命令 | `horizon_tc_ui/hb_analyzer.py` | `visualize()` 函数 |
| 分析器核心 | `horizon_tc_ui/analyzer/` | `HBAnalyzer` 类 |
| 可视化工具 | `horizon_tc_ui/visualize.py` | `Visualize` 类 |

> **注意**：如需深度的性能瓶颈分析（算子耗时、BPU 利用率、内存优化），请 delegate 到 `hb-analyzer-performance` Skill。本文件仅覆盖 `hb_analyzer` 命令的使用。
