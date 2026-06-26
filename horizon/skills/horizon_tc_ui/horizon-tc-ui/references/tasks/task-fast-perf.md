# 快速性能估算（fast-perf 模式）

## 适用场景

**触发关键词**：性能估算、fast-perf、快速编译、不需要精度、性能评估、check 模式

**前置条件**：
- 已有 `.onnx` 或 `.caffemodel` + `.prototxt` 模型文件
- 已确认目标 march 架构
- **不需要**准备校准数据（calibration dataset）
- **不需要**编写 YAML 配置文件

## 产出物

| 产物文件 | 路径 | 说明 |
|---------|------|------|
| `{prefix}.hbm` | `./model_output/{prefix}.hbm` | HBM 模型（无精度保证，仅性能参考） |
| `{prefix}.json` | `./model_output/{prefix}.json` | 性能分析 JSON（内存占用、算子信息） |
| `hb_compile.log` | 当前目录 + `./model_output/` | 编译日志 |

> **重要**：fast-perf 模式生成的 HBM 模型**没有经过校准量化**，精度不可保证，仅用于性能（延迟、内存）评估。

## 步骤

### 步骤 1：基本命令

```bash
hb_compile --fast-perf -m model.onnx --march nash-e
```

这是最简命令，会自动：
1. 使用 `fast_perf_template.yaml` 模板生成临时 YAML
2. 从 ONNX 模型自动推断 `input_name`、`input_shape`、`input_type_rt`、`input_type_train`
3. 跳过校准（`optimization: run_fast`）
4. 执行完整的 export → convert → compile 流程

### 步骤 2：处理动态输入 shape

如果模型有动态维度（如 batch 维度是 `?` 或 `-1`），需要手动指定：

```bash
hb_compile --fast-perf -m model.onnx --march nash-e \
  --input-shape input 1x3x640x640
```

**多输入模型**（多次使用 `--input-shape`）：
```bash
hb_compile --fast-perf -m model.onnx --march nash-e \
  --input-shape input0 1x3x224x224 \
  --input-shape input1 1x256
```

### 步骤 3：Caffe 模型

```bash
hb_compile --fast-perf -m model.caffemodel --proto model.prototxt --march nash-e
```

### 步骤 4：指定 BPU 核心数

```bash
hb_compile --fast-perf -m model.onnx --march nash-p --core-num 4
```

> `core_num` 仅在 check/fast-perf 模式下可用。标准编译模式需在 YAML 中配置。

### 步骤 5：分阶段跳过

```bash
# 只编译到量化阶段，不生成 HBM
hb_compile --fast-perf -m model.onnx --march nash-e --skip compile
```

### 步骤 6：查看性能报告

```bash
# 查看 perf JSON 文件
cat model_output/model.json | python3 -m json.tool

# 使用 hb_model_info 查看模型信息
hb_model_info model_output/model.hbm
```

## 自动 input_type 推断规则

fast-perf 模式根据模型的 `input_layout` 和输入 shape 自动推断输入类型（源码 `yaml_builder.py:update_params_of_fast_perf()`）：

| 模型 input_layout | 输入 shape 条件 | 推断 input_type_train | 推断 input_type_rt |
|------------------|----------------|----------------------|-------------------|
| 非空（有 layout）且为 4D、channel=3、宽高为偶数 | 4D 且宽高为偶数 | `bgr` | `nv12` |
| 其他情况（非 4D、channel≠3、奇数宽高、无 layout） | 不满足上述条件 | `featuremap` | `featuremap` |

`input_layout_train` 根据 channel 维度位置自动推断：channel 在第 1 维为 `NCHW`，在第 3 维为 `NHWC`。

## 与完整编译的区别

| 对比项 | fast-perf 模式 | 完整编译（YAML 配置） |
|-------|---------------|---------------------|
| YAML 配置 | 自动生成，无需手动编写 | 需要手动编写 YAML |
| 校准数据 | 不需要（`optimization: run_fast`） | 需要 `cal_data_dir` |
| 量化精度 | 无保证 | 经过校准，精度有保证 |
| 输入参数 | 自动从模型推断 | YAML 中显式配置 |
| optimize_level | 固定 `O2` | 可配置（`O0`/`O1`/`O2`） |
| 适用阶段 | 早期性能评估 | 最终部署 |
| 输出 HBM 可用性 | 仅性能参考 | 可部署到板端 |

## 输出产物和性能报告解读

### perf JSON 文件结构

```json
{
  "summary": {
    "DDR access data": {
      "input memory": "...",
      "output memory": "...",
      "static memory": "...",
      "dynamic memory": "...",
      "intermediate memory": "...",
      "temporary memory": "...",
      "min memory requirement": "..."
    }
  }
}
```

### 使用 hb_model_info 查看

```bash
hb_model_info model_output/model.hbm
```

会输出：
- 模型依赖信息（HBDK 版本、HMCT 版本）
- 模型参数（march、working_dir、output_model_file_prefix 等）
- 输入/输出参数（名称、shape、数据类型）
- 校准参数
- 编译器参数（optimize_level、core_num 等）
- 内存信息（来自 perf JSON）

## 校验清单

- [ ] 命令执行完成，无报错退出
- [ ] `hb_compile.log` 中包含 `The hb_compile completes running.`
- [ ] `model_output/{prefix}.hbm` 文件存在
- [ ] `model_output/{prefix}.json` 文件存在
- [ ] `hb_model_info model_output/model.hbm` 可正常输出
- [ ] perf JSON 中 `min memory requirement` 有合理数值
- [ ] 日志中 `optimize_level` 确认为 `O2`
- [ ] 日志中 `optimization` 确认为 `run_fast`

## 常见偏差与修法

| 偏差 | 修法 | 对应 troubleshooting |
|-----|------|---------------------|
| 未指定 `--march` | fast-perf 必须指定 march | compile-errors.md |
| 同时指定 `-c` 和 `--fast-perf` | 二者互斥，去掉 `-c` | compile-errors.md |
| 模型不是 `.onnx` 或 `.caffemodel` | fast-perf 仅支持 onnx 和 caffe | compile-errors.md |
| 动态 shape 未指定 `--input-shape` | 使用 `--input-shape` 补全动态维度 | compile-errors.md |
| `--input-shape` 维度长度与模型不匹配 | 确保维度数量与模型输入一致 | compile-errors.md |
| `--core-num` 与 march 不匹配 | 参考 `core_num_range` 合法范围 | compile-errors.md |

## 相关工具 / 模块链接

- **hb_compile**：编译入口，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/hb_compile.py`
- **HBMBuilder**：构建流程，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/compile/hbm_builder.py`
- **ConfigGenerator**：模板生成，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/hb_config_generator.py`
- **YamlBuilder**：YAML 自动生成（fast-perf 内部使用），源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/utils/yaml_builder.py`
- **fast_perf_template.yaml**：模板文件，路径 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/template/fast_perf_template.yaml`
- **完整编译流程**：→ `task-float-to-hbm.md`
- **性能分析**：→ `task-perf-debug.md`
