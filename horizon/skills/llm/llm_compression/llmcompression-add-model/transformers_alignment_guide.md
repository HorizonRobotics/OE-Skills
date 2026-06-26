# 从 transformers 对齐到 llm_compression 的详细指南

当 `leap_llm` 没有参考模型时，本文档提供从 transformers 源码提取模型结构信息的完整方法。

---

## 1. 阅读 transformers 源码的顺序

按此顺序阅读 `modeling_<model>.py`：

### ① Attention 类（`<Model>Attention`）

| 检查项 | 在哪看 | 关注什么 |
|--------|--------|----------|
| proj bias | `__init__` 中 `nn.Linear(..., bias=...)` | 是否从 `config.attention_bias` 读取 |
| q_norm/k_norm | `__init__` 有无 `q_norm`/`k_norm` 属性 | 有则用 `horizon_plugin_pytorch.nn.RMSNorm` 实现 |
| head_dim | `__init__` | `config.head_dim` 还是推导 `hidden_size // num_attention_heads` |
| scaling | `__init__` | 通常 `self.head_dim ** -0.5`，有些带 `attention_scaling` |
| o_proj bias | `__init__` 中 `o_proj` | 部分模型 o_proj 固定 `bias=False` |
| GQA/MQA | `__init__` 中 `num_key_value_heads` | 决定 `num_key_value_groups` |
| sliding_window | `__init__` 或 `forward` | 是否有 `sliding_window` 参数 |

### ② MLP 类

| 检查项 | 关注什么 |
|--------|----------|
| bias | `config.mlp_bias` 还是固定 False |
| 激活函数 | `config.hidden_act`（通常 "silu"） |
| 门控结构 | gate_proj + up_proj + down_proj（标准 SwiGLU） |

### ③ DecoderLayer 类

| 检查项 | 关注什么 |
|--------|----------|
| norm 类型 | RMSNorm 还是 LayerNorm |
| norm eps | `config.rms_norm_eps` |
| 残差方式 | Pre-norm（先 norm 后 attn/mlp）是标准做法 |

### ④ Model 类（`<Model>Model`）

| 检查项 | 关注什么 |
|--------|----------|
| embed_tokens | `nn.Embedding(vocab_size, hidden_size)` |
| rotary_emb | 哪种 RoPE 实现，参数从哪来 |
| position_embeddings | `self.rotary_emb(hidden_states, position_ids)` 的签名 |

### ⑤ ForCausalLM 类

| 检查项 | 关注什么 |
|--------|----------|
| lm_head | `nn.Linear(hidden_size, vocab_size, bias=False)` |
| tie_word_embeddings | 是否共享 embed_tokens 权重 |

---

## 2. RoPE 实现方式

transformers 通过 `rope_scaling.rope_type` 决定实现：

| rope_type | 说明 | llm_compression 适配 |
|-----------|------|---------------------|
| `default` | 标准 `inv_freq = 1.0 / (base ** (arange / dim))` | `_set_cos_sin_cache` 直接实现 |
| `linear` | `inv_freq /= factor` | 在 `_set_cos_sin_cache` 中加 factor |
| `dynamic` | 按 seq_len 动态调整 base | 需要额外逻辑 |
| `yarn` | 带 attention_factor + beta_fast/beta_slow | 较复杂，需完整移植 |
| `longrope` | short_factor / long_factor 分段 | 较复杂 |
| `llama3` | low_freq_factor / high_freq_factor | 较复杂 |

**大多数模型用 `default`**，此时 `_set_cos_sin_cache` 可直接复用 qwen3 的实现。

若使用非 default RoPE，需：
1. 阅读 transformers 的 `ROPE_INIT_FUNCTIONS[rope_type]` 实现
2. 移植 `inv_freq` 计算逻辑
3. 检查是否有 `attention_scaling` 因子，有则在 cos/sin 上乘以该因子

---

## 3. transformers 典型 state_dict key 结构

### LLM（扁平结构）

```
model.embed_tokens.weight
model.layers.{i}.input_layernorm.weight
model.layers.{i}.self_attn.q_proj.weight
model.layers.{i}.self_attn.q_proj.bias          # 仅 attention_bias=True
model.layers.{i}.self_attn.k_proj.weight
model.layers.{i}.self_attn.v_proj.weight
model.layers.{i}.self_attn.o_proj.weight
model.layers.{i}.self_attn.q_norm.weight         # 仅有 QK-Norm 的模型
model.layers.{i}.self_attn.k_norm.weight
model.layers.{i}.post_attention_layernorm.weight
model.layers.{i}.mlp.gate_proj.weight
model.layers.{i}.mlp.up_proj.weight
model.layers.{i}.mlp.down_proj.weight
model.norm.weight
lm_head.weight
```

### VLM（嵌套前缀）

VLM 通常多一层前缀：`language_model.model.layers.{i}.xxx`

### llm_compression 映射规则

1. 去掉 `model.` 前缀
2. 所有非 `lm_head` 的 key 加上 `lm.` 前缀
3. `lm_head.weight` → `lm.lm_head.weight`
4. VLM 额外处理 `language_model.model.xxx` → `lm.xxx`
5. `model.prefill = model.lm`（引用），`model.decode = copy.deepcopy(model.lm)`（独立副本）

---

## 4. 关键 config 字段速查

| 字段 | 用途 | 默认值 |
|------|------|--------|
| `hidden_size` | 隐藏维度 | — |
| `num_attention_heads` | 注意力头数 | — |
| `num_key_value_heads` | KV 头数（GQA） | = num_attention_heads |
| `head_dim` | 头维度 | hidden_size // num_attention_heads |
| `intermediate_size` | MLP 中间维度 | — |
| `num_hidden_layers` | Transformer 层数 | — |
| `rms_norm_eps` | RMSNorm eps | 1e-6 |
| `rope_theta` | RoPE 基频 | 10000.0（有些模型 1e6） |
| `attention_bias` | Q/K/V/O proj bias | False |
| `mlp_bias` | MLP bias（仅部分模型） | False |
| `hidden_act` | 激活函数 | "silu" |
| `max_position_embeddings` | 最大序列长度 | — |
| `rope_scaling` | RoPE 扩展配置 | None |
| `sliding_window` | 滑动窗口大小 | None |
| `tie_word_embeddings` | 是否共享词嵌入 | False |

### VLM 额外字段

| 字段 | 说明 |
|------|------|
| `text_config` | 文本 backbone 配置（嵌套） |
| `vision_config` | 视觉 backbone 配置（嵌套） |
| `image_token_id` | 图像 token id |
| `video_token_id` | 视频 token id |
| `vision_start_token_id` / `vision_end_token_id` | 视觉输入边界 token |

---

## 5. 对齐检查清单

### 模型结构

- [ ] `attention_bias`：True 还是 False？从 config 读取？
- [ ] `q_norm`/`k_norm`：有还是无？类型？eps？
- [ ] `head_dim`：显式还是推导？
- [ ] `scaling`：是否有 `attention_scaling`？
- [ ] `o_proj bias`：是否固定 False？
- [ ] `mlp_bias`：从 config 读取还是固定？
- [ ] `hidden_act`：SiLU？GELU？
- [ ] `num_key_value_heads`：GQA/MQA/MHA？
- [ ] `tie_word_embeddings`：是否共享？

### RoPE

- [ ] `rope_type`：default 还是其他？
- [ ] `rope_theta`：基频是多少？
- [ ] `rope_scaling`：有无？若有完整移植
- [ ] `attention_scaling`：有无？
- [ ] `max_position_embeddings`：预计算范围

### 权重映射

- [ ] 打印 HF `state_dict().keys()`，确认所有 key 前缀
- [ ] `model.` 前缀是否需要去除
- [ ] `lm_head` 的位置和前缀
- [ ] VLM 多层前缀处理
- [ ] `miss_key` 仅含 QuantStub 相关 key
- [ ] `unexpected_key` 合理（如 `rotary_emb.inv_freq`）

### 量化配置

- [ ] 有 leap_llm 时从 `ConstFakeQuant`/`FakeQuantMatmul` 读取 bit 数
- [ ] 无 leap_llm 时参考同类模型的 qconfig
- [ ] `dynamic_quant_types = (nn.Linear,)` 是元组
