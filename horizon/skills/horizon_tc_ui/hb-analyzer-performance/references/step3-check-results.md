# 第 3 步：检查结果

命令执行完成后，验证输出文件是否正确生成。

## 检查输出文件

### 1. 主要输出

在当前目录查找：

```bash
ls -lh hb_analyzer_report.html
```

**预期**：应该存在此文件（几百 KB）

### 2. 分析摘要

```bash
ls -lh .hb_analyzer/analysis_summary.json
```

**预期**：JSON 文件，包含详细指标

### 3. 日志文件

```bash
ls -lh .hb_analyzer/hb_analyzer_*.log
```

**预期**：日志文件，包含执行过程

## 验证成功标志

### 检查日志中的关键信息

```bash
grep "Analysis Summary" .hb_analyzer/hb_analyzer_*.log
```

**预期输出**：应该看到 "Analysis Summary" 字样

### 检查是否有错误

```bash
grep -i "error\|failed" .hb_analyzer/hb_analyzer_*.log
```

**预期**：无错误或仅有警告

## 如果文件缺失

1. 检查命令是否成功执行（返回码 0）
2. 查看日志文件找出失败原因
3. 参考 `troubleshooting.md` 解决问题

## 下一步

文件验证通过后，进入第 4 步解读结果。
