---
name: board-detection
description: 板卡硬件平台检测 Skill。当任务涉及板端运行、板端推理、远端 HBM、性能压测或 BPU 实测，且 .horizon/.env.board 不存在或不完整时触发。自动完成板卡 IP 获取、SSH 架构探测、平台信息写入。
---

# 板卡硬件平台检测

## 执行方式

> **本 Skill 应通过 subagent 执行。** 主 agent 在前置检查中发现 `.env.board` 缺失或不完整时，应将本文件的完整内容作为 subagent prompt 派发执行。subagent 完成后汇报写入结果和需要用户确认的事项（如有），主 agent 读取 `.env.board` 继续后续流程。

## 目标

检测用户的板卡硬件平台信息，写入 `.horizon/.env.board`，供后续所有板端任务直接使用。

## 板卡检查规则

- 板卡类型按三类处理：`nash-e/m`（Linux）、`nash-p`（Linux）与 `nash-b`（QNX）
- 优先从环境变量中查找板卡信息，例如 `HORIZON_BOARD_TYPE`、`OE_BOARD_TYPE`、`BOARD_TYPE`、`BOARD`、`NASH_BOARD`
- 如果环境变量没有提供，再检查项目内相关配置文件，例如 `.env`、`.env.local`、`.horizon/board.env`、`.horizon/board.json`、`AGENTS.md`、`CLAUDE.md`
- 如果任务涉及板端运行、板端推理、远端 HBM、性能压测或 BPU 实测，但没有找到板卡信息，必须先向用户确认是否有可用板卡
- 如果用户明确没有可用板卡，涉及板端的任务应回退到 X86 评测、仿真、静态检查或可离线执行的分析工具，并说明该结果不能替代真实板端验证
- **nash-b 板卡为可选项**：用户可以跳过 nash-b 配置，但系统必须给出明确提示："已跳过 nash-b 板卡配置。后续涉及 nash-b 板端的任务将不可用，仅可在 X86 环境进行编译和离线分析。如需启用，请删除 `.horizon/.env.board` 重新执行板卡检测。"
- 板卡工作目录（`BOARD_WORKDIR`）也是 `.env.board` 完整性的必要字段。如果文件中缺少该字段，需要重新执行工作目录检测（步骤 3.5）

## 检测流程

1. **检查 `.horizon/.env.board` 是否存在**
   - 文件存在且内容完整（包含 `BOARD_TYPE`、`BOARD_IP`、`BPU_ARCH`、`BOARD_WORKDIR` 等字段）→ 直接读取，跳过后续步骤
   - 文件不存在或不完整（含缺少 `BOARD_WORKDIR`）→ 进入步骤 2

2. **获取板卡 IP**
   - 先读取项目根目录 `.env` 文件，查找 `BOARD_IP`、`BOARD_IP_NASH_P`、`BOARD_IP_NASH_B` 等字段
   - 如果 `.env` 中有板卡 IP → 进入步骤 3
   - 如果 `.env` 中没有 → 询问用户是否有可用板卡 IP
     - 用户提供了 IP → 进入步骤 3
     - 用户明确表示没有可用板卡 → 跳过本阶段，说明"当前任务将回退到 X86 评测或仿真模式，结果不能替代真实板端验证"

3. **自动检测板卡架构**
   - 使用 SSH 连接板卡（默认用户名 `root`），执行：
     ```bash
     uname -a
     hrut_somstatus
     ```
   - 从输出中自动解析架构、内核版本、镜像日期、BPU 状态等信息
   - 根据 `.env` 中 IP 与变量的对应关系自动判断板卡类型：
     - `BOARD_IP` / 无后缀 → `nash-e/m`（Linux 平台）
     - `BOARD_IP_NASH_P` / `_NASH_P` 后缀 → `nash-p`（Linux 平台）
     - `BOARD_IP_NASH_B` / `_NASH_B` 后缀 → `nash-b`（QNX 平台，`uname -a` 输出含 `QNX`）
   - **nash-b (QNX) 特殊说明**：nash-b 运行 QNX 实时操作系统，SSH 连接后 `uname -a` 的输出格式与 Linux 不同（系统名为 `QNX`，无发行版信息）。`hrut_somstatus` 命令仍可用。如果 SSH 连接或命令执行失败，可能是 QNX 板卡的 SSH 服务配置不同，需要向用户确认
   - **全程不需要用户手动确认架构信息，全部自动推断**
   - **跳过选项**：对于每种板卡类型，用户都可以选择跳过。跳过时给出明确提示：
     > ⚠️ 已跳过 [板卡类型] 的配置。后续涉及该板卡的板端任务将不可用。如需启用，请删除 `.horizon/.env.board` 重新执行板卡检测。

3.5. **检测板卡工作目录**
   - 通过 SSH 连接板卡，检查常见大容量挂载点的可用空间：
     ```bash
     df -BM --output=target,avail | grep -E '^/(map|mnt|data)' | sort -t'M' -k2 -n -r
     ```
   - 从输出中选出可用空间最大的挂载点（如 `/map`、`/mnt`、`/data`）
   - 在该挂载点下创建 `oe-skill-test` 工作目录：
     ```bash
     mkdir -p <挂载点>/oe-skill-test
     ```
   - 将完整路径（如 `/map/oe-skill-test`）记录为 `BOARD_WORKDIR`
   - 如果所有候选挂载点均不可用或空间不足（< 1GB），向用户提示并询问替代路径
   - 每块板卡独立检测，分别记录 `BOARD_WORKDIR`（nash-e/m）、`BOARD_WORKDIR_NASH_P`（nash-p）和 `BOARD_WORKDIR_NASH_B`（nash-b）
   - **nash-b (QNX) 注意**：QNX 系统的 `df` 命令参数与 Linux 不同，可能需要使用 `df -k` 替代 `df -BM`，并根据输出格式调整解析逻辑

4. **写入 `.horizon/.env.board`**
   ```bash
   # 板卡硬件平台信息（自动生成）

   # === 板卡 1: J6E/M ===
   BOARD_IP=<板卡 IP>
   BOARD_USR=root
   BOARD_TYPE=nash-e/m
   BPU_ARCH=<nash-e 或 nash-m>
   PLATFORM=J6E/M
   KERNEL_VERSION=<内核版本>
   IMAGE_DATE=<镜像日期>
   BPU_CORES=<BPU 核数>
   BOARD_WORKDIR=<挂载点>/oe-skill-test

   # === 板卡 2: J6P ===
   BOARD_IP_NASH_P=<板卡 IP>
   BOARD_TYPE_NASH_P=nash-p
   BPU_ARCH_NASH_P=nash-p
   PLATFORM_NASH_P=J6P
   KERNEL_VERSION_NASH_P=<内核版本>
   IMAGE_DATE_NASH_P=<镜像日期>
   BPU_CORES_NASH_P=<BPU 核数>
   BOARD_WORKDIR_NASH_P=<挂载点>/oe-skill-test

   # === 板卡 3: J6B (nash-b / QNX 平台) ===
   # 如用户无 nash-b 板卡，以下字段保持注释状态，并添加跳过提示
   BOARD_IP_NASH_B=<板卡 IP>
   BOARD_USR_NASH_B=root
   BOARD_TYPE_NASH_B=nash-b
   BPU_ARCH_NASH_B=nash-b
   PLATFORM_NASH_B=J6B
   KERNEL_VERSION_NASH_B=<内核版本>
   IMAGE_DATE_NASH_B=<镜像日期>
   BPU_CORES_NASH_B=1
   BOARD_WORKDIR_NASH_B=<挂载点>/oe-skill-test
   ```
   - 后续任务直接读取此文件，无需重复检测
   - 如果某类板卡用户没有，对应段保持注释状态，并在段头添加：`# ⚠️ 未配置：用户跳过或无此板卡`
   - 如果只有一块板卡，只写对应那一段即可

## 注意事项

- **硬件平台是量化配置的关键依据**：`nash-p` / J6P 使用 `fp16+int8`，`nash-e/m` / J6E/J6M 与 `nash-b` / J6B 使用 `int8`，平台信息错误会导致量化失败
- **nash-b 是 QNX 实时操作系统**：与 nash-e/m 和 nash-p 的 Linux 系统不同，nash-b 运行 QNX，部分命令行为可能有差异。SSH 检测时如果 `uname -a` 返回的系统名为 `QNX`，即可确认为 nash-b 板卡
- **nash-b 的 BPU 核数为 1**：`core_num` 只能设为 1，且不支持 `max_l2m_size` 参数
- 如果用户更换了板卡，需要删除 `.horizon/.env.board` 重新检测
