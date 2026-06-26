#!/usr/bin/env python3
"""
LightCompress 量化探索实验执行脚本 (重构版)

原始脚本已被拆分为模块化组件，此文件作为主入口。
模块结构见 lib/__init__.py

支持两种调用模式：
1. manifest 模式: --manifest manifest.json
2. 简化参数模式: --model /path/to/model --model-type Qwen2 --method gptq ...
"""

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from lib import (
    ExperimentRunner,
    ReportGenerator,
    find_existing_experiment_dir,
    fmt_metric,
    load_yaml_config,
    sanitize_fragment,
    update_pretrain_cache,
)


def die(message: str) -> None:
    """抛出系统退出异常"""
    raise SystemExit(message)


def compute_task_name(experiment: dict, current_date: str) -> str:
    """计算任务名称"""
    specification = experiment.get("specification", "_")
    return (
        f"{experiment['algo']}_{experiment['w_q']}_{experiment['a_q']}_"
        f"{specification}_{experiment['model_name']}_{current_date}"
    )


def validate_manifest(manifest: dict) -> None:
    """验证 manifest 格式"""
    required_top = ["workspace_root", "run_script_path", "env_activate", "experiments"]
    for key in required_top:
        if key not in manifest:
            die(f"manifest 缺少顶层字段: {key}")
    if not isinstance(manifest["experiments"], list) or not manifest["experiments"]:
        die("manifest.experiments 必须是非空数组")

    current_date = dt.datetime.now().strftime("%Y%m%d")
    task_names = set()

    for index, experiment in enumerate(manifest["experiments"], start=1):
        required_exp = [
            "model_name",
            "model_type",
            "model_path",
            "method_name",
            "algo",
            "w_q",
            "a_q",
        ]
        for key in required_exp:
            if key not in experiment or experiment[key] in ("", None):
                die(f"第 {index} 个 experiment 缺少字段: {key}")
        task_name = compute_task_name(experiment, current_date)
        if task_name in task_names:
            die("存在重复 task_name，请调整至少一个 experiment 的 " f"`specification` 字段以保证唯一: {task_name}")
        task_names.add(task_name)


def load_manifest(path: Path) -> dict:
    """加载并验证 manifest"""
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_manifest(data)
    return data


def ensure_paths(manifest: dict, prepare_only: bool = False) -> None:
    """确保路径存在并创建实验目录

    Args:
        manifest: 实验配置
        prepare_only: 只准备模式，跳过 run_script_path 检查
    """
    workspace_root = Path(manifest["workspace_root"]).expanduser().resolve()
    env_activate = Path(manifest["env_activate"]).expanduser().resolve()

    if not workspace_root.exists():
        die(f"workspace_root 不存在: {workspace_root}")
    if not env_activate.exists():
        die(f"env_activate 不存在: {env_activate}")

    # 设置 run_script_path
    run_script_path = Path(manifest["run_script_path"]).expanduser().resolve()
    if not prepare_only:
        if not run_script_path.exists():
            die(f"run_script_path 不存在: {run_script_path}")
    manifest["run_script_path"] = str(run_script_path)

    output_root = workspace_root

    # 确定实验名称
    experiment_name = manifest.get("experiment_name", "")
    if not experiment_name and manifest["experiments"]:
        first_exp = manifest["experiments"][0]
        model_name = first_exp.get("model_name", "unknown")
        algo = first_exp.get("algo", "unknown")
        experiment_name = f"{model_name}_{algo}"

    experiment_name = sanitize_fragment(experiment_name)

    # 删除已存在的失败实验目录
    find_existing_experiment_dir(output_root, experiment_name)

    # 创建新的实验目录
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    experiment_dir = output_root / f"{experiment_name}_{timestamp}"
    experiment_dir.mkdir(parents=True, exist_ok=True)

    # 创建子目录
    (experiment_dir / "configs").mkdir(exist_ok=True)
    (experiment_dir / "logs").mkdir(exist_ok=True)
    if manifest.get("save_artifacts", False):
        (experiment_dir / "artifacts").mkdir(exist_ok=True)

    manifest["workspace_root"] = str(workspace_root)
    manifest["env_activate"] = str(env_activate)
    manifest["output_root"] = str(output_root)
    manifest["experiment_dir"] = str(experiment_dir)
    manifest["experiment_name"] = experiment_name
    manifest["timestamp"] = timestamp

    # 保存 manifest 快照
    manifest_snapshot = experiment_dir / "manifest.json"
    manifest_snapshot.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    for experiment in manifest["experiments"]:
        model_path = Path(experiment["model_path"]).expanduser().resolve()
        if not model_path.exists():
            die(f"model_path 不存在: {model_path}")
        experiment["model_path"] = str(model_path)


# =============================================================================
# 简化参数模式
# =============================================================================


def build_manifest_from_simple_args(args) -> dict:
    """从简化参数构建 manifest"""
    # 确定 model_name
    model_path = Path(args.model).expanduser().resolve()
    model_name = args.model_name or model_path.name

    # 确定 method_name 和 algo
    method = args.method.lower()
    method_map = {
        "rtn": ("RTN", "RTN"),
        "gptq": ("GPTQ", "GPTQ"),
        "awq": ("AWQ", "AWQ"),
        "smoothquant": ("SmoothQuant", "SmoothQuant"),
        "quarot": ("QuaRot", "QuaRot"),
        "omniquant": ("OmniQuant", "OmniQuant"),
    }
    method_name, algo = method_map.get(method, (method.upper(), method.upper()))

    # 构建 w_q 和 a_q
    w_q = f"w{args.w_bit}_per_channel"
    a_q = f"a{args.a_bit}_per_token" if args.a_bit < 16 else "a16"

    # 构建 experiment
    experiment = {
        "model_name": model_name,
        "model_type": args.model_type,
        "model_path": str(model_path),
        "method_name": method_name,
        "algo": algo,
        "w_q": w_q,
        "a_q": a_q,
    }

    if args.fast_mode:
        experiment["fast_mode"] = True

    # 确定实验目录
    workspace_root = Path(args.workspace or Path.cwd() / "experiments").expanduser().resolve()
    workspace_root.mkdir(parents=True, exist_ok=True)

    # 确定环境激活脚本路径
    env_activate = args.env_activate
    if not env_activate:
        raise SystemExit("未指定 --env-activate，请提供 conda.sh 路径或确保已激活环境")

    # 确定 run_llmc.sh 路径
    # scripts/ -> skill_dir/ -> skills/ -> .claude/ -> project_root/
    default_run_script = str(
        Path(__file__).parent.parent.parent.parent.parent
        / "llm_compression"
        / "lightcompress"
        / "scripts"
        / "run_llmc.sh"
    )
    run_script_path = args.run_script or default_run_script
    run_script_path = str(Path(run_script_path).expanduser().resolve())

    # 构建 manifest
    manifest = {
        "workspace_root": str(workspace_root),
        "run_script_path": run_script_path,
        "env_activate": env_activate,
        "experiments": [experiment],
        "save_artifacts": args.save_artifacts,
        "experiment_name": args.experiment_name or f"{model_name}_{method_name}",
    }

    return manifest


def print_simple_mode_summary(manifest: dict) -> None:
    """打印简化模式摘要"""
    exp = manifest["experiments"][0]
    print("\n" + "=" * 60, flush=True)
    print("📋 实验配置", flush=True)
    print("=" * 60, flush=True)
    print(f"模型: {exp['model_name']}", flush=True)
    print(f"  - 类型: {exp['model_type']}", flush=True)
    print(f"  - 路径: {exp['model_path']}", flush=True)
    print(f"量化方法: {exp['method_name']}", flush=True)
    print(f"量化配置: {exp['w_q']} / {exp['a_q']}", flush=True)
    print(f"工作目录: {manifest['workspace_root']}", flush=True)
    print(f"保存产物: {'是' if manifest.get('save_artifacts', False) else '否'}", flush=True)
    print("=" * 60 + "\n", flush=True)


def confirm_and_run_simple(manifest: dict, skip_confirm: bool = False) -> bool:
    """确认并执行简化模式"""
    if skip_confirm:
        return True

    # 如果 stdin 是 TTY，尝试交互式确认
    if sys.stdin.isatty():
        try:
            response = input("确认开始实验? [y/N]: ").strip().lower()
            return response in ("y", "yes", "是")
        except EOFError:
            return False

    # 非交互式模式下默认需要外部确认
    print("⚠️  非交互模式，请使用 --yes 跳过确认", flush=True)
    return False


# =============================================================================
# 主函数
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="Run LightCompress quant exploration experiments")

    # 执行模式：优先处理 --execute
    parser.add_argument("--execute", help="执行已准备的实验目录路径")

    # 模式选择
    mode_group = parser.add_mutually_exclusive_group(required=False)
    mode_group.add_argument("--manifest", help="JSON manifest path (传统模式)")

    # 简化参数模式
    mode_group.add_argument("--model", help="模型路径 (简化模式)")

    # 简化模式参数
    parser.add_argument("--model-type", help="模型类型 (如 Qwen2, InternVL2)")
    parser.add_argument("--model-name", help="模型名称 (默认从路径推断)")
    parser.add_argument("--method", help="量化方法 (rtn/gptq/awq/smoothquant/quarot/omniquant)")
    parser.add_argument("--w-bit", type=int, default=4, help="权重量化位宽 (默认: 4)")
    parser.add_argument("--a-bit", type=int, default=16, help="激活量化位宽 (默认: 16, 表示不量化激活)")
    parser.add_argument("--fast-mode", action="store_true", help="快速验证模式 (n_samples=1, seq_len=128)")
    parser.add_argument("--yes", action="store_true", help="跳过确认直接执行")
    parser.add_argument("--workspace", help="工作目录 (默认: ./experiments)")
    parser.add_argument("--env-activate", help="conda 激活脚本路径")
    parser.add_argument("--run-script", help="run_llmc.sh 路径")
    parser.add_argument("--save-artifacts", action="store_true", help="保存量化产物")
    parser.add_argument("--experiment-name", help="实验名称")
    parser.add_argument("--prepare-only", action="store_true", help="只准备实验，不执行（生成 YAML 后退出）")

    args = parser.parse_args()

    # 执行模式：直接运行已准备好的实验
    if args.execute:
        experiment_dir = Path(args.execute).expanduser().resolve()
        manifest_file = experiment_dir / "manifest.json"
        if not manifest_file.exists():
            die(f"实验目录中未找到 manifest.json: {experiment_dir}")
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        manifest["experiment_dir"] = str(experiment_dir)
        run_experiments(manifest)
        return

    # 非执行模式需要 model 或 manifest
    if not args.model and not args.manifest:
        die("需要提供 --model 或 --manifest 参数")

    # 根据 mode 选择执行路径
    if args.manifest:
        # 传统 manifest 模式
        manifest_path = Path(args.manifest).expanduser().resolve()
        if not manifest_path.exists():
            die(f"manifest 不存在: {manifest_path}")

        manifest = load_manifest(manifest_path)
        ensure_paths(manifest, prepare_only=args.prepare_only)
    else:
        # 简化参数模式
        if not args.model:
            die("--model 参数是必需的")
        if not args.model_type:
            die("--model-type 参数是必需的 (如: Qwen2, InternVL2, Llama)")
        if not args.method:
            die("--method 参数是必需的 (如: gptq, awq, rtn)")

        manifest = build_manifest_from_simple_args(args)
        print_simple_mode_summary(manifest)

        if not args.prepare_only and not args.yes:
            if not confirm_and_run_simple(manifest, False):
                die("用户取消")

        ensure_paths(manifest, prepare_only=args.prepare_only)

    # 准备模式：只生成配置，不执行
    if args.prepare_only:
        experiment_dir = Path(manifest["experiment_dir"])
        # 生成 YAML 配置
        from lib import generate_yaml_config

        for experiment in manifest["experiments"]:
            if not experiment.get("config_path"):
                config_path = generate_yaml_config(experiment, experiment_dir)
                experiment["config_path"] = config_path

        # 输出 YAML 配置内容
        for experiment in manifest["experiments"]:
            config_path = experiment.get("config_path", "")
            if config_path and Path(config_path).exists():
                print(f"\n{'='*60}", flush=True)
                print(f"YAML 配置: {config_path}", flush=True)
                print("=" * 60, flush=True)
                print(Path(config_path).read_text(encoding="utf-8"), flush=True)

        print(f"\n{'='*60}", flush=True)
        print("实验准备完成！", flush=True)
        print(f"实验目录: {experiment_dir}", flush=True)
        print(f"{'='*60}", flush=True)
        print(
            json.dumps(
                {
                    "experiment_dir": str(experiment_dir),
                    "config_path": manifest["experiments"][0].get("config_path", ""),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    run_experiments(manifest)


def run_experiments(manifest: dict) -> None:
    """执行实验"""
    experiment_dir = Path(manifest["experiment_dir"])
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
        print(
            f"[{idx}/{total_experiments}] 开始实验: {experiment['model_name']} - {experiment['method_name']}",
            flush=True,
        )
        print(f"{'='*60}", flush=True)

        result = runner.run(experiment)
        result_item = {"experiment": experiment, "result": result}
        collected_results.append(result_item)

        # 更新 pretrain 缓存
        if result["status"] == "success" and result["metrics"].get("pretrain") is not None:
            yaml_config = load_yaml_config(experiment.get("config_path", ""))
            eval_config = yaml_config.get("eval", {})
            update_pretrain_cache(experiment["model_name"], eval_config, result["metrics"]["pretrain"])

        # 增量更新报告
        report_generator.update(collected_results, idx, total_experiments)

        if result["status"] == "success":
            metrics = result["metrics"]
            print(
                f"\n[完成] PPL: pretrain={fmt_metric(metrics['pretrain'])}, "
                f"transformed={fmt_metric(metrics['transformed'])}, "
                f"fake_quant={fmt_metric(metrics['fake_quant'])}",
                flush=True,
            )
            if result.get("quantized_layers", {}).get("summary"):
                print(f"[量化层] {result['quantized_layers']['summary']}", flush=True)
        else:
            print(f"\n[失败] 原因: {result.get('error', 'unknown')}", flush=True)

    # 最终完整报告
    report_generator.render_final(collected_results)

    print(f"\n{'='*60}", flush=True)
    print("实验完成！", flush=True)
    print(f"实验目录: {experiment_dir}", flush=True)
    print(f"报告路径: {report_path}", flush=True)
    print(f"{'='*60}", flush=True)

    print(
        json.dumps(
            {"experiment_dir": str(experiment_dir), "report_path": str(report_path), "results": collected_results},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
