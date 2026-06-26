# LightCompress 量化探索实验参考

## 进程状态判断（关键！）

**大模型实验评估阶段可能长时间没有日志输出，必须正确判断进程状态！**

### 检查进程是否存活

```bash
# PID 文件位置：{task_name}_{timestamp}.pid
pids=$(cat {pid_file})
for pid in $pids; do
    ps aux | grep "^.* $pid " | grep -v grep
done
```

### 判断规则

| 情况 | 错误判断 | 正确判断 |
|------|----------|----------|
| 进程还在运行 | ❌ 启动新实验覆盖 | ✅ 继续等待当前实验 |
| 进程确实失败 | ✅ 重新启动 | ✅ 检查错误日志后重新启动 |

### ⚠️ 禁止重复启动实验！

**只有在确认以下情况后才能重新启动**：
1. PID 文件中的进程确实不存在（`ps aux` 找不到）
2. 日志文件中有明确的错误/异常退出信息
3. 日志文件大小停止增长超过 5 分钟

**重复启动的后果**：
- 浪费 GPU 资源
- 日志文件冲突
- 原实验结果被覆盖

---

## 运行命令详解

**正确的运行命令**（通过 `run_llmc.sh` 调用）：
```bash
# 1. 激活环境（必须先执行）
conda activate <your_env>

# 2. 切换到 lightcompress 目录
cd {lightcompress_dir}

# 3. 执行实验
CUDA_VISIBLE_DEVICES={gpu_id} \
config={config_path} \
model={model_name} \
algo={quant_method} \
task_name={task_id} \
save_log=1 \
bash scripts/run_llmc.sh
```

**参数说明**：
| 参数 | 说明 | 示例 |
|------|------|------|
| `CUDA_VISIBLE_DEVICES` | 选择的 GPU ID | `0` |
| `config` | YAML 配置文件的**绝对路径** | `/home/.../config.yml` |
| `model` | 模型名称（用于日志命名） | `qwen3_30b` |
| `algo` | 量化方法（用于日志命名） | `smoothquant` |
| `task_name` | 实验任务名 | `w8a8_smoothquant_qwen3` |
| `save_log` | 是否保存日志 | `1`（推荐） |

**run_llmc.sh 内置功能**：
- ✅ 自动寻找未占用端口
- ✅ 失败自动重试（最多 5 次）
- ✅ 后台运行 + 日志文件记录
- ✅ PID 文件管理

**日志和 PID 文件**：
- 日志文件：`{task_name}_{timestamp}.log`
- PID 文件：`{task_name}_{timestamp}.pid`
- 终止进程：`xargs kill -9 < {task_name}_{timestamp}.pid`

---

## Manifest 字段说明

顶层字段：

| 字段 | 必填 | 说明 |
|------|------|------|
| `workspace_root` | 是 | 当前仓库根目录 |
| `run_script_path` | 是 | `llm_compression/lightcompress/scripts/run_llmc.sh` 绝对路径 |
| `env_activate` | 是 | 虚拟环境激活脚本路径 |
| `experiment_name` | 是 | 实验名称，用于生成实验目录 |
| `poll_interval_sec` | 否 | 轮询 pid 间隔，默认 10 秒 |
| `launch_timeout_sec` | 否 | 等待 `pid/log` 文件出现的超时，默认 120 秒 |
| `allowed_gpus` | 否 | 限制只在这些 GPU 中选择显存空闲最多的一张 |
| `save_artifacts` | 否 | 是否保存量化产物，默认 false |
| `experiments` | 是 | 实验列表 |

单个实验字段：

| 字段 | 必填 | 说明 |
|------|------|------|
| `model_name` | 是 | 用于 `task_name` 和报告展示 |
| `model_type` | 是 | llmc 模型类型 |
| `model_path` | 是 | 模型绝对路径 |
| `method_name` | 是 | 报告中展示的方法名 |
| `algo` | 是 | `run_llmc.sh` 中的算法变量 |
| `config_path` | 是 | 最终 YAML 配置绝对路径 |
| `w_q` | 是 | weight 标记 |
| `a_q` | 是 | activation 标记 |
| `specification` | 否 | 额外标记，默认 `_` |
| `nnodes` | 否 | 默认 1 |
| `nproc_per_node` | 否 | 默认 1 |

## `task_name` 规则

脚本遵循 `run_llmc.sh` 当前命名模式：

```text
{algo}_{w_q}_{a_q}_{specification}_{model_name}_{YYYYMMDD}
```

因此这些字段在同一天内必须能唯一标识一个实验项，否则日志和 pid 会冲突。

最简单的做法：
- `method_name` 用于报告展示。
- `specification` 用于区分同一算法的不同变体，例如 `baseline`、`bs32`、`lr5e4`、`group128`。

---

## 输出目录结构

实验目录结构（所有产物统一管理）：

```text
{experiment_name}_{timestamp}/
├── manifest.json                    # 实验清单快照
├── configs/
│   └── {model_name}__{method_name}.yml  # YAML 配置
├── logs/
│   ├── {task_name}.log              # 运行日志
│   ├── {task_name}.pid              # 进程 ID
│   ├── {task_name}.launcher.stdout.log
│   └── {task_name}.launcher.stderr.log
└── report.md                        # 最终报告
```

其中 `task_name` 格式为：`{model_name}__{method_name}__{date}`

如果 `save_artifacts: true`，还会保存量化产物：

```text
{experiment_name}_{timestamp}/
├── ...
└── artifacts/
    └── {model_name}__{method_name}/
        └── {quantized_model_files}
```

---

## GPU 选择策略

每次启动一个实验项之前都会重新执行：

```bash
nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits
```

按以下优先级排序并选择第一张 GPU：
1. `memory_free` 最大（空闲显存最多）
2. `utilization.gpu` 最小
3. `index` 最小

如果希望只在部分卡上选择，可以给 manifest 加 `allowed_gpus`。

---

## 报告格式

最终 Markdown 报告包含：
- 基本信息
- YAML 配置（直接嵌入，禁止重写为表格）
- 实验结果表格
- 运行环境

指标解释：
- `pretrain PPL`: 浮点或预量化位点
- `transformed PPL`: 中间变换位点
- `fake_quant PPL`: 最关键的量化精度指标

---

## 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| `conda: command not found` | 环境未激活 | 激活你的 conda 环境 |
| `KeyError: 'seed'` | 缺少 seed | 添加 `calib.seed: *seed` |
| `Catch input data failed` | 数据集路径错误 | 用 `wikitext-2-raw-v1` |
| GPTQ 精度下降 | blocksize 不匹配 | 见 methods_config.yml |
| `Expected all tensors on same device` | 大模型显存不足 | 脚本自动启用 `inference_per_block: True` |
| CUDA out of memory | 显存不足 | 脚本自动启用 `inference_per_block: True` |
| **GPTQ 运行时间过长** | `true_sequential: True` | **默认已设为 `true_sequential: False`**，见 methods_config.yml |
| `can't open file 'llmc/__main__.py'` | PYTHONPATH 未设置 | 确保在 lightcompress 目录执行 |
| `Address already in use` | 端口冲突 | 脚本自动重试其他端口 |
| 输出目录冲突 | 日志中出现 `existed before. Need check.` | 检查 YAML 的 `save.save_path` 是否复用了旧目录 |
| 无指标输出 | 报告里没有 PPL | 确认配置里启用了 eval，检查日志是否打印了 `EVAL: ppl on ... is ...` |
| `task_name` 冲突 | 新任务覆盖旧日志 | 修改 manifest 里的 `specification`，确保唯一 |
| **评估配置不一致** | 不同方法的 `pretrain PPL` 差异巨大 | 确保 `eval.seq_len`、`eval.inference_per_block`、`eval.path` 所有方法一致 |
| **Python 环境冲突** | `RuntimeError: operator torchvision::nms does not exist` | 使用正确的项目 conda 环境，设置 `PYTHONNOUSERSITE=1` |
| **模型代码缺少 import** | `NameError: name 'torch' is not defined` | 检查新增模型 wrapper 是否导入所有使用的模块 |
| **GPTQ 显存不足** | GPTQ 在量化过程中 OOM | 降低校准参数：`n_samples=32`, `seq_len=512`, `blocksize=64`；关闭 `actorder`, `true_sequential`, `fp32_had` |

---

## Python 环境最佳实践

推荐的环境配置：

```bash
# 激活项目 conda 环境
conda activate <your_env>

# 隔离 ~/.local 目录的包，避免版本冲突
export PYTHONNOUSERSITE=1
```

---

## 评估配置一致性检查清单

对比多种量化方法前，务必检查：

- [ ] 所有方法的 `eval.seq_len` 一致
- [ ] 所有方法的 `eval.inference_per_block` 一致
- [ ] 所有方法的 `eval.path` 指向同一数据集
- [ ] 运行后验证 `pretrain PPL` 所有方法一致

**错误示例**: GPTQ 配置 `seq_len=1024, inference_per_block=True`，而 RTN 配置 `seq_len=2048, inference_per_block=False`，导致 GPTQ 的 pretrain PPL (19.37) 与 RTN (17.18) 差异巨大。

---

## GPTQ 配置详解

### 默认值说明

GPTQ 的以下参数**默认为 False**，除非用户显性配置指定：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `true_sequential` | **False** | MoE 模型必须为 False，否则速度极慢 |
| `quant_out` | **False** | 默认不输出量化中间结果 |

### MoE 模型 + GPTQ 特殊说明

MoE 模型使用 GPTQ 量化时，`true_sequential: True` 会导致**极慢的运行速度**（可能比正常慢 10 倍以上）。

**受影响的模型**：

| 模型类型 | 模型示例 |
|----------|----------|
| `Qwen2Moe` | Qwen2-57B-A14B |
| `Qwen3Moe` | Qwen3-30B-A3B |
| `Qwen3_5Moe` | Qwen3.5-MoE 系列 |
| `Mixtral` | Mixtral-8x7B, Mixtral-8x22B |
| `DeepSeekV2` | DeepSeek-V2 |
| `DeepSeekV3` | DeepSeek-V3 |

### GPTQ 显存优化配置

GPTQ 需要维护 Hessian 矩阵，显存需求比 RTN/SmoothQuant 大。在有限显存下可使用以下配置：

```yaml
calib:
  n_samples: 32      # 减少样本数
  seq_len: 512       # 减少序列长度
quant:
  special:
    actorder: False          # 关闭激活重排序
    true_sequential: False   # 关闭顺序量化
    blocksize: 64            # 减小块大小
    fp32_had: False          # 关闭 FP32 Hadamard
```

**注意**: 校准配置可以调整，但评估配置 (`eval.*`) 必须与其他方法一致。

---

## 推荐工作流

1. 根据用户需求先生成或复制 YAML 配置副本。
2. 把所有实验项写进一个 manifest。
3. 执行内置脚本。
4. 查看报告，优先关注每个模型的最优 `fake_quant PPL`。
5. 如果有失败项或最优结果仍不理想，再做下一轮参数调优。
