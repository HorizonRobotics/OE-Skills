# oe_code_chunk_oellm_runtime

## 仓库概述

- **名称**: oellm_runtime (Horizon OE LLM Runtime SDK) v2.0.2
- **分发形式**: 预编译 C++ 动态库（`liboellm_runtime.so`）+ 公开头文件 + 示例工程，无源码可编译（仅 examples 需交叉编译）
- **用途**: 在 Horizon J6（Open Explorer）边缘硬件上运行多模态视觉语言模型（VLM）推理，支持同步/异步推理、批量推理、HTTP 服务
- **角色**: J6 Open Explorer (OE) LLM v2.0.0 RC3 的板端推理运行时，位于 LLM 包根目录 `runtime/` 下
- **核心产物**: `liboellm_runtime.so`（~15 MB），依赖 `libdnn.so`、`libhbucp.so`、`libhbrt4.so`、`libchat_template.so`、`libhbvp.so`、`libhbtl.so`、`libhbhpl.so`、`libhbdsp_plugin.so` 等
- **支持模型**: InternVL2 / InternVL2.5 / InternVL3.5、Qwen2.5-VL、Qwen3-VL
- **目标架构**: aarch64（J6 板端），不可在 x86 主机上运行

## 目录结构

```
runtime/
  CLAUDE.md                                # Claude Code 工作指引文档

  include/                                 # 公开 C++ 头文件
    oellm_runtime_basic/
      oellm_runtime.h                      #   OellmRuntime 类（Init/Infer/InferAsync/WaitInferResponse/GetOellmInferMetric）
      oellm_runtime_common.h               #   所有请求/响应/指标数据类型定义
      oellm_runtime_error_code.h           #   OellmErrorCode 错误码枚举
      oellm_runtime_version.h              #   编译期版本宏 + 运行时 GetVersion()

  lib/                                     # 预编译动态库（全部需放在同一目录）
    liboellm_runtime.so                    #   主入口库（~15 MB）
    liboellm_hlog_wrapper.so               #   OE LLM 日志封装
    libdnn.so                              #   DNN 推理库
    libhbucp.so                            #   UCP 统一计算平台
    libhbrt4.so                            #   BPU 运行时 v4
    libhbtl.so                             #   HBTL 模板库（~94 MB，最大）
    libhbvp.so                             #   视觉处理库
    libhbhpl.so                            #   HPL 硬件加速库
    libhbdsp_plugin.so                     #   DSP 插件库
    libhb_arm_rpc.so                       #   ARM RPC 通信库
    libchat_template.so                    #   Chat 模板渲染库
    libhlog_wrapper.so                     #   日志封装库
    libperfetto_sdk.so                     #   Perfetto 性能追踪 SDK
    libprotobuf.so / .so.32 / .so.32.0.12  #   Protocol Buffers 运行时
    libalog.so / .so.1 / .so.1.2.2         #   ALog 日志库
    libopencv_world.so / .so.409 / .so.4.9.0  #   OpenCV 4.9.0

  configs/                                 # 模型配置文件（每模型一个目录）
    InternVL2-1B_config/
      oellm_config.json                    #   InternVL2-1B 推理配置
    InternVL2-2B_config/
      oellm_config.json                    #   InternVL2-2B 推理配置
    InternVL2_5-1B_config/
      oellm_config.json                    #   InternVL2.5-1B 推理配置
    InternVL2_5-2B_config/
      oellm_config.json                    #   InternVL2.5-2B 推理配置
    InternVL3_5-1B_config/
      oellm_config.json                    #   InternVL3.5-1B 推理配置
    Qwen2_5-VL-7B_config/
      oellm_config.json                    #   Qwen2.5-VL-7B 推理配置
    Qwen3-VL-2B_config/
      oellm_config.json                    #   Qwen3-VL-2B 图像推理配置
      oellm_video_config.json              #   Qwen3-VL-2B 视频推理配置

  examples/                                # C++ 示例工程（aarch64 交叉编译）
    3rdparty/                              #   第三方 header-only 库
      nlohmann/                            #     nlohmann/json（JSON 解析）
      httplib/                             #     cpp-httplib（HTTP 服务）
    oellm_simple/                          #   基础推理示例
      simple_demo_request.cc               #     同步推理
      simple_demo_request_async.cc         #     异步推理 + 回调（支持流式输出）
      simple_demo_request_async_wait.cc    #     异步推理 + 阻塞等待
      sampler_config.json                  #     采样参数配置示例
      simple_demo_sampler_config.h         #     采样配置 C++ 头文件
      CMakeLists.txt                       #     CMake 构建文件
      build_demo.sh                        #     构建脚本
    oellm_batch_request/                   #   批量推理示例
      batch_request_demo_request.cc        #     多图片并行推理
      CMakeLists.txt
      build_demo.sh
    oellm_image_data/                      #   原始字节输入示例
      image_data_demo_request.cc           #     内存图像数据推理（绕过文件加载）
      CMakeLists.txt
      build_demo.sh
    oellm_serving/                         #   HTTP 推理服务示例
      oellm_serving.cc                     #     0.0.0.0:8080 HTTP 服务（multipart form POST）
      vlm.html                             #     Web 前端页面
      CMakeLists.txt
      build_demo.sh
```

## C++ 头文件 API

### OellmRuntime 类 (`oellm_runtime.h`)

```cpp
namespace oellm {

class OellmRuntime {
public:
  OellmRuntime();                          // 构造 runtime 句柄
  ~OellmRuntime();                         // 析构（自动释放资源）

  // 禁止拷贝构造和移动
  OellmRuntime(OellmRuntime const&) = delete;
  OellmRuntime(OellmRuntime&&) = delete;
  OellmRuntime& operator=(OellmRuntime const&) = delete;
  OellmRuntime& operator=(OellmRuntime&&) = delete;

  OellmErrorCode Init(std::string const& config_path);

  OellmErrorCode Infer(OellmRequest const& request, OellmResponse& response);

  OellmErrorCode InferAsync(OellmRequest const& request,
                            ResponseCallBack response_cb = nullptr,
                            void* userdata = nullptr);

  OellmErrorCode WaitInferResponse(int32_t timeout, OellmResponse& response);

  OellmErrorCode GetOellmInferMetric(OellmMetric& metric);
};

// 异步回调签名
using ResponseCallBack = std::function<void(OellmResponse const&, void*)>;

}  // namespace oellm
```

| 方法 | 说明 |
|------|------|
| `Init(config_path)` | 初始化 runtime，加载配置文件指定的 ViT / LM / embed 模型 |
| `Infer(request, response)` | 同步推理，阻塞直到完成 |
| `InferAsync(request, cb, userdata)` | 异步推理，cb 非空时在回调中接收结果，cb 为空时需配合 WaitInferResponse |
| `WaitInferResponse(timeout, response)` | 阻塞等待已提交的异步推理完成 |
| `GetOellmInferMetric(metric)` | **消费式读取**已完成推理的性能指标（读取后清空内部缓冲） |

### 数据类型 (`oellm_runtime_common.h`)

#### 枚举类型

| 枚举 | 值 | 说明 |
|------|-----|------|
| `OellmBackend` | `kBpuAny(0)`, `kBpu0(1)`–`kBpu3(4)` | BPU 核心选择 |
| `OellmPriority` | `kPriorityNormal(0)`, `kPriorityHigh(1)`, `kPriorityUrgent(2)` | 推理优先级（urgent > high > normal） |
| `OellmStatus` | `kInValid(0)`, `kStart(1)`, `kRunning(2)`, `kNormalFinished(3)`, `kMaxContextFinished(4)`, `kInternalError(5)` | 推理状态 |
| `OellmRequestDataType` | `kBasic(0)`, `kImage(1)`, `kAudio(2)`, `kVideo(3)`, `kBytes(4)`, `kCustom(100)` | 请求数据类型 |
| `OellmResponseDataType` | `kBasic(0)`, `kLogits(1)`, `kCustom(100)` | 响应数据类型 |
| `OellmMetricType` | `kBasic(0)`, `kVlm(1)`, `kCustom(100)` | 指标数据类型 |
| `ImageType` | `kRgb(0)`, `kBgr(1)`, `kYUV444(2)`, `kNv12(3)`, `kFeature(4)` | 图像类型（kFeature 跳过预处理直接输入） |
| `ImageLayout` | `kHwc(0)`, `kChw(1)` | 图像内存布局 |

#### 核心结构体

**OellmPrompt** — 支持三种 prompt 形式：
```cpp
struct OellmPrompt {
  struct TextPrompt { std::string text; };
  struct TokenIdPrompt { std::vector<int32_t> token_ids; };      // 占位，暂不支持
  struct EmbeddingPrompt { std::vector<uint8_t> embedding_bytes; }; // 占位，暂不支持
  using Prompt = std::variant<TextPrompt, TokenIdPrompt, EmbeddingPrompt>;

  Prompt system_prompt = TextPrompt{.text = ""};
  Prompt user_prompt = TextPrompt{.text = ""};
};
```

**OellmImageData** — 图像数据（路径或原始字节）：
```cpp
struct OellmImageData : public OellmRequestData {
  std::variant<std::string, std::vector<uint8_t>> image;  // 文件路径 或 原始字节
  ImageType type = ImageType::kRgb;
  ImageLayout layout = ImageLayout::kHwc;
  int32_t width = 0;     // 原始字节时需设置
  int32_t height = 0;    // 原始字节时需设置
};
```

**OellmVideoData** — 视频数据：
```cpp
struct OellmVideoData : public OellmRequestData {
  std::variant<std::string, std::vector<uint8_t>> video;
};
```

**OellmSampleParams** — 采样参数：
```cpp
struct OellmSampleParams {
  enum class SampleParamType {
    kTopK, kTopP, kTemperature, kTailFree, kTypical, kMinP
  };
  struct SampleParam {
    SampleParamType sample_type;
    std::variant<int, float> value;
  };
  struct PenaltyParams {
    int32_t penalty_last_n = 128;    // 惩罚窗口
    float penalty_repeat = 1.0f;     // 重复惩罚
    float penalty_freq = 0.0f;       // 频率惩罚
    float penalty_present = 0.0f;    // 存在惩罚
  };

  bool do_sample = false;                              // false = 贪心 argmax
  std::vector<SampleParam> sample_params;              // 按顺序执行
  int32_t min_token_num = 1;
  bool enable_penalty = false;
  PenaltyParams penalty_params;
};
```

**OellmRequest** — 推理请求：
```cpp
struct OellmRequest {
  struct Request {
    int32_t request_id = -1;
    bool need_partial_result = false;                  // 回调时逐 token 返回
    OellmPriority priority = OellmPriority::kPriorityNormal;
    OellmSampleParams sample_params;
    OellmPrompt prompt;
    std::optional<std::vector<std::shared_ptr<OellmRequestData>>> data;
  };
  std::vector<Request> oellm_requests;                 // 支持多请求并行
  bool only_prefill = false;
  bool output_logits = false;
};
```

**OellmResponseData** — 推理结果：
```cpp
struct OellmResponseData {
  int32_t request_id;
  std::string text_result;
  std::vector<int32_t> token_ids;
  OellmStatus status;                                  // 必须检查！
};
```

**OellmMetricData / VlmMetric** — 性能指标：
```cpp
struct OellmMetricData {
  int32_t request_id;
  double e2e;              // 端到端耗时
  double ttft;             // 首字耗时 (Time To First Token)
  double tpot;             // 单 token 耗时 (Time Per Output Token)
  double prefill_cost;     // prefill 耗时 (ms)
  double prefill_tps;      // prefill tokens/s
  double decode_tps;       // decode tokens/s
  int32_t prefill_token_num;
  int32_t decode_token_num;
};

struct VlmMetric : public OellmMetricData {
  double vit_preprocess_cost;   // 视觉前处理耗时
  double vit_cost;              // ViT 模型推理耗时
};
```

### 错误码 (`oellm_runtime_error_code.h`)

| 错误码 | 值 | 说明 |
|--------|-----|------|
| `kOk` | 0 | 成功 |
| `kErrInvalidParam` | -1 | 无效参数 |
| `kErrInitFailed` | -2 | 初始化失败 |
| `kErrModelLoadFailed` | -3 | 模型加载失败 |
| `kErrInferenceFailed` | -4 | 推理失败 |
| `kErrOom` | -5 | 内存不足 |
| `kErrAborted` | -6 | 推理中止 |
| `kErrTimeout` | -7 | 超时 |
| `kErrNotSupported` | -8 | 不支持 |
| `kErrKvCacheFull` | -9 | KV cache 已满 |
| `kErrMemAllocFailed` | -10 | 内存分配失败 |
| `kErrMemFreeFailed` | -11 | 内存释放失败 |
| `kErrMemFlushFailed` | -12 | 内存刷新失败 |

### 版本接口 (`oellm_runtime_version.h`)

```cpp
#define OELLM_VERSION_MAJOR 2
#define OELLM_VERSION_MINOR 0
#define OELLM_VERSION_PATCH 2
#define OELLM_VERSION_CODE  OELLM_MAKE_VERSION(2, 0, 2)  // = 20002

// 编译期版本比较
#if OELLM_VERSION_CODE >= OELLM_MAKE_VERSION(1, 1, 0)
  // ...
#endif

// 运行时版本字符串
const char* oellm::GetVersion();  // 返回 "2.0.2"
```

## 模型配置文件

### oellm_config.json 结构

```json
{
  "work_dir": "/map/data/oellm/models/qwen3-vl-2b/",
  "vit_model_file": "Qwen3-VL-2B-Instruct_vision_448x448_w8_nash-p_corenum_4.hbm",
  "lm_model_file": "Qwen3-VL-2B-Instruct_language_chunk_512_cache_1024_w8_nash-p_corenum_4_4.hbm",
  "embed_weight_name": "Qwen3-VL-2B-Instruct_embed_tokens.bin",
  "runtime_type": "VLM",
  "max_batch_size": 4,
  "max_image_cnt": 4,
  "backends": {
    "vit": [1, 2, 3, 4],
    "prefill": [1, 2, 3, 4],
    "decode": [1, 2, 3, 4]
  }
}
```

| 字段 | 说明 |
|------|------|
| `work_dir` | 板卡上模型文件的绝对路径 |
| `vit_model_file` | ViT 视觉模型 HBM 文件 |
| `lm_model_file` | 语言模型 HBM 文件（含 prefill + decode） |
| `embed_weight_name` | 词嵌入权重 .bin 文件 |
| `runtime_type` | 运行时类型（"VLM"） |
| `max_batch_size` | 最大批处理大小 |
| `max_image_cnt` | 最大图片数量 |
| `backends` | 各模型部分使用的 BPU 核心编号（1–4，0=任意核心） |

### 视频配置 vs 图像配置

视频配置（`oellm_video_config.json`）的区别：`max_batch_size` 降为 1，换取更大的 `max_image_cnt`（如 16 帧）和更大的 KV cache（LM 文件名 `cache_4096` 而非 `cache_1024`）。

### sampler_config.json 结构

```json
{
  "do_sample": true,
  "sample_params": [
    {"sample_type": "kTopK", "value": 50},
    {"sample_type": "kTopP", "value": 0.9},
    {"sample_type": "kTemperature", "value": 0.7}
  ],
  "enable_penalty": true,
  "penalty_params": {
    "penalty_last_n": 128,
    "penalty_repeat": 1.1,
    "penalty_freq": 0.0,
    "penalty_present": 0.0
  }
}
```

## 示例工程

### 构建方式

所有 demo 均为 aarch64 交叉编译，需设置 `LINARO_GCC_ROOT` 环境变量（默认 `/opt/aarch64/arm-gnu-toolchain-12.2.rel1-x86_64-aarch64-none-linux-gnu`）：

```bash
cd examples/<demo_name>
bash build_demo.sh
# 产物位于 examples/<demo_name>/build/
```

CMake 使用 C++17，通过 `-loellm_runtime` 链接，设置 `RPATH=$ORIGIN/../../lib`。

### 示例列表

| 示例 | 文件 | 说明 |
|------|------|------|
| 同步推理 | `oellm_simple/simple_demo_request.cc` | `Infer()` 阻塞等待结果 |
| 异步回调 | `oellm_simple/simple_demo_request_async.cc` | `InferAsync(cb)` + `need_partial_result` 流式输出 |
| 异步等待 | `oellm_simple/simple_demo_request_async_wait.cc` | `InferAsync()` + `WaitInferResponse()` |
| 批量推理 | `oellm_batch_request/batch_request_demo_request.cc` | 多张图片各自 prompt 并行推理 |
| 原始字节 | `oellm_image_data/image_data_demo_request.cc` | 内存图像数据（RGB/BGR/NV12/Feature 等格式） |
| HTTP 服务 | `oellm_serving/oellm_serving.cc` | 0.0.0.0:8080 multipart form POST（非 OpenAI 兼容） |

### 运行参数

```bash
# 通用参数
--config_path /path/to/oellm_config.json   # 必需：模型配置文件
--image_path img.jpg                        # 图片路径（批量时逗号分隔）
--prompt "describe this image"             # 文本提示
--sampler_config_path sampler_config.json  # 可选：采样参数覆盖（仅 oellm_simple 系列）
--priority 0|1|2                           # 可选：Normal/High/Urgent
--no_warmup                                # 可选：跳过首次预热推理
--need_partial_result                      # 可选：启用流式回调

# 原始字节特有参数
--image_data_path image.bin                # 原始图像字节文件
--image_type rgb|bgr|yuv444|nv12|feature  # 图像类型
--image_layout hwc|chw                     # 内存布局
--image_width 448                          # 图像宽度
--image_height 448                         # 图像高度
```

## API 使用模式

```cpp
#include "oellm_runtime_basic/oellm_runtime.h"

// 1. 构造 + 初始化
auto runtime = std::make_shared<oellm::OellmRuntime>();
auto rc = runtime->Init("/path/to/oellm_config.json");

// 2. 构建请求
oellm::OellmRequest req;
oellm::OellmRequest::Request r;
r.request_id = 0;
r.prompt = oellm::OellmPrompt{
    .user_prompt = oellm::OellmPrompt::TextPrompt{.text = "your prompt"}};

// 图片输入（文件路径）
auto img = std::make_shared<oellm::OellmImageData>();
img->data_type = oellm::OellmRequestDataType::kImage;
img->image = std::string("image.jpg");
r.data.emplace();
r.data->emplace_back(img);

req.oellm_requests.emplace_back(std::move(r));

// 3. 推理（三选一）
// a) 同步
oellm::OellmResponse resp;
runtime->Infer(req, resp);

// b) 异步 + 回调（可流式）
runtime->InferAsync(req, [](oellm::OellmResponse const& resp, void*) {
    for (auto& d : resp.response_datas) {
        std::cout << d->text_result << std::flush;
    }
}, nullptr);

// c) 异步 + 阻塞等待
runtime->InferAsync(req);
runtime->WaitInferResponse(60000, resp);  // 超时 60s

// 4. 读取结果
for (auto& d : resp.response_datas) {
    // 必须检查 status！
    if (d->status == oellm::OellmStatus::kNormalFinished) {
        std::cout << d->text_result;
    }
}

// 5. 读取性能指标（消费式，每次推理调用一次）
oellm::OellmMetric metric;
runtime->GetOellmInferMetric(metric);
for (auto& m : metric.metric_datas) {
    // VLM 指标需 dynamic_pointer_cast
    auto vlm = std::dynamic_pointer_cast<oellm::VlmMetric>(m);
    if (vlm) {
        std::cout << "ViT: " << vlm->vit_cost << "ms\n";
    }
}
```

## 常用查询映射

| 用户意图 | 推荐搜索关键词 | 说明 |
|---|---|---|
| 初始化 runtime | `OellmRuntime`, `Init`, `config_path` | 构造与初始化 |
| 同步推理 | `Infer`, `OellmRequest`, `OellmResponse` | 阻塞推理接口 |
| 异步推理 | `InferAsync`, `ResponseCallBack`, `need_partial_result` | 异步 + 回调/等待 |
| 阻塞等待 | `WaitInferResponse`, `timeout` | 异步结果等待 |
| 性能指标 | `GetOellmInferMetric`, `OellmMetric`, `VlmMetric`, `ttft`, `tpot` | 消费式指标读取 |
| 图片输入 | `OellmImageData`, `ImageType`, `ImageLayout`, `kFeature` | 图片数据格式 |
| 视频输入 | `OellmVideoData`, `oellm_video_config` | 视频推理 |
| 原始字节 | `image_data`, `kRgb`, `kBgr`, `kNv12`, `width`, `height` | 内存图像数据 |
| Prompt 构造 | `OellmPrompt`, `TextPrompt`, `system_prompt`, `user_prompt` | Prompt 三种形式 |
| 采样参数 | `OellmSampleParams`, `kTopK`, `kTopP`, `kTemperature`, `do_sample` | 采样策略配置 |
| 重复惩罚 | `PenaltyParams`, `penalty_repeat`, `penalty_freq`, `penalty_present` | 重复抑制 |
| 推理优先级 | `OellmPriority`, `kPriorityNormal`, `kPriorityHigh`, `kPriorityUrgent` | 请求调度 |
| BPU 核心分配 | `OellmBackend`, `backends`, `kBpu0`, `core_id` | BPU 核心绑定 |
| 推理状态 | `OellmStatus`, `kNormalFinished`, `kMaxContextFinished`, `kInternalError` | 结果状态检查 |
| 错误处理 | `OellmErrorCode`, `kErrKvCacheFull`, `kErrTimeout`, `kErrOom` | 错误码判断 |
| 版本信息 | `GetVersion`, `OELLM_VERSION_CODE`, `OELLM_MAKE_VERSION` | 编译期/运行时版本 |
| 模型配置 | `oellm_config.json`, `work_dir`, `vit_model_file`, `lm_model_file` | 配置文件结构 |
| 批量推理 | `batch_request`, `oellm_requests`, `max_batch_size` | 多请求并行 |
| HTTP 服务 | `oellm_serving`, `httplib`, `/vlm`, `multipart` | Web 推理服务 |
| Chat 模板 | `libchat_template.so`, `chat_template` | 对话模板渲染 |
| KV cache | `kErrKvCacheFull`, `cache_1024`, `cache_4096` | KV cache 容量 |
| 交叉编译 | `LINARO_GCC_ROOT`, `aarch64`, `build_demo.sh`, `CMakeLists.txt` | 示例构建 |

## 规则与约定

- **仅面向 J6 板端**：不可在 x86 主机上运行，只支持 aarch64 交叉编译
- **单实例非线程安全**：`OellmRuntime` 实例不支持并发调用；需串行化或利用优先级机制调度
- **所有 .so 必须同目录**：`liboellm_runtime.so` 依赖的其他动态库必须在同一目录下，通过 RPATH 查找
- **必须检查 response status**：`kNormalFinished`（正常）、`kMaxContextFinished`（达最大长度）、`kInternalError`（异常）
- **GetOellmInferMetric 是消费式读取**：返回已完成推理的指标后即清空内部缓冲，每次推理只调用一次
- **VlmMetric 需 dynamic_pointer_cast**：`metric_datas` 是 `shared_ptr<OellmMetricData>`，VLM 场景需转型为 `VlmMetric` 才能访问 `vit_cost` / `vit_preprocess_cost`
- **kFeature 跳过预处理**：`ImageType::kFeature` 将字节直接作为 ViT 输入，配合预提取的 feature .bin 文件
- **原始字节需完整描述**：传 `std::vector<uint8_t>` 时必须同时设置 `type`、`layout`、`width`、`height`
- **oellm_serving 非 OpenAI 兼容**：使用 cpp-httplib，在 `/vlm` 路径提供 multipart form POST 接口
- **InferAsync 流式输出**：设置 `need_partial_result=true` 后，回调会在每解码一个 token 时触发
- **backends 配置**：BPU 核心编号 1–4，0 表示任意核心；vit/prefill/decode 可独立配置核心分配
