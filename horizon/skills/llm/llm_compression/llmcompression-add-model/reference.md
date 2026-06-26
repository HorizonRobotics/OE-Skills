## 代码模板

### attention.py shape 流

```
proj 后:     [bsz, q_len, num_heads * head_dim]
view:        [bsz, q_len, num_heads, head_dim]
norm(若有):  view 后、transpose 前
transpose:   [bsz, num_heads, q_len, head_dim]
RoPE reshape: [bsz * num_heads, q_len, head_dim]  (3D)
RoPE 后必须立即 reshape 回 4D: [bsz, num_kv_heads, q_len, head_dim]
cache cat:   [bsz, num_kv_heads, max_kvcache_len, head_dim]
```

`cur_len` 从 4D 时 `key_states.shape[2]` 读取。

### cache KV 标准模式

```python
if cache_keys is not None and cache_values is not None:
    cache_keys = self.cache_k_fq(cache_keys)              # 量化 cache
    cur_len = key_states.shape[2]
    cache_keys = cache_keys[:, cur_len:].transpose(1, 2)   # 切掉前 cur_len slot
    key_states = self.dequant(key_states)                   # dequant 当前
    cache_keys = self.dequant(cache_keys)                   # dequant cache
    key_states = torch.cat([cache_keys, key_states], dim=2) # cat
    key_states = self.cache_k_fq(key_states)                # 重新量化
```

cat 后 kv_len 必须 = max_kvcache_len。

### QuantStub 标准四件套

```python
self.quant_input_embeds = QuantStub()
self.quant_cos = QuantStub()
self.quant_sin = QuantStub()
self.quant_attention_mask = QuantStub()
self.dequant = DeQuantStub()
```

### cos/sin 索引

```python
cos = self.quant_cos(self.cos)
sin = self.quant_sin(self.sin)
position_ids_expanded = position_ids.unsqueeze(-1).expand(-1, -1, cos.size(-1))
cos = torch.gather(cos, 1, position_ids_expanded)
sin = torch.gather(sin, 1, position_ids_expanded)
```

VLM 使用 mRoPE（3D position_ids）时需按 mrope_section 分别索引再拼接。

### 权重映射模板

```python
hf_model = <HFModelClass>.from_pretrained(model_dir, config=model_config, trust_remote_code=True)
new_state_dict = {}
for key, value in hf_model.state_dict().items():
    new_key = key
    if new_key.startswith("model."):
        new_key = new_key[len("model."):]
    if new_key == "lm_head.weight":
        new_key = "lm.lm_head.weight"
    elif not new_key.startswith("lm."):
        new_key = "lm." + new_key
    new_state_dict[new_key] = value
miss_key, unexpected_key = model.load_state_dict(new_state_dict, strict=False)

# prefill/decode 是 lm 的引用或 deepcopy，不是映射目标
if self.is_shared_lm_mode():
    model.prefill = model.lm
    model.decode = model.lm
else:
    model.prefill = model.lm
    model.decode = copy.deepcopy(model.lm)
```

验证：`miss_key` 仅含 QuantStub 相关 key，`unexpected_key` 合理。

### get_qconfig_setting 模板

```python
from horizon_plugin_pytorch.dtype import qint16
from horizon_plugin_pytorch.quantization.qconfig_setter import SetDynamicQuantTemplate

module_name_config = {}
# KV cache 配置：用 get_kvcache_names 保持命名一致
for name in self.get_kvcache_names(model_name):
    if name.endswith("cache_k_fq"):
        module_name_config[name] = {"output": qint16}
    elif name.endswith("cache_v_fq"):
        module_name_config[name] = {"output": qint8}

for i in range(n_layers):
    module_name_config[f"layers.{i}.self_attn._generated_matmul_0"] = {"input": [qint8, qint16]}
    module_name_config[f"layers.{i}.self_attn._generated_matmul_1"] = {"input": [qint16, qint8]}

q_template = q_template + [ModuleNameTemplate(module_name_config, freeze=True)]
q_template.append(SetDynamicQuantTemplate(op_kwargs={nn.Linear: {"block_size": "full", "dim": -1}}))
```

详细案例见 [qwen3_case_study.md](qwen3_case_study.md)
