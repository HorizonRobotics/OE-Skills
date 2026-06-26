# Changelog

本文件记录 **j6-hbdk-compile**（J6 HBDK 通用模型编译 Skill）的版本历史。

- **OE Skill Hub** 上各版本的「发布说明」字段可通过 `oe-cli skill inspect j6-hbdk-compile --version <semver>` 查看；若与 Hub 上 `changelog` 摘要与本表不一致，以本文件对实现层面的**展开说明**为准。
- 日期为 OE Hub 返回的 `createdAt`（UTC）换算，仅供参考。

---

## [1.1.8] — 2026-06-11（OE Hub `latest`）

### 主要更新（相对 **1.1.7**）

- **节点删除策略重构（`remove_nodes`）**：
  - 将 **Quantize / Dequantize / Cast** 归为同一处理类别；**Reshape / Transpose** 单独作为布局类，在流程末尾按类型删除，不再与 QDQ/Cast 混处理。
- **convert 后算子类型匹配（按名删除路径）**：
  - 修复 convert 后 attached op 类型与配置字符串（如 `"Cast"`）不一致时误报 **`[未找到] 未找到节点`**、导致该删未删的问题。
- **`_remove_op_connected_to_io`**：新增 `_normalize_op_types()`，支持传入类型列表；类型过滤改为调用 `matches_remove_op_type()`。

---

## [1.1.7] — 2026-04-21

### 主要更新（相对 **1.1.6**）

- **SKILL.md**：
  - 在「模型合法性检查」中明确：**任一校验失败须立即终止**本 skill 工作流（异常或非零退出），不得在无合法模型时继续 `-c` 或虚构已通过校验；
  - 新增 **硬门禁** 与 **对 Agent 的禁止事项**：不得为通过检查而修改 `compile_model.py` 中的校验逻辑、不得使用不做同等语义校验的旁路脚本推进编译、不得建议通过删断言 / `sed` 等方式绕过校验。

---

## [1.1.6] — 2026-04-21

### 主要更新（相对 **1.1.4**）

- **模型路径后缀**：在拉取 IO（`--generate-config`）与正式 `load_model` 前校验，仅允许 **`.onnx` / `.bc`**，否则立即报错终止。
- **qat.bc 合法性**：
  - 使用 **`hbdk4.compiler.load`** 加载 `.bc`，失败时抛出明确错误并附带 **hbdk4 版本不兼容** 的排查提示；
  - 加载成功后检查是否为 **QAT 阶段 qat.bc**，不满足则 **`RuntimeError` 终止**。
- **PTQ ONNX 合法性**：对 `.onnx` 在 **`onnx.load` 之后**遍历图节点，必须至少包含一个 **`op_type == HzCalibration`** 的节点（Horizon PTQ 标志）；否则 **`RuntimeError` 终止**并提示确认是否为 **horizon_plugin_pytorch** 导出的 PTQ ONNX。  

---

## [1.1.4] — 2026-04-17

### 新增

- 本 `CHANGELOG.md`，集中记录版本与变更。

---

## [1.1.3] — 2026-04-17

### 主要更新与修复（实现层面，相对 **1.1.2**）

- **qat_bc 可视化 ONNX**：`visualize` 改为作用于 **`self.model`**（原误用 `self.quantized_model` 的场景）；产物命名与日志文案对齐为 qat_bc 可视化说明。
- **`_print_hbm_io`**：改为接收 **`hbm_func`**（由 `Hbm(hbm_path)[0]` 传入）；遍历 `flatten_inputs` / `flatten_outputs`；`dtype` 使用 `np_dtype`；量化信息通过 `type.quant_info is not None` 判断并输出 `scales`，避免误判。
- **按名删除 I/O 附着节点**：若目标 I/O 不可删除，由抛错改为 **`logger.warning` 并中止该次删除**（`return False`），避免流程直接崩溃。
- **Pyramid / Resizer**：仅在输入为 **4 维** 时执行 batch split 或直接配置；非 4 维形状给出 **warning** 并跳过，避免错误走入「batch==1」分支。
- **`hbm_perf`**：显式传入 **`output_dir`**，避免报告写到进程当前工作目录；`execute_hbm_perf` 增加与 HBM function 名相关的参数，便于与产出 HTML 命名对齐；主流程中在打印 I/O 前构造 `Hbm` 并传入 `hbm[0]`。

---

## [1.1.1] — 2026-04-15

### 主要更新与修复

- **SKILL**：强化「生成配置后须用户确认」等交互原则与 PTQ 相关说明。
- **compile_model / 文档**：pyramid、resizer 相关入边排除逻辑及文档补充，避免误删与配置不一致。

---

## [1.0.0] — 2026-04-14

### 发布说明（Hub）

- Initial release（首次发布）。

### 能力基线（概括）

- 基于 **YAML** 的编译配置驱动；支持 **ONNX** 与 **BC** 模型路径。
- 提供 **`compile_model.py`**：生成配置模板、加载配置执行 `hbdk4` 编译流程、CPU 算子检查、HBM 校验、**hbm_perf**（可选）、编译报告输出。
- 支持 **Docker** 模式与常见编译选项（平台、march、QDQ 处理策略等，详见 `SKILL.md` 与 `config_template.yaml`）。
- 支持从 **PTQ yaml** 自动提取输入预处理相关字段。自动映射 `input_type_rt`、`mean_value`、`scale_value` 等至编译配置。

---

