# hb_verifier 板端推理验证

## 适用场景

**触发关键词**：板端推理、板端验证、hb_verifier、SSH、板端部署、一致性验证、板端测试

**前置条件**：
- 已编译生成 `.hbm` 模型文件
- 已有模型输入数据（`.npy` 文件）
- 板端可通过 SSH 连接（如需板端推理）
- 已安装 `horizon_tc_ui` 工具包

## 产出物

| 产物 | 路径 | 说明 |
|-----|------|------|
| 控制台输出 | 终端 | 一致性 / cosine 对比结果 |
| `hb_verifier.log` | 当前目录 | 详细日志（DEBUG 级别） |
| 板端临时文件 | `{remote_root}/` | 板端推理的输入输出数据 |

## 步骤

### 步骤 1：hb_verifier 完整流程

hb_verifier 执行以下四个阶段（源码 `hb_verifier.py:verifier()`）：

```
1. VerifierParamsCheck  → 参数校验
2. VerifierDataPreprocess → 数据预处理
3. VerifierInference    → 推理执行（仿真 + 板端）
4. VerifierComparator   → 结果对比
```

### 步骤 2：基础验证（仅仿真，不连板端）

```bash
# BC vs HBM 一致性对比（consistency 模式）
hb_verifier -m model_output/model_quantized_model.bc,model_output/model.hbm \
  -i input_data.npy \
  --skip-arm
```

**多输入模型**：
```bash
hb_verifier -m model_output/model_quantized_model.bc,model_output/model.hbm \
  -i input0.npy -i input1.npy \
  --skip-arm
```

### 步骤 3：板端推理验证（完整流程）

```bash
hb_verifier -m model_output/model_quantized_model.bc,model_output/model.hbm \
  -i input_data.npy \
  --ip 192.168.1.100 \
  -u root \
  -p password \
  --port 22 \
  --remote-root /userdata/verifier/
```

**板端参数说明**：

| 参数 | 说明 | 默认值 | 注意 |
|-----|------|-------|------|
| `--ip` | 板端 IP 地址 | 空 | 多 HBM 模型时逗号分隔，数量需匹配 |
| `-u` / `--username` | SSH 用户名 | `root` | 多 HBM 时逗号分隔 |
| `-p` / `--password` | SSH 密码 | 空 | 多 HBM 时逗号分隔 |
| `--port` | SSH 端口 | `22` | 多 HBM 时逗号分隔 |
| `--remote-root` | 板端工作目录 | 按架构自动设置 | nash_b: `/userdata/hb_verifier/`，其他: `/map/hb_verifier/` |

> **注意**：板端参数如果是多 HBM 模型（packed model），需要逗号分隔多个值，数量与 HBM 模型数量匹配。`--ip` 填 `None` 表示对应模型不走板端（如 bc vs hbm 时 bc 侧填 `None`）。

### 步骤 4：控制执行阶段

```bash
# 只跑仿真，跳过板端
hb_verifier -m model_output/model_quantized_model.bc,model_output/model.hbm \
  -i input_data.npy \
  --skip-arm

# 只跑板端，跳过仿真
hb_verifier -m model_output/model_quantized_model.bc,model_output/model.hbm \
  -i input_data.npy \
  --skip-sim \
  --ip 192.168.1.100 -u root -p password --port 22 \
  --remote-root /userdata/
```

> **注意**：`--skip-sim` 和 `--skip-arm` 不能同时指定，否则会报错。

### 步骤 5：调整对比精度

```bash
# 设置对比小数位数（默认 5）
hb_verifier -m model_output/model_quantized_model.bc,model_output/model.hbm \
  -i input_data.npy \
  -c 3
```

对比使用 `np.allclose(output1, output2, rtol=0, atol=10^-digits)`。

### 步骤 6：consistency vs cosine 模式

hb_verifier 根据**模型类型组合**自动选择对比模式（源码 `verifier/params_check.py:check_mode()`）：

**consistency 模式**：
- 触发条件：`bc vs hbm` 或 `hbm vs hbm`
- 对比方式：逐元素对比，`np.allclose`
- 输出：是否通过、不匹配比例、最大绝对/相对差异

**cosine 模式**：
- 触发条件：`onnx vs onnx`、`onnx vs bc`、`bc vs bc`
- 对比方式：余弦相似度
- 输出：每个输出 tensor 的 cosine 值（越接近 1 越好）

### 步骤 7：SSH 常见故障快速自检

| 故障 | 检查项 | 修法 |
|-----|-------|------|
| 连接超时 | 板端 IP 是否正确、网络是否通 | `ping {ip}` 检查连通性 |
| 认证失败 | 用户名密码是否正确 | 手动 `ssh {username}@{ip}` 验证 |
| 端口不通 | SSH 端口是否正确（默认 22） | `telnet {ip} {port}` 检查端口 |
| remote_root 不存在 | 板端目录是否存在 | SSH 登录后 `ls {remote_root}` 确认 |
| 权限不足 | 板端用户是否有写权限 | 检查目录权限或使用 root 用户 |
| 多 HBM 参数不匹配 | 板端参数数量是否与 HBM 数量一致 | 确保逗号分隔的参数数量匹配 |

### 步骤 8：查看验证结果

```bash
# 查看日志
cat hb_verifier.log

# 日志中的关键输出：
# - "The model output consistency comparison was successful." → 通过
# - "The model output consistency compare was failed." → 不通过
```

## 校验清单

- [ ] 模型文件存在且后缀正确（`.onnx` / `.bc` / `.hbm`）
- [ ] 仅支持两个模型对比
- [ ] 输入数据文件存在且格式正确（仅支持 `.npy`）
- [ ] `--skip-sim` 和 `--skip-arm` 不同时使用
- [ ] 板端推理时 SSH 连接参数完整（ip、username、password、port、remote-root）
- [ ] 多 HBM 模型时，板端参数数量与 HBM 数量匹配
- [ ] `compare_digits` 值合理（默认 5）
- [ ] 验证完成后日志中包含对比结果
- [ ] consistency 模式：通过或不通过明确
- [ ] cosine 模式：每个输出 tensor 的 cosine 值已输出

## 常见偏差与修法

| 偏差 | 修法 | 对应 troubleshooting |
|-----|------|---------------------|
| `--skip-sim` 和 `--skip-arm` 同时指定 | 去掉其中一个 | board-ssh-errors.md |
| 模型数量不是 2 个 | 每次只对比两个模型 | runtime-errors.md |
| SSH 连接失败 | 检查 IP、端口、用户名密码 | board-ssh-errors.md |
| 板端 remote_root 不存在 | 创建目录或修改路径 | board-ssh-errors.md |
| 输入数据与模型不匹配 | 确认输入 shape 和格式 | runtime-errors.md |
| 多 HBM 参数数量不匹配 | 确保逗号分隔的参数数量与 HBM 数量一致 | board-ssh-errors.md |

## 相关工具 / 模块链接

- **hb_verifier**：板端验证工具，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/hb_verifier.py`
- **VerifierParamsCheck**：参数校验，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/verifier/params_check.py`
- **VerifierDataPreprocess**：数据预处理，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/verifier/data_preprocess.py`
- **VerifierInference**：推理执行，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/verifier/inference.py`
- **VerifierComparator**：结果对比，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/verifier/comparator.py`
- **精度分析**：→ `task-accuracy-debug.md`
- **评估数据预处理**：→ `task-eval-preprocess.md`
