#!/usr/bin/env python3
"""HMCT build_model / check_model 一键运行脚本.

用法:
    # build_model: 使用真实校准数据构建量化模型
    python run_build.py build \
        --onnx_path model.onnx \
        --cali_data_dir ./calibration_data/ \
        --march nash-e \
        --name_prefix ./output/model

    # build_model: 使用 quant_config / input_dict
    python run_build.py build \
        --onnx_path model.onnx \
        --cali_data_dir ./calibration_data/ \
        --quant_config_path quant_config.json \
        --input_dict_path input_dict.json \
        --march nash-e

    # check_model: 使用随机数据快速验证转换流程
    python run_build.py check \
        --onnx_path model.onnx \
        --march nash-e

校准数据目录结构 (--cali_data_dir):
    calibration_data/
    ├── input_name_0/       # 子目录名需与模型输入节点名一致
    │   ├── 0.npy
    │   └── ...
    └── input_name_1/
        └── ...

JSON 配置文件 (均可选):
    --input_dict_path    input_dict (input_shape / transformer / color_convert 等)
    --cali_dict_path     cali_dict (calibration_type / calibration_data 等);
                         指定后将覆盖 --cali_data_dir
    --quant_config_path  quant_config (PTQ 量化配置)
"""

import argparse
import json
import logging
import os
import sys
from typing import Any, Optional

import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def load_cali_data(onnx_path: str, cali_data_dir: str) -> dict:
    """从目录加载校准数据, 子目录名需与模型输入名一致."""
    from hmct.ir import OnnxModel

    onnx_model = OnnxModel(onnx_path)
    input_names = onnx_model.graph.input_names

    cali_data = {name: [] for name in input_names}

    for input_name in sorted(os.listdir(cali_data_dir)):
        input_dir = os.path.join(cali_data_dir, input_name)
        if not os.path.isdir(input_dir):
            continue
        if input_name not in cali_data:
            logger.warning(
                "目录 '%s' 不在模型输入 %s 中, 跳过",
                input_name,
                input_names,
            )
            continue
        npy_files = sorted(
            f for f in os.listdir(input_dir) if f.endswith(".npy")
        )
        for npy_name in npy_files:
            cali_data[input_name].append(
                np.load(os.path.join(input_dir, npy_name))
            )
        logger.info(
            "加载输入 '%s' 的校准数据: %d 条",
            input_name,
            len(cali_data[input_name]),
        )

    return cali_data


def _load_json(path: Optional[str], label: str) -> Optional[Any]:
    """加载可选的 JSON 配置文件, 路径为空时返回 None."""
    if not path:
        return None
    abs_path = os.path.abspath(path)
    with open(abs_path) as f:
        data = json.load(f)
    logger.info("加载 %s: %s", label, abs_path)
    return data


def run_command(args: argparse.Namespace, *, check_mode: bool) -> None:
    """统一执行入口: build_model (check_mode 控制是否使用随机数据).

    cali_data_dir / cali_dict_path 仅 build 子命令暴露; check 不传时通过 getattr 兜底。
    """
    label = "check_model" if check_mode else "build_model"

    onnx_path = os.path.abspath(args.onnx_path)
    name_prefix = os.path.abspath(args.name_prefix)
    parent_dir = os.path.dirname(name_prefix)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    from hmct.api import build_model

    # 校准数据: 仅 build 子命令暴露相关参数, check 用 getattr 兜底
    cali_dict_path = getattr(args, "cali_dict_path", None)
    cali_data_dir = getattr(args, "cali_data_dir", None)
    cali_dict = _load_json(cali_dict_path, "cali_dict")
    cali_data: Optional[dict] = None
    if not check_mode and cali_dict is None and cali_data_dir:
        cali_data = load_cali_data(onnx_path, os.path.abspath(cali_data_dir))

    input_dict = _load_json(args.input_dict_path, "input_dict")
    quant_config = _load_json(args.quant_config_path, "quant_config")

    build_kwargs: dict = {
        "onnx_file": onnx_path,
        "march": args.march,
        "name_prefix": name_prefix,
        "verbose": not args.quiet,
    }
    if check_mode:
        build_kwargs["check_mode"] = True

    optional_kwargs = {
        "cali_data": cali_data,
        "cali_dict": cali_dict,
        "input_dict": input_dict,
        "quant_config": quant_config,
    }
    for key, value in optional_kwargs.items():
        if value is not None:
            build_kwargs[key] = value

    logger.info("mode:        %s", label)
    logger.info("onnx_path:   %s", onnx_path)
    logger.info("march:       %s", args.march)
    logger.info("name_prefix: %s", name_prefix)
    logger.info("%s kwargs keys: %s", label, sorted(build_kwargs.keys()))

    result_model = build_model(**build_kwargs)

    if result_model is not None:
        if check_mode:
            logger.info("check_model 通过! 模型转换流程验证成功.")
        else:
            logger.info("build_model 完成!")
    else:
        logger.error("%s 返回 None, 请检查日志", label)
        sys.exit(1)


def run_build(args: argparse.Namespace) -> None:
    """build 子命令入口."""
    run_command(args, check_mode=False)


def run_check(args: argparse.Namespace) -> None:
    """check 子命令入口 (基于 build_model + check_mode=True)."""
    run_command(args, check_mode=True)


def _add_common_args(p: argparse.ArgumentParser) -> None:
    """build 与 check 共用参数."""
    p.add_argument(
        "--onnx_path",
        required=True,
        help="输入 ONNX 模型路径",
    )
    p.add_argument(
        "--march",
        default="nash-p",
        help="BPU 芯片架构 (默认: nash-p)",
    )
    p.add_argument(
        "--input_dict_path",
        default=None,
        help="input_dict JSON 文件路径 (input_shape / transformer / color_convert 等)",
    )
    p.add_argument(
        "--quant_config_path",
        default=None,
        help="quant_config JSON 文件路径 (PTQ 量化配置)",
    )
    p.add_argument(
        "--name_prefix",
        default="model",
        help="输出模型名称或路径前缀 (默认: model)",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="关闭 verbose 输出 (默认 verbose=True)",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="HMCT build_model / check_model 一键运行脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")
    subparsers.required = True

    # -- build 子命令 --
    build_parser = subparsers.add_parser(
        "build",
        help="使用真实校准数据构建量化模型",
    )
    _add_common_args(build_parser)
    build_parser.add_argument(
        "--cali_data_dir",
        default=None,
        help="校准数据目录 (子目录名需与模型输入名一致)",
    )
    build_parser.add_argument(
        "--cali_dict_path",
        default=None,
        help="cali_dict JSON 文件路径; 指定后将覆盖 --cali_data_dir",
    )
    build_parser.set_defaults(func=run_build)

    # -- check 子命令 --
    check_parser = subparsers.add_parser(
        "check",
        help="使用随机数据快速验证模型转换流程 (build_model + check_mode=True)",
    )
    _add_common_args(check_parser)
    check_parser.set_defaults(func=run_check)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
