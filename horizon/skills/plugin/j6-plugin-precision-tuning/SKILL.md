---
name: j6-plugin-precision-tuning
description: 当用户遇到 Horizon Plugin PyTorch 精度调优问题时使用。本 skill 聚焦 PyTorch 侧精度调优，不处理 export、convert、compile 或板端一致性问题。
---

# J6 Horizon Plugin PyTorch 精度调优

## 核心原则

解决 **PyTorch 侧** 的训练/校准精度问题。

按下面顺序收敛问题：

1. 先看 `Calibration / QAT` 哪一段开始掉点。
2. 用 `QuantAnalysis` 围绕 badcase 做逐层比较和敏感度分析。
3. 只有基础问题基本排干净后，再做 `int8 / int16 / fp16` 混合精度取舍。

**不要直接把 float 模型和 QAT 模型拿来做常规逐层比较。**
常规精度 debug 优先比较 `float vs calibration(fake_quant)`；QAT 训练异常时，更多是用 float finetune、关 fake quant、`lr=0` 之类手段排查训练 pipeline。

## 执行前门禁

在给出调优建议、修改 qconfig、或要求用户重跑大量实验前，先确认下面信息够不够：

| 必需信息 | 为什么需要 |
| --- | --- |
| 当前异常阶段：`Calibration` / `QAT` | 决定先走哪条排查路径 |
| 至少一个稳定评测指标 | 防止只盯单帧数值、忽略真实精度 |
| 当前模型类型：float / calibration / qat | 防止用错工具和比较对象 |
| 平台 / march：J6E/M 还是 J6P | 决定 int16 / fp16 的主路线 |
| 用于查 badcase 的 dataloader | `QuantAnalysis` 后续步骤都依赖它 |
| 现有产物：敏感度表、逐层对比结果等（若已有 `model_check_result.txt` 也可作为背景参考） | 避免重复劳动 |

### 推荐补充信息

- 校准数据量、batch size、observer 类型。
- QAT 学习率、weight decay、是否 freeze BN。
- 是否已经试过关闭 fake quant、`lr=0`、float finetune。

如果缺少这些信息且会影响判断，先要求补充；不要在没有 badcase 或没有阶段归属的情况下直接开混合精度“盲调”。

## 先判断问题更像哪一类

| 现象 | 更像的问题 | 优先动作 |
| --- | --- | --- |
| `Calibration` 精度崩溃 | scale、fixed scale、共享模块、量化不友好模块、pipeline 问题 | 结合已有检查结果，再做 `float vs calibration` badcase 分析 |
| `Calibration` 还行，`QAT` 崩溃或 loss 异常 | 训练 pipeline、训练参数、fake quant 使用方式问题 | 先排查 float finetune / `_FLOAT` / `lr=0` |
| 全 int16 都不达标 | 不是简单 int8 分辨率不够，可能有 pipeline 或模块本身不友好 | 先解决全 int16 基线，再谈更复杂混合精度 |
| 全 int16 达标，全 int8 不达标 | 正常进入混合精度调优 | 用敏感度结果挑高精度算子 |
| 需要决定哪些算子升到 int16 | 混合精度配置问题 | 用 `sensitivity()` + qconfig 模板 |

## 正确 API 用法

### 1) `prepare`、`QconfigSetter` 与模板

当前仓库主推的混合精度配置方式是 `QconfigSetter + templates`：

```python
import torch

from horizon_plugin_pytorch.quantization import (
    QconfigSetter,
    get_qconfig,
    prepare,
    qint8,
    qint16,
)
from horizon_plugin_pytorch.quantization.qconfig_setter import (
    ConvDtypeTemplate,
    MatmulDtypeTemplate,
    ModuleNameTemplate,
    SensitivityTemplate,
)

setter = QconfigSetter(
    reference_qconfig=get_qconfig(),
    templates=[
        ModuleNameTemplate({"": torch.float16}),
        ConvDtypeTemplate(input_dtype=qint8, weight_dtype=qint8),
        MatmulDtypeTemplate(input_dtypes=qint8),
        SensitivityTemplate(
            sensitive_table=table,
            topk_or_ratio=0.2,
            sensitive_type="activation",
            low_precision_dtype=qint8,
            high_precision_dtype=qint16,
        ),
    ],
)

qat_model = prepare(model, example_inputs=example_inputs, qconfig_setter=setter)
```

说明：

- `SensitivityTemplate` 是当前仓库里真实存在的模板接口。
- `topk_or_ratio` 可以传整数或比例。
- `sensitive_type` 取值为 `activation` / `weight` / `both`。
- `ModuleNameTemplate` 常用于 J6P 场景下把默认输出先设成 `torch.float16`。

### 2) `get_qconfig`

`get_qconfig` 支持的 observer 不是任意类，当前实现只接受：

- `MinMaxObserver`
- `MSEObserver`
- `HistogramObserver`

接口签名：

```python
get_qconfig(
    observer=HistogramObserver,
    in_dtype=qint8,
    weight_dtype=qint8,
    out_dtype=qint8,
    fix_scale=False,
)
```

注意：此接口中的 fix_scale 表示对应的伪量化不再更新 scale。和 fixed_scale 不同，fixed_scale 是针对特定模块的特定输入/输出设置一个固定值域，而不是简单地禁止更新 scale。

如果要表达更复杂的自定义量化行为，优先通过 `QConfig` / `QconfigSetter` 模板组合实现，而不是强行把所有逻辑塞进 `get_qconfig(...)`。

### 3) `FixedScaleObserver` 正确用法

`FixedScaleObserver` 适用于需要强制固定 scale 和 zero_point 的场景（如输入图像归一化到 `[0,1]` 后的 QuantStub、输出层需要固定值域等）。它不会根据输入数据统计 scale，而是始终返回构造时传入的固定值。

**务必使用 `observer_v2` 中的 `FixedScaleObserver`，`observer` 模块中的版本已废弃。**

#### 直接构造

```python
from horizon_plugin_pytorch.quantization.observer_v2 import FixedScaleObserver
from horizon_plugin_pytorch.quantization import qint8

# 构造时传入 scale 和 zero_point
observer = FixedScaleObserver(scale=1 / 128.0, zero_point=0, dtype=qint8)
```

参数说明：
- `scale`（必传）：固定 scale 值，必须 > 0。也可传 `torch.Tensor`（per-channel 场景）。
- `zero_point`：固定 zero_point 值，默认 0。
- `dtype`：量化数据类型，默认 `qint8`，也可选 `qint16`。
- `qscheme`：量化方案，默认 `torch.per_tensor_symmetric`。
- `ch_axis`：per-channel 的通道轴，默认 -1（per-tensor）。

#### 通过 `QconfigSetter` + `ModuleNameTemplate` 的 threshold 设置（推荐）

推荐使用 `ModuleNameTemplate` 的 `threshold` 参数来设置固定值域。模板内部会自动将 `threshold` 转换为 `FixedScaleObserver` 的 `scale`（计算方式：`scale = threshold / (-quant_min)`），无需手动构造 `QConfig`。

```python
from horizon_plugin_pytorch.quantization import (
    QconfigSetter,
    get_qconfig,
    prepare,
    qint8,
    qint16,
)
from horizon_plugin_pytorch.quantization.qconfig_setter import ModuleNameTemplate

# 通过 threshold 设置固定值域：数据范围为 [-threshold, threshold]
setter = QconfigSetter(
    reference_qconfig=get_qconfig(),
    templates=[
        ModuleNameTemplate({
            "": qint8,                              # 全局默认 dtype
            "quant": {"threshold": 1.0},            # quant 模块 output 的 fixed scale，scale = 1.0 / 128
            "backbone.conv1": {
                "dtype": qint16,                     # 同时设置 dtype 和 threshold
                "threshold": {"output": 1.0, "input": 0.5},  # 分别设置 output 和 input 的 fixed scale
            },
        }),
    ],
)
model = prepare(model, example_inputs=example_inputs, qconfig_setter=setter)
```

`ModuleNameTemplate` 的 `config_mapping` 用法：
- 值为 dtype：应用到 output，如 `{"conv": qint16}`
- 值为 dict 且含 `dtype`/`threshold` 键：按 key-value 对指定，如 `{"conv": {"dtype": qint16, "threshold": 1.0}}`
- 值为 dict 且不含 `dtype`/`threshold` 键：当作完整的 dtype 映射，如 `{"conv": {"output": qint16, "weight": qint8}}`
- `threshold` 为 float：应用到 output，如 `{"conv": {"threshold": 1.0}}`
- `threshold` 为 dict：分别指定各端口，如 `{"conv": {"threshold": {"input": 1.0, "output": 0.5}}}`
- `dtype` 和 `threshold` 可同时给出

### 4) `HistogramObserver.reset_scale`

做过一次校准后，可以在 **不重跑 calibration 数据** 的前提下重算 scale：

```python
from horizon_plugin_pytorch.quantization import qint8, qint16
from horizon_plugin_pytorch.quantization.observer_v2 import HistogramObserver

HistogramObserver.reset_scale(
    calib_model,
    method="percentile",
    method_kwargs={"percentile": 0.999999},
    dtype=qint8,
)

HistogramObserver.reset_scale(
    calib_model,
    method="percentile",
    method_kwargs={"percentile": 1.0},
    dtype=qint16,
)
```

可选地使用 `prefix` 只重算局部模块。调完后重新保存 `state_dict` 再评测。

### 5) `QuantAnalysis`

当前推荐从包入口导入：

```python
from horizon_plugin_profiler import QuantAnalysis
```

典型流程：

```python
qa = QuantAnalysis(float_model, calibration_model, "fake_quant")
qa.auto_find_bad_case(dataloader)
qa.run()
qa.compare_per_layer()
qa.sensitivity()
```

关键点：

- `analysis_model_type` 做 PyTorch 精度调优时常用的是 `"fake_quant"`。
- `run()` 前必须先 `auto_find_bad_case(...)`、`set_bad_case(...)` 或 `load_bad_case(...)`。
- `load_bad_case()` 默认读 `out_dir/all_badcase_info.pt`。

### 6) fake quant 状态切换

```python
from horizon_plugin_pytorch.quantization import FakeQuantState, set_fake_quantize

set_fake_quantize(model, FakeQuantState.CALIBRATION)
set_fake_quantize(model, FakeQuantState.VALIDATION)
set_fake_quantize(model, FakeQuantState._FLOAT)
```

用途：

- `CALIBRATION`：只更新统计量，不做真实伪量化，通常配合 `model.eval()`。
- `VALIDATION`：固定 scale，开启伪量化，用于评测 calibration / qat 模型。
- `_FLOAT`：**仅供诊断**。关闭 fake quant，用于判断训练 pipeline 或 fake quant 使用方式是否有明显问题，不应把它当成正常精度结论。

### 7) QAT 模式

如果浮点训练里用了 freeze BN 技巧，QAT 中需要显式切换：

```python
from horizon_plugin_pytorch.quantization import QATMode, set_qat_mode

set_qat_mode(QATMode.WithBN)
```

## 分阶段排查流程

### 1. Calibration 精度问题

适用：`Calibration` 后精度不达标，或者全 int16 calibration 都崩。

建议顺序：

1. 用 `float_model` 和 `calibration_model` 创建 `QuantAnalysis`。
2. 先 `auto_find_bad_case(dataloader)`，不要一开始就人工拍脑袋选样本。
3. 再 `run()` + `compare_per_layer()` 看误差从哪里开始放大。
4. 必要时结合 `HistogramObserver.reset_scale(...)` 试 `mse` / `percentile`。
5. 如果敏感算子大多是 `QuantStub`、共享模块或固定值输入相关节点，优先结合已有结构 / qconfig 检查结果，判断是不是设置特定 scale、输入值域或共享模块拆分问题。

观察原则：

- **极值明显被截断**：更像 scale 太小、统计范围不够、缺特定的 fixed scale。
- **极值没怎么截断，但误差仍大**：更像 dtype 分辨率不够、数值范围太宽、需要升高精度。

### floatvscalib debug 结果解读

当用户要求解读 floatvscalib（float vs calibration）debug 结果时，**必须在执行任何分析之前**先读取 `references/debug-analysis-framework.md`。该文档包含完整的误差分类标准、逐算子分析流程和修复方案对照表，是 floatvscalib 场景的核心执行框架，**不可跳过**。

读取后严格按以下流程执行：

1. **提取 top-5 敏感算子列表**：从 `output_xxx_sensitive_ops.txt` 中提取算子名和 ATOL 值
2. **逐算子检索逐层对比数据**：对每个 top-5 算子，**必须**通过 Bash 执行 `grep "<算子名>" compare_per_layer_out.csv` 提取该算子的完整数据行。⛔ **禁止**使用 Read 工具全文读取 `compare_per_layer_out.csv`——该文件通常有数千行（>500KB），Read 只返回开头部分（backbone 层），会遗漏 decoder 等后部算子数据。从 grep 结果中提取以下字段：
   - `base_model_min`, `base_model_max`（float 模型的值域）
   - `analy_model_min`, `analy_model_max`（calibration 模型的值域）
   - `COSINE`, `ATOL`（精度指标）
   - `max_qscale_diff`（scale 差异）
3. **误差类型分类**：对比 base_model 和 analy_model 的 min/max 值域——值域被截断为**截断误差**，值域接近但精度仍差为**舍入误差**
4. **差异化修复方案**：
   - 截断误差 → 从 `abnormal_layer_advisor.csv` 读取 `Set fixed scale X` 建议值 + 增加样本量
   - 舍入误差 → 提升 dtype 到 qint16，并给出具体的 `fix-scale` 数值建议（基于算子实际最大范围）
5. **结构化输出**：对每个 top-5 算子输出排名、值域对比、误差类型和具体修复建议

**不要**将所有精度问题统一归为"提升 dtype"——必须先做误差归因，再给差异化建议。

### 2. QAT 精度或训练异常

适用：calibration 还行，但 QAT 精度崩、loss 不收敛、出现 nan。

按下面顺序排查：

1. **去掉 prepare，直接用 QAT pipeline finetune float 模型**，看是否仍崩。若仍崩，更像训练 pipeline 没对齐。
2. **关掉 fake quant**：

   ```python
   set_fake_quantize(model, FakeQuantState._FLOAT)
   ```

   若关闭后训练正常，优先怀疑 fake quant 使用方式或量化配置。

3. **把 lr 设为 0**。如果 `lr=0` 仍与 calibration 精度差很多，优先怀疑 pipeline 或 checkpoint 对齐问题。
4. 再去调学习率、scheduler、weight decay、数据增强强度。

对于 QAT 调参，不要忽略这些共识：

- QAT 其余配置尽量与 float 训练对齐。
- 一般不建议继续保留 warmup。
- 校准精度较好时，可以尝试固定 input / output scale；较差时不一定适合固定。

### 3. 混合精度调优

混合精度不是一开始就把最终比例拍死，而是：

1. 先得到一个“精度上限比较靠谱”的高精度基线。
2. 再逐步减少高精度算子比例，直到找到兼顾性能与精度的配置。

#### J6E/M

建议顺序：

1. 先做 **全 int16**，确认上限并排除使用问题。
2. 再尝试 **全 int8**。
3. 全 int8 不达标时，基于敏感度结果做 `int8 / int16` 混合精度。
4. 若全 int16 仍不够，再考虑少量 `fp16`，而不是过早全面铺开 fp16。

#### J6P

J6P 浮点能力更强，通常更自然的起点是：

- 非 GEMM 算子先走 `torch.float16`
- Conv / Matmul 等 GEMM 算子从 `int8/int16` 开始权衡

典型模板思路：

```python
setter = QconfigSetter(
    reference_qconfig=get_qconfig(),
    templates=[
        ModuleNameTemplate({"": torch.float16}),
        ConvDtypeTemplate(input_dtype=qint16, weight_dtype=qint16),
        MatmulDtypeTemplate(input_dtypes=qint16),
    ],
)
```

### 4. 如何用敏感度结果落到配置上

优先推荐 `SensitivityTemplate`，因为它是当前仓库里的主线接口。

```python
SensitivityTemplate(
    sensitive_table=table,
    topk_or_ratio=0.2,
    sensitive_type="activation",
    low_precision_dtype=qint8,
    high_precision_dtype=qint16,
)
```

经验：

- 先统一比例粗调，比如 20%、10%、5%。
- 精度达标后，再细调单个输出对应的敏感度表。
- 若敏感度表带 `flops`，性能优化时可以优先保留大算子为低精度。

### 5. 兼容旧工程时的旧式 setter

仓库里仍有旧式接口，但它们在 `qconfig_template.py`，不属于当前更推荐的模板主线：

```python
from horizon_plugin_pytorch.quantization.qconfig_template import (
    sensitive_op_calibration_8bit_weight_16bit_act_qconfig_setter,
    sensitive_op_qat_8bit_weight_16bit_act_qconfig_setter,
)
```

可以用于兼容旧代码，但新方案优先使用 `QconfigSetter + SensitivityTemplate`。

## 输出报告模板

每次分析结束，都按下面格式输出，避免只给零散命令：

```markdown
## 结论摘要
- 当前最可能的问题阶段：calibration / qat / mixed precision / 暂不能判断
- 主要证据：...

## 已确认事实
- 平台 / march：...
- 当前模型：float / calibration / qat
- 稳定指标：...
- badcase：...

## 已做检查
1. ...
2. ...

## 关键发现
- 第一个明显放大误差的算子：...
- 更像是截断误差 / 舍入误差 / 共享模块 / qconfig 错误 / 训练 pipeline 问题
- 相关产物：`compare_per_layer_out.txt` / `output_xxx_sensitive_ops.txt` / 其他已有分析结果

## 下一步最小动作
- ...

## 需要补充的输入
- ...
```

如果证据还不够，明确写“暂不能判断”，不要为了给结论而猜根因。

## 常见误区

| 误区 | 正确做法 |
| --- | --- |
| Calibration 掉点就立刻做混合精度 | 先结合已有的结构、qconfig、shared module、fixed scale 检查结果 |
| 直接比较 float 和 QAT 做常规逐层分析 | 优先比较 float 和 calibration(fake_quant) |
| `qa.sensitive()` 是当前 API | 当前接口是 `qa.sensitivity()` |
| 全 int16 也崩还能继续细调 int8 比例 | 先把全 int16 基线救起来 |
| 看到 fixed scale 提示就删 | 先判断它是否正是应该固定值域的地方 |
| QAT 崩溃就只会调 lr | 先排 float finetune、`_FLOAT`、`lr=0`、pipeline 对齐 |
| 敏感度表靠前的层一定就是根因 | 还要结合逐层比较、统计范围和业务含义 |
| `_FLOAT` 模式下正常，就可以拿来当最终精度 | `_FLOAT` 只用于诊断，不代表量化方案成立 |

## 何时不该用这个 skill

以下情况应切到别的 skill 或别的问题域：

- 问题已经确认出在 `export / convert / compile / hbm / 板端`。
- 用户当前问题还停留在 `prepare` 后的结构 / 融合 / qconfig 检查阶段。
- 用户要做的是 HBIR 导出，而不是 PyTorch 侧精度调优。
- 用户要分析的是部署一致性，而不是 calibration / QAT 阶段精度。

此时不要继续在 PyTorch 精度调优路径里打转。

## floatvscalib 场景自动加载文档

以下文档在 **floatvscalib debug 场景下必须立即加载**，不要跳过：

| 文档 | 路径 | 加载条件 |
|------|------|----------|
| Debug 结果解读框架 | `references/debug-analysis-framework.md` | 用户要求解读 floatvscalib debug 结果、分析 float vs calibration 精度问题、或 debug 产物目录中包含 `compare_per_layer_out`、`abnormal_layer_advisor`、`sensitive_ops` 文件时。**必须**在进入本 Skill 后立即读取，不要延迟到后续步骤 |

## 按需加载参考文档

以下文档**只在相关任务时才需要读取**，不必在每次进入本 Skill 时全部加载：

（当前无其他按需加载文档）
