---
name: ucp
description: 地平线 J6 UCP 技能入口，通过路由机制将用户意图分发至对应子 skill，涵盖模型性能评测、HBM 推理部署、推理代码生成、Perfetto Trace 采集与分析等能力。
---

# UCP Skill

## 概述

本 skill 是地平线 J6 UCP 的统一入口，涵盖模型性能评测、HBM 推理部署、推理代码生成、Perfetto Trace 采集与分析等能力。通过内部路由机制将用户意图分发至对应的子 skill，仅加载命中的子 skill 以节省上下文开销。

## 路由职责

本文件是 UCP skill 的路由入口，负责：
1. 根据用户意图将任务路由至对应的子 skill
2. 仅加载命中路由的子 skill，避免未使用的 skill 占用上下文
3. 规范路由表的注册与移除流程，路由表增删操作须严格执行 `ROUTING_OPS.md` 中的步骤，不得跳过
4. 兼容不同来源的 skill（多源规范详见 `ROUTING_OPS.md`）

## 路由表

路由表是子 skill 分发的唯一依据。

### 字段定义

| 字段 | 必填 | 说明 |
|------|------|------|
| `skill_name` | 是 | 子 skill 目录名，对应 `.skills/<skill_name>/` |
| `trigger_keywords` | 是 | 触发关键词（逗号分隔），匹配任一即命中，不区分大小写 |
| `trigger_patterns` | 否 | 正则模式（`\|` 分隔），用于精确意图识别 |
| `priority` | 是 | 优先级，数值越小越优先，多个子 skill 命中时按此排序 |
| `source` | 是 | 来源：`local` / `shared`（见「多源规范」） |
| `enabled` | 是 | 是否参与路由，`false` 时跳过该条目 |

### 当前路由表

| skill_name | trigger_keywords | trigger_patterns | priority | source | enabled |
|------------|-----------------|-----------------|----------|--------|---------|
| `j6-ucp-model-perf-eval` | 性能测试, perf评测, benchmark, 板端测试, 模型性能, hrt_model_exec | `hrt_model_exec.*perf\b\|perf[_-]?(评测\|测试\|评估)` | 20 | local | true |
| `j6-ucp-hbm-infer` | hbm_infer, HbmRpcSession, X86客户端, 模型部署 | `hbm_infer\w*\|\bHbmRpcSession\b\|\bHTensor\b` | 30 | local | true |
| `j6-ucp-infer-generating` | UCP推理代码, C++推理, tensor内存, 推理任务, Cache同步, DNN接口, 代码生成 | `\b生成.*推理.*代码\b\|\b推理.*C\+\+.*代码\b` | 40 | local | true |
| `j6-ucp-perfetto-trace-catcher` | 抓trace, trace采集, Perfetto采集, pftrace采集, hrt_model_exec tracing, tracebox | `\b(抓|采集|capture|collect).*trace\b|\btracebox\b` | 45 | local | true |
| `j6-ucp-perfetto-trace-analysis` | Perfetto, pftrace, 性能瓶颈, 推理延迟, pipeline stalls, 有效占用率, trace分析 | `\.pftrace\b\|\bperfetto\b` | 50 | local | true |
| `j6-board-monitor` | BPU监控, DDR带宽, 内存使用, 资源监控, 设定帧率, hrt_ucp_monitor, hrut_ddr, 板端资源, 占用率监控 | `\b(BPU|DDR|内存).*(监控|监测|测量)\|\b(10Hz|20Hz|30Hz).*推理\|hrt_ucp_monitor\|hrut_ddr` | 25 | local | true |

## 路由算法

```
输入: 用户消息
输出: 命中的子 skill 列表（按 priority 升序）

1. 遍历路由表中 enabled=true 的条目
2. 对每条规则:
   a. trigger_keywords: 用户消息是否包含任一关键词（不区分大小写）
   b. trigger_patterns: 用户消息是否匹配任一正则
   c. a 或 b 命中即记录该子 skill 及其 priority
3. 按 priority 升序排列命中结果
4. 返回排序列表
```

### 路由决策

- **有命中**：按 priority 顺序全量加载所有命中的子 skill。命中的子 skill 均与用户意图相关，应全部加载
- **无命中**：不加载任何子 skill，按常规方式处理

## 加载方式

路由命中后，**全量读取** `.skills/<skill_name>/` 下所有文件（`SKILL.md` 须存在且作为主文件优先加载）：

| 要求 | 说明 |
|------|------|
| `SKILL.md` | **须存在**，包含子 skill 的适用场景、流程、约束 |
| 其余文件 | **按需加载**，不限制文件名和结构，各子 skill 自行组织 |

未命中路由的子 skill 目录不做任何读取。

## 路由表增删

注册、移除流程及多源规范详见 [ROUTING_OPS.md](ROUTING_OPS.md)。修改路由表时须按该文件步骤执行，不得跳过。
