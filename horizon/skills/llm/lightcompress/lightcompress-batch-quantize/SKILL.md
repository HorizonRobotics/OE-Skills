---
name: lightcompress-batch-quantize
version: 2.0.3
description: 批量执行 LightCompress 量化实验并生成对比表。

---

# LightCompress 批量量化实验

## 概述

批量执行 = 循环调用 `lightcompress-quant-explore` skill。本 skill 只负责编排，不重复实现单实验逻辑。

## Phase 1: 解析用户输入，展开实验列表

将用户输入展开为实验的笛卡尔积：`models x methods x configs`。

示例输入：
```text
对 Qwen3-0.6B、Qwen2.5-7B 跑 RTN W8A8 和 GPTQ W4A8 量化
```

展开为 4 个实验：
1. Qwen3-0.6B + RTN W8A8
2. Qwen3-0.6B + GPTQ W4A8
3. Qwen2.5-7B + RTN W8A8
4. Qwen2.5-7B + GPTQ W4A8

## Phase 2: 检查精度缓存

调用 `quant-accuracy-cache` skill 查询每个实验是否已有结果。

匹配规则：model.name + quant.method + quant.w_bit + quant.a_bit。

- 命中缓存：记录结果，从待执行列表中移除
- 未命中缓存：保留在待执行列表

## Phase 3: 逐个调用 lightcompress-quant-explore

对待执行列表中的每个实验：

1. 调用 `lightcompress-quant-explore` skill 启动实验
   - **不指定 GPU**，让子 skill 自动选择空闲 GPU
2. 等待实验真正启动（通过 `nvidia-smi` 确认显存占用上升）
3. 启动下一个实验

自动回答子 skill 的交互问题：
| 子 skill 问题 | 预设答案 |
|---------------|----------|
| 开始实验 / 取消 | 开始实验 |
| 保存到缓存 / 跳过 | 保存到缓存 |
| 缓存冲突处理 | 保留两者 |

## Phase 4: 汇总结果，生成对比表

所有实验完成后，汇总为对比表：

```markdown
| 模型 | 方法 | 配置 | Pretrain PPL | Fake Quant PPL | PPL 变化 | 来源 |
|------|------|------|--------------|----------------|----------|------|
| Qwen3-0.6B | RTN | W8A8 | 21.30 | 22.15 | +0.85 | 实验 |
| Qwen2.5-7B | GPTQ | W4A8 | 7.00 | 7.45 | +0.45 | 缓存 |
```

调用 `quant-accuracy-cache` 保存新产生的实验结果。

## 与其他 Skill 的协作

| Skill | 关系 | 说明 |
|-------|------|------|
| `lightcompress-quant-explore` | 依赖 | 单实验执行引擎，负责 GPU 选择、配置生成、实验运行 |
| `quant-accuracy-cache` | 协作 | 实验前查询缓存跳过重复，实验后保存结果 |
