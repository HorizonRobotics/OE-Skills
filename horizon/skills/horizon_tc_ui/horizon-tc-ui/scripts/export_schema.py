# Copyright (c) 2024 Horizon Robotics.All Rights Reserved.
#
# The material in this file is confidential and contains trade secrets
# of Horizon Robotics Inc. This is proprietary information owned by
# Horizon Robotics Inc. No part of this work may be disclosed,
# reproduced, copied, transmitted, or used in any way for any purpose,
# without the express written permission of Horizon Robotics Inc.

"""
Schema 导出脚本。

用途：
  从 horizon_tc_ui/config/schema_yaml.py 中的 schema_yaml 定义
  自动导出 JSON Schema 文件（assets/schemas/yaml_schema.json）。

输入：无（读取 horizon_tc_ui 已安装的 schema_yaml 模块）
输出：JSON Schema 文件
退出码：
  0 - 导出成功（或 --check 模式下校验通过）
  1 - 参数错误
  3 - 运行时错误（导入失败、IO 异常等）

示例：
  # 导出到默认路径
  python export_schema.py

  # 导出到指定路径
  python export_schema.py --output /tmp/my_schema.json

  # 仅校验不写入（检查当前 schema 是否与已有文件一致）
  python export_schema.py --check

  # JSON 输出
  python export_schema.py --format json
"""

import argparse
import json
import logging
import os
import sys

# 脚本版本
SCRIPT_VERSION = "1.0.0"

# 默认输出路径（相对于 horizon_tc_ui/skill/ 目录）
DEFAULT_OUTPUT = "assets/schemas/yaml_schema.json"

# 文件头注释（作为 JSON 对象内的 _comment 字段嵌入，保持 JSON 合法性）
HEADER_COMMENT = (
    "自动生成，请勿手工修改 | "
    "源头: horizon_tc_ui/config/schema_yaml.py | "
    "生成方式: python skill/scripts/export_schema.py"
)


def schema_to_json_schema(schema_dict: dict) -> dict:
    """
    将 schema_yaml.py 中的 schema 定义转换为标准 JSON Schema 格式。

    schema_yaml 使用 schema 库的语法（Optional, Use, Or, And 等），
    此函数将其转换为 JSON Schema (Draft-07) 格式。
    """
    json_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "horizon_tc_ui YAML 配置 Schema",
        "description": (
            "从 horizon_tc_ui/config/schema_yaml.py "
            "自动生成的 JSON Schema"
        ),
        "type": "object",
        "properties": {},
        "required": [],
    }

    # 遍历 schema_yaml 的顶层 key（model_parameters, input_parameters 等）
    for section_key, section_value in schema_dict.items():
        section_name = section_key
        if hasattr(section_key, "schema"):
            # schema.Optional 对象
            section_name = section_key.schema

        section_schema = {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

        if isinstance(section_value, dict):
            for param_key, param_value in section_value.items():
                param_name = param_key
                is_required = True

                if hasattr(param_key, "schema"):
                    # schema.Optional 对象
                    param_name = param_key.schema
                    is_required = not hasattr(param_key, "default")

                # 将 schema 类型映射为 JSON Schema 类型
                param_schema = _convert_schema_value(param_value, param_name)

                section_schema["properties"][param_name] = param_schema

                if is_required:
                    section_schema.setdefault(
                        "required", []
                    ).append(param_name)

            # 检查是否有 Optional(str): object 这种通配符（允许额外参数）
            for param_key in section_value:
                if hasattr(param_key, "schema") and param_key.schema is str:
                    section_schema["additionalProperties"] = True
                    break

        json_schema["properties"][section_name] = section_schema
        json_schema["required"].append(section_name)

    return json_schema


def _convert_schema_value(value, name: str) -> dict:
    """将 schema 库的值类型转换为 JSON Schema 属性定义。"""
    from schema import And, Or, Use

    # 处理 Use 类型
    if isinstance(value, Use):
        return _convert_use_type(value, name)

    # 处理 Or 类型（多类型选一）
    if isinstance(value, Or):
        return _convert_or_type(value)

    # 处理 And 类型（需满足所有条件）
    if isinstance(value, And):
        return _convert_and_type(value)

    # 处理 Python 原生类型
    if value is str:
        return {"type": "string"}
    if value is int:
        return {"type": "integer"}
    if value is float:
        return {"type": "number"}
    if value is bool:
        return {"type": "boolean"}
    if value is dict:
        return {"type": "object"}
    if value is list:
        return {"type": "array"}
    if value is object:
        return {"type": "object", "description": "任意类型"}

    # 处理 None
    if value is None:
        return {"type": "null"}

    # 默认：尝试推断
    return {"type": "string", "description": f"参数: {name}"}


def _convert_use_type(use_obj, name: str) -> dict:
    """处理 schema.Use 类型。"""
    inner = use_obj._callable
    if inner is str:
        return {"type": "string"}
    if inner is int:
        return {"type": "integer"}
    if inner is float:
        return {"type": "number"}
    if inner is bool:
        return {"type": "boolean"}
    if inner is dict:
        return {"type": "object"}
    # 自定义转换函数（如 use_none_or_int）
    return {"type": ["string", "integer", "null"],
            "description": f"参数: {name}，支持字符串、整数或 null"}


def _convert_or_type(or_obj) -> dict:
    """处理 schema.Or 类型。"""
    types = []
    for arg in or_obj._args:
        if arg is bool:
            types.append("boolean")
        elif arg is str:
            types.append("string")
        elif arg is int:
            types.append("integer")
        elif arg is float:
            types.append("number")
        elif arg is dict:
            types.append("object")
        elif arg is list:
            types.append("array")
        elif arg is None:
            types.append("null")

    if not types:
        return {"type": "object"}

    # 去重
    unique_types = list(dict.fromkeys(types))
    if len(unique_types) == 1:
        return {"type": unique_types[0]}
    return {"type": unique_types}


def _convert_and_type(and_obj) -> dict:
    """处理 schema.And 类型。"""
    # And 取第一个类型作为主类型
    for arg in and_obj._args:
        if arg is str:
            return {"type": "string", "minLength": 1}
        if arg is int:
            return {"type": "integer"}
        if arg is float:
            return {"type": "number"}
        if arg is bool:
            return {"type": "boolean"}
    return {"type": "string"}


def generate_schema() -> dict:
    """从 schema_yaml.py 导入并生成 JSON Schema。"""
    try:
        from horizon_tc_ui.config.schema_yaml import schema_yaml
    except ImportError as e:
        raise ImportError(
            f"无法导入 horizon_tc_ui.config.schema_yaml: {e}\n"
            "请确保 horizon_tc_ui 已正确安装（pip install -e .）"
        ) from e

    return schema_to_json_schema(schema_yaml)


def main():
    parser = argparse.ArgumentParser(
        description="从 schema_yaml.py 导出 JSON Schema 文件",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help=(
            f"输出文件路径，默认 {DEFAULT_OUTPUT}"
            "（相对于脚本所在目录的 assets/schemas/）"
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="仅检查不写入：对比生成的 schema 与已有文件是否一致",
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
        version=f"export_schema.py {SCRIPT_VERSION}",
    )

    args = parser.parse_args()

    # 配置日志
    if args.v:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)
    elif args.q:
        logging.basicConfig(level=logging.ERROR, stream=sys.stderr)
    else:
        logging.basicConfig(level=logging.INFO, stream=sys.stderr)

    # 确定输出路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    skill_dir = os.path.dirname(script_dir)

    output_path = args.output or os.path.join(skill_dir, DEFAULT_OUTPUT)

    try:
        schema = generate_schema()
    except ImportError as e:
        logging.error(str(e))
        error_result = {
            "status": "error",
            "exit_code": 3,
            "message": str(e),
            "data": {},
            "errors": [{
                "field": "import",
                "expected": "成功导入 schema_yaml",
                "actual": "导入失败",
                "suggestion": (
                    "请确保 horizon_tc_ui 已安装"
                    "（pip install -e .）"
                ),
            }],
        }
        if args.format == "json":
            print(json.dumps(error_result, indent=2, ensure_ascii=False))
        sys.exit(3)
    except Exception as e:
        logging.error(f"生成 Schema 时异常: {e}")
        sys.exit(3)

    # 将注释作为 JSON 对象内的 _comment 字段嵌入，保持 JSON 合法性
    schema_with_comment = {"_comment": HEADER_COMMENT}
    schema_with_comment.update(schema)
    file_content = (
        json.dumps(
            schema_with_comment, indent=2, ensure_ascii=False
        )
        + "\n"
    )

    if args.check:
        # 检查模式：对比已有文件
        if not os.path.exists(output_path):
            logging.error(f"目标文件不存在: {output_path}")
            if args.format == "json":
                result = {
                    "status": "error",
                    "exit_code": 3,
                    "message": f"目标文件不存在: {output_path}",
                    "data": {},
                    "errors": [{
                        "field": "output_file",
                        "expected": "文件存在",
                        "actual": "文件不存在",
                        "suggestion": (
                            "先运行不带 --check 的命令生成文件: "
                            f"python {os.path.basename(__file__)}"
                        ),
                    }],
                }
                print(json.dumps(result, indent=2, ensure_ascii=False))
            sys.exit(3)

        with open(output_path, encoding="utf-8") as f:
            existing_content = f.read()

        if existing_content == file_content:
            logging.info("Schema 文件已是最新，无需更新")
            if args.format == "json":
                result = {
                    "status": "success",
                    "exit_code": 0,
                    "message": "Schema 文件已是最新",
                    "data": {"file": output_path},
                    "errors": [],
                }
                print(json.dumps(result, indent=2, ensure_ascii=False))
            sys.exit(0)
        else:
            logging.error("Schema 文件已过时，需要重新生成")
            if args.format == "json":
                result = {
                    "status": "error",
                    "exit_code": 2,
                    "message": "Schema 文件已过时",
                    "data": {"file": output_path},
                    "errors": [{
                        "field": "schema_file",
                        "expected": "与 schema_yaml.py 一致",
                        "actual": "不一致",
                        "suggestion": (
                            f"运行 python {os.path.basename(__file__)} "
                            "重新生成"
                        ),
                    }],
                }
                print(json.dumps(result, indent=2, ensure_ascii=False))
            sys.exit(2)

    # 写入模式
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        logging.info(f"创建目录: {output_dir}")
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(file_content)

    logging.info(f"Schema 已导出到: {output_path}")

    if args.format == "json":
        result = {
            "status": "success",
            "exit_code": 0,
            "message": f"Schema 已导出到 {output_path}",
            "data": {
                "file": output_path,
                "sections": list(schema.get("properties", {}).keys()),
            },
            "errors": [],
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"成功: Schema 已导出到 {output_path}")

    sys.exit(0)


if __name__ == "__main__":
    main()
