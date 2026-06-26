---
name: skills
description: HBDK4模型编译工具的使用指南索引，按任务场景组织
---

> 基于HBDK4版本 **4.9.7** 编写，Docker镜像版本 **v3.9.0_rc4**。

# 流程总览

`.bc`模型有两个来源：
- **PTQ流程**：ONNX模型通过 `hbdk4.compiler.onnx.export` 导出（`ptq.onnx → ptq.bc`）
- **QAT流程**：由其它模块从 `torch.nn.Module` 导出（`qat.bc`），该torch模型不在hbdk工作流内，由外部提供

```
PTQ: ONNX模型(ptq.onnx) → 导出HBIR(ptq.bc) ─┐
                                              ├→ 定点化(quantized.bc) → 编译(HBM) → 部署
QAT: torch.nn.Module → qat.bc（外部提供） ────┘
                                                    │              │
                                               插入预处理节点    性能评估
                                               查询/修改模型     推理验证
                                                                    │
                          完整工作流参考 → references/workflow_reference.md
```

# Skill列表

## 模型导入与序列化
| Skill | 说明 |
|-------|------|
| [model-export.md](model-export.md) | 将ONNX模型导出为伪量化HBIR模型（.bc文件），支持模型统计和可视化 |
| [model-serialization.md](model-serialization.md) | 将HBIR模型保存到.bc文件，或从.bc文件加载HBIR模型 |

## 模型转换与编译
| Skill | 说明 |
|-------|------|
| [model-convert.md](model-convert.md) | 将伪量化HBIR模型转换为指定march的定点模型 |
| [model-compile.md](model-compile.md) | 将定点化HBIR模型编译为HBM文件 |

## 模型修改
| Skill | 说明 |
|-------|------|
| [model-info-query.md](model-info-query.md) | 查询和修改HBIR模型的输入输出、march信息、tensor名称、精度配置等 |
| [insert-nodes.md](insert-nodes.md) | 在HBIR模型输入输出参数上插入预处理节点（pyramid/preprocess/resize/transpose/split/rle） |
| [remove-io-nodes.md](remove-io-nodes.md) | 删除HBIR模型输入输出相邻节点或指定类型/名称的节点 |

## HBM模型
| Skill | 说明 |
|-------|------|
| [model-inference.md](model-inference.md) | 推理HBIR和HBM模型，包括本地推理和远程BPU推理 |
| [hbm-perf.md](hbm-perf.md) | 对HBM模型进行性能分析，包括静态perf和动态perf |
| [hbm-modify.md](hbm-modify.md) | 修改HBM模型描述信息和名称，查询量化信息 |

## 参考
| 文档 | 说明 |
|------|------|
| [references/api_reference.md](references/api_reference.md) | API快速参考 |
| [references/workflow_reference.md](references/workflow_reference.md) | 端到端工作流参考 |

# 快速入门路径

**场景：我有一个ONNX模型，想部署到BPU**

1. [model-export.md](model-export.md) — 导出ONNX为HBIR
2. [model-convert.md](model-convert.md) — 定点化转换
3. [model-compile.md](model-compile.md) — 编译为HBM
4. [hbm-perf.md](hbm-perf.md) — 评估性能

**场景：我需要在模型输入上插入预处理（如NV12输入、归一化）**

1. [model-info-query.md](model-info-query.md) — 查看模型输入输出
2. [insert-nodes.md](insert-nodes.md) — 插入预处理节点
3. [model-convert.md](model-convert.md) — 定点化（insert节点必须在convert前）

**场景：我有一个QAT模型（qat.bc），想部署到BPU**

1. [model-serialization.md](model-serialization.md) — 加载qat.bc
2. [model-convert.md](model-convert.md) — 定点化转换
3. [model-compile.md](model-compile.md) — 编译为HBM
4. [hbm-perf.md](hbm-perf.md) — 评估性能

**场景：我有一个已编译的HBM，想修改描述或验证推理**

1. [hbm-modify.md](hbm-modify.md) — 修改HBM描述
2. [model-inference.md](model-inference.md) — 推理验证

**场景：我想了解完整的端到端流程**

→ [references/workflow_reference.md](references/workflow_reference.md)
