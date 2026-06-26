# HMCT 工作流补充规范

> 本文档从 horizon-router SKILL.md 拆出，按需加载。当用户需求涉及 HMCT 量化构建、精度调优、敏感度分析等场景时阅读本文件。
>
> **⛔ 优先级声明**：本文档是 HMCT 数据准备和分析任务的**最高权威**。当子 Skill（hmct-workflow、j6-hmct-cosine-similarity-tuning 等）的默认行为与本文档冲突时，以本文档为准。子 Skill 描述单步工具的用法，本文档规范数据准备和分析阶段的端到端行为。

---

## 1. 校准数据格式规范

HMCT 的所有工具（`build_model`、`hmct-debugger`、`hmct_precision_tuning.py` 等）要求校准数据目录为**嵌套格式**。

### 嵌套格式（正确，可直接使用）

```
cali_data/
├── <tensor_name_1>/       # 子目录名必须与模型输入节点名一致
│   ├── 0.npy
│   ├── 1.npy
│   └── ...
└── <tensor_name_2>/
    ├── 0.npy
    ├── 1.npy
    └── ...
```

- 每个模型输入张量对应一个子目录
- 子目录名**必须与 ONNX 模型的输入节点名一致**
- 子目录内为编号的 `.npy` 文件（`0.npy`, `1.npy`, ...）

### 平铺格式（需转换后才能使用）

```
my_data/
├── b0_input_data_imgs.npy          # b<batch_idx>_<prefix>_<tensor_name>.npy
├── b0_input_data_da_mask.npy
├── b1_input_data_imgs.npy
├── b1_input_data_da_mask.npy
└── ...
```

- 所有文件在同一目录下，无子目录
- 文件名含批次索引和张量名（常见命名模式：`b<idx>_input_data_<name>.npy` 或 `b<idx>_<name>.npy`）

### 格式检测方法

在使用 `--cali_data_dir` 或 `calibrated_data` 前，**必须先检查目录格式**：

```python
import os, re

def check_cali_format(data_dir, model_input_names):
    """检查数据目录格式，返回 'nested' / 'flat' / 'unknown'"""
    subdirs = [d for d in os.listdir(data_dir)
               if os.path.isdir(os.path.join(data_dir, d))]
    # 嵌套格式：子目录名覆盖模型输入名
    if set(model_input_names).issubset(set(subdirs)):
        return "nested"
    # 平铺格式：目录下只有 .npy 文件，命名含批次索引
    npy_files = [f for f in os.listdir(data_dir) if f.endswith('.npy')]
    if npy_files and any(re.match(r'b\d+_', f) for f in npy_files):
        return "flat"
    return "unknown"
```

获取模型输入名：

```python
import onnx
model = onnx.load(model_path)
input_names = [inp.name for inp in model.graph.input]
```

### 平铺 → 嵌套转换

当检测到平铺格式时，**自动重组为嵌套格式**，不要询问用户是否需要：

```python
import os, re, shutil

def restructure_flat_to_nested(flat_dir, output_dir):
    """将 flat 格式重组为 nested 格式"""
    os.makedirs(output_dir, exist_ok=True)
    pattern = re.compile(r'^b(\d+)_(?:input_data_)?(.+)\.npy$')
    for fname in sorted(os.listdir(flat_dir)):
        m = pattern.match(fname)
        if m:
            batch_idx = m.group(1)
            tensor_name = m.group(2)
            tensor_dir = os.path.join(output_dir, tensor_name)
            os.makedirs(tensor_dir, exist_ok=True)
            shutil.copy2(
                os.path.join(flat_dir, fname),
                os.path.join(tensor_dir, f"{batch_idx}.npy")
            )
```

### 重组后验证

重组完成后**必须验证**：

1. 子目录名是否与 ONNX 模型输入节点名一致
2. 每个子目录中的 `.npy` 文件是否可正常加载
3. 将验证结果和处理统计写入 `outputs/` 目录的报告文件

---

## 1.5 HMCT 校准方法崩溃处理（强制流程）

当 `calibration_type: histogram` 导致 HMCT 报错（如 IndexError、calibration_method 崩溃）时，**必须**按以下顺序处理：

1. **检查 HMCT 版本**：`hmct --version`，记录版本号
2. **检查 ONNX 模型兼容性**：
   - 动态 shape 是否已固定（`input_dict` 是否提供）
   - 模型是否包含不支持的算子（如 GridSample、ScatterND）
3. **尝试修复**：
   - 提供 `input_dict` 固定动态 shape
   - 简化模型输入/输出（删除非推理输入）
4. **如果修复后仍崩溃**：
   - ⛔ **禁止**静默降级为 `max` 或 `kl` 校准
   - 使用 `oe-mcp search_doc` 检索 "histogram calibration error" 或相关报错信息
   - 向用户报告：说明 histogram 校准在当前模型/版本上不可用，建议走 QAT 路径或等待工具链更新
5. **绝对禁止**：因为 histogram 崩溃而改用其他校准方法 + PTQ 路径来替代本应走 QAT 路径的任务

---

## 2. 敏感度分析工作流

### 工具选择

当用户请求"敏感度分析"/"敏感度评估"时，**优先使用 `hmct-debugger runall`**，它会一次性运行全部 debug 分析（节点灵敏度、数据分布、逐通道分布、累积误差、灵敏度分析），产出完整报告。

| 场景 | 推荐工具 |
|------|----------|
| 用户要求"敏感度分析/评估"，无特定偏好 | `hmct-debugger runall` |
| 用户只需要节点灵敏度排序 | `hmct-debugger get-sensitivity-of-nodes` |
| 用户要看特定节点的数据分布 | `hmct-debugger plot-distribution` |
| 用户要求自定义分析组合 | 分别调用对应工具 |

### CLI 与 Python 脚本的关系

`hmct-debugger` CLI 和 `j6-hmct-cosine-similarity-tuning/script/` 下的 Python 脚本**功能等价**：

- **CLI**（`hmct-debugger runall ...`）：封装了底层 Python API，接口更简洁，推荐在大多数场景使用
- **Python 脚本**（`script/get_sensitivity_of_nodes.py`）：直接调用 `hmct.quantizer.debugger` API，适合需要自定义后处理或集成到更大流程中的场景

### 长时间任务处理（⛔ 关键）

`get-sensitivity-of-nodes` / `runall` 在大模型（>1000 节点）上可能运行**数小时**（约 6 秒/节点）。

**必须遵循以下流程**：

1. 编写包含完整分析逻辑的脚本（脚本自身负责将结果写入指定 `save_dir`）
2. 使用 Bash `run_in_background: true` 启动
3. **一次性启动验证**（等 5-10 秒后检查）：
   ```bash
   ps aux | grep hmct-debugger | grep -v grep
   tail -5 <output_log>
   ```
   确认进程存活且日志无 `Traceback` / `Error`
4. 验证通过后，**停止工作，等待系统完成通知**
5. 收到通知后，读取 `save_dir` 中的分析结果，生成报告写入 `outputs/`

**⛔ 禁止**：

```
# ❌ 以下模式会触发 API 重复调用检测，导致会话终止：
Bash: sleep 540 && tail -c 300 analysis.log   # 第1次
Bash: sleep 540 && tail -c 300 analysis.log   # 第2次
Bash: sleep 540 && tail -c 300 analysis.log   # 第3次 → 崩溃！
```

> 详见 horizon-router SKILL.md「长时间任务的等待策略」。

---

## 3. HMCT 任务的数据预检流程

当 HMCT 路由 A（量化构建）、路由 C（精度调优）、路由 D（精度 Debug）需要使用校准数据时，**必须在调用工具前执行以下预检**：

```
1. 获取 ONNX 模型的输入节点名列表
2. 检查 cali_data_dir 目录格式（嵌套 / 平铺 / 未知）
3. 嵌套格式 → 直接进入下一步
4. 平铺格式 → 自动重组为嵌套格式 → 验证重组结果
5. 未知格式 → 分析目录内容，尝试推断并组织为嵌套格式
6. 将数据处理过程和结果写入 outputs/ 目录
7. 使用处理后的嵌套格式目录继续后续 HMCT 操作
```

> **注意**：数据预检和重组属于"多步骤任务的中间产出"（见 horizon-router SKILL.md），重组完成后必须**立即**将处理报告写入 `outputs/`，不要等到后续 HMCT 操作完成后再写。
