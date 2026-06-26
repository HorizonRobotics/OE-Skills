# 完整 hb_compile 主流程：ONNX/Caffe → HBM

## 适用场景

**触发关键词**：编译模型、ONNX 转 HBM、完整编译、PTQ、量化、hb_compile

**前置条件**：
- 已安装 `horizon_tc_ui` 工具包（依赖 hbdk4 >= 4.0.22, hmct）
- 已有浮点模型文件（`.onnx` 或 `.caffemodel` + `.prototxt`）
- 已有编译配置 YAML 文件（参考 `task-yaml-authoring.md`）
- 已确认目标芯片 march 架构

## 产出物

| 产物文件 | 路径 | 说明 |
|---------|------|------|
| `{prefix}.hbm` | `{working_dir}/{prefix}.hbm` | 最终编译产物，可部署到板端 |
| `{prefix}.json` | `{working_dir}/{prefix}.json` | 性能分析结果（内存、算子等） |
| `hb_compile.log` | 当前工作目录 + `{working_dir}/` | 完整编译日志（会被复制到 working_dir） |
| `{prefix}_quantized_model.bc` | `{working_dir}/` | 量化后的 HBIR 中间产物 |
| `{prefix}_ptq_model.bc` | `{working_dir}/` |PTQ 导出后的浮点 HBIR（仅 `HORIZON_TC_UI_DEBUG` 模式） |
| `{prefix}_inserted_model.bc` | `{working_dir}/` | 插入预处理节点后的 HBIR（仅 DEBUG 模式） |
| `{prefix}_quantized_removed_model.bc` | `{working_dir}/` | 移除指定节点后的 HBIR（有 remove_node 配置时） |

**命名规则**：`{output_model_file_prefix}` 来自 YAML 配置，默认为 `model`。

## 步骤

### 编译流程总览

hb_compile 的完整流程包含三个阶段（源码 `hbm_builder.py:HBMBuilder.build()`）：

```
ONNX/Caffe → [export] → 浮点 HBIR (.bc)
                      → [convert] → 量化 HBIR (.bc)
                                  → [compile] → HBM (.hbm) + perf (.json)
```

> 如果需要判断已有 .bc 文件是浮点还是定点产物，参见 [detect-bc-type.md](../tips/detect-bc-type.md)

### 步骤 1：标准编译（使用 YAML 配置）

最常用的模式，使用已准备好的 YAML 配置文件：

```bash
hb_compile -c compile_config.yaml
```

这会依次执行 export → convert → compile 三个阶段，最终生成 `.hbm` 文件。

### 步骤 2：fast-perf 模式（快速性能估算）

无需 YAML 配置，直接从模型文件快速编译用于性能评估：

```bash
hb_compile --fast-perf -m model.onnx --march nash-e
```

**带 input_shape**（模型有动态维度时必填）：
```bash
hb_compile --fast-perf -m model.onnx --march nash-e \
  --input-shape input_name 1x3x224x224
```

**指定 BPU 核心数**：
```bash
hb_compile --fast-perf -m model.onnx --march nash-p --core-num 4
```

> fast-perf 模式会自动使用 `fast_perf_template.yaml` 模板，`optimization: run_fast` 跳过校准，`optimize_level: O2`。

### 步骤 3：check 模式（模型检查）

检查模型是否可编译，支持 ONNX/Caffe 模型：

```bash
hb_compile -m model.onnx --march nash-e
```

Caffe 模型：
```bash
hb_compile -m model.caffemodel --proto model.prototxt --march nash-e
```

### 步骤 4：bc_config 模式（从 .bc 重新编译）

已有量化后的 `.bc` 文件，只需重新编译（修改 compiler 参数时无需重新量化）：

```bash
hb_compile -c compile_config.yaml -m quantized_model.bc
```

> 注意：此模式下 `--skip` 参数不生效。

### 步骤 5：分阶段跳过（--skip）

在标准编译模式中，可以跳过特定阶段用于调试：

```bash
# 只执行 export 阶段，生成浮点 HBIR 后停止
hb_compile -c compile_config.yaml --skip convert

# 执行 export + convert，跳过 compile
hb_compile -c compile_config.yaml --skip compile

# 跳过 export（YAML 校验和 PTQ 模型构建仍会执行，但 HBMBuilder.build() 直接返回，不生成任何中间产物）
hb_compile -c compile_config.yaml --skip export
```

**skip 的执行逻辑**（源码 `hbm_builder.py:build()`）：
```python
if skip == "export": return       # 什么都不做
export_model()
if skip == "convert": return      # 只做了 export
convert_model()
node_info()
remove_node()
if skip == "compile": return      # 做了 export + convert
compile_model()
hbm_perf()
print_model_info()
```

### 步骤 6：日志与产物确认

```bash
# 查看编译日志
cat hb_compile.log

# 确认 HBM 产物
ls -lh model_output/*.hbm

# 查看性能报告
cat model_output/model.json

# 查看模型信息
hb_model_info model_output/model.hbm
```

## 校验清单

- [ ] `hb_compile.log` 中出现 `Start hb_compile...` 和 `The hb_compile completes running.`
- [ ] 日志中 `hbdk version` 和 `hmct version` 版本号正常显示
- [ ] 日志中 `Start to export model.` → `Successfully export model.` 配对出现
- [ ] 日志中 `Start to convert model.` → `Successfully convert model.` 配对出现
- [ ] 日志中 `Start to compile model.` → `Successfully compile the hbm model` 配对出现
- [ ] `{working_dir}/{prefix}.hbm` 文件存在且大小合理（> 0 bytes）
- [ ] `{working_dir}/{prefix}.json` 文件存在（perf 结果）
- [ ] `hb_compile.log` 已被复制到 `{working_dir}/` 目录
- [ ] `hb_model_info {prefix}.hbm` 可正常读取模型信息
- [ ] 日志中无 `ERROR` 级别的报错

## 常见偏差与修法

| 偏差 | 修法 | 对应 troubleshooting |
|-----|------|---------------------|
| `--fast-perf` 和 `-c` 同时指定 | 二者互斥，去掉其中一个 | compile-errors.md |
| fast-perf 模式未指定 `--march` | fast-perf 必须指定 march 参数 | compile-errors.md |
| fast-perf 模式传入 `.bc` 或 `.hbm` | fast-perf 仅支持 `.onnx` 和 `.caffemodel` | compile-errors.md |
| check 模式传入非 onnx/caffe 模型 | check 模式仅支持 onnx 和 caffe 模型 | compile-errors.md |
| bc_config 模式传入非 `.bc` 模型 | 该模式仅支持 `.bc` 模型重新编译 | compile-errors.md |
| bc_config 模式缺少 march | 需通过 `-c` 配置或 `--march` 参数指定 | compile-errors.md |
| 编译日志中 `--skip` 不生效 | bc_config 模式下 skip 不生效 | compile-errors.md |
| `core_num` 与 march 不匹配 | 检查 `mapper_consts.core_num_range` 中的合法范围 | compile-errors.md |

## 相关工具 / 模块链接

- **hb_compile**：编译入口，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/hb_compile.py`
- **HBMBuilder**：构建流程核心，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/compile/hbm_builder.py`
- **HBIRHandle**：HBIR 操作封装，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/hbir_handle.py`
- **ParamsParser**：参数校验，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/config/params_parser.py`
- **hb_model_info**：模型信息查看 → `task-model-inspection.md`
- **YAML 编写**：配置文件编写 → `task-yaml-authoring.md`
- **编译失败排查**：→ `task-compile-debug.md`
