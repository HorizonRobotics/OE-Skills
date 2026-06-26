"""
LightCompress 量化探索实验 - 模块化拆分

模块结构:
- config: YAML 配置生成、精度缓存管理、大模型参数优化
- gpu_selector: GPU 查询与选择
- log_parser: 日志解析、进度报告、量化层分析
- experiment_runner: 实验执行核心逻辑
- report_generator: 报告生成与更新
"""

import re
import shutil
from pathlib import Path

from .config import (
    YAMLConfigGenerator,
    PretrainCache,
    LargeModelOptimizer,
    FastModeOptimizer,
    CalibSampleOptimizer,
    generate_yaml_config,
    get_known_accuracy,
    update_pretrain_cache,
    load_yaml_config,
    estimate_model_size,
    should_optimize_params_for_large_model,
    optimize_yaml_for_large_model,
)

from .gpu_selector import GPUSelector, GPUInfo

from .log_parser import (
    LogParser,
    ProgressReporter,
    ProgressParser,
    PPLParser,
    QuantizedLayersParser,
    ErrorDetector,
)

from .experiment_runner import ExperimentRunner, ProcessManager

from .report_generator import ReportGenerator, ResultAnalyzer, QuantizedLayersReporter, fmt_metric


def sanitize_fragment(value: str) -> str:
    """清理文件名片段"""
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("_")
    return text or "_"


def find_existing_experiment_dir(output_root: Path, experiment_name: str) -> None:
    """查找并删除已存在的失败实验目录"""
    dirs_to_delete = []
    for item in output_root.iterdir():
        if item.is_dir() and item.name.startswith(experiment_name):
            report_file = item / "report.md"
            if not report_file.exists():
                dirs_to_delete.append(item)
            else:
                content = report_file.read_text(encoding='utf-8', errors='ignore')
                if "失败" in content and "成功" not in content:
                    dirs_to_delete.append(item)

    for dir_path in dirs_to_delete:
        shutil.rmtree(dir_path)
        print(f"[清理] 已删除失败的实验目录: {dir_path.name}", flush=True)

__all__ = [
    # config
    "YAMLConfigGenerator",
    "PretrainCache",
    "LargeModelOptimizer",
    "FastModeOptimizer",
    "CalibSampleOptimizer",
    "generate_yaml_config",
    "get_known_accuracy",
    "update_pretrain_cache",
    "load_yaml_config",
    "estimate_model_size",
    "should_optimize_params_for_large_model",
    "optimize_yaml_for_large_model",
    # gpu_selector
    "GPUSelector",
    "GPUInfo",
    # log_parser
    "LogParser",
    "ProgressReporter",
    "ProgressParser",
    "PPLParser",
    "QuantizedLayersParser",
    "ErrorDetector",
    # experiment_runner
    "ExperimentRunner",
    "ProcessManager",
    # report_generator
    "ReportGenerator",
    "ResultAnalyzer",
    "QuantizedLayersReporter",
    "fmt_metric",
    # common utils
    "sanitize_fragment",
    "find_existing_experiment_dir",
]
