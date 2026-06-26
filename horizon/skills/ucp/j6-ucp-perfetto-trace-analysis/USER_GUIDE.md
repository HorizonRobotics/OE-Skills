# UCP Inference Trace Analysis User Guide

**Version:** `v1.0.0`

**Skill name:** `ucp_perfetto_trace_analysis`

## What this skill does

This skill analyzes **UCP model inference** Perfetto traces and looks for bottlenecks using a fixed, validated workflow.

It is **not** a generic Perfetto analysis tool. It is only for the UCP inference directions bundled with this skill.

## Supported analysis directions

The default report covers these four directions:

1. **UCP Critical Path Slice Analysis (Excluding BPU and CPU Operators)**
2. **UCP CPU Operator Slice Analysis**
3. **BPU flow dispatch / response delay**
4. **Corrected BPU effective occupancy**

## What you need before running it

- Python 3
- the `perfetto` Python package
- a local Perfetto trace file such as `.pftrace`

Install the dependency with:

```bash
pip install perfetto
```

## Quick start

Run the bundled analyzer with the trace path:

```bash
python scripts/analyze_trace.py /path/to/trace.pftrace
```

By default, this runs all four supported directions and exports **one Markdown report**.

## Focused runs

If you want only one supported direction, use `--analysis-direction`:

```bash
python scripts/analyze_trace.py /path/to/trace.pftrace --analysis-direction dnn_name
python scripts/analyze_trace.py /path/to/trace.pftrace --analysis-direction opinfer_desc_flow
python scripts/analyze_trace.py /path/to/trace.pftrace --analysis-direction bpu_flow_delay
python scripts/analyze_trace.py /path/to/trace.pftrace --analysis-direction bpu_effective_occupancy
```

## Output behavior

Default behavior:

- generate one Markdown report
- include one section per supported direction
- include a rule description, summary table, offender table when applicable, and a conclusion for each direction
- print only a concise terminal recap

After the report is exported, the default workflow is considered complete.

## Conclusion language

The skill can produce the conclusion text in Chinese or English.

If the desired language is not clear from the conversation, the expected behavior is to ask which language you want for the final conclusion.

## `trace_processor_shell` behavior

The bundled analyzer uses Perfetto Python `trace_processor`, which depends on `trace_processor_shell`.

Two modes are supported:

1. **Default mode**
   - do not pass `--trace-processor-bin`
   - Perfetto Python may auto-download or auto-discover a compatible binary

2. **Explicit local-binary mode**
   - pass `--trace-processor-bin /path/to/trace_processor_shell`
   - use this when you already have a local usable binary or when automatic startup is unavailable

Example:

```bash
python scripts/analyze_trace.py /path/to/trace.pftrace --trace-processor-bin /path/to/trace_processor_shell
```

## If automatic startup fails

Recovery order:

1. First check whether you can provide a **local usable** `trace_processor_shell` path.
2. Only if you cannot provide one, use manual download guidance for your platform.

This is the intended fallback order for this skill.

## Scope boundary

This skill stops at the validated UCP inference report workflow.

It does **not** automatically expand into:

- generic Perfetto exploration
- unrelated profiling tasks
- custom new bottleneck directions outside the bundled four

## Reference files

- `SKILL.md` — skill scope and workflow
- `references/setup.md` — setup, binary fallback, troubleshooting
- `references/output.md` — report and output behavior
- `references/directions.md` — exact semantics for the four directions
- `references/sql_patterns.md` — reusable SQL patterns
