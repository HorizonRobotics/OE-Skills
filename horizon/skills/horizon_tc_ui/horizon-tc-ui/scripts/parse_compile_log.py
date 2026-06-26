# Copyright (c) 2024 Horizon Robotics.All Rights Reserved.
#
# The material in this file is confidential and contains trade secrets
# of Horizon Robotics Inc. This is proprietary information owned by
# Horizon Robotics Inc. No part of this work may be disclosed,
# reproduced, copied, transmitted, or used in any way for any purpose,
# without the express written permission of Horizon Robotics Inc.

"""hb_compile.log 解析工具。

用途：
    解析 hb_compile 编译日志，抽取阶段时间线（export/convert/compile）、
    warnings、errors、quantize summary、编译器 advice 等信息。

输入：
    --input: hb_compile.log 文件路径（必填）

输出：
    --format text: 精简摘要（stdout）
    --format json: 完整 JSON 报告（stdout）
    日志信息输出到 stderr

退出码：
    0: 解析成功
    1: 参数错误
    3: 运行时错误（文件不存在、解析失败等）

示例：
    # 文本模式
    python parse_compile_log.py --input hb_compile.log

    # JSON 模式
    python parse_compile_log.py --input hb_compile.log --format json
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


def parse_compile_log(log_path: str) -> dict:
    """解析 hb_compile.log 文件。

    Args:
        log_path: 日志文件路径

    Returns:
        包含解析结果的字典
    """
    result = {
        "status": "success",
        "exit_code": 0,
        "message": "解析成功",
        "data": {
            "phases": [],
            "warnings": [],
            "errors": [],
            "quantize_summary": {},
            "compiler_advice": [],
            "version_info": {},
            "timeline": {},
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
            lines = f.readlines()
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

    data = result["data"]
    current_phase = None
    phase_start_time = None

    # 阶段关键词映射
    phase_patterns = {
        "export": re.compile(r"(?:start|starting).*export", re.IGNORECASE),
        "convert": re.compile(r"(?:start|starting).*convert", re.IGNORECASE),
        "quantize": re.compile(r"(?:start|starting).*quantiz", re.IGNORECASE),
        "compile": re.compile(r"(?:start|starting).*compil", re.IGNORECASE),
        "perf": re.compile(r"(?:start|starting).*perf", re.IGNORECASE),
    }

    # 时间戳模式: [2024-01-01 12:00:00,000] 或 2024-01-01 12:00:00
    time_pattern = re.compile(
        r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:,\d{3})?)"
    )

    # 版本信息
    version_patterns = {
        "hbdk_version": re.compile(
            r"hbdk\s*version[:\s]+(\S+)", re.IGNORECASE
        ),
        "hmct_version": re.compile(
            r"hmct\s*version[:\s]+(\S+)", re.IGNORECASE
        ),
        "hb_compile_version": re.compile(
            r"hb_compile\s*version[:\s]+(\S+)", re.IGNORECASE
        ),
        "hb_verifier_version": re.compile(
            r"verifier\s*tool\s*version[:\s]+(\S+)", re.IGNORECASE
        ),
    }

    # quantize summary 相关
    quantize_section = False
    quantize_patterns = {
        "quantize_type": re.compile(
            r"quantize\s*type[:\s]+(\S+)", re.IGNORECASE
        ),
        "calibration_type": re.compile(
            r"calibration\s*type[:\s]+(\S+)", re.IGNORECASE
        ),
        "total_layers": re.compile(
            r"total\s*layers?[:\s]+(\d+)", re.IGNORECASE
        ),
        "quantized_layers": re.compile(
            r"quantized\s*layers?[:\s]+(\d+)", re.IGNORECASE
        ),
    }

    # compiler advice
    advice_pattern = re.compile(
        r"advice|建议|optimization\s*suggestion", re.IGNORECASE
    )

    # 编译完成标记
    complete_pattern = re.compile(
        r"completes?\s*running|编译完成|finish", re.IGNORECASE
    )

    for line_num, line in enumerate(lines, 1):
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # 提取时间戳
        time_match = time_pattern.search(line_stripped)
        current_time = time_match.group(1) if time_match else None

        # 提取版本信息
        for ver_key, ver_pat in version_patterns.items():
            ver_match = ver_pat.search(line_stripped)
            if ver_match:
                data["version_info"][ver_key] = ver_match.group(1)

        # 检测阶段切换
        for phase_name, phase_pat in phase_patterns.items():
            if phase_pat.search(line_stripped):
                if current_phase and phase_start_time:
                    data["phases"].append({
                        "phase": current_phase,
                        "start": phase_start_time,
                        "end": current_time,
                    })
                current_phase = phase_name
                phase_start_time = current_time
                data["timeline"][phase_name] = {
                    "start": current_time,
                    "line": line_num,
                }
                logging.debug(f"检测到阶段: {phase_name} (行 {line_num})")

        # 检测编译完成
        if complete_pattern.search(line_stripped) and current_phase:
            data["phases"].append({
                "phase": current_phase,
                "start": phase_start_time,
                "end": current_time,
            })
            data["timeline"][current_phase]["end"] = current_time
            current_phase = None

        # 提取 WARNING
        if "WARNING" in line_stripped or "[WARN]" in line_stripped:
            data["warnings"].append({
                "line": line_num,
                "time": current_time,
                "message": line_stripped,
            })

        # 提取 ERROR
        if "ERROR" in line_stripped or "[ERROR]" in line_stripped:
            data["errors"].append({
                "line": line_num,
                "time": current_time,
                "message": line_stripped,
            })

        # 检测 quantize summary 区域
        if re.search(
            r"quantiz.*summary|summary.*quantiz",
            line_stripped,
            re.IGNORECASE,
        ):
            quantize_section = True
            continue

        if quantize_section:
            matched = False
            for q_key, q_pat in quantize_patterns.items():
                q_match = q_pat.search(line_stripped)
                if q_match:
                    data["quantize_summary"][q_key] = q_match.group(1)
                    matched = True
            # 如果遇到空行或非摘要行，结束摘要区域
            if (
                not matched
                and not re.match(r"^[-=*]+$", line_stripped)
                and re.search(
                    r"^(INFO|DEBUG|WARNING|ERROR)", line_stripped
                )
            ):
                quantize_section = False

        # 检测 compiler advice
        if advice_pattern.search(line_stripped):
            data["compiler_advice"].append({
                "line": line_num,
                "time": current_time,
                "message": line_stripped,
            })

    # 处理最后一个未关闭的阶段
    if current_phase:
        data["phases"].append({
            "phase": current_phase,
            "start": phase_start_time,
            "end": None,
        })

    # 统计信息
    data["stats"] = {
        "total_lines": len(lines),
        "warning_count": len(data["warnings"]),
        "error_count": len(data["errors"]),
        "phase_count": len(data["phases"]),
        "advice_count": len(data["compiler_advice"]),
    }

    return result


def format_text(result: dict) -> str:
    """将结果格式化为文本摘要。"""
    lines = []
    data = result.get("data", {})

    if result["status"] != "success":
        lines.append(f"解析失败: {result['message']}")
        return "\n".join(lines)

    # 版本信息
    ver_info = data.get("version_info", {})
    if ver_info:
        lines.append("=== 版本信息 ===")
        for key, val in ver_info.items():
            lines.append(f"  {key}: {val}")
        lines.append("")

    # 阶段时间线
    phases = data.get("phases", [])
    if phases:
        lines.append("=== 编译阶段时间线 ===")
        for phase in phases:
            start = phase.get("start", "?")
            end = phase.get("end", "进行中")
            lines.append(f"  [{phase['phase']}] {start} -> {end}")
        lines.append("")

    # 统计
    stats = data.get("stats", {})
    lines.append("=== 统计 ===")
    lines.append(f"  总行数:   {stats.get('total_lines', 0)}")
    lines.append(f"  警告数:   {stats.get('warning_count', 0)}")
    lines.append(f"  错误数:   {stats.get('error_count', 0)}")
    lines.append(f"  阶段数:   {stats.get('phase_count', 0)}")
    lines.append(f"  建议数:   {stats.get('advice_count', 0)}")
    lines.append("")

    # Quantize Summary
    q_summary = data.get("quantize_summary", {})
    if q_summary:
        lines.append("=== 量化摘要 ===")
        for key, val in q_summary.items():
            lines.append(f"  {key}: {val}")
        lines.append("")

    # 最近 5 条 Warning
    warnings = data.get("warnings", [])
    if warnings:
        lines.append(f"=== 警告（最近 {min(5, len(warnings))} 条）===")
        for w in warnings[-5:]:
            lines.append(f"  L{w['line']}: {w['message'][:120]}")
        lines.append("")

    # 最近 5 条 Error
    errors = data.get("errors", [])
    if errors:
        lines.append(f"=== 错误（最近 {min(5, len(errors))} 条）===")
        for e in errors[-5:]:
            lines.append(f"  L{e['line']}: {e['message'][:120]}")
        lines.append("")

    # Compiler Advice
    advices = data.get("compiler_advice", [])
    if advices:
        lines.append(f"=== 编译器建议（{len(advices)} 条）===")
        for a in advices:
            lines.append(f"  L{a['line']}: {a['message'][:120]}")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    """主函数入口。"""
    parser = argparse.ArgumentParser(
        description=(
            "hb_compile.log 解析工具，"
            "抽取编译阶段时间线、警告、错误、量化摘要等信息"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  %(prog)s --input hb_compile.log
  %(prog)s --input hb_compile.log --format json
  %(prog)s --input model_output/hb_compile.log --format text
        """,
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="hb_compile.log 文件路径",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="输出格式：text（精简摘要）或 json（完整报告），默认 text",
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

    result = parse_compile_log(args.input)

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_text(result))

    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
