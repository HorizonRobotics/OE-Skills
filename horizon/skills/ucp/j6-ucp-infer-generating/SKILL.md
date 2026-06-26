---
name: j6-ucp-infer-generating
description: 提供基于 UCP 的模型推理 C++ 代码生成能力。当用户询问 UCP/DNN 推理接口怎么用、某个 API 的参数含义、如何加载模型、如何分配 tensor 内存、如何提交推理任务、Cache 同步怎么做，或要求只生成推理流程中某个模块的代码时使用。
---

## 基本推理步骤

1. Step 01 - .hbm 模型加载
   `references/steps/step-01-load-model.md`
2. Step 02 - 张量信息与内存申请
   `references/steps/step-02-prepare-tensor.md`
3. Step 03 - 预处理（数据填充与缓存刷新）
   `references/steps/step-03-preprocess.md`
4. Step 04 - 执行推理
   `references/steps/step-04-run-inference.md`
5. Step 05 - 输出解析
   `references/steps/step-05-postprocess.md`
6. Step 06 - 资源释放
   `references/steps/step-06-release-resource.md`

文档路径均为本目录下的相对路径。其中 Step 03/04/05 需要每个推理帧重做，其他步骤可以复用。

## 分析行为规则

- 当用户的生成要求涉及到一个或多个步骤时，再阅读对应的步骤文档。
- 遇到不明确的 API 调用时，阅读 `references/api/index.md` 路由详细 API 介绍。

## 代码生成规则

- 代码生成聚焦 UCP 接口调用，无关代码（信息打印、非 UCP 接口返回值的检查、异常处理、命令行参数解析等）默认不关注。
- 代码生成时必须参考用户代码上下文，统一代码风格，复用已有逻辑。

## 代码生成流程

**必须逐个 step 生成代码，用户确认后再进入下个 step 分析生成流程**

1. 阅读用户代码上下文和用户请求。
2. 确定代码生成涉及的 Steps 列表。
3. 对每个涉及的 Step 串行执行:
   3.1 阅读对应的 Step 文档。
   3.2 根据上下文或用户请求确定具体分支，若可以确定 -> 继续下一步；否则 -> AskUserQuestion -> 重新执行此步骤。
   3.3 确定要使用的 UCP API 列表。
   3.4 对每个涉及的 API 串行执行:
      3.4.1 确定 API 所在头文件。
      3.4.2 根据上下文或用户请求确定 API 的每个参数，若可以确定 -> 继续下一步；否则 -> AskUserQuestion -> 重新执行此步骤。
      3.4.3 API 参数均确定后进行下一个 API 的处理。
   3.5 分支均确定后进行下一个 Step 的处理。
4. 执行代码生成并检查正确性。
