"""
GPU 选择模块

职责：
- 查询 GPU 信息
- 选择最优 GPU
- 显存分析
"""

import csv
import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass
class GPUInfo:
    """GPU 信息数据类"""
    index: int
    name: str
    memory_used_mib: int
    memory_total_mib: int
    memory_free_mib: int
    utilization_gpu: int

    @property
    def memory_free_gb(self) -> float:
        """空闲显存 (GB)"""
        return self.memory_free_mib / 1024

    @property
    def memory_total_gb(self) -> float:
        """总显存 (GB)"""
        return self.memory_total_mib / 1024

    def __str__(self) -> str:
        return (
            f"GPU {self.index}: {self.name} "
            f"(空闲: {self.memory_free_gb:.1f}GB / {self.memory_total_gb:.1f}GB, "
            f"利用率: {self.utilization_gpu}%)"
        )


class GPUSelector:
    """GPU 选择器"""

    def __init__(self, allowed_gpus: Optional[list[int]] = None):
        self.allowed_gpus = allowed_gpus
        self._gpus: Optional[list[GPUInfo]] = None

    def query(self) -> list[GPUInfo]:
        """查询所有 GPU 信息"""
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.used,memory.total,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            capture_output=True,
        )

        if completed.returncode != 0:
            raise RuntimeError(
                f"nvidia-smi 查询失败: {completed.stderr.strip() or completed.stdout.strip()}"
            )

        rows = []
        for row in csv.reader(completed.stdout.splitlines()):
            if not row:
                continue
            idx, name, mem_used, mem_total, util = [item.strip() for item in row]
            rows.append(
                GPUInfo(
                    index=int(idx),
                    name=name,
                    memory_used_mib=int(mem_used),
                    memory_total_mib=int(mem_total),
                    memory_free_mib=int(mem_total) - int(mem_used),
                    utilization_gpu=int(util),
                )
            )

        if not rows:
            raise RuntimeError("未检测到任何 GPU")

        self._gpus = rows
        return rows

    def get_all(self) -> list[GPUInfo]:
        """获取所有 GPU 信息 (带缓存)"""
        if self._gpus is None:
            self._gpus = self.query()
        return self._gpus

    def get_allowed(self) -> list[GPUInfo]:
        """获取允许使用的 GPU"""
        gpus = self.get_all()
        if self.allowed_gpus is None:
            return gpus
        return [gpu for gpu in gpus if gpu.index in self.allowed_gpus]

    def select_best(self) -> GPUInfo:
        """
        选择空闲显存最多的 GPU

        排序优先级:
        1. 空闲显存 (从多到少)
        2. GPU 利用率 (从低到高)
        3. GPU 索引 (从小到大)
        """
        gpus = self.get_allowed()
        if not gpus:
            raise RuntimeError("allowed_gpus 过滤后没有可用 GPU")

        gpus.sort(
            key=lambda gpu: (
                -gpu.memory_free_mib,
                gpu.utilization_gpu,
                gpu.index,
            )
        )
        return gpus[0]

    def print_all(self) -> None:
        """打印所有 GPU 信息"""
        print("\n📊 GPU 信息:", flush=True)
        print("-" * 60, flush=True)
        for gpu in self.get_all():
            prefix = "✅ " if (
                self.allowed_gpus is None or gpu.index in self.allowed_gpus
            ) else "❌ "
            print(f"  {prefix}{gpu}", flush=True)
        print("-" * 60, flush=True)
