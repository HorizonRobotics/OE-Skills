# YAML 参数参考 — input_parameters

> 源码依据：`horizon_tc_ui/config/schema_yaml.py`（schema 定义）
> 校验逻辑：`horizon_tc_ui/config/params_parser.py` → `_validate_input_parameters()`
> 常量定义：`horizon_tc_ui/config/mapper_consts.py`

## 完整参数表

| 参数 | 类型 | 默认值 | 必填 | 可选范围 | 说明 |
|------|------|--------|------|----------|------|
| `input_name` | str | `""` | 多输入时**必填** | 分号分隔的节点名 | 模型输入节点名称列表。单输入时可省略（自动从模型读取）；多输入时必须显式指定以确保顺序 |
| `input_type_rt` | str | `""` | **必填** | 见下方合法值列表 | 推理时（runtime）的输入数据类型 |
| `input_type_train` | str | `""` | **必填** | 见下方合法值列表 | 训练时的输入数据类型 |
| `input_layout_train` | str | `""` | 非 featuremap 输入时**必填** | `NCHW` / `NHWC` | 训练数据的内存布局 |
| `input_layout_rt` | str | `""` | 否 | - | **已废弃**，指定此参数无效 |
| `input_space_and_range` | str | `""` | 否 | `regular` / `bt601_video` | 输入色彩空间与范围。未指定时运行时自动填充为 `regular`。`bt601_video` 仅与 `nv12` 配合使用 |
| `input_shape` | str | `None` | 动态形状时**必填** | 格式 `"1x3x224x224"`，多个输入用分号分隔 | 输入张量形状。动态维度模型必须显式指定 |
| `input_batch` | str | `None` | 否 | 单个整数值 | 统一设置所有输入的 batch 大小。要求 input_shape 第一维为 1 |
| `separate_batch` | bool/str/int | `false` | 否 | bool | 是否对部分输入分离 batch。与 `separate_name` 互斥 |
| `separate_name` | str | `None` | 否 | 分号分隔的节点名 | 指定需要分离 batch 的输入名称。与 `separate_batch` 互斥 |
| `norm_type` | str | `None` | 否 | - | **已废弃**。现在由 mean/scale/std 的指定情况自动推导 |
| `mean_value` | str | `None` | 否 | 逗号分隔的浮点数，多个输入用分号 | 预处理均值，按通道指定 |
| `scale_value` | str | `None` | 否 | 逗号分隔的浮点数，多个输入用分号 | 预处理缩放因子。与 `std_value` 互斥 |
| `std_value` | str | `None` | 否 | 逗号分隔的浮点数，多个输入用分号 | 预处理标准差。与 `scale_value` 互斥 |

## input_type_rt 合法值

源码位置：`mapper_consts.py` → `input_type_rt_open_list`（当前开放使用）

| 值 | 说明 | 布局推断 |
|----|------|---------|
| `nv12` | YUV420 半平面格式（视频输入常用） | 无布局（NONE_types） |
| `yuv444` | YUV444 格式 | NHWC |
| `rgb` | RGB 格式 | NHWC |
| `bgr` | BGR 格式 | NHWC |
| `gray` | 灰度图 | NCHW |
| `featuremap` | 特征图（非图像输入） | NCHW |

完整列表（含暂未开放的值）：`mapper_consts.py` → `input_type_rt_list`
额外包含：`yuv444_128`, `yuv_bt601_full`, `yuv_bt601_video`

## input_type_train 合法值

源码位置：`mapper_consts.py` → `input_type_train_open_list`（当前开放使用）

| 值 | 说明 |
|----|------|
| `rgb` | RGB 格式 |
| `bgr` | BGR 格式 |
| `featuremap` | 特征图 |
| `gray` | 灰度图 |
| `yuv444` | YUV444 格式 |

完整列表（含暂未开放的值）：`mapper_consts.py` → `input_type_train_list`
额外包含：`yuv444_128`, `yuv_bt601_full`, `yuv_bt601_video`

## train → rt 合法转换表

源码位置：`mapper_consts.py` → `legal_trans_dict`

| input_type_train | 可转换到的 input_type_rt |
|------------------|------------------------|
| `rgb` | `bgr`, `nv12`, `yuv444`, `yuv444_128`, `yuv420sp_bt601_video` |
| `bgr` | `rgb`, `nv12`, `yuv444`, `yuv444_128`, `yuv420sp_bt601_video` |
| `yuv444` | `yuv444_128`, `nv12` |

train 与 rt 类型相同时无需转换，始终合法。
不在上表中的转换组合将报错。

## 布局（layout）推断规则

源码位置：`mapper_consts.py` → `NHWC_types` / `NCHW_types` / `NONE_types`

| input_type_rt | 自动推断的布局 |
|---------------|--------------|
| `rgb`, `bgr`, `yuv444`, `yuv444_128` | NHWC |
| `gray`, `featuremap` | NCHW |
| `nv12`, `yuv420sp_bt601_video` | 无布局（NONE） |

## 互斥关系

1. **`separate_batch` vs `separate_name`**：不能同时指定
   - 源码：`params_parser.py` → `_validata_separate_name()` L524-L526

2. **`scale_value` vs `std_value`**：不能同时指定
   - 源码：`params_parser.py` → `_validate_norm_type()` L673-L675

3. **`input_batch` 限制**：只能指定单个值，且要求所有 input_shape 第一维为 1
   - 源码：`params_parser.py` → `_validate_input_batch()` L494-L503

## NV12 奇数 shape 限制

当 `input_type_rt` 为 `nv12` 时，输入形状的 H 和 W 维度必须为偶数。

- NCHW 布局：检查 `shape[2]` 和 `shape[3]`
- NHWC 布局：检查 `shape[1]` 和 `shape[2]`

源码：`params_parser.py` → `_validate_odd_shape()` L756-L769

## norm_type 自动推导规则

源码：`params_parser.py` → `_validate_norm_type()` L677-L691

| mean_value | scale_value | std_value | 推导的 norm_type |
|-----------|------------|----------|-----------------|
| - | - | - | `no_preprocess` |
| 有 | - | - | `data_mean` |
| - | 有 | - | `data_scale` |
| - | - | 有 | `data_std` |
| 有 | 有 | - | `data_mean_and_scale` |
| 有 | - | 有 | `data_mean_and_std` |

**注意**：当 `input_type_rt` 为 `featuremap` 时，不支持配置 mean/scale/std。

## 多输入规则

1. 模型有多个输入时，`input_name` 必须显式指定所有输入名称
2. 所有列表型参数（`input_type_rt`, `input_shape`, `mean_value` 等）的数量必须与模型输入数量一致
3. 参数值使用分号 `;` 分隔多个输入

## 典型错误

| 错误片段 | 原因 | 修法 |
|---------|------|------|
| `Model has more than one input! It is necessary to explicitly specify all the input_name` | 多输入模型未指定 input_name | 显式列出所有输入名称 |
| `Wrong num of input_name specified` | input_name 数量与模型不匹配 | 确保数量一致 |
| `Input names duplicated` | input_name 有重复 | 去重 |
| `The specified input_name Xxx does not exist in model file` | 输入名称不在模型中 | 使用模型实际的输入名称 |
| `The input_shape parse failed` | input_shape 格式错误 | 使用 `1x3x224x224` 格式 |
| `The model is a dynamically input model. Please specify the 'input_shape'` | 动态维度模型未指定 input_shape | 显式指定完整形状 |
| `The specified input_type_rt is Xxx, but the input_shape is not four-dimensional` | 非 featuremap 类型但形状不是 4 维 | 设置类型为 featuremap 或修正形状 |
| `This model has non-featuremap inputs, please specify the input_layout_train` | 非 featuremap 输入未指定布局 | 设置 `NCHW` 或 `NHWC` |
| `The input_type_train 'Xxx' ... is not supported to be transformed to input_type_rt 'Yyy'` | train→rt 转换不合法 | 参考上方转换表 |
| `Only one of scale_value and std_value can be specified` | 同时指定了 scale 和 std | 只保留一个 |
| `nv12 type does not support odd number input size` | NV12 输入形状有奇数维度 | 将 H/W 调整为偶数 |
| `The specified input_space_and_range: Xxx and input_type_rt Yyy combination is invalid` | `bt601_video` 只能与 `nv12` 配合 | 修正组合 |
