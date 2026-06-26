# hb_verifier 工具参考

## 1. 概述

`hb_verifier` 是用于验证模型精度的对比工具，支持在模拟器（SIM）和/或真实板端（ARM）上运行推理，并将结果与原始模型输出进行对比。它采用四阶段流水线：参数校验 → 数据预处理 → 推理执行 → 结果对比。

**入口点**（`setup.py` 中的 `console_scripts`）：

```
hb_verifier = horizon_tc_ui.hb_verifier:cmd_main
```

## 2. 命令签名

```bash
hb_verifier [OPTIONS]
```

| 选项 | 类型 | 默认值 | 必填 | 隐藏 | 说明 |
|------|------|--------|------|------|------|
| `-m, --model` | `str` | 无 | 是 | 否 | 模型文件路径，支持 onnx/bc/hbm，逗号分隔多个 |
| `-i, --input` | `str`，`multiple=True` | 无 | 是 | 否 | 原始模型输入文件，可多次指定 |
| `-c, --compare_digits` | `int` | `5` | 否 | 否 | 对比的小数位数 |
| `--ip` | `str` | `None` | 否 | 否 | 板端 IP 地址（逗号分隔，数量需与 HBM 模型数匹配） |
| `-u, --username` | `str` | `""` | 否 | 否 | 板端用户名（逗号分隔） |
| `-p, --password` | `str` | `""` | 否 | 否 | 板端密码（逗号分隔） |
| `--port` | `str` | `""` | 否 | 否 | 板端 SSH 端口（逗号分隔） |
| `--remote-root` | `str` | `""` | 否 | 否 | 板端远程根路径（逗号分隔） |
| `-s, --run-sim` | `flag` | `None` | 否 | 是 | 运行模拟器（已废弃，建议使用 `--skip-sim`） |
| `--skip-sim` | `flag` | `False` | 否 | 是 | 跳过模拟器推理 |
| `--skip-arm` | `flag` | `False` | 否 | 是 | 跳过板端推理 |
| `-r, --dump-all-nodes-results` | `flag` | `False` | 否 | 是 | 导出所有节点结果（当前不支持） |
| `-h, --help` | `flag` | - | 否 | 否 | 显示帮助信息 |
| `--version` | `flag` | - | 否 | 否 | 显示版本信息 |

**互斥规则**：
- `--skip-sim` 与 `--skip-arm` 不能同时指定（同时指定会报错）
- `--run-sim` 与 `--skip-sim` 不能同时指定
- `--run-sim` 已废弃，建议使用 `--skip-sim`

## 3. 典型调用示例

### 最小调用（仅模拟器验证）

```bash
hb_verifier -m model.onnx -i input1.bin -i input2.bin
```

### 常用调用（模拟器 + 板端验证）

```bash
hb_verifier -m model.onnx,model.hbm -i input.bin \
  --ip 192.168.1.100 \
  -u root \
  -p password123 \
  --port 22 \
  --remote-root /userdata/verifier
```

### 全量调用（多模型 + 板端 + 指定对比精度）

```bash
hb_verifier -m model.onnx,model1.hbm,model2.hbm \
  -i input1.bin -i input2.bin \
  --ip 192.168.1.100,192.168.1.101 \
  -u root,root \
  -p pass1,pass2 \
  --port 22,22 \
  --remote-root /userdata/v1,/userdata/v2 \
  -c 3
```

### 仅板端验证（跳过模拟器）

```bash
hb_verifier -m model.onnx,model.hbm -i input.bin \
  --skip-sim \
  --ip 192.168.1.100 -u root --remote-root /userdata/verifier
```

### 仅模拟器验证（跳过板端）

```bash
hb_verifier -m model.onnx,model_quantized_model.bc -i input.bin --skip-arm
```

## 4. 输入要求

### 文件格式

- **模型文件**：支持 `.onnx`、`.bc`、`.hbm`，多个模型用逗号分隔
- **输入文件**：原始模型输入文件（通常为 `.bin` 格式的二进制数据），每个输入需单独通过 `-i` 指定

### 板端参数要求

当需要板端验证时（未指定 `--skip-arm`），必须提供以下参数组：

| 参数 | 说明 | 格式 |
|------|------|------|
| `--ip` | 板端 IP | 逗号分隔，数量与 HBM 模型数匹配 |
| `-u, --username` | SSH 用户名 | 逗号分隔 |
| `-p, --password` | SSH 密码 | 逗号分隔（空密码表示无密码认证） |
| `--port` | SSH 端口 | 逗号分隔 |
| `--remote-root` | 远程工作目录 | 逗号分隔 |

## 5. 输出产物

### 控制台输出

- 四阶段流水线的执行日志
- 每个输出 tensor 的 cosine / consistency 对比结果
- 对比结果表格（按输出节点列出各模型的相似度值）

### 日志位置

- 日志文件：`./hb_verifier.log`（当前工作目录）
- console 级别：`INFO`；file 级别：`DEBUG`

### 四阶段流水线

```
参数校验 (VerifierParamsCheck)
    ↓
数据预处理 (VerifierDataPreprocess)
    ↓
推理执行 (VerifierInference)
    ↓
结果对比 (VerifierComparator)
```

## 6. 退出码与错误约定

| 退出码 | 含义 |
|--------|------|
| `0` | 成功完成 |
| `-1` | 执行过程中发生异常（由 `@on_exception_exit` 装饰器处理） |

常见错误场景：
- 同时指定 `--skip-sim` 和 `--skip-arm` → 报错（不支持）
- 同时指定 `--run-sim` 和 `--skip-sim` → `ValueError`
- 板端 SSH 连接失败 → `paramiko.AuthenticationException` 或 `paramiko.SSHException`
- 模型文件不存在或格式不支持 → 参数校验阶段报错
- 输入文件数量与模型输入数量不匹配 → 参数校验阶段报错

## 7. 版本兼容性

| 依赖 | 最低版本 | 说明 |
|------|----------|------|
| hbdk4-compiler | 无特殊要求 | 推理阶段需要 |
| hmct | 无特殊要求 | 无版本限制 |
| paramiko | 已安装 | SSH 连接板端需要 |

## 8. 源码入口

| 模块 | 路径 | 说明 |
|------|------|------|
| CLI 入口 | `horizon_tc_ui/hb_verifier.py` | `cmd_main()` 函数 |
| 主流程 | `horizon_tc_ui/hb_verifier.py` | `verifier()` 函数，编排四阶段流水线 |
| 参数校验 | `horizon_tc_ui/verifier/params_check.py` | `VerifierParamsCheck` 类 |
| 数据预处理 | `horizon_tc_ui/verifier/data_preprocess.py` | `VerifierDataPreprocess` 类 |
| 推理执行 | `horizon_tc_ui/verifier/inference.py` | `VerifierInference` 类 |
| 结果对比 | `horizon_tc_ui/verifier/comparator.py` | `VerifierComparator` 类 |
| 参数结构 | `horizon_tc_ui/verifier/__init__.py` | `VerifierParams` 数据结构 |
