#!/usr/bin/env python3
"""HMCT PTQ Precision Tuning Automation Script.

Handles phases 1-7 of cosine similarity tuning workflow.
Merged from hmct_precision_tuning.py and hmct_debug_impl.py.

Usage:
    # Full auto tuning
    python hmct_precision_tuning.py --onnx_path model.onnx --cali_data_dir ./cali_data

    # With user fixed node config
    python hmct_precision_tuning.py --onnx_path model.onnx --cali_data_dir ./cali_data \
        --node_config_path fixed_config.json

    # Custom progressive thresholds
    python hmct_precision_tuning.py --onnx_path model.onnx --cali_data_dir ./cali_data \
        --progressive_thresholds 0.99 0.999 0.9999
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

try:
    from hmct.api import build_model
    from hmct.ir import OnnxModel
except ImportError:
    logger.error("HMCT not installed. Please install hmct package first.")
    raise


# ============================================================
# Constants & Phase Configuration
# ============================================================

DEFAULT_COS_THRESHOLD = 0.99

PROGRESSIVE_THRESHOLDS = [0.99, 0.999, 0.9999, 0.99999]

DUAL_INT16_QTYPE = {"input0": "int16", "input1": "int16"}


class Phase:
    """Tuning phases as constants for clarity."""

    INT8_BASELINE = 1
    INT16_UPPER = 2
    INT8_INT16_MIXED = 3
    INT16_DUAL_INT16 = 4
    INT16_DUAL_INT16_MIXED = 5
    FP16 = 6
    INT16_DUAL_INT16_FP16_MIXED = 7

    _NAMES = {
        1: "INT8_BASELINE",
        2: "INT16_UPPER",
        3: "INT8_INT16_MIXED",
        4: "INT16_DUAL_INT16",
        5: "INT16_DUAL_INT16_MIXED",
        6: "FP16",
        7: "INT16_DUAL_INT16_FP16_MIXED",
    }

    @classmethod
    def name(cls, phase: int) -> str:
        return cls._NAMES.get(phase, f"UNKNOWN_{phase}")


@dataclass
class PhaseConfig:
    """Configuration for each phase."""

    save_dir: str
    all_node_type: str
    op_config: dict = field(default_factory=dict)
    baseline_save_dir: Optional[str] = None
    fallback_save_dir: Optional[str] = None
    target_qtype: Any = ""


PHASE_CONFIGS = {
    Phase.INT8_BASELINE: PhaseConfig(
        save_dir="output_int8",
        all_node_type="int8",
    ),
    Phase.INT16_UPPER: PhaseConfig(
        save_dir="output_int16",
        all_node_type="int16",
    ),
    Phase.INT8_INT16_MIXED: PhaseConfig(
        save_dir="output_int8_int16_mixed",
        all_node_type="int8",
        baseline_save_dir="output_int8",
        fallback_save_dir="output_int16",
        target_qtype="int16",
    ),
    Phase.INT16_DUAL_INT16: PhaseConfig(
        save_dir="output_dual_int16",
        all_node_type="int16",
        op_config={
            "Conv": {"qtype": "dual-int16"},
            "Gemm": {"qtype": "dual-int16"},
            "MatMul": {"qtype": "dual-int16"},
        },
    ),
    Phase.INT16_DUAL_INT16_MIXED: PhaseConfig(
        save_dir="output_int16_dual_int16_mixed",
        all_node_type="int16",
        op_config={
            "Conv": {"qtype": "dual-int16"},
            "Gemm": {"qtype": "dual-int16"},
            "MatMul": {"qtype": "dual-int16"},
        },
        baseline_save_dir="output_int16",
        fallback_save_dir="output_dual_int16",
        target_qtype=DUAL_INT16_QTYPE,
    ),
    Phase.FP16: PhaseConfig(
        save_dir="output_float16",
        all_node_type="float16",
    ),
    Phase.INT16_DUAL_INT16_FP16_MIXED: PhaseConfig(
        save_dir="output_dual_int16_float16_mixed",
        all_node_type="int16",
        op_config={
            "Conv": {"qtype": "dual-int16"},
            "Gemm": {"qtype": "dual-int16"},
            "MatMul": {"qtype": "dual-int16"},
        },
        baseline_save_dir="output_dual_int16",
        fallback_save_dir="output_float16",
        target_qtype="float16",
    ),
}


# ============================================================
# Calibration Data Loading (merged from hmct_debug_impl.py)
# ============================================================


def load_cali_data(
    onnx_path: str,
    cali_data_dir: str,
) -> Dict[str, List[np.ndarray]]:
    """Load calibration data from directory.

    Directory structure:
        cali_data_dir/
        ├── input_name_0/
        │   ├── 0.npy
        │   └── ...
        └── input_name_1/
            └── ...
    """
    onnx_model = OnnxModel(onnx_path)
    input_names = onnx_model.graph.input_names

    cali_data: Dict[str, List[np.ndarray]] = {name: [] for name in input_names}

    for input_name in sorted(os.listdir(cali_data_dir)):
        input_dir = os.path.join(cali_data_dir, input_name)
        if not os.path.isdir(input_dir):
            continue
        if input_name not in cali_data:
            logger.warning(
                "Directory '%s' not in model inputs %s, skipping.",
                input_name,
                input_names,
            )
            continue
        npy_files = sorted(f for f in os.listdir(input_dir) if f.endswith(".npy"))
        for npy_name in npy_files:
            cali_data[input_name].append(
                np.load(os.path.join(input_dir, npy_name))
            )
        logger.info(
            "Loaded %d calibration samples for input '%s'.",
            len(cali_data[input_name]),
            input_name,
        )

    return cali_data


# ============================================================
# HMCT Build (direct API call, replaces subprocess)
# ============================================================


def run_hmct_build(
    onnx_path: str,
    cali_data: Dict[str, List[np.ndarray]],
    save_dir: str,
    march: str,
    quant_config: dict,
) -> str:
    """Run HMCT build_model directly and return log path."""
    os.makedirs(save_dir, exist_ok=True)

    config_path = os.path.join(save_dir, "quant_config.json")
    with open(config_path, "w") as f:
        json.dump(quant_config, f, indent=2)

    log_path = os.path.join(save_dir, "hmct.log")
    name_prefix = os.path.join(save_dir, "model")

    # Add file handler to capture HMCT logging output
    file_handler = logging.FileHandler(log_path, mode="w")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )
    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)

    try:
        logger.info("Running HMCT build_model (march=%s)...", march)
        ptq_model = build_model(
            onnx_file=onnx_path,
            march=march,
            cali_data=cali_data,
            quant_config=quant_config,
            name_prefix=name_prefix,
            save_model=True,
            verbose=True,
        )
        if ptq_model is None:
            logger.error("build_model returned None")
    except Exception:
        logger.exception("HMCT build_model failed")
    finally:
        root_logger.removeHandler(file_handler)
        file_handler.close()

    return log_path


# ============================================================
# Log Parsing
# ============================================================


def parse_cosine_similarity_from_log(log_path: str) -> Dict[str, float]:
    """Parse cosine similarity results from HMCT log."""
    results: Dict[str, float] = {}

    if not os.path.exists(log_path):
        logger.warning("Log file not found: %s", log_path)
        return results

    with open(log_path, "r") as f:
        content = f.read()

    # Pattern 1: "output_name: cosine_similarity=0.9987"
    pattern = r"(\S+)\s*[:\s]+cosine[_\s]?similarity\s*[=:]\s*([\d.]+)"
    matches = re.findall(pattern, content, re.IGNORECASE)
    for name, value in matches:
        results[name] = float(value)

    # Pattern 2: HMCT table after "The quantized model output:"
    if not results and "The quantized model output:" in content:
        section = content.split("The quantized model output:")[1]
        for line in section.split("\n"):
            if "Output" in line or "---" in line or "Cosine Similarity" in line:
                continue
            parts = line.split()
            if len(parts) >= 2:
                try:
                    name = parts[0]
                    value = float(parts[1])
                    if 0 <= value <= 1:
                        results[name] = value
                except (ValueError, IndexError):
                    continue

    # Pattern 3: pipe-delimited table
    if not results:
        pipe_pattern = r"\|\s*(\S+)\s*\|\s*([\d.]+)\s*\|"
        for line in content.split("\n"):
            if "cos" in line.lower() or "similarity" in line.lower():
                for name, value in re.findall(pipe_pattern, line):
                    if name not in ("name", "tensor", "output", "---"):
                        try:
                            results[name] = float(value)
                        except ValueError:
                            continue

    logger.info("Parsed %d cosine similarity results from %s", len(results), log_path)
    return results


def normalize_node_name(node_name: str) -> str:
    """Normalize node name by removing _FROM_QUANTIZED_SOFTMAX suffix.

    Example:
        Softmax_618_reciprocal_FROM_QUANTIZED_SOFTMAX -> Softmax_618
    """
    return re.sub(r"_[a-zA-Z]+_FROM_QUANTIZED_SOFTMAX$", "", node_name)


def parse_node_sensitivity(log_path: str) -> Dict[str, float]:
    """Parse node sensitivity log to get node cosine similarities."""
    sensitivities: Dict[str, float] = {}

    if not os.path.exists(log_path):
        logger.warning("Sensitivity log not found: %s", log_path)
        return sensitivities

    with open(log_path, "r") as f:
        content = f.read()

    # Table format: "node_name   0.15596"
    if "node sensitivity" in content.lower():
        for line in content.split("\n"):
            if ("node" in line.lower() and "cosine" in line.lower()) or "---" in line:
                continue
            parts = line.split()
            if len(parts) >= 2:
                try:
                    name = parts[0]
                    value = float(parts[1])
                    if 0 <= value <= 1:
                        normalized = normalize_node_name(name)
                        if (
                            normalized not in sensitivities
                            or value < sensitivities[normalized]
                        ):
                            sensitivities[normalized] = value
                except (ValueError, IndexError):
                    continue

    # Fallback: "node_name: cosine_similarity=0.xxx"
    if not sensitivities:
        pattern = r"(\S+)\s*[:\s]+(?:cosine[_\s]?similarity)?\s*[=:]\s*([\d.]+)"
        for name, value in re.findall(pattern, content, re.IGNORECASE):
            try:
                normalized = normalize_node_name(name)
                val = float(value)
                if normalized not in sensitivities or val < sensitivities[normalized]:
                    sensitivities[normalized] = val
            except ValueError:
                continue

    logger.info("Parsed %d node sensitivities from %s", len(sensitivities), log_path)
    return sensitivities


# ============================================================
# Sensitivity Analysis
# ============================================================


def run_sensitivity_analysis(
    calibrated_model_path: str,
    cali_data_dir: str,
    save_dir: str,
    num_sample: int = 1,
) -> str:
    """Run sensitivity analysis and return node_sensitivity.log path."""
    os.makedirs(save_dir, exist_ok=True)

    script_path = Path(__file__).parent / "get_sensitivity_of_nodes.py"
    if not script_path.exists():
        raise FileNotFoundError(
            f"get_sensitivity_of_nodes.py not found at {script_path}."
        )

    log_path = os.path.join(save_dir, "sensitivity.log")
    node_sensitivity_path = os.path.join(save_dir, "node_sensitivity.log")

    cmd = [
        sys.executable,
        str(script_path),
        "--calibrated_model_path",
        calibrated_model_path,
        "--cali_data_dir",
        cali_data_dir,
        "--metric",
        "cosine-similarity",
        "--num_sample",
        str(num_sample),
        "--save_dir",
        save_dir,
    ]

    logger.info("Running sensitivity analysis: %s", " ".join(cmd))

    with open(log_path, "w") as log_file:
        result = subprocess.run(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )

    if result.returncode != 0:
        logger.error(
            "Sensitivity analysis failed (returncode=%d). Check: %s",
            result.returncode,
            log_path,
        )

    return node_sensitivity_path


# ============================================================
# Utilities
# ============================================================


def check_threshold_met(
    cos_results: Dict[str, float],
    threshold: float,
) -> bool:
    """Check if all outputs meet the cosine similarity threshold."""
    if not cos_results:
        logger.warning("No cosine similarity results to check")
        return False

    all_met = True
    for name, value in cos_results.items():
        if value < threshold:
            logger.info("  %s: %.6f < %.4f (NOT MET)", name, value, threshold)
            all_met = False
        else:
            logger.info("  %s: %.6f >= %.4f (OK)", name, value, threshold)

    return all_met


def build_quant_config(
    all_node_type: str,
    op_config: dict,
    node_config: dict,
    user_node_config: dict,
    calibration_type: Optional[Union[str, List[str]]] = None,
    per_channel: Optional[Union[bool, List[bool]]] = None,
    asymmetric: Optional[Union[bool, List[bool]]] = None,
    bias_correction: Optional[bool] = None,
    bias_correction_num_sample: Optional[int] = None,
    bias_correction_metric: Optional[str] = None,
) -> dict:
    """Build quant_config with user config preserved (user overrides).

    Field placement matches HMCT's QuantConfig schema:
      - calibration_type / per_channel / asymmetric -> model_config.activation
      - bias_correction (with num_sample / metric)  -> model_config.weight

    Args:
        calibration_type: Activation calibration method (e.g. "max", "kl", "load",
            or a list like ["max", "kl"]). None => omit (HMCT default).
        per_channel: Per-channel activation quantization toggle. Accepts bool
            (False/True) or a list of bools to search both. None => omit
            (HMCT default = False).
        asymmetric: Asymmetric activation quantization toggle. Accepts bool
            (False/True) or a list of bools to search both. None => omit
            (HMCT default = False).
        bias_correction: If True, enable bias correction on weights. If False or
            None, the bias_correction field is omitted (HMCT default = disabled).
        bias_correction_num_sample: num_sample for bias_correction. int >= 1.
            Only applied when bias_correction is True. None => HMCT default (1).
        bias_correction_metric: model error metric for bias_correction. One of
            {"cosine-similarity", "mse", "mae", "mre", "sqnr", "chebyshev"}.
            Only applied when bias_correction is True. None => HMCT default
            ("cosine-similarity").
    """
    activation: dict = {}
    if calibration_type is not None:
        activation["calibration_type"] = calibration_type
    if per_channel is not None:
        activation["per_channel"] = per_channel
    if asymmetric is not None:
        activation["asymmetric"] = asymmetric

    weight: dict = {}
    if bias_correction is True:
        bc: dict = {}
        if bias_correction_num_sample is not None:
            bc["num_sample"] = bias_correction_num_sample
        if bias_correction_metric is not None:
            bc["metric"] = bias_correction_metric
        weight["bias_correction"] = bc

    model_config: dict = {"all_node_type": all_node_type}
    if activation:
        model_config["activation"] = activation
    if weight:
        model_config["weight"] = weight

    quant_config: dict = {"model_config": model_config}

    if op_config:
        quant_config["op_config"] = op_config.copy()

    merged_node_config = {}
    merged_node_config.update(node_config)
    merged_node_config.update(user_node_config)  # User config takes priority

    if merged_node_config:
        quant_config["node_config"] = merged_node_config

    return quant_config


def find_calibrated_model(save_dir: str) -> Optional[str]:
    """Find *_calibrated_model.onnx in save_dir."""
    if not os.path.isdir(save_dir):
        return None
    for f in os.listdir(save_dir):
        if f.endswith("_calibrated_model.onnx"):
            return os.path.join(save_dir, f)
    return None


def load_user_node_config(node_config_path: str) -> dict:
    """Load user-provided node_config."""
    if not node_config_path or not os.path.exists(node_config_path):
        return {}

    with open(node_config_path, "r") as f:
        config = json.load(f)

    if "node_config" in config:
        config = config["node_config"]

    logger.info(
        "Loaded user node_config with %d nodes from %s",
        len(config),
        node_config_path,
    )
    return config


# ============================================================
# Phase Execution
# ============================================================


def _make_result(
    phase: int,
    success: bool,
    cos_results: Dict[str, float],
    config_desc: str,
    quant_config: Optional[dict] = None,
) -> dict:
    return {
        "phase": phase,
        "phase_name": Phase.name(phase),
        "success": success,
        "cos_results": cos_results,
        "config": config_desc,
        "quant_config": quant_config or {},
    }


def run_phase(
    phase: int,
    onnx_path: str,
    cali_data: Dict[str, List[np.ndarray]],
    user_node_config: dict,
    work_dir: str,
    march: str,
    calibration_type: Optional[Union[str, List[str]]] = None,
    per_channel: Optional[Union[bool, List[bool]]] = None,
    asymmetric: Optional[Union[bool, List[bool]]] = None,
    bias_correction: Optional[bool] = None,
    bias_correction_num_sample: Optional[int] = None,
    bias_correction_metric: Optional[str] = None,
) -> Tuple[bool, Dict[str, float]]:
    """Run a single non-progressive phase. Returns (success, cosine_results)."""
    config = PHASE_CONFIGS[phase]
    save_dir = os.path.join(work_dir, config.save_dir)

    logger.info("")
    logger.info("=" * 60)
    logger.info("Phase %d: %s", phase, Phase.name(phase))
    logger.info("Save dir: %s", save_dir)
    logger.info("=" * 60)

    quant_config = build_quant_config(
        all_node_type=config.all_node_type,
        op_config=config.op_config,
        node_config={},
        user_node_config=user_node_config,
        calibration_type=calibration_type,
        per_channel=per_channel,
        asymmetric=asymmetric,
        bias_correction=bias_correction,
        bias_correction_num_sample=bias_correction_num_sample,
        bias_correction_metric=bias_correction_metric,
    )

    log_path = run_hmct_build(
        onnx_path=onnx_path,
        cali_data=cali_data,
        save_dir=save_dir,
        march=march,
        quant_config=quant_config,
    )

    cos_results = parse_cosine_similarity_from_log(log_path)
    success = check_threshold_met(cos_results, DEFAULT_COS_THRESHOLD)

    return success, cos_results


def run_progressive_fallback(
    phase: int,
    onnx_path: str,
    cali_data: Dict[str, List[np.ndarray]],
    cali_data_dir: str,
    user_node_config: dict,
    work_dir: str,
    march: str,
    num_sample: int,
    progressive_thresholds: List[float],
    calibration_type: Optional[Union[str, List[str]]] = None,
    per_channel: Optional[Union[bool, List[bool]]] = None,
    asymmetric: Optional[Union[bool, List[bool]]] = None,
    bias_correction: Optional[bool] = None,
    bias_correction_num_sample: Optional[int] = None,
    bias_correction_metric: Optional[str] = None,
) -> Tuple[bool, Dict[str, float], dict]:
    """Run progressive fallback phase (3, 5, or 7).

    Returns (success, cosine_results, final_quant_config).
    """
    config = PHASE_CONFIGS[phase]
    save_dir = os.path.join(work_dir, config.save_dir)

    logger.info("")
    logger.info("=" * 60)
    logger.info("Phase %d: %s", phase, Phase.name(phase))
    logger.info("Save dir: %s", save_dir)
    logger.info("=" * 60)

    # Find calibrated model from baseline phase
    baseline_save_dir = os.path.join(work_dir, config.baseline_save_dir)
    calibrated_model = find_calibrated_model(baseline_save_dir)

    if not calibrated_model:
        logger.error("Calibrated model not found in %s", baseline_save_dir)
        return False, {}, {}

    logger.info("Using calibrated model: %s", calibrated_model)

    # Run sensitivity analysis
    node_sensitivity_path = run_sensitivity_analysis(
        calibrated_model_path=calibrated_model,
        cali_data_dir=cali_data_dir,
        save_dir=save_dir,
        num_sample=num_sample,
    )

    sensitivities = parse_node_sensitivity(node_sensitivity_path)
    if not sensitivities:
        logger.error("No node sensitivities found")
        return False, {}, {}

    # Progressive threshold loop
    for threshold in progressive_thresholds:
        logger.info("")
        logger.info("--- Trying threshold <= %s ---", threshold)

        node_config: dict = {}
        for node_name, value in sensitivities.items():
            if value <= threshold and node_name not in user_node_config:
                if isinstance(config.target_qtype, dict):
                    node_config[node_name] = config.target_qtype.copy()
                else:
                    node_config[node_name] = {"qtype": config.target_qtype}

        logger.info(
            "Found %d nodes to upgrade to %s",
            len(node_config),
            config.target_qtype,
        )

        if threshold == progressive_thresholds[0] and not node_config:
            logger.info("No nodes below first threshold, moving to next")
            continue

        quant_config = build_quant_config(
            all_node_type=config.all_node_type,
            op_config=config.op_config,
            node_config=node_config,
            user_node_config=user_node_config,
            calibration_type=calibration_type,
            per_channel=per_channel,
            asymmetric=asymmetric,
            bias_correction=bias_correction,
            bias_correction_num_sample=bias_correction_num_sample,
            bias_correction_metric=bias_correction_metric,
        )

        round_save_dir = os.path.join(save_dir, f"threshold_{threshold}")
        log_path = run_hmct_build(
            onnx_path=onnx_path,
            cali_data=cali_data,
            save_dir=round_save_dir,
            march=march,
            quant_config=quant_config,
        )

        cos_results = parse_cosine_similarity_from_log(log_path)
        success = check_threshold_met(cos_results, DEFAULT_COS_THRESHOLD)

        if success:
            logger.info("")
            logger.info("=" * 60)
            logger.info("SUCCESS at threshold <= %s", threshold)
            logger.info("Nodes upgraded: %d", len(node_config))
            logger.info("=" * 60)

            final_config_path = os.path.join(save_dir, "final_quant_config.json")
            with open(final_config_path, "w") as f:
                json.dump(quant_config, f, indent=2)

            return True, cos_results, quant_config

    # All thresholds exhausted — fallback to previous full-precision phase
    fallback_dir = config.fallback_save_dir or config.baseline_save_dir
    logger.warning(
        "All thresholds exhausted. Falling back to %s result.", fallback_dir
    )

    fallback_config_path = os.path.join(work_dir, fallback_dir, "quant_config.json")
    if os.path.exists(fallback_config_path):
        with open(fallback_config_path, "r") as f:
            fallback_quant_config = json.load(f)
    else:
        fallback_quant_config = build_quant_config(
            all_node_type=config.all_node_type,
            op_config=config.op_config,
            node_config={},
            user_node_config=user_node_config,
            calibration_type=calibration_type,
            per_channel=per_channel,
            asymmetric=asymmetric,
            bias_correction=bias_correction,
            bias_correction_num_sample=bias_correction_num_sample,
            bias_correction_metric=bias_correction_metric,
        )

    fallback_log_path = os.path.join(work_dir, fallback_dir, "hmct.log")
    cos_results = parse_cosine_similarity_from_log(fallback_log_path)

    logger.info("")
    logger.info("=" * 60)
    logger.info("FALLBACK: using %s result (not mixed-precision)", fallback_dir)
    logger.info("=" * 60)

    final_config_path = os.path.join(save_dir, "final_quant_config.json")
    with open(final_config_path, "w") as f:
        json.dump(fallback_quant_config, f, indent=2)

    return True, cos_results, fallback_quant_config


# ============================================================
# Report Generation
# ============================================================


def generate_report(
    results: List[dict],
    work_dir: str,
    onnx_path: str,
    cali_data_dir: str,
    march: str,
    node_config_path: str,
    num_sample: int,
) -> str:
    """Generate tuning report markdown."""
    report_path = os.path.join(work_dir, "tuning_report.md")

    report = f"""# PTQ Precision Tuning Report

## Background & Goals
- **Model**: {onnx_path}
- **Calibration Data**: {cali_data_dir}
- **BPU Architecture**: {march}
- **Metric & Threshold**: Cosine Similarity (>= {DEFAULT_COS_THRESHOLD})
- **User Fixed Config**: {node_config_path or 'None'}
- **Num Sample**: {num_sample}

## Tuning Process & Results

| # | Phase | Configuration | Output Cosine Similarity | Threshold Met |
|---|-------|--------------|--------------------------|---------------|
"""

    for i, result in enumerate(results, 1):
        cos_str = ", ".join(
            f"{k}={v:.6f}" for k, v in result["cos_results"].items()
        )
        status = "YES" if result["success"] else "NO"
        report += (
            f"| {i} | {result['phase_name']} "
            f"| {result['config']} | {cos_str} | {status} |\n"
        )

    # Find final config
    final_config = None
    for result in reversed(results):
        if result["success"] and result.get("quant_config"):
            final_config = result["quant_config"]
            break

    config_json = json.dumps(final_config, indent=2) if final_config else "{}"
    report += f"""
## Final quant_config

```json
{config_json}
```

## Output Directories

"""

    for phase_id, cfg in sorted(PHASE_CONFIGS.items()):
        report += f"- Phase {phase_id} ({Phase.name(phase_id)}): `{cfg.save_dir}`\n"

    report += "\nGenerated by: hmct_precision_tuning.py\n"

    with open(report_path, "w") as f:
        f.write(report)

    return report_path


# ============================================================
# CLI
# ============================================================


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="HMCT PTQ Precision Tuning Automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--onnx_path",
        required=True,
        help="Input ONNX model path",
    )
    parser.add_argument(
        "--cali_data_dir",
        required=True,
        help="Calibration data directory (subdirectory names must match input names)",
    )
    parser.add_argument(
        "--march",
        default="nash-p",
        help="BPU architecture (default: nash-p)",
    )
    parser.add_argument(
        "--work_dir",
        default=None,
        help="Working directory (default: same as onnx file)",
    )
    parser.add_argument(
        "--node_config_path",
        default="",
        help="User-provided node_config JSON file (preserved across phases)",
    )
    parser.add_argument(
        "--num_sample",
        type=int,
        default=1,
        help="Number of bad cases for sensitivity analysis (default: 1)",
    )
    parser.add_argument(
        "--progressive_thresholds",
        type=float,
        nargs="+",
        default=None,
        help="Progressive thresholds (default: [0.99, 0.999, 0.9999, 0.99999])",
    )
    parser.add_argument(
        "--calibration_type",
        type=str,
        nargs="+",
        default=None,
        help=(
            "Activation calibration method(s) for quant_config "
            "(e.g. 'max', 'kl', 'load'). Accepts one or more values; multiple "
            "values trigger HMCT modelwise search. Default: not set (HMCT "
            "default behavior)."
        ),
    )

    def _tri_bool(value: str) -> Optional[bool]:
        v = value.strip().lower()
        if v in ("true", "1", "yes", "on"):
            return True
        if v in ("false", "0", "no", "off"):
            return False
        raise argparse.ArgumentTypeError(
            f"Expected boolean (true/false), got: {value!r}"
        )

    parser.add_argument(
        "--per_channel",
        type=_tri_bool,
        nargs="+",
        default=None,
        help=(
            "Per-channel activation quantization toggle. Writes "
            "`model_config.activation.per_channel`. Accepts one or two boolean "
            "values (e.g. `true`, `false`, or `true false` to search both). "
            "Default: not set (HMCT default = false)."
        ),
    )
    parser.add_argument(
        "--asymmetric",
        type=_tri_bool,
        nargs="+",
        default=None,
        help=(
            "Asymmetric activation quantization toggle. Writes "
            "`model_config.activation.asymmetric`. Accepts one or two boolean "
            "values (e.g. `true`, `false`, or `true false` to search both). "
            "Default: not set (HMCT default = false)."
        ),
    )
    parser.add_argument(
        "--bias_correction",
        type=_tri_bool,
        default=None,
        help=(
            "Enable weight bias correction. Writes "
            "`model_config.weight.bias_correction`. Default: not set "
            "(HMCT default = disabled)."
        ),
    )
    parser.add_argument(
        "--bias_correction_num_sample",
        type=int,
        default=None,
        help=(
            "num_sample for bias_correction (int >= 1). Only applied when "
            "--bias_correction is true. Default: not set (HMCT default = 1)."
        ),
    )
    parser.add_argument(
        "--bias_correction_metric",
        type=str,
        choices=[
            "cosine-similarity",
            "mse",
            "mae",
            "mre",
            "sqnr",
            "chebyshev",
        ],
        default=None,
        help=(
            "metric for bias_correction. Only applied when --bias_correction "
            "is true. Default: not set (HMCT default = cosine-similarity)."
        ),
    )
    return parser.parse_args()


# ============================================================
# Main — Explicit Phase Control Flow
# ============================================================
#
# Workflow (matches SKILL.md):
#
#   Phase 1 (INT8)  ──pass──> DONE
#                    ──fail──v
#   Phase 2 (INT16) ──pass──> Phase 3 (INT8+INT16 mixed) ──> DONE
#                    ──fail──v
#   Phase 4 (dual)  ──pass──> Phase 5 (INT16+dual mixed)  ──> DONE
#                    ──fail──v
#   Phase 6 (FP16)  ──pass──> Phase 7 (dual+FP16 mixed)   ──> DONE
#                    ──fail──> FAILED (contact R&D)


def main() -> int:
    args = parse_args()

    onnx_path = os.path.abspath(args.onnx_path)
    cali_data_dir = os.path.abspath(args.cali_data_dir)
    work_dir = (
        os.path.abspath(args.work_dir) if args.work_dir else os.path.dirname(onnx_path)
    )
    os.makedirs(work_dir, exist_ok=True)

    progressive_thresholds = args.progressive_thresholds or PROGRESSIVE_THRESHOLDS
    user_node_config = load_user_node_config(args.node_config_path)

    # Normalize calibration_type: None => not set; single value => str; multi => list.
    calibration_type: Optional[Union[str, List[str]]] = None
    if args.calibration_type:
        calibration_type = (
            args.calibration_type[0]
            if len(args.calibration_type) == 1
            else list(args.calibration_type)
        )

    def _normalize_bool_list(
        values: Optional[List[bool]], name: str
    ) -> Optional[Union[bool, List[bool]]]:
        """nargs='+' bool list -> single bool when len==1, else deduped list."""
        if values is None:
            return None
        if len(values) == 1:
            return values[0]
        deduped = list(dict.fromkeys(values))
        if len(deduped) > 2:
            raise ValueError(
                f"--{name} accepts at most 2 distinct boolean values, got {values}"
            )
        return deduped

    per_channel = _normalize_bool_list(args.per_channel, "per_channel")
    asymmetric = _normalize_bool_list(args.asymmetric, "asymmetric")

    bias_correction_num_sample = args.bias_correction_num_sample
    if bias_correction_num_sample is not None and bias_correction_num_sample < 1:
        raise ValueError(
            "--bias_correction_num_sample must be >= 1, "
            f"got {bias_correction_num_sample}"
        )
    if (
        bias_correction_num_sample is not None or args.bias_correction_metric is not None
    ) and not args.bias_correction:
        logger.warning(
            "--bias_correction_num_sample / --bias_correction_metric are ignored "
            "because --bias_correction is not set to true."
        )

    logger.info("Starting PTQ Precision Tuning")
    logger.info("ONNX:        %s", onnx_path)
    logger.info("Calibration: %s", cali_data_dir)
    logger.info("Work dir:    %s", work_dir)
    logger.info("March:       %s", args.march)
    logger.info("Threshold:   %s", DEFAULT_COS_THRESHOLD)
    logger.info("Num sample:  %d", args.num_sample)
    logger.info(
        "Calibration type: %s",
        calibration_type if calibration_type is not None else "<HMCT default>",
    )
    logger.info(
        "Activation per_channel: %s",
        per_channel if per_channel is not None else "<HMCT default = false>",
    )
    logger.info(
        "Activation asymmetric: %s",
        asymmetric if asymmetric is not None else "<HMCT default = false>",
    )
    logger.info(
        "Bias correction: %s (num_sample=%s, metric=%s)",
        args.bias_correction if args.bias_correction is not None else "<HMCT default = disabled>",
        bias_correction_num_sample if bias_correction_num_sample is not None else "<HMCT default = 1>",
        args.bias_correction_metric if args.bias_correction_metric is not None else "<HMCT default = cosine-similarity>",
    )

    # Load calibration data once
    cali_data = load_cali_data(onnx_path, cali_data_dir)

    results: List[dict] = []

    # Common kwargs for run_phase
    phase_kw = dict(
        onnx_path=onnx_path,
        cali_data=cali_data,
        user_node_config=user_node_config,
        work_dir=work_dir,
        march=args.march,
        calibration_type=calibration_type,
        per_channel=per_channel,
        asymmetric=asymmetric,
        bias_correction=args.bias_correction,
        bias_correction_num_sample=bias_correction_num_sample,
        bias_correction_metric=args.bias_correction_metric,
    )

    # Common kwargs for run_progressive_fallback
    prog_kw = dict(
        **phase_kw,
        cali_data_dir=cali_data_dir,
        num_sample=args.num_sample,
        progressive_thresholds=progressive_thresholds,
    )

    def _finish(final_success: bool) -> int:
        report_path = generate_report(
            results=results,
            work_dir=work_dir,
            onnx_path=onnx_path,
            cali_data_dir=cali_data_dir,
            march=args.march,
            node_config_path=args.node_config_path,
            num_sample=args.num_sample,
        )
        status = "SUCCESSFUL" if final_success else "FAILED"
        logger.info("")
        logger.info("=" * 60)
        logger.info("TUNING %s", status)
        logger.info("Report saved to: %s", report_path)
        logger.info("=" * 60)
        return 0 if final_success else 1

    # ── Phase 1: INT8 Baseline ──────────────────────────────
    success, cos = run_phase(Phase.INT8_BASELINE, **phase_kw)
    results.append(
        _make_result(Phase.INT8_BASELINE, success, cos, "all_node_type=int8")
    )
    if success:
        return _finish(True)

    # ── Phase 2: Full INT16 Upper Bound ─────────────────────
    success_2, cos_2 = run_phase(Phase.INT16_UPPER, **phase_kw)
    results.append(
        _make_result(Phase.INT16_UPPER, success_2, cos_2, "all_node_type=int16")
    )

    if success_2:
        # ── Phase 3: INT8+INT16 Progressive Mixed ──────────
        success_3, cos_3, qconfig_3 = run_progressive_fallback(
            Phase.INT8_INT16_MIXED, **prog_kw
        )
        results.append(
            _make_result(
                Phase.INT8_INT16_MIXED,
                success_3,
                cos_3,
                "Progressive fallback (int16)",
                qconfig_3,
            )
        )
        return _finish(True)

    # Phase 2 failed → skip Phase 3 → Phase 4

    # ── Phase 4: INT16 + Conv/Gemm/MatMul dual-int16 ───────
    success_4, cos_4 = run_phase(Phase.INT16_DUAL_INT16, **phase_kw)
    results.append(
        _make_result(
            Phase.INT16_DUAL_INT16,
            success_4,
            cos_4,
            "all_node_type=int16, Conv/Gemm/MatMul=dual-int16",
        )
    )

    if success_4:
        # ── Phase 5: INT16+dual-int16 Progressive Mixed ────
        success_5, cos_5, qconfig_5 = run_progressive_fallback(
            Phase.INT16_DUAL_INT16_MIXED, **prog_kw
        )
        results.append(
            _make_result(
                Phase.INT16_DUAL_INT16_MIXED,
                success_5,
                cos_5,
                "Progressive fallback (dual-int16)",
                qconfig_5,
            )
        )
        return _finish(True)

    # Phase 4 failed → skip Phase 5 → Phase 6

    # ── Phase 6: Full FP16 ─────────────────────────────────
    success_6, cos_6 = run_phase(Phase.FP16, **phase_kw)
    results.append(
        _make_result(Phase.FP16, success_6, cos_6, "all_node_type=float16")
    )

    if success_6:
        # ── Phase 7: dual-int16+FP16 Progressive Mixed ────
        success_7, cos_7, qconfig_7 = run_progressive_fallback(
            Phase.INT16_DUAL_INT16_FP16_MIXED, **prog_kw
        )
        results.append(
            _make_result(
                Phase.INT16_DUAL_INT16_FP16_MIXED,
                success_7,
                cos_7,
                "Progressive fallback (float16)",
                qconfig_7,
            )
        )
        return _finish(True)

    # All phases failed
    logger.error(
        "FP16 still not meeting threshold. "
        "Please contact Horizon R&D for assistance."
    )
    return _finish(False)


if __name__ == "__main__":
    sys.exit(main())
