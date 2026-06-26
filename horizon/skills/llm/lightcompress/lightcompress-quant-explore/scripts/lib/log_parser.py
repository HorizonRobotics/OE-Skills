"""
日志解析模块

职责：
- 进度解析
- PPL 指标提取
- 量化层分析
- 错误检测
- 进度报告器
"""

import re
import threading
from collections import defaultdict
from pathlib import Path
from typing import Optional


# 错误模式
ERROR_PATTERNS = [
    r"CUDA out of memory",
    r"torch\.OutOfMemoryError",
    r"ChildFailedError",
    r"Traceback \(most recent call last\)",
    r"Address already in use",
    r"DistNetworkError",
    r"Launch Failed after",
    r"Exception: .* existed before\. Need check\.",
]

# 进度阶段关键词
PROGRESS_PATTERNS = {
    "loading_weights": r"Loading weights:\s+(\d+)%",
    "loading_weights_detail": r"Loading weights:\s+\d+%\|[^|]+\|\s+(\d+)/(\d+)",
    "replace_block": r"Replace block index:\s+(\d+)/(\d+)",
    "replace_layer": r"replace >>>\s+(\S+)\s+in\s+(\d+)-th block",
    "eval_batch": r"index\s+:\s+(\d+)/(\d+)",
    "eval_ppl": r"EVAL: ppl on\s+(\S+)\s+is\s+([0-9.]+)",
    "deploy_stage": r"-- deploy_(\S+)\s+(\S+)\s+--",
    "model_loaded": r"self\.model_config\s*:",
}


class LogParser:
    """日志解析器"""

    def __init__(self, log_file: Path):
        self.log_file = log_file
        self._content: Optional[str] = None

    def _read(self) -> str:
        """读取日志内容"""
        if self._content is None:
            if self.log_file.exists():
                self._content = self.log_file.read_text(encoding="utf-8", errors="ignore")
            else:
                self._content = ""
        return self._content

    def get_lines(self) -> list[str]:
        """获取日志行列表"""
        return self._read().splitlines()

    def tail(self, count: int = 20) -> str:
        """获取日志尾部"""
        lines = self.get_lines()
        return "\n".join(lines[-count:])


class ProgressParser(LogParser):
    """进度解析器"""

    def parse(self) -> dict:
        """解析日志中的进度信息"""
        if not self.log_file.exists():
            return {"stage": "unknown", "progress": 0, "details": ""}

        lines = self.get_lines()
        text = self._read()

        result = {
            "stage": "unknown",
            "progress": 0,
            "details": "",
            "quantized_layers": [],
            "total_blocks": 0,
            "current_block": 0,
        }

        if "Loading weights:" in text:
            for line in reversed(lines):
                match = re.search(r"Loading weights:\s+(\d+)%", line)
                if match:
                    result["stage"] = "loading_weights"
                    result["progress"] = int(match.group(1))
                    detail_match = re.search(r"(\d+)/(\d+)", line)
                    if detail_match:
                        result["details"] = f"权重加载: {detail_match.group(1)}/{detail_match.group(2)}"
                    break

        elif "Replace block index:" in text:
            result["stage"] = "quantizing"
            for line in reversed(lines):
                match = re.search(r"Replace block index:\s+(\d+)/(\d+)", line)
                if match:
                    result["current_block"] = int(match.group(1))
                    result["total_blocks"] = int(match.group(2))
                    if result["total_blocks"] > 0:
                        result["progress"] = int(result["current_block"] * 100 / result["total_blocks"])
                    result["details"] = f"量化层替换: {result['current_block']}/{result['total_blocks']} 层"
                    break

        elif "index :" in text and "eval_func" in text:
            result["stage"] = "evaluating"
            for line in reversed(lines):
                match = re.search(r"index\s+:\s+(\d+)/(\d+)", line)
                if match:
                    current = int(match.group(1))
                    total = int(match.group(2))
                    if total > 0:
                        result["progress"] = int(current * 100 / total)
                    result["details"] = f"评估进度: {current}/{total} batch"
                    break

        elif "EVAL: ppl on" in text:
            result["stage"] = "completed"
            result["progress"] = 100
            for line in reversed(lines):
                match = re.search(r"EVAL: ppl on\s+(\S+)\s+is\s+([0-9.]+)", line)
                if match:
                    result["details"] = f"评估完成: {match.group(1)} PPL = {match.group(2)}"
                    break

        elif "model_config" in text.lower():
            result["stage"] = "initializing"
            result["details"] = "模型初始化中..."

        return result


class PPLParser(LogParser):
    """PPL 指标解析器"""

    def parse(self) -> dict:
        """解析 PPL 指标"""
        dataset_name = None
        values = []
        pattern = re.compile(r"EVAL: ppl on ([^ ]+) is ([0-9.]+)")

        for line in self.get_lines():
            match = pattern.search(line)
            if match:
                dataset_name = dataset_name or match.group(1)
                values.append(float(match.group(2)))

        metrics = {
            "dataset": dataset_name or "unknown",
            "pretrain": None,
            "transformed": None,
            "fake_quant": None,
            "raw_values": values,
        }

        if len(values) >= 3:
            metrics["pretrain"], metrics["transformed"], metrics["fake_quant"] = values[:3]
        elif len(values) == 2:
            metrics["pretrain"], metrics["fake_quant"] = values
        elif len(values) == 1:
            metrics["fake_quant"] = values[0]

        return metrics


class QuantizedLayersParser(LogParser):
    """量化层解析器"""

    def parse(self) -> dict:
        """解析日志中哪些层被量化"""
        if not self.log_file.exists():
            return {"quantized": [], "not_quantized": [], "by_type": {}, "summary": ""}

        lines = self.get_lines()
        text = self._read()

        quantized_layers = set()
        layer_by_type = defaultdict(set)
        total_blocks = 0
        model_type = ""

        for line in lines:
            match = re.search(r"replace >>>\s+(\S+)\s+in\s+(\d+)-th block", line)
            if match:
                layer_name = match.group(1)
                block_idx = int(match.group(2))
                total_blocks = max(total_blocks, block_idx + 1)
                full_name = f"layers.{block_idx}.{layer_name}"
                quantized_layers.add(full_name)

                layer_type = layer_name.split(".")[-1] if "." in layer_name else layer_name
                layer_by_type[layer_type].add(block_idx)

        config_match = re.search(r"model_type.*?\"(\S+)\"", text)
        if config_match:
            model_type = config_match.group(1)

        summary_parts = []
        if layer_by_type:
            for layer_type, blocks in sorted(layer_by_type.items()):
                summary_parts.append(f"{layer_type}: {len(blocks)} 层")

        summary = ", ".join(summary_parts) if summary_parts else "未能解析量化层信息"

        not_quantized = []
        is_moe_model = any(
            kw in text
            for kw in ["Qwen3Moe", "Moe", "moe", "Mixtral", "num_local_experts"]
        )

        if is_moe_model:
            expert_quantized = any(
                "expert" in lt or "gate" in lt
                for lt in layer_by_type.keys()
            )
            if not expert_quantized:
                not_quantized.append("MoE 专家层 (gate_proj, up_proj, down_proj)")

        mlp_layers = ["gate_proj", "up_proj", "down_proj", "mlp.gate"]
        has_mlp_quantized = any(lt in layer_by_type for lt in mlp_layers)

        if not has_mlp_quantized and total_blocks > 0:
            not_quantized.append("MLP 层（保持原始精度）")

        return {
            "quantized": sorted(list(quantized_layers)),
            "not_quantized": not_quantized,
            "by_type": {k: sorted(list(v)) for k, v in layer_by_type.items()},
            "total_blocks": total_blocks,
            "model_type": model_type,
            "summary": summary,
        }


class ErrorDetector(LogParser):
    """错误检测器"""

    def detect(self) -> Optional[str]:
        """检测日志中的错误"""
        text = self._read()
        for pattern in ERROR_PATTERNS:
            match = re.search(pattern, text)
            if match:
                return match.group(0)
        return None


class ProgressReporter:
    """进度报告器，在后台线程中定期报告进度"""

    def __init__(self, log_file: Path, interval_sec: int = 120):
        self.log_file = log_file
        self.interval_sec = interval_sec
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_report = ""

    def start(self) -> None:
        """启动进度报告线程"""
        self._thread = threading.Thread(target=self._report_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """停止进度报告线程"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _report_loop(self) -> None:
        """报告循环"""
        while not self._stop_event.is_set():
            parser = ProgressParser(self.log_file)
            progress = parser.parse()

            import datetime as dt
            now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
            report = (
                f"📊 进度报告 ({now}):\n"
                f"========================================\n"
                f"| 阶段 | 状态 | 进度 | 说明 |\n"
                f"|------|------|------|------|\n"
                f"| {progress['stage']} | 进行中 | {progress['progress']}% | {progress['details']} |\n"
                f"========================================"
            )

            if report != self._last_report:
                print(report, flush=True)
                self._last_report = report

            self._stop_event.wait(self.interval_sec)
