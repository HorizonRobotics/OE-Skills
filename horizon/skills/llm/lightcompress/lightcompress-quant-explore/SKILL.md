---
name: lightcompress-quant-explore
version: 2.0.3
description: 执行 LightCompress 量化实验并生成精度报告。当用户要求运行量化实验、量化精度测试或 PPL 评估时触发。
---

# LightCompress 量化探索实验

## 执行流程（4 阶段）

### Phase 1: 准备实验

调用 `prepare_experiment.py` 创建实验目录和 YAML 配置：

```bash
python {skill_dir}/scripts/prepare_experiment.py \
  --model /path/to/model \
  --model-type Qwen2 \
  --method smoothquant \
  --w-bit 8 \
  --a-bit 8
```

> **注意**：不指定 `--workspace` 时，脚本默认使用 `{当前工作目录}/experiments` 作为输出目录。

脚本输出 JSON 包含：
- `experiment_dir`: 实验目录路径
- `config_path`: YAML 配置路径
- `yaml_content`: 完整 YAML 配置内容

### Phase 2: 用户确认

向用户展示完整的 YAML 配置内容，让用户检查是否符合预期。

使用 AskUserQuestion 询问：**开始实验** / **取消**

### Phase 3: 执行实验

用户确认后，调用 `execute_experiment.py` 执行实验：

```bash
python {skill_dir}/scripts/execute_experiment.py {experiment_dir}
```

### Phase 4: 保存精度缓存

实验成功后，检查 `<project_root>/.claude/skills/quant-accuracy-cache/` 是否存在：
- 存在：调用 `quant-accuracy-cache` skill 保存结果
- 不存在：跳过

---

## 参数说明

### prepare_experiment.py 参数

| 参数 | 必需 | 说明 | 默认值 |
|------|------|------|--------|
| `--model` | ✅ | 模型路径 | - |
| `--model-type` | ✅ | 模型类型 | - |
| `--method` | ✅ | 量化方法 | - |
| `--w-bit` | | 权重量化位宽 | 4 |
| `--a-bit` | | 激活量化位宽 | 8 |
| `--fast-mode` | | 快速验证模式 | false |
| `--save-artifacts` | | 保存量化产物 | false |
| `--workspace` | | 工作目录 | ./experiments |
| `--mix-bits` | | 混合精度组(可多次),见下方示例 | - |
| `--special` | | 覆盖 quant.special 参数(可多次),`KEY=VAL` | - |
| `--calib-path` | | 校准数据集路径 | 内置 wikitext2_calib |
| `--calib-name` | | 校准数据集名 | wikitext2 |
| `--calib-n-samples` | | 校准样本数(**显式值不被显存降级**) | 自动 |
| `--calib-seq-len` | | 校准序列长度 | 模板默认 |
| `--calib-preproc` | | 校准预处理 | wikitext2_gptq |
| `--eval-path` | | 评估数据集路径 | 内置 wikitext2_eval |
| `--eval-seq-len` | | 评估序列长度 | 模板默认 |
| `--no-eval-pretrain` | | 只评 fake_quant,跳过 pretrain | false |
| `--inference-per-block` | | 逐 block 推理评测(大模型省显存) | false |
| `--save-path` | | fakequant 保存路径(指定即开 save_fake) | - |

### 混合精度 (mix_bits) 示例

将 q/o_proj + MoE expert 设为 W4、其余 W8(Gemma4Moe 常用):

```bash
python {skill_dir}/scripts/prepare_experiment.py \
  --model /jfs-public/openexplorer_llm/models/gemma-4-26B-A4B-it \
  --model-type Gemma4Moe --method gptq --w-bit 8 --a-bit 8 \
  --mix-bits "name=qo_experts_w4;bit=4;layers=self_attn.q_proj,self_attn.o_proj,experts.experts.*.gate_proj,experts.experts.*.up_proj,experts.experts.*.down_proj" \
  --calib-n-samples 256 --calib-seq-len 1024 \
  --no-eval-pretrain --inference-per-block \
  --save-path /path/to/save/ \
  --env-activate ~/miniconda3/etc/profile.d/conda.sh
```

- `--mix-bits` 格式:`"name=组名;bit=位宽;layers=层1,层2,..."`,层名支持通配符 `*`(如 `experts.experts.*.gate_proj`)。多组混合精度可多次传 `--mix-bits`。
- 未列入 mix_bits 的层使用全局 `--w-bit` 位宽。

### 支持的模型类型

| 模型系列 | type 值 |
|----------|---------|
| Qwen | `Qwen`, `Qwen2`, `Qwen3`, `Qwen3Moe` |
| InternVL | `InternVL2`, `InternVL3_5` |
| DeepSeek | `DeepSeekV2`, `DeepSeekV3` |
| Gemma4 | `Gemma4`, `Gemma4Moe`(MoE 自动识别 num_experts) |

---

## 外部配置文件

| 文件 | 用途 |
|------|------|
| [base_template.yml](base_template.yml) | YAML 模板 |
| [methods_config.yml](methods_config.yml) | 量化方法参数 |
| [pretrain_accuracy_cache.yml](pretrain_accuracy_cache.yml) | pretrain 缓存 |
