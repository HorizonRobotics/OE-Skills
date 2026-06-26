---
name: llmcompression-add-model
version: 2.0.3
description: 为 llm_compression 框架新增 LLM/VLM 模型支持。当用户需要在 llm_compression/models/ 中接入新模型时触发。
---

# 新增 LLM/VLM 模型到 llm_compression

## 整体流程

1. **确定参考源** → leap_llm 或 transformers
2. **差异分析** → 详细对比新增模型与参考模型的 diff
3. **创建目录结构** → `llm_compression/models/<model_name>/`
4. **编写** blocks/、`model.py`、`process_utils.py`、`<model_name>_model.py`
5. **创建配置文件** → `llm_compression/configs/<model_name>.yml`
6. **注册模型** → `llm_compression/models/__init__.py`
7. **自测验证** → 至少完成 smoke test；如真实权重不可用，做半真实配置验证
8. **生成报告** → 输出接入报告并记录关键问题、解决方式和验证结果

---

## Step 0：确定参考源

**首先**检查 `leap_llm/models/` 下有没有同名目录：

- **有**：以 `leap_llm` 该模型的 `forward()` 方法为主要参考（不是 `build()`）
- **没有**：去 transformers 源码查找：`<site-packages>/transformers/models/<model_name>/modeling_<model_name>.py`

同时参考已集成模型的框架写法：
- VLM：`llm_compression/models/qwen2_5_vl/`（无 QK-Norm）或 `qwen3_vl/`（有 QK-Norm + DeepStack）
- LLM：`llm_compression/models/qwen3/`

### 当 leap_llm 没有参考模型时（从 transformers 对齐）

必须直接阅读 transformers 源码，提取模型结构信息。详细的阅读方法、config 字段速查和对齐检查清单见 [transformers_alignment_guide.md](transformers_alignment_guide.md)。

核心步骤：
1. 阅读 `configuration_<model>.py`：获取 config 字段及默认值
2. 阅读 `modeling_<model>.py`：提取 Attention/MLP/DecoderLayer/Model/ForCausalLM 结构
3. 与框架内参考模型逐项对比差异

---

## Step 0.5：差异分析（必须在写代码前完成）

整理差异清单，包含三类：

- **模型层 diff**：attention 形式（q_norm/k_norm、attention_bias、sliding_window）、mlp（bias、激活函数）、norm 类型、rope 实现、权重命名
- **数据层 diff**：position_ids 方式（1D 还是 3D mRoPE）、mask 形状、padding 方向、多模态输入
- **generate 逻辑层 diff**：prefill/decode 流程、chunk_prefill、cache 管理、停止条件

要求：
- 明确指出**哪里相同、哪里不同**，不要笼统说"类似 qwen3"
- 无法确认的点标记"待确认"

---

## Step 1：blocks/attention.py

### 1.0 License 头声明（blocks/ 下所有文件 + model.py 必须添加）

`models/*/blocks/` 下的所有 `.py` 文件以及 `models/*/model.py` 派生自 HuggingFace Transformers（Apache 2.0），必须保留 transformers 原始的完整 License 声明，并追加 Horizon 修改声明。

**获取正确的 Copyright 行**：查看 `transformers/models/<model>/modeling_<model>.py` 文件头的 Copyright 行，原样复制。不同模型的 Copyright 行不同（如 Qwen 系列含 Alibaba Group，Gemma 系列只有 HuggingFace Team）。

```python
# Copyright <year> <original authors from transformers>. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Modifications Copyright (c) Horizon Robotics. All rights reserved.
```

此声明适用于 blocks/ 下所有文件（`__init__.py`、`attention.py`、`mlp.py`、`transformer_block.py`、`moe.py`、`vision_*.py`、`linear_attention.py`、`text_*.py` 等）以及 `model.py`。

### 1.1 逐项确认（无论参考源是 leap_llm 还是 transformers）

| 检查项 | llm_compression 映射 |
|--------|---------------------|
| proj bias | 与参考源一致，若从 config 读则 `getattr(config, "attention_bias", False)` |
| q_norm/k_norm | 有则 `horizon_plugin_pytorch.nn.RMSNorm(head_dim, eps=config.rms_norm_eps)` |
| head_dim | `getattr(config, "head_dim", config.hidden_size // config.num_attention_heads)` |
| scaling | 成员变量 `self.scaling = self.head_dim ** -0.5` |

### 1.2 量化组件

```python
self.cache_k_fq = QuantStub()
self.cache_v_fq = QuantStub()
self.dequant = DeQuantStub()
```

- **有 leap_llm**：对照 `build()` 中 leap 算子位置插入
- **无 leap_llm**：参考 qwen3 的标准模式——cache KV 操作前后 quant/dequant 是固定的

### 1.3 关键规则

- RoPE 后必须立即 reshape 回 4D 再做 cache 操作
- cache KV: cat 前 dequant，cat 后重新量化
- `attention_mask` 已是 4D，直接 `torch.add`，不要 unsqueeze
- GQA matmul: reshape 为 `[bsz, num_kv_heads, -1, head_dim]` 再 matmul
- new_key/new_value 返回前 quant → dequant

shape 流和代码模板见 [reference.md](reference.md)

---

## Step 2：model.py（TextModel）

### 2.1 cos/sin 预计算

- **无 leap_llm 时**：阅读 transformers 的 `<Model>RotaryEmbedding`，提取 `inv_freq` 公式
- 大多数模型用标准 RoPE，可复用 qwen3 的 `_set_cos_sin_cache`，只需确认 `rope_theta`
- 预计算后截取到 `max_kvcache_len`，存为普通属性（不用 `register_buffer`）

### 2.2 QuantStub 与 cos/sin 索引

- QuantStub 标准四件套：`quant_input_embeds`、`quant_cos`、`quant_sin`、`quant_attention_mask`、`dequant`
- **有 leap_llm**：对照 `build()` 中 leap 算子输入
- **无 leap_llm**：直接复用标准四件套
- cos/sin 用 `torch.gather` 按 `position_ids` 索引；VLM mRoPE 需按 mrope_section 分别索引再拼接

代码模板见 [reference.md](reference.md)

### 2.4 forward() 输出

```python
# 取最后 token → norm → lm_head → dequant
return token_logits, new_keys, new_values
```

---

## Step 3：process_utils.py

### 3.1 复用 generate_utils.py

```python
from llm_compression.models.generate_utils import (
    chunk_prefill_forward, chunk_visual_forward, get_causal_mask,
    get_causal_mask_chunks, get_decoder_mask, get_paded_input_ids_attn_mask,
    init_kv_cache, init_prefill_kv_cache, is_finished, padding_data,
    process_kv_cache,
)
```

### 3.2 generate_func 流程

**prefill**：判断 chunk_prefill → 左 padding → 初始化 KV cache → position_ids 转 int64 → get_causal_mask → forward

**decode**：init_kv_cache → 循环（argmax/sampling → embed → position_ids.long() → decoder_mask → forward → process_kv_cache）

### 3.3 config 访问（关键差异）

- **LLM**：`config.max_kvcache_len` / `config.max_lm_input_len`（`update_config_from_custom_config` 直接写入 model_config）
- **VLM**：`config.text_config.max_kvcache_len` / `config.text_config.max_lm_input_len`（嵌套 config）

### 3.4 VLM 额外逻辑

| 函数 | 用途 |
|------|------|
| `get_rope_index` | mRoPE 3D position_ids `(3, bsz, seq_len)` |
| `gen_inputs_embeds` | `masked_scatter` 将 image embeddings 填入 text |
| `scatter_deepstack_embeds` | DeepStack 中间层 visual features |

---

## Step 4：<model_name>_model.py（BaseQModel 子类）

### 4.1 build_model config 更新

- **LLM**：`update_config_from_custom_config(model_config, self.custom_config.model.text_config)`
- **VLM**：分别 update `model_config.vision_config` 和 `model_config.text_config`

### 4.2 权重加载与 get_qconfig_setting

- 权重映射：HF key 去掉 `model.` 前缀，加 `lm.` 前缀；`lm_head.weight` → `lm.lm_head.weight`。注意：不是映射到 `prefill.`，而是映射到 `lm.`，因为 `model.prefill = model.lm` 是引用赋值
- 验证：`miss_key` 仅含 QuantStub 相关 key，`unexpected_key` 合理
- **有 leap_llm**：`ConstFakeQuant(N)` → `{"output": qintN}`，`FakeQuantMatmul(a, b, None)` → `{"input": [qintA, qintB]}`
- **无 leap_llm**：参考 qwen3 标准配置（cache_k_fq: qint16, cache_v_fq: qint8, matmul: [qint8, qint16]/[qint16, qint8]）
- 使用 `SetDynamicQuantTemplate(op_kwargs={nn.Linear: {"block_size": "full", "dim": -1}})` 配置动态量化
- KV cache 配置推荐用 `self.get_kvcache_names(model_name)` 遍历构建

代码模板见 [reference.md](reference.md)

### 4.4 必须实现的接口

`build_model`、`get_model_trace_dummy_input`、`get_generated_model`、`get_generated_model_cfg`、`get_model_dtype`、`get_kvcache_names`、`get_model_input_output_name`、`input_preprocess`、`output_postprocess`、`get_qconfig_setting`

所有 `import` 必须放文件顶部。

---

## Step 5：配置文件

**必须先问用户**模型权重路径。

- LLM：`model_list: [prefill, decode]`，无 `vision_config`
- VLM：`model_list: [visual, prefill, decode]`，`vision_config` 默认 `image_height/width: 448`
- `max_lm_input_len` 默认 512，`max_kvcache_len` 默认 1024，`rmsnorm_version: cuda_hp`
- `model_dtype: float32` 是默认精度

**shared LM 模式**：当显存不足以 deepcopy LM 时，可用 `model_list: [visual, lm]`（VLM）或 `[lm]`（LLM），prefill 和 decode 共享同一份权重，显存减半。`BaseQModel.is_shared_lm_mode()` 自动检测。

---

## Step 6：注册与验证

注册：`llm_compression/models/__init__.py` 中 `from .<model_name>.<model_name>_model import XxxModel`

测试：yml 中 `eval_step: 5` → `sh llm_compression/scripts/torch_eval.sh`（使用项目 conda 环境）→ 成功标准：`exit_code: 0` + `Evaluation Results` 表格

---

## Step 7：自测验证（新增模型后必须执行）

### 7.1 最低要求

至少完成以下 3 类检查中的 1 类；如果真实权重不可用或模型过大，优先做第 2 类：

- **权重级验证**：能加载真实权重时，跑 `build_model` + `torch_eval.sh`
- **半真实配置 smoke test**：保留真实模型关键结构参数，裁剪层数或 expert/vocab 大小，直接跑 `process_utils.generate_func`
- **小配置 smoke test**：手工构造小 config，验证 prefill/decode/cache 主链路可执行

### 7.2 推荐 smoke test 覆盖矩阵

- `chunk_prefill=False`
- `chunk_prefill=True`
- 仅 `linear_attention` 路径（如果模型存在）
- 至少 1 个 `full_attention` 路径（如果模型存在）
- 至少 `1` 层和 `2` 层两组 case；若前几层没有覆盖到关键结构，可补 1 个特定层型 case

### 7.3 半真实配置裁剪原则

当真实模型太大、权重不完整或容易爆显存时：

- **保留**：`hidden_size`、`head_dim`、`num_attention_heads`、`num_key_value_heads`、`rope_parameters`、`layer_types`、线性注意力关键维度
- **可以裁剪**：`num_hidden_layers`、`vocab_size`、`num_experts`、`num_experts_per_tok`
- **目标**：优先验证结构、shape、cache 流是否正确，而不是追求语义输出

### 7.4 自测记录要求

需要至少记录以下信息：

- 使用的环境与 GPU，如 `CUDA_VISIBLE_DEVICES=0,1,2`
- 测试类型：小配置 / 半真实配置 / 真实权重
- 测试 case 列表
- 每个 case 是否通过
- 关键输出：返回 shape、是否报错、是否覆盖 `chunk_prefill`

---

## Step 8：生成报告与留痕

### 8.1 报告文件

完成新增模型后，生成报告文件：

- 推荐路径：`llm_compression/reports/<model_name>_integration_report.md`

### 8.2 报告至少包含

- **任务背景**：用户要求、模型目录、环境、GPU 约束
- **参考源**：`leap_llm` 还是 `transformers`
- **差异分析摘要**：模型层、数据层、generate 逻辑层
- **代码改动**：新增/修改了哪些文件
- **遇到的问题**：如权重不完整、模型太大、cache 不兼容、shape 报错
- **解决方式**：具体采取了什么裁剪、替代验证或代码修复
- **自测结果**：测试矩阵、是否通过、代表性输出
- **未完成项/风险**：例如真实权重尚未验证、量化尚未验证

---

## 常见报错

| 报错 | 排查 |
|------|------|
| `config has no attribute 'text_config'` | LLM 直接 `config.xxx` |
| `size mismatch at dim 3` | causal_mask 多余 squeeze？kv_len ≠ max_kvcache_len？ |
| `gather() Expected int64` | position_ids 在 process_utils 转 `.long()` |
| 3D vs 4D shape 不匹配 | RoPE 后未 reshape 回 4D？`cur_len` 取错维度？ |
| `miss_key` 含非 QuantStub key | 权重映射遗漏 |
| `mat1 and mat2 cannot be multiplied` | hidden_size/head_dim 不匹配 |

---

## 核心方法论

1. **不能无脑 copy**：bias、norm、scaling、rope、cache 格式逐项对照
2. **参考源用法**：有 leap_llm 时 `forward()` 参考结构 + `build()` 参考量化位置；无 leap_llm 时 transformers `forward()` 是唯一参考，量化位置参考已集成模型
3. **shape 全程追踪**：遇到 mismatch 从数据生成处开始追踪
4. **职责分离**：process_utils 管数据预处理、model.py 管前向计算、qmodel.py 管配置加载和权重映射
5. **框架模式复用**：cache KV 处理、QuantStub 四件套、generate_func 流程、权重映射逻辑都是模板化的

详细案例见 [qwen3_case_study.md](qwen3_case_study.md)，transformers 对齐详细指南见 [transformers_alignment_guide.md](transformers_alignment_guide.md)。
