#!/usr/bin/env python3
"""
LightCompress 量化实验准备脚本

功能：
1. 创建实验目录
2. 生成 YAML 配置文件
3. 保存 manifest 快照

使用：
    python prepare_experiment.py --model /path/to/model --model-type Qwen2 --method gptq --w-bit 4 --a-bit 8
"""

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

# 添加 lib 目录到路径
sys.path.insert(0, str(Path(__file__).parent))
from lib import (
    CalibSampleOptimizer,
    estimate_model_size,
    find_existing_experiment_dir,
    generate_yaml_config,
    sanitize_fragment,
)


def die(message: str) -> None:
    """抛出系统退出异常"""
    raise SystemExit(message)


def parse_mix_bits(specs: list) -> dict:
    """解析 --mix-bits 参数为 mix_bits 配置 dict。

    每个 spec 形如:
        "name=qo_experts_w4;bit=4;layers=self_attn.q_proj,experts.experts.*.gate_proj"
    可多次传入(多个混合精度组)。

    返回:
        {"qo_experts_w4": {"layer_name": [...], "weight": {"bit": 4}}}
    """
    mix_bits = {}
    for idx, spec in enumerate(specs):
        fields = {}
        for part in spec.split(";"):
            part = part.strip()
            if not part:
                continue
            if "=" not in part:
                die(f"--mix-bits 格式错误(缺 '='): {part}")
            k, v = part.split("=", 1)
            fields[k.strip()] = v.strip()

        if "bit" not in fields or "layers" not in fields:
            die(f"--mix-bits 每组必须含 bit= 和 layers=: {spec}")

        name = fields.get("name", f"mix_bits_{idx}")
        layers = [x.strip() for x in fields["layers"].split(",") if x.strip()]
        if not layers:
            die(f"--mix-bits layers 为空: {spec}")
        mix_bits[name] = {
            "layer_name": layers,
            "weight": {"bit": int(fields["bit"])},
        }
    return mix_bits


def parse_special(specs: list) -> dict:
    """解析 --special KEY=VAL 列表为 special 覆盖 dict,自动转 bool/int/float。"""
    out = {}
    for spec in specs:
        if "=" not in spec:
            die(f"--special 格式错误(应为 KEY=VAL): {spec}")
        k, v = spec.split("=", 1)
        k, v = k.strip(), v.strip()
        if v.lower() in ("true", "false"):
            out[k] = v.lower() == "true"
        elif v.lstrip("-").isdigit():
            out[k] = int(v)
        else:
            try:
                out[k] = float(v)
            except ValueError:
                out[k] = v
    return out


def build_manifest(args) -> dict:
    """从参数构建 manifest"""
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

    # 混合精度 mix_bits
    if args.mix_bits:
        experiment["mix_bits"] = parse_mix_bits(args.mix_bits)

    # special 参数覆盖(percdamp/actorder 等)
    if args.special:
        experiment["special_overrides"] = parse_special(args.special)

    # calib / eval / save 透传(None 表示用默认,由 config.py 决定)
    calib_overrides = {
        "path": args.calib_path,
        "name": args.calib_name,
        "n_samples": args.calib_n_samples,
        "seq_len": args.calib_seq_len,
        "preproc": args.calib_preproc,
    }
    calib_overrides = {k: v for k, v in calib_overrides.items() if v is not None}
    if calib_overrides:
        experiment["calib_overrides"] = calib_overrides

    eval_overrides = {
        "path": args.eval_path,
        "seq_len": args.eval_seq_len,
    }
    eval_overrides = {k: v for k, v in eval_overrides.items() if v is not None}
    if args.no_eval_pretrain:
        eval_overrides["only_fake_quant"] = True
    if args.inference_per_block:
        eval_overrides["inference_per_block"] = True
    if eval_overrides:
        experiment["eval_overrides"] = eval_overrides

    if args.save_path:
        experiment["save_path"] = args.save_path

    # 确定实验目录
    workspace_root = Path(args.workspace or Path.cwd() / "experiments").expanduser().resolve()
    workspace_root.mkdir(parents=True, exist_ok=True)

    # 确定环境激活脚本路径
    env_activate = args.env_activate
    if not env_activate:
        raise SystemExit("未指定 --env-activate，请提供 conda.sh 路径或确保已激活环境")

    # 确定 run_llmc.sh 路径
    # 基于脚本位置动态计算: scripts/ -> skill_dir/ -> skills/ -> .claude/ -> project_root/
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


def print_summary(manifest: dict) -> None:
    """打印实验摘要"""
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


def prepare_experiment(manifest: dict) -> str:
    """准备实验环境"""
    workspace_root = Path(manifest["workspace_root"])
    env_activate = Path(manifest["env_activate"])

    if not workspace_root.exists():
        die(f"workspace_root 不存在: {workspace_root}")
    if not env_activate.exists():
        die(f"env_activate 不存在: {env_activate}")

    # 确定实验名称
    experiment_name = manifest.get("experiment_name", "")
    if not experiment_name and manifest["experiments"]:
        first_exp = manifest["experiments"][0]
        model_name = first_exp.get("model_name", "unknown")
        algo = first_exp.get("algo", "unknown")
        experiment_name = f"{model_name}_{algo}"

    experiment_name = sanitize_fragment(experiment_name)

    # 删除已存在的失败实验目录
    find_existing_experiment_dir(workspace_root, experiment_name)

    # 创建新的实验目录
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    experiment_dir = workspace_root / f"{experiment_name}_{timestamp}"
    experiment_dir.mkdir(parents=True, exist_ok=True)

    # 创建子目录
    (experiment_dir / "configs").mkdir(exist_ok=True)
    (experiment_dir / "logs").mkdir(exist_ok=True)
    if manifest.get("save_artifacts", False):
        (experiment_dir / "artifacts").mkdir(exist_ok=True)

    # 更新 manifest
    manifest["env_activate"] = str(env_activate)
    manifest["output_root"] = str(workspace_root)
    manifest["experiment_dir"] = str(experiment_dir)
    manifest["experiment_name"] = experiment_name
    manifest["timestamp"] = timestamp

    # 验证模型路径
    for experiment in manifest["experiments"]:
        model_path = Path(experiment["model_path"]).expanduser().resolve()
        if not model_path.exists():
            die(f"model_path 不存在: {model_path}")
        experiment["model_path"] = str(model_path)

    # 生成 YAML 配置
    for experiment in manifest["experiments"]:
        config_path = generate_yaml_config(experiment, experiment_dir)
        experiment["config_path"] = config_path

        # 校准样本数自动优化
        # 注意：用户通过 --calib-n-samples 显式指定时视为明确意图，跳过基于显存的自动降级，
        # 仅在用户未指定时才按显存估算调整(避免静默破坏用户配置)。
        model_path = Path(experiment["model_path"])
        model_info = estimate_model_size(model_path)
        method = experiment.get("algo", "RTN")

        user_set_n_samples = "n_samples" in experiment.get("calib_overrides", {})
        if user_set_n_samples:
            n = experiment["calib_overrides"]["n_samples"]
            print(f"[校准样本] 使用用户显式值 n_samples={n}，跳过显存自动降级", flush=True)
        else:
            optimized_path, changes = CalibSampleOptimizer.optimize_yaml(config_path, model_info, method)
            if changes:
                experiment["config_path"] = optimized_path

    # 保存 manifest 快照
    manifest_snapshot = experiment_dir / "manifest.json"
    manifest_snapshot.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return str(experiment_dir)


def main():
    parser = argparse.ArgumentParser(description="准备 LightCompress 量化实验环境")

    # 必需参数
    parser.add_argument("--model", required=True, help="模型路径")
    parser.add_argument("--model-type", required=True, help="模型类型 (如 Qwen2, InternVL2)")
    parser.add_argument("--method", required=True, help="量化方法 (rtn/gptq/awq/smoothquant/quarot/omniquant)")

    # 可选参数
    parser.add_argument("--model-name", help="模型名称 (默认从路径推断)")
    parser.add_argument("--w-bit", type=int, default=4, help="权重量化位宽 (默认: 4)")
    parser.add_argument("--a-bit", type=int, default=16, help="激活量化位宽 (默认: 16)")
    parser.add_argument("--fast-mode", action="store_true", help="快速验证模式")
    parser.add_argument("--workspace", help="工作目录 (默认: ./experiments)")
    parser.add_argument("--env-activate", help="conda 激活脚本路径")
    parser.add_argument("--run-script", help="run_llmc.sh 路径")
    parser.add_argument("--save-artifacts", action="store_true", help="保存量化产物")
    parser.add_argument("--experiment-name", help="实验名称")

    # 混合精度
    parser.add_argument(
        "--mix-bits", action="append", default=[],
        help='混合精度组,可多次传入。格式: "name=NAME;bit=4;layers=l1,l2,..." '
             '例: --mix-bits "name=qo_experts_w4;bit=4;layers=self_attn.q_proj,self_attn.o_proj,'
             'experts.experts.*.gate_proj,experts.experts.*.up_proj,experts.experts.*.down_proj"'
    )
    # 量化方法 special 参数覆盖
    parser.add_argument(
        "--special", action="append", default=[],
        help="覆盖 quant.special 参数,可多次。格式 KEY=VAL,例: --special percdamp=0.01 --special actorder=true"
    )
    # calib 参数
    parser.add_argument("--calib-path", help="校准数据集路径(默认内置 wikitext2_calib)")
    parser.add_argument("--calib-name", help="校准数据集名(默认 wikitext2)")
    parser.add_argument("--calib-n-samples", type=int, help="校准样本数(用户显式值不被降级)")
    parser.add_argument("--calib-seq-len", type=int, help="校准序列长度")
    parser.add_argument("--calib-preproc", help="校准预处理(默认 wikitext2_gptq)")
    # eval 参数
    parser.add_argument("--eval-path", help="评估数据集路径(默认内置 wikitext2_eval)")
    parser.add_argument("--eval-seq-len", type=int, help="评估序列长度")
    parser.add_argument("--no-eval-pretrain", action="store_true", help="只评 fake_quant,跳过 pretrain 评测")
    parser.add_argument("--inference-per-block", action="store_true", help="逐 block 推理评测(大模型省显存)")
    # save
    parser.add_argument("--save-path", help="fakequant 模型保存路径(指定即开启 save_fake)")

    args = parser.parse_args()

    # 构建 manifest
    manifest = build_manifest(args)
    print_summary(manifest)

    # 准备实验环境
    experiment_dir = prepare_experiment(manifest)

    # 读取生成的 YAML 配置（使用优化后的配置路径）
    config_path = manifest["experiments"][0].get("config_path", "")
    yaml_content = ""
    if config_path and Path(config_path).exists():
        yaml_content = Path(config_path).read_text(encoding="utf-8")

    # 输出结果
    print(f"\n{'='*60}", flush=True)
    print(f"YAML 配置: {config_path}", flush=True)
    print("=" * 60, flush=True)
    print(yaml_content, flush=True)

    print(f"\n{'='*60}", flush=True)
    print("实验准备完成！", flush=True)
    print(f"实验目录: {experiment_dir}", flush=True)
    print(f"{'='*60}", flush=True)

    # 输出 JSON 结果供 Claude 解析
    print(
        json.dumps(
            {"experiment_dir": experiment_dir, "config_path": config_path, "yaml_content": yaml_content},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
