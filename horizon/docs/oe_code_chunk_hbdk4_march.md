# oe_code_chunk_hbdk4_march

## 仓库概述

- **名称**: `hbdk4-march` v4.11.2
- **用途**: Horizon Robotics BPU（Brain Processing Unit）机器架构（march）描述包
- **角色**: HBDK4 工具链的基础依赖，为 `hbdk4-compiler` 和 `hmct` 提供 BPU 目标架构元数据
- **形式**: 解压后的 Python wheel（二进制包），非源码仓库
- **导入路径**: `hbdk4.march`（注意不是 `hbdk4_march`）
- **兼容性**: ABI3 stable，兼容 CPython 3.10+，manylinux_2_28_x86_64
- **支持架构**: Nash 系列 —— `nash-e`、`nash-m`、`nash-p`、`nash-h`、`nash-b`、`nash-b-lite`、`nash-b-plus`

## 目录结构

```
hbdk4_march-4.11.2-cp310/
├── CLAUDE.md                          # 包说明文档
├── hbdk4_march-4.11.2.data/
│   └── purelib/
│       └── hbdk4/
│           └── march/
│               ├── __init__.py        # 公开 API：BpuMarchDesc 类 + 模块函数
│               └── _libs/
│                   ├── _hbmarch_py.so # Python C++ 扩展（所有 API 委托至此）
│                   ├── libhbmarch_clib.so  # 底层 C 库
│                   └── version.py     # 构建元数据（版本、时间戳、编译器信息）
└── hbdk4_march-4.11.2.dist-info/
    ├── METADATA                       # 包元数据
    ├── RECORD                         # 安装文件清单
    ├── WHEEL                          # wheel 格式信息
    ├── metadata.json                  # JSON 格式元数据
    └── top_level.txt                  # 顶层命名空间
```

## 关键模块与 API

### 模块级函数（`hbdk4.march`）

| 函数签名 | 说明 |
|---|---|
| `bpu_march_to_bpu_project(identifier: str) -> str` | 将 BPU march 名称映射到项目代号（如 `nash-b` → `BPU_PROJECT-nash-b`） |
| `get_all_bpu_march_names() -> List[str]` | 返回所有受支持的 BPU march 名称列表 |
| `get_march_num_cores(march: str) -> int` | 获取指定 march 的 BPU 核心数 |

### `BpuMarchDesc` 类

| 方法 / 属性 | 说明 |
|---|---|
| `BpuMarchDesc.get_by_march_name(march_name: str)` | 按 march 名加载 flatbuffer 配置（`pub_fb` / `priv_fb`） |
| `BpuMarchDesc.get_by_filename(filename: str)` | 按文件名加载 flatbuffer 配置 |
| `BpuMarchDesc.registry_config_data(data: bytes)` | 将配置二进制数据注册到编译器内存注册表 |
| `BpuMarchDesc.get_all_march_names() -> List[str]` | 发现所有内置 march 配置名称 |
| `.identifier -> str` | 获取当前 march 名称（property） |
| `.bpu_project -> str` | 获取对应 BPU 项目代号（property） |

### 下游使用方式（`hbdk4.compiler.march`）

```python
from hbdk4.march import get_all_bpu_march_names, bpu_march_to_bpu_project, get_march_num_cores
March = create_march_enum()  # 动态构建 March 枚举，每个 march 名成为一个枚举成员
march.series      # MarchSeries.nash
march.maybe_qnx   # True if nash-b (QNX 平台)
march.num_cores   # BPU 核心数
March.get("nash-e")  # 按名称查找枚举成员
```

## 常用查询映射

| 用户意图 | 推荐搜索关键词 | 说明 |
|---|---|---|
| 查看所有支持的 BPU 架构 | `get_all_bpu_march_names`, `march names` | 返回 nash-e/m/p/h/b 等列表 |
| 查询某个 march 对应的项目代号 | `bpu_march_to_bpu_project`, `bpu project` | 如 nash-b → BPU_PROJECT-nash-b |
| 查询 BPU 核心数 | `get_march_num_cores`, `num_cores` | 不同 march 核心数不同 |
| 加载 march 配置数据 | `BpuMarchDesc`, `get_by_march_name` | 加载 pub_fb/priv_fb flatbuffer |
| 注册配置到编译器 | `registry_config_data` | 将 config 推入编译器内存注册表 |
| Nash 系列有哪些变体 | `nash-e`, `nash-m`, `nash-p`, `nash-h`, `nash-b` | 7 种 march 变体 |
| Journey 6 目标架构 | `nash`, `march`, `J6` | J6 系列对应 Nash 架构 |
| QNX 平台判断 | `maybe_qnx`, `nash-b` | nash-b march 对应 QNX 平台 |
| 编译器 March 枚举 | `create_march_enum`, `March`, `MarchBase` | 在 hbdk4.compiler.march 中动态构建 |
| March 系列分类 | `MarchSeries`, `series` | 目前仅有 MarchSeries.nash |
| 架构配置 flatbuffer | `pub_fb`, `priv_fb`, `flatbuffer` | 公有/私有配置数据 |
| 包版本信息 | `version.py`, `VERSION`, `BUILD_TIME` | 版本 4.11.2，构建于 2026-06-11 |
| 构建环境 | `HOST_TRIPLE`, `CMAKE_C_COMPILER_VERSION` | x86_64-linux, GCC 12.2.0 |
| 源码修订版本 | `REVISIONS`, `hbdk`, `llvm-project`, `qemu` | 追踪的 git commit hash |
| 原生二进制依赖 | `_hbmarch_py.so`, `libhbmarch_clib.so` | C++ 扩展和底层 C 库 |
| 包安装依赖关系 | `hbdk4-march`, `hbdk4-compiler` 依赖 | compiler 导入时强依赖 march |
| hmct 量化使用 march | `march`, `quant_config`, `model_builder` | hmct 量化时指定目标 march |
| wheel 兼容性 | `abi3`, `cp310`, `manylinux_2_28` | ABI3 stable, CPython 3.10+ |
| 导入路径问题 | `hbdk4.march`, `top_level.txt` | 命名空间是 hbdk4.march 非 hbdk4_march |
| 按文件名查找配置 | `get_by_filename` | 从 .hbm 文件名推断 march |

## 规则与约定

- **导入命名空间**: 始终使用 `from hbdk4.march import ...`，而非 `hbdk4_march`
- **纯二进制包**: 无法从此目录修改、重新构建或调试原生扩展；所有逻辑委托至 `_hbmarch_py.so`
- **强依赖**: `hbdk4-compiler` 在导入时即需要本包，缺失会立即抛出 `ImportError`
- **动态枚举**: `March` 枚举在 `hbdk4.compiler.march` 中运行时构建，不应硬编码枚举值
- **命名规范**: march 名使用连字符（`nash-e`），枚举成员使用下划线（`nash_e`），查找时自动转换
- **BpuMarchDesc 用法**: 类方法加载配置后通过 `cls.pub_fb` / `cls.priv_fb` 类属性存储，非实例属性
- **构建信息**: 版本和构建元数据位于 `_libs/version.py`，包含 `VERSION`、`BUILD_TIME`、`REVISIONS` 等常量
- **版本通道**: `VERSION_CHANNEL = "stable"`，发布由 `cirunner` CI 账户构建
