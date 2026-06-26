# Copyright (c) 2024 Horizon Robotics.All Rights Reserved.
#
# The material in this file is confidential and contains trade secrets
# of Horizon Robotics Inc. This is proprietary information owned by
# Horizon Robotics Inc. No part of this work may be disclosed,
# reproduced, copied, transmitted, or used in any way for any purpose,
# without the express written permission of Horizon Robotics Inc.

"""YAML 配置文件差异对比工具。

用途：
    对比两份 YAML 配置文件，输出字段级差异。
    对每个差异项尝试从 references/yaml/*.md 反查潜在影响说明。

输入：
    --input: 两个 YAML 文件路径（必填，需指定两次或使用 --base/--target）

输出：
    --format text: 人类可读的差异报告（stdout）
    --format json: 结构化 JSON 差异（stdout）
    日志信息输出到 stderr

退出码：
    0: 对比成功（无论是否有差异）
    1: 参数错误
    3: 运行时错误

示例：
    # 文本模式
    python diff_yaml.py --base old.yaml --target new.yaml

    # JSON 模式
    python diff_yaml.py --base old.yaml --target new.yaml --format json
"""

import argparse
import json
import logging
import os
import sys

try:
    import yaml
except ImportError:
    print(
        "错误: 需要 pyyaml 依赖，请确保 horizon_tc_ui 已安装",
        file=sys.stderr,
    )
    sys.exit(4)


def setup_logging(verbose: bool = False, quiet: bool = False) -> None:
    """配置日志，所有日志输出到 stderr。"""
    handler = logging.StreamHandler(sys.stderr)
    if verbose:
        handler.setLevel(logging.DEBUG)
    elif quiet:
        handler.setLevel(logging.ERROR)
    else:
        handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(handler.level)


# 潜在影响查找表（基于 references/yaml/*.md 的内容映射）
_IMPACT_MAP = {
    # model_parameters
    "model_parameters.march": (
        "更换 BPU 架构会影响所有编译参数和量化结果，需重新校准"
    ),
    "model_parameters.working_dir": (
        "更换工作目录会影响输出文件路径和缓存位置"
    ),
    "model_parameters.onnx_model": "更换模型文件会导致完全不同的编译结果",
    "model_parameters.caffe_model": "更换模型文件会导致完全不同的编译结果",
    "model_parameters.output_model_file_prefix": (
        "更换前缀会影响输出文件命名"
    ),
    "model_parameters.output_nodes": (
        "更换输出节点会改变模型输出 tensor，影响下游推理"
    ),
    "model_parameters.remove_node_type": (
        "更换移除节点类型会改变模型结构，可能影响推理精度"
    ),
    "model_parameters.remove_node_name": (
        "更换移除节点名称会改变模型结构，可能影响推理精度"
    ),
    "model_parameters.debug_mode": (
        "调试模式变更不影响编译结果，仅影响日志输出"
    ),
    "model_parameters.enable_vpu": (
        "VPU 开关影响向量运算单元的启用，可能影响性能和精度"
    ),
    "model_parameters.enable_spu": (
        "SPU 开关影响标量运算单元的启用，可能影响性能"
    ),
    # input_parameters
    "input_parameters.input_name": (
        "更换输入名称会导致与模型输入不匹配，编译失败"
    ),
    "input_parameters.input_type_rt": (
        "更换推理输入类型会影响数据预处理和 BPU 输入格式，"
        "可能影响精度"
    ),
    "input_parameters.input_type_train": (
        "更换训练输入类型会影响量化校准的数据格式"
    ),
    "input_parameters.input_layout_train": (
        "更换布局会影响通道维度的解析，可能导致数据错位"
    ),
    "input_parameters.input_shape": (
        "更换输入形状会改变模型推理的 tensor 尺寸，"
        "影响性能和内存"
    ),
    "input_parameters.input_batch": (
        "更换 batch 大小会影响推理吞吐量和内存占用"
    ),
    "input_parameters.separate_batch": (
        "separate_batch 变更会影响多输入的 batch 分配策略"
    ),
    "input_parameters.mean_value": (
        "更换均值会影响输入数据的归一化，直接影响推理精度"
    ),
    "input_parameters.scale_value": (
        "更换缩放值会影响输入数据的归一化，直接影响推理精度"
    ),
    "input_parameters.std_value": (
        "更换标准差会影响输入数据的归一化，直接影响推理精度"
    ),
    "input_parameters.input_space_and_range": (
        "更换色彩空间和范围会影响颜色转换结果"
    ),
    # calibration_parameters
    "calibration_parameters.cal_data_dir": (
        "更换校准数据集会导致不同的量化参数，影响精度"
    ),
    "calibration_parameters.calibration_type": (
        "更换校准方法（kl/max）会影响量化策略，影响精度"
    ),
    "calibration_parameters.per_channel": (
        "per_channel 开关影响量化粒度，"
        "per_channel 通常精度更好但耗时更长"
    ),
    "calibration_parameters.max_percentile": (
        "更换百分位阈值会影响量化范围裁剪，影响精度"
    ),
    "calibration_parameters.run_on_cpu": (
        "更换 CPU 运行节点列表会影响量化计算的位置"
    ),
    "calibration_parameters.run_on_bpu": (
        "更换 BPU 运行节点列表会影响量化计算的位置"
    ),
    "calibration_parameters.optimization": (
        "更换优化选项会改变校准行为（如 run_fast 跳过校准）"
    ),
    "calibration_parameters.cal_data_type": (
        "校准数据类型影响校准数据的读取方式"
    ),
    "calibration_parameters.quant_config": (
        "量化配置变更会直接影响量化策略和结果"
    ),
    # compiler_parameters
    "compiler_parameters.compile_mode": (
        "更换编译模式（latency/bandwidth/balance）"
        "会影响编译优化策略"
    ),
    "compiler_parameters.optimize_level": (
        "更换优化级别（O0/O1/O2）会影响编译优化程度和编译时间"
    ),
    "compiler_parameters.core_num": (
        "更换 BPU 核心数会影响推理并行度和性能"
    ),
    "compiler_parameters.max_time_per_fc": (
        "更换最大算子时间限制会影响编译调度策略"
    ),
    "compiler_parameters.jobs": "更换并行任务数会影响编译速度",
    "compiler_parameters.input_source": (
        "更换输入数据源（pyramid/ddr/resizer）"
        "会影响数据通路和性能"
    ),
    "compiler_parameters.advice": (
        "advice 值影响编译器优化建议的激进程度"
    ),
    "compiler_parameters.balance_factor": (
        "balance_factor 影响带宽和延迟的权衡比例"
    ),
    "compiler_parameters.debug": (
        "调试模式开关不影响编译结果，仅影响日志输出"
    ),
    "compiler_parameters.cache_mode": (
        "缓存模式影响编译缓存的复用策略"
    ),
    "compiler_parameters.cache_path": (
        "缓存路径影响编译缓存的存储位置"
    ),
    "compiler_parameters.max_l2m_size": (
        "L2M 大小限制影响编译时的内存分配策略"
    ),
    "compiler_parameters.hbdk3_compatible_mode": (
        "HBDK3 兼容模式已废弃，指定无效"
    ),
    # custom_op
    "custom_op.op_register_files": (
        "自定义算子注册文件变更影响自定义算子的可用性"
    ),
    "custom_op.custom_op_method": (
        "自定义算子方法变更影响算子注册方式"
    ),
    "custom_op.custom_op_dir": (
        "自定义算子目录变更影响自定义算子的加载"
    ),
}


def _lookup_impact(field_path: str) -> str:
    """从影响查找表中反查字段的潜在影响。"""
    # 精确匹配
    if field_path in _IMPACT_MAP:
        return _IMPACT_MAP[field_path]

    # 前缀匹配
    # 如 input_parameters.mean_value[0] -> input_parameters.mean_value
    base_path = field_path.split("[")[0]
    if base_path in _IMPACT_MAP:
        return _IMPACT_MAP[base_path]

    return "暂无已知影响说明，请人工确认"


def _flatten_dict(d: dict, parent_key: str = "", sep: str = ".") -> dict:
    """将嵌套字典展平为点分隔的键值对。"""
    items = {}
    if not isinstance(d, dict):
        return {parent_key: d}
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(_flatten_dict(v, new_key, sep=sep))
        else:
            items[new_key] = v
    return items


def diff_yaml(base_path: str, target_path: str) -> dict:
    """对比两份 YAML 文件的差异。

    Args:
        base_path: 基准 YAML 文件路径
        target_path: 目标 YAML 文件路径

    Returns:
        包含差异结果的字典
    """
    result = {
        "status": "success",
        "exit_code": 0,
        "message": "对比成功",
        "data": {
            "base": base_path,
            "target": target_path,
            "diffs": [],
        },
        "errors": [],
    }

    # 检查文件
    for path, label in [(base_path, "基准文件"), (target_path, "目标文件")]:
        if not os.path.isfile(path):
            result["status"] = "error"
            result["exit_code"] = 3
            result["message"] = f"{label}不存在: {path}"
            result["errors"].append({
                "field": "_file",
                "expected": f"存在的{label}",
                "actual": f"文件不存在: {path}",
                "suggestion": f"请检查{label}路径是否正确",
            })
            return result

    try:
        with open(base_path, encoding="utf-8") as f:
            base_data = yaml.safe_load(f) or {}
        with open(target_path, encoding="utf-8") as f:
            target_data = yaml.safe_load(f) or {}
    except Exception as e:
        result["status"] = "error"
        result["exit_code"] = 3
        result["message"] = f"解析 YAML 失败: {e}"
        result["errors"].append({
            "field": "_parse",
            "expected": "合法的 YAML 格式",
            "actual": str(e),
            "suggestion": "请检查 YAML 文件格式",
        })
        return result

    base_flat = _flatten_dict(base_data)
    target_flat = _flatten_dict(target_data)

    all_keys = sorted(set(list(base_flat.keys()) + list(target_flat.keys())))
    diffs = []

    for key in all_keys:
        base_val = base_flat.get(key)
        target_val = target_flat.get(key)

        if base_val == target_val:
            continue

        # 将值转为可序列化的字符串
        base_str = str(base_val) if base_val is not None else "(未设置)"
        target_str = str(target_val) if target_val is not None else "(未设置)"

        change_type = "modified"
        if base_val is None:
            change_type = "added"
        elif target_val is None:
            change_type = "removed"

        impact = _lookup_impact(key)

        diffs.append({
            "field": key,
            "change_type": change_type,
            "base_value": base_str,
            "target_value": target_str,
            "potential_impact": impact,
        })

    result["data"]["diffs"] = diffs
    result["data"]["stats"] = {
        "total_diffs": len(diffs),
        "added": sum(1 for d in diffs if d["change_type"] == "added"),
        "removed": sum(1 for d in diffs if d["change_type"] == "removed"),
        "modified": sum(1 for d in diffs if d["change_type"] == "modified"),
    }

    return result


def format_text(result: dict) -> str:
    """将结果格式化为文本输出。"""
    lines = []
    data = result.get("data", {})

    if result["status"] != "success":
        lines.append(f"对比失败: {result['message']}")
        return "\n".join(lines)

    base = data.get("base", "?")
    target = data.get("target", "?")
    diffs = data.get("diffs", [])
    stats = data.get("stats", {})

    lines.append("=== YAML 差异对比 ===")
    lines.append(f"  基准: {base}")
    lines.append(f"  目标: {target}")
    lines.append("")

    if not diffs:
        lines.append("  两份配置文件完全一致，无差异")
        return "\n".join(lines)

    lines.append(
        f"  差异统计: 共 {stats['total_diffs']} 处差异"
        f"（新增 {stats['added']} / "
        f"删除 {stats['removed']} / "
        f"修改 {stats['modified']}）"
    )
    lines.append("")

    change_type_map = {
        "added": "新增",
        "removed": "删除",
        "modified": "修改",
    }

    for d in diffs:
        ct = change_type_map.get(d["change_type"], d["change_type"])
        lines.append(f"  [{ct}] {d['field']}")
        lines.append(f"    基准值: {d['base_value']}")
        lines.append(f"    目标值: {d['target_value']}")
        lines.append(f"    潜在影响: {d['potential_impact']}")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    """主函数入口。"""
    parser = argparse.ArgumentParser(
        description="YAML 配置文件差异对比工具，输出字段级差异并反查潜在影响",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  %(prog)s --base old.yaml --target new.yaml
  %(prog)s --base old.yaml --target new.yaml --format json
        """,
    )
    parser.add_argument(
        "--base",
        required=True,
        help="基准 YAML 文件路径",
    )
    parser.add_argument(
        "--target",
        required=True,
        help="目标 YAML 文件路径",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="输出格式：text 或 json，默认 text",
    )
    parser.add_argument(
        "-v",
        action="store_true",
        default=False,
        help="详细模式",
    )
    parser.add_argument(
        "-q",
        action="store_true",
        default=False,
        help="静默模式",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 1.0.0",
    )

    args = parser.parse_args()
    setup_logging(verbose=args.v, quiet=args.q)

    result = diff_yaml(args.base, args.target)

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_text(result))

    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
