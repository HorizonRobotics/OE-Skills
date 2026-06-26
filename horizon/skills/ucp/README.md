# Skills

本目录包含项目的技能（skill）文件，用于辅助代码生成、问题排查和性能分析等场景。

确保 agent 正确理解了 [SKILL.md](./SKILL.md) 路由文件。正常提需求即可，无需特殊操作，当问题涉及对应场景时技能会自动加载。

## 管理路由表

路由表在 SKILL.md 中维护，添加和移除操作需要 agent 严格遵循 SKILL.md 中"注册与移除"章节的流程规范执行。用户只需描述意图即可，例如：

- 把 `ucp_interface_triage` skill注册到路由表

或

- 从路由表移除 `dsp_custom_operator` skill
