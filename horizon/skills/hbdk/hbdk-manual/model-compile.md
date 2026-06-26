---
name: model-compile
description: 将定点化HBIR模型编译为HBM文件，支持直接编译HBM或先编译HBO再链接
---


# 编译路径选择
- **直接编译HBM**：简单场景，内部会先编译HBO再自动link
- **先编译HBO再link**：需要多模型打包，或需要对单个HBO做额外处理时使用

# 代码示例

## 方式一：直接编译为HBM
```python
from hbdk4.compiler import convert, compile, March

converted_module = convert(exported_module, March.nash_e)
hbm = compile(converted_module, "deploy.hbm", March.nash_e, 0)
```

## 方式二：先编译HBO再链接HBM
```python
from hbdk4.compiler import convert, compile, link, March

converted_module = convert(exported_module, March.nash_e)
hbo = compile(converted_module, "deploy.hbo", March.nash_e, 0)
hbm = link([hbo], "deploy.hbm")
```

## 多模型打包
```python
from hbdk4.compiler import compile, link, March
from hbdk4.compiler.hbm import Hbo

hbo1 = compile(converted_module_1, "model1.hbo", March.nash_e, 0)
hbo2 = compile(converted_module_2, "model2.hbo", March.nash_e, 0)
hbm = link([hbo1, hbo2], "packed.hbm")

# 也可从已有HBO文件打包
hbo1 = Hbo("model1.hbo")
hbo2 = Hbo("model2.hbo")
hbm = link([hbo1, hbo2], "packed.hbm")
```

## 带编译选项
```python
hbm = compile(
    converted_module, "deploy.hbm", March.nash_e, 0,
    progress_bar=True,
    advice=0.01,
    balance=2,
    debug=False,
    jobs=4,
)
```

## 使用L2M优化
```python
# 让编译器自动决定L2M使用量
hbm = compile(converted_module, "deploy.hbm", March.nash_e, max_l2m_size=None)

# 限制L2M最大使用量（bytes）
hbm = compile(converted_module, "deploy.hbm", March.nash_e, max_l2m_size=1024*1024)
```

## 使用增量编译缓存
```python
from hbdk4.compiler import CacheMode

# 启用缓存，增量编译时跳过未变化的算子
hbm = compile(
    converted_module, "deploy.hbm", March.nash_e,
    cache_mode=CacheMode.enable,
    cache_path="./cache"
)
```

# API参考

## `hbdk4.compiler.compile(m, path, march, opt=2, jobs=4, max_time_per_fc=0.0, debug=False, progress_bar=False, advice=0.0, balance=100, input_no_padding=False, output_no_padding=False, cache_mode="disable", cache_path="", max_l2m_size=0, **kwargs) -> Union[Hbm, Hbo]`
- **m** (Module): HBIR模块
- **path** (str): 输出路径，.hbm或.hbo结尾
- **march** (Union[MarchBase, str]): BPU架构
- **opt** (int): 优化级别，默认2
- **jobs** (int): 编译线程数，默认4
- **max_time_per_fc** (float): 单个funccall最大时间约束(μs)，范围1000~10000000
- **debug** (bool): 是否包含调试信息（用于详细perf分析）
- **progress_bar** (bool): 是否显示进度条
- **advice** (float): 输出耗时超过指定时间(μs)的算子建议
- **balance** (int): 平衡cycles和DDR访问，0(最小DDR)~100(最小cycles)
- **input_no_padding** (bool): 模型输入是否无padding
- **output_no_padding** (bool): 模型输出是否无padding
- **cache_mode** (Union[CacheModeBase, str]): 缓存模式，"disable"/"enable"/"force_overwrite"
- **cache_path** (str): 缓存文件路径
- **max_l2m_size** (int|None): L2M大小限制(bytes)，0=不使用，None=编译器自动决定，N=不超过N

## `hbdk4.compiler.link(hbo_list, output_path, desc=None) -> Hbm`
- **hbo_list** (List[Hbo]): HBO对象列表
- **output_path** (str): 输出HBM路径，必须.hbm结尾
- **desc** (str, optional): HBM描述信息
