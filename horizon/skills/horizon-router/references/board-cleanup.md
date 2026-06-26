# 板端缓存清理

> 从 horizon-router SKILL.md 拆出，涉及板端部署的任务完成后按需加载。

任何涉及向开发板部署文件的任务（`scp` 上传模型、部署 `hrt_model_exec`、生成板端日志等），在**任务完成后**必须清理板端残留文件，防止磁盘空间耗尽。

## 清理步骤

```bash
# 1. 停止板端残留进程
ssh root@<BOARD_IP> "pkill -f hrt_model_exec; pkill -f hrt_ucp_monitor; pkill -f hrut_ddr; pkill -f run_at_fps"

# 2. 清理 BOARD_WORKDIR 下的部署文件和日志
ssh root@<BOARD_IP> "rm -rf ${BOARD_WORKDIR}/*.hbm ${BOARD_WORKDIR}/*.log ${BOARD_WORKDIR}/*.csv ${BOARD_WORKDIR}/*.txt ${BOARD_WORKDIR}/*.sh ${BOARD_WORKDIR}/hrt_model_exec* ${BOARD_WORKDIR}/remote_bpu*"

# 3. 清理 /tmp 下的部署残留
ssh root@<BOARD_IP> "rm -rf /tmp/remote_bpu /tmp/hrt_lib /tmp/board_inputs /tmp/board_outputs"
```

## 规则

- 清理在**数据采集完成、结果拉回本地之后**执行，不要提前清理
- 如果是批量任务（策略 A/B），在所有模型评测完毕、报告生成后再统一清理
- 清理命令失败不阻塞任务（板端可能已断连），但必须在 transcript 中记录清理状态
