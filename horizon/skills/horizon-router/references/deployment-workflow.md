# 量化部署全流程与全链路部署规范

> 本文档从 horizon-router SKILL.md 拆出，按需加载。当用户需求涉及量化、编译、部署完整链路时阅读本文件。
>
> **⛔ 优先级声明**：本文档是全链路部署任务的**最高权威**。当子 Skill 的默认行为与本文档冲突时，以本文档为准。子 Skill 服务于单步操作，本文档服务于端到端目标。

## PTQ 链路

用户输入为 **ONNX 模型 + 校准数据**时走此链路。

```
浮点模型校验 → 校准数据准备 → 量化（含精度调优） → 编译 → [数学等价性能优化] → HBM 精度验证 → UCP 部署代码生成
```

## QAT 链路

用户输入为 **PyTorch 模型代码**（`.pt` / `.pth` + 模型定义）时走此链路。

- "量化适配"在 Horizon 工具链中特指 QAT 适配（horizon_plugin_pytorch），不等同于 PTQ
- 唯一例外：用户给了 PyTorch 代码但**明确说"导出 ONNX 再量化"**，此时走 PTQ 路径
- **QAT → PTQ 降级阻断检查**：当用户提供了 PyTorch 代码但 Agent 考虑走 PTQ 路径时，**必须**先完成以下检查并输出结果，否则禁止降级：

  ```
  QAT→PTQ 降级检查（全部必须验证后才能降级）：
  □ 1. 用户是否明确要求"导出 ONNX 再量化"？ → [是/否]
  □ 2. GPU 是否可用（torch.cuda.is_available()）？ → [是/否]
       - 如果不可用：是否已尝试 GPU docker 容器方案？ → [是/否/N/A]
  □ 3. 是否已尝试 QAT 适配（j6-plugin-adaptation）？ → [是/否]
       - 如果未尝试：理由是什么？ → [填写]
  □ 4. 是否存在已有的 .bc 文件证明 QAT 已完成？ → [是/否]
  ```

  **只有当以下条件之一满足时才允许降级为 PTQ**：
  - 问题 1 回答"是"（用户明确指示"导出 ONNX 再量化"）
  - 或者：问题 2 已尝试 GPU docker 且仍不可用 + 问题 3 已尝试 QAT 且失败 + 向用户报告并得到确认

```
浮点模型校验 → QAT 适配 → 导出 HBIR/BC → 编译 → [数学等价性能优化] → HBM 精度验证 → UCP 部署代码生成
```

## 全链路部署规范

当用户需求覆盖「量化 → 编译 → 部署」完整链路时，以下规则**必须逐条执行**，不可跳过：

### 1. "部署"必须生成 UCP 推理代码
- `hbm_perf` / `hbm_infer` 仅用于**性能验证**和**精度对比**，不等同于部署
- 部署的交付物是 `j6-ucp-infer-generating` 生成的 C++ 推理代码（或 `j6-ucp-hbm-infer` 的 Python SDK 代码）
- 必须在开发板上通过 UCP 代码运行推理，验证输出与浮点模型一致
- **⛔ 禁止将 `hbm_infer` / `hbrt4-run-model` / 自定义 shell 脚本作为"部署完成"的标志**——这些仅可作为部署前的快速验证手段，最终交付物必须是 UCP 推理代码

**UCP 部署闭环验证检查表（必须全部完成才算"部署完成"）**：

```
□ 1. UCP 推理代码已生成（C++ 或 Python SDK）
□ 2. 推理代码已在开发板上编译成功（C++ 交叉编译 + scp 上传）
□ 3. 推理代码已在开发板上运行，并输出了推理结果
□ 4. 推理结果与浮点模型输出对比，精度在可接受范围内
□ 5. 板端推理延时已实测并记录
```

**⛔ 以下情况不算"部署完成"**：
- 仅生成了代码但未在板端编译运行
- 仅用 `hrt_model_exec perf` 测试了性能但未运行推理验证输出正确性
- 仅用 `hbm_infer` Python SDK 做了精度对比但未生成 UCP 推理代码
- Agent 自己声称代码正确但未经板端实测

### 2. PTQ 校准方法和量化精度默认值
- `calibration_type` 必须设为 `"histogram"`（直方图），不要用 `"max"`
- `"max"` 仅用于快速验证，生产部署必须用 `"histogram"`
- 量化配置中 `all_node_type` 的选取需根据用户要求和目标平台：
  - **nash-p / nash-h**：用户未指定时默认 `float16`，conv 类单独设 `int8`
  - **nash-e / nash-m / nash-b**：用户未指定时默认 `int8`
- **⛔ 禁止在用户未要求的情况下使用 `all_node_type: int8` 对 nash-p/nash-h 平台做全局 INT8 量化**——这会浪费 nash-p 的 fp16 能力

### 3. 编译配置：删除反量化节点
- `remove_node_type` 必须同时包含 `["Quantize", "Dequantize"]`，仅删 Quantize 会遗留 Dequantize 算子，导致板端推理输出仍为量化值而非 float32
- pyramid 输入格式需在 `input_sources` 中配置 `source_type: pyramid`，并设置 `mean_value` / `scale_value`

### 4. 预处理配置必须从用户代码提取
- 阅读用户提供的预处理代码（如 `get_data_loaders()`），提取 `mean_value`、`scale_value`、`input_type_rt` 等参数
- 在编译 YAML 的 `input_sources` 中配置板端预处理节点（NV12 → RGB、mean/scale 归一化），不要跳过此步骤选择 DDR 模式

### 5. QAT 链路必须检查 GPU 环境
- QAT 校准和训练需要 GPU。执行前先检查 `torch.cuda.is_available()`
- 若返回 False，按以下顺序排查：
  1. `nvidia-smi` — 确认 GPU 驱动正常
  2. `docker exec <container> python3 -c "import torch; print(torch.cuda.is_available())"` — 确认容器内有 GPU
  3. 若容器内 CUDA 不可用，常见原因：
     - **容器启动时未传 `--gpus all`**：`docker inspect <container>` 检查 `HostConfig.DeviceRequests` 是否为 null。若为 null，说明启动命令缺少 GPU 参数，需要**重建容器**（Docker 不支持给运行中的容器追加 GPU）
     - **长时间运行的容器丢失 GPU hook**：Docker daemon 重启或 NVIDIA 驱动更新后，已运行的容器可能丢失 nvidia-container-runtime 注入的 GPU 设备映射。修复方法：**`docker restart <container>`**，重启后 nvidia hook 重新生效
  4. **切换到 OE GPU docker 容器**（推荐方案）：
     ```bash
     docker run --rm --gpus all --shm-size="15g" --entrypoint /bin/bash \
       -v $OE_DIR:/open_explorer \
       -v <数据目录>:/data \
       -v <工作目录>:/workspace \
       openexplorer/ai_toolchain_ubuntu_22_j6_gpu:$OE_VERSION \
       -c "python3 your_qat_script.py"
     ```
     容器内 `torch.cuda.is_available() = True`，`horizon_plugin_pytorch` / `hbdk4` / `hmct` 均可用
- GPU 不可用时，应明确告知用户并建议切换到 GPU docker 容器，不可静默跳过校准/导出/编译步骤

### 6. 部署后可选：板端资源验证
- 当用户提到目标帧率、实车设计帧率、资源预算等关键词时，部署完成后应使用 `j6-board-monitor` 验证模型在目标帧率下的 BPU/DDR/内存消耗
- 这不是强制步骤，但在实车场景中很常见——确认模型不仅功能正确，且资源消耗在可接受范围内
- 路由到 `j6-board-monitor` skill（Scenario A：受控推理 + 同步监控）

### 7. 部署报告必须包含延时与精度对比
- 任何端到端部署任务的**最终报告**都必须包含以下字段，缺一不可：
  - **板端推理延时**（ms）：使用 `hbm_perf(remote_ip=...)` 或 `j6-ucp-model-perf-eval` 实测
  - **精度对比**：HBM 推理输出与浮点模型输出的 cosine similarity / Top-K 匹配率
  - **CPU 算子检查结果**：编译后是否存在 CPU fallback 算子
- 仅输出精度对比而缺少延时数据，或仅输出延时而缺少精度对比，均视为报告不完整
- 延时数据应标注测量方式（hbm_perf 静态分析 vs 板端实测）

### 8. QAT 链路：`.bc` 为必检中间产物
- QAT 链路（PyTorch 代码 → horizon_plugin_pytorch）的产物链为：`.pt/.pth` → `.bc` → `.hbm`
- `.bc` 文件是 QAT 适配完成的唯一标志物，必须在 outputs 中交付
- 如果 `.bc` 未生成，说明 QAT 适配流程未完成，不应跳过直接进入 HMCT PTQ 路径
- Agent 应在报告中明确记录 `.bc` 的生成状态

### 9. 延时不达标的降级策略
- 当板端实测延时超过用户目标时，按以下顺序尝试优化：
  1. **检查编译配置**：确认 `debug: false`、`opt_level: 2`、`core_num` 合理
  2. **检查 CPU 算子**：CPU fallback 算子是常见延时瓶颈，列出具体算子名
  3. **后处理迁移 C++**：将 Python 后处理逻辑（NMS、decode、sigmoid 等）改为 C++ 实现，路由到 `j6-ucp-infer-generating`
  4. **混合精度调整**：对延时敏感的层使用 int8，精度敏感的层使用 int16/fp16
- 在报告中明确说明延时是否达标，若不达标需列出已尝试的优化措施和当前瓶颈

### 10. QAT 链路：关闭伪量化精度验证（_float 验证）
- QAT 适配完成后、导出 `.bc` 之前，应验证**关闭伪量化**（`_float` 模式）下的推理精度与原始浮点模型对齐
- 方法：在 `set_fake_quantize(model, FakeQuantState.VALIDATION)` 后，额外运行一次不带伪量化的推理，对比输出
- 如果 `_float` 精度与浮点差异过大（cosine < 0.999），说明 QAT 适配本身引入了精度损失，应先修复适配问题再进入编译流程
- 这是 QAT 链路中"量化适配完成"的验证门槛，不通过则不应继续后续步骤
