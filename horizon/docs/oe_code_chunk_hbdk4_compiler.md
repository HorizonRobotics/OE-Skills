# oe_code_chunk_hbdk4_compiler

## 仓库概述

- **名称**: hbdk4-compiler v4.11.2 — Horizon BDK4 Compiler
- **Python 包**: `hbdk4_compiler-4.11.2-cp310`，已解压的 pip wheel（非 git 源码仓库）
- **用途**: 将神经网络模型（ONNX、PyTorch TorchScript）编译为面向 Horizon BPU (Brain Processing Unit) 的优化 `.hbm` 二进制文件
- **角色**: J6 Open Explorer 工具链后端编译器，接收 HBIR（MLIR dialect）并生成可在 Nash 系列 BPU 上运行的 HBM
- **依赖**: `numpy`, `netron>=6.0.2`, `hbdk4-march==4.11.2`；可选 `paramiko`（RemoteBPU）
- **支持目标平台**: nash-e, nash-m, nash-p, nash-h, nash-b, nash-b-lite, nash-b-plus
- **原生扩展**: `_hbdk.*.so`, `_hbrt4_py.so`, `_mlir.ir.so` 等 C++ 扩展
- **原生工具**: `hbdk-lld`(链接器), `hbrt4-run-model-nash`(模拟器), `hbdk4-perf`(性能分析), `hbrt4-disas`(反汇编), `hbdk-hbm-desc`(元数据), `mlir-opt`/`mlir-translate`(MLIR 工具), `qemu-system-riscv64`(RISC-V 仿真)

## 目录结构

```
hbdk4_compiler-4.11.2.data/purelib/hbdk4/compiler/
  __init__.py              # 顶层 API: load, save, convert, compile, link, statistics, visualize
  apis.py                  # 主编译流水线函数实现
  extra_apis.py            # 高级 API: calibrate(), llm_convert()
  overlay.py               # Module/Function/Argument/Operation/Value Python 封装 (IR 操作核心)
  ir.py                    # MLIR Python 绑定入口 (register_attribute_builder)
  march.py                 # March 枚举 (从 hbdk4-march 动态构建)
  cache_mode.py            # CacheMode 枚举 (disable/enable/force_overwrite)
  hbm.py                   # Hbm/Graph/Node/Variable/Memspace 运行时表示
  hbm_tools.py             # hbm_extract_desc, hbm_update_desc, hbm_perf, hbm_pack
  pack_models.py           # pack_models() 多模型合并
  remote_bpu.py            # RemoteBPU 类 (SSH 远程 BPU 开发板执行)
  leap.py                  # Leap 编程模型: @leap_func 自定义算子编译
  passmanager.py           # PassManager 封装
  rewrite.py               # IR 重写工具
  hpc.py                   # HPC op 打包 (pack_hpc_ops)
  version.py               # 版本信息
  dialects/                # MLIR dialect Python 绑定 (hbir, hbdk, hbtl, qnt, b25, b30, arith, func, linalg, scf, ...)
  onnx/                    # ONNX 前端: opset9~opset20 算子转换 + horizon.py 自定义算子
  torch/                   # PyTorch 前端: jit/ (TorchScript) + export/ (torch.export)
  frontend/                # 通用前端框架: registry.py (OpConvertorRegistry), convertor.py, adaptor.py
  ops/                     # 算子定义: hbir.py, hbtl.py, qnt.py, b25.py, common.py
  overlay_utils/           # overlay 辅助: base, pytree, module_modifier, arg_modifiers, func_modifiers
  numba/                   # Numba 自定义算子编译: compile_custom()
  triton/                  # 内置 Triton BPU 编译器 (language/, compiler/, runtime/, ops/)
  inference/               # 推理辅助: hbtl/, ude/
  utils/                   # 工具: types.py, visualize.py, process.py, pytree.py, default.py
  docs/                    # API 参考文档 (hbdk_api_reference.md, hbir_op_*.mdx, leap_op.mdx)
  _mlir_libs/              # 原生 .so + 二进制工具 (hbdk-lld, mlir-opt, etc.)
  include/                 # C/C++ 头文件 (dsp/, spu/, vpu/, ude/)
  lib/firmware/            # BPU 固件文件
  toolchain/               # RISC-V 交叉编译工具链 (riscv64-unknown-elf)
  tools/                   # 辅助工具脚本
```

## 关键模块与 API

### 编译流水线 (apis.py)
```python
from hbdk4.compiler import load, save, convert, compile, link, statistics, visualize

m = load("model.bc")                     # 加载 MLIR bytecode (.bc) 或文本 (.mlir)
m2 = convert(m, march="nash-b")          # HBIR → 后端 IR
hbm = compile(m2, "out.hbm", march="nash-b", opt=2, jobs=4)  # 编译为 .hbm
save(m2, "converted.bc")                 # 保存中间结果
```

- `compile()` 关键参数: `opt`(优化等级), `jobs`(线程数), `balance`(cycles vs DDR, 0~100), `cache_mode`, `max_l2m_size`, `input_no_padding`, `output_no_padding`
- `link(hbo_list, output_path)` — 调用 `hbdk-lld` 将 .hbo 链接为 .hbm

### IR 操作 (overlay.py)
- `Module` — MLIR Module 封装: `.functions`, `.clone()`, `.precision_config`
- `Function` — 函数: `.inputs`, `.outputs`, `.statistics()`, `.remove_unused_args_and_results()`
- `Argument` — 参数: `.insert_transpose()`, `.erase()`, `.is_removable`, `.get_attached_op()`
- `remove_unused_args_and_results(m, whitelist=...)` — 移除无用输入输出

### 运行时 (hbm.py)
- `Hbm` — .hbm 文件: `.graphs`, `.version`, `.description`
- `Graph` — 计算图: `.feed()` (推理), `.perf()` (性能分析), `.nodes`, `.variables`
- `Node` / `Variable` / `Memspace` — 运行时节点、变量、内存空间
- `Graph.feed(inputs, remote_ip=...)` — 本地模拟或 SSH 远程执行

### 高级 API (extra_apis.py)
- `calibrate(m, gran="single")` — 量化校准
- `llm_convert(m, march, enable_softmax_vae=..., rmsnorm_version=...)` — LLM 专用降级

### Leap 编程模型 (leap.py)
- `@leap_func` — 装饰自定义 Python 函数，编译为 BPU 算子
- `leap.invoke(module, func_name, *args)` — 执行 Leap 编译后的函数
- `leap_export()` / `load_library()` — 导出/加载

### HBM 工具 (hbm_tools.py)
- `hbm_extract_desc(model)` / `hbm_update_desc(model, desc_dict)` — 元数据读写
- `hbm_perf(model, ...)` — 性能分析 (封装 hbdk4-perf)
- `hbm_pack(model_list, output)` — 多 HBM 打包

## 常用查询映射

| 用户意图 | 推荐搜索关键词 | 说明 |
|---|---|---|
| 模型编译为 HBM | `compile`, `hbm`, `apis.py` | `compile()` 生成 .hbm/.hbo |
| 将 HBIR 降级为后端 IR | `convert`, `backend ir`, `march` | `convert()` 按目标平台降级 |
| 链接 HBM | `link`, `hbdk-lld`, `hbo` | .hbo → .hbm 链接 |
| 加载/保存 MLIR | `load`, `save`, `bytecode`, `.bc` | MLIR 序列化/反序列化 |
| IR 图操作 | `Module`, `Function`, `overlay.py` | overlay 层封装 |
| 移除无用输入输出 | `remove_unused_args_and_results` | 图简化优化 |
| 插入 transpose | `insert_transpose`, `Argument` | 在输入输出上插入转置 |
| 目标平台 march | `March`, `march.py`, `nash` | BPU 架构枚举 |
| ONNX 前端转换 | `opset`, `onnx/`, `OpConvertorRegistry` | ONNX 算子到 HBIR 映射 |
| PyTorch 前端 | `torch/`, `jit/`, `export/` | TorchScript / torch.export |
| 算子融合 | `fusion`, `statistics`, `expand_fusion` | 统计 fusion 内部算子 |
| 量化校准 | `calibrate`, `extra_apis` | 量化参数收集 |
| 量化配置/精度 | `PrecisionConfig`, `precision_config` | 混精度配置 |
| 自定义算子 (Python) | `leap`, `leap_func`, `leap_export` | Leap 编程模型 |
| 自定义算子 (Numba) | `numba`, `compile_custom` | Numba JIT 自定义算子 |
| Triton BPU 编译 | `triton/`, `compiler/`, `language/` | 内置 Triton 编译器 |
| LLM 编译 | `llm_convert`, `softmax_vae`, `rmsnorm` | LLM 专用降级选项 |
| 运行时推理 | `Graph.feed`, `hbm.py`, `remote_ip` | 模型模拟执行 |
| 性能分析 | `hbm_perf`, `Graph.perf`, `hbdk4-perf` | 性能 profiling |
| HBM 元数据 | `hbm_extract_desc`, `hbm_update_desc` | HBM 描述信息读写 |
| 多模型打包 | `pack_models`, `hbm_pack` | 多 Module/HBM 合并 |
| 远程 BPU 执行 | `RemoteBPU`, `paramiko`, `SSH` | 远端开发板推理 |
| 编译缓存 | `cache_mode`, `CacheMode`, `cache_path` | 编译结果缓存 |
| L2M 内存配置 | `max_l2m_size` | L2M 使用上限 |
| 算子约束文档 | `hbir_op_J6E_constraint`, `docs/` | 各平台算子限制 |
| MLIR dialect | `dialects/`, `hbir`, `hbdk`, `hbtl`, `qnt` | IR 层级定义 |
| MLIR Pass 管理 | `PassManager`, `passmanager` | Pass 调度 |
| IR 重写 | `rewrite.py` | 图重写工具 |
| 可视化 | `visualize`, `netron`, `OnnxConvertor` | 生成 ONNX 可视化 |
| HPC op 打包 | `pack_hpc_ops`, `hpc.py` | HPC 算子处理 |
| 编译优化级别 | `opt`, `balance`, `jobs` | compile() 参数 |
| 输入输出 padding | `input_no_padding`, `output_no_padding` | 原生输入输出 |
| 编译时间限制 | `max_time_per_fc` | 单 funccall 最大时间 |
| 编译建议 | `advice`, `advice_path` | 算子耗时建议 |
| 多模型 HBM | `pack_models`, `link` | 多模型链接 |
| 算子注册 | `OpConvertorRegistry`, `registry.py` | 前端算子转换器 |
| BPU 固件 | `lib/firmware/` | 固件文件 |
| RISC-V 仿真 | `qemu-system-riscv64`, `toolchain/` | VPU/SPU 模拟 |

## 规则与约定

- **包结构**: 解压后的 wheel，所有代码在 `hbdk4_compiler-4.11.2.data/purelib/hbdk4/compiler/` 下，无构建脚本
- **命名空间**: `hbdk4.compiler.*`，顶层 `__init__.py` re-export 核心 API
- **IR 层级**: ONNX/Torch → HBIR(高层) → HBDK/HBTL(后端) → .hbo → .hbm
- **march 依赖**: `hbdk4-march==4.11.2` 为强依赖，缺少时导入失败
- **dialect 绑定**: `dialects/` 下 `_xxx_ops_gen.py` 为自动生成，勿手动修改
- **原生调用**: Python 通过 `_hbdk` / `_hbrt4_py` C++ 扩展调用底层编译/运行时
- **文件后缀**: `.bc` = MLIR bytecode, `.hbo` = 目标文件, `.hbm` = 链接后二进制
- **模型限制**: 输入/输出各最多 512 个，每个 ≤2GB；张量最多 10 维
- **支持类型**: ui8, si8, si16, ui32, si32, si64, float, bool
- **文档位置**: `docs/hbdk_api_reference.md` 为完整 API 参考，`hbir_op_J6*.mdx` 为算子约束
- **RemoteBPU**: 需 `pip install hbdk4-compiler[RemoteBPU]` 安装 paramiko
