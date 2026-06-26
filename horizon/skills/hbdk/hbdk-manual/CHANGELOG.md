# Changelog

## 2026-04-25

### 新增
- `SKILL.md` — skills导航入口，流程总览、skill列表、快速入门路径
- `model_export.md` — ONNX模型导出为HBIR（原 `onnx_export_to_hbir.md` 重命名扩展）

### 优化
- `model_serialization.md` — 补充 `Module.parse()` 用法、save会clone说明、注意事项
- `model_convert.md` — 补全March枚举表（含核数和QNX标注）、advice输出解读
- `model_compile.md` — 补充编译路径选择说明、L2M用法、CacheMode缓存示例
- `insert_nodes.md` — 修正 `insert_transpose` permutes语义说明、新增 nv12_yh12/nv12_yh10 模式、补充 bgr2rgb/rgb2bgr
- `model_info_query.md` — 补充 precision_config 和 extract_function 用法
- `model_inference.md` — 修正 remote_port 类型为 int、补充 pytree 构造示例
- `hbm_perf.md` — 修正 API 为 `hbm_perf()` 函数（当前版本 `Hbm[i].perf()` 不可用）
- `remove_io_nodes.md` / `hbm_modify.md` — 无变更，保持原样
- `references/api_reference.md` — 补全 Module/Function 属性表、PrecisionConfig、修正 hbm_perf 和 transpose 说明
- `references/workflow_reference.md` — 新增 RLE 流程、精度调优流程、编译路径选择表

### 修正
- `insert_roi_resize` 参数名 `interpolation_mode` → `interp_mode`，与实际 API 对齐
- `insert_transpose` permutes 示例修正：NCHW→NHWC 应使用 `[0,3,1,2]`
- `hbm_perf` 确认为当前正式 API（非弃用），移除 `Hbm[i].perf()` 不可用接口的文档

### 移除
- `onnx_export_to_hbir.md` — 重命名为 `model_export.md`
