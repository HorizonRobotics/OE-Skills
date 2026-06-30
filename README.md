<p align="center">
  <b>中文</b> | <a href="README.en.md">English</a>
</p>

> 面向 Horizon OpenExplorer（OE）工具链场景的 Agent Skills 集合。围绕 PTQ/QAT 量化、HBDK 编译、UCP 板端推理、性能与精度评估等核心环节，将路径知识、阶段依赖和验证流程模块化，支持 Agent 按流程完成从浮点模型到板端部署的端到端优化。

# 功能介绍

* **工具链路由编排**：`horizon-router` 作为顶层入口，依据 `skill-index.json` 中每个 Skill 的 `description` 字段分流到对应子 Skill

* **端到端部署流程**：覆盖「量化 → 编译 → 板端推理 → 性能/精度评估」完整链路，全链路部署规范优先于单步 Skill 的默认行为

* **环境与板卡检测**：自动探测开发板型号、OE 包版本、本地 Python/CUDA/PyTorch 匹配，按需创建 venv 安装

* **精度调优**：QAT 适配与导出、PTQ 量化构建、混合精度调优、训练-部署一致性 debug、Cosine Similarity

* **性能分析**：Perfetto trace 抓取与分析、`hb_analyzer` 性能瓶颈定位、板端 BPU/DDR/内存资源监控

* **LLM 量化与压缩**：LightCompress 批量量化实验（RTN/GPTQ/AWQ/SmoothQuant）、`llm_compression` 校准/编译/板端评测



# 快速开始

## 安装

### 安装skills

```python
# 直接对你的Agent说
安装这个skill：https://github.com/HorizonRobotics/OE-Skills/blob/main/agent-setup.md
```



### 手动配置mcp

> 前一步默认已安装，建议用户安装完成后确认一下mcp服务是否可用。如下为手动配置mcp的方式：

<table><colgroup><col width="100"><col width="720"></colgroup>
<thead>
<tr>
<th></th>
<th>命令</th>
</tr>
</thead>
<tbody>
<tr>
<td>通用</td>
<td>直接对你的Agent说：帮我配置<strong>如下mcp服务</strong><pre><code class="language-python">"oe-mcp": {
  "type": "http",
  "url": "https://mcp.oe.horizon.auto/mcp"
}
</code></pre></td>
</tr>
<tr>
<td>codex</td>
<td>codex mcp add oe-mcp --url https://mcp.oe.horizon.auto/mcp</td>
</tr>
<tr>
<td>Claude code</td>
<td><code>claude mcp add --transport http oe-mcp https://mcp.oe.horizon.auto/mcp</code></td>
</tr>
<tr>
<td>cursor</td>
<td><code>command+shift+p</code>，打开mcp设置，点击New MCP Server，在json中增加相关配置保存即可：<pre><code class="language-json">{
  "mcpServers": {
    "oe-mcp": {
      "type": "http",
      "url": "https://mcp.oe.horizon.auto/mcp"
    }
  }
}
</code></pre></td>
</tr>
</tbody>
</table>



## 使用

| **任务场景**    | **提示词**                                                                                                        | **调用skill**                      |
| ----------- | -------------------------------------------------------------------------------------------------------------- | -------------------------------- |
| 模型延时实测      | 帮我在开发板`xx.xx.xx.xx`上测试一下`xxx.hbm`的延时                                                                           | j6-ucp-model-perf-eval           |
| 模型延时分析      | 帮我分析一下`xxx.hbm`的延时瓶颈，开发板`xx.xx.xx.xx`                                                                          | hb-analyzer-performance          |
| onnx精度优化    | 帮我对模型`xxx.onnx`做精度调优，校准数据路径为`{calib_data}`，使用`{OE_docker}`                                                     | j6-hmct-cosine-similarity-tuning |
| torch模型精度优化 | 模型校准后验证集 top-1 从浮点的 78% 掉到 55%。请帮我分析和调优，校准和评测代码：`{calib.py}`                                                   | j6-plugin-precision-tuning       |
| 量化配置检查      | 帮我分析 model\_check\_result.txt，看看量化配置哪里有问题                                                                      | j6-plugin-model-check-result     |
| 编写hbm评测代码   | 帮我评测一下`xxx.hbm`的精度，calib评测代码为`val.py`，开发板`xx.xx.xx.xx`。若网络延迟较高，减少评测帧数到100                                      | j6-ucp-hbm-infer                 |
| 编写hbm部署代码   | 我有四个小模型，放在`{model_path}`，这几个模型间没有数据依赖，可同时推理，帮我写一下ucp部署代码，测试使用开发板`xx.xx.xx.xx`                                  | j6-ucp-infer-generating          |
| 单算子测试验证     | 帮我写一个 Conv2d 的量化编译全流程代码，输入是 (1, 3, 32, 32)，march 为 nash-p                                                      | j6-plugin-hbdk-generating        |
| onnx模型部署    | 需综合调用多个skill，具体使用经验请参考文档[onnx模型部署全流程示例](https://horizonrobotics.feishu.cn/wiki/JrvywmYHxioBUKk5sCAcw4qYnFf)    |                                  |
| pytorch模型部署 | 需综合调用多个skill，具体使用经验请参考文档[pytorch模型部署全流程示例](https://horizonrobotics.feishu.cn/wiki/JrvywmYHxioBUKk5sCAcw4qYnFf) |                                  |



# 目录结构

```plain&#x20;text
OE-Skills/
├── README.md                # 本文件
├── agent-setup.md           # Agent 安装指引文档
├── setup.sh                 # 安装脚本，将 horizon/ 资源铺设到目标项目 .horizon/
└── horizon/                 # 资源目录（安装时复制到目标项目）
    ├── HORIZON.md           # 工作区规则和使用说明
    ├── VERSION              # 当前版本号
    ├── skill-index.json     # Skill 索引（模块、路径、描述、触发条件）
    ├── docs/                # Horizon 工具链离线文档
    └── skills/              # 按模块组织的 Skill 集合
        ├── horizon-router/  # 顶层路由 Skill
        ├── hbdk/            # HBDK 编译相关
        ├── plugin/          # Horizon Plugin（QAT 量化）
        ├── hmct/            # HMCT / PTQ 量化
        ├── ucp/             # UCP / 板端推理
        ├── horizon_tc_ui/   # 可视化分析工具
        └── llm/             # LLM 量化与压缩
```



# Skills介绍

### 顶层路由 Skills

`horizon-router` 是工具链入口，处理 PTQ/QAT 量化编译、板端部署、性能精度评估等请求，并路由到对应子 Skill。环境检测类 Skill 在板端任务或工具链操作触发时按需调用。

| Skill                    | 功能           | 触发场景                                   |
| ------------------------ | ------------ | -------------------------------------- |
| horizon-router           | 顶层路由入口       | 任何 Horizon 工具链相关请求的分流                  |
| board-detection          | 板卡硬件平台检测     | 板端运行/推理/压测且`.env.board` 缺失             |
| oe-package-detection     | OE 包环境检测     | 普通 PTQ/QAT 量化编译部署且`.env.oe-package` 缺失 |
| oe-package-install       | OE 包本地安装     | `oe-package-detection` 完成后按需触发         |
| oe-llm-package-detection | OE-LLM 包环境检测 | LightCompress 等依赖 OE-LLM 包的任务          |
| oe-llm-package-install   | OE-LLM 包本地安装 | `oe-llm-package-detection` 完成后按需触发     |

### HBDK 模块（模型编译）

| Skill           | 功能               | 触发场景                                  |
| --------------- | ---------------- | ------------------------------------- |
| j6-hbdk-compile | YAML 配置驱动通用模型编译  | 模型编译、导出 hbm、生成上板产物、pyramid/resizer 输入 |
| hbdk-manual     | HBDK4 编译工具使用指南索引 | 查询编译工具按任务场景的使用方式                      |

### Horizon Plugin 模块（pytorch 量化）

| Skill                        | 功能                     | 触发场景                                       |
| ---------------------------- | ---------------------- | ------------------------------------------ |
| j6-plugin-adaptation         | 浮点 PyTorch 模型 QAT 工具适配 | 为模型适配`horizon_plugin_pytorch`              |
| j6-plugin-export             | QAT 模型导出 HBIR IR       | `hbdk4.export` 导出 QAT 模型                   |
| j6-plugin-hbdk-generating    | 量化到编译全流程代码生成           | 同时覆盖量化和编译多个步骤                              |
| j6-plugin-model-check-result | 量化配置检查结果分析             | 分析`model_check_result.txt`，定位结构/qconfig 问题 |
| j6-plugin-graph-diff         | FX Graph 计算图差异对比       | 定位两份计算图的结构与算子参数差异                          |
| j6-plugin-consistency-debug  | 训练-部署一致性问题定位           | QAT 训练正常但 export/convert/compile/HBM 掉点    |
| j6-plugin-precision-tuning   | PyTorch 侧精度调优          | calibration 后精度不达标、QAT loss 不收敛、混合精度调优     |

### HMCT 模块（onnx 量化）

| Skill                            | 功能           | 触发场景                                   |
| -------------------------------- | ------------ | -------------------------------------- |
| hmct-workflow                    | 模型转换与精度调优总入口 | HMCT、模型转换、模型量化、PTQ、精度调优、节点敏感度          |
| j6-hmct-cosine-similarity-tuning | PTQ 精度调优工作流  | Cosine Similarity 不达标（默认 ≥0.99）、混合精度回退 |

### UCP 模块（板端推理）

| Skill                          | 功能                           | 触发场景                                             |
| ------------------------------ | ---------------------------- | ------------------------------------------------ |
| j6-ucp-infer-generating        | UCP 推理 C++ 代码生成              | UCP/DNN 推理接口用法、API 参数、模型加载、tensor 内存、Cache 同步    |
| j6-ucp-hbm-infer               | hbm\_infer Python 客户端代码生成    | X86 侧 Python 调用 HBM 模型推理、HbmRpcSession/HTensor   |
| j6-ucp-model-perf-eval         | hrt\_model\_exec perf 板端性能评测 | 模型性能测试、benchmark、thread\_num/core\_id 扫描、吞吐/延迟对比 |
| j6-ucp-perfetto-trace-catcher  | Perfetto trace 板端抓取          | 抓取 UCP`.pftrace`、J6 开发板 trace 采集                 |
| j6-ucp-perfetto-trace-analysis | Perfetto trace 性能瓶颈分析        | UCP 推理 trace 诊断、延迟/流水线 stall/BPU 空隙分析            |
| j6-board-monitor               | 板端资源监控与采集                    | BPU 占用率、DDR 带宽、内存使用、LLM 推理期间资源监控                 |

### Horizon TC UI 模块（集成辅助工具）

| Skill                   | 功能                    | 触发场景                                                                             |
| ----------------------- | --------------------- | -------------------------------------------------------------------------------- |
| hb-analyzer-performance | hb\_analyzer 模型性能分析   | 模型文件性能/延时/带宽/BPU 利用率/瓶颈分析                                                        |
| horizon-tc-ui           | OpenExplorer CLI 工具集成 | hb\_compile/hb\_model\_info/hb\_verifier/hb\_analyzer、YAML 配置、PTQ 量化、HBIR/HBM 产物 |

### LLM 模块（量化与压缩）

| Skill                        | 功能                      | 触发场景                                                                                       |
| ---------------------------- | ----------------------- | ------------------------------------------------------------------------------------------ |
| lightcompress-batch-quantize | 批量量化实验与对比表生成            | 多模型/多方法/多配置批量量化实验                                                                          |
| lightcompress-quant-explore  | 单次量化实验与精度报告             | 量化实验、PPL 评估、RTN/GPTQ/AWQ/SmoothQuant                                                       |
| llmcompression-add-model     | llm\_compression 新增模型支持 | 在`llm_compression/models/` 接入新 LLM/VLM 模型                                                  |
| llmcompression-operations    | llm\_compression 日常操作   | 校准(calib)、GPU 精度评测(torch\_eval)、HBM 编译(compile)、板端评测(hbm\_rpc\_eval)、量化分析(quant\_analysis) |

> 全链路部署规范优先：当需求涉及「量化 → 编译 → 部署」完整链路时，`horizon-router/references/deployment-workflow.md` 中的全链路规范是最高权威。若子 Skill 默认行为与全链路规范冲突（如 `calibration_type`、`all_node_type`、`remove_node_type`、部署交付物形式），以全链路规范为准。



# 免责声明

感谢您关注OE Skills 项目，我们希望这些技能和知识能帮助您更好地进行OpenExplorer开发。

在使用之前，请您了解：

* 本目录中的 Agent Skills 内容仅供技术参考和学习使用，不代表其适用于任何生产环境或关键业务系统。

* Agent自动生成的代码及其他产物，其正确性、完整性受模型能力、skill能力、用户提示词等多种因素影响，请开发者务必自己审核产物的安全性、兼容性和正确性。作者及贡献者不对因使用本内容导致的任何直接或间接损失承担责任。

* 本内容可能涉及第三方依赖或接口调用，相关权限及合规性需由开发者自行核实。

* 除非另有明确约定，本目录所有内容均基于开源协议发布，不提供任何形式的技术支持或担保。
