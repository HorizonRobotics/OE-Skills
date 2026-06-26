# 编译失败排查

## 适用场景

**触发关键词**：编译失败、OP 不支持、shape 推导失败、convert 失败、compile 失败、export 失败、hbdk 报错

**前置条件**：
- 已执行 `hb_compile` 命令并报错
- 已有 `hb_compile.log` 日志文件

## 产出物

| 产物 | 说明 |
|-----|------|
| `hb_compile.log` | 完整编译日志，包含错误栈 |
| 失败阶段的中间产物 | 用于定位问题 |
| 排查报告 | 问题根因和修法建议 |

## 步骤

### 系统化排查路径

```
编译失败
├── 1. 确定失败阶段（export / convert / compile）
│   ├── 搜索日志 "Start to export" / "Start to convert" / "Start to compile"
│   └── 找到最后一个 "Start to" 但没有对应 "Successfully" 的阶段
│
├── 2. 根据失败阶段定位问题
│   ├── export 失败 → 模型解析问题、ONNX 格式问题
│   ├── convert 失败 → OP 不支持、shape 推导失败、量化问题
│   └── compile 失败 → 编译器内部错误、内存不足、超时
│
├── 3. 查看具体错误信息
│   ├── 搜索 "ERROR" 关键字
│   ├── 搜索 "ValueError" / "RuntimeError" 关键字
│   └── 查看 Python 异常栈
│
└── 4. 针对性修复
    ├── OP 不支持 → 使用 remove_node / node_info / run_on_cpu
    ├── shape 推导失败 → 检查 input_shape 配置
    └── 编译器错误 → 调整 optimize_level / max_time_per_fc
```

### 步骤 1：确定失败阶段

```bash
# 查看日志中的阶段标记
grep -n "Start to\|Successfully\|ERROR\|ValueError\|RuntimeError" hb_compile.log
```

典型输出：
```
123: Start to export model.
145: Successfully export model.
146: Start to convert model.
234: ERROR: ...
```

上面的例子说明失败在 convert 阶段。

### 步骤 2：export 阶段失败排查

**常见原因**：
- ONNX 模型格式不兼容或版本问题
- ONNX opset 版本不支持
- 模型中存在无法解析的算子

**排查命令**：
```bash
# 检查 ONNX 模型是否可正常加载
hb_model_info model.onnx

# 检查 ONNX opset 版本
python3 -c "
import onnx
model = onnx.load('model.onnx')
print('opset:', model.opset_import[0].version)
"
```

### 步骤 3：OP 不支持排查

convert 阶段最常见的错误是 OP 不支持。

**查看日志中的 OP 信息**：
```bash
# 搜索不支持的 OP
grep -i "unsupported\|not support\|unregistered" hb_compile.log
```

**使用 DEBUG 模式保留中间产物**：
```bash
export HORIZON_TC_UI_DEBUG=1
hb_compile -c compile_config.yaml --skip convert

# 查看浮点 HBIR 的算子信息
hb_model_info model_output/model_ptq_model.bc
```

**修法**：

1. **使用 remove_node 移除多余节点**（仅支持特定类型）：
```yaml
model_parameters:
  remove_node_type: Quantize;Transpose;Dequantize;Cast;Reshape;Softmax
```

> 支持移除的节点类型（源码 `mapper_consts.removal_list`）：`Quantize`, `Transpose`, `Dequantize`, `Cast`, `Reshape`, `Softmax`

2. **使用 node_info 指定算子运行位置**：
```yaml
model_parameters:
  node_info: "UnsupportedOp_0:cpu"
```

3. **使用 run_on_cpu 指定算子在 CPU 运行**（非 bernoulli2 架构）：
```yaml
calibration_parameters:
  run_on_cpu: "OpName_0;OpName_1"
```

### 步骤 4：shape 推导失败排查

**常见原因**：
- `input_shape` 配置与模型不匹配
- 模型有动态维度但 `input_shape` 未指定
- `input_shape` 格式错误（如使用 `,` 而非 `x` 分隔）

**排查命令**：
```bash
# 查看模型真实输入 shape
hb_model_info model.onnx

# 检查 YAML 中的 input_shape 配置
grep "input_shape" compile_config.yaml
```

**修法**：
```yaml
input_parameters:
  input_shape: '1x3x224x224'    # 使用 x 分隔，不要用逗号
```

**动态 shape 模型**：
- 如果模型输入有 `?`、`-1` 或 `0` 等动态维度
- 必须在 YAML 中显式指定 `input_shape`
- fast-perf 模式使用 `--input-shape` 参数

### 步骤 5：compile 阶段失败排查

**常见原因**：
- 编译器超时（`max_time_per_fc` 设置过小）
- 内存不足
- optimize_level 过高导致编译器内部错误

**修法**：

1. **增加编译超时时间**：
```yaml
compiler_parameters:
  max_time_per_fc: 10000000    # 最大允许值 10000000，0 表示不限制
```

2. **降低优化级别**：
```yaml
compiler_parameters:
  optimize_level: O1    # 从 O2 降到 O1 或 O0
```

3. **调整编译模式**：
```yaml
compiler_parameters:
  compile_mode: latency    # 尝试 bandwidth 或 balance
```

4. **减少 BPU 核心数**：
```yaml
compiler_parameters:
  core_num: 1    # 减少核心数降低编译复杂度
```

### 步骤 6：使用分阶段编译定位

```bash
# 只跑 export
hb_compile -c compile_config.yaml --skip convert

# 跑 export + convert
hb_compile -c compile_config.yaml --skip compile

# 全量编译
hb_compile -c compile_config.yaml
```

通过逐步放开 skip，精确定位失败阶段。

### 步骤 7：日志关键字定位

| 关键字 | 含义 | 可能原因 |
|-------|------|---------|
| `Start to export` | export 阶段开始 | - |
| `Successfully export` | export 阶段成功 | - |
| `Start to convert` | convert 阶段开始 | - |
| `Successfully convert` | convert 阶段成功 | - |
| `Start to compile` | compile 阶段开始 | - |
| `Successfully compile` | compile 阶段成功 | - |
| `ValueError` | Python 参数校验错误 | 配置参数不合法 |
| `RuntimeError` | 运行时错误 | 编译器内部错误 |
| `unsupported` | OP 不支持 | 算子不在支持列表 |
| `not support` | 不支持的操作 | 参数组合不合法 |
| `shape` | shape 相关错误 | 维度推导失败 |
| `timeout` | 编译超时 | max_time_per_fc 过小 |
| `memory` | 内存问题 | 系统内存不足 |

## 校验清单

- [ ] `hb_compile.log` 文件存在且包含完整日志
- [ ] 已确定失败阶段（export / convert / compile）
- [ ] 已搜索日志中的 ERROR / ValueError / RuntimeError 关键字
- [ ] 如为 OP 不支持，已确认具体 OP 名称和类型
- [ ] 如为 shape 推导失败，已对比模型真实 shape 和 YAML 配置
- [ ] 如为 compile 阶段失败，已尝试降低 optimize_level
- [ ] 已使用 `hb_model_info` 确认模型输入信息
- [ ] 已使用 `--skip` 分阶段验证定位问题

## 常见偏差与修法

| 偏差 | 修法 | 对应 troubleshooting |
|-----|------|---------------------|
| ONNX opset 版本不兼容 | 检查并转换 opset 版本 | compile-errors.md |
| input_shape 格式错误 | 使用 `x` 分隔维度，不用逗号 | yaml-schema-errors.md |
| 动态 shape 未指定 | 显式配置 input_shape | compile-errors.md |
| OP 不支持 | 使用 run_on_cpu / remove_node / node_info | compile-errors.md |
| 编译超时 | 增大 max_time_per_fc（最大 10000000） | compile-errors.md |
| 编译器内存不足 | 降低 optimize_level 或减少 input_batch | compile-errors.md |
| core_num 与 march 不匹配 | 参考 core_num_range 合法范围 | compile-errors.md |
| optimize_level 值不合法 | HBDK4 仅支持 O0/O1/O2 | compile-errors.md |

## 相关工具 / 模块链接

- **hb_compile**：编译入口，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/hb_compile.py`
- **HBMBuilder**：构建流程，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/compile/hbm_builder.py`
- **HBIRHandle**：HBIR 操作，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/hbir_handle.py`
  - `convert_quantize_model()` - convert 阶段入口
  - `compile_model()` - compile 阶段入口
  - `check_cpu_ops()` - 检查 CPU 算子
  - `statistics()` - 算子统计
- **ParamsParser**：参数校验，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/config/params_parser.py`
- **hb_model_info**：模型信息查看 → `task-model-inspection.md`
- **mapper_consts**：常量定义（OP 移除列表等），源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/config/mapper_consts.py`
