# Quant/DeQuant 部署边界插入规则

本文件定义了在模型中插入 `QuantStub`/`DeQuantStub` 的完整规则，供 `j6-plugin-quantization` skill 参考。

## 目录

1. [核心概念](#核心概念)
2. [核心规则](#核心规则)
3. [判断部署边界内/外](#判断部署边界内外)
4. [标准模板](#标准模板)
5. [常见错误](#常见错误)

## 核心概念

- **部署模块 / 部署子图**：推理落板时真正需要保留、需要进入量化图的部分，例如 backbone、neck、head
- **非部署模块 / 非部署逻辑**：只在训练、评估、可视化、后处理中使用，例如 loss、matcher、NMS、metrics

`QuantStub -> ... -> DeQuantStub` 中间这段，应该只包含**部署模块**。

## 核心规则

1. **quant/dequant 是部署边界**：标记从哪里开始/结束部署（进入/离开量化图）
2. **每个输入和输出都单独创建 quant/dequant**：不要复用同一个 stub 处理多个输入或多个输出
3. **QuantStub 初始化不设置 scale**：不要传 `scale=...`，交给量化流程决定
4. **QuantStub 只针对浮点 tensor**：只有浮点 tensor 输入/输出才需要插入 quant/dequant
5. **scalar 或非浮点 tensor 不插入 QuantStub**：标量、`bool`、整数/索引、已是定点语义的 tensor，不插 quant
6. **quant 和 dequant 之间只放部署逻辑**：loss、训练标签处理、评价指标、前后处理、可视化等非部署逻辑必须放在边界之外
7. **train/eval 的边界定义必须一致**：不要仅因 `self.training` 为真/假就改变"哪里需要 dequant"的位置
8. **图内常量 tensor 输入要纳入 quant 语义**：如 `x + const_tensor` 里的 `const_tensor`，如果是 tensor 形式则应量化；scalar 可按属性处理

## 判断部署边界内外

### 可以放在 quant 与 dequant 之间的内容

- 主干网络 / backbone
- neck / encoder / decoder / detection head
- 明确要参与板端推理的特征变换
- 明确属于部署图一部分的张量级算子

### 不能放在 quant 与 dequant 之间的内容

- loss 计算
- matcher / assigner / target builder
- 训练分支专用监督逻辑
- 输入前处理（dataloader / Python 侧处理）
- 输出后处理（NMS、阈值过滤、格式整理、映射回原图）
- evaluator / metrics / logger / visualizer
- `.cpu()` / `.numpy()` / Python list/dict 整理 / 画图 / dump 文件

## 标准模板

### 单输入、单输出

```python
class MyNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.quant = QuantStub()
        self.dequant = DeQuantStub()
        self.net = ...

    def forward(self, x):
        x = self.quant(x)                # 部署输入边界
        y = self.net(x)
        y = self.dequant(y)              # 部署输出边界
        return y
```

### 多输入（每个 tensor 输入一个 QuantStub）

```python
class MyNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.quant_img = QuantStub()      # 每个输入独立 stub
        self.quant_points = QuantStub()
        self.dequant_out = DeQuantStub()
        self.net = ...

    def forward(self, img, points, meta=None):
        img = self.quant_img(img)
        points = self.quant_points(points)
        out = self.net(img, points, meta=meta)  # meta 非 tensor 不量化
        out = self.dequant_out(out)
        return out
```

### 多输出（每个输出一个 DeQuantStub）

```python
class MyNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.quant_x = QuantStub()
        self.dequant_logits = DeQuantStub()    # 每个输出独立 stub
        self.dequant_boxes = DeQuantStub()
        self.backbone = ...
        self.head = ...

    def forward(self, x):
        x = self.quant_x(x)
        feats = self.backbone(x)
        logits, boxes = self.head(feats)
        logits = self.dequant_logits(logits)
        boxes = self.dequant_boxes(boxes)
        return logits, boxes
```

### 混合输入（只有浮点 tensor 才插 QuantStub）

```python
def forward(self, x, mask, ids, scale_factor: float):
    x = self.quant(x)              # x 是浮点 tensor，需要 quant
    # mask 是 bool tensor，不插 quant
    # ids 是整型 tensor，不插 quant
    # scale_factor 是 scalar，不插 quant
    out = self.net(x, mask=mask, ids=ids, scale_factor=scale_factor)
    out = self.dequant(out)
    return out
```

### dict 输出（按 key 独立 dequant）

```python
def forward(self, x):
    x = self.quant_x(x)
    out = self.net(x)  # out: dict
    out["logits"] = self.dequant_logits(out["logits"])
    out["boxes"] = self.dequant_boxes(out["boxes"])
    return out
```

### 部署输出之后还有 float-only 后处理

```python
# 正确：非部署逻辑放在边界外
x = self.quant(x)
pred = self.head(x)
pred = self.dequant_pred(pred)      # 先离开量化图
pred = self.nms_postprocess(pred)   # 再做非部署逻辑
return pred
```

### 训练时有 loss，部署时只要预测结果

```python
# 正确：loss/criterion 放在边界外
x = self.quant(x)
pred = self.head(x)
pred = self.dequant_pred(pred)

if self.training:
    loss = self.criterion(pred, targets)
    return pred, loss
return pred
```

## 常见错误

1. **复用同一个 stub 处理多个输入/输出** — 改为一一对应的独立 stub
2. **dequant 放太早** — 导致后续模块跑在 float 上，只在真正离开部署图时 dequant
3. **用 `self.training` 决定是否 dequant** — 边界定义应一致，不要 train/eval 两套边界
4. **把非部署逻辑放在 quant 和 dequant 之间** — loss/NMS/后处理/评估等放在边界外
5. **设置 `QuantStub(scale=...)`** — 不要传 scale，交给量化流程决定
6. **对非浮点 tensor 强行插 QuantStub** — scalar、bool、整型 tensor 不需要
