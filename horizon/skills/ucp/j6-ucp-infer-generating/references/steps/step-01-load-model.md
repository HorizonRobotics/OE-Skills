# Step 01 - 模型加载

## 涉及头文件
- `hobot/dnn/hb_dnn.h`

## 涉及 API
- `hbDNNInitializeFromFiles`
  原型: `int32_t hbDNNInitializeFromFiles(hbDNNPackedHandle_t *dnnPackedHandle, char const **modelFileNames, int32_t modelFileCount);`
  作用：从模型文件路径列表加载并初始化 DNN 打包句柄。

- `hbDNNInitializeFromDDR`
  原型: `int32_t hbDNNInitializeFromDDR(hbDNNPackedHandle_t *dnnPackedHandle, const void **modelData, int32_t *modelDataLengths, int32_t modelDataCount);`
  作用：从内存中的模型数据初始化 DNN 打包句柄。

- `hbDNNGetModelNameList`
  原型: `int32_t hbDNNGetModelNameList(char const ***modelNameList, int32_t *modelNameCount, hbDNNPackedHandle_t dnnPackedHandle);`
  作用：获取 packed handle 内模型名列表及数量。

- `hbDNNGetModelHandle`
  原型: `int32_t hbDNNGetModelHandle(hbDNNHandle_t *dnnHandle, hbDNNPackedHandle_t dnnPackedHandle, char const *modelName);`
  作用：按模型名从 packed handle 获取单模型句柄。

## 产出
- 用于模型管理的 `hbDNNPackedHandle_t` 及用于后续查询属性与推理执行的 `hbDNNHandle_t`。

## 示例代码

### 1. 加载模型文件

#### 分支 1：从模型文件加载（默认）

```cpp
hbDNNPackedHandle_t packed_handle = nullptr;
CHECK(hbDNNInitializeFromFiles(&packed_handle, model_path_ptr, model_path_count));
```

#### 分支 2：从 DDR 加载

```cpp
hbDNNPackedHandle_t packed_handle = nullptr;
CHECK(hbDNNInitializeFromDDR(&packed_handle, model_datas, model_data_lengths, model_data_count));
```

### 2. 获取模型句柄

#### 分支 1：用户指定模型名称

```cpp
hbDNNHandle_t model_handle = nullptr;
CHECK(hbDNNGetModelHandle(&model_handle, packed_handle, model_name_ptr));
```

#### 分支 2：获取模型名称列表（默认）

```cpp
int32_t model_count = 0;
const char **model_name_list = nullptr;
CHECK(hbDNNGetModelNameList(&model_name_list, &model_count, packed_handle));

hbDNNHandle_t model_handle = nullptr;
CHECK(hbDNNGetModelHandle(&model_handle, packed_handle, model_name_list[0]));
```
