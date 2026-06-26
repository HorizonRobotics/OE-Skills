# 性能分析（Perf Debug）

## 适用场景

**触发关键词**：性能分析、perf、延迟、帧率、内存占用、BPU 利用率、性能优化、hbm_perf

**前置条件**：
- 已编译生成 `.hbm` 模型文件
- 已有 perf JSON 文件（编译时自动生成）
- 已确认目标板端环境（如需板端 perf）

> **重要**：深度性能分析（算子级耗时、BPU 利用率分析、性能优化建议）已 **delegate 到 hb-analyzer-performance skill**。本文档仅覆盖本地工具链的准备工作和基础命令。

## 产出物

| 产物文件 | 路径 | 说明 |
|---------|------|------|
| `{prefix}.hbm` | `{working_dir}/` | HBM 模型文件 |
| `{prefix}.json` | `{working_dir}/` | 性能分析 JSON（编译时自动生成） |
| `<graph_name>.json` | `.hb_analyzer/` | 单图性能数据（核心：FPS、latency、计算量、带宽等指标均在此文件） |
| `analysis_summary.json` | `.hb_analyzer/` | 汇总分析数据（注意：`hbm_key_indicators` 是 `list[{title, value, unit}]`，不是 dict） |
| `hb_analyzer_report.html` | `.hb_analyzer/` | hb_analyzer 生成的 HTML 报告 |
| `hb_analyzer.log` | 当前目录 | hb_analyzer 日志文件 |

## 步骤

### 步骤 1：确认已有 HBM 和 perf JSON

编译 HBM 时会自动生成 perf JSON：

```bash
# 确认 HBM 文件存在
ls -lh model_output/model.hbm

# 确认 perf JSON 文件存在
ls -lh model_output/model.json

# 查看 perf JSON 内容
cat model_output/model.json | python3 -m json.tool
```

如果 perf JSON 不存在，可以手动生成：

```bash
python3 -c "
from hbdk4.compiler import hbm_perf
hbm_perf('model_output/model.hbm', 'model_output/')
"
```

### 步骤 2：使用 hb_model_info 查看基础性能信息

```bash
# 查看模型信息（包含内存信息）
hb_model_info model_output/model.hbm
```

输出包含：
- **内存信息**（来自 perf JSON）：
  - `input memory` - 输入内存占用
  - `output memory` - 输出内存占用
  - `static memory` - 静态内存
  - `dynamic memory` - 动态内存
  - `intermediate memory` - 中间内存
  - `temporary memory` - 临时内存
  - `min memory requirement` - 最小内存需求

### 步骤 3：使用 hb_analyzer analyze 进行性能分析

```bash
# 本地分析（使用已有 HBM 和 perf JSON）
hb_analyzer analyze -m model_output/model.hbm --perf model_output/model.json

# 指定 march 分析（无 HBM 时）
hb_analyzer analyze --march nash-e -m model.onnx

# 板端分析（需要 SSH 连接）
hb_analyzer analyze -m model_output/model.hbm \
  --ip 192.168.1.100 \
  --username root \
  --password password \
  --port 22
```

### 步骤 4：查看分析结果

```bash
# 查看 per-graph JSON（核心性能数据：FPS、latency 等）
ls -lh .hb_analyzer/*.json | grep -v analysis_summary

# 查看 HTML 报告
ls -lh .hb_analyzer/hb_analyzer_report.html

# 查看分析摘要（汇总数据）
cat .hb_analyzer/analysis_summary.json | python3 -m json.tool

# 查看日志
cat hb_analyzer.log
```

> **⚠️ 重要**：Per-graph JSON（如 `e2e_dt_3in1.json`）是提取延时和 FPS 的**主要数据源**。如果缺失，将无法获取 latency 和 FPS。`analysis_summary.json` 中的 `hbm_key_indicators` 是 `list[{title, value, unit}]`，提取时需做 list → dict 转换。

### 步骤 5：使用 hb_analyzer visualize 可视化

> **⚠️ 严重警告：`hb_analyzer visualize` 会阻塞进程，必须手动 `Ctrl+C` 终止！**
>
> 该命令会启动 HTTP 服务器，**进程将永久挂起、不会自动退出**。
> - **禁止**在前台直接运行，否则后续所有操作都会被卡住
> - **推荐做法**：在后台运行（`&`）或直接查看生成的可视化产物文件

```bash
# HBM 模型可视化（生成 prototxt）（⚠️ 阻塞！需 Ctrl+C 终止）
hb_analyzer visualize -m model_output/model.hbm
# 产物：.hb_analyzer/{model_name}.prototxt

# BC 模型可视化（生成 onnx）（⚠️ 阻塞！需 Ctrl+C 终止）
hb_analyzer visualize -m model_output/model_quantized_model.bc
# 产物：.hb_analyzer/{model_name}.onnx

# ONNX 模型可视化（⚠️ 阻塞！需 Ctrl+C 终止）
hb_analyzer visualize -m model.onnx
```

### 步骤 6：Delegate 到 hb-analyzer-performance

当需要深度性能分析时：

> **DELEGATE**: 使用 `hb-analyzer-performance` skill 进行深度性能分析。
>
> 前置准备：
> 1. HBM 模型文件（`model_output/model.hbm`）
> 2. perf JSON 文件（`model_output/model.json`）
> 3. 目标 march 架构信息
> 4. 如需板端 perf，准备 SSH 连接参数（ip、username、password、port）

## 校验清单

- [ ] HBM 文件存在且大小合理
- [ ] perf JSON 文件存在且包含 `summary` 字段
- [ ] perf JSON 中 `min memory requirement` 有合理数值
- [ ] `hb_model_info` 可正常读取模型内存信息
- [ ] `hb_analyzer analyze` 命令执行完成
- [ ] `.hb_analyzer/hb_analyzer_report.html` 文件已生成
- [ ] `.hb_analyzer/<graph_name>.json` per-graph JSON 已生成（至少一个）
- [ ] `.hb_analyzer/analysis_summary.json` 文件已生成
- [ ] 板端分析时 SSH 连接正常（如使用）

## 常见偏差与修法

| 偏差 | 修法 | 对应 troubleshooting |
|-----|------|---------------------|
| perf JSON 不存在 | 重新编译或手动运行 hbm_perf | runtime-errors.md |
| perf JSON 无 memory info | 模型可能无 BPU 算子，检查模型结构 | runtime-errors.md |
| hb_analyzer 命令不存在 | 确认 horizon_tc_ui 已正确安装 | runtime-errors.md |
| 板端 SSH 连接失败 | 检查网络、用户名密码、端口 | board-ssh-errors.md |
| HBM 模型无法加载 | 确认 HBM 文件完整且与当前 HBDK 版本兼容 | runtime-errors.md |

## 相关工具 / 模块链接

- **hb_analyzer**：性能分析工具，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/hb_analyzer.py`
- **HBMHandle**：HBM 操作封装，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/hbm_handle.py`
  - `perf()` - 性能数据获取
  - `check_cpu_ops()` - CPU 算子检查
- **hb_model_info**：模型信息查看 → `task-model-inspection.md`
- **hb_compile**：编译（含 perf 生成）→ `task-float-to-hbm.md`
- **深度性能分析**：delegate 到 `hb-analyzer-performance` skill
