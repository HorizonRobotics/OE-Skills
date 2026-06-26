---
name: j6-plugin-set-march
description: 在适配 horizon_plugin_pytorch 的过程中，为脚本或入口添加 march 设置逻辑。
---

# 为 Horizon 量化/部署流程设置 march（先询问用户版）

## 目标

在接入 `horizon_plugin_pytorch` 的训练、推理、校准、导出或编译流程中，显式设置当前使用的 BPU `march`。

本 Skill 强约束：

- **先询问用户想用哪个 march**：只有在用户明确给出 march 后，才插入对应的 `set_march(...)` 代码。
- **不擅自猜具体 march**：如果用户没有说明，只能提示可选值并请求确认；不能默认写死成 `NASH_E` / `NASH_M` 等。
- **只做 march 设置相关改动**：不顺带改 prepare、qconfig、fake quantize、dynamic block 或其他量化逻辑。
- **优先放在脚本入口或模型构建前**：通常应在模型构建、prepare、train/predict/export 之前调用。

## 理解 `march.py` 的核心用法

### 1) march 枚举值

```python
horizon.march.March.NASH_E
horizon.march.March.NASH_M
horizon.march.March.NASH_P
horizon.march.March.NASH_B
```

### 2) 设置 march

```python
horizon.march.set_march(horizon.march.March.NASH_E)
```

## 标准改法（通用模板）

### 1) 先向用户确认 march

在执行改动前，必须询问：

- 你想使用哪个 march？

推荐给用户的可选项表达：

- `horizon.march.March.NASH_E`
- `horizon.march.March.NASH_P`
- `horizon.march.March.NASH_B`

如果用户没有给出明确 march：

- **不要直接修改代码**。
- 先停在方案说明阶段，等待用户确认具体 march。

### 2) 增加 import

如果文件里还没有 `horizon_plugin_pytorch` 导入，先补：

```python
import horizon_plugin_pytorch as horizon
```

如果文件已经导入 `horizon_plugin_pytorch`，则直接复用，不重复导入。

### 3) 在合适位置插入 `set_march`

通常插入位置优先级：

1. 脚本 `main()` / `if __name__ == "__main__":` 中，且在模型构建前
2. 推理/训练/导出入口函数开头
3. 若工程统一从配置读取，则在读取完 config 后、build model 前

```python
import horizon_plugin_pytorch as horizon


def main():
    horizon.march.set_march(horizon.march.March.NASH_E)
    model = build_model()
    ...
```

## 适用场景

这个 Skill 适合以下需求：

- 适配 `horizon_plugin_pytorch` 时，需要补 march 设置
- 训练/校准/验证/导出脚本里缺少 `horizon.march.set_march(...)`
- 需要把用户指定的 march 显式写进入口逻辑
- 需要统一脚本行为，避免依赖进程中的全局残留 march

## 不适用场景

以下情况不属于本 Skill 的直接处理范围：

- 给模型做 `prepare(...)`
- 调整 fake quantize 状态
- 插入 `QuantStub` / `DeQuantStub`
- 处理动态控制流 / dynamic block
- 根据不同 march 大规模改模型实现细节

如果用户同时提这些需求，应分步处理，march 设置仅负责其中一环。

## 常见插入位置建议

### 训练/推理/导出脚本

典型结构：

```python
def main():
    args = parse_args()
    cfg = Config.fromfile(args.config)
    horizon.march.set_march(horizon.march.March.NASH_E)
    model = build_from_registry(cfg.model)
```

注意：

- `set_march(...)` 一般应在 `build_model()` / `prepare()` / `export()` 之前。
- 如果后续代码依赖 `get_march()` 或 `with_march`，更要提前设置。

### 单元测试/最小复现脚本

典型结构：

```python
import horizon_plugin_pytorch as horizon

horizon.march.set_march(horizon.march.March.NASH_E)
```

用于保证测试环境稳定。

## 注意事项

### 1) 不要重复设置多个互相矛盾的 march

如果文件里已经存在：

```python
horizon.march.set_march(...)
```

先判断是否需要修改已有逻辑，而不是再追加一条新的。

### 2) 不要把 skill 变成“自动选 march”

本 Skill 的要求是：**询问用户想用哪个 march**。

因此 agent 在实际使用该 Skill 时，应该：

- 先向用户确认 march
- 再执行代码改动

而不是擅自从上下文猜一个。

## 快速自检清单

- 已确认用户期望的 march。
- 文件中存在 `import horizon_plugin_pytorch as horizon`。
- 在模型构建/prepare/export 前调用了 `horizon.march.set_march(...)`。
- 没有新增重复或冲突的 `set_march(...)`。
- 如果使用默认值，该默认值是用户明确接受的，而不是 agent 擅自决定的。
