#!/usr/bin/env python3
"""
单元测试 - 验证模块重构后的功能
"""

import sys
from pathlib import Path

# 添加模块路径
sys.path.insert(0, str(Path(__file__).parent))

from lib import (
    GPUSelector,
    GPUInfo,
    LogParser,
    PPLParser,
    QuantizedLayersParser,
    ErrorDetector,
    ProgressParser,
    ProgressReporter,
    ReportGenerator,
    ResultAnalyzer,
    fmt_metric,
    estimate_model_size,
    PretrainCache,
    YAMLConfigGenerator,
)


def test_fmt_metric():
    """测试指标格式化"""
    print("\n[TEST] fmt_metric")
    assert fmt_metric(1.23456) == "1.2346"
    assert fmt_metric(None) == "-"
    assert fmt_metric(0.0) == "0.0000"
    print("  ✅ 通过")


def test_gpu_info():
    """测试 GPUInfo 数据类"""
    print("\n[TEST] GPUInfo")
    gpu = GPUInfo(
        index=0,
        name="RTX 4090",
        memory_used_mib=1000,
        memory_total_mib=24000,
        memory_free_mib=23000,
        utilization_gpu=10,
    )
    assert gpu.memory_free_gb == 23000 / 1024
    assert gpu.memory_total_gb == 24000 / 1024
    assert "GPU 0" in str(gpu)
    assert "RTX 4090" in str(gpu)
    print("  ✅ 通过")


def test_gpu_selector():
    """测试 GPU 选择器"""
    print("\n[TEST] GPUSelector")
    selector = GPUSelector()
    gpus = selector.query()
    assert len(gpus) > 0, "应该检测到至少一张 GPU"

    best = selector.select_best()
    assert best is not None, "应该能选出最佳 GPU"

    print(f"  检测到 {len(gpus)} 张 GPU")
    print(f"  最佳 GPU: {best}")
    print("  ✅ 通过")


def test_log_parser():
    """测试日志解析器"""
    print("\n[TEST] LogParser")

    # 测试 LogParser 基础功能
    test_log = Path("/tmp/test_llmc_log.txt")
    test_log.write_text("""Replace block index: 1/48
Replace block index: 2/48
EVAL: ppl on wikitext2 is 9.5762
EVAL: ppl on wikitext2 is 10.1234
EVAL: ppl on wikitext2 is 14.8210
""")

    parser = LogParser(test_log)
    lines = parser.get_lines()
    assert len(lines) == 5
    tail = parser.tail(3)
    assert "14.8210" in tail
    print("  LogParser: ✅")

    # 测试 PPLParser
    ppl_parser = PPLParser(test_log)
    metrics = ppl_parser.parse()
    assert metrics["dataset"] == "wikitext2"
    assert metrics["pretrain"] == 9.5762
    assert metrics["transformed"] == 10.1234
    assert metrics["fake_quant"] == 14.821  # 注意浮点精度
    print("  PPLParser: ✅")

    # 测试 ProgressParser - 量化阶段
    progress_parser = ProgressParser(test_log)
    progress = progress_parser.parse()
    assert progress["stage"] == "quantizing"
    assert progress["current_block"] == 2
    print("  ProgressParser (quantizing): ✅")

    # 测试 ProgressParser - 完成状态（只有 EVAL 信息）
    eval_log = Path("/tmp/test_eval_log.txt")
    eval_log.write_text("EVAL: ppl on wikitext2 is 14.8210\n")
    progress_parser2 = ProgressParser(eval_log)
    progress2 = progress_parser2.parse()
    assert progress2["stage"] == "completed"
    assert progress2["progress"] == 100
    print("  ProgressParser (completed): ✅")

    # 测试加载阶段的进度
    loading_log = Path("/tmp/test_loading_log.txt")
    loading_log.write_text("Loading weights: 50%\nLoading weights: 100%\n")
    progress_parser3 = ProgressParser(loading_log)
    progress3 = progress_parser3.parse()
    assert progress3["stage"] == "loading_weights"
    assert progress3["progress"] == 100
    print("  ProgressParser (loading): ✅")

    # 测试 ErrorDetector - 正常日志
    error_detector = ErrorDetector(test_log)
    error = error_detector.detect()
    assert error is None, "正常日志不应检测到错误"
    print("  ErrorDetector (normal): ✅")

    # 测试错误检测
    error_log = Path("/tmp/test_error_log.txt")
    error_log.write_text("CUDA out of memory\nSome other text")
    error_detector2 = ErrorDetector(error_log)
    error2 = error_detector2.detect()
    assert error2 is not None
    assert "CUDA out of memory" in error2
    print("  ErrorDetector (error): ✅")

    print("  ✅ 通过")

    # 清理
    test_log.unlink(missing_ok=True)
    eval_log.unlink(missing_ok=True)
    loading_log.unlink(missing_ok=True)
    error_log.unlink(missing_ok=True)


def test_quantized_layers_parser():
    """测试量化层解析"""
    print("\n[TEST] QuantizedLayersParser")

    test_log = Path("/tmp/test_quant_layers.txt")
    test_log.write_text("""
replace >>> q_proj in 0-th block
replace >>> k_proj in 0-th block
replace >>> v_proj in 0-th block
replace >>> o_proj in 0-th block
replace >>> gate_proj in 0-th block
replace >>> up_proj in 0-th block
replace >>> down_proj in 0-th block
replace >>> q_proj in 1-th block
replace >>> gate_proj in 1-th block
""")

    parser = QuantizedLayersParser(test_log)
    result = parser.parse()

    assert len(result["quantized"]) > 0
    assert "q_proj" in result["by_type"]
    assert len(result["by_type"]["q_proj"]) == 2  # block 0 and 1
    assert result["total_blocks"] == 2
    assert "q_proj" in result["summary"]

    print(f"  解析到 {len(result['quantized'])} 个量化层")
    print(f"  层类型: {list(result['by_type'].keys())}")
    print("  ✅ 通过")

    test_log.unlink(missing_ok=True)


def test_result_analyzer():
    """测试结果分析器"""
    print("\n[TEST] ResultAnalyzer")

    entries = [
        {
            "experiment": {"method_name": "gptq"},
            "result": {
                "status": "success",
                "metrics": {
                    "fake_quant": 14.82,
                    "pretrain": 9.58,
                    "transformed": None,
                    "dataset": "wikitext2",
                }
            }
        },
        {
            "experiment": {"method_name": "awq"},
            "result": {
                "status": "success",
                "metrics": {
                    "fake_quant": 15.20,
                    "pretrain": 9.58,
                    "transformed": None,
                    "dataset": "wikitext2",
                }
            }
        },
        {
            "experiment": {"method_name": "rtn"},
            "result": {
                "status": "failed",
                "metrics": {
                    "fake_quant": None,
                    "pretrain": None,
                    "transformed": None,
                    "dataset": "unknown",
                }
            }
        },
    ]

    analyzer = ResultAnalyzer(entries)

    # 测试获取成功的实验
    successful = analyzer.get_successful()
    assert len(successful) == 2

    # 测试获取失败的实验
    failures = analyzer.get_failures()
    assert len(failures) == 1

    # 测试排序
    ranked = analyzer.rank_by_ppl()
    assert ranked[0]["experiment"]["method_name"] == "gptq"  # 14.82 < 15.20

    # 测试最佳结果
    best = analyzer.get_best()
    assert best["experiment"]["method_name"] == "gptq"

    # 测试分析
    lines = analyzer.analyze()
    assert any("gptq" in line for line in lines)
    assert any("最优" in line for line in lines)

    print("  get_successful: ✅")
    print("  get_failures: ✅")
    print("  rank_by_ppl: ✅")
    print("  get_best: ✅")
    print("  analyze: ✅")
    print("  ✅ 通过")


def test_pretrain_cache():
    """测试 pretrain 缓存"""
    print("\n[TEST] PretrainCache")

    cache = PretrainCache()

    # 测试缓存 key 构建
    key = cache.build_cache_key("qwen3moe", "wikitext2", 1024, 32)
    assert key == "qwen3moe|wikitext2|1024|32"

    # 测试 set/get
    cache.set(key, 9.5762, {"dataset": "wikitext2", "seq_len": 1024, "num_samples": 32})
    value = cache.get(key)
    assert value == 9.5762

    # 测试不存在的 key
    assert cache.get("nonexistent|key") is None

    print("  build_cache_key: ✅")
    print("  set/get: ✅")
    print("  ✅ 通过")


def test_estimate_model_size():
    """测试模型大小估算"""
    print("\n[TEST] estimate_model_size")

    # 使用示例模型路径（用户需根据实际情况修改）
    model_path = Path("/path/to/models/Qwen3-30B-A3B")

    if model_path.exists():
        info = estimate_model_size(model_path)
        print(f"  模型大小: {info['size_gb']:.1f} GB")
        print(f"  层数: {info['num_layers']}")
        print(f"  MoE: {info['is_moe']}")
        print(f"  专家数: {info['num_experts']}")
        assert info["size_gb"] > 0
        assert info["is_moe"] == True
        assert info["num_experts"] == 128
    else:
        print("  ⚠️ 模型路径不存在，跳过（请配置实际模型路径）")

    print("  ✅ 通过")


def test_gptq_special_params():
    """测试 GPTQ special 参数正确注入"""
    print("\n[TEST] GPTQ Special Params Injection")

    import yaml
    import tempfile

    generator = YAMLConfigGenerator()
    experiment = {
        "model_name": "test_model",
        "model_type": "Qwen3",
        "model_path": "/tmp/test_model",
        "method_name": "gptq-w4a8",
        "algo": "gptq",
        "w_q": "w4_perchannel",
        "a_q": "a8_dy_pertoken",
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        exp_dir = Path(tmpdir)
        config_path = generator.generate(experiment, exp_dir)

        config = yaml.safe_load(Path(config_path).read_text())

        # 验证 GPTQ special 参数被正确注入
        quant = config.get("quant", {})
        print(f"  quant config: {quant}")

        # 检查 GPTQ 特有参数(位于 quant.special 子节点)
        special = quant.get("special", {})
        assert "actorder" in special, "缺少 actorder 参数"
        assert special["actorder"] == True, f"actorder 应为 True，实际为 {special['actorder']}"

        assert "true_sequential" in special, "缺少 true_sequential 参数"
        assert special["true_sequential"] == False, f"true_sequential 应为 False，实际为 {special['true_sequential']}"

        assert "blocksize" in special, "缺少 blocksize 参数"
        assert special["blocksize"] == -1, f"blocksize 应为 -1，实际为 {special['blocksize']}"

        print("  actorder: ✅")
        print("  true_sequential: ✅")
        print("  blocksize: ✅")
        print("  ✅ 通过")


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("开始运行单元测试")
    print("=" * 60)

    tests = [
        test_fmt_metric,
        test_gpu_info,
        test_gpu_selector,
        test_log_parser,
        test_quantized_layers_parser,
        test_result_analyzer,
        test_pretrain_cache,
        test_estimate_model_size,
        test_gptq_special_params,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  ❌ 失败: {e}")
            failed += 1
        except Exception as e:
            print(f"  ❌ 异常: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
