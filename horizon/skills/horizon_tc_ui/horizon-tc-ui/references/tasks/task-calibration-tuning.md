# 精度掉点时的 Calibration 调优

## 适用场景

**触发关键词**：精度掉点、校准、calibration、量化精度、cosine 低、kl、max、percentile、per_channel、quant_config

**前置条件**：
- 已完成一次完整编译并生成 HBM
- 已通过 hb_verifier 或板端推理确认精度不达标
- 已有校准数据集目录（`cal_data_dir`）

## 产出物

| 产出物 | 路径 | 说明 |
|-------|------|------|
| 更新后的 YAML | 用户指定 | 调整 calibration_parameters 后的配置 |
| 重新编译的 HBM | `{working_dir}/{prefix}.hbm` | 调优后的编译产物 |
| 校准中间数据 | `{cal_data_dir}/` | 校准数据集（.npy 格式） |

## 步骤

### Calibration 决策树

```
精度不达标
├── 所有输出都掉点
│   ├── 校准数据是否合理？ → 检查 cal_data_dir 数据分布
│   ├── 校准方法是否合适？ → 尝试 kl → max（配合 max_percentile 调整）
│   └── 是否开启 per_channel？ → 尝试开启 per_channel: true
│
├── 部分输出掉点
│   ├── 特定层掉点？ → 使用 quant_config 逐层配置
│   ├── 特定输入掉点？ → 检查该输入的 cal_data_dir
│   └── 特定通道掉点？ → 开启 per_channel: true
│
└── 个别样本掉点
    ├── 校准数据覆盖不足？ → 增加 cal_data_dir 样本量
    └── 异常样本干扰？ → 清理校准数据集中的异常样本
```

### 步骤 1：选择校准方法

在 YAML 的 `calibration_parameters` 中配置 `calibration_type`：

```yaml
calibration_parameters:
  calibration_type: kl    # 校准方法
```

**校准方法对比**（源码 `mapper_consts.py`）：

| 方法 | 适用场景 | 说明 |
|-----|---------|------|
| `kl` | 通用推荐 | KL 散度最小化，大多数场景首选 |
| `max` | 极端值敏感模型 | 使用激活值最大范围，适合对极端值敏感的模型 |
| `mix` | 已废弃 | 不推荐使用 |
| `default` | 已废弃 | 不推荐使用 |
| `skip` | 跳过校准 | 不做量化校准（fast-perf 模式自动使用） |

**推荐尝试顺序**：`kl` → `max`（配合 `max_percentile` 调整截断比例）

### 步骤 2：使用 max_percentile 调整范围

当 `max` 方法过激时，使用 `max_percentile` 控制截断比例：

```yaml
calibration_parameters:
  calibration_type: max
  max_percentile: 0.9999    # 取值范围 [0.5, 1.0]，默认值 1.0
```

> `max_percentile` 值越小，截断越激进。常用值：`0.9999`, `0.999`, `0.99`。

### 步骤 3：开启 per_channel

对于某些通道敏感的模型（如检测头、分割头），开启逐通道校准：

```yaml
calibration_parameters:
  calibration_type: kl
  per_channel: true    # 默认 false
```

> **何时开启**：当整体 cosine 尚可但个别输出 tensor 掉点严重时，优先尝试开启 per_channel。

### 步骤 4：准备校准数据

```yaml
calibration_parameters:
  cal_data_dir: ./calibration_data_dir    # 单输入
  # cal_data_dir: ./cal_data_dir_0;./cal_data_dir_1    # 多输入（分号分隔）
```

**校准数据要求**：
- 格式：`.npy` 文件（支持 `uint8` 或 `float32` 类型）
- 目录命名：建议以 `_uint8` 或 `_f32` 结尾（影响 `cal_data_type` 自动识别）
- 数量：推荐 100-500 张，覆盖实际推理场景
- 内容：与训练数据分布一致的预处理后数据

**多输入模型**（每个输入节点一个目录）：
```yaml
calibration_parameters:
  cal_data_dir: ./cal_data_image;./cal_data_feature
```

### 步骤 5：使用 quant_config 精细控制

对于需要逐层调整的场景，使用 `quant_config`。`quant_config` 支持在 `model_config`、`op_config`、`subgraph_config`、`node_config` 四个层面配置量化参数，优先级从小到大：`model_config < op_config < subgraph_config < node_config`。

**方式一：引用 JSON 配置文件**：
```yaml
calibration_parameters:
  calibration_type: kl
  quant_config: quant_config.json    # 引用外部 JSON 文件
```

**方式二：直接在 YAML 中配置**（dict 格式）：
```yaml
calibration_parameters:
  calibration_type: kl
  quant_config:
    model_config:
      default:
        activation:
          calibration_type: max
          per_channel: true
    node_config:
      "/model/layer/Conv_0":
        activation:
          calibration_type: kl
```

> `quant_config` 允许对特定层/算子覆盖全局校准配置。注意：由于编译过程中会对部分算子进行拆分融合，`node_config` 中的算子名称应参考 `optimized_float_model.onnx` 中的名称。

### 步骤 6：使用 run_on_cpu / run_on_bpu 控制算子部署

将精度敏感的算子放到 CPU 执行（非 bernoulli2 架构）：

```yaml
calibration_parameters:
  run_on_cpu: "Conv_0;MatMul_1"    # 指定在 CPU 上运行的算子名
  run_on_bpu: "Conv_2"             # 指定在 BPU 上运行的算子名
```

> 也可以使用 `node_info` 参数（优先级更高）：
> ```yaml
> model_parameters:
>   node_info: "Conv_0:int16;Conv_1:int16"
> ```

### 步骤 7：重新编译并验证

```bash
# 使用更新后的配置重新编译
hb_compile -c updated_config.yaml

# 验证精度
hb_verifier -m model.onnx,model_output/model.hbm -i input_data.bin
```

## 校验清单

- [ ] `calibration_type` 在合法列表中（`kl`, `max`, `skip`，已废弃的 `mix`, `default` 不推荐使用）
- [ ] `max_percentile` 在 [0.5, 1.0] 范围内（如使用）
- [ ] `per_channel` 为布尔值（`true` 或 `false`）
- [ ] `cal_data_dir` 目录存在且包含 `.npy` 文件
- [ ] 多输入模型时，`cal_data_dir` 数量与输入节点数一致
- [ ] `quant_config` 中的层名在模型中存在
- [ ] `run_on_cpu` / `run_on_bpu` 的算子名在模型中存在
- [ ] 编译日志中校准阶段无报错
- [ ] 日志中 `calibration_type` 确认使用了预期方法
- [ ] 重新验证后精度指标达到预期

## 常见偏差与修法

| 偏差 | 修法 | 对应 troubleshooting |
|-----|------|---------------------|
| `calibration_type` 值不合法 | 使用 `kl`, `max`, `skip` 之一（`mix`, `default` 已废弃） | calibration-errors.md |
| `max_percentile` 超出 [0.5, 1.0] 范围 | 调整为 0.5~1.0 之间的浮点数 | calibration-errors.md |
| `cal_data_dir` 目录不存在 | 创建目录并放入校准数据 | calibration-errors.md |
| `cal_data_dir` 数量与输入不匹配 | 多输入需要分号分隔多个目录 | calibration-errors.md |
| `run_on_cpu` 与 `node_info` 冲突 | `node_info` 优先级更高，统一使用一种方式 | calibration-errors.md |
| `scale_value` 和 `std_value` 同时指定 | 只能二选一 | yaml-schema-errors.md |
| 校准数据格式不正确 | 确保使用 `.npy` 格式 | calibration-errors.md |

## 相关工具 / 模块链接

- **ParamsParser**：校准参数校验，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/config/params_parser.py`
  - `_validate_calibration_type()` - 校准方法校验
  - `_validate_cal_data_dir()` - 校准数据目录校验
  - `_validate_per_channel()` - per_channel 校验
  - `_validate_max_percentile()` - percentile 校验
- **mapper_consts**：校准相关常量定义，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/config/mapper_consts.py`
  - `autoq_caltype_list` = [`kl`, `max`, `mix`, `default`]
  - `preq_caltype_list` = [`skip`]
- **schema_yaml**：YAML Schema 定义，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/config/schema_yaml.py`
- **hb_verifier**：精度验证 → `task-board-deploy-verify.md`
- **精度分析**：→ `task-accuracy-debug.md`
