# Copyright (c) 2024 Horizon Robotics.All Rights Reserved.
#
# The material in this file is confidential and contains trade secrets
# of Horizon Robotics Inc. This is proprietary information owned by
# Horizon Robotics Inc. No part of this work may be disclosed,
# reproduced, copied, transmitted, or used in any way for any purpose,
# without the express written permission of Horizon Robotics Inc.

"""
环境检测脚本。

用途：
  检测当前运行环境是否满足 horizon_tc_ui 工具链的要求，
  包括已安装的 Python 包、CLI 工具以及 march 支持列表。

输入：无（仅检测当前环境）
输出：JSON 格式的环境检测报告（--format json）或人类可读文本（默认）
退出码：
  0 - 环境检测全部通过
  1 - 参数错误
  3 - 运行时错误（IO 异常等）
  4 - 环境不满足要求（依赖缺失、版本不匹配、CLI 不在 PATH 等）

示例：
  python detect_env.py
  python detect_env.py --format json
  python detect_env.py -v
"""

import argparse
import contextlib
import json
import logging
import shutil
import sys
from importlib.metadata import PackageNotFoundError, version

# 需要检测的 CLI 工具列表
REQUIRED_CLIS = [
    "hb_compile",
    "hb_model_info",
    "hb_verifier",
    "hb_analyzer",
    "hb_config_generator",
    "hb_eval_preprocess",
]

# 脚本版本
SCRIPT_VERSION = "1.0.0"


def get_package_version(package_name: str) -> dict:
    """检测指定 Python 包是否安装并返回版本信息。"""
    try:
        ver = version(package_name)
        return {
            "installed": True,
            "version": ver,
        }
    except PackageNotFoundError:
        return {
            "installed": False,
            "version": None,
        }


def check_cli_in_path(cli_name: str) -> dict:
    """检测 CLI 工具是否在系统 PATH 中。"""
    cli_path = shutil.which(cli_name)
    return {
        "name": cli_name,
        "found": cli_path is not None,
        "path": cli_path,
    }


def get_hbdk4_version() -> dict:
    """检测 hbdk4 包版本（复用 import_from 语义）。"""
    result = {"installed": False, "version": None}
    try:
        import importlib
        hbdk4 = importlib.import_module("hbdk4")
        result["installed"] = True
        # 尝试从 hbdk4.__version__ 获取版本
        result["version"] = getattr(hbdk4, "__version__", None)
        # 如果模块内没有 __version__，尝试通过 importlib.metadata 获取
        if result["version"] is None:
            with contextlib.suppress(PackageNotFoundError):
                result["version"] = version("hbdk4")
    except ImportError:
        pass
    return result


def get_hmct_version() -> dict:
    """检测 hmct 包版本（复用 import_from 语义）。"""
    result = {"installed": False, "version": None}
    try:
        import importlib
        hmct = importlib.import_module("hmct")
        result["installed"] = True
        result["version"] = getattr(hmct, "__version__", None)
        if result["version"] is None:
            with contextlib.suppress(PackageNotFoundError):
                result["version"] = version("hmct")
    except ImportError:
        pass
    return result


def get_march_list() -> list:
    """获取支持的 march 列表，复用 tool_utils.get_march_list 语义。"""
    try:
        from horizon_tc_ui.utils.tool_utils import (
            get_march_list as _get_march_list,
        )
        return _get_march_list()
    except ImportError:
        logging.warning(
            "无法从 horizon_tc_ui 导入 get_march_list，使用默认列表"
        )
        return [
            "nash-b-lite",
            "nash-b",
            "nash-b-plus",
            "nash-e",
            "nash-m",
            "nash-p",
            "nash-h",
        ]


def detect_env() -> dict:
    """执行完整的环境检测并返回结果字典。"""
    errors = []

    # 1. 检查 horizon_tc_ui
    tc_ui = get_package_version("horizon_tc_ui")
    if not tc_ui["installed"]:
        errors.append({
            "field": "horizon_tc_ui",
            "expected": "已安装",
            "actual": "未安装",
            "suggestion": (
                "请执行 pip install horizon_tc_ui "
                "或 pip install -e . 安装"
            ),
        })

    # 2. 检查 hbdk4
    hbdk4 = get_hbdk4_version()
    if not hbdk4["installed"]:
        errors.append({
            "field": "hbdk4",
            "expected": "已安装",
            "actual": "未安装",
            "suggestion": "请安装 hbdk4 包（参考内部文档）",
        })

    # 3. 检查 hmct
    hmct = get_hmct_version()
    if not hmct["installed"]:
        errors.append({
            "field": "hmct",
            "expected": "已安装",
            "actual": "未安装",
            "suggestion": "请安装 hmct 包（参考内部文档）",
        })

    # 4. 检查 CLI 工具
    cli_results = []
    for cli_name in REQUIRED_CLIS:
        cli_info = check_cli_in_path(cli_name)
        cli_results.append(cli_info)
        if not cli_info["found"]:
            errors.append({
                "field": f"cli.{cli_name}",
                "expected": "在系统 PATH 中",
                "actual": "未找到",
                "suggestion": (
                    f"请确保 {cli_name} 已安装且路径已加入 PATH 环境变量"
                ),
            })

    # 5. 获取 march 支持列表
    march_list = get_march_list()

    result = {
        "status": "success" if len(errors) == 0 else "error",
        "exit_code": 0 if len(errors) == 0 else 4,
        "message": (
            "环境检测通过"
            if len(errors) == 0
            else f"环境检测失败，共 {len(errors)} 项未通过"
        ),
        "data": {
            "horizon_tc_ui": tc_ui,
            "hbdk4": hbdk4,
            "hmct": hmct,
            "cli_tools": cli_results,
            "march_list": march_list,
        },
        "errors": errors,
    }
    return result


def format_text_output(result: dict) -> str:
    """将检测结果格式化为人类可读的文本。"""
    lines = []
    lines.append("=" * 60)
    lines.append("  环境检测报告")
    lines.append("=" * 60)

    data = result["data"]

    # horizon_tc_ui
    tc_ui = data["horizon_tc_ui"]
    if tc_ui["installed"]:
        lines.append(f"[通过] horizon_tc_ui 已安装，版本: {tc_ui['version']}")
    else:
        lines.append("[失败] horizon_tc_ui 未安装")

    # hbdk4
    hbdk4 = data["hbdk4"]
    if hbdk4["installed"]:
        ver_str = hbdk4["version"] or "未知"
        lines.append(f"[通过] hbdk4 已安装，版本: {ver_str}")
    else:
        lines.append("[失败] hbdk4 未安装")

    # hmct
    hmct = data["hmct"]
    if hmct["installed"]:
        ver_str = hmct["version"] or "未知"
        lines.append(f"[通过] hmct 已安装，版本: {ver_str}")
    else:
        lines.append("[失败] hmct 未安装")

    # CLI 工具
    lines.append("")
    lines.append("CLI 工具检测:")
    for cli in data["cli_tools"]:
        if cli["found"]:
            lines.append(f"  [通过] {cli['name']}: {cli['path']}")
        else:
            lines.append(f"  [失败] {cli['name']}: 未找到")

    # march 列表
    lines.append("")
    lines.append(f"支持的 march 列表 ({len(data['march_list'])} 个):")
    for march in data["march_list"]:
        lines.append(f"  - {march}")

    lines.append("")
    lines.append(f"检测结果: {result['message']}")
    lines.append("=" * 60)

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="检测 horizon_tc_ui 运行环境是否满足要求",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="输出格式：text（人类可读）或 json（机器可解析），默认 text",
    )
    parser.add_argument(
        "-v",
        action="store_true",
        help="详细模式，输出 DEBUG 级别日志",
    )
    parser.add_argument(
        "-q",
        action="store_true",
        help="静默模式，仅输出错误信息",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"detect_env.py {SCRIPT_VERSION}",
    )

    args = parser.parse_args()

    # 配置日志
    if args.v:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)
    elif args.q:
        logging.basicConfig(level=logging.ERROR, stream=sys.stderr)
    else:
        logging.basicConfig(level=logging.INFO, stream=sys.stderr)

    try:
        result = detect_env()
    except Exception as e:
        logging.error(f"环境检测运行时异常: {e}")
        error_result = {
            "status": "error",
            "exit_code": 3,
            "message": f"运行时异常: {e}",
            "data": {},
            "errors": [{
                "field": "runtime",
                "expected": "正常执行",
                "actual": str(e),
                "suggestion": "请检查日志获取详细信息",
            }],
        }
        if args.format == "json":
            print(json.dumps(error_result, indent=2, ensure_ascii=False))
        else:
            print(f"错误: {error_result['message']}", file=sys.stderr)
        sys.exit(3)

    if args.format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_text_output(result))

    sys.exit(result["exit_code"])


if __name__ == "__main__":
    main()
