# UCP Perfetto Inference Output Guide

## Default output contract

Unless the user explicitly asks otherwise, the skill should produce one Markdown report covering all four validated **UCP inference** directions.

The terminal should only provide a concise recap of what was exported.

The default report should contain, for each direction:

1. a grouped statistics table
2. an offender table
3. a short interpretation / conclusion paragraph

The terminal should not be the primary artifact in the default report-first mode.

### Focused/manual override

If the user explicitly asks for a single-direction or terminal-first run, it is acceptable to use the focused output mode instead, as long as it stays within the four supported UCP directions.

In that override mode, the analysis should output:

1. a grouped statistics table in the terminal
2. an offender table in the terminal
3. a short summary paragraph
4. a concise interpretation / conclusion paragraph

Default table length:

- top 10 grouped rows
- top 10 offender rows

Do not skip the tables and output only the conclusion unless the user explicitly asks for a conclusion-only response.

## No-anomaly behavior

If no anomalies match the current rule:

- say so explicitly
- include the active threshold or rule semantics in the message

Example:

- `No anomalous slices matched the current rule (dur >= 2.000 ms after the configured exclusions).`
- `按当前规则未发现命中异常的 slice（已应用配置中的排除条件，阈值为 dur >= 2.000 ms）。`

## Conclusion language interview

If the desired language is not already clear from the conversation, ask whether the final conclusion should be in Chinese or English.

Recommended prompts:

- `Do you want the final conclusion in Chinese or English?`
- `你希望最终结论用中文还是英文输出？`

If the user is already writing mainly in one language, prefer that language unless they say otherwise.

## Markdown export behavior

Markdown export is the default output mode for the bundled all-directions UCP workflow.

If the user explicitly wants terminal-only or focused/manual output, switch away from the default report mode.

## Markdown report contents

In the default report mode, include:

- one section per validated direction
- summary table for each direction
- offender table for each direction
- final conclusion paragraph for each direction
- clear note when a direction has no anomalies or is skipped

After the report is exported, the skill should treat the task as complete unless the user explicitly asks for deeper follow-up analysis outside this skill.

Do not proactively ask whether the user wants deeper analysis as part of the default completion message.
