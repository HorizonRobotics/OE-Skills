---
name: model-convert
description: 将伪量化HBIR模型转换为指定march的定点模型。convert会根据目标BPU架构对算子进行定点化和算子分配
---


# 代码示例

## 从.bc文件加载已有模块
```python
from hbdk4.compiler import load

exported_module = load("converted.bc")
```

## 基本转换
```python
from hbdk4.compiler import convert, March

converted_module = convert(exported_module, March.nash_e)
```

## 启用advice检查算子分配
```python
# advice=True会输出每个算子的backend分配信息
converted_module = convert(exported_module, March.nash_e, advice=True)

# 输出示例:
# Op "Conv" -> bpu (原因: 支持的卷积算子)
# Op "Shape" -> external_cpu (原因: BPU不支持Shape算子)
```

## 指定advice输出到文件
```python
converted_module = convert(exported_module, March.nash_e, advice=True, advice_path="advice.json")
```

## 使用字符串指定march
```python
converted_module = convert(exported_module, "nash-b")
```

# API参考

## `hbdk4.compiler.load(path) -> Module`
- **path** (str): .bc文件路径
- **返回**: Module对象

## `hbdk4.compiler.convert(m, march, advice=False, advice_path="", **kwargs) -> Module`
- **m** (Module): HBIR模块
- **march** (Union[MarchBase, str]): BPU架构，支持字符串或March枚举
- **advice** (bool): 是否启用算子检查，输出每个算子分配到BPU/CPU的信息及原因
- **advice_path** (str): 算子检查信息保存路径，为空则直接打印
- **返回**: 新的定点化Module（原始Module不被修改）

# March枚举值
| 枚举值 | 说明 | 最大核数 |
|--------|------|----------|
| March.nash_e | Nash-E | 1 |
| March.nash_m | Nash-M | 1 |
| March.nash_p | Nash-P | 4 |
| March.nash_h | Nash-H | 3 |
| March.nash_b | Nash-B (QNX) | 1 |
| March.nash_b_lite | Nash-B Lite (QNX) | 1 |
| March.nash_b_plus | Nash-B Plus (QNX) | 1 |

> "最大核数"是该架构支持的上限。编译时需指定实际使用的核数，不指定则默认1核。perf时的核心数必须与编译时一致。

# advice输出解读
advice=True时，convert会输出JSON格式的算子分配信息：
- **bpu**: 算子在BPU上运行（最优性能）
- **external_cpu**: 算子在外部CPU上运行（需关注性能影响）
- 每个算子会附带分配原因说明

当大量算子分配到external_cpu时，建议检查模型结构或联系算子支持情况。

# 注意事项
- 插入算子（insert_xxx）需在convert之前调用
- advice=True会输出每个算子的backend信息（bpu/external_cpu）及原因
- convert会clone原始Module，不会修改输入Module
- march也支持字符串格式（如"nash-e"），会自动转换为March枚举
