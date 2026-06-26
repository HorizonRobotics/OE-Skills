# hbDNNTensor

- 类别: 结构体
- 头文件: `hobot/dnn/hb_dnn.h`

## 作用
封装 DNN 张量内存与属性。

## 字段说明
- `hbUCPSysMem sysMem`: 张量底层内存。
- `hbDNNTensorProperties properties`: 张量属性。

## 使用注意事项
- 内存和属性需匹配模型输入/输出要求。
