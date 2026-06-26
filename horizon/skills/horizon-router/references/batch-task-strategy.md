# 批量任务处理策略

> 从 horizon-router SKILL.md 拆出，当任务涉及多个模型（>3个）的相同操作时按需加载。

当任务涉及对 **多个模型（>3个）** 执行相同操作（批量评测、批量分析、批量编译等）时，根据当前 agent 的能力选择策略：

## 策略 A：有 Agent 工具时（主 agent）— 拆分并行

1. 扫描目录，确定模型列表和总数
2. 每 1-3 个模型分配一个独立 sub-agent，使用 `run_in_background: true` 并行启动
3. 每个 sub-agent 独立完成「执行 → 收集结果 → 写入文件」
4. 所有 sub-agent 完成后，汇总生成最终报告

> 同时并行的 sub-agent 不超过 4-6 个。模型数量 >10 时分批启动。

## 策略 B：无 Agent 工具时（sub-agent）— 脚本 + 等待通知

1. 编写一个完整的批处理脚本，脚本内部串行处理所有模型，**脚本自身负责汇总结果并生成报告文件**（如 `final_report.md` + `results.json`）
2. **脚本健壮性要求**：批处理脚本必须满足以下条件，否则不允许启动：
   - 每个样本的处理逻辑外层必须有 `try/except`，单个样本失败时记录错误并跳过，**不得中断整个批处理**
   - 脚本末尾必须有明确的完成标记（如 `log("ALL DONE")` 或写入 `done.flag` 文件）
3. **启动前 dry run**：在完整启动前，先用 1-2 个样本做最小验证：
   ```bash
   # 示例：取第一个模型测试脚本核心逻辑
   python3 -c "
   import batch_script
   result = batch_script.process_one('/path/to/first_model.hbm')
   print('dry run OK:', result)
   " 2>&1 | tail -20
   ```
   - 如果 dry run 报错，修复后重新验证，直到通过
   - 如果脚本不支持单函数调用，可以 `python3 -m py_compile batch_script.py` 做语法检查 + 用 `--max-models 1` 等参数限制范围
4. 使用 Bash 的 `run_in_background: true` 在后台启动脚本
5. **启动验证（必须做，不算轮询）**：启动后等待 5-10 秒，执行**一次性**检查确认脚本没有立即崩溃：
   ```bash
   # 检查 1: 进程是否存活
   ps aux | grep batch_script | grep -v grep
   # 检查 2: 日志是否有正常输出（非 Traceback）
   tail -5 scratch/batch_eval.log
   ```
   - 如果发现进程已退出或日志包含 `Traceback`/`Error`，**立即修复并重启**，然后重新做一次启动验证
   - 启动验证通过后，停止工作
6. **停止工作，等待系统的后台任务完成通知**——不要在等待期间执行任何进度检查命令
7. 收到通知后，读取脚本生成的报告文件，将其内容作为最终输出

> **⛔ 禁止轮询**：禁止反复执行相同或相似的 Bash 命令来检查进度（如反复 `cat results.json | wc -l`、反复 `python3 -c "import json; ..."` ）。连续 3 次相似命令会触发 API 的重复调用检测，导致 agent 崩溃。后台任务完成时系统会自动通知，你不需要主动检查。
>
> **启动验证 ≠ 轮询**：步骤 5 的一次性启动检查是**必须的**，它只执行一次，目的是确认脚本没有立即崩溃。轮询指的是反复检查进度（"处理了多少个？"），这是禁止的。
>
> **如果需要在等待期间做事**：可以做与批处理无关的工作（如写报告模板、整理目录结构），但**绝对不要检查批处理的进度**。

## 正反示例

**❌ 错误做法（会导致 agent 崩溃或产出丢失）：**
```
# 错误 1: 不验证就启动，脚本有 bug 导致全部失败
1. Write batch_script.py  # 700 行，未做 dry run
2. Bash: python3 batch_script.py  (run_in_background: true)
3. "等待完成通知"  → 脚本 6 秒后崩溃，agent 不知道

# 错误 2: 反复轮询进度
Bash: python3 -c "import json; print(len(json.load(open('results.json'))))"  # 第1次
Bash: python3 -c "import json; print(len(json.load(open('results.json'))))"  # 第2次
Bash: python3 -c "import json; print(len(json.load(open('results.json'))))"  # 第3次 → 崩溃！
```

**✅ 正确做法（sub-agent）：**
```
1. Write batch_script.py  # 包含 try/except + 完成标记
2. Bash: python3 -m py_compile batch_script.py  # 语法检查
3. Bash: python3 -c "from batch_script import process_one; process_one(first_model)"  # dry run
4. Bash: python3 batch_script.py  (run_in_background: true)
5. [等 5 秒] Bash: ps aux | grep batch_script && tail -5 scratch/batch.log  # 一次性启动验证
6. 启动正常 → 回复："脚本已在后台运行，等待完成通知。"  → 停止
7. [系统通知：后台任务完成]
8. Read: final_report.md  → 将内容作为最终输出
```
