# 基础结构量化编译 Skill 使用指南

## 功能概述

本 Skill 帮你自动生成**基础网络结构**的量化编译全流程代码——从 `set_march` 到编译出 HBM 文件。

覆盖的完整流程：

```
set_march → 定义模型（含 Quant/DeQuant）→ 配置量化参数 → prepare → 校准 → [可选] QAT 训练 → export → convert → remove_io_op → statistics → compile HBM
```

### 支持的网络结构

- 单算子：Conv2d、Linear
- 多算子组合：Conv+BN+ReLU+Linear 等
- 含 Matmul 的结构：MultiheadAttention、TransformerEncoder
- 多输入/多输出网络

### 不支持的场景

- 动态控制流（if/else 分支）模型
- 非基础结构的复杂模型（如带自定义算子）

---

## 怎么触发

只要你的需求涉及**从量化到编译的任何环节**，直接描述即可。你不需要提到"skill"或任何特定术语。

---

## 触发示例

### 全流程：从 set_march 到 HBM

当你需要完整的量化编译代码时，以下说法都能触发：

> 帮我写一个 Conv2d 的量化编译全流程代码，模型只有一个卷积层，输入是 (1, 3, 32, 32)，march 用 nash-p

> 我有个 Linear 层，输入维度 64 输出维度 10，帮我量化部署到 J6H 平台

> 帮我生成 Conv+BN+ReLU+Linear 网络的量化编译代码，从 set_march 到编译出 HBM

> 在地平线 J6P 上量化部署一个简单的分类网络

> 帮我做 QAT 量化训练然后编译出 HBM，模型是 Conv+ReLU

### MultiheadAttention / Transformer 结构

> 我的模型有一个 MultiheadAttention 加一个 Linear，帮我做量化编译到 nash-m

> 帮我给 nn.MultiheadAttention(embed_dim=128, num_heads=4) 做量化流程代码，校准就行不需要 QAT，march 用 nash-p

> 我有个简单的 TransformerEncoder（1 层，embed_dim=64），帮我量化部署到 J6E

### 多输入网络

> 我的网络有两个图像输入，一个 RGB 一个深度图，分别过 Conv 然后拼接，帮我量化编译到 nash-p

> 模型接收图像 tensor 和关键点坐标 tensor，图像过 backbone，关键点过 MLP，然后融合，帮我做量化流程

> 网络输入是图像 tensor、一个 bool mask 和一个 float scale，帮我量化部署到 nash-h

### 多输出网络

> 检测网络输出 logits 和 boxes 两个 tensor，帮我做量化编译到 nash-p

> 模型输出三个不同尺度的特征图，帮我做量化流程，march 用 nash-m，只校准不 QAT

> 网络返回一个 dict，里面有 "logits" 和 "boxes"，帮我量化部署

### 只需要量化（不编译）

> 帮我给 Conv+ReLU 网络做量化，校准就行

> 我的模型需要配置量化参数并校准，march 用 nash-p

### 只需要导出编译（已有量化模型）

> 我已经有 qat_net 了，帮我从 export 开始到编译出 HBM，march 是 nash-p

> 怎么把量化后的模型编译成 HBM 文件？

> 编译 HBM 之前为什么要 remove_io_op？帮我生成完整导出编译代码

---

## 使用流程

触发 Skill 后，会依次确认以下信息：

1. **目标平台（march）** — 必选，从 J6P/J6H/J6M/J6E/J6B 中选择
2. **是否进行 QAT 训练** — 校准后直接导出，还是校准 + QAT 训练再导出
3. **模型结构和输入信息** — 默认 Conv+BN+ReLU+Linear，(1,3,32,32)，可按需修改

确认后自动生成可运行的完整代码。
