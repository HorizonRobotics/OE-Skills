"""
实验执行模块

职责：
- 实验执行核心逻辑
- 进程管理
- 启动器生成
- 临时文件处理
"""

import datetime as dt
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from .config import (
    estimate_model_size,
    generate_yaml_config,
    get_known_accuracy,
    load_yaml_config,
    optimize_yaml_for_large_model,
    should_optimize_params_for_large_model,
    update_pretrain_cache,
    FastModeOptimizer,
)
from .gpu_selector import GPUSelector
from .log_parser import (
    ErrorDetector,
    LogParser,
    PPLParser,
    ProgressReporter,
    QuantizedLayersParser,
)


def die(message: str) -> None:
    """抛出系统退出异常"""
    raise SystemExit(message)


def sanitize_fragment(value: str) -> str:
    """清理文件名片段"""
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("_")
    return text or "_"


def compute_task_name(experiment: dict, current_date: str) -> str:
    """计算任务名称"""
    specification = experiment.get("specification", "_")
    return (
        f"{experiment['algo']}_{experiment['w_q']}_{experiment['a_q']}_"
        f"{specification}_{experiment['model_name']}_{current_date}"
    )


def find_log_and_pid_files(log_dir: Path, task_name: str) -> tuple[Optional[Path], Optional[Path]]:
    """
    查找 run_llmc.sh 生成的日志和 pid 文件。

    run_llmc.sh 的 run_with_retry 函数会额外添加时间戳后缀:
      - 日志文件: {task_name}_{timestamp}.log
      - pid 文件: {task_name}_{timestamp}.pid
    """
    # 先尝试精确匹配
    log_file = log_dir / f"{task_name}.log"
    pid_file = log_dir / f"{task_name}.pid"
    if log_file.exists() and pid_file.exists():
        return log_file, pid_file

    # 用 glob 匹配带时间戳后缀的文件
    log_candidates = sorted(
        log_dir.glob(f"{task_name}_*.log"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    pid_candidates = sorted(
        log_dir.glob(f"{task_name}_*.pid"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )

    for log_cand in log_candidates:
        log_stem = log_cand.stem
        pid_cand = log_dir / f"{log_stem}.pid"
        if pid_cand.exists():
            return log_cand, pid_cand

    if log_candidates:
        log_file = log_candidates[0]
        log_stem = log_file.stem
        pid_file = log_dir / f"{log_stem}.pid"
        if pid_file.exists():
            return log_file, pid_file
        return log_file, None

    if pid_candidates:
        pid_file = pid_candidates[0]
        pid_stem = pid_file.stem
        log_file = log_dir / f"{pid_stem}.log"
        if log_file.exists():
            return log_file, pid_file
        return None, pid_file

    return None, None


def read_pid_file(pid_file: Optional[Path]) -> list[int]:
    """读取 PID 文件"""
    if pid_file is None or not pid_file.exists():
        return []
    pids = []
    for raw in pid_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        raw = raw.strip()
        if raw.isdigit():
            pids.append(int(raw))
    return sorted(set(pids))


def any_pid_alive(pids: list[int]) -> bool:
    """检查是否有 PID 存活"""
    for pid in pids:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            continue
    return False


def build_launcher_env(
    env_activate: Path,
    cuda_devices: str,
    experiment: dict,
    config_path: Optional[str] = None,
    log_dir: Optional[str] = None,
) -> dict:
    """构建运行环境变量

    run_llmc.sh 通过环境变量接收参数：
    - model, algo, w_q, a_q, specification, config
    - 通过 --log_dir 参数指定日志目录
    """
    import os
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = cuda_devices
    env["model"] = experiment["model_name"]
    env["algo"] = experiment["algo"]
    env["w_q"] = experiment["w_q"]
    env["a_q"] = experiment["a_q"]
    env["specification"] = experiment.get("specification", "_")
    env["config"] = config_path or experiment.get("config_path", "")
    env["nnodes"] = str(experiment.get("nnodes", 1))
    env["nproc_per_node"] = str(experiment.get("nproc_per_node", 1))
    # 禁用 run_llmc.sh 的 prepare_job_data_links 函数
    env["JOB_DATA_ROOT"] = "/nonexistent_llmc_job_data"
    return env


def build_launcher_cmd(
    run_script_path: Path,
    log_dir: str,
) -> list[str]:
    """构建 run_llmc.sh 的命令行

    run_llmc.sh 只接受少量命令行参数，主要参数通过环境变量传递
    """
    return [
        "bash", str(run_script_path),
        "--log_dir", log_dir,
    ]


def modify_yaml_save_path(
    config_path: str,
    artifact_dir: Path,
    experiment: dict
) -> str:
    """修改 YAML 配置中的 save_path 指向临时目录，并自动修正 GPTQ blocksize 配置"""
    config_file = Path(config_path)
    if not config_file.exists():
        return config_path

    content = config_file.read_text(encoding="utf-8")

    # 修改 save_path
    save_path_pattern = r"(save:\s*\n\s*save_path:\s*)[^\n]+"
    replacement = rf"\g<1>{str(artifact_dir)}"
    modified_content = re.sub(save_path_pattern, replacement, content)

    # 自动修正 GPTQ blocksize 配置
    if "method: GPTQ" in modified_content or "method: 'GPTQ'" in modified_content or 'method: "GPTQ"' in modified_content:
        if re.search(r"granularity:\s*['\"]?per_channel['\"]?", modified_content):
            blocksize_match = re.search(r"blocksize:\s*(\d+)", modified_content)
            if blocksize_match and blocksize_match.group(1) != "-1":
                old_blocksize = blocksize_match.group(1)
                modified_content = re.sub(r"(blocksize:\s*)\d+", r"\g<1>-1", modified_content)
                print(f"[GPTQ 配置修正] 检测到 per_channel 量化，已将 blocksize 从 {old_blocksize} 修正为 -1", flush=True)

    temp_config = artifact_dir / f"config_{experiment.get('model_name', 'unknown')}.yml"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    temp_config.write_text(modified_content, encoding="utf-8")

    return str(temp_config)


class ProcessManager:
    """进程管理器"""

    def __init__(self, poll_interval_sec: int = 10, launch_timeout_sec: int = 120):
        self.poll_interval_sec = poll_interval_sec
        self.launch_timeout_sec = launch_timeout_sec

    def wait_for_files(self, log_dir: Path, task_name: str) -> tuple[Optional[Path], Optional[Path]]:
        """等待日志和 PID 文件生成"""
        start = time.time()
        while time.time() - start < self.launch_timeout_sec:
            log_file, pid_file = find_log_and_pid_files(log_dir, task_name)
            if log_file is not None or pid_file is not None:
                return log_file, pid_file
            time.sleep(2)
        return None, None

    def wait_for_completion(self, pid_file: Optional[Path]) -> None:
        """等待进程完成"""
        while True:
            pids = read_pid_file(pid_file)
            if not pids or not any_pid_alive(pids):
                break
            time.sleep(self.poll_interval_sec)


class ExperimentRunner:
    """实验执行器"""

    def __init__(self, manifest: dict, current_date: str):
        self.manifest = manifest
        self.current_date = current_date
        self.experiment_dir = Path(manifest["experiment_dir"])
        self.run_script_path = Path(manifest["run_script_path"])
        self.env_activate = Path(manifest["env_activate"])
        self.progress_interval = manifest.get("progress_report_interval_sec", 120)
        self.save_artifacts = manifest.get("save_artifacts", False)
        self.process_manager = ProcessManager(
            poll_interval_sec=manifest.get("poll_interval_sec", 10),
            launch_timeout_sec=manifest.get("launch_timeout_sec", 120),
        )

    def run(self, experiment: dict) -> dict:
        """运行单个实验"""
        experiment_slug = f"{sanitize_fragment(experiment['model_name'])}__{sanitize_fragment(experiment['method_name'])}"
        log_dir = self.experiment_dir / "logs" / experiment_slug
        log_dir.mkdir(parents=True, exist_ok=True)

        # 清理之前失败的日志文件
        self._cleanup_old_logs(log_dir)

        # 检测模型大小
        model_path = Path(experiment["model_path"])
        model_info = estimate_model_size(model_path)

        # 获取或生成配置
        config_path = self._get_or_generate_config(experiment)
        yaml_config = load_yaml_config(config_path)

        # 注意：pretrain 缓存命中不跳过量化实验
        # 已知 pretrain 精度只用于跳过 pretrain 评估阶段（通过 YAML 配置）
        # 量化实验本身仍需执行以获取 fake_quant 精度

        # 选择 GPU
        selector = GPUSelector(self.manifest.get("allowed_gpus"))
        gpu = selector.select_best()
        selector.print_all()
        cuda_devices = str(gpu.index)
        gpu_info = {
            "mode": "single",
            "devices": cuda_devices,
            "gpu_count": 1,
            "gpu": {
                "index": gpu.index,
                "name": gpu.name,
                "memory_used_mib": gpu.memory_used_mib,
                "memory_total_mib": gpu.memory_total_mib,
                "memory_free_mib": gpu.memory_free_mib,
                "utilization_gpu": gpu.utilization_gpu,
            },
        }
        print(f"[GPU 选择] 模型大小 {model_info['size_gb']:.1f}GB, 使用 GPU {gpu.index}", flush=True)

        task_name = compute_task_name(experiment, self.current_date)

        # 快速验证模式（优先级高于大模型优化）
        if experiment.get("fast_mode", False):
            config_path, fast_changes = FastModeOptimizer.optimize_yaml(config_path)
        else:
            fast_changes = []

        # 大模型参数优化
        if should_optimize_params_for_large_model(model_info):
            config_path = optimize_yaml_for_large_model(config_path, model_info)

        # 精简模式：使用临时目录
        artifact_dir = None
        if not self.save_artifacts:
            artifact_dir = Path(tempfile.mkdtemp(prefix=f"llmc_quant_{task_name}_"))
            config_path = modify_yaml_save_path(config_path, artifact_dir, experiment)

        # 构建命令行和环境变量
        launcher_cmd = build_launcher_cmd(self.run_script_path, str(log_dir))
        launcher_env = build_launcher_env(
            self.env_activate, cuda_devices, experiment, config_path, str(log_dir)
        )
        launch_stdout = log_dir / f"{task_name}.launcher.stdout.log"
        launch_stderr = log_dir / f"{task_name}.launcher.stderr.log"
        status = "success"
        reporter = None

        try:
            completed = subprocess.run(
                launcher_cmd,
                cwd=str(log_dir),
                env=launcher_env,
                text=True,
                capture_output=True,
            )

            launch_stdout.write_text(completed.stdout or "", encoding="utf-8")
            launch_stderr.write_text(completed.stderr or "", encoding="utf-8")

            if completed.returncode != 0:
                status = "failed"

            # 等待日志和 PID 文件
            log_file, pid_file = self.process_manager.wait_for_files(log_dir, task_name)

            if log_file is None and pid_file is None:
                return self._create_failed_result(
                    task_name, gpu_info, model_info, log_dir, launch_stdout, launch_stderr,
                    "run_llmc.sh 未生成 pid/log 文件"
                )

            # 启动进度报告器
            reporter = ProgressReporter(log_file, self.progress_interval) if log_file else None
            if reporter:
                reporter.start()

            # 等待进程完成
            self.process_manager.wait_for_completion(pid_file)

        finally:
            if reporter:
                reporter.stop()

        # 清理临时产物
        if artifact_dir and artifact_dir.exists():
            try:
                shutil.rmtree(artifact_dir)
                print(f"[清理] 已删除临时产物: {artifact_dir}", flush=True)
            except Exception as e:
                print(f"[警告] 清理临时产物失败: {e}", flush=True)

        # 解析结果
        return self._parse_and_build_result(
            log_file, task_name, gpu_info, model_info, launch_stdout, launch_stderr, status, experiment
        )

    def _cleanup_old_logs(self, log_dir: Path) -> None:
        """清理之前失败的日志文件"""
        for old_file in log_dir.glob("*"):
            if old_file.is_file() and old_file.suffix in [".log", ".pid"]:
                try:
                    content = old_file.read_text(encoding='utf-8', errors='ignore')
                    has_error = any(
                        pattern in content
                        for pattern in ["Error", "Exception", "Traceback", "OOM", "Failed"]
                    )
                    has_success = "EVAL: ppl on" in content and "fake_quant" in content
                    if has_error or not has_success:
                        old_file.unlink()
                        print(f"[清理] 已删除失败的日志文件: {old_file.name}", flush=True)
                except Exception:
                    try:
                        old_file.unlink()
                    except Exception:
                        pass

    def _get_or_generate_config(self, experiment: dict) -> str:
        """获取或生成配置文件"""
        config_path = experiment.get("config_path", "")
        if not config_path:
            print(f"[自动生成] 实验 {experiment['model_name']} 缺少 config_path，正在生成...", flush=True)
            config_path = generate_yaml_config(experiment, self.experiment_dir)
            experiment["config_path"] = config_path
        return config_path

    def _create_failed_result(
        self,
        task_name: str,
        gpu_info: dict,
        model_info: dict,
        log_dir: Path,
        launch_stdout: Path,
        launch_stderr: Path,
        error: str
    ) -> dict:
        """创建失败结果"""
        return {
            "status": "failed",
            "task_name": task_name,
            "gpu_info": gpu_info,
            "model_info": model_info,
            "log_file": str(log_dir / f"{task_name}.log"),
            "pid_file": str(log_dir / f"{task_name}.pid"),
            "launcher_stdout": str(launch_stdout),
            "launcher_stderr": str(launch_stderr),
            "metrics": {
                "dataset": "unknown",
                "pretrain": None,
                "transformed": None,
                "fake_quant": None,
                "raw_values": []
            },
            "quantized_layers": {"quantized": [], "not_quantized": [], "by_type": {}, "summary": ""},
            "error": error,
            "experiment_dir": str(self.experiment_dir),
        }

    def _print_oom_hints(self, experiment: dict) -> None:
        """CUDA OOM 时打印可操作的降显存建议。"""
        n_samples = experiment.get("calib_overrides", {}).get("n_samples")
        cur = f"(当前 calib.n_samples={n_samples})" if n_samples else ""
        suggested = max(32, n_samples // 2) if n_samples else 64
        print("\n" + "=" * 60, flush=True)
        print("⚠️  检测到 CUDA OOM,可尝试以下措施降低显存:", flush=True)
        print("=" * 60, flush=True)
        print(f"  1. 降低 calib 样本数 {cur}:重跑时 --calib-n-samples {suggested}", flush=True)
        print("  2. 设置环境变量缓解显存碎片(逐 block 量化后段易触发):", flush=True)
        print("     export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True", flush=True)
        print("  3. 确认已启用逐 block 推理评测:--inference-per-block", flush=True)
        print("  4. 经验:26B MoE 单卡 24GB,calib 越大后段 block 显存累积越高,", flush=True)
        print("     大样本(>128)更易在尾部 block OOM;必要时分两步(小 calib 量化 + 单独评测)。", flush=True)
        print("=" * 60 + "\n", flush=True)

    def _parse_and_build_result(
        self,
        log_file: Optional[Path],
        task_name: str,
        gpu_info: dict,
        model_info: dict,
        launch_stdout: Path,
        launch_stderr: Path,
        status: str,
        experiment: dict
    ) -> dict:
        """解析日志并构建结果"""
        if log_file and log_file.exists():
            metrics = PPLParser(log_file).parse()
            quantized_layers = QuantizedLayersParser(log_file).parse()
            error = ErrorDetector(log_file).detect()
            tail = LogParser(log_file).tail(20)
        else:
            metrics = {
                "dataset": "unknown",
                "pretrain": None,
                "transformed": None,
                "fake_quant": None,
                "raw_values": [],
            }
            quantized_layers = {
                "quantized": [],
                "not_quantized": [],
                "by_type": {},
                "summary": "",
            }
            error = None
            tail = ""

        # 如果 pretrain 缓存命中，使用缓存的 pretrain PPL
        if experiment.get("_cached_pretrain_ppl") is not None:
            metrics["pretrain"] = experiment["_cached_pretrain_ppl"]
            print(f"[缓存复用] pretrain PPL: {metrics['pretrain']:.4f}", flush=True)

        if status != "failed" and (error or not metrics["raw_values"]):
            status = "failed"
            error = error or "日志中未提取到 PPL 指标"

        # OOM 友好提示:给出可操作的降显存建议(不自动重试,避免隐式行为)
        if error and ("out of memory" in error.lower() or "oom" in error.lower()):
            self._print_oom_hints(experiment)

        return {
            "status": status,
            "task_name": task_name,
            "gpu_info": gpu_info,
            "model_info": model_info,
            "log_file": str(log_file),
            "pid_file": str(log_file.parent / f"{log_file.stem}.pid") if log_file else None,
            "launcher_stdout": str(launch_stdout),
            "launcher_stderr": str(launch_stderr),
            "metrics": metrics,
            "quantized_layers": quantized_layers,
            "error": error,
            "tail": tail,
            "experiment_dir": str(self.experiment_dir),
        }
