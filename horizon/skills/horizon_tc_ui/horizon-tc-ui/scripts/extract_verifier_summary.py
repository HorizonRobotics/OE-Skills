# Copyright (c) 2024 Horizon Robotics.All Rights Reserved.
#
# The material in this file is confidential and contains trade secrets
# of Horizon Robotics Inc. This is proprietary information owned by
# Horizon Robotics Inc. No part of this work may be disclosed,
# reproduced, copied, transmitted, or used in any way for any purpose,
# without the express written permission of Horizon Robotics Inc.

"""hb_verifier 输出摘要提取工具。

用途：
    解析 hb_verifier 控制台输出或日志文件，提取每个输出 tensor 的
    cosine similarity 和 consistency 值，生成汇总表。
    低于阈值的项标红提示。

    注意：本工具不做深度分析，深度分析请委托给 horizon-model-cosine-analyzer。

输入：
    --input: hb_verifier 日志文件路径（必填）

输出：
    --format text: 汇总表（stdout）
    --format json: 结构化 JSON 报告（stdout）
    日志信息输出到 stderr

退出码：
    0: 解析成功
    1: 参数错误
    3: 运行时错误

示例：
    # 文本模式
    python extract_verifier_summary.py --input hb_verifier.log

    # JSON 模式
    python extract_verifier_summary.py --input hb_verifier.log --format json

    # 自定义阈值
    python extract_verifier_summary.py --input hb_verifier.log --threshold 0.99
"""

import argparse
import json
import logging
import os
import re
import sys


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


# ANSI 颜色码（用于终端标红）
_ANSI_RED = "\033[91m"
_ANSI_RESET = "\033[0m"


def parse_verifier_log(log_path: str, threshold: float = 0.99) -> dict:
    """解析 hb_verifier 日志文件。

    Args:
        log_path: 日志文件路径
        threshold: cosine/consistency 阈值，低于此值标红

    Returns:
        包含解析结果的字典
    """
    result = {
        "status": "success",
        "exit_code": 0,
        "message": "解析成功",
        "data": {
            "threshold": threshold,
            "tensors": [],
            "summary": {},
        },
        "errors": [],
    }

    if not os.path.isfile(log_path):
        result["status"] = "error"
        result["exit_code"] = 3
        result["message"] = f"文件不存在: {log_path}"
        result["errors"].append({
            "field": "_file",
            "expected": "存在的日志文件",
            "actual": f"文件不存在: {log_path}",
            "suggestion": "请检查日志文件路径是否正确",
        })
        return result

    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            content = f.read()
            lines = content.splitlines()
    except Exception as e:
        result["status"] = "error"
        result["exit_code"] = 3
        result["message"] = f"读取文件失败: {e}"
        result["errors"].append({
            "field": "_file",
            "expected": "可读的日志文件",
            "actual": f"读取失败: {e}",
            "suggestion": "请检查文件权限",
        })
        return result

    tensors = result["data"]["tensors"]

    # 匹配 cosine similarity 行
    # 常见格式: "cosine similarity: 0.9998" 或 "cosine: 0.9998"
    cosine_pattern = re.compile(
        r"(?:cosine\s*(?:similarity)?|cos)\s*[:=]\s*([\d.]+)",
        re.IGNORECASE,
    )

    # 匹配 consistency 行
    # 常见格式: "consistency: 0.9995" 或 "consistency ratio: 0.9995"
    consistency_pattern = re.compile(
        r"consistency\s*(?:ratio)?\s*[:=]\s*([\d.]+)",
        re.IGNORECASE,
    )

    # 匹配 tensor/output 名称
    # 常见格式: "output: tensor_name" 或 "tensor: name" 或 "output_name"
    tensor_name_pattern = re.compile(
        r"(?:output|tensor|layer)\s*(?:name)?\s*[:=]\s*(\S+)",
        re.IGNORECASE,
    )

    # 匹配完整的比较结果行（包含名称和数值）
    # 格式如: "output_name  cosine: 0.9998  consistency: 0.9995"
    combined_pattern = re.compile(
        r"(\S+)\s+.*?cosine\s*[:=]\s*([\d.]+)",
        re.IGNORECASE,
    )

    current_tensor = None
    current_cosine = None
    current_consistency = None

    for line_num, line in enumerate(lines, 1):
        line_stripped = line.strip()

        # 尝试提取 tensor 名称
        name_match = tensor_name_pattern.search(line_stripped)
        if name_match:
            # 如果之前有未保存的 tensor，先保存
            if current_tensor and (
                current_cosine is not None
                or current_consistency is not None
            ):
                tensors.append({
                    "name": current_tensor,
                    "cosine": current_cosine,
                    "consistency": current_consistency,
                    "below_threshold": (
                        (
                            current_cosine is not None
                            and current_cosine < threshold
                        )
                        or (
                            current_consistency is not None
                            and current_consistency < threshold
                        )
                    ),
                })
            current_tensor = name_match.group(1)
            current_cosine = None
            current_consistency = None

        # 尝试提取 cosine 值
        cos_match = cosine_pattern.search(line_stripped)
        if cos_match:
            val = float(cos_match.group(1))
            if current_tensor:
                current_cosine = val
            else:
                # 尝试从同一行提取名称
                comb_match = combined_pattern.search(line_stripped)
                if comb_match:
                    current_tensor = comb_match.group(1)
                    current_cosine = val
                else:
                    current_tensor = f"_unknown_{line_num}"
                    current_cosine = val

        # 尝试提取 consistency 值
        con_match = consistency_pattern.search(line_stripped)
        if con_match:
            val = float(con_match.group(1))
            if current_tensor:
                current_consistency = val
            else:
                current_tensor = f"_unknown_{line_num}"
                current_consistency = val

    # 保存最后一个 tensor
    if current_tensor and (
        current_cosine is not None
        or current_consistency is not None
    ):
        tensors.append({
            "name": current_tensor,
            "cosine": current_cosine,
            "consistency": current_consistency,
            "below_threshold": (
                (
                    current_cosine is not None
                    and current_cosine < threshold
                )
                or (
                    current_consistency is not None
                    and current_consistency < threshold
                )
            ),
        })

    # 生成摘要统计
    below_count = sum(1 for t in tensors if t["below_threshold"])
    cosine_values = [
        t["cosine"] for t in tensors if t["cosine"] is not None
    ]
    consistency_values = [
        t["consistency"]
        for t in tensors
        if t["consistency"] is not None
    ]

    result["data"]["summary"] = {
        "total_tensors": len(tensors),
        "below_threshold_count": below_count,
        "pass_count": len(tensors) - below_count,
        "cosine_min": min(cosine_values) if cosine_values else None,
        "cosine_max": max(cosine_values) if cosine_values else None,
        "cosine_avg": (
            sum(cosine_values) / len(cosine_values)
            if cosine_values else None
        ),
        "consistency_min": (
            min(consistency_values) if consistency_values else None
        ),
        "consistency_max": (
            max(consistency_values) if consistency_values else None
        ),
        "consistency_avg": (
            sum(consistency_values) / len(consistency_values)
            if consistency_values else None
        ),
    }

    if not tensors:
        logging.warning("未在日志中找到 cosine/consistency 数据")
        result["data"]["summary"]["note"] = (
            "未找到有效数据，"
            "请确认日志内容是否包含 verifier 比较结果"
        )

    return result


def format_text(result: dict, use_color: bool = True) -> str:
    """将结果格式化为文本汇总表。"""
    lines = []
    data = result.get("data", {})

    if result["status"] != "success":
        lines.append(f"解析失败: {result['message']}")
        return "\n".join(lines)

    threshold = data.get("threshold", 0.99)
    tensors = data.get("tensors", [])
    summary = data.get("summary", {})

    lines.append(f"=== hb_verifier 汇总表（阈值: {threshold}）===")
    lines.append("")

    if not tensors:
        lines.append("  未找到有效的 tensor 比较数据")
        note = summary.get("note", "")
        if note:
            lines.append(f"  备注: {note}")
        return "\n".join(lines)

    # 表头
    header = (
        f"  {'Tensor 名称':<40}"
        f" {'Cosine':>10}"
        f" {'Consistency':>12}"
        f" {'状态':>8}"
    )
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))

    for t in tensors:
        name = t["name"][:38]
        cosine = (
            f"{t['cosine']:.6f}"
            if t["cosine"] is not None
            else "N/A"
        )
        consistency = (
            f"{t['consistency']:.6f}"
            if t["consistency"] is not None
            else "N/A"
        )
        status = "FAIL" if t["below_threshold"] else "PASS"

        if t["below_threshold"] and use_color:
            line = (
                f"  {_ANSI_RED}{name:<40}"
                f" {cosine:>10}"
                f" {consistency:>12}"
                f" {status:>8}{_ANSI_RESET}"
            )
        else:
            marker = " *" if t["below_threshold"] else ""
            line = (
                f"  {name:<40}"
                f" {cosine:>10}"
                f" {consistency:>12}"
                f" {status:>8}{marker}"
            )

        lines.append(line)

    lines.append("")

    # 摘要
    lines.append("=== 统计摘要 ===")
    lines.append(f"  总 tensor 数:      {summary.get('total_tensors', 0)}")
    lines.append(f"  通过数:            {summary.get('pass_count', 0)}")
    lines.append(
        f"  低于阈值数:        "
        f"{summary.get('below_threshold_count', 0)}"
    )
    if summary.get("cosine_min") is not None:
        lines.append(f"  Cosine 最小值:     {summary['cosine_min']:.6f}")
        lines.append(f"  Cosine 最大值:     {summary['cosine_max']:.6f}")
        lines.append(f"  Cosine 平均值:     {summary['cosine_avg']:.6f}")
    if summary.get("consistency_min") is not None:
        lines.append(f"  Consistency 最小值: {summary['consistency_min']:.6f}")
        lines.append(f"  Consistency 最大值: {summary['consistency_max']:.6f}")
        lines.append(f"  Consistency 平均值: {summary['consistency_avg']:.6f}")

    lines.append("")
    lines.append("注: 标 * 或 FAIL 的项低于设定阈值")
    lines.append("注: 深度分析请使用 horizon-model-cosine-analyzer")

    return "\n".join(lines)


def main() -> int:
    """主函数入口。"""
    parser = argparse.ArgumentParser(
        description=(
            "hb_verifier 输出摘要提取工具，"
            "提取 cosine/consistency 值并生成汇总表"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  %(prog)s --input hb_verifier.log
  %(prog)s --input hb_verifier.log --format json
  %(prog)s --input hb_verifier.log --threshold 0.995
        """,
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="hb_verifier 日志文件路径",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="输出格式：text（汇总表）或 json（结构化报告），默认 text",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.99,
        help="cosine/consistency 阈值，低于此值标红，默认 0.99",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        default=False,
        help="禁用 ANSI 颜色输出",
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

    result = parse_verifier_log(args.input, threshold=args.threshold)

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_text(result, use_color=not args.no_color))

    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
