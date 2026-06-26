# j6-hbdk-compile Skill 说明文档

> 版本: 1.1.7 | 更新日期: 2026-04-23

---

## 1. 核心功能

j6-hbdk-compile 是一个面向 Horizon J6 平台的**通用模型编译 Skill**，将 PTQ 量化后的模型（`.onnx` 或 `.bc`）编译为可部署的 `.hbm` 产物。

核心能力：

- **YAML 配置驱动**：通过 `compile_config_*.yaml` 声明式管理全部编译参数，配置即文档、可复现
- **双格式输入**：支持 ONNX（Horizon PTQ 导出）和 BC（QAT 阶段 qat.bc）两种模型格式
- **PTQ Config 自动导入**：从 PTQ 校准配置 YAML 自动提取输入预处理参数（mean/std/scale → 输入源配置）、编译参数等，避免手动转录出错
- **输入源配置**：支持 DDR / Pyramid / Resizer 三种输入源，含 NV12 图像预处理（mean/std/divisor/data_type）
- **节点删除策略**：灵活的 QDQ 节点删除——按类型删除、按名称删除、白名单保留，自动处理 Pyramid/Resizer 派生入边
- **模型合法性门禁**：加载阶段强制校验模型后缀、阶段（qat.bc vs quantized.bc）、PTQ 标志算子（HzCalibration），不合格立即终止
- **Docker 模式**：支持将编译脚本部署到 Docker 容器内执行，适配隔离环境
- **全流程自动化**：编译 → CPU 算子检查 → HBM 校验 → hbm_perf 性能测试 → 报告生成，一步到位

---

## 2. 详细设计

### 2.1 整体架构

```
┌──────────────────────────────────────────────────────────────┐
│                     SKILL.md (工作流调度层)                      │
│  解析用户意图 → 生成/修改配置 → 等待确认 → 调用脚本 → 交付结果    │
└────────────────────────┬─────────────────────────────────────┘
                         │ 调用
                         ▼
┌──────────────────────────────────────────────────────────────┐
│              compile_model.py (编译执行层)                      │
│  CLI 入口 → 加载配置 → 加载模型 → 配置输入源 → 转换 →          │
│  删节点 → 编译 → 检查CPU算子 → hbm_perf → 生成报告             │
└──────────────────────────────────────────────────────────────┘
                         │ 依赖
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                   hbdk4 (HBDK 编译器 SDK)                      │
│  load / convert / compile / statistics / hbm_perf / save /   │
│  visualize / Hbm / March                                     │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 工作流（7 步）

| Step | 名称 | 说明 | 交互要求 |
|------|------|------|----------|
| 1 | 解析指令 & 生成配置 | 提取参数 → `--generate-config` 生成 YAML → 根据用户输入修改字段 | 无 |
| 2 | 用户确认配置 | 展示配置路径与关键字段摘要，**强制等待用户确认** | **必须等待** |
| 3 | 执行编译 | `compile_model.py -c <config>` 跑完整编译流程 | 需确认后 |
| 4 | 检查 CPU 算子 | 调用 `statistics()` 检测 `hbtl*` 前缀算子 | 发现时询问 |
| 5 | 校验 HBM 产物 | 检查 `.hbm` 文件存在且非空 | 自动 |
| 6 | 执行 hbm_perf | 有 perf_ip 则远程、否则本地 | 自动 |
| 7 | 生成报告 | `compile_report_<model>_<ts>.md` | 自动 |

**Step 2 门禁规则**：
- **默认**：生成配置后必须展示并等待用户下一条消息确认，禁止自动进入 Step 3
- **唯一例外**：用户在同一条消息中已写明「直接编译」「跳过确认」等授权语
- **仍需单独确认**：缺少模型路径、mean/std 等关键项与用户描述不符、检测到 CPU 算子后是否继续

### 2.3 模型合法性检查（硬门禁）

在模型加载阶段（`--generate-config` 拉取 IO 和正式 `-c` 编译均会执行），以下任一检查失败即**立即终止**：

| 检查项 | 条件 | 失败行为 |
|--------|------|----------|
| 文件后缀 | 仅 `.onnx` / `.bc` | `ValueError` 终止 |
| BC 加载 | `hbdk4.compiler.load` 成功 | 失败提示 hbdk4 版本不兼容 |
| BC 阶段 | 模块属性无 `hbdk.target`（= qat.bc） | 存在则说明是 quantized.bc，`RuntimeError` 终止 |
| ONNX PTQ | 图中存在 `op_type == "HzCalibration"` | 不存在则 `RuntimeError` 终止 |

**Agent 禁止事项**：
- 禁止修改 `compile_model.py` 中的校验逻辑以通过检查
- 禁止编写旁路脚本绕过同等语义校验
- 禁止建议用户通过删断言/sed/环境变量等方式绕过

### 2.4 配置文件设计

配置文件为 YAML 格式，分为 5 个区域：

```
基本配置          model_path, output_dir, march, output_model_file_prefix
输入源配置        input_sources[] (name, source_type, mean, std, divisor, data_type)
节点删除配置      remove_node_type, remove_input/output_nodes, preserve_input/output_nodes
编译参数          debug, opt_level, core_num, jobs, cache_path, max_l2m_size, ...
性能测试配置      perf_ip, perf_username
```

#### 输入源配置 (input_sources)

每个输入源独立配置，支持多输入：

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `name` | 输入节点名称（与模型对应） | - |
| `source_type` | ddr / pyramid / resizer | - |
| `mean` | 均值（pyramid/resizer 适用） | None |
| `std` | 标准差（pyramid/resizer 适用） | None |
| `divisor` | 归一化除数 | 1.0 |
| `data_type` | 训练数据格式：rgb / bgr / yuv444 / featuremap | "rgb" |

**data_type → 预处理 mode 映射**：

| data_type | insert_image_preprocess mode | 说明 |
|-----------|-----|------|
| rgb | "yuvbt601full2rgb" | NV12→RGB |
| bgr | "yuvbt601full2bgr" | NV12→BGR |
| yuv444 | None | 不做色彩转换 |
| featuremap | 跳过预处理 | 直接 DDR |

**Pyramid/Resizer 输入处理链**：
```
input_node → insert_transpose([0,3,1,2]) → insert_image_preprocess(mean/std/divisor/mode) → insert_image_convert("nv12") / insert_roi_resize("nv12")
```

Batch > 1 时先 `insert_split(0)` 再逐个配置。

#### 节点删除配置

支持的**正确组合**：

| 场景 | remove_node_type | remove_input_nodes | remove_output_nodes | preserve_input_nodes | preserve_output_nodes |
|------|-----------------|-------------------|--------------------|--------------------|---------------------|
| 删除所有 Quantize | `["Quantize"]` | - | - | - | - |
| 删 Quantize + 保留白名单 | `["Quantize"]` | - | - | `["node_to_keep"]` | - |
| 按名称删输入 QDQ | - | `["specific_input"]` | - | - | - |
| 按名称删输出 QDQ | - | - | `["specific_output"]` | - | - |

**禁止组合**（立即报错）：
- `remove_node_type` 含 `Quantize` 时同时提供 `remove_input_nodes`
- `remove_node_type` 含 `Dequantize` 时同时提供 `remove_output_nodes`
- `remove_node_type` 含 `Cast` 时同时提供 `remove_*_nodes`

**Pyramid/Resizer 派生入边保护**：
- 配置为 pyramid/resizer 的根输入名及其派生入边（如 `{root}_y`、`{root}_uv`）自动排除在删除名单之外
- 避免删掉 NV12 拆分后的 Y/UV 通道的 Quantize 导致 HBDK 报 `unremovable` 错误

### 2.5 PTQ Config 导入

从 PTQ 校准配置 YAML 自动映射到编译配置，核心映射关系：

| PTQ 字段 | 编译配置字段 | 转换规则 |
|----------|-------------|---------|
| `model_parameters.march` | `march` | 直接映射 |
| `model_parameters.working_dir` | `output_dir` | 直接映射 |
| `input_parameters.input_name` | `input_sources[].name` | 分号分割多输入 |
| `input_parameters.input_type_rt` | `input_sources[].source_type` | nv12/gray→pyramid, 其余→ddr |
| `input_parameters.input_type_train` | `input_sources[].data_type` | 直接映射 |
| `input_parameters.mean_value` | `input_sources[].mean` | 分号+空格/JSON解析 |
| `input_parameters.scale_value` | `input_sources[].std` | `std = 1/scale` |
| `input_parameters.std_value` | `input_sources[].std` | 直接映射 |
| `compiler_parameters.optimize_level` | `opt_level` | "O2" → 2 |
| `compiler_parameters.core_num` | `core_num` | 直接映射 |
| `compiler_parameters.jobs` | `jobs` | 直接映射 |

**norm_type 推断**（忽略 PTQ 的 `norm_type` 字段，通过参数组合推断）：

| 参数组合 | 推断的 norm_type |
|----------|----------------|
| mean + scale | data_mean_and_scale |
| mean + std | data_mean_and_std |
| scale only | data_scale |
| std only | data_std |
| mean only | data_mean |
| 无 | no_preprocess |

**scale 与 std 互斥**：PTQ config 中 `scale_value` 和 `std_value` 不能同时指定。

**多输入支持**：PTQ 配置中的分号分割字段（如 `input_name: "cam1;cam2"`、`mean_value: "128;None;123 125 136"`）按索引分别解析到各 `InputSourceConfig`。

### 2.6 编译参数版本适配

| HBDK 版本 | 特性 |
|-----------|------|
| >= 4.9.2 | 支持 `enable_hpc` 参数 |
| >= 4.1.3 | `func.remove_io_op()` API（优先使用） |
| < 4.1.3 | 旧版 QDQ 删除方法（`arg.remove_attached_op()` + schema 判断） |

版本判断使用 `packaging.version.Version`（优先）或简单分段比较（降级）。

### 2.7 Docker 模式

当用户提到「docker 里运行」「容器里编译」等关键词时启用：

1. 确认 Docker 工作路径
2. 将 `compile_model.py` 写入 Docker 工作路径
3. 后续命令在 Docker 路径下执行

### 2.8 中间产物

编译过程中自动保存的中间文件（均在 `output_dir` 下）：

| 产物 | 说明 |
|------|------|
| `compile_config_<model>.yaml` | 配置文件（自动复制到输出目录） |
| `<model>_<ts>.log` | 编译过程日志（实时 flush） |
| `<model>_converted.bc` | Convert 后的量化模型 |
| `<model>_qat.onnx` | QAT BC 的可视化 ONNX（仅 BC 输入） |
| `<model>_removed_quantized.bc` | 删节点后的模型 |
| `<model>_removed_quantized.onnx` | 删节点后的可视化 ONNX |
| `<model>.hbm` | 最终编译产物 |
| `compile_report_<model>_<ts>.md` | 编译报告 |

### 2.9 IO 信息打印

编译流程在三个阶段打印模型 IO 信息，方便用户核对：

1. **原始模型加载后**：`shape`, `dtype`（干净输出，无 `[INFO]` 前缀）
2. **删节点后**：增加 `quant_info` 字段
3. **HBM 编译完成后**：增加 `quant_info.scales` 和 `strides`

---

## 3. 异常兜底方案

### 3.1 模型合法性校验失败

| 异常场景 | 错误类型 | 处理方式 | 用户需执行的动作 |
|----------|---------|---------|---------------|
| 文件后缀非 `.onnx`/`.bc` | `ValueError` | 立即终止，输出不支持的后缀 | 换用合法格式的模型 |
| `.bc` 加载失败 | `RuntimeError` | 立即终止，提示 hbdk4 版本不兼容 | 对齐导出模型时的 hbdk4 版本 |
| `.bc` 为 quantized（含 `hbdk.target`） | `RuntimeError` | 立即终止，要求 qat.bc | 改用 QAT 阶段导出的 qat.bc |
| ONNX 无 `HzCalibration` | `RuntimeError` | 立即终止，提示非 PTQ ONNX | 确认是否为 horizon_plugin_pytorch 导出的 PTQ ONNX |

**兜底原则**：校验失败 = **停止整个 Skill 工作流**，不得继续编译、不得反复试编译、不得虚构已通过校验的结论。

### 3.2 编译过程异常

| 异常场景 | 处理方式 |
|----------|---------|
| 配置文件为空或格式错误 | `load_config_from_yaml` 抛出 `ValueError`，提示检查配置 |
| 模型文件不存在 | CLI 校验阶段 `sys.exit(1)` |
| hbdk4 未安装 | CLI 校验阶段提示，不进入编译 |
| `func.remove_io_op` 失败 | 降级到旧版 `_remove_qdq_legacy` 方法 |
| 节点不可删除（`is_removable[0] == False`） | `logger.warning` 并跳过该节点，不崩溃 |
| 可视化 ONNX 保存失败 | `logger.warning`，不影响编译继续 |
| 编译主流程异常 | `compile_full` 捕获异常 → 记录 `result["error"]` → 生成报告（含错误信息） → `sys.exit(1)` |

### 3.3 CPU 算子检测

| 场景 | 处理方式 |
|------|---------|
| 无 CPU 算子 | 正常继续 |
| 存在 `hbtl*` 前缀算子 | **列出具体算子名称**，询问用户是否继续（不得只说"有 CPU 算子"） |
| `b30*`/`func*`/`hbdk*` 前缀 | 正常 BPU 算子，不警告 |

### 3.4 HBM 产物校验

- 检查 `.hbm` 文件是否存在且大小非零
- 不存在或为空 → 报错并排查日志

### 3.5 hbm_perf 失败

- 异常被捕获 → `logger.error` 记录 → 返回 `None`
- 不影响编译成功状态，perf 报告字段为空

### 3.6 PTQ Config 解析失败

- `parse_ptq_config` 异常被捕获 → 输出警告 → 降级使用默认配置
- 不会因 PTQ 配置解析失败而终止流程

### 3.7 版本兼容性降级

| 场景 | 降级策略 |
|------|---------|
| `packaging` 未安装 | 版本比较降级为分段整数比较 |
| HBDK 版本未知 | `supports_enable_hpc()` 默认返回 True；`supports_remove_io_op()` 默认返回 True |
| HBDK < 4.1.3 | 使用旧版 `_remove_qdq_legacy` 删除 QDQ |
| HBDK < 4.9.2 | 不传 `enable_hpc` 参数 |

### 3.8 Pyramid/Resizer 非标准输入

| 场景 | 处理方式 |
|------|---------|
| 输入非 4 维 | `logger.warning` 并跳过，不进入 Pyramid/Resizer 配置 |
| Batch > 1 | 自动 `insert_split(0)` 拆分后逐个配置 |
| 派生入边（`{root}_y`/`{root}_uv`） | 自动排除在删除名单外 |

### 3.9 日志可靠性

- 使用 `_ImmediateFlushFileHandler`：每次 `emit` 后立即 `flush`
- 避免长时间编译时默认块缓冲导致日志文件无法实时查看

---

## 4. 关键设计决策

| 决策 | 原因 |
|------|------|
| 配置文件门禁（Step 2 强制确认） | 编译耗时可能数十分钟，配置错误代价高；防止 Agent 自动跑编译产生无用产物 |
| 模型合法性硬门禁 | qat.bc vs quantized.bc、PTQ vs 非 PTQ ONNX 的混淆会导致编译结果不可预测，必须在源头拦截 |
| 禁止修改 `compile_model.py` 绕过校验 | 校验逻辑是 Skill 与用户的契约，Agent 不应为"完成编译任务"而破坏安全边界 |
| scale → std 转换（`std = 1/scale`） | PTQ 预处理公式 `(data - mean) * scale` 与 API 公式 `(data - mean) / std` 的数学等价转换 |
| 忽略 PTQ 的 `norm_type` 字段 | 参考 horizon_tc_ui 实现，`norm_type` 可能不准确，通过 mean/scale/std 组合推断更可靠 |
| Pyramid/Resizer 派生入边自动排除 | HBDK convert 后 NV12 输入会拆分为 `_y`/`_uv` 边，误删其 Quantize 会导致 `unremovable` 编译失败 |
| 时间戳输出目录 | 避免多次编译覆盖产物，保留历史版本 |

---

## 5. 文件清单

| 文件 | 职责 |
|------|------|
| `SKILL.md` | Skill 工作流定义、触发条件、交互规则、参数映射 |
| `compile_model.py` | 编译执行脚本（CLI + ModelCompiler 类 + 配置工具 + PTQ 解析 + 报告生成） |
| `config_template.yaml` | 配置文件模板（供参考，实际配置由 `--generate-config` 动态生成） |
| `__init__.py` | Python 包导出（ModelCompiler, CompileConfig 等核心类） |
| `CHANGELOG.md` | 版本变更记录 |
