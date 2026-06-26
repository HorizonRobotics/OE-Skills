"""
配置管理模块

职责：
- YAML 配置文件生成
- pretrain 精度缓存管理
- 大模型参数优化
"""

import datetime as dt
import json
import re
from pathlib import Path
from typing import Optional

# 内置默认数据集路径(用户未通过 --calib-path/--eval-path 指定时使用)
DEFAULT_CALIB_PATH = "/jfs-public/openexplorer_llm/data/data_set/wikitext2_calib"
DEFAULT_EVAL_PATH = "/jfs-public/openexplorer_llm/data/data_set/wikitext2_eval"


def get_skill_dir() -> Path:
    """获取 skill 目录路径"""
    return Path(__file__).parent.parent.parent


class PretrainCache:
    """pretrain 精度缓存管理器"""

    def __init__(self, cache_file: Optional[Path] = None):
        if cache_file is None:
            cache_file = get_skill_dir() / "pretrain_accuracy_cache.yml"
        self.cache_file = cache_file
        self._cache_data = None

    def _load(self) -> dict:
        """加载缓存数据"""
        if self._cache_data is not None:
            return self._cache_data

        if not self.cache_file.exists():
            self._cache_data = {"pretrain_cache": {}, "eval_config_snapshot": {}}
            return self._cache_data

        import yaml
        self._cache_data = yaml.safe_load(
            self.cache_file.read_text(encoding="utf-8")
        ) or {"pretrain_cache": {}, "eval_config_snapshot": {}}

        return self._cache_data

    def _save(self) -> None:
        """保存缓存数据"""
        import yaml
        self.cache_file.write_text(
            yaml.dump(self._cache_data, allow_unicode=True, default_flow_style=False),
            encoding="utf-8"
        )

    def build_cache_key(
        self,
        model_name: str,
        dataset: str = "wikitext2",
        seq_len: int = 2048,
        num_samples: int = 512
    ) -> str:
        """构建缓存 key"""
        return f"{model_name}|{dataset}|{seq_len}|{num_samples}"

    def get(self, cache_key: str) -> Optional[float]:
        """获取缓存的 PPL 值"""
        data = self._load()
        return data.get("pretrain_cache", {}).get(cache_key)

    def set(
        self,
        cache_key: str,
        ppl_value: float,
        eval_config: dict
    ) -> None:
        """设置缓存值"""
        data = self._load()
        data["pretrain_cache"][cache_key] = float(ppl_value)
        data["eval_config_snapshot"][cache_key] = {
            "dataset": eval_config.get("name", "wikitext2"),
            "seq_len": eval_config.get("seq_len", 2048),
            "num_samples": eval_config.get("num_samples", 512),
            "bs": eval_config.get("bs", 1),
            "inference_per_block": eval_config.get("inference_per_block", False),
            "date": dt.datetime.now().strftime("%Y-%m-%d"),
            "source": "实测"
        }
        self._save()

    @staticmethod
    def build_cache_key_from_config(model_name: str, eval_config: dict) -> str:
        """
        从配置字典构建缓存 key（统一方法）

        参数来源统一使用 eval_config：
        - dataset: eval.name
        - seq_len: eval.seq_len
        - num_samples: eval.num_samples
        """
        cache = PretrainCache()
        return cache.build_cache_key(
            model_name=model_name,
            dataset=eval_config.get("name", "wikitext2"),
            seq_len=eval_config.get("seq_len", 2048),
            num_samples=eval_config.get("num_samples", 512)
        )

    def check_and_skip_pretrain(
        self,
        model_name: str,
        eval_config: dict,
        calib_config: dict
    ) -> Optional[float]:
        """检查缓存，如果命中则返回 PPL 值，否则返回 None"""
        # 统一使用 eval_config 中的参数
        cache_key = self.build_cache_key_from_config(model_name, eval_config)
        return self.get(cache_key)


class LargeModelOptimizer:
    """大模型参数优化器"""

    # 大模型阈值配置
    SIZE_THRESHOLD_GB = 20
    MOE_EXPERT_THRESHOLD = 64
    MOE_SIZE_THRESHOLD_GB = 10

    # 大模型优化参数
    LARGE_MODEL_PARAMS = {
        "n_samples": 32,
        "num_samples": 32,
        "seq_len": 1024,
        "inference_per_block": True,
    }

    def __init__(self, model_info: dict):
        self.model_info = model_info

    def should_optimize(self) -> bool:
        """判断是否需要为大模型优化评估参数"""
        if self.model_info["size_gb"] > self.SIZE_THRESHOLD_GB:
            return True
        if self.model_info["is_moe"] and self.model_info.get("num_experts", 0) > self.MOE_EXPERT_THRESHOLD:
            return True
        if self.model_info["is_moe"] and self.model_info["size_gb"] > self.MOE_SIZE_THRESHOLD_GB:
            return True
        return False

    def get_optimized_params(self) -> dict:
        """获取优化后的参数"""
        return self.LARGE_MODEL_PARAMS.copy()

    def optimize_yaml(self, config_path: str) -> tuple[str, list[str]]:
        """
        为大模型优化 YAML 配置参数

        返回:
            (优化后的配置路径, 变更列表)
        """
        config_file = Path(config_path)
        if not config_file.exists():
            return config_path, []

        content = config_file.read_text(encoding="utf-8")
        changes = []

        # 优化 calib.n_samples
        # 注意：用户在 YAML 中显式写的值视为明确意图，一律保留，不强制降级。
        # 大模型下仅打印领域知识提示（calib 越大越慢/越占显存），由用户自行决策。
        n_samples_pattern = r"(calib:\s*\n(?:[ \t]+[^\n]+\n)*[ \t]+n_samples:\s*)(\d+)"

        def replace_n_samples(match):
            original = int(match.group(2))
            target = self.LARGE_MODEL_PARAMS["n_samples"]
            if original > target:
                changes.append(
                    f"[提示] calib.n_samples={original} 保留用户显式值 "
                    f"(大模型默认建议 {target}; calib 越大越慢/越占显存)"
                )
            return match.group(0)

        content = re.sub(n_samples_pattern, replace_n_samples, content)

        # 优化 eval.num_samples（同步修改）
        eval_num_samples_pattern = r"(eval:\s*\n(?:[ \t]+[^\n]+\n)*[ \t]+num_samples:\s*)(\d+)"

        def replace_eval_num_samples(match):
            original = int(match.group(2))
            target = self.LARGE_MODEL_PARAMS["num_samples"]
            if original > target:
                changes.append(
                    f"[提示] eval.num_samples={original} 保留用户显式值 "
                    f"(大模型默认建议 {target})"
                )
            return match.group(0)

        content = re.sub(eval_num_samples_pattern, replace_eval_num_samples, content)

        # 优化 eval.seq_len
        eval_seq_len_pattern = r"(eval:\s*\n(?:[ \t]+[^\n]+\n)*[ \t]+seq_len:\s*)(\d+)"

        def replace_eval_seq_len(match):
            original = int(match.group(2))
            target = self.LARGE_MODEL_PARAMS["seq_len"]
            if original > target:
                changes.append(
                    f"[提示] eval.seq_len={original} 保留用户显式值 "
                    f"(大模型默认建议 {target})"
                )
            return match.group(0)

        content = re.sub(eval_seq_len_pattern, replace_eval_seq_len, content)

        # 启用 inference_per_block: True
        if "inference_per_block:" in content:
            content = re.sub(
                r"inference_per_block:\s*False",
                "inference_per_block: True",
                content
            )
            changes.append("eval.inference_per_block: False -> True")
        else:
            eval_block_pattern = r"(eval:\s*\n(?:[ \t]+[^\n]+\n)+)"

            def add_inference_per_block(match):
                indent = "    "
                return match.group(1) + f"{indent}inference_per_block: True\n"

            content = re.sub(eval_block_pattern, add_inference_per_block, content)
            changes.append("eval.inference_per_block: True (新增)")

        if not changes:
            return config_path, []

        optimized_config = config_file.parent / f"{config_file.stem}_optimized.yml"
        optimized_config.write_text(content, encoding="utf-8")

        return str(optimized_config), changes

    def print_optimization_info(self, changes: list[str]) -> None:
        """打印优化信息"""
        print("\n" + "=" * 60, flush=True)
        print("⚠️  大模型参数优化已启用", flush=True)
        print("=" * 60, flush=True)
        print(f"模型大小: {self.model_info['size_gb']:.1f}GB", flush=True)
        print(f"MoE 模型: {'是' if self.model_info['is_moe'] else '否'}", flush=True)
        if self.model_info.get("num_experts", 0) > 0:
            print(f"专家数量: {self.model_info['num_experts']}", flush=True)
        print("\n📊 已优化的参数:", flush=True)
        for change in changes:
            print(f"  - {change}", flush=True)
        print("=" * 60 + "\n", flush=True)


class CalibSampleOptimizer:
    """校准样本数优化器 - 根据 GPU 显存和模型大小自动调整"""

    # 默认 GPU 显存大小（24GB RTX 4090）
    DEFAULT_GPU_MEMORY_GB = 24

    # 安全边际系数（预留显存比例）
    SAFETY_MARGIN = 0.85  # 使用 85% 的总显存

    # 量化方法内存开销系数（相对于模型大小，用于计算运行时占用）
    # 这些值是经验值，表示模型运行时相对于静态权重的额外内存需求
    METHOD_RUNTIME_OVERHEAD = {
        "smoothquant": 1.3,  # SmoothQuant 运行时约 1.3x 模型大小
        "awq": 1.2,
        "gptq": 1.15,
        "omniquant": 1.4,
        "quarot": 1.3,
        "rtn": 1.1,
    }

    # 样本数档位（根据可用显存自动选择）
    SAMPLE_TIERS = [512, 256, 128, 64, 32]

    @classmethod
    def estimate_calib_memory_gb(
        cls,
        n_samples: int,
        seq_len: int,
        hidden_size: int,
        dtype_bytes: int = 2  # bfloat16
    ) -> float:
        """估算校准激活内存（GB）"""
        # 激活内存 = samples × seq_len × hidden_size × dtype
        bytes_per_sample = seq_len * hidden_size * dtype_bytes
        total_bytes = n_samples * bytes_per_sample
        return total_bytes / (1024 ** 3)

    @classmethod
    def calculate_optimal_samples(
        cls,
        model_size_gb: float,
        gpu_memory_gb: float,
        method: str,
        seq_len: int = 2048,
        hidden_size: int = 4096,
        target_samples: int = 512
    ) -> int:
        """
        计算最优校准样本数

        策略：按档位递减，找到第一个能放下的样本数
        """
        method_lower = method.lower()
        runtime_ratio = cls.METHOD_RUNTIME_OVERHEAD.get(method_lower, 1.2)

        # 模型运行时占用
        model_runtime_gb = model_size_gb * runtime_ratio

        # 可用于校准的显存
        available_for_calib = gpu_memory_gb * cls.SAFETY_MARGIN - model_runtime_gb

        if available_for_calib <= 0:
            # 显存严重不足，返回最小样本数
            return 32

        # 从目标样本数开始，按档位递减
        for samples in cls.SAMPLE_TIERS:
            if samples > target_samples:
                continue
            calib_memory = cls.estimate_calib_memory_gb(samples, seq_len, hidden_size)
            if calib_memory <= available_for_calib:
                return samples

        # 如果最小档位也放不下，返回 32
        return 32

    @classmethod
    def get_gpu_memory_gb(cls) -> float:
        """获取可用 GPU 显存大小"""
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                # 取第一个 GPU 的显存
                memory_mib = int(result.stdout.strip().split("\n")[0])
                return memory_mib / 1024  # MiB -> GB
        except Exception:
            pass
        return cls.DEFAULT_GPU_MEMORY_GB

    @classmethod
    def optimize_yaml(cls, config_path: str, model_info: dict, method: str) -> tuple[str, list[str]]:
        """
        优化校准样本数

        返回:
            (优化后的配置路径, 变更列表)
        """
        config_file = Path(config_path)
        if not config_file.exists():
            return config_path, []

        # 读取配置获取参数
        import yaml
        config = yaml.safe_load(config_file.read_text(encoding="utf-8"))

        calib_config = config.get("calib", {})
        model_config = model_info.get("config", {})

        current_samples = calib_config.get("n_samples", 512)
        seq_len = calib_config.get("seq_len", 2048)
        hidden_size = model_config.get("hidden_size", 4096)
        model_size_gb = model_info.get("size_gb", 10)

        # 获取 GPU 显存
        gpu_memory_gb = cls.get_gpu_memory_gb()

        # 计算最优样本数
        optimal_samples = cls.calculate_optimal_samples(
            model_size_gb=model_size_gb,
            gpu_memory_gb=gpu_memory_gb,
            method=method,
            seq_len=seq_len,
            hidden_size=hidden_size,
            target_samples=current_samples
        )

        if optimal_samples >= current_samples:
            # 无需调整
            return config_path, []

        # 调整样本数
        content = config_file.read_text(encoding="utf-8")

        n_samples_pattern = r"(calib:\s*\n(?:[ \t]+[^\n]+\n)*[ \t]+n_samples:\s*)(\d+)"

        def replace_n_samples(match):
            return f"{match.group(1)}{optimal_samples}"

        content = re.sub(n_samples_pattern, replace_n_samples, content)

        change = f"calib.n_samples: {current_samples} -> {optimal_samples} (GPU显存优化)"

        optimized_config = config_file.parent / f"{config_file.stem}_calib_optimized.yml"
        optimized_config.write_text(content, encoding="utf-8")

        print("\n" + "=" * 60, flush=True)
        print("📊 校准样本数自动优化", flush=True)
        print("=" * 60, flush=True)
        print(f"GPU 显存: {gpu_memory_gb:.1f}GB", flush=True)
        print(f"模型大小: {model_size_gb:.1f}GB", flush=True)
        print(f"量化方法: {method}", flush=True)
        print(f"优化参数: {change}", flush=True)
        print("=" * 60 + "\n", flush=True)

        return str(optimized_config), [change]


class FastModeOptimizer:
    """快速验证模式优化器"""

    # 快速验证模式参数
    FAST_MODE_PARAMS = {
        "n_samples": 1,
        "num_samples": 1,
        "seq_len": 128,
        "inference_per_block": True,
    }

    @classmethod
    def optimize_yaml(cls, config_path: str) -> tuple[str, list[str]]:
        """
        应用快速验证模式参数

        返回:
            (优化后的配置路径, 变更列表)
        """
        config_file = Path(config_path)
        if not config_file.exists():
            return config_path, []

        content = config_file.read_text(encoding="utf-8")
        changes = []

        # 优化 calib.n_samples
        n_samples_pattern = r"(calib:\s*\n(?:[ \t]+[^\n]+\n)*[ \t]+n_samples:\s*)(\d+)"

        def replace_n_samples(match):
            original = int(match.group(2))
            target = cls.FAST_MODE_PARAMS["n_samples"]
            if original != target:
                changes.append(f"calib.n_samples: {original} -> {target}")
                return f"{match.group(1)}{target}"
            return match.group(0)

        content = re.sub(n_samples_pattern, replace_n_samples, content)

        # 优化 eval.num_samples
        eval_num_samples_pattern = r"(eval:\s*\n(?:[ \t]+[^\n]+\n)*[ \t]+num_samples:\s*)(\d+)"

        def replace_eval_num_samples(match):
            original = int(match.group(2))
            target = cls.FAST_MODE_PARAMS["num_samples"]
            if original != target:
                changes.append(f"eval.num_samples: {original} -> {target}")
                return f"{match.group(1)}{target}"
            return match.group(0)

        content = re.sub(eval_num_samples_pattern, replace_eval_num_samples, content)

        # 优化 eval.seq_len
        eval_seq_len_pattern = r"(eval:\s*\n(?:[ \t]+[^\n]+\n)*[ \t]+seq_len:\s*)(\d+)"

        def replace_eval_seq_len(match):
            original = int(match.group(2))
            target = cls.FAST_MODE_PARAMS["seq_len"]
            if original != target:
                changes.append(f"eval.seq_len: {original} -> {target}")
                return f"{match.group(1)}{target}"
            return match.group(0)

        content = re.sub(eval_seq_len_pattern, replace_eval_seq_len, content)

        # 启用 inference_per_block: True
        if "inference_per_block:" in content:
            content = re.sub(
                r"inference_per_block:\s*False",
                "inference_per_block: True",
                content
            )
            changes.append("eval.inference_per_block: False -> True")
        else:
            eval_block_pattern = r"(eval:\s*\n(?:[ \t]+[^\n]+\n)+)"

            def add_inference_per_block(match):
                indent = "    "
                return match.group(1) + f"{indent}inference_per_block: True\n"

            content = re.sub(eval_block_pattern, add_inference_per_block, content)
            changes.append("eval.inference_per_block: True (新增)")

        if not changes:
            return config_path, []

        fast_config = config_file.parent / f"{config_file.stem}_fast.yml"
        fast_config.write_text(content, encoding="utf-8")

        print("\n" + "=" * 60, flush=True)
        print("⚡ 快速验证模式已启用", flush=True)
        print("=" * 60, flush=True)
        print("\n📊 已优化的参数:", flush=True)
        for change in changes:
            print(f"  - {change}", flush=True)
        print("\n⚠️  注意：精度仅供参考，不可用于最终评估", flush=True)
        print("=" * 60 + "\n", flush=True)

        return str(fast_config), changes


class YAMLConfigGenerator:
    """YAML 配置生成器"""

    def __init__(self, skill_dir: Optional[Path] = None):
        self.skill_dir = skill_dir or get_skill_dir()
        self.template_path = self.skill_dir / "base_template.yml"
        self.methods_path = self.skill_dir / "methods_config.yml"

    def generate(
        self,
        experiment: dict,
        experiment_dir: Path
    ) -> str:
        """
        根据 experiment 配置自动生成 YAML 配置文件

        返回生成的配置文件路径
        """
        import yaml

        # 1. 读取模板
        if not self.template_path.exists():
            raise FileNotFoundError(f"模板文件不存在: {self.template_path}")
        template_content = self.template_path.read_text(encoding="utf-8")

        # 2. 从 experiment 中提取参数
        model_type = experiment.get("model_type", "")
        model_path = experiment.get("model_path", "")
        quant_method = experiment.get(
            "algo",
            experiment.get("quant_method", experiment.get("method_name", "RTN"))
        )

        # 规范化量化方法名称
        quant_method_normalized = (
            quant_method.upper()
            if quant_method.lower() in ["rtn", "gptq", "awq"]
            else quant_method
        )

        # 替换占位符
        config_content = template_content.replace("{{model_type}}", model_type)
        config_content = config_content.replace("{{model_path}}", model_path)
        config_content = config_content.replace("{{quant_method}}", quant_method_normalized)

        # 3. 解析基础配置
        base_config = yaml.safe_load(config_content)
        if base_config is None:
            base_config = {}

        # 4. 从 methods_config.yml 获取方法特殊参数
        quant_config = base_config.get("quant", {})
        if self.methods_path.exists():
            methods_data = yaml.safe_load(self.methods_path.read_text(encoding="utf-8"))
            if methods_data:
                # methods_config.yml 中的 key 使用 special_ 前缀
                method_key = f"special_{quant_method.lower()}"
                if quant_method.lower() == "gptq":
                    method_key = "special_gptq_per_channel"
                elif quant_method.lower() in methods_data:
                    method_key = quant_method.lower()

                if method_key in methods_data:
                    method_special = methods_data[method_key]
                    if isinstance(method_special, dict):
                        # 将方法特有参数放到 special 组中
                        special_config = {}
                        for key, value in method_special.items():
                            if key not in ["method", "weight", "act"]:
                                special_config[key] = value
                        if special_config:
                            quant_config["special"] = special_config
                        # weight 和 act 特殊配置合并
                        if "weight" in method_special:
                            quant_config["weight"] = {
                                **quant_config.get("weight", {}),
                                **method_special["weight"]
                            }
                        if "act" in method_special:
                            quant_config["act"] = {
                                **quant_config.get("act", {}),
                                **method_special["act"]
                            }
                        if "method" in method_special:
                            quant_config["method"] = method_special["method"]

        # 应用 experiment 中的量化配置覆盖
        self._apply_quant_overrides(experiment, quant_config)

        # 注入 special 参数覆盖(percdamp/actorder 等)
        special_overrides = experiment.get("special_overrides")
        if special_overrides:
            quant_config.setdefault("special", {})
            quant_config["special"].update(special_overrides)

        # 注入混合精度 mix_bits
        mix_bits = experiment.get("mix_bits")
        if mix_bits:
            quant_config["mix_bits"] = mix_bits

        base_config["quant"] = quant_config

        # 注入 calib / eval / save 覆盖与默认数据集路径
        self._apply_calib_eval_save(experiment, base_config)

        # 5. 检查 pretrain 缓存
        self._check_pretrain_cache(experiment, base_config)

        # 6. 保存配置文件
        return self._save_config(experiment, experiment_dir, base_config)

    def _apply_quant_overrides(self, experiment: dict, quant_config: dict) -> None:
        """应用 experiment 中的量化配置覆盖"""
        if "w_q" not in experiment and "a_q" not in experiment:
            return

        w_q = experiment.get("w_q", "")
        a_q = experiment.get("a_q", "")

        if w_q:
            w_parts = w_q.split("_")
            if len(w_parts) >= 2:
                w_bit = int(w_parts[0].replace("w", ""))
                # granularity 可能是 "per_channel" 或 "per"，需要拼接
                w_granularity = "_".join(w_parts[1:]) if len(w_parts) > 2 else w_parts[1]
                quant_config.setdefault("weight", {})
                quant_config["weight"]["bit"] = w_bit
                quant_config["weight"]["granularity"] = w_granularity.replace(
                    "perchannel", "per_channel"
                ).replace("pergroup", "per_group")
                # group_size 从 granularity 推断
                if "group" in w_granularity or "per_group" in w_granularity:
                    if quant_config["weight"].get("group_size", -1) == -1:
                        quant_config["weight"]["group_size"] = 128

        if a_q:
            a_parts = a_q.split("_")
            if len(a_parts) >= 1:
                a_bit = int(a_parts[0].replace("a", "")) if a_parts[0].startswith("a") else 16
                quant_config.setdefault("act", {})
                quant_config["act"]["bit"] = a_bit
                if len(a_parts) > 1:
                    # granularity 可能是 "per_token"，需要拼接
                    a_granularity = "_".join(a_parts[1:])
                    quant_config["act"]["granularity"] = a_granularity.replace(
                        "pertoken", "per_token"
                    )

    def _apply_calib_eval_save(self, experiment: dict, base_config: dict) -> None:
        """注入 calib / eval / save 覆盖,并兜底默认数据集路径。

        - 用户通过 --calib-* / --eval-* / --save-path 传入的值优先。
        - 未传时,calib/eval 的 path 若仍是占位符或缺失,填入内置默认路径。
        """
        # --- calib ---
        calib = base_config.setdefault("calib", {})
        for k, v in experiment.get("calib_overrides", {}).items():
            calib[k] = v
        if not calib.get("path") or "/path/to/" in str(calib.get("path", "")):
            calib["path"] = DEFAULT_CALIB_PATH

        # --- eval ---
        ev = base_config.get("eval", {})
        # base_template 用单 dict 形式;统一在 dict 上改
        if isinstance(ev, list):
            ev = ev[0] if ev else {}
            base_config["eval"] = ev
        eval_ov = experiment.get("eval_overrides", {})
        if eval_ov.get("path"):
            ev["path"] = eval_ov["path"]
        if not ev.get("path") or "/path/to/" in str(ev.get("path", "")):
            ev["path"] = DEFAULT_EVAL_PATH
        if eval_ov.get("seq_len") is not None:
            ev["seq_len"] = eval_ov["seq_len"]
        if eval_ov.get("inference_per_block"):
            ev["inference_per_block"] = True
        if eval_ov.get("only_fake_quant"):
            ev["eval_pos"] = ["fake_quant"]

        # --- save ---
        save_path = experiment.get("save_path")
        if save_path:
            base_config["save"] = {"save_fake": True, "save_path": save_path}

    def _check_pretrain_cache(self, experiment: dict, base_config: dict) -> None:
        """检查 pretrain 缓存，决定是否跳过 pretrain 评估"""
        cache = PretrainCache()
        eval_config = base_config.get("eval", {})
        model_name = experiment.get("model_name", "")

        # 统一使用 eval_config 中的参数构建缓存 key
        cache_key = PretrainCache.build_cache_key_from_config(model_name, eval_config)

        cached_ppl = cache.get(cache_key)
        if cached_ppl is not None:
            base_config["eval"]["eval_pos"] = ["fake_quant"]
            # 保存缓存的 pretrain PPL 到 experiment 中，供后续结果解析使用
            experiment["_cached_pretrain_ppl"] = cached_ppl
            print(f"[缓存命中] 跳过 pretrain 评估: {cache_key}", flush=True)

    def _save_config(
        self,
        experiment: dict,
        experiment_dir: Path,
        base_config: dict
    ) -> str:
        """保存配置文件"""
        import yaml

        config_dir = experiment_dir / "configs"
        config_dir.mkdir(parents=True, exist_ok=True)

        model_name = experiment.get("model_name", "unknown")
        method_name = experiment.get("method_name", "unknown")
        config_path = config_dir / f"{model_name}__{method_name}.yml"

        yaml_content = yaml.dump(
            base_config,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False
        )

        header = f"""# =============================================================================
# 自动生成的量化配置
# 模型: {model_name}
# 方法: {method_name}
# 生成时间: {dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
# =============================================================================

"""
        config_path.write_text(header + yaml_content, encoding="utf-8")
        print(f"[配置生成] {config_path}", flush=True)

        return str(config_path)


# =============================================================================
# 兼容性函数接口 (保持与原脚本的兼容性)
# =============================================================================

def load_yaml_config(config_path: str) -> dict:
    """加载 YAML 配置文件"""
    import yaml
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def generate_yaml_config(experiment: dict, experiment_dir: Path) -> str:
    """生成 YAML 配置文件 (兼容性接口)"""
    generator = YAMLConfigGenerator()
    return generator.generate(experiment, experiment_dir)


def get_known_accuracy(model_name: str, yaml_config: dict) -> dict:
    """尝试获取已知 pretrain 精度 (兼容性接口)"""
    cache = PretrainCache()
    eval_config = yaml_config.get("eval", {})

    # 统一使用 eval_config 中的参数
    cache_key = PretrainCache.build_cache_key_from_config(model_name, eval_config)

    ppl_value = cache.get(cache_key)
    if ppl_value is not None:
        return {
            "accuracy": {"wikitext2_ppl": ppl_value},
            "aligned": True,
            "params_key": cache_key,
            "source": "cache_file"
        }

    return {"accuracy": None, "aligned": False, "params_key": None}


def update_pretrain_cache(model_name: str, eval_config: dict, ppl_value: float) -> None:
    """更新 pretrain 精度缓存 (兼容性接口)"""
    cache = PretrainCache()
    # 统一使用 eval_config 中的参数
    cache_key = PretrainCache.build_cache_key_from_config(model_name, eval_config)
    cache.set(cache_key, ppl_value, eval_config)
    print(f"[缓存更新] 已保存 pretrain PPL: {model_name} -> {ppl_value:.4f}", flush=True)


def should_optimize_params_for_large_model(model_info: dict) -> bool:
    """判断是否需要为大模型优化评估参数 (兼容性接口)"""
    optimizer = LargeModelOptimizer(model_info)
    return optimizer.should_optimize()


def optimize_yaml_for_large_model(config_path: str, model_info: dict) -> str:
    """为大模型优化 YAML 配置参数 (兼容性接口)"""
    optimizer = LargeModelOptimizer(model_info)
    optimized_path, changes = optimizer.optimize_yaml(config_path)
    if changes:
        optimizer.print_optimization_info(changes)
    return optimized_path


def estimate_model_size(model_path: Path) -> dict:
    """估算模型大小"""
    config_file = model_path / "config.json"
    config = {}

    if config_file.exists():
        config = json.loads(config_file.read_text(encoding="utf-8"))

    total_size = 0
    for f in model_path.iterdir():
        if f.is_file():
            total_size += f.stat().st_size
    size_gb = total_size / (1024 ** 3)

    num_layers = config.get("num_hidden_layers", 0)
    model_type = config.get("model_type", "")
    architectures = config.get("architectures", [])

    # 多模态/嵌套模型(如 Gemma4Moe)的 MoE 字段在 text_config 子配置里,
    # 顶层只有 model_type=gemma4 / arch=Gemma4ForConditionalGeneration,不含 moe 关键词。
    # 合并顶层与 text_config 一起判断。
    text_config = config.get("text_config", {}) if isinstance(config.get("text_config"), dict) else {}
    if not num_layers:
        num_layers = text_config.get("num_hidden_layers", 0)

    is_moe = any(
        kw in model_type.lower() or any(kw in arch.lower() for arch in architectures)
        for kw in ["moe", "mixtral", "qwen3moe", "qwen3_moe", "gemma4moe", "gemma4_moe", "sparse"]
    )

    # enable_moe_block 是 Gemma4Moe 的显式 MoE 开关
    if config.get("enable_moe_block") or text_config.get("enable_moe_block"):
        is_moe = True

    num_experts = 0
    for src in (config, text_config):
        if "num_local_experts" in src:
            is_moe = True
            num_experts = src["num_local_experts"]
            break
        if "num_experts" in src:
            # 含 num_experts 字段即视为 MoE(Gemma4Moe 用此字段而非 num_local_experts)
            num_experts = src["num_experts"]
            if num_experts > 0:
                is_moe = True
            break

    return {
        "size_gb": size_gb,
        "num_layers": num_layers,
        "is_moe": is_moe,
        "num_experts": num_experts,
        "config": config,
    }
