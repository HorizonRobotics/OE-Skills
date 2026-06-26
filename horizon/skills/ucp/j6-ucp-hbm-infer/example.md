# User Guide

两种触发 hbm-infer skill 的方式：
- **明确触发**：提及 `hbm-infer` 后跟需求描述
- **自动触发**：当提问涉及 hbm_infer 客户端 API、远程推理代码编写、板端推理调试等场景时，skill 会自动匹配触发

## Example 1: Single Model Remote Inference

> 生成googlenet_224x224_nv12.hbm的远程推理代码，模型输入为nv12类型，输入图像为zebra_cls.jpeg，你可以调用相应接口查询模型输入输出具体信息并以此准备输入数据，分类ID正确结果为340。远程开发板IP为10.103.43.28，用户名为root，无密码，本地python环境为~/.venv/。

**关键要素：**
- 指定模型文件和输入类型（NV12）
- 指定输入图像
- 允许查询模型 I/O 信息以准备数据
- 提供预期结果用于验证
- 提供板端连接信息

**Skill 行为：**
1. 查找工作区中的模型文件和图像文件
2. 通过 `get_input_info()` / `get_output_info()` 查询模型规格：
   - 输入：`data_y` [1,224,224,1] uint8 + `data_uv` [1,112,112,2] uint8（NV12 双平面）
   - 输出：`output` [1,1000] float32
3. 将 JPEG 图像 resize 到 224x224，转 I420 再拆分为 Y 平面和 UV 交织平面，匹配模型输入形状
4. 生成使用 Standard 模式的完整推理脚本，包含 try/finally 资源清理
5. 运行验证，Top-1 分类 ID = 340，置信度 9.9965，结果正确

---

## Example 2: Multi-Process Profile Benchmark

> 开启3个进程分别推理工作区中的3个分类模型各1000帧并统计profile信息。

**关键要素：**
- 多进程并发推理
- 多模型（工作区中所有分类模型）
- 指定帧数（1000帧）
- 统计 profile 性能数据

**Skill 行为：**
1. 逐一查询三个模型的输入输出规格（输入名称、形状、类型各不相同）：
   - googlenet_nv12：`data_y` / `data_uv`，uint8
   - resnet50_nv12：`input_y` / `input_uv`，uint8
   - resnet50_rgb：`input` [1,224,224,3]，int8
2. 为 NV12 模型和 RGB 模型分别准备输入数据
3. 使用 `multiprocessing.Process` 开启 3 个进程并发执行，每个进程独立创建 `HbmRpcSession` 并设置 `with_profile=True`
4. 推理完成后通过 `get_profile()` 汇总各阶段延迟（frame / infer / commu / prepr / pospr）的 avg/min/max

**Profile 结果摘要（3进程并发，各1000帧）：**

| 模型 | Frame Avg (ms) | Inference Avg (ms) | Network Avg (ms) | 吞吐 (FPS) |
|------|---------------|-------------------|-----------------|-----------|
| googlenet_nv12 | 9.28 | 1.22 | 6.26 | ~101 |
| resnet50_nv12 | 10.61 | 1.71 | 7.08 | ~173 |
| resnet50_rgb | 12.22 | 1.61 | 9.13 | ~136 |

关键发现：网络通信是主要瓶颈（占总延迟 60-75%）；NV12 输入数据量小，网络开销低于 RGB。
