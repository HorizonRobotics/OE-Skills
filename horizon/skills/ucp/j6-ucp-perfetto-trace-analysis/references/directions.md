# UCP Inference Analysis Directions

This file contains the detailed rule definitions for the four supported UCP inference bottleneck directions.

## UCP Critical Path Slice Analysis (Excluding BPU and CPU Operators)

### Question answered

Which `category='dnn'` slices remain suspicious after excluding known non-problem patterns, and what likely explains their long wall time?

### Reusable rule

1. Start from `slice` rows where `category='dnn'`.
2. Exclude invalid or zero-duration slices.
3. Exclude slice names ending with `Wait`.
4. Probe `args` first, then exclude slices whose debug arguments contain `op_type` matching `Cpu`.
5. Group the remaining slices by `slice.name`.
6. Sort by the selected duration metric, usually total or max duration.
7. Flag slices above the configured threshold. Default used in the validated workflow: `2 ms`.

### Cause attribution

If the slice is on a thread-execution track, overlap the slice interval with `thread_state` and summarize the dominant state:

- `Running` → execution itself dominates
- `R`, `R+` → runnable but waiting for CPU
- `S`, `D`, `I` → sleeping / blocked / I/O-like waiting

### Output contract

- grouped summary: `name`, `count`, `avg`, `max`, `total`, threshold hit count
- offender table: `name`, `id`, `duration`, likely cause, `locate_sql`

## UCP CPU Operator Slice Analysis

### Question answered

Which `OpInfer` slices with CPU debug type are unusually slow relative to peers at the same semantic stage?

### Reusable rule

1. Filter to `slice.name='OpInfer'`.
2. Keep only slices whose debug `op_type` matches `Cpu`.
3. Extract `task_info.desc` from the relevant debug argument.
4. Determine the slice’s position in the containing flow.
5. Group by `(task_info.desc, flow_position)`.
6. Compute the group average duration.
7. Flag slices when both conditions hold:
   - `dur / group_avg > ratio_threshold`
   - `dur - group_avg > diff_threshold`

### Validated defaults

- ratio threshold: `1.5`
- absolute difference threshold: `1 ms`

### Important semantic note

Flow position must be defined explicitly. In the validated workflow, position was derived from the full flow chain, not just the local `OpInfer` subset.

### Output contract

- summary by `(task_desc, flow_position)`
- offender table with `name`, `id`, `duration`, bottleneck rule, likely cause if available, and `locate_sql`

## BPU flow dispatch / response delay

### Question answered

For `category='bpu'` slices that belong to a flow, where are the large gaps before the hardware slice starts or after it ends?

### Reusable rule

1. Keep only `category='bpu'` slices that participate in a `flow`.
2. Confirm flow topology. If the trace is branching, do not assume one predecessor and one successor without justification.
3. For linear flows, identify the direct predecessor and successor within the same flow.
4. Compute:
   - dispatch delay = `bpu.ts - prev.end`
   - response delay = `next.ts - bpu.end`
5. Flag slices where either delay exceeds the threshold.

### Validated default threshold

- `1 ms`

### Output contract

- summary counts for dispatch, response, and either-side threshold hits
- offender table with `name`, `id`, `dur`, `dispatch_delay`, `response_delay`, `locate_sql`

## Corrected BPU effective occupancy

### Question answered

Which in-flow `category='bpu'` slices have anomalous actual hardware occupancy after correcting for serialized execution on each hardware pool?

### Critical semantic rule

Do **not** use one global BPU pool.

Different `track.name` values represent different hardware pools and must be treated as parallel. Occupancy competition happens **within each exact `track.name` bucket only**.

### Reusable rule

1. Collect all valid `category='bpu'` slices, including those not in a flow, because they still occupy the hardware pool.
2. Attach each slice to its exact `track.name`.
3. Within each `track.name` bucket, compute actual occupied time using an end-time-centric ownership rule:
   - build boundaries from all slice start and end timestamps
   - for each adjacent time segment, assign ownership to the currently active slice whose `end_ts` is earliest
4. This yields an effective occupied duration per slice for that hardware pool.
5. After occupancy is attached, keep only the in-flow slices.
6. Regroup by `(slice.name, flow_position)`.
7. Compute average and max effective occupancy per group.
8. Flag groups and slices when `max_effective / avg_effective > 1.5`.

### Important warnings

- Do not let slices from different `track.name` values compete.
- Do not present the old global-pool result as actual hardware occupancy.
- If same-track wrapper and child slices coexist and represent the same physical work at different instrumentation levels, call that out as an ambiguity before over-interpreting the result.

### Output contract

- grouped summary: `name`, `flow_position`, `slice_count`, `avg_effective_ms`, `max_effective_ms`, `max/avg`, threshold hit count
- offender table: `name`, `id`, `flow_position`, `effective_ms`, bottleneck rule, `locate_sql`
