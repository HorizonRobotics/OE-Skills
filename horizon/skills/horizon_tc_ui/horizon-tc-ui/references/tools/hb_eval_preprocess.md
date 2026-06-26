# hb_eval_preprocess 工具参考

## 1. 概述

`hb_eval_preprocess` 是评估数据预处理工具，为指定的预训练模型生成评估所需的预处理数据（`.bin` 文件）。它内置了一个模型清单（`MODEL_DICT`），支持分类、检测和分割等多种模型，根据每个模型的特性自动选择图片读取方式（skimage / opencv / PIL）并进行标准化预处理。

**入口点**（`setup.py` 中的 `console_scripts`）：

```
hb_eval_preprocess = horizon_tc_ui.hb_eval_preprocess:cmd_main
```

## 2. 命令签名

```bash
hb_eval_preprocess [OPTIONS]
```

| 选项 | 类型 | 默认值 | 必填 | 隐藏 | 说明 |
|------|------|--------|------|------|------|
| `-m, --model_name` | `click.Choice(...)` | 无 | 是 | 否 | 模型名称，从 `MODEL_DICT` 中 `enable=True` 的项选择 |
| `-i, --image_dir` | `str` | 无 | 是 | 否 | 输入图片目录 |
| `-o, --output_dir` | `str` | `"affected"` | 否 | 否 | 输出目录 |
| `-v, --val_txt` | `str` | `None` | 否 | 否 | 验证标注文件路径 |
| `-h, --help` | `flag` | - | 否 | 否 | 显示帮助信息 |
| `--version` | `flag` | - | 否 | 否 | 显示版本信息 |

## 3. 典型调用示例

### 最小调用

```bash
hb_eval_preprocess -m mobilenetv1 -i ./images
```

### 常用调用（指定输出目录）

```bash
hb_eval_preprocess -m mobilenetv1 -i ./images -o ./eval_data
```

### 全量调用（带验证标注文件）

```bash
hb_eval_preprocess -m resnet50 -i ./imagenet/val -o ./output -v ./val.txt
```

### single_mode 示例

```bash
hb_eval_preprocess -m yolov5x -i ./coco/images -o ./coco_preprocessed
```

## 4. 输入要求

### MODEL_DICT 启用模型清单

模型清单定义在 `horizon_tc_ui/eval_preprocess/conf.py` 的 `MODEL_DICT` 中，只有 `enable=True` 的模型可以使用。当前启用的模型包括：

| 模型名称 | 图片读取方式 | 类别 |
|----------|-------------|------|
| mobilenetv1 | skimage | 分类 |
| mobilenetv2 | skimage | 分类 |
| resnet50 | PIL | 分类 |
| resnet18 | PIL | 分类 |
| googlenet | opencv | 分类 |
| efficientnet_lite0~4 | skimage | 分类 |
| vargconvnet | opencv | 分类 |
| efficientnasnet_m | opencv | 分类 |
| efficientnasnet_s | opencv | 分类 |
| yolov2_darknet19 | opencv | 检测 |
| yolov3_darknet53 | opencv | 检测 |
| yolov5x | opencv | 检测 |
| yolov3_vargdarknet | opencv | 检测 |
| ssd_mobilenetv1 | opencv | 检测 |
| centernet_resnet101 | opencv | 检测 |
| deeplabv3plus_efficientnetb0 | opencv | 分割 |
| deeplabv3plus_efficientnetm1 | opencv | 分割 |
| deeplabv3plus_efficientnetm2 | opencv | 分割 |
| fastscnn_efficientnetb0 | opencv | 分割 |

**未启用的模型**（`enable=False`）：efficientdetd0, fcos_efficientnetb0, yolov4, fcos_resnet50, fcos_resnext101, unet_mobilenet, deeplabv3plus_dilation1248

### 图片读取方式

不同模型使用不同的图片读取库：

| 读取方式 | 说明 | 适用模型 |
|----------|------|----------|
| skimage | scikit-image 读取 | mobilenetv1/v2, efficientnet_lite 系列 |
| opencv | OpenCV 读取 | 大部分检测/分割模型、googlenet 等 |
| PIL | Pillow 读取 | resnet50, resnet18 |

### 输入目录

- `--image_dir`：原始图片目录，包含待预处理的图片文件
- `--val_txt`（可选）：验证标注文件路径，用于指定需要处理的图片列表及其标签

## 5. 输出产物

### 输出文件

- 输出目录（默认 `affected/` 或通过 `-o` 指定）下生成预处理后的 `.bin` 文件
- 每个输入图片对应一个或多个 `.bin` 文件（取决于模型的输入要求）
- `.bin` 文件格式适配对应模型的评估需求，可直接作为模型输入

### 日志位置

- 日志文件：`./hb_eval_preprocess.log`（当前工作目录）
- console 级别：`INFO`；file 级别：`DEBUG`

## 6. 退出码与错误约定

| 退出码 | 含义 |
|--------|------|
| `0` | 成功完成 |
| `-1` | 执行过程中发生异常（由 `@on_exception_exit` 装饰器处理） |

常见错误场景：
- `--model_name` 不在启用列表中 → `click.BadParameter`
- `--image_dir` 目录不存在 → 运行时错误
- 图片文件损坏或格式不支持 → 预处理阶段报错

## 7. 版本兼容性

| 依赖 | 最低版本 | 说明 |
|------|----------|------|
| scikit-image | 0.19.0 (py3.10) / 0.20.0 (py3.11) | skimage 读取方式需要 |
| opencv-python | 4.6.0.66 | opencv 读取方式需要 |
| Pillow | 已安装 | PIL 读取方式需要 |
| numpy | 1.23.0 (py3.10) / 1.24.2 (py3.11) | 数据处理需要 |

## 8. 源码入口

| 模块 | 路径 | 说明 |
|------|------|------|
| CLI 入口 | `horizon_tc_ui/hb_eval_preprocess.py` | `cmd_main()` 函数 |
| 预处理核心 | `horizon_tc_ui/eval_preprocess/` | `EvalPreprocess` 类 |
| 模型配置 | `horizon_tc_ui/eval_preprocess/conf.py` | `MODEL_DICT` 字典定义 |
| 版本信息 | `horizon_tc_ui/eval_preprocess/__init__.py` | `__VERSION__` |
