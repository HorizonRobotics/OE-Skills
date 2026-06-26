# HBDK4 API 参考

## 核心API导入

```python
from hbdk4.compiler import (
    load, save, convert, compile, link,
    statistics, visualize, March, CacheMode,
    Module, Hbm
)
from hbdk4.compiler.onnx import export, statistics as onnx_statistics
from hbdk4.compiler.hbm_tools import hbm_perf, hbm_pack
from hbdk4.compiler.overlay import PrecisionConfig
from hbdk4.compiler.remote_bpu import RemoteBPU
```

## 模型导出

### `hbdk4.compiler.onnx.export(proto, *, name=None) -> Module`
将ONNX模型导出为HBIR MLIR。
- **proto** (onnx.ModelProto): onnx protobuf
- **name** (Optional[str]): 函数名

### `hbdk4.compiler.onnx.statistics(proto)`
打印ONNX模型op统计。

## 模型加载与保存

### `load(path: str) -> Module`
加载.bc/.mlir文件为Module对象。

### `save(m: Module, path: str) -> None`
将Module序列化为bytecode文件。path必须以".bc"结尾。

### `Module.parse(asm: str) -> Module`
从MLIR文本解析Module。

## 模型转换与编译

### `convert(m: Module, march, advice=False, advice_path="", **kwargs) -> Module`
将HBIR转为后端IR。
- **march**: "nash-e", "nash-m", "nash-p", "nash-h", "nash-b", "nash-b-lite", "nash-b-plus"
- **advice**: 是否启用op check

### `compile(m: Module, path: str, march, opt=2, jobs=4, ...) -> Union[Hbm, Hbo]`
编译为HBM或HBO。
- **opt**: 优化级别(0-2)
- **jobs**: 编译线程数
- **balance**: DDR与cycles平衡(0-100)
- **debug**: 是否包含debug信息
- **max_time_per_fc**: 单funccall最大时间(μs)
- **input_no_padding/output_no_padding**: 输入输出是否无padding
- **cache_mode**: "disable", "enable", "force_overwrite"
- **max_l2m_size**: L2M大小限制(bytes)，0=不使用，None=自动

### `link(hbo_list: List[Hbo], output_path: str, desc=None) -> Hbm`
链接HBO列表为HBM。

## 可视化与统计

### `statistics(m: Module, expand_fusion: bool = True) -> list`
打印模型op统计信息。

### `visualize(m, onnx_file=None, use_netron=False, host=None, port=None, save_as_external_data=False, external_data_file=None)`
生成可视化ONNX文件。

## Module属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `graphs` / `functions` | List[Function] | 所有function |
| `version` | str\|None | HBDK导出版本号 |
| `march` | March\|None | BPU架构（convert前为None） |
| `precision_config` | Dict[str, PrecisionConfig] | 精度配置，key为算子OriginalName |

### `Module[i]` / `Module["name"]`
按索引或名称访问Function。

## Function属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `flatten_inputs` | List[Argument] | 扁平化输入列表 |
| `flatten_outputs` | List[Argument] | 扁平化输出列表 |
| `operations` | List[Operation] | 所有算子 |
| `support_pytree` | bool | 是否支持pytree查询 |
| `desc` | str | 描述 |

### `Function.remove_io_op(op_types=None, op_names=None)`
按类型/名称删除节点。支持类型: Dequantize, Quantize, Transpose, FilterCopy, Cast, Reshape, Softmax, RlePostProcess。

### `Function.extract_function(input_names, output_names) -> Module`
提取子图。

## Argument操作API

### 插入节点（convert前调用）
- `insert_image_convert(mode="nv12")`: 插入pyramid输入。mode: "nv12"/"gray"/"nv12_yh12"/"nv12_yh10"
- `insert_image_preprocess(mode, divisor, mean, std, is_signed, bit_width, image_layout)`: 插入预处理。mode: "skip"/"yuvbt601full2rgb"/"yuvbt601full2bgr"/"yuvbt601video2rgb"/"yuvbt601video2bgr"/"bgr2rgb"/"rgb2bgr"
- `insert_roi_resize(mode, interp_mode, pad_mode, pad_value)`: 插入ROI resize。mode: "nv12"/"gray"/"nv12_yh12"/"nv12_yh10"
- `insert_transpose(permutes)`: 插入转置。permutes[i]=原维度i放到新维度permutes[i]，注意与numpy.transpose是逆映射
- `insert_split(dim)`: 插入拆分

### 插入节点（convert后调用）
- `insert_rle()`: 插入RLE编码（需先删除Dequantize）

### 删除节点
- `is_removable`: 检查是否可删除 -> Tuple[bool, str]
- `get_attached_op`: 获取相邻op -> List[Operation]
- `remove_attached_op()`: 删除相邻op -> Tuple[bool, str]
- `erase()`: 删除参数本身 -> Tuple[bool, str]

## HBM操作

### `Hbm(hbm_file_name: str)`
加载HBM文件。
- `.graphs` / `.functions`: 图列表
- `.desc`: 描述信息
- `.staged_desc` / `staged_name`: 暂存修改
- `.save_by_staged_info(filename)`: 保存修改
- `.march`: March信息
- `.toolkit_version`: 版本信息
- `[index_or_name]`: 按索引或名称访问图

### `hbm_perf(model, ...)`
HBM性能分析。不指定remote_ip为静态perf，指定remote_ip为动态perf。

### `Hbm[i].feed(feed_dict, ...)` / `Hbm[i](...)`
HBM模型推理。

## RemoteBPU

### `RemoteBPU(hbm, march, ip, port=22, cores=None, ...)`
远程BPU执行器，用于在远程BPU板上运行模型。
- 支持Linux和QNX系统
- 自动检测架构（aarch64/riscv64/x86_64）

## PrecisionConfig枚举

| 值 | 说明 |
|----|------|
| PrecisionConfig.KEEP_FLOAT | 保持浮点运算 |
| PrecisionConfig.HIGH_PRECISION_QPP | 高精度量化后处理 |

## March枚举

| March值 | 说明 | 核数 |
|---------|------|------|
| March.nash_e | Nash-E | 1 |
| March.nash_m | Nash-M | 1 |
| March.nash_p | Nash-P | 4 |
| March.nash_h | Nash-H | 3 |
| March.nash_b | Nash-B (QNX) | 1 |
| March.nash_b_lite | Nash-B Lite (QNX) | 1 |
| March.nash_b_plus | Nash-B Plus (QNX) | 1 |

## CacheMode枚举

| CacheMode值 | 说明 |
|-------------|------|
| CacheMode.disable | 禁用缓存 |
| CacheMode.enable | 启用缓存 |
| CacheMode.force_overwrite | 强制覆盖缓存 |
