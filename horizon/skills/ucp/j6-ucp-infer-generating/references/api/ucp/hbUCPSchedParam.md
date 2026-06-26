# hbUCPSchedParam

- 类别: 结构体
- 头文件: `hobot/hb_ucp.h`

## 作用
描述任务提交到 UCP 时的调度参数。

## 字段说明
- `int32_t priority`: 任务优先级。
- `int64_t customId`: 用户自定义标识。
- `uint64_t backend`: 执行硬件后端位图。
- `uint32_t deviceId`: 设备 ID。
