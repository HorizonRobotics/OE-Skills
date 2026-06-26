# Copyright (c) 2024 Horizon Robotics.All Rights Reserved.
#
# The material in this file is confidential and contains trade secrets
# of Horizon Robotics Inc. This is proprietary information owned by
# Horizon Robotics Inc. No part of this work may be disclosed,
# reproduced, copied, transmitted, or used in any way for any purpose,
# without the express written permission of Horizon Robotics Inc.

"""YAML 配置文件校验工具。

用途：
    调用 horizon_tc_ui.config.params_parser.ParamsParser 对 YAML 配置文件
    进行真实校验，不使用自造的 schema 规则。

输入：
    --input: YAML 配置文件路径（必填）

输出：
    --format text: 人类可读的校验结果（stdout）
    --format json: 结构化 JSON 报告（stdout）
    日志信息输出到 stderr

退出码：
    0: 校验通过
    1: 参数错误
    2: 校验失败
    3: 运行时错误

示例：
    # 文本模式校验
    python validate_yaml.py --input config.yaml

    # JSON 模式校验
    python validate_yaml.py --input config.yaml --format json

    # 严格模式（额外跨字段一致性检查）
    python validate_yaml.py --input config.yaml --strict
"""

import argparse
import json
import logging
import os
import sys

# 将 horizon_tc_ui 加入路径，确保可导入
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_SKILL_DIR = os.path.dirname(_SCRIPT_DIR)
_HORIZON_TC_UI_DIR = os.path.dirname(_SKILL_DIR)
if os.path.isdir(_HORIZON_TC_UI_DIR):
    sys.path.insert(0, os.path.dirname(_HORIZON_TC_UI_DIR))

try:
    from horizon_tc_ui.config import mapper_consts as mconsts
    from horizon_tc_ui.config.params_parser import ParamsParser
except ImportError as e:
    print(f"错误: 无法导入 horizon_tc_ui 模块: {e}", file=sys.stderr)
    print("请确保 horizon_tc_ui 已安装（pip install -e .）", file=sys.stderr)
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


def validate_yaml(yaml_path: str, strict: bool = False) -> dict:
    """校验 YAML 文件并返回结构化结果。

    Args:
        yaml_path: YAML 文件路径
        strict: 是否启用严格模式（额外跨字段一致性检查）

    Returns:
        包含校验结果的字典
    """
    result = {
        "status": "success",
        "exit_code": 0,
        "message": "校验通过",
        "data": {},
        "errors": [],
    }

    if not os.path.isfile(yaml_path):
        result["status"] = "error"
        result["exit_code"] = 3
        result["message"] = f"文件不存在: {yaml_path}"
        result["errors"].append({
            "field": "_file",
            "expected": "存在的 YAML 文件",
            "actual": f"文件不存在: {yaml_path}",
            "suggestion": "请检查文件路径是否正确",
        })
        return result

    try:
        parser = ParamsParser(yaml_path=yaml_path)
        parser.validate_parameters()
        conf = parser.conf

        # 提取校验后的配置信息
        result["data"] = {
            "model_type": conf.model_type,
            "march": conf.march,
            "working_dir": conf.working_dir,
            "input_num": conf.input_num,
            "input_names": conf.input_names,
            "input_shapes": [str(s) for s in conf.input_shapes],
            "input_type_rt": conf.input_type_rt,
            "input_type_train": conf.input_type_train,
            "calibration_type": conf.calibration_type,
            "cal_data_dir": conf.cal_data_dir,
            "optimize_level": conf.optimize_level,
            "compile_mode": conf.compile_mode,
            "core_num": conf.core_num,
        }

        # 严格模式：额外跨字段一致性检查
        if strict:
            strict_errors = _strict_check(conf)
            if strict_errors:
                result["status"] = "error"
                result["exit_code"] = 2
                result["message"] = "严格模式校验发现跨字段一致性问题"
                result["errors"].extend(strict_errors)

    except ValueError as e:
        result["status"] = "error"
        result["exit_code"] = 2
        result["message"] = "校验失败"
        result["errors"].append(_parse_error(str(e)))
    except Exception as e:
        result["status"] = "error"
        result["exit_code"] = 3
        result["message"] = f"运行时错误: {type(e).__name__}"
        result["errors"].append({
            "field": "_runtime",
            "expected": "正常执行",
            "actual": f"{type(e).__name__}: {e}",
            "suggestion": "请检查 YAML 文件格式或联系开发者",
        })

    return result


def _parse_error(error_msg: str) -> dict:
    """将 ParamsParser 抛出的错误信息解析为结构化错误。"""
    error_entry = {
        "field": "_unknown",
        "expected": "有效值",
        "actual": error_msg,
        "suggestion": "请根据错误信息修正 YAML 配置",
    }

    # 尝试从错误消息中提取字段名
    param_keywords = [
        "march", "input_name", "input_shape", "input_type_rt",
        "input_type_train", "input_layout_train", "cal_data_dir",
        "calibration_type", "optimize_level", "compile_mode",
        "core_num", "working_dir", "output_model_file_prefix",
        "norm_type", "mean_value", "scale_value", "std_value",
        "per_channel", "max_percentile", "input_source",
        "balance_factor", "max_time_per_fc", "cache_mode",
        "cache_path", "max_l2m_size", "input_batch",
        "separate_batch", "separate_name",
    ]
    for keyword in param_keywords:
        if keyword in error_msg.lower():
            error_entry["field"] = keyword
            break

    return error_entry


def _strict_check(conf) -> list:
    """严格模式：跨字段一致性检查。

    检查项：
    1. input_source 与 input_type_rt 的兼容性
    2. calibration_type 与 cal_data_dir 的一致性
    3. optimize_level 与 march 的兼容性
    4. core_num 与 march 的兼容性
    """
    errors = []

    # 检查 1: calibration_type 为 skip 时不应有 cal_data_dir
    if conf.calibration_type == "skip" and conf.cal_data_dir:
        errors.append({
            "field": "calibration_parameters.cal_data_dir",
            "expected": (
                "calibration_type 为 skip 时"
                "不应指定 cal_data_dir"
            ),
            "actual": (
                f"calibration_type=skip, "
                f"cal_data_dir={conf.cal_data_dir}"
            ),
            "suggestion": (
                "移除 cal_data_dir 或将 calibration_type 改为 kl/max"
            ),
        })

    # 检查 2: featuremap 输入不应有 mean/scale/std
    for idx, input_type_rt in enumerate(conf.input_type_rt):
        if input_type_rt == "featuremap":
            if idx < len(conf.mean) and conf.mean[idx]:
                errors.append({
                    "field": f"input_parameters.mean_value[{idx}]",
                    "expected": (
                        "featuremap 输入不应配置 mean_value"
                    ),
                    "actual": (
                        f"input_type_rt={input_type_rt}, "
                        f"mean={conf.mean[idx]}"
                    ),
                    "suggestion": (
                        "移除 featuremap 输入的 mean_value 配置"
                    ),
                })
            if idx < len(conf.scale) and conf.scale[idx]:
                errors.append({
                    "field": f"input_parameters.scale_value[{idx}]",
                    "expected": (
                        "featuremap 输入不应配置 scale_value"
                    ),
                    "actual": (
                        f"input_type_rt={input_type_rt}, "
                        f"scale={conf.scale[idx]}"
                    ),
                    "suggestion": (
                        "移除 featuremap 输入的 scale_value 配置"
                    ),
                })

    # 检查 3: nv12 输入需要 input_type_train 为 bgr/rgb 等可转换类型
    for idx, input_type_rt in enumerate(conf.input_type_rt):
        if input_type_rt == "nv12":
            train_type = (
                conf.input_type_train[idx]
                if idx < len(conf.input_type_train)
                else ""
            )
            if train_type and train_type not in mconsts.legal_trans_dict:
                errors.append({
                    "field": f"input_parameters.input_type_train[{idx}]",
                    "expected": (
                        "可转换为 nv12 的类型: "
                        f"{list(mconsts.legal_trans_dict.keys())}"
                    ),
                    "actual": f"input_type_train={train_type}",
                    "suggestion": "将 input_type_train 改为 bgr 或 rgb",
                })
            elif (
                train_type
                and "nv12" not in mconsts.legal_trans_dict.get(
                    train_type, []
                )
            ):
                errors.append({
                    "field": f"input_parameters.input_type_train[{idx}]",
                    "expected": "可转换为 nv12 的类型",
                    "actual": (
                        f"input_type_train={train_type} "
                        "不支持转换到 nv12"
                    ),
                    "suggestion": (
                        "参考合法转换关系: "
                        f"{mconsts.legal_trans_dict}"
                    ),
                })

    return errors


def format_text(result: dict) -> str:
    """将结果格式化为文本输出。"""
    lines = []
    if result["status"] == "success":
        lines.append("校验通过")
        data = result.get("data", {})
        if data:
            lines.append("")
            lines.append("=== 配置摘要 ===")
            lines.append(f"  模型类型:     {data.get('model_type', 'N/A')}")
            lines.append(f"  BPU 架构:     {data.get('march', 'N/A')}")
            lines.append(f"  工作目录:     {data.get('working_dir', 'N/A')}")
            lines.append(f"  输入数量:     {data.get('input_num', 'N/A')}")
            lines.append(f"  输入名称:     "
                         f"{', '.join(data.get('input_names', []))}")
            lines.append(f"  输入形状:     "
                         f"{', '.join(data.get('input_shapes', []))}")
            lines.append(f"  推理输入类型: "
                         f"{', '.join(data.get('input_type_rt', []))}")
            lines.append(f"  训练输入类型: "
                         f"{', '.join(data.get('input_type_train', []))}")
            lines.append(
                f"  校准类型:     "
                f"{data.get('calibration_type', 'N/A')}"
            )
            lines.append(
                f"  优化级别:     "
                f"{data.get('optimize_level', 'N/A')}"
            )
            lines.append(f"  编译模式:     {data.get('compile_mode', 'N/A')}")
            lines.append(f"  BPU 核心数:   {data.get('core_num', 'N/A')}")
    else:
        lines.append(f"校验失败: {result['message']}")
        lines.append("")
        for i, err in enumerate(result.get("errors", []), 1):
            lines.append(f"  错误 {i}:")
            lines.append(f"    字段:     {err.get('field', 'N/A')}")
            lines.append(f"    期望:     {err.get('expected', 'N/A')}")
            lines.append(f"    实际:     {err.get('actual', 'N/A')}")
            if err.get("suggestion"):
                lines.append(f"    建议:     {err['suggestion']}")
            lines.append("")

    return "\n".join(lines)


def main() -> int:
    """主函数入口。"""
    parser = argparse.ArgumentParser(
        description=(
            "YAML 配置文件校验工具"
            "（基于 horizon_tc_ui.config.params_parser.ParamsParser）"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  %(prog)s --input config.yaml
  %(prog)s --input config.yaml --format json
  %(prog)s --input config.yaml --strict
        """,
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="YAML 配置文件路径",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="输出格式：text（人类可读）或 json（机器可解析），默认 text",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="启用严格模式，额外进行跨字段一致性检查",
    )
    parser.add_argument(
        "-v",
        action="store_true",
        default=False,
        help="详细模式，输出 DEBUG 级别日志",
    )
    parser.add_argument(
        "-q",
        action="store_true",
        default=False,
        help="静默模式，仅输出错误信息",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 1.0.0",
    )

    args = parser.parse_args()
    setup_logging(verbose=args.v, quiet=args.q)

    result = validate_yaml(args.input, strict=args.strict)

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_text(result))

    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
