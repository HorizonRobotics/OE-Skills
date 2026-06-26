#!/usr/bin/env python3
"""
LightCompress 量化实验执行脚本

功能：
1. 读取已准备的实验目录
2. 选择最优 GPU
3. 执行量化实验
4. 生成报告

使用：
    python execute_experiment.py /path/to/experiment_dir
"""

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

# 添加 lib 目录到路径
sys.path.insert(0, str(Path(__file__).parent))
from lib import (
    ExperimentRunner,
    ReportGenerator,
    load_yaml_config,
    update_pretrain_cache,
    fmt_metric,
)


def die(message: str) -> None:
    """抛出系统退出异常"""
    raise SystemExit(message)


def run_experiment(experiment_dir: str) -> dict:
    """执行实验并返回结果"""
    experiment_dir = Path(experiment_dir).expanduser().resolve()

    # 读取 manifest
    manifest_file = experiment_dir / "manifest.json"
    if not manifest_file.exists():
        die(f"实验目录中未找到 manifest.json: {experiment_dir}")

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    manifest["experiment_dir"] = str(experiment_dir)

    # 验证 run_script_path
    run_script_path = Path(manifest["run_script_path"])
    if not run_script_path.exists():
        die(f"run_script_path 不存在: {run_script_path}")

    current_date = dt.datetime.now().strftime("%Y%m%d")
    collected_results = []
    total_experiments = len(manifest["experiments"])

    # 初始化报告
    report_path = experiment_dir / "report.md"
    report_generator = ReportGenerator(manifest, report_path, current_date)
    report_generator.init()
    print(f"报告已初始化: {report_path}", flush=True)

    # 创建实验执行器
    runner = ExperimentRunner(manifest, current_date)

    print(f"\n{'='*60}", flush=True)
    print(f"实验目录: {experiment_dir}", flush=True)
    print(f"精简模式: {'否 (保存产物)' if manifest.get('save_artifacts', False) else '是 (不保存产物)'}", flush=True)
    print(f"{'='*60}\n", flush=True)
    print(f"开始执行 {total_experiments} 个实验...", flush=True)

    for idx, experiment in enumerate(manifest["experiments"], 1):
        print(f"\n{'='*60}", flush=True)
        print(f"[{idx}/{total_experiments}] 开始实验: {experiment['model_name']} - {experiment['method_name']}", flush=True)
        print(f"{'='*60}", flush=True)

        result = runner.run(experiment)
        result_item = {"experiment": experiment, "result": result}
        collected_results.append(result_item)

        # 更新 pretrain 缓存
        if result["status"] == "success" and result["metrics"].get("pretrain") is not None:
            yaml_config = load_yaml_config(experiment.get("config_path", ""))
            eval_config = yaml_config.get('eval', {})
            update_pretrain_cache(experiment['model_name'], eval_config, result["metrics"]["pretrain"])

        # 增量更新报告
        report_generator.update(collected_results, idx, total_experiments)

        if result["status"] == "success":
            metrics = result["metrics"]
            print(f"\n[完成] PPL: pretrain={fmt_metric(metrics['pretrain'])}, "
                  f"transformed={fmt_metric(metrics['transformed'])}, "
                  f"fake_quant={fmt_metric(metrics['fake_quant'])}", flush=True)
            if result.get("quantized_layers", {}).get("summary"):
                print(f"[量化层] {result['quantized_layers']['summary']}", flush=True)
        else:
            print(f"\n[失败] 原因: {result.get('error', 'unknown')}", flush=True)

    # 最终完整报告
    report_generator.render_final(collected_results)

    print(f"\n{'='*60}", flush=True)
    print(f"实验完成！", flush=True)
    print(f"实验目录: {experiment_dir}", flush=True)
    print(f"报告路径: {report_path}", flush=True)
    print(f"{'='*60}", flush=True)

    return {
        "experiment_dir": str(experiment_dir),
        "report_path": str(report_path),
        "results": collected_results
    }


def main():
    parser = argparse.ArgumentParser(
        description="执行 LightCompress 量化实验"
    )
    parser.add_argument("experiment_dir", help="已准备的实验目录路径")

    args = parser.parse_args()

    # 执行实验
    result = run_experiment(args.experiment_dir)

    # 输出 JSON 结果
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main())
