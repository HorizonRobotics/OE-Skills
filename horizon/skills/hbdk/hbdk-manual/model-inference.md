---
name: model-inference
description: 支持推理HBIR模型和HBM模型，包括本地推理和远程BPU推理
---


# 代码示例

## 基本推理（HBIR和HBM）
```python
from hbdk4.compiler import load, Hbm
import numpy as np

hbir = load("xxx.bc")
hbm = Hbm("xxx.hbm")

# 准备随机输入，需符合模型输入要求
inputs = {
    v.name: np.random.rand(*v.type.shape).astype(v.type.np_dtype)
    for v in hbir[0].flatten_inputs
}

# HBIR推理
hbir_outputs = hbir[0].feed(inputs)

# HBM推理
hbm_outputs = hbm[0].feed(inputs)

# 也可使用名称访问
# hbir_outputs = hbir["model_name"].feed(inputs)
# hbm_outputs = hbm["model_name"].feed(inputs)
```

## 远程BPU推理
```python
# 运行前需安装 hbdk4_runtime_aarch64 的wheel包
bpu_outputs = hbm[0].feed(
    inputs,
    remote_ip="xxx.horizon.cc",
    remote_port=22,
    remote_work_root="/tmp"
)

# 指定运行核心
bpu_outputs = hbm[0].feed(
    inputs,
    remote_ip="xxx.horizon.cc",
    remote_port=22,
    remote_work_root="/tmp",
    remote_cores=[0, 1]
)
```

## 比较HBIR和HBM输出
```python
for idx, v in enumerate(hbir[0].flatten_outputs):
    hbir_data = hbir_outputs[v.name]
    hbm_data = hbm_outputs[v.name]

    np.testing.assert_equal(
        hbm_data,
        hbir_data,
        "output{} -- {} is not equal".format(idx, v.name),
    )
```

## Pytree类型输入输出推理
```python
# 当模型提供了TreeSpec信息时，支持pytree风格的模型推理
if hbir[0].support_pytree:
    # 使用结构化输入（嵌套dict/list/tuple），按模型定义的pytree结构传入
    tree_input = {"img": np.random.rand(1, 3, 224, 224).astype(np.float32)}
    output = hbir[0](tree_input)  # __call__方式
    # 输出也为模型设置的pytree结构
    result = output["result"].score
```

## HBIR推理内存说明
```python
# 对于HBIR推理，同一graph的结果内存会被复用，后一次推理结果会覆盖前一次
# 如不想复用内存，可在推理前清除xq缓存
hbir[0].clear_xq_cache()
hbir_outputs = hbir[0].feed(inputs)
```

# API参考

## `Module[i].feed(feed_dict) -> Dict[str, np.ndarray]`
HBIR模型推理。
- **feed_dict** (Dict[str, Any]): 输入字典，key为输入名，value为numpy数组

## `Hbm[i].feed(feed_dict, output_dir=None, remote_ip=None, remote_port=22, remote_cores=None, username="root", password="", local_work_path="remote_bpu/", remote_work_root="/tmp/") -> Dict[str, np.ndarray]`
HBM模型推理。
- **feed_dict** (Dict[str, Any]): 输入字典
- **output_dir** (str): 输出目录
- **remote_ip** (str): 远程BPU IP地址
- **remote_port** (int): SSH端口
- **remote_cores** (int|List[int]): 运行核心
- **username** (str): SSH用户名
- **password** (str): SSH密码
- **local_work_path** (str): 本地临时路径
- **remote_work_root** (str): 远程临时路径

## `Module[i].__call__(*args, **kwargs)`
Pytree风格推理（当support_pytree为True时可用）。传入结构化输入，返回结构化输出。

# 注意事项
- 远程BPU推理需安装`hbdk4_runtime_aarch64`的wheel包
- HBIR推理同一graph内存复用，需注意结果覆盖问题
- 输入数据类型和形状需与模型输入要求一致
- remote_port参数类型为int
