---
name: j6-hbdk-compile
description: 通用模型编译 skill。基于 YAML 配置文件驱动，支持 ONNX 和 BC 模型格式。支持从 PTQ config 自动提取输入预处理参数。工作流：生成配置 -> 默认必须经用户确认 -> 再执行编译与报告。Use when the user mentions 模型编译、compile、导出 hbm、生成上板产物、pyramid 输入、resizer 输入。
---

# J6 HBDK Compile - 通用模型编译 Skill

> 版本: 1.1.8

## 概述

本 skill 基于 YAML 配置文件驱动模型编译流程：
1. 解析用户指令 -> 生成配置文件
2. 用户确认配置文件 -> 是否需要修改
3. 加载配置并执行编译 -> 检查 CPU 算子 -> 校验产物 -> hbm_perf -> 生成报告

**交互原则（Step 2 为默认强制门禁）**：
- **默认**：Step 1 生成或写出 `compile_config_*.yaml` 后，必须先执行 **Step 2**，向用户展示配置路径与关键字段摘要，并**结束本轮回复、等待用户下一条消息**。在用户给出明确肯定（如「直接编译」「确认」「可以」）之前，**禁止**运行 `compile_model.py -c` 或任何等价编译命令。
- **唯一例外**：用户在同一条用户消息中已写明可跳过确认（如「直接编译」「跳过确认」「按上述配置立刻编译」「生成配置后马上编」），才允许在同一轮助手流程中连续执行 Step 1→3。
- **仍须单独确认**（不得默认继续）：缺少模型路径；pyramid/resizer 的 mean/std 等关键项与用户描述不符或需用户拍板；检测到 CPU 算子后是否继续；编译失败后的重试或改配策略。
- **模型合法性校验失败**：**立即终止**本 skill 流程；**禁止**修改 `compile_model.py` 或用旁路脚本绕过检查（详见下文「模型合法性检查」）。

**默认配置**：
- 目标平台: `nash-e`
- 输出目录: 模型同级目录下的 `compile_<timestamp>` 文件夹（带时间戳避免覆盖）
- 删除 QDQ 节点: 通过 `remove_node_type: ["Quantize"]`（`remove_all_qdq` 已废弃）
- debug: `true`

### 模型合法性检查（加载阶段）

`compile_model.py` 在**首次加载模型**时（含 `--generate-config` 拉取 IO 与正式编译的 `load_model`）会执行以下检查，不通过则**立即终止**（异常或非零退出）并输出明确错误信息；**不得**在同一轮任务里继续执行后续编译步骤或假装已加载成功。

| 检查项 | 行为 |
|--------|------|
| 文件后缀 | 仅允许 `.onnx`、`.bc`；否则报错「不支持的模型类型」并停止。 |
| `.bc` 能否 `load` | 若 `hbdk4.compiler.load` 失败，提示**生成该 .bc 的 hbdk4 版本可能与当前环境不兼容**，并停止。 |
| `.bc` 阶段 | 在 load 成功后检查 inner `module` 的 **named attributes**：若存在 **`hbdk.target`**，则视为已 `convert` 的 **quantized.bc**，本流程需要 **qat.bc**；否则继续。判定规则与业务侧 `check_current_phase` 一致：无 `hbdk.target` 时按 **qat.bc** 处理。 |
| `.onnx` | `onnx.load` 成功后，图中需至少包含一个 **`op_type == "HzCalibration"`** 的节点（Horizon PTQ 标志）；否则报错并提示用户检查是否为 **horizon_plugin_pytorch 导出的 PTQ ONNX**。 |

**硬门禁（校验失败 = 停止本 skill 工作流）**  
任一检查失败时，你必须**立刻停止**：不得继续跑 `-c`、不得在未换模型的情况下反复「试编译」、不得替用户编造已通过校验的结论。应**原样引用**终端/日志中的错误信息，并明确告知用户需在**模型或环境侧**完成的动作（例如改回 **qat.bc**、换用带 **HzCalibration** 的 PTQ ONNX、对齐 **hbdk4** 与导出工具链版本）。

**对 Agent 的禁止事项（严禁绕过校验）**  
- **禁止**为通过检查而修改 `compile_model.py`（包括注释、删除或改写 `assert_supported_model_suffix`、`load_bc_model_validated`、`assert_bc_is_qat_phase`、`assert_onnx_has_hz_calibration` 及调用它们的代码路径）。  
- **禁止**编写或使用其它脚本 / 临时 Python，在**不做同等语义校验**的情况下加载模型，仅为生成 IO、写 yaml 或推进编译。  
- **禁止**向用户建议通过删断言、`sed` 去掉检查、环境变量关闭校验等方式绕过。  
- **唯一**合规做法：用户更换为**满足上表**的模型或环境后，再重新执行本仓库中的 `compile_model.py`（含 Docker 场景下同步到容器内的同一份脚本，亦不得删减校验）。

**说明**：`--generate-config` 与 `-c` 使用相同校验；若仅想改 yaml 而暂时无合法模型，可先生成空模板（不传 `-m`）或先解决模型路径/类型问题。

---

## 触发条件

### 显式触发

用户明确提出以下意图时触发：

- "编译 xxx 模型"
- "导出 hbm"
- "生成上板产物"
- "compile 模型"
- "在 docker 里编译 xxx 模型"
- "docker 中导出 hbm"

### 隐式触发

用户虽然没直接说 compile，但目标明显是拿到可部署产物时触发：

- "生成可部署模型"
- "拿到 hbm 文件"

如果是隐式触发，先用一句话说明"该目标通常需要执行 compile 才能得到 `.hbm`"，然后再开始流程。

---

## Docker 环境模式

当用户提到以下关键词时，启用 Docker 环境模式：

- "在 docker 里运行"
- "docker 中编译"
- "容器里运行"
- "docker 路径"

### Docker 模式工作流

```
Step 0: Docker 环境准备（仅 Docker 模式）
Step 1: 解析用户指令并生成配置文件
Step 2: 用户确认/修改配置文件
Step 3: 加载配置并执行编译流程
Step 4: 检查 CPU 算子
Step 5: 校验 HBM 产物
Step 6: 执行 hbm_perf
Step 7: 生成编译报告
```

### Step 0: Docker 环境准备

1. **确认 Docker 工作路径**：
   - 如果用户提供了 docker 路径，使用该路径
   - 如果用户提到 docker 但未提供路径，从模型路径推断或询问用户

2. **生成 compile_model.py 到 Docker 工作路径**：
   - 使用 Write 工具直接在 Docker 工作路径下生成脚本
   - 脚本路径: `<docker_work_path>/compile_model.py`
   - 内容来源: 读取 `~/.claude/skills/j6-hbdk-compile/compile_model.py` 并写入

3. **后续命令在 Docker 工作路径下执行**：
   ```bash
   # 生成配置文件
   python <docker_work_path>/compile_model.py --generate-config -m <model_path>
   
   # 执行编译
   python <docker_work_path>/compile_model.py -c <config_path>
   ```

### Docker 模式参数

| 参数 | 提取示例 | 必需性 |
|------|----------|--------|
| Docker 模式 | "在 docker 里运行" | 可选 |
| Docker 工作路径 | "docker 路径 /workspace" | Docker 模式时必需 |

| 用户表达 | 处理方式 |
|----------|----------|
| "docker 里运行" / "在 docker 中编译" | 启用 Docker 模式 |
| "docker 路径 xxx" / "工作路径 xxx" | Docker 工作路径 |

### Docker 模式示例

**用户**: "在 docker 里编译 /workspace/model.onnx，nash-m"

**响应**:
```
检测到 Docker 环境运行模式。

Step 0: 准备 Docker 环境
正在生成 compile_model.py 到 /workspace/ ...

Step 1: 生成配置文件...
python /workspace/compile_model.py --generate-config -m /workspace/model.onnx
...
```

---

## 工作流

严格按以下顺序执行。**Step 2 不得被跳过**（除非用户在同一条消息中已明确授权跳过，见上文「唯一例外」）；Agent 不得在仅完成 Step 1 后自动执行 Step 3。

```
Step 1: 解析用户指令并生成配置文件
Step 2: 用户确认/修改配置文件   ← 强制等待用户回复（默认）
Step 3: 加载配置并执行编译流程
Step 4: 检查 CPU 算子
Step 5: 校验 HBM 产物
Step 6: 执行 hbm_perf
Step 7: 生成编译报告
```

---

### Step 1：解析用户指令并生成配置文件

#### 1.1 参数提取

从用户输入中提取以下参数：

| 参数 | 提取示例 | 必需性 |
|------|----------|--------|
| 模型路径 | "编译 /path/to/model.onnx" | 必需 |
| 目标平台 | "目标平台 nash-p" | 可选，默认 nash-e |
| 输出目录 | "保存到 /data/output" | 可选，默认模型同级 compile_<timestamp> |
| 输入源配置 | "pyramid 输入，mean 128,128,128" | 可选 |
| 删除节点 | "删除输入节点 qdq_input" | 可选 |
| 编译参数 | "开启 debug，核数 2" | 可选 |
| 开发板 IP | "perf IP 192.168.1.100" | 可选 |
| Docker 模式 | "在 docker 里运行" | 可选 |
| Docker 工作路径 | "docker 路径 /workspace" | Docker 模式时必需 |
| PTQ 配置文件 | "ptq config /path/to/config.yaml" | 可选 |

#### 1.2 参数映射表

| 用户表达 | 配置字段 |
|----------|----------|
| "目标平台 xxx" / "march xxx" | `march` |
| "保存到 xxx" / "编译输出到 xxx" | `output_dir` |
| "开启 debug" | `debug: true` |
| "关闭 debug" | `debug: false` |
| "pyramid 输入 xxx" | 在 `input_sources` 中添加 pyramid 类型 |
| "resizer 输入 xxx" | 在 `input_sources` 中添加 resizer 类型 |
| "mean xxx" / "均值 xxx" | `input_sources[].mean` |
| "std xxx" / "标准差 xxx" | `input_sources[].std` |
| "训练数据格式 xxx" / "data_type xxx" | `input_sources[].data_type` (rgb, bgr, yuv444) |
| "删除所有 QDQ" | `remove_all_qdq: true` |
| "删除输入节点 xxx" | `remove_input_nodes` 添加 xxx |
| "删除输出节点 xxx" | `remove_output_nodes` 添加 xxx |
| "编译核数 x" / "core_num=x" | `core_num` |
| "优化等级 x" / "opt_level=x" | `opt_level` |
| "jobs x" / "并行编译 x" | `jobs` |
| "cache 路径 xxx" | `cache_path` |
| "设置 max_l2m_size 为 xxx" | `max_l2m_size` |
| "设置 max_time_per_fc 为 xxx" | `max_time_per_fc` |
| "开发板 IP xxx" / "perf IP xxx" | `perf_ip` |
| "ptq config xxx" / "使用 ptq 配置 xxx" | 自动解析 PTQ yaml 填充配置 |

#### 1.3 生成配置文件

调用编译脚本生成配置文件：

```bash
# 推荐：指定模型路径，自动创建编译产物目录并生成配置文件
python ~/.claude/skills/j6-hbdk-compile/compile_model.py --generate-config -m <model_path>
```

**行为说明**：
1. 自动创建编译产物目录：`<模型同级目录>/compile_<timestamp>/`
2. 配置文件生成到该目录下：`compile_config_<模型名>.yaml`
3. 配置文件中 `output_dir` 字段已填充编译产物目录路径

然后根据用户提供的参数修改配置文件内容。

#### 1.4 PTQ Config 导入（新功能）

当用户传入 PTQ 配置文件时，自动提取输入预处理参数：

```bash
# 从 PTQ config 导入配置
python ~/.claude/skills/j6-hbdk-compile/compile_model.py --generate-config -m <model_path> --ptq-config <ptq_config.yaml>
```

**PTQ 字段映射表**：

| PTQ 字段 | 编译配置字段 | 说明 |
|----------|-------------|------|
| `model_parameters.march` | `march` | 目标平台 |
| `input_parameters.input_name` | `input_sources[].name` | 输入节点名称 |
| `input_parameters.input_type_rt` | `input_sources[].source_type` | nv12/gray → pyramid |
| `input_parameters.input_type_train` | `input_sources[].data_type` | rgb/bgr/yuv444 |
| `input_parameters.input_source` | `input_sources[].source_type` | 显式指定优先 |
| `input_parameters.mean_value` | `input_sources[].mean` | 均值 |
| `input_parameters.scale_value` | `input_sources[].std` | std = 1/scale |
| `input_parameters.std_value` | `input_sources[].std` | 直接使用 |
| `compiler_parameters.optimize_level` | `opt_level` | O2 → 2 |
| `compiler_parameters.core_num` | `core_num` | 编译核数 |
| `compiler_parameters.jobs` | `jobs` | 并行编译数 |
| `compiler_parameters.cache_path` | `cache_path` | Cache 路径 |
| `compiler_parameters.cache_mode` | `cache_mode` | Cache 模式 |
| `compiler_parameters.max_l2m_size` | `max_l2m_size` | 最大 L2M 大小 |
| `compiler_parameters.max_time_per_fc` | `max_time_per_fc` | 每个 function 最大编译时间 |
| `compiler_parameters.input_source` | `input_sources[].source_type` | 显式指定输入源 |

**norm_type 处理**：

- PTQ yaml 中的 `norm_type` 字段被**完全忽略**
- norm 类型通过 `mean_value`、`scale_value`、`std_value` 组合推断：
  - `mean` + `scale` → data_mean_and_scale
  - `mean` + `std` → data_mean_and_std
  - `scale` → data_scale
  - `std` → data_std
  - `mean` → data_mean
  - 无参数 → no_preprocess
- `scale_value` 和 `std_value` **互斥**，不能同时指定
- **不设置默认值**：只有 PTQ config 中提供的参数才会被使用

**预处理公式转换**：

PTQ 预处理公式：`norm_data = (data - mean_value) * scale_value`

API 预处理公式：`norm_data = (data - mean) / std`

转换规则：`std = 1 / scale_value`

**示例**：

**用户**: "编译 model.onnx，使用 ptq 配置 mobilenet_config.yaml"

**响应**:
```
检测到 PTQ 配置文件，正在解析: mobilenet_config.yaml

从 PTQ config 提取:
  - march: nash-e
  - opt_level: 2
  - core_num: 1
  - jobs: 32
  - input_sources:
      - name: input
        source_type: pyramid
        data_type: bgr
        mean: [103.94, 116.78, 123.68]
        std: [58.82, 58.82, 58.82]

Step 1: 生成配置文件...
配置文件已生成: /path/to/compile_config_model.yaml
```

---

### Step 2：用户确认/修改配置文件（Agent 强制遵守）

1. **门禁**：完成 Step 1 后，除非当前用户消息已含「跳过确认 / 直接编译」类明确授权，否则**禁止**在同一轮对话中接着调用编译；必须先请用户确认。
2. **展示**：给出 `config_path`，并摘要 `model_path`、`march`、`output_dir`、`input_sources`、`remove_node_type`、`preserve_input_nodes`、`preserve_output_nodes` 等会改变产物行为的字段（全文过长时可附「完整内容见该 yaml」）。
3. **结束本轮**：用清晰问句收尾，**等待用户下一条消息**，例如：
   > 配置文件已就绪：`/path/to/compile_config_xxx.yaml`。请确认是否**按此配置直接编译**；若要改配置请说明字段，或回复「取消」终止。
4. **用户回复后的分支**：
   - **肯定**（如「直接编译」「确认」「可以」「编吧」）→ 进入 Step 3
   - **要改** → 用户改 yaml 或口述修改；Agent 更新后再回到本步展示与确认
   - **取消** → 不执行编译

---

### Step 3：加载配置并执行编译流程

仅在 Step 2 取得用户明确肯定（或同条消息已授权跳过）后执行。调用编译脚本：

```bash
python ~/.claude/skills/j6-hbdk-compile/compile_model.py -c <config_path>
```

编译流程步骤：

1. **加载模型**（含合法性检查，见上文「模型合法性检查」）
   - ONNX: `onnx.load` → 校验 `HzCalibration` → `hbdk4.compiler.onnx.export()`
   - BC: `hbdk4.compiler.load`（失败则提示 hbdk 版本兼容性）→ 校验非 quantized.bc（无 `hbdk.target` 等）→ 进入后续流程

2. **打印原始模型 IO 信息**（干净输出，方便复制）

3. **配置输入源**
   - 调用 `insert_image_preprocess()` 等方法配置 pyramid/resizer 输入

4. **转换模型**
   - `hbdk4.compiler.convert(model, march=march)`

5. **删除节点**（`remove_node_type` / `preserve_*` / `remove_*_nodes`，见配置说明）
   - `remove_node_type` 含 `Quantize` 且配置了 `preserve_input_nodes` 时：仅对「非保留、且非 pyramid/resizer 图像源」的入边尝试删相邻 Quantize。
   - **pyramid/resizer**：除配置里的根输入名外，convert 后可能出现的派生入边（如 `{根名}_y`、`{根名}_uv`）一律视为同一图像源，**不会**列入删除名单，避免 HBDK 报入边 Quantize *unremovable* 导致编译失败。
   - `Dequantize` / `Cast` 等按配置与 `hbdk` API 流程处理。

6. **打印删节点后模型 IO 信息**（带 quant_info）

7. **编译模型**
   - `hbdk4.compiler.compile(model, path=hbm_path, march=march, **params)`

8. **打印 HBM IO 信息**（带 quant_info 和 strides）

---

### IO 信息打印格式

编译过程会在以下阶段打印模型/产物的输入输出信息：

**1. 原始模型加载后**（干净输出，无 [INFO] 前缀）：
```
--- 原始模型输入 ---
  [0] input_name: shape=[1, 3, 224, 224], dtype=float32
--- 原始模型输出 ---
  [0] output_name: shape=[1, 1000], dtype=float32
```

**2. 删节点后**（带 quant_info）：
```
--- 删节点后模型输入 ---
  [0] input_name: shape=[1, 3, 224, 224], dtype=int8, quant_info=...
--- 删节点后模型输出 ---
  [0] output_name: shape=[1, 1000], dtype=int8, quant_info=...
```

**3. HBM 编译完成后**（带 quant_info 和 strides）：
```
--- HBM 输入 ---
  [0] input_name: shape=[1, 3, 224, 224], dtype=int8, quant_info=..., strides=[...]
--- HBM 输出 ---
  [0] output_name: shape=[1, 1000], dtype=int8, quant_info=..., strides=[...]
```

---

### Step 4：检查 CPU 算子

**检查方法**：
- 调用 `statistics(quantized_model)` 获取算子统计
- 检查是否存在 `hbtl` 前缀的算子

**判定标准**：
- `hbtl*` 前缀 -> CPU 算子（警告）
- `b30*`, `b30_vpu*`, `func*`, `hbdk*` 前缀 -> 正常算子

**处理规则**：
- 未发现 CPU 算子 -> 继续流程
- 发现 CPU 算子 -> 列出具体算子名称，**询问用户是否继续**

不要只说"有 CPU 算子"，必须把具体名称列出来。

---

### Step 5：校验 HBM 产物

检查以下文件是否生成：
- `<model_name>.hbm` - 最终编译产物

如果文件不存在或大小为 0，报告错误并排查日志。

---

### 中间产物

编译过程中会生成以下中间产物（保存在输出目录）：

| 产物名称 | 说明 |
|----------|------|
| `compile_config_<model_name>.yaml` | 配置文件 |
| `<model_name>_<timestamp>.log` | 编译过程日志文件 |
| `<model_name>_converted.bc` | Convert 后的量化模型 |
| `<model_name>_converted.onnx` | Convert 后的可视化 ONNX（不含权重） |
| `<model_name>_removed.bc` | Remove_nodes 后的模型（删除 QDQ 节点后） |
| `<model_name>_removed.onnx` | Remove_nodes 后的可视化 ONNX（不含权重） |
| `<model_name>.hbm` | 最终编译产物 |
| `compile_report_<model_name>_<timestamp>.md` | 编译报告 |

---

### Step 6：执行 hbm_perf

根据 `perf_ip` 配置：

- **有 perf_ip**: 调用 `hbm_perf(hbm_path, remote_ip=perf_ip)`
- **无 perf_ip**: 调用 `hbm_perf(hbm_path)`（不设置 remote_ip 参数）

生成 perf 报告 HTML 文件。

---

### Step 7：生成编译报告

在输出目录下生成报告文件：`compile_report_<model_name>_<timestamp>.md`

**报告内容**：
- 基本信息：模型路径、输出目录、目标平台、HBDK 版本
- 配置摘要：所有编译参数
- 执行步骤：每步的执行状态
- CPU 算子检查结果
- 产物列表
- Perf 报告路径（如有）
- 错误信息（如有）

---

## 配置文件字段说明

### 基本配置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `model_path` | string | "" | 模型路径 (.onnx 或 .bc)，必填 |
| `output_dir` | string | "" | 输出目录，默认模型同级 `compile_<timestamp>` |
| `march` | string | "nash-e" | 目标平台 |

### 输入源配置 (input_sources)

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | string | - | 输入节点名称 |
| `source_type` | string | - | 类型: ddr, pyramid, resizer |
| `mean` | list | [128.0, 128.0, 128.0] | 均值 |
| `std` | list | [128.0, 128.0, 128.0] | 标准差 |
| `divisor` | float | 1.0 | 归一化除数 |
| `data_type` | string | "rgb" | 训练数据格式: rgb, bgr, yuv444 |

**data_type 说明**：
- `data_type` 是模型训练时的数据格式，用于决定 `insert_image_preprocess` 的 mode 参数
- rgb -> mode="yuvbt601full2rgb"
- bgr -> mode="yuvbt601full2bgr"
- yuv444 -> mode=None
- 如果不是 rgb/bgr/yuv444 之一，会报错

### 节点删除配置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `remove_all_qdq` | bool | true | 删除所有 QDQ/Cast 节点（与 remove_input_nodes/remove_output_nodes 互斥）|
| `remove_input_nodes` | list | [] | 需删除的输入节点名称 |
| `remove_output_nodes` | list | [] | 需删除的输出节点名称 |

### 编译参数

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `debug` | bool | true | 开启 debug 模式 |
| `input_no_padding` | bool | true | 输入不填充 |
| `output_no_padding` | bool | true | 输出不填充 |
| `enable_hpc` | bool | true | 开启 HPC (需要 HBDK >= 4.9.2) |
| `enable_vpu` | bool | true | 开启 VPU |
| `core_num` | int | 1 | 编译核数 |
| `opt_level` | int | 2 | 优化等级 |
| `jobs` | int | 32 | 并行编译数 |
| `max_l2m_size` | int | 0 | 最大 L2M 大小，0 表示不限制 |
| `max_time_per_fc` | int | 0 | 每个 function 最大编译时间(秒) |
| `cache_path` | string | "" | Cache 路径 |
| `cache_mode` | string | "enable" | Cache 模式 |

### 性能测试配置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `perf_ip` | string | "" | 开发板 IP，为空则 hbm_perf 不设置 remote_ip |
| `perf_username` | string | "root" | 开发板用户名 |

---

## 版本判断

| HBDK 版本 | 特性支持 |
|-----------|----------|
| >= 4.9.2 | 支持 `enable_hpc` 参数 |
| >= 4.1.3 | `func.remove_io_op()` API |
| < 4.1.3 | 旧版本 QDQ 删除方法 |

---

## 常见错误处理

| 问题 | 处理方式 |
|------|----------|
| 模型文件不存在 | 报错并提示用户检查路径 |
| 不支持的模型格式 / 后缀 | 仅支持 `.onnx`、`.bc`，否则立即终止 |
| `.bc` 无法 load | 提示可能与当前 hbdk4 版本不兼容，建议对齐导出工具链 |
| `.bc` 为 quantized（含 `hbdk.target`） | 要求改用 **qat.bc**，本脚本从 QAT 产物开始 |
| ONNX 无 `HzCalibration` | 要求确认是否为 horizon PTQ 导出 ONNX |
| 配置文件为空或格式错误 | 报错并提示用户检查配置 |
| 检测到 CPU 算子 | 列出具体算子名，询问用户是否继续 |
| 编译过程报错 | 分析错误，尝试自动修复或提示用户 |

---

## 结果交付

完成后向用户简要汇报：
- 编译是否成功
- HBM 文件路径
- 编译耗时
- 是否存在 CPU 算子警告
- Perf 报告路径（如有）
- 编译报告路径

---

## 脚本路径

编译脚本位于：`~/.claude/skills/j6-hbdk-compile/compile_model.py`

```bash
# 生成配置文件模板（推荐指定模型路径）
python ~/.claude/skills/j6-hbdk-compile/compile_model.py --generate-config -m /path/to/model.bc

# 从 PTQ config 导入配置
python ~/.claude/skills/j6-hbdk-compile/compile_model.py --generate-config -m /path/to/model.bc --ptq-config /path/to/ptq_config.yaml

# 指定输出路径
python ~/.claude/skills/j6-hbdk-compile/compile_model.py --generate-config -m /path/to/model.bc -o my_config.yaml

# 使用配置文件编译
python ~/.claude/skills/j6-hbdk-compile/compile_model.py -c config.yaml
```
