# 第 2 步：运行分析

根据第 1 步收集的信息，选择正确的命令运行 hb_analyzer。

## 命令格式

### 模式 A：本地模型分析

```bash
hb_analyzer analyze -m <模型路径> --march <架构>
```

**示例**：
```bash
hb_analyzer analyze -m resnet18.onnx --march nash-e
```

### 模式 B：板端实测

```bash
hb_analyzer analyze -m <模型路径> --march <架构> --ip <板子IP>
```

**可选参数**：
- `--username <用户名>` - 默认 root
- `--password <密码>` - 默认为空
- `--port <端口>` - 默认 22

**示例**：
```bash
hb_analyzer analyze -m resnet18.onnx --march nash-e --ip 192.168.1.100
```

### 模式 C：分析 perf JSON

```bash
hb_analyzer analyze --perf <perf_json_路径>
```

**示例**：
```bash
hb_analyzer analyze --perf perf_result.json
```

## 执行注意事项

### 1. 工作目录
hb_analyzer 会在当前目录创建 `.hb_analyzer/` 子目录存放中间文件。

### 2. 执行时间
- 小模型（如 MobileNet）：1-3 分钟
- 中等模型（如 ResNet50）：3-10 分钟
- 大模型（如 YOLO）：10+ 分钟

告知用户预计时间，避免焦虑。

### 3. 进度提示
命令运行时，告诉用户：
"正在运行 hb_analyzer，这可能需要几分钟，请稍候..."

### 4. 完整流程（从 ONNX 开始）

如果输入是 .onnx 文件，工具会自动执行：
1. **Calibration** - 校准（如需要）
2. **Export** - 导出为 HBIR (.bc)
3. **Convert** - 转换为量化模型
4. **Compile** - 编译为 HBM
5. **Perf** - 性能测试

每个阶段都会有日志输出。

## 错误处理

如果命令失败：
1. 检查日志文件：`.hb_analyzer/hb_analyzer_*.log`
2. 查看常见问题：`references/troubleshooting.md`
3. 向用户报告具体错误信息

命令成功后，进入第 3 步。
