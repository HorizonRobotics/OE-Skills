# YAML 推荐参数组合 — 按任务分类

> 以下推荐配置均基于源码中的校验规则和约束条件设计，确保参数组合合法。
> 参考模板：`horizon_tc_ui/template/full_template.yaml`

## 1. 分类任务（ImageNet 风格）

适用于 ResNet、MobileNet、EfficientNet 等图像分类模型。

**特点**：单输入、固定分辨率、NV12 推理输入、BGR 训练数据。

```yaml
model_parameters:
  onnx_model: ./resnet50.onnx
  march: nash-h
  working_dir: ./model_output
  output_model_file_prefix: resnet50

input_parameters:
  input_type_rt: nv12
  input_type_train: bgr
  input_layout_train: NCHW
  input_shape: 1x3x224x224
  mean_value: 123.675,116.28,103.53
  std_value: 58.395,57.12,57.375

calibration_parameters:
  cal_data_dir: ./cal_data
  calibration_type: kl
  per_channel: false

compiler_parameters:
  compile_mode: latency
  optimize_level: O2
  core_num: 1
  max_time_per_fc: 0
  jobs: 16
```

**参数说明**：
- `input_type_rt: nv12`：推理输入为 NV12 格式（摄像头原始输出常用）
- `input_type_train: bgr` → `input_type_rt: nv12`：合法转换（见 `legal_trans_dict`）
- `input_layout_train: NCHW`：BGR 训练数据使用 NCHW 布局，通道维=3 校验通过
- `mean_value` / `std_value`：ImageNet 标准预处理参数
- `calibration_type: kl`：KL 散度校准，分类任务精度优先
- `per_channel: false`：per-tensor 量化，分类任务通常足够

---

## 2. 检测任务（多尺度、大样本）

适用于 YOLO 系列、SSD、RetinaNet 等目标检测模型。

**特点**：可能需要截断输出节点、较大校准数据集、per-channel 量化。

```yaml
model_parameters:
  onnx_model: ./yolov5.onnx
  march: nash-h
  working_dir: ./model_output
  output_model_file_prefix: yolov5
  output_nodes: Conv_200;Conv_201

input_parameters:
  input_type_rt: nv12
  input_type_train: bgr
  input_layout_train: NCHW
  input_shape: 1x3x640x640
  mean_value: 0,0,0
  scale_value: 0.00392156862745098

calibration_parameters:
  cal_data_dir: ./cal_data
  calibration_type: kl
  per_channel: true

compiler_parameters:
  compile_mode: latency
  optimize_level: O2
  core_num: 4
  max_time_per_fc: 0
  jobs: 32
```

**参数说明**：
- `output_nodes`：截断模型到指定输出节点（检测头输出）
- `input_shape: 1x3x640x640`：YOLOv5 标准输入分辨率
- `scale_value`：替代 std_value（YOLO 通常只做 scale，不做 mean）
- `per_channel: true`：检测任务推荐 per-channel 量化以提升精度
- `core_num: 4`：nash-h 支持 4 核，大模型推荐多核加速
- `jobs: 32`：增加并行度加速编译

---

## 3. 分割任务（高分辨率、内存敏感）

适用于 DeepLab、UNet、Mask R-CNN 等语义/实例分割模型。

**特点**：高分辨率输入、内存消耗大、可能需要 L2M 调优。

```yaml
model_parameters:
  onnx_model: ./deeplabv3.onnx
  march: nash-h
  working_dir: ./model_output
  output_model_file_prefix: deeplabv3

input_parameters:
  input_type_rt: nv12
  input_type_train: bgr
  input_layout_train: NCHW
  input_shape: 1x3x512x512
  mean_value: 123.675,116.28,103.53
  std_value: 58.395,57.12,57.375

calibration_parameters:
  cal_data_dir: ./cal_data
  calibration_type: max
  max_percentile: 0.9999
  per_channel: true

compiler_parameters:
  compile_mode: bandwidth
  optimize_level: O2
  core_num: 4
  max_time_per_fc: 120000
  max_l2m_size: 16777216
  jobs: 16
```

**参数说明**：
- `calibration_type: max` + `max_percentile: 0.9999`：分割任务特征分布广，max 校准 + 百分位截断可避免异常值影响
- `compile_mode: bandwidth`：分割模型通常带宽敏感，优先优化带宽
- `max_time_per_fc: 120000`：大模型编译耗时，设置合理超时
- `max_l2m_size: 16777216`（16MB）：为分割模型分配更多 L2M 内存（注意：nash-b/e/m 不支持）

---

## 4. 多输入任务

适用于多模态模型、双分支网络、Stereo 立体匹配等。

**特点**：多个输入必须显式指定名称、类型、形状，参数数量严格匹配。

```yaml
model_parameters:
  onnx_model: ./multi_input.onnx
  march: nash-h
  working_dir: ./model_output
  output_model_file_prefix: multi_input

input_parameters:
  input_name: left_image;right_image
  input_type_rt: nv12;nv12
  input_type_train: bgr;bgr
  input_layout_train: NCHW;NCHW
  input_shape: 1x3x480x640;1x3x480x640
  mean_value: 123.675,116.28,103.53;123.675,116.28,103.53
  std_value: 58.395,57.12,57.375;58.395,57.12,57.375

calibration_parameters:
  cal_data_dir: ./cal_data_left;./cal_data_right
  calibration_type: kl
  per_channel: false

compiler_parameters:
  compile_mode: latency
  optimize_level: O2
  core_num: 1
  jobs: 16
```

**参数说明**：
- `input_name`：**必填**，多输入模型必须显式指定所有输入名称（源码 L402-L406）
- 所有列表参数数量 = 2（与输入数严格匹配）
- `cal_data_dir`：每个输入对应一个校准数据目录
- 使用分号 `;` 分隔多个输入的参数值

---

## 5. fast_perf 最小配置（快速性能测试）

用于快速验证模型编译是否通过、评估推理性能，跳过量化校准。

参考模板：`horizon_tc_ui/template/fast_perf_template.yaml`

```yaml
model_parameters:
  onnx_model: ./model.onnx
  march: nash-h
  working_dir: ./model_output
  output_model_file_prefix: model
  remove_node_type: Quantize;Transpose;Dequantize;Cast;Reshape;Softmax

input_parameters:
  input_name: input_0
  input_shape: 1x3x224x224
  input_type_rt: nv12
  input_type_train: bgr
  input_layout_train: NCHW

calibration_parameters:
  optimization: run_fast

compiler_parameters:
  compile_mode: latency
  optimize_level: O2
  core_num: 1
  max_time_per_fc: 0
  jobs: 0
```

**参数说明**：
- `optimization: run_fast`：跳过校准流程，使用默认量化参数快速编译
- `remove_node_type`：移除量化/转置等节点，简化模型图
- `jobs: 0`：fast_perf 模板中使用 0（见 `fast_perf_template.yaml`）
- `cal_data_dir` 不需要：run_fast 模式跳过校准数据校验
- `input_name` 和 `input_shape` 在 run_fast 模式下有特殊校验逻辑（仅允许修改动态 batch 维）

---

## 6. 模型检查配置（Check 模式）

用于验证模型结构是否正确加载、检查节点信息，不进行量化编译。

参考模板：`horizon_tc_ui/template/check_template.yaml`

```yaml
model_parameters:
  onnx_model: ./model.onnx
  march: nash-h
  working_dir: ./model_output
  output_model_file_prefix: model

input_parameters:
  input_type_rt: featuremap
  input_type_train: featuremap
  input_layout_train: NCHW

compiler_parameters:
  compile_mode: latency
  optimize_level: O0
  core_num: 1
  max_time_per_fc: 0
  jobs: 32
```

**参数说明**：
- `input_type_rt: featuremap` / `input_type_train: featuremap`：跳过图像预处理逻辑
- `optimize_level: O0`：无优化，编译最快，用于快速检查
- 不需要 `cal_data_dir`：featuremap 输入跳过校准
- 不需要 `input_layout_train` 的通道校验：featuremap 跳过通道维检查

---

## 参数可追溯性索引

| 参数约束 | 源码位置 |
|---------|---------|
| train→rt 转换合法性 | `mapper_consts.py` → `legal_trans_dict` |
| input_type_rt 合法值 | `mapper_consts.py` → `input_type_rt_open_list` |
| input_type_train 合法值 | `mapper_consts.py` → `input_type_train_open_list` |
| layout 推断规则 | `mapper_consts.py` → `NHWC_types` / `NCHW_types` / `NONE_types` |
| core_num 与 march 关系 | `mapper_consts.py` → `core_num_range` |
| input_source 兼容性 | `mapper_consts.py` → `input_source_support_dict` |
| compile_mode 与 balance_factor | `mapper_consts.py` → `balance_factor_mapping` |
| optimize_level (HBDK4) | `mapper_consts.py` → `optimize_level_hbdk4` |
| cache_mode 合法值 | `mapper_consts.py` → `cache_mode_list` |
| calibration_type 合法值 | `mapper_consts.py` → `autoq_caltype_list` + `preq_caltype_list` |
| max_time_per_fc 范围 | `params_parser.py` → `_validate_max_time_per_fc()` |
| max_l2m_size 范围 | `params_parser.py` → `_validate_max_l2m_size()` |
| NV12 奇数限制 | `params_parser.py` → `_validate_odd_shape()` |
| 多输入必填规则 | `params_parser.py` → `_validate_input_name()` |
| scale vs std 互斥 | `params_parser.py` → `_validate_norm_type()` |
