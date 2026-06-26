---
name: j6-ucp-perfetto-trace-analysis
description: Use this skill whenever the user wants to quickly locate, diagnose, or analyze likely performance bottlenecks in a UCP model inference Perfetto trace. Trigger on requests about UCP inference traces, `.pftrace` files, inference latency, slow inference, pipeline stalls, CPU/BPU gaps, OpInfer delays, dispatch or response delay, low effective occupancy, critical-path investigation, or trace-based performance triage in the UCP inference path. This skill is specialized for UCP / UCP-like inference-chain performance analysis and fast bottleneck localization, not generic Perfetto profiling unrelated to UCP inference.
version: v1.1.0
---

# UCP Perfetto Inference Analysis

**Version:** `v1.1.0`

Use this skill for **UCP model inference** Perfetto traces when the goal is to quickly find, triage, and explain likely performance issues in the inference path.

It is intentionally scoped: the skill is optimized for fast bottleneck localization inside UCP inference traces, then maps that work onto a fixed set of validated analysis directions so the output stays repeatable instead of drifting into generic Perfetto exploration.

## What this skill is for

Use this skill when the user wants to:

- analyze a UCP inference `.pftrace` / Perfetto trace
- quickly find likely bottlenecks, hotspots, or latency contributors in the UCP inference path
- investigate slow inference, critical-path delay, CPU/BPU handoff gaps, OpInfer delay, dispatch / response delay, or low effective occupancy
- run one of the validated UCP bottleneck directions in this skill
- generate the default four-direction Markdown report

Do **not** use this skill for:

- generic Perfetto profiling with no UCP inference focus
- arbitrary performance investigations outside UCP inference
- UI-only trace browsing with no SQL, filtering, or scripted analysis
- non-UCP CPU profiling or unrelated workloads

## Supported directions

These four directions are the **entire scope** of the skill’s default report workflow:

- UCP Critical Path Slice Analysis (Excluding BPU and CPU Operators)
- UCP CPU Operator Slice Analysis
- BPU flow dispatch / response delay
- Corrected BPU effective occupancy

Internal CLI values used by the bundled script:

- `all` (default report mode)
- `dnn_name`
- `opinfer_desc_flow`
- `bpu_flow_delay`
- `bpu_effective_occupancy`

Read `references/directions.md` for the exact rule definitions, thresholds, grouping semantics, and output expectations.

## Default workflow

The bundled analyzer is `scripts/analyze_trace.py`. Prefer it before writing new automation.

Default behavior:

1. Probe the trace schema and relevant argument structure.
2. Run all four validated directions.
3. Export one Markdown report.
4. Return the report path and a short completion note.
5. Stop unless the user explicitly asks for deeper follow-up analysis.

Do not proactively ask whether the user wants deeper analysis after the default report is complete.

Use single-direction mode only when the user explicitly asks for focused/manual output instead of the full report.

## Input and clarification rules

Minimum required input:

- a trace file path, or a clear way to access the trace

Ask only when the answer would materially change results inside the supported directions, for example:

- target direction is unclear
- threshold semantics are unclear
- flow-position semantics are unclear
- relevant package / process / thread / time window is necessary to scope the trace safely
- hardware-pool semantics are unclear and would change occupancy results

Do not turn intake into a checklist when the user has already specified a clear target.

## Language rule

If the desired conclusion language is not already clear, ask whether the final interpretation should be in **Chinese** or **English**.

This applies to the conclusion text. SQL, identifiers, and stable field names do not need localization unless the user explicitly asks for it.

## Execution guidance

Probe first. Do not assume `args` layout, flow shape, thread-state values, or hardware-pool semantics before checking the actual trace.

Prefer direct SQL when the rule is simple. Prefer Python `trace_processor` when the analysis needs multiple probe stages, custom interval logic, occupancy reconstruction, or reusable automation.

Keep the work inside the four supported directions. Do not invent new analysis paths unless the skill itself is being intentionally extended.

## Output contract

The default artifact is a **single Markdown report** covering all four directions.

The terminal should only provide a concise recap of what was exported.

Do not use the default completion message to prompt for extra analysis that falls outside the skill’s normal scope.

For each direction, the report should include:

- a rule description
- a grouped summary table
- an offender table when applicable
- a short conclusion paragraph
- a clear note when the direction is skipped or has no anomalies

Always include a fast `locate_sql` statement in detailed offender output.

Detailed reporting rules live in `references/output.md`.

## Verification expectations

Before finalizing analysis:

- confirm the actual `args` keys and value types used in this trace
- confirm relevant `track.name` and `flow` structure in this trace
- sanity-check representative offenders against raw timestamps and durations
- reject implausible results and re-check ownership or grouping semantics before reporting

## Reference files

- `references/setup.md` — installation, binary fallback, troubleshooting
- `references/bpu_trace_setup.md` — how to enable BPU Trace (hardware switch, config, and full workflow)
- `references/output.md` — report-first output contract and language behavior
- `references/sql_patterns.md` — reusable SQL probes and locate patterns
- `references/directions.md` — exact semantics for the four supported directions
- `scripts/analyze_trace.py` — bundled reusable analyzer

## Example invocation

```bash
python scripts/analyze_trace.py /path/to/trace.pftrace
python scripts/analyze_trace.py /path/to/trace.pftrace --analysis-direction dnn_name
python scripts/analyze_trace.py /path/to/trace.pftrace --analysis-direction opinfer_desc_flow --bottleneck-ratio-threshold 1.5 --bottleneck-diff-ms 1
python scripts/analyze_trace.py /path/to/trace.pftrace --analysis-direction bpu_flow_delay
python scripts/analyze_trace.py /path/to/trace.pftrace --analysis-direction bpu_effective_occupancy
```

## When to read bpu_trace_setup.md

Read `references/bpu_trace_setup.md` and relay its content to the user when either of these occurs:

1. **Missing BPU trace data detected during analysis** — If the `bpu_flow_delay` or `bpu_effective_occupancy` direction finds the `bpu_trace` table empty or absent, the trace file was captured without BPU trace enabled. Tell the user that BPU trace data is missing, explain that BPU trace requires separate enabling steps, and provide the setup instructions from `references/bpu_trace_setup.md` so they can recapture the trace with BPU data.

2. **User asks how to enable or capture BPU trace** — If the user asks about enabling BPU trace, how to capture BPU data, or why BPU-related analysis is unavailable, read and relay the setup guide from `references/bpu_trace_setup.md`.

Do not proactively push BPU trace setup instructions when the trace already contains valid BPU data, or when the user's question is unrelated to BPU trace collection.

## Scope boundary

The normal completion condition for this skill is:

- all four validated directions have been evaluated, or the requested supported direction has been completed
- the Markdown report has been generated when using default report mode
- the result path or focused output has been returned to the user

Further iterative investigation is outside the default contract unless the user explicitly asks for follow-up work.
