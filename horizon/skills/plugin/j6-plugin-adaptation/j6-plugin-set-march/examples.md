# Horizon 设置 march Skill - 使用示例

本示例文档说明什么时候应触发 `j6-plugin-set-march`。

## 触发方式

### 直接触发（明确提及 march / set_march / Horizon 平台）

```text
帮我给这个脚本加 horizon 的 set_march
```

```text
适配 horizon_plugin_pytorch 的时候，把 march 也设置上
```

```text
给 @tools/predict.py 增加 horizon.march.set_march(...)
```

### 间接触发（提及目标芯片/BPU 平台/部署平台）

```text
这个模型要跑在 nash-e，上代码里把平台配置补一下
```

```text
导出 hbir 前需要设置 NASH_E march，帮我改下入口脚本
```

### 隐式触发（提到“按用户选择平台插入代码”）

```text
做一个适配流程：先问用户要哪个 march，再把对应代码加进去
```

---

## Prompt 中需要包含的关键信息

### 必须提供的信息

| 信息 | 说明 | 示例 |
|------|------|------|
| 目标文件/入口函数 | 要修改哪个脚本或模块 | `@tools/train.py` / `main()` |
| march 来源 | 是用户指定固定值，还是走 config | `NASH_E` / `cfg.get("march")` |

### 可选信息

| 信息 | 默认处理 | 说明 |
|------|----------|------|
| 插入位置 | agent 根据入口结构判断 | 通常在 `build_model()` 之前 |
| 是否已有 `horizon` import | agent 会检查并复用 | 已有则不重复加 |

---

## 关键行为：先询问用户，再改代码

当用户只说“加 march”但没有说具体 march 时，agent 不应直接修改代码，而应先明确询问，例如：

```text
你想使用哪个 march？我可以按你的选择插入：
- horizon.march.March.NASH_E
- horizon.march.March.NASH_P
- horizon.march.March.NASH_B
```

只有在用户明确反馈后，才执行插入。

---

## 完整使用流程示例

### 示例 1：用户给出固定 march

**用户 Prompt：**

```text
给 @tools/predict.py 加 set_march，使用 NASH_E。
```

**Agent 执行思路：**

1. 检查文件是否已导入：
   ```python
   import horizon_plugin_pytorch as horizon
   ```
2. 找到脚本入口（通常是 `main()` 或 `if __name__ == "__main__":`）
3. 在模型构建前加入：
   ```python
   horizon.march.set_march(horizon.march.March.NASH_E)
   ```
4. 避免重复插入第二条冲突的 `set_march`

**目标效果：**

```python
import horizon_plugin_pytorch as horizon

def main():
    args = parse_args()
    horizon.march.set_march(horizon.march.March.NASH_E)
    model = build_model()
```

---

### 示例 2：用户没给具体 march，需要先追问

**用户 Prompt：**

```text
帮我在这个 horizon 适配流程里加 march 设置。
```

**正确执行方式：**

agent 先问：

```text
你想使用哪个 march？
可选如：NASH_E / NASH_P / NASH_B，
```

在用户回复前，不应直接写：

```python
horizon.march.set_march(horizon.march.March.NASH_E)
```

因为这属于擅自决定 march。
