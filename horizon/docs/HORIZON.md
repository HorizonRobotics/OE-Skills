# Horizon Toolchain Mode

## 1. Purpose

本文件约束 Agent 回答 Horizon / OpenExplorer 工具链问题时的工作方式。

核心原则：

- 先做仓库路由，再做检索
  - 优先查看 `oe_docs_3_9_0_rc4/index.md`
  - 使用 `oe-mcp` 结合关键词做语义检索
- 禁止凭记忆臆测命令、参数、流程

---

## 2. When To Enter Toolchain Mode

当问题涉及以下任一主题时，必须进入“工具链模式”：

- 量化、QAT、PTQ、calibration
- 编译、HBIR、HBM、deploy artifact
- 上板、板端推理、远端推理
- 评测、benchmark、精度、时延、吞吐
- 训练适配、导出、转换、版本兼容
- CLI、脚本参数、环境变量、target platform、march
- OpenExplorer / Horizon J6 / UCP 工具链行为

以下模糊问法也默认进入工具链模式：

- `模型怎么用`
- `怎么部署`
- `怎么跑通`
- `这个参数怎么填`
- `这个命令怎么写`
- `为什么编译失败 / 精度下降 / 上板结果不一致`

---

## 3. Hard Rules

- 禁止仅凭通用知识回答 Horizon 工具链问题。
- 禁止跳过检索直接输出 CLI 命令、参数、路径或流程。
- 禁止把通用 PyTorch / ONNX 经验直接当作 Horizon 官方答案。
- CLI 参数、配置项、环境变量、阶段顺序，必须来自已检索证据。
- 未被文档或代码确认的信息，一律视为不可靠。
- 信息不足时，继续检索，不要补全猜测。

可接受证据来源：

- `oe_docs_3_9_0_rc4/index.md`
- `oe-mcp` 检索结果

---

## 4. Required Workflow

### Step 1. 先看 `oe_docs_3_9_0_rc4/index.md`

先用 `oe_docs_3_9_0_rc4/index.md` 判断：

- 该问题属于哪个阶段
- 应优先查哪个 repo
- 是否需要多仓协同
- 更偏 sample repo 还是 core repo

### Step 2. 先路由，再检索

在开始搜索前，至少先明确：

- 第一优先 repo
- 可选第二 repo
- 是否需要顺序搜索多个 repo

禁止绕过 `oe_docs_3_9_0_rc4/index.md` 直接全仓库盲搜。

### Step 3. 使用 `openexplorer MCP`

`openexplorer MCP` 有两个不同接口，必须区分使用：

- 文档检索接口（search_doc）：用于搜索官方文档、教程、流程说明、参数说明、版本说明
- 代码检索接口（search_code）：用于搜索样例代码、脚本、配置、API 实现、错误来源

使用顺序：

1. 先用文档检索接口确认流程、参数、阶段顺序
2. 再用代码检索接口确认样例入口、脚本用法、实现细节

使用原则：

- 先搜 `oe_docs_3_9_0_rc4/index.md` 路由命中的 repo
- 第一优先 repo 证据不足时，才扩展到第二 repo
- 多仓问题按 `index.md` 推荐顺序逐仓检索

### Step 4. 基于证据回答

最终回答必须建立在已检索到的文档或代码证据上。

如果用户问的是命令、参数、流程，回答中应尽量说明：

- 来自哪个 repo
- 属于哪个阶段
- 依据的是文档、样例、脚本还是代码
- 哪些内容已确认
- 哪些内容仍需继续检索

---

## 5. Routing Shortcuts

- `train`、`dataset`、`resume`、`multi-gpu`、`BEV`、`forecasting`
  - 优先 `torch_samples` 或 `train_samples`

- `QAT`、`fake quant`、`observer`、`qconfig`、`QTensor`
  - 优先 `plugin_pytorch`

- `PTQ`、`ONNX`、`Caffe`、`calibration`、`threshold`
  - 优先 `hmct`

- `HBIR`、`HBM`、`compile`、`lowering`、`preprocess injection`
  - 优先 `compiler`

- `march`、`target platform`、`芯片代号`
  - 优先 `march`

- `remote board`、`gRPC`、`session`、`timeout`、`bandwidth`
  - 优先 `hbm_infer`

- `layer mismatch`、`bad case`、`qconfig 检查`、`BPU/CPU placement`
  - 优先 `profiler`

- `single-image validation`、`classification/detection/segmentation eval`
  - 优先 `convert_samples`

- `J6`、`UCP`、`DSP`、`GPU`、`VP`、`camera demo`
  - 优先 `ucp_tutorial`

模糊问题如 `模型怎么用`、`怎么部署`、`怎么跑`，必须先基于 `oe_docs_3_9_0_rc4/index.md` 分流：

- 训练侧还是部署侧
- PyTorch 路径还是 ONNX/Caffe 路径
- compile 阶段还是 runtime 阶段
- sample 用法还是 core 实现

---

## 6. CLI Safety Rules

当用户请求命令、参数、脚本用法时：

- 先确认 repo 和阶段
- 先查文档检索接口
- 再查代码检索接口
- 禁止补全未确认参数

如果只能确认部分参数：

- 只回答已确认部分
- 明确标注未确认部分
- 继续检索，不要猜

---

## 7. Workflow Integrity

默认流程认知：

模型 -> 量化 / 转换 -> 编译 -> 部署产物 -> 上板 / 远端运行 -> 评测 / 分析

要求：

- 不要把运行时问题当作训练问题回答
- 不要把编译问题当作量化问题回答
- 不要把 sample 用法误写成底层实现
- 不要在缺少上游产物信息时直接推断下游行为

---

## 8. Forbidden Behaviors

- 禁止绕过 `oe_docs_3_9_0_rc4/index.md` 直接全仓库搜索
- 禁止未检索就输出 CLI 命令
- 禁止凭印象补命令参数
- 禁止用通用深度学习知识替代 Horizon 工具链知识
- 禁止混淆多个 repo 的职责边界
- 禁止把旧版本经验直接套到当前版本

---

## 9. One-Line Rule

先看 `oe_docs_3_9_0_rc4/index.md` 做仓库路由，再用 `oe-mcp` 的文档检索接口和代码检索接口定向搜索，最后基于已确认文档或代码回答。
