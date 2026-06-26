# YAML 参数参考 — compiler_parameters

> 源码依据：`horizon_tc_ui/config/schema_yaml.py`（schema 定义）
> 校验逻辑：`horizon_tc_ui/config/params_parser.py` → `_validate_compiler_parameters()`
> 常量定义：`horizon_tc_ui/config/mapper_consts.py`

## 完整参数表

| 参数 | 类型 | 默认值 | 必填 | 可选范围 | 说明 |
|------|------|--------|------|----------|------|
| `compile_mode` | str | `latency` | 否 | `bandwidth` / `latency` / `balance` | 编译优化模式。与 `balance_factor` 联动 |
| `balance_factor` | int | `0` | 条件必填 | 0 ~ 100 | 带宽与延迟的平衡因子。`compile_mode=balance` 时必填 |
| `optimize_level` | str | `O2` | 否 | `O0` / `O1` / `O2` | 优化级别（HBDK4 不支持 O3） |
| `core_num` | int | `1` | 否 | 见下方范围 | BPU 核心数，与 march 相关 |
| `max_time_per_fc` | int | `0` | 否 | `0` 或 `1000` ~ `10000000` | 单个全连接层最大编译时间（毫秒）。0 表示不限制 |
| `jobs` | int | `16` | 否 | 正整数 | 编译并行任务数 |
| `advice` | float | `0.0` | 否 | 浮点数 | 编译建议参数 |
| `debug` | bool/str/int | `true` | 否 | bool | 编译调试模式开关 |
| `input_source` | str/dict | `{}` | 否 | `pyramid` / `ddr` / `resizer` | 输入数据来源。与 `input_type_rt` 有兼容性约束 |
| `cache_mode` | str | `disable` | 否 | `enable` / `force_overwrite` / `disable` | 编译缓存模式。与 `cache_path` 联动 |
| `cache_path` | str | `""` | 条件必填 | 目录路径 | 编译缓存目录。`cache_mode` 非 `disable` 时必填 |
| `max_l2m_size` | int/None | `0` | 否 | `0` ~ `25165824`（24M） | L2M 内存最大大小（字节）。nash-b/e/m 系列不支持 |
| `ability_entry` | str | `None` | 否 | 字符串 | 能力入口参数 |
| `extra_params` | dict | `{}` | 否 | 字典 | 额外的编译器参数 |
| `hbdk3_compatible_mode` | bool/str/int | `false` | 否 | - | **已废弃**，指定此参数无效 |

## compile_mode 与 balance_factor 联动

源码位置：`mapper_consts.py` → `compile_mode_list` / `balance_factor_mapping`

| compile_mode | balance_factor 默认值 | 说明 |
|-------------|---------------------|------|
| `latency` | 自动设为 `100` | 延迟优先（默认模式） |
| `bandwidth` | 自动设为 `0` | 带宽优先 |
| `balance` | **必须手动指定** | 平衡模式，不指定 balance_factor 会报错 |

当 `compile_mode` 为 `latency` 或 `bandwidth` 时，如果手动指定了 `balance_factor`，
系统会发出警告并忽略手动指定的值。

源码：`params_parser.py` → `_validate_balance_factor()` L1020-L1043

## optimize_level

源码位置：`mapper_consts.py` → `optimize_level_hbdk4`

HBDK4 仅支持：`O0`, `O1`, `O2`

| 级别 | 说明 |
|------|------|
| `O0` | 无优化（调试用，编译最快） |
| `O1` | 基础优化 |
| `O2` | 完全优化（默认，推理性能最佳） |

**注意**：`O3` 在 HBDK4 中不可用（`mapper_consts.py` → `optimize_level` 包含 O3 但 `optimize_level_hbdk4` 不包含）。

## core_num 与 march 的关系

源码位置：`mapper_consts.py` → `core_num_range`

| march | 支持的 core_num |
|-------|----------------|
| `nash-b-lite` | `[1]` |
| `nash-b` | `[1]` |
| `nash-b-plus` | `[1]` |
| `nash-e` | `[1]` |
| `nash-m` | `[1]` |
| `nash-h` | `[1, 2, 3, 4]` |
| `nash-p` | `[1, 2, 3, 4]` |
| `nash-starry-p` | `[1, 2, 3, 4]` |

源码：`params_parser.py` → `_validate_core_num()` L975-L992

## input_source 与 input_type_rt 兼容性

源码位置：`mapper_consts.py` → `input_source_support_dict`

| input_source | 支持的 input_type_rt |
|-------------|---------------------|
| `pyramid` | `nv12`, `gray`, `yuv420sp_bt601_video`, `yuv_bt601_full` |
| `ddr` | `rgb`, `bgr`, `yuv444`, `yuv444_128`, `gray`, `featuremap` |
| `resizer` | `nv12`, `gray`, `yuv420sp_bt601_video`, `yuv_bt601_full` |

当未显式指定 `input_source` 时，系统会根据 `input_type_rt` 自动选择默认值：
- 如果 `input_type_rt` 在 pyramid 支持列表中 → 默认 `pyramid`
- 否则 → 默认 `ddr`

`input_source` 以字典格式按输入名称分别指定：
```yaml
input_source:
  input_0: pyramid
  input_1: ddr
```

源码：`params_parser.py` → `_validate_input_source()` L919-L963

## cache_mode 与 cache_path 联动

源码位置：`mapper_consts.py` → `cache_mode_list`

| cache_mode | 说明 | cache_path 要求 |
|-----------|------|----------------|
| `disable` | 不使用缓存（默认） | 不需要指定；若指定会发出警告并自动改为 `enable` |
| `enable` | 启用缓存 | **必须指定**有效目录 |
| `force_overwrite` | 强制覆盖缓存 | **必须指定**有效目录 |

源码：`params_parser.py` → `_validate_cache_mode()` L275-L292

## max_l2m_size

- 有效范围：`0` ~ `25165824`（24MB）
- `0` 或 `None` 表示不限制
- **nash-b**、**nash-e**、**nash-m** 系列芯片不支持此参数

源码：`params_parser.py` → `_validate_max_l2m_size()` L994-L1009

## 已废弃参数

| 参数 | 废弃原因 |
|------|---------|
| `hbdk3_compatible_mode` | HBDK3 兼容模式已移除，指定无效 |

源码：`params_parser.py` → `_validate_deprecated_params()` L1096-L1100

## 典型错误

| 错误片段 | 原因 | 修法 |
|---------|------|------|
| `The specified compile_mode Xxx is invalid` | compile_mode 不在合法列表中 | 使用 `bandwidth`/`latency`/`balance` |
| `Parameter compile_mode is set to balance, please set balance_factor` | balance 模式未指定 balance_factor | 设置 0~100 的 balance_factor |
| `The specified balance_factor Xxx is invalid, range 0-100` | balance_factor 超出范围 | 设置为 0~100 |
| `The specified optimize_level 'Xxx' is invalid` | optimize_level 不在 HBDK4 支持列表中 | 使用 `O0`/`O1`/`O2` |
| `Wrong core_num Xxx specified` | core_num 与 march 不兼容 | 参考上方 core_num 范围表 |
| `The specified max_time_per_fc is invalid, range 0 or 1000-10000000` | max_time_per_fc 超出有效范围 | 设为 0 或 1000~10000000 |
| `The input_type_rt Xxx does not support input_source Yyy` | input_source 与 input_type_rt 不兼容 | 参考上方兼容性表 |
| `The specified cache_mode Xxx is invalid` | cache_mode 不在合法列表中 | 使用 `enable`/`force_overwrite`/`disable` |
| `The cache_path must be specified when the cache_mode is not disable` | 非 disable 模式未指定 cache_path | 指定有效的缓存目录 |
| `The specified cache_path Xxx does not exist` | cache_path 目录不存在 | 创建目录 |
| `The specified max_l2m_size Xxx is invalid, range 0-25165824` | max_l2m_size 超出范围 | 设置为 0~25165824 |
| `The specified march Xxx does not support setting max_l2m_size` | nash-b/e/m 不支持 max_l2m_size | 移除此参数 |
