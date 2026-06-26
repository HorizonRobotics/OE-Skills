---
name: hbm-perf
description: 对HBM模型进行性能分析，包括静态perf和动态perf（远程BPU板端推理），以及基于JSON报告的逐层瓶颈分析
---


> 如果看更详细的信息，需要设置编译选项debug=True。
> 静态perf为编译期估算值，**上板动态perf更准确**。如需上板perf，请提供BPU板端的IP和SSH端口。

# 代码示例

## 静态性能评估
```python
from hbdk4.compiler import hbm_perf

# 静态perf，打印FPS、latency和DDR数据量，生成HTML报告
hbm_perf("deploy.hbm")
```

## 动态性能评估（远程BPU）
```python
from hbdk4.compiler import hbm_perf
import numpy as np

# 准备输入
inputs = {
    v.name: np.random.rand(*v.type.shape).astype(v.type.np_dtype)
    for v in hbm[0].flatten_inputs
}

# 动态perf：远程连接BPU推理
hbm_perf("deploy.hbm",
         remote_ip="xxx.xxx.xxx.xxx",
         remote_port=22,
         remote_work_root="/tmp/",
         inputs=inputs)

# 指定运行核心
hbm_perf("deploy.hbm",
         remote_ip="xxx.xxx.xxx.xxx",
         remote_port=22,
         remote_work_root="/tmp/",
         remote_cores=[0, 1],
         inputs=inputs)
```

## 查询HBM基本信息
```python
from hbdk4.compiler import Hbm

hbm = Hbm("deploy.hbm")  # 注意：Hbm()加载.hbm文件；load()只能加载.bc文件

# 模型元信息
print(f"March: {hbm.march_name}")          # 如 nash-p
print(f"HBDK version: {hbm.toolkit_version}")

# 图信息
g = hbm.graphs[0]
print(f"Graph name: {g.name}")              # 如 resnet50
print(f"Num cores: {g.num_cores}")          # BPU核心数

# 输入输出
for inp in g.flatten_inputs:
    print(f"Input: name={inp.name}, shape={inp.type.shape}, dtype={inp.type.np_dtype}")
for out in g.flatten_outputs:
    print(f"Output: name={out.name}, shape={out.type.shape}, dtype={out.type.np_dtype}")
```

## 节点级性能查询（无需生成报告）
```python
from hbdk4.compiler import Hbm

hbm = Hbm("deploy.hbm")
g = hbm.graphs[0]

# 遍历BPU节点，获取预估延迟和设备类型
for node in g.nodes:
    print(f"Node: {node.name}")
    print(f"  Device: {node.device}")                       # DeviceCategory.Bpu / Cpu
    print(f"  Estimated latency: {node.estimated_latency_micros} us")

# 查看节点内存布局
for node in g.nodes:
    for ms in node.memspaces:
        print(f"  Memspace: name={ms.name}, size={ms.size}, usage={ms.usage}")
    for v in node.variables:
        print(f"  Variable: name={v.name}, shape={v.type.shape}, offset={v.offset_in_memspace}")
```

## 生成并解析JSON性能报告
```python
from hbdk4.compiler import hbm_perf
import json

# 指定output_dir会同时生成HTML和JSON报告
hbm_perf("deploy.hbm", output_dir="./perf_report/")

# 加载JSON报告进行逐层分析
with open("./perf_report/resnet50.json") as f:
    report = json.load(f)

summary = report["summary"]
perf = summary["performance"]
ddr = summary["DDR access data"]
layers = summary["layer details"]
model_info = summary["model info"]
interval = summary["interval info"]
```

## 逐层瓶颈分析方法

### 1. 整体性能概览
```python
perf = report["summary"]["performance"]
ddr = report["summary"]["DDR access data"]

print(f"FPS: {perf['FPS']}")
print(f"延迟: {perf['latency (us)']} us ({perf['latency (ms)']} ms)")
print(f"DDR访问量: {ddr['DDR megabytes per run']} MB/run")
print(f"DDR读取: {ddr['loaded bytes per run']} bytes/run")
print(f"DDR写入: {ddr['stored bytes per run']} bytes/run")
print(f"最小内存需求: {ddr['min memory requirement']} bytes")
print(f"计算量: {model_info['original conv ops']} ({model_info['original conv ops']/1e9:.2f} GOPS)")
```

### 2. 计算单元利用率分析
```python
interval = report["summary"]["interval info"]
utilizations = interval["interval computing unit utilization"]
ddr_load_bw = interval["interval ddr loading bandwidth (megabytes/s)"]
ddr_store_bw = interval["interval ddr storing bandwidth (megabytes/s)"]

# 利用率高的区间说明计算bound，低的区间说明DDR bound或空闲
for i, (util, load_bw, store_bw) in enumerate(zip(utilizations, ddr_load_bw, ddr_store_bw)):
    print(f"区间{i}: 利用率={util*100:.1f}%, DDR读取={load_bw} MB/s, DDR写入={store_bw} MB/s")
```

### 3. 识别Load-Bound和Compute-Bound层
```python
import re

def parse_pct(cost_str):
    """从 '59 us (8.2% of model)' 格式中提取百分比"""
    m = re.search(r'([\d.]+)%', cost_str)
    return float(m.group(1)) if m else 0.0

layers = report["summary"]["layer details"]

# 按load cost排序 —— load占比高的层是DDR瓶颈
load_bound = sorted(layers, key=lambda l: parse_pct(l["load cost"]), reverse=True)
print("=== DDR瓶颈层 (Load-Bound) ===")
for l in load_bound[:5]:
    load_pct = parse_pct(l["load cost"])
    compute_pct = parse_pct(l["computing cost (no DDR)"])
    ratio = load_pct / compute_pct if compute_pct > 0 else float('inf')
    print(f"  {l['layer name']}: load={l['load cost']}, compute={l['computing cost (no DDR)']}, load/compute比={ratio:.1f}x")

# 按compute cost排序 —— compute占比高的层是计算瓶颈
compute_bound = sorted(layers, key=lambda l: parse_pct(l["computing cost (no DDR)"]), reverse=True)
print("\n=== 计算瓶颈层 (Compute-Bound) ===")
for l in compute_bound[:5]:
    load_pct = parse_pct(l["load cost"])
    compute_pct = parse_pct(l["computing cost (no DDR)"])
    ratio = compute_pct / load_pct if load_pct > 0 else float('inf')
    print(f"  {l['layer name']}: compute={l['computing cost (no DDR)']}, load={l['load cost']}, compute/load比={ratio:.1f}x")
```

### 4. 判断优化方向
```python
# 根据load/compute比率判断瓶颈类型
for l in layers:
    load_pct = parse_pct(l["load cost"])
    compute_pct = parse_pct(l["computing cost (no DDR)"])
    if load_pct + compute_pct < 1.0:
        continue  # 跳过占比太小的层
    if load_pct > compute_pct * 3:
        print(f"DDR瓶颈: {l['layer name']} (load {load_pct:.1f}% >> compute {compute_pct:.1f}%)")
    elif compute_pct > load_pct * 3:
        print(f"计算瓶颈: {l['layer name']} (compute {compute_pct:.1f}% >> load {load_pct:.1f}%)")
```

# API参考

## `hbdk4.compiler.hbm_perf(model, output_dir=None, remote_ip=None, remote_port=22, remote_cores=None, username="root", password="", local_work_path="remote_bpu/", remote_work_root="/tmp/", inputs=None, hpm_cycle_unit=2)`
- **model** (str): HBM文件路径
- **output_dir** (str): 输出目录，设置后会生成HTML和JSON报告
- **remote_ip** (str): 远程BPU IP地址
- **remote_port** (int): SSH端口
- **remote_cores** (int|List[int]): 运行核心
- **username** (str): SSH用户名
- **password** (str): SSH密码
- **local_work_path** (str): 本地临时路径
- **remote_work_root** (str): 远程临时路径
- **inputs** (Dict): 推理输入数据
- **hpm_cycle_unit** (int): HPM周期单位，必须为2的幂且≤128

## `Hbm(filepath)` 构造函数
加载HBM文件，返回Hbm对象。

## `Hbm.march_name` (property)
目标BPU架构名称，如 "nash-p"、"nash-e" 等。

## `Hbm.toolkit_version` (property)
编译时使用的HBDK版本号。

## `Hbm.graphs` (property)
返回Graph列表。每个Graph包含 `name`、`num_cores`、`flatten_inputs`、`flatten_outputs`、`nodes` 等属性。

## JSON报告结构（`output_dir` 下生成的 `.json` 文件）

```
{
  "summary": {
    "performance": {           # 性能概览
      "FPS": float,            # 每秒帧数
      "latency (us)": float,   # 总延迟（微秒）
      "latency (ms)": float,   # 总延迟（毫秒）
      "latency (us) by segments": [float]  # 各segment延迟
    },
    "DDR access data": {       # DDR访问数据
      "DDR megabytes per run": float,      # 每次推理DDR访问量
      "loaded bytes per run": int,         # 每次推理DDR读取量
      "stored bytes per run": int,         # 每次推理DDR写入量
      "min memory requirement": int,       # 最小内存需求
      "input memory": int,                 # 输入内存
      "output memory": int,                # 输出内存
      "static memory": int,                # 静态内存（权重等）
      "dynamic memory": int                # 动态内存
    },
    "interval info": {         # 时间区间分析
      "interval number": int,                          # 区间数
      "interval time (ms)": float,                     # 每个区间时长
      "interval computing unit utilization": [float],  # 各区间计算单元利用率
      "interval ddr loading bandwidth (megabytes/s)": [float],  # 各区间DDR读取带宽
      "interval ddr storing bandwidth (megabytes/s)": [float]   # 各区间DDR写入带宽
    },
    "layer details": [         # 逐层详情
      {
        "layer name": str,
        "active period of time": str,             # 活跃时间段
        "computing cost (no DDR)": str,           # 计算耗时（不含DDR）
        "load cost": str,                         # DDR读取耗时
        "store cost": str,                        # DDR写入耗时
        "origin ops": int                         # 原始计算量
      }
    ],
    "model info": {             # 模型信息
      "BPU march": str,
      "BPU core number": int,
      "compiling HBDK version": str,
      "compiling options": str,
      "double int8 macs": int,
      "original conv ops": int
    }
  },
  "coreSummaryGroup": [...],   # 按核心汇总（多核时有用）
  "details": [                 # 指令级时间线（嵌套列表，按核心分组）
    [                          # details[0] = 核心0的指令列表
      {
        "inst_type": str,                        # 指令类型：LOAD/TAE/VPU/TRANS/AAE/STORE
        "source_layer_names": str,               # 所属层名
        "start_time (us)": float,                # 指令开始时间（微秒）
        "working_time (us)": float               # 指令执行时长（微秒）
      },
      ...
    ],
    ...                        # 多核时 details[1] = 核心1
  ]
}
```

# 分析方法论

## 瓶颈类型判断

通过比较每层的 **load cost** 和 **computing cost (no DDR)** 百分比，判断瓶颈类型：

| 特征 | 含义 | 优化方向 |
|------|------|----------|
| load cost >> compute cost | **DDR瓶颈**（权重/特征图需从DDR搬运，计算单元等待数据） | 增大 `max_l2m_size`、降低通道数/权重精度、模型剪枝 |
| compute cost >> load cost | **计算瓶颈**（数据已就绪，计算单元满载） | 算子融合、使用更高算力march |
| 两者均低 | 该层不是瓶颈 | 关注其他层 |

## 典型模式

- **网络首层**（如 Conv_0）通常是 **计算bound**：输入特征图小、权重已在片上，计算密度高
- **网络后半段大通道层**（如 stage4/5 的 Conv）通常是 **DDR bound**：权重/特征图大，无法全部放入片上L2M
- **Gemm/FC层** 若 load cost 远高于 compute cost，说明全连接权重搬运是瓶颈，可考虑 1x1 Conv 替代或矩阵分解

## 利用率分析

`interval computing unit utilization` 按时间区间展示计算单元利用率走势：
- 前几个区间利用率高 → 前半段网络计算密集
- 后续区间利用率走低 → 后半段DDR搬运成为瓶颈，计算单元空闲等待数据
- 据此可判断整体是计算受限还是带宽受限

## 指令级并行度分析（基于details）

`details` 是JSON报告中的指令级时间线数据，每条记录包含 `inst_type`、`source_layer_names`、`start_time (us)`、`working_time (us)`。通过分析指令的时间重叠，可以量化跨层流水并行的效率。

> **动态perf的details更准确**（基于板端HPM硬件采集），静态perf的details为编译期估算。

### 1. 全局并行度分布

统计每个时刻同时有多少种指令类型在执行：

```python
details = report["details"][0]  # 单核模型取[0]，多核取对应核心索引
details_sorted = sorted(details, key=lambda d: d["start_time (us)"])

t0 = min(d["start_time (us)"] for d in details_sorted)
t_end = max(d["start_time (us)"] + d["working_time (us)"] for d in details_sorted)
total_span = t_end - t0

bin_size = 1.0  # 1us粒度
num_bins = int(total_span / bin_size) + 1

timeline = []
for b in range(num_bins):
    bs = t0 + b * bin_size
    be = bs + bin_size
    active = set()
    for d in details_sorted:
        if d["start_time (us)"] < be and d["start_time (us)"] + d["working_time (us)"] > bs:
            active.add(d["inst_type"])
    timeline.append(active)

# 并行度分布
from collections import Counter, defaultdict
parallel_dist = Counter(len(a) for a in timeline)
for n in sorted(parallel_dist):
    print(f"{n}种并行: {parallel_dist[n]} us ({parallel_dist[n]/num_bins*100:.1f}%)")

# 平均并行度
avg_parallel = sum(len(a) for a in timeline) / num_bins
print(f"平均并行度: {avg_parallel:.2f}")
```

### 2. 各指令类型利用率与掩盖率

分析每种指令有多少时间在独占执行、有多少时间与其他指令并行（被掩盖）：

```python
inst_types = ["LOAD", "TAE", "VPU", "TRANS", "AAE", "STORE"]

for t in inst_types:
    active_us = sum(1 for a in timeline if t in a)
    alone_us = sum(1 for a in timeline if a == {t})
    with_others_pct = (active_us - alone_us) / active_us * 100 if active_us > 0 else 0
    print(f"{t:6s}: 活跃{active_us/num_bins*100:.1f}%, 独占{alone_us/active_us*100:.1f}%, 与其他并行{with_others_pct:.1f}%")
```

关键指标：
- **独占比高**的指令是瓶颈来源（独占期间其他单元空闲）
- **并行率100%** 的指令（如TRANS/AAE/STORE）不构成额外开销，完全被其他指令掩盖

### 3. 两两指令类型同时活跃

量化哪两种指令最常并行执行：

```python
pair_matrix = {}
for t1 in inst_types:
    for t2 in inst_types:
        overlap = sum(1 for a in timeline if t1 in a and t2 in a)
        pair_matrix[(t1, t2)] = overlap

# 最重要的跨类型并行
for (t1, t2), us in sorted(pair_matrix.items(), key=lambda x: -x[1]):
    if t1 < t2:  # 只打下三角
        print(f"{t1} <-> {t2}: {us} us ({us/num_bins*100:.1f}%)")
```

典型规律：
- **LOAD↔TAE** 是最主要的并行对，即"A层LOAD + B层TAE"的跨层流水掩盖
- **VPU↔TAE** 通常为0（VPU和TAE不会同时活跃）
- **TRANS/AAE** 与其他指令高度并行，几乎不独占总线

### 4. 跨层并行度分析

统计每个时刻有多少个不同层的指令在同时执行：

```python
layer_timeline = []
for b in range(num_bins):
    bs = t0 + b * bin_size
    be = bs + bin_size
    active_layers = set()
    for d in details_sorted:
        if d["start_time (us)"] < be and d["start_time (us)"] + d["working_time (us)"] > bs:
            active_layers.add(d["source_layer_names"])
    layer_timeline.append(active_layers)

layer_parallel_dist = Counter(len(a) for a in layer_timeline)
for n in sorted(layer_parallel_dist):
    print(f"{n}层并行: {layer_parallel_dist[n]} us ({layer_parallel_dist[n]/num_bins*100:.1f}%)")
```

跨层并行中，统计指令对的出现频率，识别主要流水模式：

```python
cross_layer_inst = defaultdict(int)
for b in range(num_bins):
    bs = t0 + b * bin_size
    be = bs + bin_size
    inst_by_layer = defaultdict(set)
    for d in details_sorted:
        if d["start_time (us)"] < be and d["start_time (us)"] + d["working_time (us)"] > bs:
            inst_by_layer[d["source_layer_names"]].add(d["inst_type"])
    layers = list(inst_by_layer.keys())
    if len(layers) >= 2:
        for i in range(len(layers)):
            for j in range(i + 1, len(layers)):
                for t1 in inst_by_layer[layers[i]]:
                    for t2 in inst_by_layer[layers[j]]:
                        pair = tuple(sorted([t1, t2]))
                        cross_layer_inst[pair] += 1

for (t1, t2), us in sorted(cross_layer_inst.items(), key=lambda x: -x[1])[:5]:
    cross_total = sum(1 for a in layer_timeline if len(a) >= 2)
    print(f"{t1} <-> {t2}: {us} us (占跨层并行{us/cross_total*100:.1f}%)")
```

### 5. 单层独占总线分析

识别哪些层在独占执行（无跨层流水掩盖），这些层是优化重点：

```python
layer_solo = defaultdict(int)
for b, active in enumerate(layer_timeline):
    if len(active) == 1:
        for l in active:
            layer_solo[l] += 1

for l, us in sorted(layer_solo.items(), key=lambda x: -x[1])[:10]:
    print(f"{l}: 独占{us} us")
```

### 6. 按网络阶段分析

将时间线划分为多个阶段，分别统计各阶段的并行效率：

```python
phases = [
    ("前处理", 11, 38),
    ("前半段小卷积", 38, 137),
    ("中段中等卷积", 137, 245),
    ("后半段大卷积", 245, 381),
    ("FC层", 381, 407),
]

for pname, ps, pe in phases:
    span = pe - ps
    # 每个阶段内1us粒度时间轴
    phase_bins = int(span)
    phase_timeline = []
    for b in range(phase_bins):
        bs = ps + b
        be = bs + 1
        active = set()
        for d in details_sorted:
            if d["start_time (us)"] < be and d["start_time (us)"] + d["working_time (us)"] > bs:
                active.add(d["inst_type"])
        phase_timeline.append(active)

    # 各类型利用率
    type_active = {t: sum(1 for a in phase_timeline if t in a) for t in inst_types if any(t in a for a in phase_timeline)}
    util_str = " ".join(f"{t}={v/span*100:.0f}%" for t, v in type_active.items())

    # 平均并行度
    avg_p = sum(len(a) for a in phase_timeline) / phase_bins

    print(f"{pname}: {util_str}, 平均并行度={avg_p:.2f}")
```

### 7. 跨层LOAD-计算掩盖率

量化每层的LOAD被其他层计算掩盖、以及TAE被其他层LOAD掩盖的比例：

```python
# 收集所有计算区间(TAE+VPU+AAE)和LOAD区间
compute_intervals = [(d["start_time (us)"], d["start_time (us)"] + d["working_time (us)"], d["source_layer_names"])
                     for d in details_sorted if d["inst_type"] in ("TAE", "VPU", "AAE")]
load_intervals = [(d["start_time (us)"], d["start_time (us)"] + d["working_time (us)"], d["source_layer_names"])
                  for d in details_sorted if d["inst_type"] == "LOAD"]

def overlap_time(intervals_a, intervals_b):
    """计算a与b的重叠时间，排除同层"""
    total = 0
    for sa, ea, na in intervals_a:
        for sb, eb, nb in intervals_b:
            if na == nb:
                continue
            os_ = max(sa, sb)
            oe_ = min(ea, eb)
            if oe_ > os_:
                total += oe_ - os_
    return total

# 按层统计
layer_data = defaultdict(lambda: {"LOAD": [], "TAE": [], "VPU": [], "TRANS": [], "AAE": []})
for d in details_sorted:
    s = d["start_time (us)"]
    e = s + d["working_time (us)"]
    layer_data[d["source_layer_names"]][d["inst_type"]].append((s, e))

for name in sorted(layer_data, key=lambda n: -sum(e - s for s, e in layer_data[n]["LOAD"])):
    ld = layer_data[name]
    load_total = sum(e - s for s, e in ld["LOAD"])
    tae_total = sum(e - s for s, e in ld["TAE"])
    if load_total < 0.5 and tae_total < 0.5:
        continue

    layer_loads = [(s, e, name) for s, e in ld["LOAD"]]
    layer_taes = [(s, e, name) for s, e in ld["TAE"]]
    load_masked = overlap_time(layer_loads, compute_intervals)
    tae_masked = overlap_time(layer_taes, load_intervals)
    load_mask_pct = load_masked / load_total * 100 if load_total > 0 else 0
    tae_mask_pct = tae_masked / tae_total * 100 if tae_total > 0 else 0

    print(f"{name}: LOAD={load_total:.1f}us(被计算掩盖{load_mask_pct:.0f}%), TAE={tae_total:.1f}us(被LOAD掩盖{tae_mask_pct:.0f}%)")

# 全局汇总
total_load = sum(e - s for s, e, _ in load_intervals)
total_tae = sum(e - s for s, e, _ in compute_intervals)
total_load_masked = overlap_time(load_intervals, compute_intervals)
total_tae_masked = overlap_time([(s, e, n) for s, e, n in compute_intervals], load_intervals)
print(f"全局: LOAD被计算掩盖{total_load_masked/total_load*100:.1f}%, TAE被LOAD掩盖{total_tae_masked/total_tae*100:.1f}%")
```

## 指令类型说明

| 类型 | 含义 | 典型特征 |
|------|------|---------|
| LOAD | 从DDR搬运权重/特征图到片上 | 主力搬运指令，活跃率通常最高 |
| TAE | 张量计算引擎（BPU核心计算） | 主力计算指令，与LOAD形成流水 |
| VPU | 向量计算单元 | 仅前处理阶段活跃（如NV12→RGB） |
| TRANS | 数据重排（如NCHW↔NHWC） | 利用率低，几乎100%被其他指令掩盖 |
| AAE | 辅助计算引擎 | 利用率极低，完全被掩盖 |
| STORE | 从片上写回DDR | 利用率极低，仅输出时出现 |

## 并行分析关键指标

| 指标 | 计算方法 | 含义 |
|------|---------|------|
| 平均并行度 | 每时刻活跃指令类型数的平均值 | 越高越好，最大值为指令类型数(6) |
| 流水掩盖率 | LOAD被其他层计算掩盖的时间 / LOAD总时间 | 越高说明流水越充分 |
| 单层独占率 | 仅1层活跃的时间 / 总时间 | 越低越好，高则说明流水不充分 |
| 指令独占比 | 某指令独占总线时间 / 该指令活跃时间 | 独占比高→瓶颈来源 |

## 优化方向

- **LOAD独占比高的层**（如大通道Conv、FC）：权重搬运无法被其他计算掩盖，考虑增大 `max_l2m_size`、剪枝、量化
- **TAE空闲率高的阶段**（如stage4-5）：计算单元等数据，DDR带宽是瓶颈
- **跨层并行度低的阶段**：编译器调度不够充分，可尝试调整编译参数优化指令交错

# 注意事项
- 动态perf需安装`hbdk4_runtime_aarch64`的wheel包
- 仅当指定remote_ip时，VPU/SPU/CPU的性能信息才可用
- remote_port参数类型为int
- 不指定remote_ip时为静态perf，指定remote_ip时为动态perf
- JSON报告文件名与模型中的graph name一致（如 `resnet50.json`）
- `hbm_perf` 返回值为 int（0表示成功），报告内容需通过HTML/JSON文件查看
- **多模型HBM**：若HBM中包含多个graph（如通过 `link()` 打包了多个模型），静态perf会为每个graph生成独立的HTML/JSON报告；**动态perf当前不支持多graph的HBM**（内部会 assert 只允许1个graph）

# 常见问题与易错点

## HBM加载方式
- **加载 .hbm 文件**：用 `Hbm("deploy.hbm")`（从 `hbdk4.compiler` 导入）
- **加载 .bc 文件**：用 `load("model.bc")`（从 `hbdk4.compiler` 导入）
- `load()` 不支持 `.hbm` 文件，传入会报 `ValueError: invalid file. should end with .bc`

## 导入路径
- `hbm_perf` 和 `Hbm` 都从 `hbdk4.compiler` 导入（即 `from hbdk4.compiler import hbm_perf, Hbm`）
- `hbdk4` 顶层模块没有这些属性，`hbdk4.compiler.apis` 中有 `Hbm` 但没有 `hbm_perf`
- 不要用 `import hbdk4; hbdk4.load()`，顶层模块是空的

## Graph访问方式
- `hbm.graphs` 返回 Graph 列表，用 `hbm.graphs[0]` 访问
- `hbm[0]` 也可用，等同于 `hbm.graphs[0]`
- `hbm.functions` 返回的是内部Graph对象，不如 `hbm.graphs` 好用

## Node属性注意
- `node.parameters` 属性在 hbdk4 4.9.7 中有内部拼写bug（`paramters` vs `parameters`），调用会抛 `AttributeError`
- `node.estimated_latency_micros` 返回该节点的编译期预估延迟（微秒），无需生成报告即可获取
- `node.device` 返回枚举值如 `DeviceCategory.Bpu`

## Type属性
- `v.type.shape` 返回 tuple（如 `(1, 3, 224, 224)`）
- `v.type.np_dtype` 返回 numpy dtype 字符串（如 `float32`）
- `v.type._strides` 是属性不是方法，不能用 `v.type._strides()` 调用
