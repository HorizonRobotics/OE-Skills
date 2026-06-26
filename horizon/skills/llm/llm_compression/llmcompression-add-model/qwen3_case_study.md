# 新增模型到 llm_compression —— Qwen3 集成完整记录

> 本文档记录了以 Qwen3 为例，将一个新 LLM 模型集成到 `llm_compression` 框架的完整过程，包括操作步骤、遇到的问题和修复方法，可作为后续集成其他模型的参考。

---

## 目录

1. [整体目标与思路](#1-整体目标与思路)
2. [查找参考实现](#2-查找参考实现)
3. [创建目录与文件](#3-创建目录与文件)
4. [blocks/ 子模块编写](#4-blocks-子模块编写)
5. [model.py 编写](#5-modelpy-编写)
6. [qwen3_model.py 编写](#6-qwen3_modelpy-编写)
7. [process_utils.py 编写](#7-process_utilspy-编写)
8. [配置文件编写](#8-配置文件编写)
9. [模型注册](#9-模型注册)
10. [调试记录](#10-调试记录)
11. [关键经验总结](#11-关键经验总结)

---

## 1. 整体目标与思路

**任务**：将 Qwen3（纯 LLM，无视觉模块）集成到 `llm_compression` 框架，使其支持量化校准、编译和评估流程。

**参考体系**：
- `llm_compression/models/qwen2_5_vl/`：已集成的 VLM，框架写法参考
- `leap_llm/models/qwen3/`：Qwen3 的模型结构参考（**以其 `forward()` 为主**）
- `llm_compression/models/base_qmodel.py`：BaseQModel 接口定义

**最终文件结构**：
```
llm_compression/models/qwen3/
├── __init__.py
├── model.py                  # Qwen3TextModel
├── qwen3_model.py            # BaseQModel 子类，@MODEL_REGISTRY 入口
├── process_utils.py          # generate_func + 推理辅助函数
└── blocks/
    ├── __init__.py
    ├── attention.py          # Qwen3Attention
    ├── mlp.py                # Qwen3MLP
    └── transformer_block.py  # Qwen3DecoderLayer

llm_compression/configs/qwen3.yml
```

---

## 2. 查找参考实现

**操作**：检查 `leap_llm/models/` 下是否有 `qwen3` 目录。

**结果**：存在，包含完整实现：
```
leap_llm/models/qwen3/
├── model.py
└── blocks/
    ├── __init__.py
    ├── attention.py
    ├── mlp.py
    └── transformer_block.py
```

**确认的关键差异**（Qwen3 vs Qwen2.5-VL）：
- 纯 LLM，无 visual 模块
- Attention 中有 `q_norm`/`k_norm`（per-head RMSNorm）
- 使用标准 1D RoPE，而非 mrope（3-stream）
- `attention_bias = False`（从 config 读取，不硬编码）
- cos/sin 预计算方式：`_set_cos_sin_cache` 方法，用 `rope_theta` 作为 base

---

## 3. 创建目录与文件

```bash
llm_compression/models/qwen3/
llm_compression/models/qwen3/blocks/
```

---

## 4. blocks/ 子模块编写

### 4.1 attention.py

**第一版问题**（AI 初始实现）：混用了 `qwen2_5_vl/blocks/attention.py` 的逻辑，没有严格对照 `leap_llm/qwen3` 的 `forward()`，具体问题：

| 问题点 | 初始错误写法 | 正确写法 |
|---|---|---|
| q_norm/k_norm 调用 | 先 view 再 norm 再 transpose（分步） | `q_norm(q_proj(...).view(shape)).transpose(1,2)`（链式） |
| bias | 硬编码 `bias=False` | `bias=getattr(config, "attention_bias", False)` |
| scaling | `1.0 / math.sqrt(head_dim)` 硬编码 | `self.scaling = head_dim ** -0.5` 成员变量 |
| cache KV 处理 | 无 dequant/quant 来回转换 | cat 前两者都要 dequant，cat 后重新量化（与 qwen2_5_vl 一致） |
| attention_mask | `attn_weights + attention_mask.unsqueeze(1)` | 直接 `add(attn_weights, attention_mask)`（mask 已是 4D） |

**修正后的关键逻辑**：

```python
# bias 从 config 读取
self.attention_bias = getattr(config, "attention_bias", False)
self.q_proj = nn.Linear(..., bias=self.attention_bias)

# q_norm/k_norm 链式调用（对齐 leap_llm forward）
query_states = self.q_norm(self.q_proj(hidden_states).view(hidden_shape)).transpose(1, 2)
key_states   = self.k_norm(self.k_proj(hidden_states).view(hidden_shape)).transpose(1, 2)

# RoPE 用 3D，结束后必须 reshape 回 4D 再做 cache ops
query_states = query_states.reshape(-1, q_len, self.head_dim)
key_states   = key_states.reshape(-1, q_len, self.head_dim)
query_states, key_states = apply_rotary_pos_emb(query_states, key_states, cos, sin)
key_states = key_states.reshape(bsz, self.num_key_value_heads, q_len, self.head_dim)  # ← 必须

# cache KV：cat 前 dequant，cat 后重新量化
cur_len = key_states.shape[2]   # ← 4D 时取 dim=2
cache_keys = self.cache_k_fq(cache_keys)[:, cur_len:].transpose(1, 2)
key_states = self.dequant(key_states)
cache_keys = self.dequant(cache_keys)
key_states = torch.cat([cache_keys, key_states], dim=2)
key_states = self.cache_k_fq(key_states)

# attention_mask 已是 4D，直接 add
attn_weights = torch.add(attn_weights, attention_mask)
```

### 4.2 mlp.py

参考 `leap_llm/qwen3/blocks/mlp.py`，用普通 `nn.Linear` 替换 `DynamicQuantLinear`，SiLU 激活函数。

### 4.3 transformer_block.py

参考 `leap_llm/qwen3/blocks/transformer_block.py` 的 `forward()`，使用 `horizon_plugin_pytorch.nn.RMSNorm`。

---

## 5. model.py 编写

### 5.1 cos/sin 预计算

**参考**：`leap_llm/models/qwen3/model.py` 第 64-72 行。

**关键点**：
- 用 `max_position_embeddings` 计算完整 cache，再截取到 `max_kvcache_len`
- 存为普通属性 `self.cos`/`self.sin`，不用 `register_buffer`

```python
cos, sin = self._set_cos_sin_cache(
    config.max_position_embeddings, head_dim, base=config.rope_theta
)
self.cos = cos[:, :config.max_kvcache_len, :]
self.sin = sin[:, :config.max_kvcache_len, :]
```

### 5.2 forward() 中 cos/sin 索引

**参考**：`leap_llm/models/qwen3/model.py` 第 137-167 行。

```python
# 同步 device/dtype
self.cos = self.cos.to(device=position_ids.device, dtype=inputs_embeds.dtype)
self.sin = self.sin.to(device=position_ids.device, dtype=inputs_embeds.dtype)

# QuantStub 在 gather（对应 leap.gather_nd）之前插入
cos = self.quant_cos(self.cos)
sin = self.quant_sin(self.sin)

position_ids_expanded = position_ids.unsqueeze(-1).expand(-1, -1, cos.size(-1))
cos = torch.gather(cos, 1, position_ids_expanded)
sin = torch.gather(sin, 1, position_ids_expanded)
```

**QuantStub 插入原则**：对照 `leap_llm` 的 `build()` 方法，凡是 `build()` 中使用了 leap 算子的输入，在 `forward()` 中对应操作**之前**插入 QuantStub。

### 5.3 删除不必要的方法

`get_rotary_emb()` 方法在 LLM 推理流程中不会用到，删除。

---

## 6. qwen3_model.py 编写

### 6.1 build_model

**LLM 的 config 更新方式**（与 VLM 的关键差异）：

```python
# LLM：yml 的 text_config 字段直接写入 model_config 本身
update_config_from_custom_config(model_config, self.custom_config.model.text_config)

# VLM：分别写入嵌套的子 config
# update_config_from_custom_config(model_config.vision_config, ...)
# update_config_from_custom_config(model_config.text_config, ...)
```

### 6.2 get_qconfig_setting

**分析方法**：查看 `leap_llm/qwen3/blocks/attention.py` 的量化组件定义：

```python
# leap_llm 中：
self.cache_k_fq = ConstFakeQuant(16)          # → {"output": qint16}
self.cache_v_fq = ConstFakeQuant(8)           # → {"output": qint8}
self.qk_matmul  = FakeQuantMatmul(8, 16, None) # → {"input": [qint8, qint16]}
self.wv_matmul  = FakeQuantMatmul(16, 8, None) # → {"input": [qint16, qint8]}
```

对应 llm_compression 的配置（使用 `get_kvcache_names` + `SetDynamicQuantTemplate`）：

```python
from horizon_plugin_pytorch.dtype import qint16
from horizon_plugin_pytorch.quantization.qconfig_setter import SetDynamicQuantTemplate

module_name_config = {}
# KV cache 配置：用 get_kvcache_names 保持与 sync_kvcache_scales 一致
for name in self.get_kvcache_names(model_name):
    if name.endswith("cache_k_fq"):
        module_name_config[name] = {"output": qint16}
    elif name.endswith("cache_v_fq"):
        module_name_config[name] = {"output": qint8}

# Attention matmul 配置
for i in range(n_layers):
    module_name_config[f"layers.{i}.self_attn._generated_matmul_0"] = {"input": [qint8, qint16]}
    module_name_config[f"layers.{i}.self_attn._generated_matmul_1"] = {"input": [qint16, qint8]}

q_template = q_template + [ModuleNameTemplate(module_name_config, freeze=True)]
# 动态量化配置（替代旧的 dynamic_quant_types 方式）
q_template.append(SetDynamicQuantTemplate(op_kwargs={nn.Linear: {"block_size": "full", "dim": -1}}))
```

---

## 7. process_utils.py 编写

### 7.1 generate_func 整体流程

```
prefill：
  左 padding → 初始化 KV cache → get_causal_mask → prefill_model.forward

decode：
  init_kv_cache（截取有效 token，左 pad 到 max_kvcache_len）→ 循环 decode
```

### 7.2 config 字段访问

**关键差异**：LLM 的 `build_model` 中把 yml 的 `text_config` 直接 update 到 `model_config`，所以 `process_utils` 里直接访问 `config.max_kvcache_len`，**不加 `.text_config`**。

```python
# 正确（LLM）
max_kvcache_len = config.max_kvcache_len

# 错误（把 VLM 的写法搬过来）
max_kvcache_len = config.text_config.max_kvcache_len  # ← AttributeError
```

### 7.3 position_ids dtype 转换

**原则**：dtype 转换在 `process_utils.py` 里做，不在 `model.py` 里做。

```python
# prefill
position_ids = torch.arange(max_lm_input_len, device=..., dtype=torch.long).unsqueeze(0)

# decode
position_ids = cache_position.view(1, 1).long()
```

---

## 8. 配置文件编写

`llm_compression/configs/qwen3.yml`，Qwen3 是 LLM：
- `model_list: [prefill, decode]`（无 visual）
- 不写 `vision_config`
- 不写 `compile.visual`
- `max_lm_input_len: 512`，`max_kvcache_len: 1024`（默认值）

---

## 9. 模型注册

```python
# llm_compression/models/__init__.py
from .qwen2_5_vl.qwen2_5_vl_model import Qwen2_5_VL
from .qwen3.qwen3_model import Qwen3
```

---

## 10. 调试记录

### Bug 1：AttributeError: 'Qwen3Config' has no attribute 'text_config'

**原因**：LLM 的 HF config 本身就是 text config，没有嵌套的 `text_config` 子对象。`process_utils.py` 中错误地使用了 `config.text_config.max_lm_input_len`。

**修复**：`process_utils.py` 中所有 `config.text_config.xxx` 改为 `config.xxx`。

---

### Bug 2：RuntimeError: size mismatch（1528 vs 1024）at dim 3

**错误位置**：`attention.py` 中 `torch.add(attn_weights, attention_mask.unsqueeze(1))`

**根本原因**（多个问题叠加）：

1. `process_utils.py` 中 `causal_mask = get_causal_mask(...).squeeze(0)` 错误地 squeeze 掉了 batch 维，破坏了 4D 结构
2. `attention.py` 中对已是 4D 的 mask 又多了一次 `.unsqueeze(1)`
3. RoPE 后 `key_states` 仍是 3D `[bsz*num_heads, q_len, head_dim]`，`cur_len = key_states.shape[1]` 取的是正确值，但 cat 时 3D 和 4D 不兼容，导致 kv_len 超出预期

**修复**：
1. 去掉 `.squeeze(0)`，`causal_mask` 保持 4D
2. 去掉 `.unsqueeze(1)`，直接 `add`
3. RoPE 后立即 `reshape` 回 4D，`cur_len` 改为 `key_states.shape[2]`

---

### Bug 3：RuntimeError: gather() Expected dtype int64 for index

**原因**：`cache_position` 是 `torch.int32`，view 后直接传入 `torch.gather` 作为 index，而 gather 要求 index 是 int64。

**修复**：在 `process_utils.py` 里转换，decode 阶段 `position_ids = cache_position.view(1, 1).long()`。

**原则**：dtype 转换统一在 `process_utils.py` 里做，不在 `model.py` 里做。

---

## 11. 关键经验总结

### 11.1 参考源的使用方式

- `leap_llm/models/<model_name>/forward()` 是主要参考，**不是** `build()`
- `build()` 是 leap 编译器专用，里面的 `DynamicQuantLinear`/`ConstFakeQuant`/`FakeQuantMatmul` 在 llm_compression 中对应换成 `nn.Linear` + `QuantStub`/`DeQuantStub`
- 量化 bit 数从 `ConstFakeQuant(N)` 和 `FakeQuantMatmul(a, b, None)` 的参数直接读取

### 11.2 QuantStub 插入原则

对照 leap_llm 的 `build()` 方法，凡是 `build()` 中某个输入使用了 leap 算子，在 `forward()` 中对应操作**之前**插入 QuantStub。不能把 QuantStub 随意放置。

### 11.3 shape 管理原则

RoPE 操作通常需要 3D 张量，操作结束后必须立即 reshape 回与 cache 兼容的 4D，再做 cache slice/cat。`cur_len` 的读取维度随 shape 变化。

### 11.4 attention_mask 维度管理

- `get_causal_mask` 输出是 4D `[bsz, 1, seq_len, max_kvcache_len]`，在 `process_utils` 中用 `.squeeze(0)` 去掉 bsz=1 维度传给 model.forward（因为 forward 的 attention_mask 参数是 3D），但**不要 squeeze 其他维度**
- attention 里直接 `add`，**不要额外 unsqueeze**
- cat 后 kv_len 必须始终 = max_kvcache_len，mask 才能对齐

### 11.5 LLM vs VLM 的 config 差异

| 项目 | LLM | VLM |
|---|---|---|
| config 更新目标 | `model_config` 本身 | `model_config.vision_config` / `model_config.text_config` |
| process_utils 访问 | `config.max_kvcache_len` | `config.text_config.max_kvcache_len` |
| 权重映射前缀 | `lm.` | `lm.`（prefill/decode 是 lm 的引用或 deepcopy） |
| model_list | `[prefill, decode]` 或 `[lm]` | `[visual, prefill, decode]` 或 `[visual, lm]` |
| vision_config | 不写 | `image_height/width: 448`（默认） |

### 11.6 dtype 转换原则

数据预处理（包括 dtype 转换）在 `process_utils.py` 里统一完成，`model.py` 里不做。`position_ids` 需要 `int64`，在构造时或传入 forward 前转换。
