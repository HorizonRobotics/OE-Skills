# LightCompress 量化探索实验示例

## 典型触发语句

```text
帮我用 GPTQ W4A8 量化 Qwen3-1.7B，生成精度报告。
```

```text
对 InternVL2-1B 做 SmoothQuant W8A8 量化实验。
```

```text
用 QuaRot 方法量化 Qwen3-30B-A3B，W4A8 配置。
```

---

## 示例 1：GPTQ W4A8 量化

**用户请求**：

```text
对 Qwen3-1.7B 做 GPTQ W4A8 量化实验
```

**Phase 1: 准备实验**

```bash
python {skill_dir}/scripts/prepare_experiment.py \
  --model /path/to/models/Qwen3-1.7B \
  --model-type Qwen3 \
  --method gptq \
  --w-bit 4 \
  --a-bit 8
```

> **注意**：不指定 `--workspace` 时，实验目录默认创建在 `{当前工作目录}/experiments/` 下。

**输出**：

```json
{
  "experiment_dir": "/path/to/experiments/Qwen3-1.7B_GPTQ_20260402_143000",
  "config_path": "/path/to/experiments/Qwen3-1.7B_GPTQ_20260402_143000/configs/qwen3_1.7b__gptq_w4a8.yml",
  "yaml_content": "base:\n    seed: &seed 0\n..."
}
```

**Phase 2: 用户确认**

向用户展示 YAML 配置，确认是否开始实验。

**Phase 3: 执行实验**

```bash
python {skill_dir}/scripts/execute_experiment.py \
  /path/to/experiments/Qwen3-1.7B_GPTQ_20260402_143000
```

**输出**：

```json
{
  "experiment_dir": "...",
  "report_path": ".../report.md",
  "results": [...]
}
```

**Phase 4: 保存缓存**

调用 `quant-accuracy-cache` skill 保存实验结果。

---

## 示例 2：大模型自动优化

**用户请求**：

```text
对 Qwen3-30B-A3B 做 GPTQ 量化
```

**自动优化行为**：

1. `prepare_experiment.py` 检测模型大小 (>20GB)
2. 自动调整校准参数：
   - `calib.n_samples`: 512 → 128
   - `calib.bs`: 1 (保持不变)
3. 自动启用 `inference_per_block: true` 避免显存溢出

**生成的 YAML 配置片段**：

```yaml
calib:
    name: wikitext2
    n_samples: 128    # 自动优化
    bs: 1
    seq_len: 2048

eval:
    inference_per_block: true   # 大模型自动启用
```

---

## 示例 3：快速验证模式

**用户请求**：

```text
快速验证一下 InternVL2-1B 的 AWQ W4A16 量化效果
```

**命令**：

```bash
python {skill_dir}/scripts/prepare_experiment.py \
  --model /path/to/models/InternVL2-1B \
  --model-type InternVL2 \
  --method awq \
  --w-bit 4 \
  --a-bit 16 \
  --fast-mode
```

**快速模式效果**：

| 参数 | 正常模式 | 快速模式 |
|------|----------|----------|
| `calib.n_samples` | 512 | 128 |
| `calib.seq_len` | 2048 | 512 |
| `eval.seq_len` | 2048 | 512 |
| `quant.special.epochs` (OmniQuant) | 20 | 5 |

---

## 示例 4：保存量化产物

**用户请求**：

```text
对 Qwen3-1.7B 做 SmoothQuant 量化，保存量化后的权重
```

**命令**：

```bash
python {skill_dir}/scripts/prepare_experiment.py \
  --model /path/to/models/Qwen3-1.7B \
  --model-type Qwen3 \
  --method smoothquant \
  --save-artifacts
```

**实验目录结构**：

```text
Qwen3-1.7B_SmoothQuant_20260402_143000/
├── manifest.json
├── configs/
│   └── qwen3_1.7b__smoothquant_w8a8.yml
├── logs/
│   └── smoothquant_*.log
├── artifacts/           # 量化产物
│   ├── transformed/     # 变换后模型
│   └── fake_quant/      # 量化后模型
└── report.md
```

---

## 支持的模型类型

| 模型系列 | `--model-type` 值 | 示例模型 |
|----------|-------------------|----------|
| Qwen | `Qwen`, `Qwen2`, `Qwen3`, `Qwen3Moe` | Qwen3-1.7B, Qwen3-30B-A3B |
| InternVL | `InternVL2`, `InternVL3_5` | InternVL2-1B, InternVL3.5-1B |
| DeepSeek | `DeepSeekV2`, `DeepSeekV3` | DeepSeek-V2-Lite |

---

## 支持的量化方法

| 方法 | `--method` 值 | 典型配置 |
|------|---------------|----------|
| RTN | `rtn` | W4A16, W8A8 |
| GPTQ | `gptq` | W4A8, W4A16 |
| AWQ | `awq` | W4A16 |
| SmoothQuant | `smoothquant` | W8A8 |
| QuaRot | `quarot` | W4A8 |
| OmniQuant | `omniquant` | W4A8 |

---

## 实验报告示例

```markdown
# GPTQ W4A8 量化实验报告

## 实验信息

- **模型**: Qwen3-1.7B
- **方法**: GPTQ W4A8
- **时间**: 2026-04-02 14:30:00

## 精度结果

| 阶段 | PPL |
|------|-----|
| Pretrain | 20.92 |
| Fake Quant | 22.15 |
| PPL Delta | +1.23 |

## 量化层统计

- 总层数: 28
- 量化层: 28 (100%)

## 结论

GPTQ W4A8 量化后 PPL 退化 5.9%，在可接受范围内。
```
