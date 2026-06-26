# 基础结构量化编译全流程代码模板

以下是 `j6-plugin-quantization` 和 `j6-hbdk-export-compile` 两个子 skill 合并后的完整端到端代码模板。

```python
"""
基础结构量化编译全流程示例
覆盖: set_march → 模型定义(含Quant/DeQuant) → 量化配置 → prepare → 校准 → QAT → export → convert → remove_io_op → statistics → compile
"""
import torch
import torch.nn as nn
from horizon_plugin_pytorch.quantization import QuantStub
from torch.quantization import DeQuantStub
from horizon_plugin_pytorch import set_march
from horizon_plugin_pytorch.quantization import (
    prepare, set_fake_quantize, FakeQuantState,
    QconfigSetter, get_qconfig, qint8, qint16,
)
from horizon_plugin_pytorch.quantization.hbdk4 import export
from horizon_plugin_pytorch.quantization.observer_v2 import HistogramObserver, MinMaxObserver
from horizon_plugin_pytorch.quantization.qconfig_setter import (
    ModuleNameTemplate, ConvDtypeTemplate, MatmulDtypeTemplate,
)
from hbdk4.compiler import convert, compile, statistics, save


# --- 模型定义（替换为用户的模型结构）---
class MyNet(nn.Module):
    def __init__(self, in_channels=3, conv_out_channels=32, num_classes=10):
        super().__init__()
        self.conv = nn.Conv2d(in_channels, conv_out_channels, kernel_size=3, padding=1)
        self.bn = nn.BatchNorm2d(conv_out_channels)
        self.relu = nn.ReLU(inplace=True)
        self.avgpool = nn.AdaptiveAvgPool2d((1, 1))
        self.fc = nn.Linear(conv_out_channels, num_classes)
        # 部署边界: 每个输入/输出独立 stub，不设置 scale
        self.quant = QuantStub()
        self.dequant = DeQuantStub()

    def forward(self, x):
        x = self.quant(x)
        x = self.relu(self.bn(self.conv(x)))
        x = self.avgpool(x)
        x = torch.flatten(x, 1)
        x = self.fc(x)
        x = self.dequant(x)
        return x


def run_quantization_pipeline(march="nash-p"):  # 默认 nash-p，用户未指定时使用
    # ===== j6-plugin-quantization: 量化流程 =====

    # 1. 设置平台
    set_march(march)

    # 2. 创建模型和输入
    model = MyNet()
    example_input = torch.randn(1, 3, 32, 32)
    model.eval()

    # 验证浮点模型推理正常
    with torch.no_grad():
        model(example_input)

    # 3. 配置量化参数
    if march in ("nash-p", "nash-h"):
        global_output_dtype = torch.float16
    else:
        global_output_dtype = qint8

    # 校准阶段使用 HistogramObserver
    qconfig_setter = QconfigSetter(
        get_qconfig(observer=HistogramObserver),
        templates=[
            ModuleNameTemplate({"": global_output_dtype}),
            ConvDtypeTemplate(input_dtype=qint8, weight_dtype=qint8),
            MatmulDtypeTemplate(input_dtypes=[qint8, qint8]),
        ],
    )

    # 4. Prepare
    calib_net = prepare(model, (example_input,), qconfig_setter=qconfig_setter)

    # 5. 校准（CALIBRATION）
    calib_net.eval()
    set_fake_quantize(calib_net, FakeQuantState.CALIBRATION)
    with torch.no_grad():
        calib_net(example_input)

    # 6. QAT 训练（可选）
    # 如果用户选择 calib-only，跳过此步骤，直接用 calib_net 进入导出
    # 如果用户选择 calib+qat，使用 MinMaxObserver 重新 prepare 后训练
    qconfig_setter_qat = QconfigSetter(
        get_qconfig(observer=MinMaxObserver),
        templates=[
            ModuleNameTemplate({"": global_output_dtype}),
            ConvDtypeTemplate(input_dtype=qint8, weight_dtype=qint8),
            MatmulDtypeTemplate(input_dtypes=[qint8, qint8]),
        ],
    )
    qat_net = prepare(model, (example_input,), qconfig_setter=qconfig_setter_qat)
    qat_net.train()
    set_fake_quantize(qat_net, FakeQuantState.QAT)
    # 训练循环（略）

    # 以下用 qat_net 演示（如果仅校准，将 qat_net 替换为 calib_net 即可）

    # ===== j6-hbdk-export-compile: 导出编译流程 =====

    # 7. 导出 QAT BC（切换到 VALIDATION 状态后 export）
    qat_net.eval()
    set_fake_quantize(qat_net, FakeQuantState.VALIDATION)

    # 验证量化模型在 VALIDATION 状态下推理正常
    with torch.no_grad():
        qat_net(example_input)

    qat_bc = export(qat_net, example_input)

    # 8. Convert
    quantized_model = convert(qat_bc, march)
    save(quantized_model, "quantized.bc")

    # 9. Remove IO Op
    func = quantized_model.functions[0]
    func.remove_io_op(op_types=["Dequantize", "Quantize"])
    save(quantized_model, "quantized_remove.bc")

    # 10. Statistics
    stats = statistics(quantized_model)
    if "hbtl" in str(stats).lower():
        print("[WARNING] 存在 CPU 算子，编译可能失败或运行时回退 CPU")

    # 11. Compile
    hbm_name = "model.hbm"
    compile(quantized_model, hbm_name, march, opt=2, jobs=64, progress_bar=True, debug=False)

    print(f"量化编译完成，产物: quantized.bc, quantized_remove.bc, {hbm_name}")


if __name__ == "__main__":
    run_quantization_pipeline()
```
