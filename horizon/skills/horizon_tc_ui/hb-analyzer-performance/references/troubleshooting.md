# 故障排查

hb_analyzer 常见问题及解决方案。

## 错误 1：缺少 march 参数

**错误信息**：
```
Parameter march is required for onnx or hbir model.
```

**原因**：.onnx 或 .bc 模型需要指定目标架构

**解决**：
```bash
hb_analyzer analyze -m model.onnx --march nash-e
```

## 错误 2：模型文件未找到

**错误信息**：
```
FileNotFoundError: model.onnx not found
```

**解决**：
1. 检查文件路径是否正确
2. 使用绝对路径
3. 确认文件存在：`ls -lh model.onnx`

## 错误 3：march 不一致

**错误信息**：
```
Input march nash-e is inconsistent with model march nash-p
```

**原因**：.bc 模型已包含架构信息，与命令行参数冲突

**解决**：
- 使用模型内置的 march，或
- 重新生成 .bc 模型

## 错误 4：板端连接失败

**错误信息**：
```
SSH connection failed
```

**解决**：
1. 检查 IP 地址是否正确
2. 确认板子在线：`ping <ip>`
3. 测试 SSH 连接：`ssh root@<ip>`
4. 检查防火墙设置

## 错误 5：内存不足

**错误信息**：
```
Out of memory
```

**解决**：
1. 关闭其他程序释放内存
2. 使用更小的模型测试
3. 增加系统交换空间

## 错误 6：依赖缺失

**错误信息**：
```
ModuleNotFoundError: No module named 'hbdk4'
```

**解决**：
```bash
pip install -e .
```

## 日志查看

所有详细日志在：
```bash
cat .hb_analyzer/hb_analyzer_*.log
```

查找错误：
```bash
grep -i error .hb_analyzer/hb_analyzer_*.log
```
