"""
报告生成模块

职责：
- 报告初始化
- 增量更新
- 最终渲染
- 结果分析
"""

import datetime as dt
from collections import defaultdict
from pathlib import Path
from typing import Optional

from .config import should_optimize_params_for_large_model


def fmt_metric(value: Optional[float]) -> str:
    """格式化指标值"""
    return "-" if value is None else f"{value:.4f}"


class ResultAnalyzer:
    """结果分析器"""

    def __init__(self, entries: list[dict]):
        self.entries = entries

    def get_successful(self) -> list[dict]:
        """获取成功的实验"""
        return [
            item for item in self.entries
            if item["result"]["status"] == "success"
            and item["result"]["metrics"]["fake_quant"] is not None
        ]

    def get_failures(self) -> list[dict]:
        """获取失败的实验"""
        return [
            item for item in self.entries
            if item["result"]["status"] != "success"
        ]

    def rank_by_ppl(self) -> list[dict]:
        """按 PPL 排序成功的实验"""
        successful = self.get_successful()
        return sorted(successful, key=lambda item: item["result"]["metrics"]["fake_quant"])

    def get_best(self) -> Optional[dict]:
        """获取最佳结果"""
        ranked = self.rank_by_ppl()
        return ranked[0] if ranked else None

    def analyze(self) -> list[str]:
        """生成分析结论"""
        successful = self.get_successful()
        if not successful:
            return [
                "- 所有方法都未成功产出可解析的 PPL，优先检查日志中的 OOM、端口冲突或配置路径问题。"
            ]

        ranked = self.rank_by_ppl()
        best = ranked[0]
        lines = [
            f"- 最优方法是 `{best['experiment']['method_name']}`，"
            f"fake_quant PPL 为 {best['result']['metrics']['fake_quant']:.4f}。"
        ]

        if best["result"]["metrics"]["pretrain"] is not None:
            delta = best["result"]["metrics"]["fake_quant"] - best["result"]["metrics"]["pretrain"]
            lines.append(f"- 该最优结果相对 pretrain 的 PPL 劣化为 {delta:.4f}，数值越接近 0 越好。")

        if len(ranked) >= 2:
            second = ranked[1]
            gap = second["result"]["metrics"]["fake_quant"] - best["result"]["metrics"]["fake_quant"]
            lines.append(
                f"- 与次优方法 `{second['experiment']['method_name']}` 相比，"
                f"最优方法额外降低了 {gap:.4f} 的 fake_quant PPL。"
            )

        failures = self.get_failures()
        if failures:
            lines.append(f"- 共有 {len(failures)} 个方法执行失败，失败项不会纳入精度排序。")

        return lines


class QuantizedLayersReporter:
    """量化层报告生成器"""

    @staticmethod
    def render(quantized_layers: dict) -> list[str]:
        """生成量化层分析报告"""
        lines = []

        if not quantized_layers.get("by_type"):
            lines.append("- 未能解析量化层信息")
            return lines

        lines.append("#### 已量化层")
        lines.append("")

        for layer_type, blocks in sorted(quantized_layers["by_type"].items()):
            if layer_type in ["q_proj", "k_proj", "v_proj", "o_proj"]:
                lines.append(f"- **Attention 层 `{layer_type}`**: 所有 {len(blocks)} 层均已量化")
            elif "expert" in layer_type or "gate" in layer_type:
                lines.append(f"- **MoE 专家层 `{layer_type}`**: {len(blocks)} 层已量化")
            elif layer_type in ["gate_proj", "up_proj", "down_proj"]:
                lines.append(f"- **MLP 层 `{layer_type}`**: {len(blocks)} 层已量化")
            else:
                lines.append(f"- **其他层 `{layer_type}`**: {len(blocks)} 层已量化")

        if quantized_layers.get("not_quantized"):
            lines.append("")
            lines.append("#### 未量化层")
            lines.append("")
            for layer_desc in quantized_layers["not_quantized"]:
                lines.append(f"- {layer_desc}")

        if quantized_layers.get("summary"):
            lines.append("")
            lines.append(f"**摘要**: {quantized_layers['summary']}")

        return lines


class ReportGenerator:
    """报告生成器"""

    def __init__(self, manifest: dict, report_path: Path, current_date: str):
        self.manifest = manifest
        self.report_path = report_path
        self.current_date = current_date
        self.experiment_dir = Path(manifest.get("experiment_dir", "."))
        self.configs_dir = self.experiment_dir / "configs"
        self.save_artifacts = manifest.get("save_artifacts", False)
        self.experiments = manifest.get("experiments", [])

    def _load_yaml_content(self, experiment: dict) -> Optional[str]:
        """加载 YAML 配置文件内容"""
        config_path = experiment.get("config_path", "")
        if not config_path:
            # 尝试从 configs 目录查找
            exp_slug = f"{experiment['model_name']}__{experiment['method_name']}.yml"
            config_path = self.configs_dir / exp_slug
            if not config_path.exists():
                # 尝试其他命名方式
                candidates = list(self.configs_dir.glob(f"*{experiment['model_name']}*{experiment['method_name']}*.yml"))
                if candidates:
                    config_path = candidates[0]
                else:
                    return None

        try:
            config_file = Path(config_path)
            if config_file.exists():
                return config_file.read_text(encoding="utf-8")
        except Exception:
            pass
        return None

    def init(self) -> None:
        """初始化报告骨架"""
        lines = [
            "# LightCompress 量化探索实验报告",
            "",
            "## 基本信息",
            "",
            "| 项目 | 值 |",
            "|------|----|",
            f"| 实验目录 | `{self.experiment_dir}` |",
            f"| workspace_root | `{self.manifest['workspace_root']}` |",
            f"| 实验日期 | {self.current_date} |",
            f"| 计划实验数 | {len(self.experiments)} |",
            f"| 已完成 | 0 |",
            f"| 保存产物 | {'是' if self.save_artifacts else '否 (精简模式)'} |",
            "",
            "## 实验矩阵",
            "",
            "| 模型 | 方法 | 算法 | 状态 | fake_quant PPL |",
            "|------|------|------|------|----------------|",
        ]

        for exp in self.experiments:
            lines.append(f"| {exp['model_name']} | {exp['method_name']} | {exp['algo']} | ⏳ 待运行 | - |")

        lines.extend([
            "",
            "## 实验结果详情",
            "",
            "*结果将在实验完成后逐步更新...*",
            "",
        ])

        self.report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def update(self, collected_results: list[dict], completed_count: int, total_count: int) -> None:
        """增量更新报告"""
        lines = [
            "# LightCompress 量化探索实验报告",
            "",
            "## 基本信息",
            "",
            "| 项目 | 值 |",
            "|------|----|",
            f"| 实验目录 | `{self.experiment_dir}` |",
            f"| workspace_root | `{self.manifest['workspace_root']}` |",
            f"| 实验日期 | {self.current_date} |",
            f"| 计划实验数 | {total_count} |",
            f"| 已完成 | {completed_count} |",
            f"| 保存产物 | {'是' if self.save_artifacts else '否 (精简模式)'} |",
            "",
            "## 实验矩阵",
            "",
            "| 模型 | 方法 | 算法 | 状态 | fake_quant PPL |",
            "|------|------|------|------|----------------|",
        ]

        # 构建已完成的实验状态映射
        completed_map = {}
        for item in collected_results:
            exp = item["experiment"]
            key = f"{exp['model_name']}|{exp['method_name']}"
            completed_map[key] = item

        # 更新实验矩阵
        for exp in self.experiments:
            key = f"{exp['model_name']}|{exp['method_name']}"
            if key in completed_map:
                item = completed_map[key]
                res = item["result"]
                metrics = res.get("metrics", {})
                if res["status"] == "success":
                    status = "✅ 成功"
                    ppl = f"{metrics['fake_quant']:.4f}" if metrics.get('fake_quant') is not None else "N/A"
                else:
                    status = "❌ 失败"
                    ppl = "-"
                lines.append(f"| {exp['model_name']} | {exp['method_name']} | {exp['algo']} | {status} | {ppl} |")
            else:
                lines.append(f"| {exp['model_name']} | {exp['method_name']} | {exp['algo']} | ⏳ 待运行 | - |")

        lines.extend([
            "",
            "## 实验结果详情",
            "",
        ])

        # 添加每个已完成实验的详细结果
        for item in collected_results:
            lines.extend(self._render_experiment_detail(item))

        lines.extend([
            f"*最后更新: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
        ])

        self.report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def render_final(self, collected_results: list[dict]) -> None:
        """渲染最终完整报告"""
        grouped = defaultdict(list)
        for item in collected_results:
            grouped[item["experiment"]["model_name"]].append(item)

        lines = [
            "# LightCompress 量化探索实验报告",
            "",
            "## 基本信息",
            "",
            "| 项目 | 值 |",
            "|------|----|",
            f"| 实验目录 | `{self.experiment_dir}` |",
            f"| workspace_root | `{self.manifest['workspace_root']}` |",
            f"| 实验日期 | {self.current_date} |",
            f"| 实验数 | {len(collected_results)} |",
            f"| 保存产物 | {'是' if self.save_artifacts else '否 (精简模式)'} |",
            "",
            "## 实验矩阵",
            "",
            "| 模型 | 方法 | 算法 | GPU 模式 | 参数优化 |",
            "|------|------|------|----------|----------|",
        ]

        for item in collected_results:
            lines.extend(self._render_matrix_row(item))

        for model_name, entries in grouped.items():
            lines.extend(self._render_model_section(model_name, entries))

        # 失败项
        failed_entries = [item for item in collected_results if item["result"]["status"] != "success"]
        if failed_entries:
            lines.extend(self._render_failures_section(failed_entries))

        # 结论
        lines.extend(self._render_conclusion(grouped, collected_results))

        self.report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _render_experiment_detail(self, item: dict) -> list[str]:
        """渲染单个实验详情"""
        exp = item["experiment"]
        res = item["result"]
        metrics = res.get("metrics", {})

        lines = [
            f"### {exp['model_name']} - {exp['method_name']}",
            "",
        ]

        # 加载并嵌入 YAML 配置
        yaml_content = self._load_yaml_content(exp)
        if yaml_content:
            lines.extend([
                "**YAML 配置**:",
                "",
                "```yaml",
                yaml_content.strip(),
                "```",
                "",
            ])

        if res["status"] == "success":
            lines.extend([
                "**实验结果**:",
                "",
                f"- **数据集**: {metrics.get('dataset', 'N/A')}",
                f"- **pretrain PPL**: {fmt_metric(metrics.get('pretrain'))}",
                f"- **transformed PPL**: {fmt_metric(metrics.get('transformed'))}",
                f"- **fake_quant PPL**: {fmt_metric(metrics.get('fake_quant'))}",
                "",
            ])

            quant_layers = res.get("quantized_layers", {})
            if quant_layers.get("summary"):
                lines.extend([
                    "**量化层分析**:",
                    f"- {quant_layers['summary']}",
                    "",
                ])

            gpu_info = res.get("gpu_info", {})
            if gpu_info.get("mode") == "skipped":
                lines.append(f"- **GPU**: - (精度复用)")
            elif gpu_info.get("gpu"):
                gpu = gpu_info["gpu"]
                lines.append(f"- **GPU**: {gpu.get('index', '?')} ({gpu.get('name', 'unknown')})")
        else:
            lines.extend([
                f"- **状态**: ❌ 失败",
                f"- **原因**: {res.get('error', 'unknown')}",
                "",
            ])
            if res.get("tail"):
                tail_lines_list = res["tail"].split("\n")[-10:]
                lines.extend([
                    "**日志尾部**:",
                    "```",
                    *tail_lines_list,
                    "```",
                    "",
                ])

        lines.append("---")
        lines.append("")
        return lines

    def _render_matrix_row(self, item: dict) -> list[str]:
        """渲染矩阵行"""
        exp = item["experiment"]
        gpu_info = item["result"].get("gpu_info", {})
        if gpu_info.get("mode") == "skipped":
            gpu_str = "- (复用)"
        elif gpu_info.get("gpu"):
            gpu_str = f"GPU {gpu_info['gpu'].get('index', '?')}"
        else:
            gpu_str = "unknown"
        model_info = item["result"].get("model_info", {})
        param_opt = "是" if should_optimize_params_for_large_model(model_info) else "否"
        return [f"| {exp['model_name']} | {exp['method_name']} | {exp['algo']} | {gpu_str} | {param_opt} |"]

    def _render_model_section(self, model_name: str, entries: list[dict]) -> list[str]:
        """渲染模型章节"""
        first_exp = entries[0]["experiment"]
        first_result = entries[0]["result"]
        model_info = first_result.get("model_info", {})

        lines = [
            "",
            f"## 模型 `{model_name}`",
            "",
            f"- 模型类型: `{first_exp['model_type']}`",
            f"- 模型路径: `{first_exp['model_path']}`",
            f"- 模型大小: {model_info.get('size_gb', 0):.1f} GB",
            f"- 层数: {model_info.get('num_layers', 'unknown')}",
            f"- MoE 模型: {'是' if model_info.get('is_moe', False) else '否'}",
            "",
            "### 精度结果",
            "",
            "| 方法 | 算法 | GPU | 数据集 | pretrain PPL | transformed PPL | fake_quant PPL | 来源 | 状态 |",
            "|------|------|-----|--------|--------------|-----------------|----------------|------|------|",
        ]

        for item in entries:
            lines.extend(self._render_result_row(item))

        lines.extend([
            "",
            "### 精度分析",
            "",
        ])

        analyzer = ResultAnalyzer(entries)
        lines.extend(analyzer.analyze())

        successful = [item for item in entries if item["result"]["status"] == "success"]
        if successful:
            lines.extend([
                "",
                "### 量化层分析",
                "",
            ])
            quantized_layers = successful[0]["result"].get("quantized_layers", {})
            lines.extend(QuantizedLayersReporter.render(quantized_layers))

        # 嵌入每个实验的 YAML 配置
        for item in entries:
            exp = item["experiment"]
            yaml_content = self._load_yaml_content(exp)
            if yaml_content:
                lines.extend([
                    "",
                    f"#### {exp['method_name']} 配置",
                    "",
                    "```yaml",
                    yaml_content.strip(),
                    "```",
                ])

        return lines

    def _render_result_row(self, item: dict) -> list[str]:
        """渲染结果行"""
        exp = item["experiment"]
        res = item["result"]
        gpu_info = res.get("gpu_info", {})
        metrics = res["metrics"]
        status_text = "成功" if res["status"] == "success" else f"失败: {res.get('error') or '-'}"

        accuracy_source = res.get("accuracy_source", {})
        if accuracy_source.get("type") == "known":
            source_text = f"📋 复用 ({accuracy_source.get('params_key', '')})"
        else:
            source_text = "✅ 实测"

        if gpu_info.get("mode") == "skipped":
            gpu_text = "- (复用)"
        else:
            gpu = gpu_info.get("gpu", {})
            gpu_text = f"GPU {gpu.get('index', '?')}" if gpu else "-"

        return [
            f"| {exp['method_name']} | {exp['algo']} | {gpu_text} | {metrics['dataset']} | "
            f"{fmt_metric(metrics['pretrain'])} | {fmt_metric(metrics['transformed'])} | "
            f"{fmt_metric(metrics['fake_quant'])} | {source_text} | {status_text} |"
        ]

    def _render_failures_section(self, failed_entries: list[dict]) -> list[str]:
        """渲染失败项章节"""
        lines = [
            "",
            "## 失败项",
            "",
            "| 模型 | 方法 | 原因 | 日志尾部 |",
            "|------|------|------|----------|",
        ]
        for item in failed_entries:
            exp = item["experiment"]
            res = item["result"]
            tail = (res.get("tail") or "").replace("\n", "<br>")
            lines.append(f"| {exp['model_name']} | {exp['method_name']} | {res.get('error') or '-'} | {tail} |")
        return lines

    def _render_conclusion(self, grouped: dict, collected_results: list[dict]) -> list[str]:
        """渲染结论"""
        lines = [
            "",
            "## 结论",
            "",
        ]

        success_count = len([
            item for item in collected_results
            if item["result"]["status"] == "success"
        ])

        if success_count == 0:
            lines.append("- 本次实验没有成功产出可用的量化精度结果，建议先修复配置或资源问题后重跑。")
        else:
            lines.append(f"- 本次共成功完成 {success_count}/{len(collected_results)} 个实验项。")
            for model_name, entries in grouped.items():
                successful = [
                    item for item in entries
                    if item["result"]["status"] == "success"
                    and item["result"]["metrics"]["fake_quant"] is not None
                ]
                if not successful:
                    continue
                best = min(successful, key=lambda item: item["result"]["metrics"]["fake_quant"])

                quant_layers = best["result"].get("quantized_layers", {})
                quant_summary = quant_layers.get("summary", "")

                lines.append(
                    f"- 模型 `{model_name}` 的推荐方法是 `{best['experiment']['method_name']}`，"
                    f"其 fake_quant PPL 最低，为 {best['result']['metrics']['fake_quant']:.4f}。"
                )
                if quant_summary:
                    lines.append(f"  - 量化层: {quant_summary}")

        return lines
