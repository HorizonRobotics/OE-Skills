#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用模型编译脚本 - 支持 ONNX 和 BC 模型格式
基于 YAML 配置文件驱动

Usage:
    # 生成配置文件模板
    python compile_model.py --generate-config -o config.yaml

    # 使用配置文件编译
    python compile_model.py -c config.yaml
"""

import os
import sys
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

try:
    import click
except ImportError:
    print("请安装 click: pip install click")
    sys.exit(1)

try:
    import yaml
except ImportError:
    print("请安装 pyyaml: pip install pyyaml")
    sys.exit(1)

try:
    from packaging.version import Version
    def version_ge(v1: str, v2: str) -> bool:
        """比较版本号是否 v1 >= v2"""
        try:
            return Version(v1) >= Version(v2)
        except:
            return True  # 无法解析时默认返回 True
except ImportError:
    def version_ge(v1: str, v2: str) -> bool:
        """简单版本比较"""
        try:
            parts1 = [int(x) for x in v1.split('.')[:3]]
            parts2 = [int(x) for x in v2.split('.')[:3]]
            return parts1 >= parts2
        except:
            return True

try:
    from hbdk4.compiler import load, convert, compile, statistics, March, hbm_perf, save, visualize, Hbm
    from hbdk4.compiler import version as hbdk_version
    HBDK_AVAILABLE = True
except ImportError:
    HBDK_AVAILABLE = False
    print("警告: hbdk4 未安装，部分功能不可用")

# ============== 模型路径合法性（后缀 / PTQ-QAT 阶段）==============
# Skill 契约：以下 assert_* / load_bc_model_validated 为强制门禁，供 j6-hbdk-compile
# 工作流依赖；不得为绕过失败而删改或短路，正确做法是换合法模型或对齐 hbdk4 / 导出流程。

SUPPORTED_MODEL_SUFFIXES = (".onnx", ".bc")

BC_LOAD_VERSION_HINT = (
    "提示：生成该 .bc 时使用的 hbdk4 版本可能与当前环境中的 hbdk4 不兼容，"
    "请使用与导出模型一致或兼容的工具链 / 环境后重试。"
)


def assert_supported_model_suffix(model_path: str) -> None:
    """仅允许 .onnx / .bc。"""
    suf = Path(model_path).suffix.lower()
    if suf not in SUPPORTED_MODEL_SUFFIXES:
        raise ValueError(
            f"不支持的模型类型：仅支持后缀 {SUPPORTED_MODEL_SUFFIXES}，当前为 '{suf or '(无)'}'。"
            "请使用 .onnx 或 .bc 模型。"
        )


def _iter_module_named_attributes(hbdk_model):
    """与业务侧 check_current_phase 一致：遍历 inner module 的 named attributes。"""
    inner = getattr(hbdk_model, "module", hbdk_model)
    if inner is None or not hasattr(inner, "attributes"):
        return []
    return list(inner.attributes)


def assert_bc_is_qat_phase(hbdk_model) -> None:
    """qat.bc 不应含 hbdk.target；若模块属性中存在 hbdk.target，则为已做过 convert 的 quantized.bc。

    参考：若 ``hbdk.target`` 不在 module attributes 中，则可视为 qat.bc 阶段产物。
    """
    names = {named_attr.name for named_attr in _iter_module_named_attributes(hbdk_model)}
    if "hbdk.target" in names:
        raise RuntimeError(
            "检测到当前 .bc 为 quantized.bc（模块属性中存在 hbdk.target），"
            "本编译流程需要从 QAT 阶段导出的 qat.bc。"
            "请改用 qat.bc 后再执行编译。"
        )


def assert_onnx_has_hz_calibration(onnx_model) -> None:
    """Horizon PTQ ONNX 须包含自定义算子 HzCalibration；否则视为非 PTQ 模型并终止。"""
    for node in onnx_model.graph.node:
        if node.op_type == "HzCalibration":
            return
    raise RuntimeError(
        "ONNX 中未找到 Horizon 自定义算子 HzCalibration，无法按 PTQ 模型继续编译。"
        "请确认该 ONNX 是否为 horizon_plugin_pytorch 导出的 PTQ 模型；"
    )


def load_bc_model_validated(model_path: str):
    """加载 .bc；失败则提示可能与当前 hbdk4 不兼容。"""
    if not HBDK_AVAILABLE:
        raise RuntimeError("hbdk4 未安装，无法加载 .bc 模型")
    try:
        return load(model_path)
    except Exception as e:
        raise RuntimeError(f"加载 .bc 失败: {e}\n{BC_LOAD_VERSION_HINT}") from e


# ============== 枚举和数据类定义 ==============

class ModelFormat(Enum):
    """支持的模型格式"""
    ONNX = "onnx"
    BC = "bc"


class InputSourceType(Enum):
    """输入源类型"""
    DDR = "ddr"
    PYRAMID = "pyramid"
    RESIZER = "resizer"


@dataclass
class InputSourceConfig:
    """输入源配置"""
    name: str                          # 输入节点名称
    source_type: InputSourceType       # 输入源类型
    mean: List[float] = None           # pyramid/resizer 均值
    std: List[float] = None            # pyramid/resizer 标准差
    divisor: float = 1.0               # 归一化除数
    data_type: str = "rgb"             # 训练数据格式: rgb, bgr, yuv444
    layout_transpose: List[int] = None # 布局转换维度

    def __post_init__(self):
        # 不设置默认值，完全根据配置文件来
        # 如果 mean/std 为 None，会在 to_dict 中处理
        pass

    def get_preprocess_mode(self) -> Optional[str]:
        """根据 data_type 获取 insert_image_preprocess 的 mode 参数

        - rgb -> "yuvbt601full2rgb"
        - bgr -> "yuvbt601full2bgr"
        - yuv444 -> None
        - featuremap -> None（featuremap 输入不需要图像预处理，直接跳过）

        Raises:
            ValueError: 如果 data_type 不是支持的类型
        """
        if self.data_type == "rgb":
            return "yuvbt601full2rgb"
        elif self.data_type == "bgr":
            return "yuvbt601full2bgr"
        elif self.data_type in ("yuv444", "featuremap"):
            return None
        else:
            raise ValueError(
                f"data_type 必须是 'rgb', 'bgr', 'yuv444' 或 'featuremap' 之一，当前值为: '{self.data_type}'。featuremap 输入不需要图像预处理。"
            )

    def to_dict(self) -> dict:
        """转换为字典。DDR 输入仅 name/source_type/data_type；pyramid/resizer 可含 mean/std/divisor。"""
        d = {
            "name": self.name,
            "source_type": self.source_type.value,
            "data_type": self.data_type,
        }
        if self.source_type in (InputSourceType.PYRAMID, InputSourceType.RESIZER):
            if self.mean is not None:
                d["mean"] = self.mean
            if self.std is not None:
                d["std"] = self.std
            if self.mean is not None or self.std is not None:
                d["divisor"] = getattr(self, "divisor", 1.0)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "InputSourceConfig":
        """从字典创建。DDR 条目忽略 mean/std/divisor（仅 pyramid/resizer 使用）。"""
        st = InputSourceType(data.get("source_type", "ddr"))
        if st == InputSourceType.DDR:
            mean, std, divisor = None, None, 1.0
        else:
            mean = data.get("mean")
            std = data.get("std")
            divisor = data.get("divisor", 1.0)
        return cls(
            name=data.get("name", ""),
            source_type=st,
            mean=mean,
            std=std,
            divisor=divisor,
            data_type=data.get("data_type", "rgb"),
        )


@dataclass
class CompileConfig:
    """编译配置"""
    # 基本配置
    model_path: str                           # 模型路径
    output_dir: str = None                    # 输出目录（从 PTQ working_dir 映射）
    march: str = "nash-e"                     # 目标平台
    output_model_file_prefix: str = None      # 新增：自定义编译产物名称（.hbm 文件前缀，默认使用模型 stem）

    # 输入源配置
    input_sources: List[InputSourceConfig] = field(default_factory=list)

    # 节点删除配置
    # remove_all_qdq 已不再支持
    remove_node_type: List[str] = field(default_factory=list)  # 要删除的节点类型，如 ["Quantize"]
    remove_input_nodes: List[str] = field(default_factory=list)  # 按名称删除输入节点相邻的 QDQ
    remove_output_nodes: List[str] = field(default_factory=list)  # 按名称删除输出节点相邻的 QDQ
    preserve_input_nodes: List[str] = field(default_factory=list)  # 要保留的输入节点白名单
    preserve_output_nodes: List[str] = field(default_factory=list)  # 要保留的输出节点白名单

    # 编译参数
    debug: bool = True                        # 默认 True
    input_no_padding: bool = True
    output_no_padding: bool = True
    enable_hpc: bool = True
    enable_vpu: bool = True
    core_num: int = 1
    opt_level: int = 2
    jobs: int = 32
    max_l2m_size: int = 0
    max_time_per_fc: int = 0                  # 每个 function 最大编译时间
    cache_path: str = None
    cache_mode: str = "enable"

    # 性能测试配置
    perf_ip: str = None                       # 为空则 hbm_perf 不设置 remote_ip
    perf_username: str = "root"

    def to_dict(self) -> dict:
        """转换为字典"""
        d = {
            "model_path": self.model_path,
            "output_dir": self.output_dir,
            "march": self.march,
            "input_sources": [src.to_dict() for src in self.input_sources],
            "remove_node_type": self.remove_node_type,
            "remove_input_nodes": self.remove_input_nodes,
            "remove_output_nodes": self.remove_output_nodes,
            "preserve_input_nodes": self.preserve_input_nodes,
            "preserve_output_nodes": self.preserve_output_nodes,
            "debug": self.debug,
            "input_no_padding": self.input_no_padding,
            "output_no_padding": self.output_no_padding,
            "enable_hpc": self.enable_hpc,
            "enable_vpu": self.enable_vpu,
            "core_num": self.core_num,
            "opt_level": self.opt_level,
            "jobs": self.jobs,
            "max_l2m_size": self.max_l2m_size,
            "max_time_per_fc": self.max_time_per_fc,
            "cache_path": self.cache_path,
            "cache_mode": self.cache_mode,
            "perf_ip": self.perf_ip,
            "perf_username": self.perf_username,
        }
        if self.output_model_file_prefix:
            d["output_model_file_prefix"] = self.output_model_file_prefix
        return d


# ============== 配置文件工具 ==============

def get_default_output_dir(model_path: str) -> str:
    """获取默认输出目录，带时间戳避免覆盖"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_dir = Path(model_path).parent
    return str(model_dir / f"compile_{timestamp}")


def get_model_io_info(model_path: str) -> dict:
    """获取模型的输入输出信息（快速模式，直接读取不进行 export）

    Returns:
        dict: {
            "inputs": [{"name": str, "shape": list, "dtype": str}, ...],
            "outputs": [{"name": str, "shape": list, "dtype": str}, ...]
        }
    """
    result = {"inputs": [], "outputs": []}

    if not model_path or not os.path.exists(model_path):
        return result

    try:
        assert_supported_model_suffix(model_path)
        suffix = Path(model_path).suffix.lower()
        if suffix == ".onnx":
            # 直接从 ONNX 模型读取输入输出信息，不进行耗时的 export
            import onnx
            onnx_model = onnx.load(model_path)
            assert_onnx_has_hz_calibration(onnx_model)

            # 获取输入信息
            for inp in onnx_model.graph.input:
                # 跳过初始值（如权重）
                if any(init.name == inp.name for init in onnx_model.graph.initializer):
                    continue
                shape = [d.dim_value if d.dim_value > 0 else -1 for d in inp.type.tensor_type.shape.dim]
                dtype = str(inp.type.tensor_type.elem_type)
                # 转换 dtype 为可读格式
                dtype_map = {1: "float32", 2: "uint8", 3: "int8", 6: "int32", 7: "int64", 10: "float16"}
                dtype = dtype_map.get(inp.type.tensor_type.elem_type, f"onnx_dtype_{dtype}")
                result["inputs"].append({
                    "name": inp.name,
                    "shape": shape,
                    "dtype": dtype
                })

            # 获取输出信息
            for out in onnx_model.graph.output:
                shape = [d.dim_value if d.dim_value > 0 else -1 for d in out.type.tensor_type.shape.dim]
                dtype = str(out.type.tensor_type.elem_type)
                dtype_map = {1: "float32", 2: "uint8", 3: "int8", 6: "int32", 7: "int64", 10: "float16"}
                dtype = dtype_map.get(out.type.tensor_type.elem_type, f"onnx_dtype_{dtype}")
                result["outputs"].append({
                    "name": out.name,
                    "shape": shape,
                    "dtype": dtype
                })

        elif suffix == ".bc":
            print("正在加载 BC 模型...")
            model = load_bc_model_validated(model_path)
            assert_bc_is_qat_phase(model)
            print("BC 模型加载完成（已校验为 qat.bc 阶段）")

            if not model or not model.functions:
                return result

            func = model.functions[0]

            # 获取输入信息
            for inp in func.flatten_inputs:
                shape = list(inp.type.shape) if hasattr(inp.type, 'shape') else []
                dtype = str(getattr(inp.type, 'dtype', 'unknown'))
                result["inputs"].append({
                    "name": inp.name,
                    "shape": shape,
                    "dtype": dtype
                })

            # 获取输出信息
            for out in func.flatten_outputs:
                shape = list(out.type.shape) if hasattr(out.type, 'shape') else []
                dtype = str(getattr(out.type, 'dtype', 'unknown'))
                result["outputs"].append({
                    "name": out.name,
                    "shape": shape,
                    "dtype": dtype
                })

    except (ValueError, RuntimeError):
        raise
    except Exception as e:
        raise RuntimeError(f"获取模型 IO 信息失败: {e}") from e

    return result


def generate_config_template(output_path: str = None, model_path: str = None, output_dir: str = None, ptq_config_path: str = None) -> str:
    """生成配置文件模板

    Args:
        output_path: 输出路径
        model_path: 模型路径，用于填充模板和获取模型输入输出信息
        output_dir: 编译产物目录路径，写入配置文件的 output_dir 字段
        ptq_config_path: PTQ 配置文件路径，自动提取输入预处理参数
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 处理模型路径
    model_path_value = model_path if model_path else ""

    # 获取模型输入输出信息
    io_info = get_model_io_info(model_path)

    # 打印详细信息到控制台
    if io_info["inputs"]:
        print("\n--- 模型输入节点 ---")
        for inp in io_info["inputs"]:
            print(f"  {inp['name']}: shape={inp['shape']}, dtype={inp['dtype']}")

    if io_info["outputs"]:
        print("\n--- 模型输出节点 ---")
        for out in io_info["outputs"]:
            print(f"  {out['name']}: shape={out['shape']}, dtype={out['dtype']}")

    # 生成输入节点名字列表（注释形式）
    input_names_comment = ""
    if io_info["inputs"]:
        input_names = [inp['name'] for inp in io_info["inputs"]]
        input_names_comment = f"# 可用输入节点: {input_names}"

    # 生成输出节点名字列表（注释形式）
    output_names_comment = ""
    if io_info["outputs"]:
        output_names = [out['name'] for out in io_info['outputs']]
        output_names_comment = f"# 可用输出节点: {output_names}"

    # output_dir 字段值
    output_dir_value = output_dir if output_dir else ""

    # 解析 PTQ config（如果提供）
    ptq_config = None
    march_value = "nash-e"
    opt_level_value = 2
    core_num_value = 1
    jobs_value = 32
    max_l2m_size_value = 0
    max_time_per_fc_value = 0
    cache_path_value = ""
    cache_mode_value = "enable"
    input_sources_yaml = ""
    input_sources_list = []
    # 新的节点删除配置
    remove_node_type_value = []
    remove_input_nodes_value = []
    remove_output_nodes_value = []
    preserve_input_nodes_value = []
    preserve_output_nodes_value = []

    if ptq_config_path:
        print(f"\n检测到 PTQ 配置文件，正在解析: {ptq_config_path}")
        try:
            ptq_config = parse_ptq_config(ptq_config_path)
            march_value = ptq_config["march"]
            opt_level_value = ptq_config["opt_level"]
            core_num_value = ptq_config.get("core_num", 1)
            jobs_value = ptq_config.get("jobs", 32)
            max_l2m_size_value = ptq_config.get("max_l2m_size", 0)
            max_time_per_fc_value = ptq_config.get("max_time_per_fc", 0)
            cache_path_value = ptq_config.get("cache_path") or ""
            cache_mode_value = ptq_config.get("cache_mode", "enable")

            # 节点删除配置 - 直接映射 remove_node_type
            remove_node_type_value = ptq_config.get("remove_node_types", [])
            remove_input_nodes_value = ptq_config.get("remove_input_nodes", [])

            # 打印从 PTQ config 提取的信息
            print(f"\n从 PTQ config 提取:")
            print(f"  - march: {march_value}")
            print(f"  - opt_level: {opt_level_value}")
            print(f"  - core_num: {core_num_value}")
            print(f"  - jobs: {jobs_value}")
            if cache_path_value:
                print(f"  - cache_path: {cache_path_value}")
                print(f"  - cache_mode: {cache_mode_value}")
            if max_l2m_size_value > 0:
                print(f"  - max_l2m_size: {max_l2m_size_value}")
            if max_time_per_fc_value > 0:
                print(f"  - max_time_per_fc: {max_time_per_fc_value}")

            # 打印节点删除配置
            if remove_node_type_value:
                print(f"  - remove_node_type: {remove_node_type_value}")
            if remove_input_nodes_value:
                print(f"  - remove_node_name: {remove_input_nodes_value}")

            if ptq_config["input_sources"]:
                print("  - input_sources:")
                for src in ptq_config["input_sources"]:
                    print(f"      - name: {src.name}")
                    print(f"        source_type: {src.source_type.value}")
                    print(f"        data_type: {src.data_type}")
                    if src.source_type in (InputSourceType.PYRAMID, InputSourceType.RESIZER):
                        print(f"        mean: {src.mean if src.mean is not None else 'None (无均值处理)'}")
                        print(f"        std: {src.std if src.std is not None else 'None (无标准差处理)'}")

                # PTQ 多输入已正确解析 name，无需再覆盖（parse_ptq_config 已处理）
                # 仅在单输入且 name 为空时自动匹配
                if len(ptq_config["input_sources"]) == 1 and not ptq_config["input_sources"][0].name and io_info["inputs"]:
                    ptq_src = ptq_config["input_sources"][0]
                    ptq_src.name = io_info["inputs"][0]["name"]
                    print(f"\n  自动匹配输入节点名称: {ptq_src.name}")

                input_sources_list = ptq_config["input_sources"]

                # 生成 input_sources yaml：DDR 仅 name/source_type/data_type；pyramid/resizer 按需带 mean/std/divisor
                input_sources_lines = ["input_sources:"]
                for src in input_sources_list:
                    input_sources_lines.append(f"  - name: \"{src.name}\"")
                    input_sources_lines.append(f"    source_type: \"{src.source_type.value}\"")
                    if src.source_type in (InputSourceType.PYRAMID, InputSourceType.RESIZER):
                        if src.mean is not None:
                            input_sources_lines.append(f"    mean: {src.mean}")
                        if src.std is not None:
                            input_sources_lines.append(f"    std: {src.std}")
                        if src.mean is not None or src.std is not None:
                            input_sources_lines.append(f"    divisor: {getattr(src, 'divisor', 1.0)}")
                    input_sources_lines.append(f"    data_type: \"{src.data_type}\"")
                input_sources_yaml = "\n".join(input_sources_lines)

        except Exception as e:
            print(f"警告: 解析 PTQ config 失败: {e}")
            print("将使用默认配置")

    # 构建 input_sources 部分
    if input_sources_yaml:
        input_sources_section = input_sources_yaml
    else:
        input_sources_section = f"""# input_sources:
#   - name: "input_node_name"        # 输入节点名称
#     source_type: "pyramid"           # 类型: ddr, pyramid, resizer
#     mean: [128.0, 128.0, 128.0]      # 均值
#     std: [128.0, 128.0, 128.0]       # 标准差
#     divisor: 1.0                     # 归一化除数
#     data_type: "yuv444"              # 数据格式: yuv444, rgb, bgr"""

    template = f"""# 模型编译配置文件
# 生成时间: {timestamp}
{"# PTQ 配置来源: " + ptq_config_path if ptq_config_path else ""}

# ============== 基本配置 ==============
model_path: "{model_path_value}"       # 模型路径 (.onnx 或 .bc)，必填
output_dir: "{output_dir_value}"       # 输出目录，默认为模型同级 compile_<timestamp> 文件夹
march: "{march_value}"                 # 目标平台: nash-e, nash-m, nash-p, nash-h, nash-b, nash-b-lite, nash-b-plus

# ============== 输入源配置 ==============
# 配置 pyramid/resizer 输入，支持多个输入
{input_names_comment}
{input_sources_section}

# ============== 节点删除配置 ==============
# remove_node_type: 要删除的节点类型列表
# - ["Quantize", "Dequantize", "Cast"]: 删除所有 QDQ 节点
# - ["Quantize"]: 只删除 Quantize 节点
# - []: 不删除任何节点
{output_names_comment}
remove_node_type: {remove_node_type_value}  # 要删除的节点类型，如 ["Quantize", "Dequantize", "Cast"]

# remove_input_nodes: 按名称删除输入节点相邻的 QDQ（与 remove_node_type 包含 "Quantize" 时互斥）
remove_input_nodes: {remove_input_nodes_value}

# remove_output_nodes: 按名称删除输出节点相邻的 QDQ（与 remove_node_type 包含 "Dequantize" 时互斥）
remove_output_nodes: {remove_output_nodes_value}

# preserve_input_nodes: 要保留的输入节点白名单（与 remove_node_type 包含 "Quantize" 配合使用）
preserve_input_nodes: {preserve_input_nodes_value}

# preserve_output_nodes: 要保留的输出节点白名单（与 remove_node_type 包含 "Dequantize" 配合使用）
preserve_output_nodes: {preserve_output_nodes_value}

# ============== 编译参数 ==============
debug: true                       # 开启 debug 模式，默认 true
input_no_padding: true            # 输入不填充
output_no_padding: true           # 输出不填充
enable_hpc: true                  # 开启 HPC (需要 HBDK >= 4.9.2)
enable_vpu: true                  # 开启 VPU
core_num: {core_num_value}                       # 编译核数
opt_level: {opt_level_value}                      # 优化等级
jobs: {jobs_value}                          # 并行编译数
max_l2m_size: {max_l2m_size_value}                   # 最大 L2M 大小，0 表示不限制
max_time_per_fc: {max_time_per_fc_value}                # 每个 function 最大编译时间(秒)，0 表示不限制
cache_path: "{cache_path_value}"                    # Cache 路径，为空则不启用
cache_mode: "{cache_mode_value}"              # Cache 模式: enable, disable, readonly

# ============== 性能测试配置 ==============
perf_ip: ""                       # 开发板 IP 地址，为空则 hbm_perf 不设置 remote_ip 参数
perf_username: "root"             # 开发板用户名
"""

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(template)
        print(f"配置文件模板已生成: {output_path}")

    return template


def load_config_from_yaml(config_path: str) -> CompileConfig:
    """从 YAML 文件加载配置"""
    with open(config_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    if not data:
        raise ValueError(f"配置文件为空: {config_path}")

    # 设置默认 output_dir（带时间戳）
    output_dir = data.get("output_dir")
    if not output_dir and data.get("model_path"):
        output_dir = get_default_output_dir(data["model_path"])

    # 解析 input_sources
    input_sources = []
    for src_data in data.get("input_sources", []):
        input_sources.append(InputSourceConfig.from_dict(src_data))

    config = CompileConfig(
        model_path=data.get("model_path", ""),
        output_dir=output_dir,
        march=data.get("march", "nash-e"),
        input_sources=input_sources,
        remove_node_type=data.get("remove_node_type", []),
        remove_input_nodes=data.get("remove_input_nodes", []),
        remove_output_nodes=data.get("remove_output_nodes", []),
        preserve_input_nodes=data.get("preserve_input_nodes", []),
        preserve_output_nodes=data.get("preserve_output_nodes", []),
        debug=data.get("debug", True),
        input_no_padding=data.get("input_no_padding", True),
        output_no_padding=data.get("output_no_padding", True),
        enable_hpc=data.get("enable_hpc", True),
        enable_vpu=data.get("enable_vpu", True),
        core_num=data.get("core_num", 1),
        opt_level=data.get("opt_level", 2),
        jobs=data.get("jobs", 32),
        max_l2m_size=data.get("max_l2m_size", 0),
        max_time_per_fc=data.get("max_time_per_fc", 0),
        cache_path=data.get("cache_path") or None,
        cache_mode=data.get("cache_mode", "enable"),
        perf_ip=data.get("perf_ip") or None,
        perf_username=data.get("perf_username", "root"),
        # 新增：支持用户自定义编译产物名称（默认使用模型 stem）
        output_model_file_prefix=data.get("output_model_file_prefix"),
    )

    return config


def save_config_to_yaml(config: CompileConfig, output_path: str):
    """保存配置到 YAML 文件"""
    data = config.to_dict()

    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print(f"配置已保存到: {output_path}")


# ============== 前处理代码解析 ==============

def parse_preprocess_code(code: str) -> dict:
    """
    解析前处理代码，提取 mean/std/divisor
    """
    result = {"mean": None, "std": None, "divisor": None, "scale": None}

    mean_pattern = r'mean\s*=\s*\[([^\]]+)\]'
    mean_match = re.search(mean_pattern, code)
    if mean_match:
        result["mean"] = [float(x.strip()) for x in mean_match.group(1).split(",")]

    std_pattern = r'std\s*=\s*\[([^\]]+)\]'
    std_match = re.search(std_pattern, code)
    if std_match:
        result["std"] = [float(x.strip()) for x in std_match.group(1).split(",")]

    divisor_pattern = r'/\s*(\d+\.?\d*)'
    divisor_matches = re.findall(divisor_pattern, code)
    if divisor_matches:
        result["divisor"] = float(divisor_matches[0])

    scale_pattern = r'\*\s*(\d+\.?\d*)'
    scale_matches = re.findall(scale_pattern, code)
    if scale_matches:
        result["scale"] = float(scale_matches[0])

    return result


# ============== PTQ Config 解析 ==============

def _parse_ptq_value_list(value_str, input_idx: int = 0) -> list:
    """解析 PTQ yaml 中的 mean_value/scale_value/std_value 字符串为列表

    参考 horizon_tc_ui 的 split(';')[input_idx] + json.loads 逻辑，支持多输入：
    1. 用分号分割多个输入节点的参数值
    2. 对指定 input_idx 的值，用空格/逗号/JSON 解析通道值
    3. "None" 或空值返回 None（featuremap 输入常用）
    4. 单值如 0.017 或 128 解析为 [0.017] 或 [128.0]（不自动扩展为 3 通道）

    支持格式:
    - 多输入: "128;None;123 125 136;None" -> 第0个: [128.0], 第2个: [123.0,125.0,136.0]
    - 单值: 0.017 或 128 或 "128"
    - 列表字符串: "[103.94, 116.78, 123.68]"
    - 空格/逗号: "103.94 116.78 123.68"
    """
    if value_str is None:
        return None

    if isinstance(value_str, (list, tuple)):
        return [float(v) for v in value_str]

    if isinstance(value_str, (int, float)):
        return [float(value_str)]

    s = str(value_str).strip()
    s = s.replace("'", " ").replace('"', " ").strip()
    s = s[:-1] if s.endswith(";") else s

    # 分割多输入参数，取指定索引
    if ";" in s:
        parts = [p.strip() for p in s.split(";")]
        if input_idx < len(parts):
            s = parts[input_idx]
        else:
            s = parts[0]  # 回退到第一个
    else:
        s = s

    if not s or s.lower() in ("none", "null", "n/a", ""):
        return None

    # 处理 JSON 列表格式 "[1,2,3]" 或 "[ 1, 2, 3 ]"
    if s.startswith("[") and s.endswith("]"):
        try:
            import json
            values = json.loads(s)
            if isinstance(values, (list, tuple)):
                return [float(v) for v in values]
            return [float(values)]
        except:
            pass  # 回退到字符串解析

    # 用空格/逗号分割通道值
    s = s.replace(",", " ")
    values = s.strip().split()

    result = []
    for v in values:
        if v and v.lower() not in ("none", "null"):
            try:
                result.append(float(v))
            except ValueError:
                pass

    # 关键修复：如果结果只有1个值且可能是3通道图像，自动广播为3个相同值（解决 c dim 3 vs mean size 1 错误）
    if len(result) == 1 and len(result) < 3:
        result = result * 3

    return result if result else None


def _parse_ptq_string_list(value_str) -> list:
    """解析 PTQ yaml 中的字符串列表（如 remove_node_name, remove_node_type）

    支持格式:
    - 列表: ["name1", "name2"]
    - 分号分隔: "name1;name2"
    - 单值: "name1"

    Returns:
        list of strings
    """
    if value_str is None:
        return []

    if isinstance(value_str, (list, tuple)):
        return [str(v) for v in value_str]

    s = str(value_str).strip()
    if not s:
        return []

    # 移除引号
    s = s.replace("'", " ").replace('"', " ").strip()
    # 移除末尾分号
    s = s[:-1] if s.endswith(";") else s

    # 用分号分割
    if ";" in s:
        values = [v.strip() for v in s.split(";") if v.strip()]
    else:
        values = [s] if s else []

    return values


def _scale_to_std(scale_value, input_idx: int = 0) -> list:
    """将 PTQ 的 scale_value 转换为 insert_image_preprocess 的 std

    PTQ 预处理公式: norm_data = (data - mean_value) * scale_value
    API 预处理公式: norm_data = (data - mean) / std

    转换: std = 1 / scale
    """
    scale_list = _parse_ptq_value_list(scale_value, input_idx)
    if scale_list is None:
        return None
    return [1.0 / s if s != 0 else 1.0 for s in scale_list]


def _get_norm_params_from_ptq(input_params: dict, input_idx: int = 0) -> dict:
    """根据 mean/scale/std 参数推断归一化配置（支持多输入索引）

    参考 horizon_tc_ui 的 inverse_preprocess_node_for_quantized_model 逻辑：
    - 忽略 norm_type 参数，通过 mean/scale/std 组合推断
    - scale 和 std 互斥
    - 不设置默认值，没有参数则 norm_type = no_preprocess
    - "None" 值被解析为 None（featuremap 输入常用）

    Args:
        input_params: PTQ yaml 的 input_parameters 部分
        input_idx: 当前输入的索引（用于 split(';')[input_idx]）

    Returns:
        dict: {
            "mean": list or None,
            "std": list or None,
            "norm_type": str,
        }
    """
    result = {
        "mean": None,
        "std": None,
        "norm_type": "no_preprocess",
    }

    # 解析各项参数（传入 input_idx 支持多输入）
    mean_value = input_params.get("mean_value")
    scale_value = input_params.get("scale_value")
    std_value = input_params.get("std_value")

    # scale 和 std 互斥检查（全局检查）
    if scale_value and std_value:
        raise ValueError(
            "PTQ config 中 scale_value 和 std_value 不能同时指定"
        )

    # 解析参数值（支持多输入索引）
    mean = _parse_ptq_value_list(mean_value, input_idx) if mean_value else None
    scale = _parse_ptq_value_list(scale_value, input_idx) if scale_value else None
    std = _parse_ptq_value_list(std_value, input_idx) if std_value else None

    # 参考 tc-ui 的 norm_type 推断逻辑
    if mean is not None and scale is not None:
        # data_mean_and_scale: PTQ 公式 (data - mean) * scale
        # API 公式: (data - mean) / std，所以 std = 1/scale
        result["mean"] = mean
        result["std"] = _scale_to_std(scale_value, input_idx)
        result["norm_type"] = "data_mean_and_scale"
    elif mean is not None and std is not None:
        # data_mean_and_std: PTQ 公式 (data - mean) / std
        result["mean"] = mean
        result["std"] = std
        result["norm_type"] = "data_mean_and_std"
    elif scale is not None:
        # data_scale: PTQ 公式 data * scale
        # API 公式: data / std，所以 std = 1/scale
        result["std"] = _scale_to_std(scale_value, input_idx)
        result["norm_type"] = "data_scale"
    elif std is not None:
        # data_std: PTQ 公式 data / std
        result["std"] = std
        result["norm_type"] = "data_std"
    elif mean is not None:
        # data_mean: PTQ 公式 data - mean
        result["mean"] = mean
        result["norm_type"] = "data_mean"

    return result


def _map_ptq_input_source(input_params: dict, input_idx: int = 0) -> str:
    """映射 PTQ input_parameters 到 source_type（支持多输入）

    优先级:
    1. 显式配置的 input_source
    2. 根据 input_type_rt[input_idx] 映射
    """
    # 优先使用显式配置的 input_source
    input_source = input_params.get("input_source")
    if input_source:
        if isinstance(input_source, dict):
            # input_source: {input_name: source_type}
            return list(input_source.values())[0]
        return input_source

    # 根据 input_type_rt 映射（支持多输入分号分割），严格参考 tc-ui
    input_type_rt_str = input_params.get("input_type_rt", "featuremap")
    if isinstance(input_type_rt_str, str) and ";" in str(input_type_rt_str):
        parts = [p.strip() for p in str(input_type_rt_str).split(";")]
        input_type_rt = parts[input_idx] if input_idx < len(parts) else parts[0]
    elif isinstance(input_type_rt_str, (list, tuple)):
        input_type_rt = input_type_rt_str[input_idx] if input_idx < len(input_type_rt_str) else input_type_rt_str[0]
    else:
        input_type_rt = input_type_rt_str

    type_map = {
        "nv12": "pyramid",
        "gray": "pyramid",
        "rgb": "ddr",
        "bgr": "ddr",
        "yuv444": "ddr",      # yuv444 训练数据 -> ddr (非 pyramid)
        "featuremap": "ddr",
    }
    mapped = type_map.get(str(input_type_rt).lower().strip(), "ddr")
    return mapped


def parse_ptq_config(ptq_config_path: str) -> dict:
    """解析 PTQ yaml 配置文件

    Args:
        ptq_config_path: PTQ 配置文件路径

    Returns:
        dict: {
            "march": str,
            "input_sources": [InputSourceConfig],
            "opt_level": int,
            "core_num": int,
            "jobs": int,
            "cache_path": str,
            "cache_mode": str,
            "max_l2m_size": int,
            "max_time_per_fc": int,
            "extra_params": dict,
            "remove_node_types": list,  # 直接映射 remove_node_type
            "remove_input_nodes": list,  # 直接映射 remove_node_name
            "raw_data": dict,  # 原始 PTQ 数据，用于调试
        }
    """
    with open(ptq_config_path, 'r', encoding='utf-8') as f:
        ptq_data = yaml.safe_load(f)

    result = {
        "march": "nash-e",
        "output_dir": None,  # 从 working_dir 或默认生成
        "input_sources": [],
        "opt_level": 2,
        "core_num": 1,
        "jobs": 32,
        "cache_path": None,
        "cache_mode": "enable",
        "max_l2m_size": 0,
        "max_time_per_fc": 0,
        "extra_params": {},
        "remove_node_types": [],
        "remove_input_nodes": [],
        "output_model_file_prefix": None,  # 新增：支持自定义编译产物名称
        "raw_data": ptq_data,
    }

    # 解析 model_parameters
    model_params = ptq_data.get("model_parameters", {})
    result["march"] = model_params.get("march", "nash-e")

    # 新增：映射 working_dir -> output_dir（PTQ config 常用字段）
    if "working_dir" in model_params and model_params["working_dir"]:
        result["output_dir"] = model_params["working_dir"]
    # 如果有 output_model_file_prefix，可用于后续 hbm 命名（见新需求）
    if "output_model_file_prefix" in model_params and model_params["output_model_file_prefix"]:
        result["output_model_file_prefix"] = model_params["output_model_file_prefix"]

    # 解析 remove_node_type 和 remove_node_name
    # remove_all_qdq 已不再支持（配置模板和校验逻辑中已移除）
    # 映射逻辑：
    # - remove_node_type: 直接映射到编译配置的 remove_node_type
    # - remove_node_name: 直接映射到编译配置的 remove_input_nodes
    remove_node_type = model_params.get("remove_node_type", "")
    remove_node_name = model_params.get("remove_node_name", "")

    if remove_node_type:
        # 解析 remove_node_type（分号分隔，字符串列表）
        result["remove_node_types"] = _parse_ptq_string_list(remove_node_type)

    if remove_node_name:
        # 解析 remove_node_name（分号分隔，字符串列表）
        result["remove_input_nodes"] = _parse_ptq_string_list(remove_node_name)

    # 解析 input_parameters
    input_params = ptq_data.get("input_parameters", {})

    # 支持多输入：严格参考 horizon_tc_ui 的 get_list_from_txt + get_item_from_string
    # input_name/input_type_* 使用 _parse_ptq_string_list (分号分割 + None 处理)
    # mean/scale/std 使用 _parse_ptq_value_list (支持索引 + "None" -> None)
    input_names = _parse_ptq_string_list(input_params.get("input_name", ""))
    input_type_rts = _parse_ptq_string_list(input_params.get("input_type_rt", ""))
    input_type_trains = _parse_ptq_string_list(input_params.get("input_type_train", ""))

    # 如果没有输入名称，从 PTQ 配置或默认生成
    if not input_names:
        name_str = str(input_params.get("input_name", ""))
        if ";" in name_str:
            input_names = _parse_ptq_string_list(name_str)
        else:
            input_names = ["input_0"]

    num_inputs = len(input_names)
    if num_inputs == 0:
        num_inputs = 1
        input_names = ["input_0"]

    # 为每个输入生成独立的 InputSourceConfig（严格对齐 tc-ui 逻辑）
    for i in range(num_inputs):
        name = input_names[i] if i < len(input_names) else f"input_{i}"
        source_type_str = _map_ptq_input_source(input_params, i)

        # data_type 优先使用 input_type_train 列表，否则回退
        data_type_str = input_type_trains[i] if i < len(input_type_trains) else input_params.get("input_type_train", "yuv444")
        if isinstance(data_type_str, (list, tuple)):
            data_type_str = data_type_str[0] if data_type_str else "yuv444"

        input_source = {
            "name": name,
            "source_type": source_type_str,
            "data_type": str(data_type_str).lower() if data_type_str else "yuv444",
        }

        # DDR 输入仅保留三字段；归一化与 divisor 仅适用于 pyramid/resizer
        if source_type_str in ("pyramid", "resizer"):
            norm_params = _get_norm_params_from_ptq(input_params, i)
            if norm_params.get("mean") is not None:
                input_source["mean"] = norm_params["mean"]
            if norm_params.get("std") is not None:
                input_source["std"] = norm_params["std"]
            if input_source.get("mean") is not None or input_source.get("std") is not None:
                input_source["divisor"] = 1.0

        result["input_sources"].append(InputSourceConfig.from_dict(input_source))

    # 解析 compiler_parameters
    compiler_params = ptq_data.get("compiler_parameters", {})

    # optimize_level: O2 -> 2
    opt_level_str = compiler_params.get("optimize_level", "O2")
    if isinstance(opt_level_str, str):
        result["opt_level"] = int(opt_level_str.replace("O", ""))
    else:
        result["opt_level"] = opt_level_str

    # core_num
    result["core_num"] = compiler_params.get("core_num", 1)

    # jobs
    result["jobs"] = compiler_params.get("jobs", 32)

    # cache_path
    result["cache_path"] = compiler_params.get("cache_path") or None

    # cache_mode
    result["cache_mode"] = compiler_params.get("cache_mode", "enable")

    # max_l2m_size
    result["max_l2m_size"] = compiler_params.get("max_l2m_size", 0)

    # max_time_per_fc
    result["max_time_per_fc"] = compiler_params.get("max_time_per_fc", 0)

    # extra_params (捕获其他未映射的参数，包括 working_dir 等 PTQ 字段)
    known_compiler_keys = {
        "optimize_level", "core_num", "jobs", "cache_path", "cache_mode",
        "max_l2m_size", "max_time_per_fc", "debug", "input_source"
    }
    extra_params = {}
    for key, value in compiler_params.items():
        if key not in known_compiler_keys:
            extra_params[key] = value
    result["extra_params"] = extra_params

    return result


# ============== 版本判断工具 ==============

def get_hbdk_version() -> str:
    """获取 HBDK 版本"""
    if not HBDK_AVAILABLE:
        return "unknown"
    return getattr(hbdk_version, 'VERSION', 'unknown')


def get_march_enum(march: str):
    """将 march 字符串转换为 March 枚举"""
    march_map = {
        "nash-e": March.nash_e,
        "nash-m": March.nash_m,
        "nash-p": March.nash_p,
        "nash-h": March.nash_h,
        "nash-b": March.nash_b,
        "nash-b-lite": March.nash_b_lite,
        "nash-b-plus": March.nash_b_plus,
    }
    return march_map.get(march, March.nash_e)


def supports_enable_hpc() -> bool:
    """判断是否支持 enable_hpc 参数 (HBDK >= 4.9.2)"""
    version = get_hbdk_version()
    if version == "unknown":
        return True  # 默认支持
    return version_ge(version, "4.9.2")


def supports_remove_io_op() -> bool:
    """判断是否支持 remove_io_op API"""
    version = get_hbdk_version()
    if version == "unknown":
        return True
    return version_ge(version, "4.1.3")


class _ImmediateFlushFileHandler(logging.FileHandler):
    """文件日志每次 emit 后 flush，避免默认块缓冲导致长时间编译时无法在输出目录实时查看日志。"""

    def emit(self, record):
        super().emit(record)
        self.flush()


# 节点删除：量化/反量化/Cast 与布局变换算子分属不同处理类别
QDQ_CAST_OP_TYPES = ("Quantize", "Dequantize", "Cast")
INPUT_QDQ_CAST_OP_TYPES = ("Quantize", "Cast")
OUTPUT_QDQ_CAST_OP_TYPES = ("Dequantize", "Cast")
LAYOUT_OP_TYPES = ("Reshape", "Transpose")

# 配置中的逻辑类型 -> convert 后可能出现的实际算子类型
REMOVE_OP_TYPE_ALIASES = {
    "Quantize": (
        "Quantize",
        "b30vpu.quantize",
        "b30.quantize",
        "qnt.const_fake_quant",
    ),
    "Dequantize": (
        "Dequantize",
        "b30vpu.dequantize",
        "b30.dequantize",
    ),
    "Cast": (
        "Cast",
        "hbdk.cast_type",
        "hbir.cast_type",
        "b30vpu.unary_eltwise",
    ),
}


def expand_remove_op_types(config_op_types: List[str]) -> set:
    """将配置里的 Quantize/Dequantize/Cast 展开为可匹配的实际算子类型集合。"""
    expanded = set()
    for op_type in config_op_types:
        expanded.update(REMOVE_OP_TYPE_ALIASES.get(op_type, (op_type,)))
    return expanded


def matches_remove_op_type(attached_op_type: str, config_op_types: List[str]) -> bool:
    """判断 attached_op 类型是否属于待删除的配置类型。"""
    if not config_op_types:
        return True
    op_type_str = str(attached_op_type)
    if op_type_str in expand_remove_op_types(config_op_types):
        return True
    lower = op_type_str.lower()
    for op_type in config_op_types:
        if op_type.lower() in lower:
            return True
    return False


# ============== 编译器类 ==============

class ModelCompiler:
    """通用模型编译器"""

    def __init__(self, config: CompileConfig, config_path: str = None):
        self.config = config
        self.config_path = config_path
        self.model = None
        self.quantized_model = None
        self.model_format = self._detect_model_format()

        # 确定输出目录和日志文件路径
        if self.config.output_dir:
            self.output_dir = self.config.output_dir
        else:
            self.output_dir = get_default_output_dir(self.config.model_path)
        os.makedirs(self.output_dir, exist_ok=True)

        # 设置日志（同时输出到控制台和文件）
        self.logger = self._setup_logger()

        # 复制配置文件到输出目录
        if self.config_path:
            self._copy_config_to_output()

        # 版本信息
        self.hbdk_version = get_hbdk_version()
        self._log_version_info()

    def _copy_config_to_output(self):
        """复制配置文件到输出目录"""
        import shutil
        config_name = os.path.basename(self.config_path)
        dest_path = os.path.join(self.output_dir, config_name)
        # 如果源文件和目标文件是同一个文件，跳过复制
        if os.path.abspath(self.config_path) == os.path.abspath(dest_path):
            self.logger.info(f"配置文件已在输出目录中: {dest_path}")
        else:
            shutil.copy2(self.config_path, dest_path)
            self.logger.info(f"配置文件已复制到: {dest_path}")

    def _detect_model_format(self) -> ModelFormat:
        """检测模型格式"""
        assert_supported_model_suffix(self.config.model_path)
        suffix = Path(self.config.model_path).suffix.lower()
        if suffix == ".onnx":
            return ModelFormat.ONNX
        return ModelFormat.BC

    def _setup_logger(self) -> logging.Logger:
        """设置日志（同时输出到控制台和文件）"""
        logger = logging.getLogger("ModelCompiler")
        logger.setLevel(logging.INFO)

        # 清除已有的 handlers
        logger.handlers.clear()

        # 控制台 handler
        console_handler = logging.StreamHandler()
        console_formatter = logging.Formatter("[%(levelname)s] %(message)s")
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        # 文件 handler - 使用模型名+时间戳格式
        model_name = Path(self.config.model_path).stem
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"{model_name}_{timestamp}.log"
        log_path = os.path.join(self.output_dir, log_filename)

        file_handler = _ImmediateFlushFileHandler(log_path, encoding="utf-8")
        file_formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        logger.info(f"日志文件: {log_path}")

        return logger

    def _log_version_info(self):
        """记录版本信息"""
        self.logger.info(f"HBDK 版本: {self.hbdk_version}")
        self.logger.info(f"模型格式: {self.model_format.value}")
        self.logger.info(f"目标平台: {self.config.march}")

    # ========== 模型加载 ==========

    def load_model(self):
        """加载模型"""
        if not HBDK_AVAILABLE:
            raise RuntimeError("hbdk4 未安装，无法加载模型")

        self.logger.info(f"加载模型: {self.config.model_path}")

        if self.model_format == ModelFormat.ONNX:
            self._load_onnx_model()
        else:
            self._load_bc_model()

        self.logger.info("模型加载完成")

    def _load_onnx_model(self):
        """加载 ONNX 模型"""
        from hbdk4.compiler.onnx import export
        import onnx

        onnx_model = onnx.load(self.config.model_path)
        assert_onnx_has_hz_calibration(onnx_model)
        model_name = Path(self.config.model_path).stem
        self.model = export(onnx_model, name=model_name)

    def _load_bc_model(self):
        """加载 BC 模型"""
        self.model = load_bc_model_validated(self.config.model_path)
        assert_bc_is_qat_phase(self.model)
        try:
            # 保存可视化 ONNX
            model_name = Path(self.config.model_path).stem
            qat_onnx_path = os.path.join(self.output_dir, f"{model_name}_qat.onnx")
            visualize(self.model, onnx_file=qat_onnx_path)
            self.logger.info(f"qat_bc 可视化 ONNX 已保存: {qat_onnx_path}")
        except Exception as e:
            self.logger.warning(f"可视化 ONNX 保存失败（不影响编译）: {e}")


    def _print_model_io(self, use_logger=True):
        """打印模型输入输出信息

        Args:
            use_logger: True 使用 logger（带 [INFO] 前缀），False 使用 print（干净输出）
        """
        if not self.model or not self.model.functions:
            return

        func = self.model.functions[0]

        lines = ["\n--- 原始模型输入 ---"]
        for i, inp in enumerate(func.flatten_inputs):
            shape = list(inp.type.shape) if hasattr(inp.type, 'shape') else 'unknown'
            dtype = getattr(inp.type, 'dtype', 'unknown')
            lines.append(f"  [{i}] {inp.name}: shape={shape}, dtype={dtype}")

        lines.append("\n--- 原始模型输出 ---")
        for i, out in enumerate(func.flatten_outputs):
            shape = list(out.type.shape) if hasattr(out.type, 'shape') else 'unknown'
            dtype = getattr(out.type, 'dtype', 'unknown')
            lines.append(f"  [{i}] {out.name}: shape={shape}, dtype={dtype}")
        self.logger.info("\n".join(lines))

    def _print_quantized_model_io(self):
        """打印量化模型输入输出信息（带 quant_info）"""
        if not self.quantized_model or not self.quantized_model.functions:
            return

        func = self.quantized_model.functions[0]

        lines = ["\n--- 删节点后模型输入 ---"]
        for i, inp in enumerate(func.flatten_inputs):
            shape = list(inp.type.shape) if hasattr(inp.type, 'shape') else 'unknown'
            dtype = getattr(inp.type, 'dtype', 'unknown')
            quant_info = getattr(inp, 'quant_info', '')
            lines.append(f"  [{i}] {inp.name}: shape={shape}, dtype={dtype}, quant_info={quant_info}")

        lines.append("\n--- 删节点后模型输出 ---")
        for i, out in enumerate(func.flatten_outputs):
            shape = list(out.type.shape) if hasattr(out.type, 'shape') else 'unknown'
            dtype = getattr(out.type, 'dtype', 'unknown')
            quant_info = getattr(out, 'quant_info', '')
            lines.append(f"  [{i}] {out.name}: shape={shape}, dtype={dtype}, quant_info={quant_info}")
        self.logger.info("\n".join(lines))

    def _print_hbm_io(self, hbm_func):
        """打印 HBM 输入输出信息（带 quant_info 和 strides）"""
        try:
            lines = ["\n--- HBM模型输入 ---"]
            for i, inp in enumerate(hbm_func.flatten_inputs):
                shape = list(inp.type.shape) if hasattr(inp.type, 'shape') else 'unknown'
                dtype = getattr(inp.type, 'np_dtype', 'unknown')
                quant_info = getattr(inp.type, "quant_info", None)
                strides = getattr(inp.type, '_strides', 'unknown')
                qi_str = ""
                if quant_info is not None:
                    # 与「if input.type.quant_info」一致：用 is not None，避免个别对象 __bool__ 为 False 时被误判
                    scales = getattr(quant_info, "scales", quant_info)
                    qi_str = f", scales={scales}"
                lines.append(
                    f"  [{i}] {inp.name}: shape={shape}, strides={strides}, dtype={dtype}{qi_str}"
                )

            lines.append("\n--- HBM 输出 ---")
            for i, out in enumerate(hbm_func.flatten_outputs):
                shape = list(out.type.shape) if hasattr(out.type, 'shape') else 'unknown'
                dtype = getattr(out.type, 'np_dtype', 'unknown')
                quant_info = getattr(out.type, "quant_info", None)
                strides = getattr(out.type, '_strides', 'unknown')
                qi_str = ""
                if quant_info is not None:
                    scales = getattr(quant_info, "scales", quant_info)
                    qi_str = f", scales={scales}"
                lines.append(
                    f"  [{i}] {out.name}: shape={shape}, strides={strides}, dtype={dtype}{qi_str}"
                )   
            self.logger.info("\n".join(lines))

        except Exception as e:
            self.logger.warning(f"读取 HBM IO 信息失败: {e}")

    # ========== 节点删除 ==========

    def _validate_remove_config(self):
        """校验节点删除配置的互斥规则

        当前支持的组合场景（严格互斥）：
        1. remove_node_type=["Quantize", "Dequantize", "Cast"]：删除所有 QDQ/Cast 节点（最常用）
        2. remove_node_type=["Quantize"] + preserve_input_nodes=[]：仅删除所有 Quantize 节点
        3. remove_node_type=["Quantize", "Dequantize", "Cast"] + preserve_*_nodes：QDQ/Cast 按名称删除，保留白名单
        4. remove_input_nodes=["specific_input"]：仅删除指定输入节点相邻的 Quantize（不设置 remove_node_type）
        5. 同理支持 Dequantize / remove_output_nodes / preserve_output_nodes

        **禁止组合**（会立即停止编译）：
        - remove_node_type 包含 "Quantize" 且同时提供 remove_input_nodes
        - remove_node_type 包含 "Dequantize" 且同时提供 remove_output_nodes
        - remove_node_type 包含 "Cast" 且同时提供 remove_*_nodes

        用户提供的 full_compile_config.yaml 示例中同时使用了 remove_node_type: 'Quantize' 和 remove_node_name，会触发此检查。
        """
        remove_types = set(self.config.remove_node_type)

        if "Quantize" in remove_types and self.config.remove_input_nodes:
            supported = """
支持的组合场景：
1. remove_all_qdq: true （推荐，默认删除所有QDQ）
2. remove_node_type: ["Quantize"] + preserve_input_nodes: ["要保留的输入节点名"]
3. remove_input_nodes: ["具体输入节点名"] （不设置 remove_node_type=Quantize）
4. 仅 remove_output_nodes / Dequantize 类似

请修正配置后重新编译。"""
            raise ValueError(
                f"配置冲突: remove_node_type 包含 'Quantize' 时，不能同时使用 remove_input_nodes。\n{supported}"
            )

        if "Dequantize" in remove_types and self.config.remove_output_nodes:
            supported = """
支持的组合场景：
1. remove_all_qdq: true （推荐）
2. remove_node_type: ["Dequantize"] + preserve_output_nodes: ["要保留的输出节点名"]
3. remove_output_nodes: ["具体输出节点名"] （不设置 remove_node_type=Dequantize）

请修正配置后重新编译。"""
            raise ValueError(
                f"配置冲突: remove_node_type 包含 'Dequantize' 时，不能同时使用 remove_output_nodes。\n{supported}"
            )

        if "Cast" in remove_types and (self.config.remove_input_nodes or self.config.remove_output_nodes):
            supported = """
支持的组合场景：
1. remove_all_qdq: true （推荐）
2. remove_node_type: ["Cast"] （不设置 remove_input/output_nodes）

请修正配置后重新编译。"""
            raise ValueError(
                f"配置冲突: remove_node_type 包含 'Cast' 时，不能同时使用 remove_input_nodes 或 remove_output_nodes。\n{supported}"
            )

    def _get_all_input_names(self) -> List[str]:
        """获取模型所有输入节点名称"""
        if not self.quantized_model or not self.quantized_model.functions:
            return []
        func = self.quantized_model.functions[0]
        return [inp.name for inp in func.flatten_inputs]

    def _get_all_output_names(self) -> List[str]:
        """获取模型所有输出节点名称"""
        if not self.quantized_model or not self.quantized_model.functions:
            return []
        func = self.quantized_model.functions[0]
        return [out.name for out in func.flatten_outputs]

    def _get_pyramid_resizer_names(self) -> set:
        """获取已配置为 pyramid/resizer 的输入节点名称"""
        result = set()
        for src in self.config.input_sources:
            if src.source_type in [InputSourceType.PYRAMID, InputSourceType.RESIZER]:
                result.add(src.name)
        return result

    def _get_pyramid_resizer_input_exclusions(self) -> set:
        """配置为 pyramid/resizer 的输入在图上的实际入边名（含 lowering 后的派生名）。
        本方法对当前 ``func.flatten_inputs`` 中任意满足 ``inp == base`` 或 ``inp.startswith(base + "_")``
        的入边一律视为图像源边，与根名同等对待，不参与按名删除 Quantize。
        """
        bases = self._get_pyramid_resizer_names()
        if not bases:
            return set()
        excluded: set = set()
        for inp in self._get_all_input_names():
            for b in bases:
                if inp == b or inp.startswith(b + "_"):
                    excluded.add(inp)
                    break
        return excluded

    def remove_nodes(self):
        """删除节点

        执行顺序:
        1. 校验配置互斥
        2. 处理 Quantize/Dequantize/Cast（QDQ/Cast 一类；有 preserve 白名单时按名称删除）
        3. 处理 remove_input_nodes / remove_output_nodes（按名称精确删除）
        4. 处理 Reshape/Transpose（布局类，最后按类型删除）
        """
        # 1. 校验配置互斥
        self._validate_remove_config()

        func = self.quantized_model.functions[0]
        remove_types = self.config.remove_node_type
        qdq_cast_types = [t for t in remove_types if t in QDQ_CAST_OP_TYPES]
        has_preserve = bool(self.config.preserve_input_nodes or self.config.preserve_output_nodes)

        # 2. Quantize/Dequantize/Cast 归为一类；有 preserve 白名单时按 IO 名称删除，避免误删保留边
        if qdq_cast_types:
            if has_preserve:
                input_op_types = [t for t in qdq_cast_types if t in INPUT_QDQ_CAST_OP_TYPES]
                output_op_types = [t for t in qdq_cast_types if t in OUTPUT_QDQ_CAST_OP_TYPES]
                if input_op_types:
                    self._remove_input_qdq_cast_by_name(func, input_op_types)
                if output_op_types:
                    self._remove_output_qdq_cast_by_name(func, output_op_types)
            else:
                self._remove_nodes_by_type(func, qdq_cast_types)

        # 处理 remove_input_nodes（按名称删除输入节点相邻的 Quantize）
        if self.config.remove_input_nodes:
            self._remove_input_nodes_by_name(func)

        # 处理 remove_output_nodes（按名称删除输出节点相邻的 Dequantize）
        if self.config.remove_output_nodes:
            self._remove_output_nodes_by_name(func)

        # 4. Reshape/Transpose 与 QDQ/Cast 分开，最后按类型删除
        layout_types = [t for t in remove_types if t in LAYOUT_OP_TYPES]
        if layout_types:
            self._remove_nodes_by_type(func, layout_types)

        # 保存 remove_nodes 后的模型
        model_name = Path(self.config.model_path).stem
        removed_bc_path = os.path.join(self.output_dir, f"{model_name}_removed_quantized.bc")
        save(self.quantized_model, removed_bc_path)
        self.logger.info(f"Remove_nodes 后模型已保存: {removed_bc_path}")

        # 保存可视化 ONNX
        removed_onnx_path = os.path.join(self.output_dir, f"{model_name}_removed_quantized.onnx")
        try:
            visualize(self.quantized_model, onnx_file=removed_onnx_path)
            self.logger.info(f"Remove_nodes 后可视化 ONNX 已保存: {removed_onnx_path}")
        except Exception as e:
            self.logger.warning(f"可视化 ONNX 保存失败（不影响编译）: {e}")

    def _remove_input_qdq_cast_by_name(self, func, op_types: List[str]):
        """按名称删除输入端相邻的 Quantize/Cast 节点

        逻辑:
        - 计算"其他节点" = 所有输入节点 - preserve_input_nodes - pyramid/resizer 根名及其派生入边
        - 按名称删除这些节点相邻、且类型属于 op_types 的算子
        """
        all_inputs = set(self._get_all_input_names())
        preserve = set(self.config.preserve_input_nodes)
        pyramid_resizer_inputs = self._get_pyramid_resizer_input_exclusions()

        nodes_to_remove = all_inputs - preserve - pyramid_resizer_inputs

        if not nodes_to_remove:
            self.logger.info(f"  没有需要删除 {op_types} 的输入节点")
            return

        self.logger.info(f"\n删除输入节点相邻的 {op_types}: {nodes_to_remove}")

        for io_name in nodes_to_remove:
            self._remove_op_connected_to_io(func, io_name, op_types)

    def _remove_output_qdq_cast_by_name(self, func, op_types: List[str]):
        """按名称删除输出端相邻的 Dequantize/Cast 节点

        逻辑:
        - 计算"其他节点" = 所有输出节点 - preserve_output_nodes
        - 按名称删除这些节点相邻、且类型属于 op_types 的算子
        """
        all_outputs = set(self._get_all_output_names())
        preserve = set(self.config.preserve_output_nodes)

        nodes_to_remove = all_outputs - preserve

        if not nodes_to_remove:
            self.logger.info(f"  没有需要删除 {op_types} 的输出节点")
            return

        self.logger.info(f"\n删除输出节点相邻的 {op_types}: {nodes_to_remove}")

        for io_name in nodes_to_remove:
            self._remove_op_connected_to_io(func, io_name, op_types)

    def _remove_input_nodes_by_name(self, func):
        """按名称删除输入节点相邻的 QDQ"""
        nodes = self.config.remove_input_nodes
        if not nodes:
            return

        self.logger.info(f"\n删除输入节点相邻的 QDQ: {nodes}")

        for io_name in nodes:
            self._remove_op_connected_to_io(func, io_name, "Quantize")

    def _remove_output_nodes_by_name(self, func):
        """按名称删除输出节点相邻的 QDQ"""
        nodes = self.config.remove_output_nodes
        if not nodes:
            return

        self.logger.info(f"\n删除输出节点相邻的 QDQ: {nodes}")

        for io_name in nodes:
            self._remove_op_connected_to_io(func, io_name, "Dequantize")

    def _remove_nodes_by_type(self, func, op_types: List[str]):
        """按类型删除节点"""
        self.logger.info(f"\n删除节点类型: {op_types}...")

        if supports_remove_io_op():
            try:
                func.remove_io_op(op_types=op_types)
                self.logger.info(f"  使用 remove_io_op API 删除 {op_types} 成功")
            except Exception as e:
                self.logger.warning(f"  remove_io_op 失败: {e}，尝试旧方法")
                self._remove_qdq_legacy(func, op_types)
        else:
            self._remove_qdq_legacy(func, op_types)

        self.logger.info(f"{op_types} 删除完成")

    def _remove_qdq_legacy(self, func, op_types: List[str] = None):
        """旧版本删除 quantize/dequantize"""
        if op_types is None:
            op_types = ["Quantize", "Dequantize", "Cast"]

        for args in [func.flatten_inputs, func.flatten_outputs]:
            for arg in args:
                removable, _ = arg.is_removable
                if removable:
                    attached_ops = arg.get_attached_op
                    if attached_ops:
                        op = attached_ops[0]
                        op_type_str = str(getattr(op, 'type', ''))
                        if matches_remove_op_type(op_type_str, op_types):
                            arg.remove_attached_op()
                            continue

                        # 旧版本检查 schema
                        if hasattr(op, 'schema'):
                            schema = op.schema
                            if hasattr(schema, 'namespace') and schema.namespace == "quant":
                                if hasattr(schema, 'signature') and schema.signature in ["qcast", "dcast"]:
                                    arg.remove_attached_op()

    def _remove_nodes_by_ioname(self):
        """根据输入输出节点名称删除相关算子"""
        all_nodes = list(self.config.remove_input_nodes) + list(self.config.remove_output_nodes)

        if not all_nodes:
            return

        self.logger.info(f"\n开始删除指定节点: {all_nodes}")

        func = self.quantized_model[0]
        removed_num = 0

        for io_name in all_nodes:
            removed = self._remove_op_connected_to_io(func, io_name)
            removed_num += removed

        self.logger.info(f"节点删除完成，共删除 {removed_num} 个节点")

    def _normalize_op_types(self, op_type):
        """将算子类型参数规范为 list[str] 或 None（None 表示不限制类型）。"""
        if op_type is None:
            return None
        if isinstance(op_type, str):
            return [op_type]
        return list(op_type)

    def _remove_op_connected_to_io(self, func, io_name: str, op_type=None):
        """删除与指定输入/输出节点直接相连的算子

        参考 remove_op_by_ioname 实现：
        - 遍历所有 inputs 和 outputs
        - 检查 attached_op 的输入或输出名称是否匹配 io_name
        - 如果指定了 op_type，则只删除 Quantize/Dequantize/Cast 等匹配类型的算子

        Args:
            func: 模型函数
            io_name: 输入/输出节点名称
            op_type: 可选，单个类型或类型列表（如 "Quantize" 或 ["Quantize", "Cast"]）

        Returns:
            int: 删除的节点数量
        """
        op_types = self._normalize_op_types(op_type)
        type_reason = ""

        for loc in func.flatten_inputs + func.flatten_outputs:
            # 检查是否可删除
            if not loc.is_removable[0]:
                if io_name == loc.name:
                    self.logger.warning(f"  [失败] 无法删除节点: {io_name}, 将跳过，请可视化确认模型结构是否正常")
                    return False 

            # 获取 attached_op
            if not loc.get_attached_op:
                continue
            attached_op = loc.get_attached_op[0]
            if op_types is not None and not matches_remove_op_type(attached_op.type, op_types):
                type_reason = f"算子类型不匹配: {attached_op.type}"
                continue
            removed = None
            output_name = attached_op.outputs[0].name
            input_name = attached_op.inputs[0].name

            # 检查 io_name 是否匹配 attached_op 的输入或输出
            if io_name in [output_name, input_name]:
                # 如果指定了 op_type，检查算子类型
                removed, diagnostic = loc.remove_attached_op()
                if removed:
                    self.logger.info(f"  [成功] 删除节点: {io_name}")
                    return 1
                else:
                    self.logger.warning(f"  [失败] 无法删除节点: {io_name}, 原因: {diagnostic}")
                    return 0

        # 未找到匹配的节点
        self.logger.warning(f"  [失败] 节点: {io_name}, 原因: {type_reason}")
        return 0


    # ========== 输入源配置 ==========

    def configure_input_source(self):
        """配置 pyramid/resizer 输入源"""
        if not self.config.input_sources:
            return

        self.logger.info("\n配置输入源...")

        func = self.model.functions[0]

        for inp in func.flatten_inputs[::-1]:
            for inp_config in self.config.input_sources:
                if inp.name == inp_config.name:
                    self._apply_input_source(inp, inp_config)
                    break

        self.logger.info("输入源配置完成")

    def _apply_input_source(self, input_node, config: InputSourceConfig):
        """应用输入源配置

        data_type 是训练时的数据格式 (rgb/bgr/yuv444)，决定 preprocess mode:
        - rgb -> "yuvbt601full2rgb"
        - bgr -> "yuvbt601full2bgr"
        - yuv444 -> None

        pyramid/resizer 的输入始终是 nv12 格式。
        """
        if config.data_type == "featuremap":
            self.logger.info(f"  输入 {config.name} 配置为 featuremap 模式（跳过预处理和 convert）")
            if getattr(config, 'layout_transpose', None):
                input_node = input_node.insert_transpose(config.layout_transpose)
            return

        # 非 featuremap 输入正常处理
        mode = config.get_preprocess_mode()

        if config.source_type == InputSourceType.DDR:
            if getattr(config, 'layout_transpose', None):
                input_node.insert_transpose(config.layout_transpose)
            self.logger.info(f"  输入 {config.name} 配置为 DDR 模式")

        elif config.source_type == InputSourceType.PYRAMID:
            # pyramid 输入: transpose -> preprocess -> convert(nv12)
            if len(input_node.type.shape) == 4:
                if input_node.type.shape[0] > 1:
                    # batch > 1，需要先 split 再配置
                    batch_size = input_node.type.shape[0]
                    self.logger.info(f"  输入 {config.name} batch={batch_size}，执行 split...")
                    split_inputs = input_node.insert_split(0)
                    for split_input in reversed(split_inputs):
                        self._configure_pyramid_input(split_input, config, mode)
                    self.logger.info(
                        f"  输入 {config.name} 配置为 Pyramid 模式 (split): "
                        f"mean={config.mean}, std={config.std}, divisor={config.divisor}, "
                        f"data_type={config.data_type}, mode={mode}"
                    )
                else:
                    # batch == 1，直接配置
                    self._configure_pyramid_input(input_node, config, mode)
                    self.logger.info(
                        f"  输入 {config.name} 配置为 Pyramid 模式: "
                        f"mean={config.mean}, std={config.std}, divisor={config.divisor}, "
                        f"data_type={config.data_type}, mode={mode}"
                    )
            else:
                self.logger.warning(f"  输入 {config.name} 形状 {input_node.type.shape} 不支持 Pyramid 模式")
                return
        elif config.source_type == InputSourceType.RESIZER:
            # resizer 输入: transpose -> preprocess -> roi_resize(nv12)
            if len(input_node.type.shape) == 4:
                if input_node.type.shape[0] > 1:
                    # batch > 1，需要先 split 再配置
                    batch_size = input_node.type.shape[0]
                    self.logger.info(f"  输入 {config.name} batch={batch_size}，执行 split...")
                    split_inputs = input_node.insert_split(0)
                    for split_input in reversed(split_inputs):
                        self._configure_resizer_input(split_input, config, mode)
                    self.logger.info(
                        f"  输入 {config.name} 配置为 Resizer 模式 (split): "
                        f"mean={config.mean}, std={config.std}, divisor={config.divisor}, "
                        f"data_type={config.data_type}, mode={mode}"
                    )
                else:
                    # batch == 1，直接配置
                    self._configure_resizer_input(input_node, config, mode)
                    self.logger.info(
                        f"  输入 {config.name} 配置为 Resizer 模式: "
                        f"mean={config.mean}, std={config.std}, divisor={config.divisor}, "
                        f"data_type={config.data_type}, mode={mode}"
                    )
            else:
                self.logger.warning(f"  输入 {config.name} 形状 {input_node.type.shape} 不支持 Resizer 模式")
                return

    def _configure_pyramid_input(self, input_node, config: InputSourceConfig, mode: Optional[str]):
        """配置单个 pyramid 输入节点

        如果 mean 和 std 都为 None，跳过 insert_image_preprocess（无预处理）
        """
        input_node = input_node.insert_transpose(permutes=[0, 3, 1, 2])

        # 只有当 mean 或 std 不为 None 时才插入预处理
        if config.mean is not None or config.std is not None:
            input_node = input_node.insert_image_preprocess(
                mode=mode,
                divisor=int(config.divisor),
                mean=config.mean,
                std=config.std
            )

        input_node.insert_image_convert("nv12")

    def _configure_resizer_input(self, input_node, config: InputSourceConfig, mode: Optional[str]):
        """配置单个 resizer 输入节点

        如果 mean 和 std 都为 None，跳过 insert_image_preprocess（无预处理）
        """
        input_node = input_node.insert_transpose(permutes=[0, 3, 1, 2])

        # 只有当 mean 或 std 不为 None 时才插入预处理
        if config.mean is not None or config.std is not None:
            input_node = input_node.insert_image_preprocess(
                mode=mode,
                divisor=int(config.divisor),
                mean=config.mean,
                std=config.std
            )

        input_node.insert_roi_resize("nv12")

    # ========== 模型转换与编译 ==========

    def convert_model(self):
        """转换模型到目标平台 IR"""
        self.logger.info(f"\n转换模型到 {self.config.march}...")

        march_enum = get_march_enum(self.config.march)

        self.quantized_model = convert(
            self.model,
            march=march_enum,
            enable_vpu=self.config.enable_vpu
        )
        self.logger.info("模型转换完成")

        # 保存 convert 后的模型（使用统一名称逻辑）
        if self.config.output_model_file_prefix:
            model_name = self.config.output_model_file_prefix
        else:
            model_name = Path(self.config.model_path).stem
        convert_bc_path = os.path.join(self.output_dir, f"{model_name}_converted.bc")
        save(self.quantized_model, convert_bc_path)
        self.logger.info(f"Convert 后模型已保存: {convert_bc_path}")
        
    def compile_model(self) -> Tuple[str, float]:
        """编译模型生成 HBM

        Returns:
            Tuple[str, float]: (hbm_path, compile_duration_seconds)
        """
        # 支持自定义产物名称（output_model_file_prefix）
        if self.config.output_model_file_prefix:
            model_name = self.config.output_model_file_prefix
        else:
            model_name = Path(self.config.model_path).stem
        hbm_path = os.path.join(self.output_dir, f"{model_name}.hbm")

        self.logger.info(f"编译模型到: {hbm_path}")

        # 构建编译参数
        compile_params = {
            "opt": self.config.opt_level,
            "jobs": self.config.jobs,
            "debug": self.config.debug,
            "input_no_padding": self.config.input_no_padding,
            "output_no_padding": self.config.output_no_padding,
            "progress_bar": True,
        }

        # 版本判断：是否支持特定参数
        if supports_enable_hpc():
            compile_params["enable_hpc"] = self.config.enable_hpc

        if self.config.max_l2m_size > 0:
            compile_params["max_l2m_size"] = self.config.max_l2m_size

        if self.config.max_time_per_fc > 0:
            compile_params["max_time_per_fc"] = self.config.max_time_per_fc

        if self.config.cache_path:
            compile_params["cache_path"] = self.config.cache_path
            compile_params["cache_mode"] = self.config.cache_mode

        if self.config.core_num > 1:
            compile_params["core_num"] = self.config.core_num

        # 打印编译参数
        self.logger.info("编译参数:")
        for key, value in compile_params.items():
            self.logger.info(f"  {key}: {value}")

        # 执行编译（记录耗时）
        import time
        start_time = time.time()
        march_enum = get_march_enum(self.config.march)
        compile(
            self.quantized_model,
            path=hbm_path,
            march=march_enum,
            **compile_params
        )
        end_time = time.time()
        compile_duration = end_time - start_time

        # 格式化耗时输出
        if compile_duration >= 60:
            minutes = int(compile_duration // 60)
            seconds = compile_duration % 60
            duration_str = f"{minutes} 分 {seconds:.2f} 秒"
        else:
            duration_str = f"{compile_duration:.2f} 秒"

        print(f"\n编译耗时: {duration_str}")
        self.logger.info(f"编译耗时: {duration_str}")
        self.logger.info("模型编译完成")
        return hbm_path, compile_duration

    # ========== 统计信息 ==========

    def get_statistics(self) -> Dict:
        """获取模型统计信息"""
        if not self.quantized_model:
            return {"total_ops": 0, "op_types": {}, "cpu_ops": []}

        stats = statistics(self.quantized_model, expand_fusion=True)

        result = {
            "total_ops": 0,
            "op_types": {},
            "cpu_ops": [],
        }

        for func_stats in stats:
            if isinstance(func_stats, dict):
                for op_name, count in func_stats.items():
                    result["total_ops"] += count
                    result["op_types"][op_name] = result["op_types"].get(op_name, 0) + count

                    # 检测 CPU 算子 (hbtl 前缀)
                    if op_name.startswith("hbtl"):
                        result["cpu_ops"].append(op_name)

        return result

    def check_cpu_ops(self) -> Tuple[bool, List[str]]:
        """检查是否存在 CPU 算子"""
        stats = self.get_statistics()
        cpu_ops = stats["cpu_ops"]
        return len(cpu_ops) == 0, cpu_ops

    # ========== HBM Perf ==========

    def execute_hbm_perf(self, hbm_path: str, name: str) -> Optional[str]:
        """执行 hbm_perf"""
        if not HBDK_AVAILABLE:
            self.logger.warning("hbdk4 未安装，跳过 hbm_perf")
            return None

        self.logger.info(f"\n执行 hbm_perf...")

        out_dir = Path(self.config.output_dir or ".")
        out_dir_str = str(out_dir)
        # hbdk hbm_perf 固定产出 model.html / model.json（在 output_dir 下），与 hbm 文件名无关
        perf_report_path = str(out_dir / f"{name}.html")

        try:
            if self.config.perf_ip:
                # 有 IP，设置 remote_ip 参数
                self.logger.info(f"  remote_ip: {self.config.perf_ip}")
                hbm_perf(hbm_path, output_dir=out_dir_str, remote_ip=self.config.perf_ip)
            else:
                # 无 IP，不设置 remote_ip；必须传 output_dir，否则会写到进程 cwd（常为家目录）
                hbm_perf(hbm_path, output_dir=out_dir_str)

            self.logger.info(f"  perf 报告保存到: {perf_report_path}")
            self.logger.info("hbm_perf 完成")
            return perf_report_path

        except Exception as e:
            self.logger.error(f"hbm_perf 失败: {e}")
            return None

    # ========== 完整编译流程 ==========

    def compile_full(self) -> Tuple[str, Dict]:
        """执行完整编译流程"""
        result = {
            "model_path": self.config.model_path,
            "output_dir": self.config.output_dir,
            "march": self.config.march,
            "hbdk_version": self.hbdk_version,
            "steps": [],
            "hbm_path": None,
            "statistics": None,
            "cpu_ops": [],
            "perf_report": None,
            "success": False,
            "error": None
        }

        try:
            # Step 1: 加载模型
            self.load_model()
            result["steps"].append("load_model: OK")

            # 打印原始模型输入输出（干净输出，方便用户复制）
            self._print_model_io(use_logger=False)

            # Step 2: 配置输入源
            self.configure_input_source()
            result["steps"].append("input_source: OK")

            # Step 3: 转换模型
            self.convert_model()
            result["steps"].append("convert: OK")

            # Step 4: 删除节点 (必须在 convert 之后执行)
            self.remove_nodes()
            result["steps"].append("remove_nodes: OK")

            # 打印删节点后模型输入输出（带 quant_info）
            self._print_quantized_model_io()

            # Step 5: 检查 CPU 算子
            no_cpu, cpu_ops = self.check_cpu_ops()
            result["cpu_ops"] = cpu_ops
            if not no_cpu:
                self.logger.warning(f"检测到 CPU 算子: {cpu_ops}")
            else:
                self.logger.info(f"未检测到 CPU 算子")
            result["steps"].append(f"check_cpu_ops: {'OK' if no_cpu else 'WARNING'}")

            # Step 6: 编译模型
            hbm_path, compile_duration = self.compile_model()
            result["hbm_path"] = hbm_path
            result["compile_duration"] = compile_duration
            result["steps"].append("compile: OK")

            # 打印 HBM 输入输出（带 quant_info 和 strides）
            hbm = Hbm(hbm_path)
            self._print_hbm_io(hbm[0])

            # Step 7: 获取统计信息
            result["statistics"] = self.get_statistics()

            # Step 8: hbm_perf
            perf_report = self.execute_hbm_perf(hbm_path, hbm[0].name)
            result["perf_report"] = perf_report
            result["steps"].append("hbm_perf: OK")

            result["success"] = True

        except Exception as e:
            result["error"] = str(e)
            self.logger.error(f"编译失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())

        return result["hbm_path"], result


# ============== 报告生成 ==============

def generate_compile_report(result: Dict, output_dir: str = None):
    """生成编译报告"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_name = Path(result["model_path"]).stem

    if output_dir is None:
        output_dir = result.get("output_dir", ".") or "."

    report_path = os.path.join(output_dir, f"compile_report_{model_name}_{timestamp}.md")

    # 格式化编译耗时
    compile_duration = result.get('compile_duration', 0)
    if compile_duration >= 60:
        minutes = int(compile_duration // 60)
        seconds = compile_duration % 60
        duration_str = f"{minutes} 分 {seconds:.2f} 秒"
    else:
        duration_str = f"{compile_duration:.2f} 秒"

    report_content = f"""# 模型编译报告

## 基本信息

| 项目 | 值 |
|------|-----|
| 模型路径 | {result['model_path']} |
| 输出目录 | {result.get('output_dir', 'N/A')} |
| 目标平台 | {result['march']} |
| HBDK 版本 | {result['hbdk_version']} |
| HBM 路径 | {result.get('hbm_path', 'N/A')} |
| 编译耗时 | {duration_str} |
| 编译状态 | {'成功' if result['success'] else '失败'} |

## 执行步骤

"""
    for step in result["steps"]:
        report_content += f"- {step}\n"

    if result["cpu_ops"]:
        report_content += f"""
## CPU 算子警告

检测到以下 CPU 算子:
"""
        for op in result["cpu_ops"]:
            report_content += f"- {op}\n"

    if result["statistics"] and result["statistics"]["op_types"]:
        report_content += f"""
## 算子统计

| 算子类型 | 数量 |
|----------|------|
"""
        for op_type, count in sorted(result["statistics"]["op_types"].items()):
            report_content += f"| {op_type} | {count} |\n"

    if result.get("perf_report"):
        report_content += f"""
## 性能测试报告

perf 报告路径: {result['perf_report']}
"""

    if result["error"]:
        report_content += f"""
## 错误信息

```
{result['error']}
```
"""

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    print(f"\n报告已生成: {report_path}")
    return report_path


# ============== CLI 接口 ==============

@click.command()
@click.option("-c", "--config", "config_path", help="配置文件路径 (.yaml)")
@click.option("--generate-config", is_flag=True, help="生成配置文件模板")
@click.option("-m", "--model", "model_path", help="模型路径，用于生成配置文件名")
@click.option("-o", "--output", default=None, help="生成的配置文件路径（默认根据模型名生成）")
@click.option("--ptq-config", "ptq_config_path", default=None, help="PTQ 配置文件路径 (.yaml)，自动提取输入预处理参数")
def main(config_path, generate_config, model_path, output, ptq_config_path):
    """模型编译工具"""
    if generate_config:
        # 根据模型路径生成配置文件名和编译产物目录
        if model_path:
            model_name = Path(model_path).stem
            # 创建编译产物目录（带时间戳）
            output_dir = get_default_output_dir(model_path)
            os.makedirs(output_dir, exist_ok=True)
            print(f"编译产物目录: {output_dir}")

            # 配置文件路径放到编译产物目录下
            if output is None:
                config_filename = f"compile_config_{model_name}.yaml"
            else:
                config_filename = os.path.basename(output)
            output = os.path.join(output_dir, config_filename)

            # 生成配置文件，并将 output_dir 写入配置，同时支持 PTQ config
            generate_config_template(output, model_path, output_dir, ptq_config_path)
        elif output is None:
            output = "compile_config.yaml"
            generate_config_template(output, None, None, ptq_config_path)
        else:
            generate_config_template(output, None, None, ptq_config_path)
        return

    if not config_path:
        click.echo("错误: 请指定配置文件路径 (-c config.yaml)")
        click.echo("使用 --generate-config 生成配置文件模板")
        sys.exit(1)

    if not os.path.exists(config_path):
        click.echo(f"错误: 配置文件不存在: {config_path}")
        sys.exit(1)

    # 加载配置
    config = load_config_from_yaml(config_path)

    # 验证必填字段
    if not config.model_path:
        click.echo("错误: 配置文件中 model_path 不能为空")
        sys.exit(1)

    if not os.path.exists(config.model_path):
        click.echo(f"错误: 模型文件不存在: {config.model_path}")
        sys.exit(1)

    # 检查 HBDK
    if not HBDK_AVAILABLE:
        print("错误: hbdk4 未安装")
        sys.exit(1)

    # 执行编译
    compiler = ModelCompiler(config, config_path)
    hbm_path, result = compiler.compile_full()

    # 输出结果
    print("\n" + "="*60)
    if result["success"]:
        print("编译完成!")
        print(f"HBM 路径: {hbm_path}")
        if result["cpu_ops"]:
            print(f"警告: 检测到 CPU 算子: {result['cpu_ops']}")
        if result.get("perf_report"):
            print(f"Perf 报告: {result['perf_report']}")
    else:
        print(f"编译失败: {result['error']}")
    print("="*60)

    # 生成报告
    generate_compile_report(result)

    if not result["success"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
