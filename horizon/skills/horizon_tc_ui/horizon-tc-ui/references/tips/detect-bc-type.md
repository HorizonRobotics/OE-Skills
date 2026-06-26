# BC 模型定点/浮点类型判断

## 适用场景

**触发关键词**：定点、浮点、bc类型、bc模型类型、quantized bc、float bc

**前置条件**：
- 已有 `.bc` 模型文件
- 已安装 `horizon_tc_ui` 工具包（依赖 hbdk4 >= 4.0.22）

**使用时机**：在涉及 export 或 convert BC 阶段的操作时，需要判断已有 `.bc` 文件所处阶段。

## 判断方法

### 核心原理

BC（HBIR）模型在编译流程中分两个阶段产出：

```
ONNX/Caffe → [export] → 浮点 BC (.bc) → [convert] → 定点 BC (.bc) → [compile] → HBM (.hbm)
```

- **浮点 BC**（export 阶段产物）：包含 `qnt.const_fake_quant` 算子，尚未真正量化
- **定点 BC**（convert 阶段产物）：已完成量化，fake quant 节点已被消费

### 代码判断

通过 `HB_HBIRRuntime` 加载 BC 模型，检查 `current_phase` 属性：

```python
from horizon_tc_ui.hb_hbirruntime import HB_HBIRRuntime

sess = HB_HBIRRuntime(model_file="model.bc")
if sess.current_phase == "export":
    print("浮点 BC 模型（export 阶段产物，尚未量化）")
else:
    print("定点 BC 模型（convert 阶段产物，已完成量化）")
```

**判断规则**：
- `current_phase == "export"` → **浮点 BC 模型**
- `current_phase` 不为 `"export"`（值为 `None`） → **定点 BC 模型**

### 内部实现原理

源码位于 `hb_hbirruntime.py:check_current_phase()`：

```python
def check_current_phase(self) -> None:
    for op in self.function.operations:
        if op.type == "qnt.const_fake_quant":
            self.current_phase = "export"
```

逻辑：遍历模型所有算子，若存在 `qnt.const_fake_quant` 类型的算子，说明模型处于 export 阶段（浮点模型，fake quant 节点尚未被消费）；若不存在则为定点模型。

## 编译流程产物对照

| 产物文件名 | 产出阶段 | 模型类型 |
|-----------|---------|---------|
| `{prefix}_ptq_model.bc` | export | 浮点 BC |
| `{prefix}_quantized_model.bc` | convert | 定点 BC |

> 注意：`{prefix}_ptq_model.bc` 仅在 `HORIZON_TC_UI_DEBUG` 调试模式下保留，正常编译流程中不保留该文件。

## 校验清单

- [ ] BC 文件存在且后缀为 `.bc`
- [ ] `HB_HBIRRuntime` 加载成功，无 ValueError
- [ ] `current_phase` 属性值明确（`"export"` 或 `None`）

## 常见偏差与修法

| 偏差 | 修法 |
|-----|------|
| BC 文件损坏或版本不兼容 | 确认 HBDK 版本 >= 4.0.22，重新编译生成 BC |
| 误将 `.onnx` 传入 `HB_HBIRRuntime` | `HB_HBIRRuntime` 仅接受 `.bc` 后缀文件 |

## 相关文档

- **编译主流程**：[task-float-to-hbm.md](../tasks/task-float-to-hbm.md) — export/convert/compile 三阶段说明
- **模型信息查看**：[task-model-inspection.md](../tasks/task-model-inspection.md) — `hb_model_info` 工具使用
- **HBIR 运行时源码**：`horizon_tc_ui/hb_hbirruntime.py` — `HB_HBIRRuntime` 类和 `check_current_phase()` 方法
- **HBIR 操作封装**：`horizon_tc_ui/hbir_handle.py` — `HBIRHandle` 类，使用 `hbdk.target` 模块属性做等价判断
