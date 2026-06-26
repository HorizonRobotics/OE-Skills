# hb_eval_preprocess 评估数据预处理

## 适用场景

**触发关键词**：评估预处理、eval preprocess、校准数据生成、bin 文件、板端输入数据

**前置条件**：
- 已有原始图片数据集目录
- 已确认模型名称在 MODEL_DICT 支持列表中
- 已安装 `horizon_tc_ui` 工具包及额外依赖（cv2, skimage, PIL 等）

## 产出物

| 产物文件 | 路径 | 说明 |
|---------|------|------|
| `{image_name}_{org_h}_{org_w}_{dst_h}_{dst_w}.bin` | `{output_dir}/` | 预处理后的二进制文件，可直接作为模型输入 |

**命名规则**：`{原始图片名}_{原始高}_{原始宽}_{目标高}_{目标宽}.bin`

示例：`cat_224_224_224_224.jpg_224_224_224_224.bin`

## 步骤

### 步骤 1：确认支持的模型

hb_eval_preprocess 仅支持 MODEL_DICT 中 `enable: True` 的模型（源码 `eval_preprocess/conf.py`）：

**分类模型**（enable: True）：
- `mobilenetv1`, `mobilenetv2`
- `resnet50`, `resnet18`
- `googlenet`
- `efficientnet_lite0` ~ `efficientnet_lite4`
- `vargconvnet`
- `efficientnasnet_m`, `efficientnasnet_s`

**检测模型**（enable: True）：
- `yolov2_darknet19`, `yolov3_darknet53`, `yolov5x`
- `ssd_mobilenetv1`
- `centernet_resnet101`
- `yolov3_vargdarknet`

**分割模型**（enable: True）：
- `deeplabv3plus_efficientnetb0`
- `fastscnn_efficientnetb0`
- `deeplabv3plus_efficientnetm1`
- `deeplabv3plus_efficientnetm2`

**不支持的模型**（enable: False）：
- `efficientdetd0`, `fcos_efficientnetb0`, `yolov4`, `fcos_resnet50`, `fcos_resnext101`
- `unet_mobilenet`, `deeplabv3plus_dilation1248`

### 步骤 2：准备输入数据

**输入目录要求**：
- 目录中包含图片文件（支持 `.jpg`, `.jpeg`, `.png` 格式）
- 其他格式文件会被跳过并输出警告

**可选 val_txt**：
- 使用 `-v` 参数指定 val.txt 文件
- val.txt 每行一个图片文件名（不含扩展名）
- 仅处理 val.txt 中列出的图片

### 步骤 3：基本命令

```bash
hb_eval_preprocess -m mobilenetv1 -i ./images -o ./calibration_data
```

**参数说明**：
- `-m` / `--model_name`：模型名称（必须在支持列表中）
- `-i` / `--image_dir`：输入图片目录（可以是单张图片文件）
- `-o` / `--output_dir`：输出目录（默认 `affected`）
- `-v` / `--val_txt`：可选的验证集列表文件

### 步骤 4：使用 val_txt 过滤

```bash
hb_eval_preprocess -m resnet50 \
  -i ./ILSVRC2012_img_val \
  -o ./cal_data_resnet50 \
  -v ./val.txt
```

### 步骤 5：单张图片处理

```bash
# 输入单张图片时，output_dir 参数仍需要但不会创建目录
hb_eval_preprocess -m mobilenetv1 -i ./test_image.jpg -o ./output
```

### 步骤 6：确认输出

```bash
# 查看生成的 bin 文件
ls -lh ./calibration_data/

# 确认 bin 文件大小合理（应与目标 shape 的字节数匹配）
# 例如 224x224x3 uint8 = 150528 bytes
```

## 输入输出目录约定

| 项目 | 说明 |
|-----|------|
| 输入目录 | 包含 `.jpg` / `.jpeg` / `.png` 图片的目录 |
| 输入单文件 | 也可以是单张图片文件路径 |
| 输出目录 | 生成的 `.bin` 文件存放目录 |
| val_txt | 每行一个图片文件名（不含扩展名），用于过滤 |

## 输出 .bin 文件命名规则

```
{原始图片名}_{原始高}_{原始宽}_{目标高}_{目标宽}.bin
```

- `原始高/宽`：图片原始尺寸
- `目标高/宽`：模型输入尺寸（由模型对应的 data_transformer 决定）

## 校验清单

- [ ] 模型名称在支持列表中（`enable: True`）
- [ ] 输入图片目录存在且包含有效图片
- [ ] 输出目录已创建（如不存在会自动创建）
- [ ] 生成的 `.bin` 文件大小合理（与模型输入 shape 匹配）
- [ ] 日志中显示图片列表解析成功
- [ ] 日志中显示 `Successfully generated the binary file`
- [ ] numpy 版本建议为 1.23.0（非强制但建议）
- [ ] 所有图片格式为 jpg/jpeg/png

## 常见偏差与修法

| 偏差 | 修法 | 对应 troubleshooting |
|-----|------|---------------------|
| 模型名称不在支持列表 | 检查 MODEL_DICT 中 enable: True 的模型 | runtime-errors.md |
| 输入目录无有效图片 | 确认目录包含 jpg/jpeg/png 文件 | runtime-errors.md |
| bin 文件大小异常 | 确认模型对应的 data_transformer 配置正确 | runtime-errors.md |
| numpy 版本警告 | 建议使用 numpy 1.23.0 | runtime-errors.md |
| val.txt 路径不存在 | 确认 val.txt 文件路径正确 | runtime-errors.md |

## 相关工具 / 模块链接

- **hb_eval_preprocess**：评估预处理工具，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/hb_eval_preprocess.py`
- **EvalPreprocess**：核心处理类，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/eval_preprocess/eval_preprocess.py`
- **MODEL_DICT**：支持模型清单，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/eval_preprocess/conf.py`
- **data_transformer**：各模型的数据预处理函数，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/eval_preprocess/data_transformer.py`
- **dataloader**：数据加载器，源码 `/home/users/wenhao.ma/codeWKS/tc_sys/horizon_tc_ui/eval_preprocess/dataloader.py`
