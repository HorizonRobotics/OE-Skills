---
name: j6-plugin-insert-quant-dequant
description: 为浮点 PyTorch 模型插入部署边界 QuantStub/DeQuantStub（horizon_plugin_pytorch）。满足：quant/dequant 是部署边界；每个输入/输出各自独立 stub；QuantStub 初始化不设置 scale。
---

# 给任意浮点模型插入 Quant/DeQuant（Horizon 部署边界版）

## 目标

把任意 **浮点** `torch.nn.Module` 改造成可被 `horizon_plugin_pytorch` 量化工具链处理的形式：在**部署输入边界**插入 `QuantStub`，在**部署输出边界**插入 `DeQuantStub`。

这里必须先区分两类逻辑：

- **部署模块 / 部署子图**：推理落板时真正需要保留、需要进入量化图的部分，例如 backbone、neck、head、deploy module 等。
- **非部署模块 / 非部署逻辑**：只在训练、评估、可视化、日志或 CPU/浮点后处理中使用，不属于最终部署子图，例如 loss 计算、matcher、target assign、NMS 后处理、结果格式整理、metrics、debug print、可视化等。

`QuantStub -> ... -> DeQuantStub` 中间这段，应该只包含**部署模块**。凡是**部署时不需要**的逻辑，都不应该被夹在 quant 和 dequant 中间。

本 Skill 强约束：

- **quant/dequant 是部署边界**：标记从哪里开始/结束部署（进入/离开量化图）。
- **每个输入和输出都单独创建 quant/dequant**：不要复用同一个 stub 处理多个输入或多个输出。
- **QuantStub 初始化不要设置 scale**：不要传 `scale=...`，交给量化流程决定。
- **QuantStub 只针对浮点 tensor**：只有浮点 tensor 输入/输出才需要按部署边界插入 quant/dequant。
- **scalar 或非浮点 tensor 不插入 QuantStub**：标量（scalar），以及 `bool`、整数/索引、已是定点语义的 tensor，不要为了“形式统一”强行插 quant。
- **quant 和 dequant 之间只放部署逻辑**：loss、训练标签处理、评价指标、前后处理、可视化等非部署逻辑必须放在边界之外。
- **train/eval 的边界定义必须一致**：不要仅因 `self.training` 为真/假就改变“哪里需要 dequant”的位置；是否 `dequant` 取决于后续逻辑是否已经离开部署图，而不是取决于当前处于训练还是评估模式。
- **区分“边界输入”和“图内常量输入”**：`QuantStub/DeQuantStub` 负责标注部署边界；但如果部署图内部存在参与算子计算的 **tensor 常量输入**（例如 `x + const_tensor` 里的 `const_tensor`），也必须把它纳入 quant 语义。标量（scalar）可按算子属性处理，不显式插 quant 节点；**tensor 形式的常量输入应视为输入参与量化**。

## 第零步：先判断谁属于“部署边界内”

在插入 `QuantStub/DeQuantStub` 之前，先把目标代码拆成两段：

### A. 可以放在 quant 与 dequant 之间的内容

这些通常属于部署模块：

- 主干网络 / backbone
- neck / encoder / decoder / detection head
- 明确要参与板端推理的特征变换
- 明确属于部署图一部分的张量级算子

### B. 不能放在 quant 与 dequant 之间的内容

这些通常属于非部署逻辑：

- loss 计算
- matcher / assigner / target builder
- 训练分支专用监督逻辑
- 输入前处理（如果它不属于模型部署图，而是 dataloader / Python 侧处理）
- 输出后处理（如 NMS、阈值过滤、格式整理、映射回原图）
- COCO evaluator / metrics / logger / visualizer
- `.cpu()` / `.numpy()` / Python list/dict 整理 / 画图 / dump 文件

如果某段逻辑在板端部署时不会保留，就不要把它塞进 quant/dequant 边界里。

补充说明：

- “输入”不只指 `forward(...)` 的外部参数，也包括部署图内部某个算子的独立输入。
- 因此，一个由模型内部构造出来的常量 `Tensor`，只要它作为 `add/cat/matmul/attention` 等算子的输入参与部署图计算，就不能把它当成“天然 float 附件”忽略量化。
- 但这不意味着要把它误改成新的部署边界：**边界 QuantStub 仍只负责模型 I/O 边界**；图内常量 `Tensor` 的重点是“必须进入 quant 语义”，而不是“必须伪装成外部输入”。

## 标准改法（通用模板）

### 1) 增加 import

```python
from horizon_plugin_pytorch.quantization import QuantStub
from torch.quantization import DeQuantStub
```

### 2) 在 `__init__` 中：为每个输入/输出创建独立 stub

#### 情况 A：单输入、单输出

```python
self.quant_x = QuantStub()
self.dequant_y = DeQuantStub()
```

#### 情况 B：多输入（每个输入一个 QuantStub）

假设签名是 `forward(self, x, y, meta=None)`，其中 `x/y` 是 tensor，`meta` 是非 tensor：

```python
self.quant_x = QuantStub()
self.quant_y = QuantStub()
```

说明：

- **不要**把 `x/y` 共同送进同一个 `self.quant`。
- 只有**浮点 tensor**（如 `float16/float32`）通常需要量化。
- 非 tensor（如 `meta`）通常不量化。
- scalar、`bool` tensor、整型/索引 tensor、已是定点语义的 tensor，通常也**不**作为 `QuantStub` 的对象。

例如：

```python
def forward(self, x, mask, index, scale_factor: float):
    x = self.quant_x(x)         # x 是浮点 tensor，需要 quant
    # mask 是 bool tensor，不插 quant
    # index 是整型 tensor，不插 quant
    # scale_factor 是 scalar，不插 quant
    out = self.net(x, mask=mask, index=index, scale_factor=scale_factor)
    ...
```

#### 情况 C：多输出（每个输出一个 DeQuantStub）

假设模型返回 `(logits, boxes)`：

```python
self.dequant_logits = DeQuantStub()
self.dequant_boxes = DeQuantStub()
```

### 3) 在 `forward` 中：只在部署边界调用 stub（且覆盖所有 return 路径）

核心原则：

- `quant` 之后立即进入**部署模块**
- `dequant` 之后才能进入**非部署逻辑**
- 不要写成“量化 -> loss/后处理/评估 -> 反量化”这种错误边界

#### 情况 A：单输入、单输出

```python
x = self.quant_x(x)
y = self.net(x)
y = self.dequant_y(y)
return y
```

#### 情况 B：多输入

```python
x = self.quant_x(x)
y = self.quant_y(y)
out = self.net(x, y, meta=meta)
...
```

#### 情况 C：tuple/list 输出（逐项独立 dequant）

```python
logits, boxes = self.head(feats)
logits = self.dequant_logits(logits)
boxes = self.dequant_boxes(boxes)
return logits, boxes
```

#### 情况 D：dict 输出（按 key 独立 dequant）

```python
out = {"logits": logits, "boxes": boxes, "features": feats}

out["logits"] = self.dequant_logits(out["logits"])
out["boxes"] = self.dequant_boxes(out["boxes"])
return out
```

#### 情况 E：部署输出之后还有 float-only 后处理

典型错误写法：

```python
x = self.quant_x(x)
pred = self.head(x)
pred = self.nms_postprocess(pred)      # 错：如果这不是部署图的一部分，就不该夹在中间
pred = self.dequant_pred(pred)
return pred
```

正确思路是先明确部署输出边界，再离开量化图：

```python
x = self.quant_x(x)
pred = self.head(x)
pred = self.dequant_pred(pred)
pred = self.nms_postprocess(pred)      # 对：非部署逻辑放在边界外
return pred
```

#### 情况 F：训练时有 loss，部署时只要预测结果

典型错误写法：

```python
x = self.quant_x(x)
pred = self.head(x)
loss = self.criterion(pred, targets)   # 错：loss 不属于部署图
pred = self.dequant_pred(pred)
return pred, loss
```

正确思路：

```python
x = self.quant_x(x)
pred = self.head(x)
pred = self.dequant_pred(pred)

if self.training:
    loss = self.criterion(pred, targets)
    return pred, loss
return pred
```

也就是说：

- `criterion / loss / matcher` 这类逻辑应在 `dequant` 之后，或者更外层的训练引擎里完成
- 不要为了“图方便”把训练专用逻辑留在部署边界内部

进一步强调：

- 如果训练态下，模型输出会立刻送去 `criterion / matcher / assigner / metrics / Python 后处理`，那么这些输出在训练态**同样应该先 dequant**。
- 不要写成“评估时 dequant，训练时不 dequant”的分裂边界，除非你能明确证明训练态返回值仍然继续留在部署图内部、还会被后续量化模块使用。

典型错误写法：

```python
x = self.quant_x(x)
pred = self.head(x)

if not self.training:
    pred = self.dequant_pred(pred)

return pred
```

上面这段的问题是：

- 评估态把 `pred` 视作部署边界输出；
- 训练态却又把 `pred` 留在量化图内部；
- 于是同一个返回值在 train/eval 下拥有两套不同的边界定义。

如果 `pred` 在训练时马上就会送入 loss/matcher，那么这也是错误边界。

更合理的写法通常是：

```python
x = self.quant_x(x)
pred = self.head(x)
pred = self.dequant_pred(pred)

if self.training:
    loss = self.criterion(pred, targets)
    return pred, loss
return pred
```

或者如果 `criterion` 在模型外：

```python
x = self.quant_x(x)
pred = self.head(x)
pred = self.dequant_pred(pred)
return pred
```


#### 情况 G：图内部的常量 tensor 输入

假设模型内部存在：

```python
def fun(x, const_tensor):
    return x + const_tensor
```

其中 `const_tensor` 虽然不是用户从 `forward(...)` 外部传进来的，但它是 `add` 的一个 **tensor 输入**。这种场景应遵守：

- 如果 `const_tensor` 是 **scalar 常量**（如 `x + 1.0`），通常可按 scalar 处理，不一定显式插 quant 节点。
- 如果 `const_tensor` 是 **Tensor 常量输入**（如 shape 为 `[1, H*W, C]` 的位置编码），则应纳入 quant 处理，不能直接把量化 tensor 与裸 float tensor 混用。

换句话说：

- **它不一定是部署边界输入**；
- **但它严格来说仍然是算子输入**；
- 因此 **浮点 tensor 形式的常量输入也要量化**。
- 如果该常量只是 scalar，或者本身是 `bool` / 整型 / 已有定点语义的 tensor，则通常不需要额外插 `QuantStub`。

### 4) 多分支/早返回：每条 return 都要符合部署边界定义

如果有：

- `if return_features: return feats`
- `if not include_top: return feats_list`

你必须明确这些返回值是否属于“**部署输出边界**”：

- **如果是部署输出**：每个输出分别 `DeQuantStub()`。
- **如果不是部署输出**（仍在部署内部，供后续量化模块消费）：**不要 dequant**，保持量化态。

补充判断标准：

- 如果返回值马上还要进入 loss、评估器、可视化、Python 后处理，这通常说明这里已经到了**部署边界外**，应先 `dequant`
- 如果返回值还要继续流入另一个部署模块，则这里仍在**部署边界内**，不应提前 `dequant`

## 约定与命名建议（便于审查）

- 输入量化 stub：`quant_<argname>`（如 `quant_x`、`quant_img`、`quant_points`）
- 输出反量化 stub：`dequant_<outname>`（如 `dequant_logits`、`dequant_boxes`）
- 如果输出是 `list` 且有固定语义：用语义命名多个 dequant（不要 `dequant0/dequant1`，除非确实没有语义名）。

## 常见坑（按本 Skill 直接规避）

- **不要复用 stub**：一个 `QuantStub` 同时量化多个输入，或一个 `DeQuantStub` 同时反量化多个输出，都会让部署边界不清晰且不符合本规范。
- **不要设置 QuantStub(scale=...)**：这里强制不传 scale。
- **不要见到 tensor 就一律 quant**：只有浮点 tensor 才是 `QuantStub` 的目标；scalar、`bool` tensor、整型/索引 tensor、已是定点语义的 tensor，不要强行插 quant。
- **不要把 dequant 放太早**：只在你要离开部署/量化图时 dequant（例如进入 float-only 后处理、numpy/CPU 逻辑、显示/导出等）。
- **不要用 `self.training` 直接决定是否 dequant**：`dequant` 的依据应是“后续是否进入部署边界外逻辑”，而不是“当前是不是训练模式”。
- **不要把非部署逻辑放在 quant/dequant 中间**：例如 loss、matcher、后处理、metrics、可视化、数据格式转换等。
- **不要把“训练需要”误认为“部署需要”**：训练图里会出现的逻辑，不代表就应该保留在部署量化边界内。
- **不要把 dataloader/数据预处理硬塞进量化图**：如果它本来是模型外的 Python 逻辑，就应该继续放在边界外。
- **不要把图内浮点 tensor 常量输入误判成“无需量化的 float 附件”**：像位置编码、常量 bias tensor、参与 `cat/add/matmul` 的固定 tensor，只要是浮点 tensor 且作为算子输入，就应纳入 quant 语义；只有 scalar 常量，或 `bool`/整型/已定点语义 tensor，才通常不需要单独插 quant 节点。
- **不要把图内 tensor 常量输入误改造成新的模型边界**：它需要量化，不代表它必须被重构成新的 `forward(...)` 外部输入；仍应优先保持在部署图内部处理。

## 快速自检清单

- `__init__` 中：每个**部署输入浮点 tensor** 都有独立的 `QuantStub()`；每个**部署输出浮点 tensor** 都有独立的 `DeQuantStub()`。
- scalar、`bool` tensor、整型/索引 tensor、已是定点语义的 tensor，是否避免了误插 `QuantStub()`？
- 是否已经明确区分：哪些模块属于部署、哪些逻辑属于非部署？
- `QuantStub` 和 `DeQuantStub` 中间，是否只包含部署时真正需要保留的模块？
- 部署图内部若存在常量 **浮点 Tensor** 形式的算子输入，是否已经确保它进入 quant 语义，而不是与量化 tensor 直接做 float 混算？
- loss / matcher / 前处理 / 后处理 / evaluator / 可视化 / numpy 转换，是否都在边界之外？
- `forward` 中：所有 return 路径都严格遵守同一套部署边界定义。
- train / eval 下是否对同一类返回值使用了**一致的边界定义**，而不是一边 `dequant`、一边不 `dequant`？
- `QuantStub()` 初始化无 `scale` 参数。

