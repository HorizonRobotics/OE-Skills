#!/usr/bin/env python3

from __future__ import annotations

import argparse
import heapq
import importlib
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


DEFAULT_THRESHOLD_MS = 2.0
DEFAULT_BOTTLENECK_DIFF_MS = 1.0


@dataclass
class ProbeResult:
    debug_op_type_key: str | None
    debug_op_type_flat_key: str | None
    debug_op_type_cpu_match_count: int
    has_cpu_op_type: bool
    debug_task_info_key: str | None
    debug_task_info_flat_key: str | None
    opinfer_cpu_count: int
    opinfer_cpu_desc_count: int
    candidate_debug_keys: list[dict[str, Any]]
    thread_states: list[dict[str, Any]]
    task_info_samples: list[dict[str, Any]]


@dataclass
class ReportTable:
    title: str
    headers: list[str]
    rows: list[list[Any]]


@dataclass
class DirectionReport:
    title: str
    tables: list[ReportTable]
    rule_description: str
    conclusion: str
    status: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze UCP inference Perfetto traces using the four predefined bottleneck directions bundled with this skill."
    )
    parser.add_argument("trace_path", help="Path to .pftrace file")
    parser.add_argument(
        "--min-duration-ms",
        type=float,
        default=DEFAULT_THRESHOLD_MS,
        help="Flag slices whose wall duration is >= this threshold in ms",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum detailed rows to print",
    )
    parser.add_argument(
        "--probe-only",
        action="store_true",
        help="Only inspect args/thread_state structure and stop",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format",
    )
    parser.add_argument(
        "--trace-processor-bin",
        default=None,
        help="Optional path to local trace_processor_shell binary. If omitted, Perfetto Python will auto-download or auto-discover a compatible binary.",
    )
    parser.add_argument(
        "--analysis-direction",
        choices=["all", "dnn_name", "opinfer_desc_flow", "bpu_flow_delay", "bpu_effective_occupancy"],
        default="all",
        help="Which predefined UCP inference analysis direction to run",
    )
    parser.add_argument(
        "--bottleneck-ratio-threshold",
        type=float,
        default=1.5,
        help="Flag grouped slices whose ratio to group average exceeds this threshold",
    )
    parser.add_argument(
        "--bottleneck-diff-ms",
        type=float,
        default=DEFAULT_BOTTLENECK_DIFF_MS,
        help="Flag second-direction slices only if dur - group_avg_dur also exceeds this many ms",
    )
    parser.add_argument(
        "--conclusion-language",
        choices=["auto", "zh", "en"],
        default="auto",
        help="Language for conclusion text. 'auto' infers from environment and defaults to English.",
    )
    parser.add_argument(
        "--markdown-output",
        default=None,
        help="Optional path to write a Markdown report. Terminal tables remain the default output.",
    )
    return parser.parse_args()


def ms_to_ns(value_ms: float) -> int:
    return int(round(value_ms * 1_000_000))


def row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row.__dict__)


def query_dicts(tp: Any, sql: str) -> list[dict[str, Any]]:
    return [row_to_dict(row) for row in tp.query(sql)]


def sql_quote(value: str) -> str:
    return value.replace("'", "''")


def open_trace_processor(trace_path: str, tp_bin: str) -> Any:
    trace_processor_module = importlib.import_module("perfetto.trace_processor")
    trace_processor_api_module = importlib.import_module("perfetto.trace_processor.api")
    if tp_bin:
        config = trace_processor_api_module.TraceProcessorConfig(
            bin_path=tp_bin,
            load_timeout=30,
        )
    else:
        config = trace_processor_api_module.TraceProcessorConfig(load_timeout=30)
    try:
        return trace_processor_module.TraceProcessor(trace=trace_path, config=config)
    except Exception as exc:
        if tp_bin:
            raise SystemExit(
                f"Failed to start trace_processor_shell using the provided binary path: {tp_bin}\n"
                f"Original error: {exc}\n"
                "Please verify the path, executable permission, and architecture match."
            ) from exc
        raise SystemExit(
            "Automatic startup of trace_processor_shell failed.\n"
            f"Original error: {exc}\n"
            "Next step: first ask the user whether they can provide a local usable "
            "trace_processor_shell path.\n"
            "Suggested user-facing prompt: 'Automatic startup of trace_processor_shell failed. "
            "Can you provide a local usable trace_processor_shell path?'\n"
            "Only if the user cannot provide a local usable binary, offer platform-specific "
            "download guidance and rerun with --trace-processor-bin."
        ) from exc


def probe_trace(tp: Any) -> ProbeResult:
    candidate_debug_keys = query_dicts(
        tp,
        """
        WITH dnn AS (
          SELECT id, arg_set_id
          FROM slice
          WHERE category = 'dnn' AND dur > 0
        )
        SELECT
          a.flat_key,
          a.key,
          a.value_type,
          COUNT(*) AS cnt,
          MIN(COALESCE(a.string_value, CAST(a.int_value AS TEXT), CAST(a.real_value AS TEXT))) AS sample
        FROM dnn d
        JOIN args a ON a.arg_set_id = d.arg_set_id
        WHERE lower(COALESCE(a.key, '')) LIKE '%debug%'
           OR lower(COALESCE(a.flat_key, '')) LIKE '%debug%'
           OR lower(COALESCE(a.key, '')) LIKE '%op_type%'
           OR lower(COALESCE(a.flat_key, '')) LIKE '%op_type%'
        GROUP BY 1, 2, 3
        ORDER BY cnt DESC, a.flat_key, a.key
        LIMIT 100
        """,
    )
    thread_states = query_dicts(
        tp,
        """
        SELECT state, COUNT(*) AS cnt
        FROM thread_state
        GROUP BY state
        ORDER BY cnt DESC, state
        """,
    )
    debug_op_type_matches = query_dicts(
        tp,
        """
        WITH dnn AS (
          SELECT id, arg_set_id
          FROM slice
          WHERE category = 'dnn' AND dur > 0
        )
        SELECT
          a.flat_key,
          a.key,
          COUNT(*) AS cpu_match_count
        FROM dnn d
        JOIN args a ON a.arg_set_id = d.arg_set_id
        WHERE lower(COALESCE(a.flat_key, '')) = 'debug.op_type'
          AND lower(COALESCE(a.string_value, '')) LIKE '%cpu%'
        GROUP BY 1, 2
        ORDER BY cpu_match_count DESC
        """,
    )
    task_info_rows = query_dicts(
        tp,
        """
        SELECT a.flat_key, a.key, COUNT(*) AS cnt
        FROM slice s
        JOIN args a ON a.arg_set_id = s.arg_set_id
        WHERE s.name = 'OpInfer'
          AND EXISTS (
            SELECT 1
            FROM args op
            WHERE op.arg_set_id = s.arg_set_id
              AND lower(COALESCE(op.flat_key, '')) = 'debug.op_type'
              AND lower(COALESCE(op.string_value, '')) LIKE '%cpu%'
          )
          AND lower(COALESCE(a.flat_key, '')) = 'debug.task_info'
        GROUP BY 1, 2
        ORDER BY cnt DESC
        """,
    )
    task_info_samples = query_dicts(
        tp,
        """
        SELECT
          json_extract(a.string_value, '$.desc') AS task_desc,
          COUNT(*) AS cnt,
          MIN(a.string_value) AS sample
        FROM slice s
        JOIN args op ON op.arg_set_id = s.arg_set_id
        JOIN args a ON a.arg_set_id = s.arg_set_id
        WHERE s.name = 'OpInfer'
          AND lower(COALESCE(op.flat_key, '')) = 'debug.op_type'
          AND lower(COALESCE(op.string_value, '')) LIKE '%cpu%'
          AND lower(COALESCE(a.flat_key, '')) = 'debug.task_info'
        GROUP BY 1
        ORDER BY cnt DESC, task_desc
        """,
    )
    opinfer_cpu_count = query_dicts(
        tp,
        """
        SELECT COUNT(DISTINCT s.id) AS cnt
        FROM slice s
        JOIN args op ON op.arg_set_id = s.arg_set_id
        WHERE s.name = 'OpInfer'
          AND lower(COALESCE(op.flat_key, '')) = 'debug.op_type'
          AND lower(COALESCE(op.string_value, '')) LIKE '%cpu%'
        """,
    )[0]["cnt"]
    opinfer_cpu_desc_count = query_dicts(
        tp,
        """
        SELECT COUNT(DISTINCT s.id) AS cnt
        FROM slice s
        JOIN args op ON op.arg_set_id = s.arg_set_id
        JOIN args ti ON ti.arg_set_id = s.arg_set_id
        WHERE s.name = 'OpInfer'
          AND lower(COALESCE(op.flat_key, '')) = 'debug.op_type'
          AND lower(COALESCE(op.string_value, '')) LIKE '%cpu%'
          AND lower(COALESCE(ti.flat_key, '')) = 'debug.task_info'
          AND json_extract(ti.string_value, '$.desc') IS NOT NULL
        """,
    )[0]["cnt"]

    debug_op_type_key_exists = query_dicts(
        tp,
        """
        WITH dnn AS (
          SELECT id, arg_set_id
          FROM slice
          WHERE category = 'dnn' AND dur > 0
        )
        SELECT
          a.flat_key,
          a.key,
          COUNT(*) AS cnt
        FROM dnn d
        JOIN args a ON a.arg_set_id = d.arg_set_id
        WHERE lower(COALESCE(a.flat_key, '')) = 'debug.op_type'
        GROUP BY 1, 2
        ORDER BY cnt DESC
        LIMIT 1
        """,
    )
    any_op_type_entry = debug_op_type_key_exists[0] if debug_op_type_key_exists else None
    selected = debug_op_type_matches[0] if debug_op_type_matches else None
    selected_task_info = task_info_rows[0] if task_info_rows else None
    has_cpu_op_type = int(selected["cpu_match_count"]) > 0 if selected else False
    # Prefer the CPU-matching entry for backward compatibility; fall back to the
    # any-existence entry so that direction 1 SQL can still use the key when
    # there are no CPU operators but the key exists in the trace.
    resolved_op_type_key = selected if selected else any_op_type_entry
    return ProbeResult(
        debug_op_type_key=resolved_op_type_key["key"] if resolved_op_type_key else None,
        debug_op_type_flat_key=resolved_op_type_key["flat_key"] if resolved_op_type_key else None,
        debug_op_type_cpu_match_count=int(selected["cpu_match_count"]) if selected else 0,
        has_cpu_op_type=has_cpu_op_type,
        debug_task_info_key=selected_task_info["key"] if selected_task_info else None,
        debug_task_info_flat_key=selected_task_info["flat_key"] if selected_task_info else None,
        opinfer_cpu_count=int(opinfer_cpu_count),
        opinfer_cpu_desc_count=int(opinfer_cpu_desc_count),
        candidate_debug_keys=candidate_debug_keys,
        thread_states=thread_states,
        task_info_samples=task_info_samples,
    )


def build_slow_slice_sql(threshold_ns: int, debug_op_type_flat_key: str | None, limit: int, has_cpu_op_type: bool = True) -> str:
    cpu_exclude_clause = ""
    if debug_op_type_flat_key and has_cpu_op_type:
        debug_key = sql_quote(debug_op_type_flat_key)
        cpu_exclude_clause = f"""
        AND NOT EXISTS (
          SELECT 1
          FROM args a
          WHERE a.arg_set_id = s.arg_set_id
            AND lower(COALESCE(a.flat_key, '')) = lower('{debug_key}')
            AND lower(COALESCE(a.string_value, '')) LIKE '%cpu%'
        )"""
    return f"""
    WITH filtered AS (
      SELECT s.id, s.name, s.ts, s.dur, s.track_id, s.arg_set_id
      FROM slice s
      WHERE s.category = 'dnn'
        AND s.name IS NOT NULL
        AND s.dur IS NOT NULL
        AND s.dur > 0
        AND substr(s.name, -4) <> 'Wait'
        {cpu_exclude_clause}
    ),
    slow AS (
      SELECT *
      FROM filtered
      WHERE dur >= {threshold_ns}
    ),
    thread_mapped AS (
      SELECT slow.*, tt.utid
      FROM slow
      LEFT JOIN thread_track tt ON tt.id = slow.track_id
    ),
    state_overlap AS (
      SELECT
        tm.id,
        ts.state,
        ts.io_wait,
        ts.blocked_function,
        SUM(MIN(tm.ts + tm.dur, ts.ts + ts.dur) - MAX(tm.ts, ts.ts)) AS overlap_dur
      FROM thread_mapped tm
      JOIN thread_state ts ON ts.utid = tm.utid
      WHERE tm.utid IS NOT NULL
        AND ts.dur > 0
        AND ts.ts < tm.ts + tm.dur
        AND tm.ts < ts.ts + ts.dur
      GROUP BY tm.id, ts.state, ts.io_wait, ts.blocked_function
    ),
    ranked_cause AS (
      SELECT id, state, io_wait, blocked_function, overlap_dur,
        ROW_NUMBER() OVER (PARTITION BY id ORDER BY overlap_dur DESC, state ASC) AS rn
      FROM state_overlap
    )
    SELECT
      tm.name,
      tm.id,
      tm.ts,
      tm.dur,
      tm.track_id,
      tm.utid,
      rc.state AS dominant_state,
      rc.io_wait,
      rc.blocked_function,
      rc.overlap_dur,
      'SELECT s.*, a.key, a.flat_key, a.string_value, a.int_value, a.real_value FROM slice s LEFT JOIN args a ON a.arg_set_id = s.arg_set_id WHERE s.id = ' || tm.id || ' ORDER BY a.flat_key, a.key;' AS locate_sql
    FROM thread_mapped tm
    LEFT JOIN ranked_cause rc ON rc.id = tm.id AND rc.rn = 1
    ORDER BY tm.dur DESC, tm.id ASC
    LIMIT {int(limit)}
    """


def build_summary_sql(debug_op_type_flat_key: str | None, threshold_ns: int, has_cpu_op_type: bool = True) -> str:
    cpu_exclude_clause = ""
    if debug_op_type_flat_key and has_cpu_op_type:
        debug_key = sql_quote(debug_op_type_flat_key)
        cpu_exclude_clause = f"""
        AND NOT EXISTS (
          SELECT 1
          FROM args a
          WHERE a.arg_set_id = s.arg_set_id
            AND lower(COALESCE(a.flat_key, '')) = lower('{debug_key}')
            AND lower(COALESCE(a.string_value, '')) LIKE '%cpu%'
        )"""
    return f"""
    WITH filtered AS (
      SELECT s.id, s.name, s.dur
      FROM slice s
      WHERE s.category = 'dnn'
        AND s.name IS NOT NULL
        AND s.dur IS NOT NULL
        AND s.dur > 0
        AND substr(s.name, -4) <> 'Wait'
        {cpu_exclude_clause}
    )
    SELECT name,
           COUNT(*) AS slice_count,
           SUM(CASE WHEN dur >= {threshold_ns} THEN 1 ELSE 0 END) AS over_threshold_count,
           SUM(dur) AS total_dur_ns,
           AVG(dur) AS avg_dur_ns,
           MAX(dur) AS max_dur_ns
    FROM filtered
    GROUP BY name
    HAVING over_threshold_count > 0
    ORDER BY total_dur_ns DESC, max_dur_ns DESC, name ASC
    """


def build_opinfer_desc_flow_ctes(debug_op_type_flat_key: str, debug_task_info_flat_key: str) -> str:
    op_key = sql_quote(debug_op_type_flat_key)
    task_info_key = sql_quote(debug_task_info_flat_key)
    return f"""
    WITH op AS (
      SELECT s.id, s.name, s.ts, s.dur, s.track_id, s.arg_set_id
      FROM slice s
      JOIN args op ON op.arg_set_id = s.arg_set_id
      WHERE s.name = 'OpInfer'
        AND s.dur IS NOT NULL
        AND s.dur > 0
        AND lower(COALESCE(op.flat_key, '')) = lower('{op_key}')
        AND lower(COALESCE(op.string_value, '')) LIKE '%cpu%'
      GROUP BY s.id
    ),
    op_task AS (
      SELECT o.id,
             json_extract(ti.string_value, '$.desc') AS task_desc,
             ti.string_value AS task_info_json
      FROM op o
      LEFT JOIN args ti
        ON ti.arg_set_id = o.arg_set_id
       AND lower(COALESCE(ti.flat_key, '')) = lower('{task_info_key}')
    ),
    e AS (
      SELECT trace_id, slice_out, slice_in
      FROM flow
      WHERE slice_out != slice_in
    ),
    deg AS (
      SELECT trace_id, slice_id, SUM(in_deg) AS in_deg, SUM(out_deg) AS out_deg
      FROM (
        SELECT trace_id, slice_in AS slice_id, COUNT(*) AS in_deg, 0 AS out_deg FROM e GROUP BY trace_id, slice_in
        UNION ALL
        SELECT trace_id, slice_out AS slice_id, 0 AS in_deg, COUNT(*) AS out_deg FROM e GROUP BY trace_id, slice_out
      )
      GROUP BY trace_id, slice_id
    ),
    roots AS (
      SELECT trace_id, slice_id AS root_slice
      FROM deg
      WHERE in_deg = 0
    ),
    walk(trace_id, slice_id, flow_position) AS (
      SELECT r.trace_id, r.root_slice, 0
      FROM roots r
      UNION ALL
      SELECT e.trace_id, e.slice_in, w.flow_position + 1
      FROM walk w
      JOIN e ON e.trace_id = w.trace_id AND e.slice_out = w.slice_id
    ),
    pos AS (
      SELECT trace_id, slice_id, MIN(flow_position) AS flow_position
      FROM walk
      GROUP BY trace_id, slice_id
    ),
    op_flow AS (
      SELECT DISTINCT o.id, f.trace_id AS flow_id
      FROM op o
      JOIN flow f ON f.slice_out = o.id OR f.slice_in = o.id
    ),
    resolved AS (
      SELECT o.id, o.name, o.ts, o.dur, o.track_id, o.arg_set_id,
             of.flow_id, p.flow_position, ot.task_desc, ot.task_info_json
      FROM op o
      JOIN op_flow of ON of.id = o.id
      JOIN pos p ON p.trace_id = of.flow_id AND p.slice_id = o.id
      LEFT JOIN op_task ot ON ot.id = o.id
      WHERE ot.task_desc IS NOT NULL
    )
    """


def build_opinfer_desc_flow_summary_sql(debug_op_type_flat_key: str, debug_task_info_flat_key: str) -> str:
    return build_opinfer_desc_flow_ctes(debug_op_type_flat_key, debug_task_info_flat_key) + """
    SELECT task_desc,
           flow_position,
           COUNT(*) AS slice_count,
           AVG(dur) AS avg_dur_ns,
           MAX(dur) AS max_dur_ns,
           SUM(dur) AS total_dur_ns
    FROM resolved
    GROUP BY task_desc, flow_position
    ORDER BY task_desc ASC, flow_position ASC
    """


def build_opinfer_desc_flow_bottleneck_sql(
    debug_op_type_flat_key: str,
    debug_task_info_flat_key: str,
    ratio_threshold: float,
    diff_threshold_ns: int,
    limit: int,
) -> str:
    return build_opinfer_desc_flow_ctes(debug_op_type_flat_key, debug_task_info_flat_key) + f"""
    , grouped AS (
      SELECT task_desc,
             flow_position,
             COUNT(*) AS group_n,
             AVG(dur) AS group_avg_dur_ns
      FROM resolved
      GROUP BY task_desc, flow_position
    ),
    bottlenecks AS (
      SELECT r.id, r.name, r.ts, r.dur, r.track_id, r.arg_set_id, r.flow_id, r.flow_position,
             r.task_desc, g.group_n, g.group_avg_dur_ns,
             CAST(r.dur AS FLOAT) / g.group_avg_dur_ns AS dur_ratio
      FROM resolved r
      JOIN grouped g ON g.task_desc = r.task_desc AND g.flow_position = r.flow_position
      WHERE g.group_avg_dur_ns > 0
        AND (r.dur - g.group_avg_dur_ns) > {int(diff_threshold_ns)}
        AND CAST(r.dur AS FLOAT) / g.group_avg_dur_ns > {float(ratio_threshold)}
    ),
    thread_mapped AS (
      SELECT b.*, tt.utid
      FROM bottlenecks b
      LEFT JOIN thread_track tt ON tt.id = b.track_id
    ),
    state_overlap AS (
      SELECT tm.id, ts.state, ts.io_wait, ts.blocked_function,
             SUM(MIN(tm.ts + tm.dur, ts.ts + ts.dur) - MAX(tm.ts, ts.ts)) AS overlap_dur
      FROM thread_mapped tm
      JOIN thread_state ts ON ts.utid = tm.utid
      WHERE tm.utid IS NOT NULL
        AND ts.dur > 0
        AND ts.ts < tm.ts + tm.dur
        AND tm.ts < ts.ts + ts.dur
      GROUP BY tm.id, ts.state, ts.io_wait, ts.blocked_function
    ),
    ranked_cause AS (
      SELECT id, state, io_wait, blocked_function, overlap_dur,
             ROW_NUMBER() OVER (PARTITION BY id ORDER BY overlap_dur DESC, state ASC) AS rn
      FROM state_overlap
    )
    SELECT tm.name, tm.id, tm.ts, tm.dur, tm.flow_id, tm.flow_position, tm.task_desc,
           tm.group_n, tm.group_avg_dur_ns, tm.dur_ratio, tm.track_id, tm.utid,
           rc.state AS dominant_state, rc.io_wait, rc.blocked_function, rc.overlap_dur,
           'dur / avg(task_desc, flow_position) > {float(ratio_threshold):.3f} AND dur - avg(task_desc, flow_position) > {diff_threshold_ns / 1_000_000:.3f}ms' AS bottleneck_rule,
           'SELECT s.*, a.key, a.flat_key, a.string_value, a.int_value, a.real_value FROM slice s LEFT JOIN args a ON a.arg_set_id = s.arg_set_id WHERE s.id = ' || tm.id || ' ORDER BY a.flat_key, a.key;' AS locate_sql
    FROM thread_mapped tm
    LEFT JOIN ranked_cause rc ON rc.id = tm.id AND rc.rn = 1
    ORDER BY tm.dur_ratio DESC, tm.dur DESC, tm.id ASC
    LIMIT {int(limit)}
    """


def build_bpu_flow_delay_ctes() -> str:
    return """
    WITH e AS (
      SELECT trace_id, slice_out, slice_in
      FROM flow
      WHERE slice_out != slice_in
    ),
    deg AS (
      SELECT trace_id, slice_id, SUM(in_deg) AS in_deg, SUM(out_deg) AS out_deg
      FROM (
        SELECT trace_id, slice_in AS slice_id, COUNT(*) AS in_deg, 0 AS out_deg FROM e GROUP BY trace_id, slice_in
        UNION ALL
        SELECT trace_id, slice_out AS slice_id, 0 AS in_deg, COUNT(*) AS out_deg FROM e GROUP BY trace_id, slice_out
      )
      GROUP BY trace_id, slice_id
    ),
    roots AS (
      SELECT trace_id, slice_id AS root_slice
      FROM deg
      WHERE in_deg = 0
    ),
    walk(trace_id, slice_id, flow_position) AS (
      SELECT trace_id, root_slice, 0
      FROM roots
      UNION ALL
      SELECT e.trace_id, e.slice_in, w.flow_position + 1
      FROM walk w
      JOIN e ON e.trace_id = w.trace_id AND e.slice_out = w.slice_id
    ),
    pos AS (
      SELECT trace_id, slice_id, MIN(flow_position) AS flow_position
      FROM walk
      GROUP BY trace_id, slice_id
    ),
    bpu_flow AS (
      SELECT DISTINCT s.id AS bpu_id, s.name AS bpu_name, s.ts AS bpu_ts, s.dur AS bpu_dur,
             s.track_id, s.arg_set_id, e.trace_id AS flow_id
      FROM slice s
      JOIN e ON e.slice_out = s.id OR e.slice_in = s.id
      WHERE s.category = 'bpu' AND s.dur IS NOT NULL AND s.dur > 0
    ),
    prev_edge AS (
      SELECT trace_id, slice_in AS bpu_id, slice_out AS prev_id
      FROM e
    ),
    next_edge AS (
      SELECT trace_id, slice_out AS bpu_id, slice_in AS next_id
      FROM e
    ),
    joined AS (
      SELECT b.flow_id, p.flow_position, b.bpu_id, b.bpu_name, b.bpu_ts, b.bpu_dur,
             b.track_id, b.arg_set_id, pe.prev_id, ne.next_id
      FROM bpu_flow b
      LEFT JOIN pos p ON p.trace_id = b.flow_id AND p.slice_id = b.bpu_id
      LEFT JOIN prev_edge pe ON pe.trace_id = b.flow_id AND pe.bpu_id = b.bpu_id
      LEFT JOIN next_edge ne ON ne.trace_id = b.flow_id AND ne.bpu_id = b.bpu_id
    ),
    metrics AS (
      SELECT j.flow_id, j.flow_position, j.bpu_id, j.bpu_name, j.bpu_ts, j.bpu_dur, j.track_id, j.arg_set_id,
             j.prev_id, sp.name AS prev_name, sp.category AS prev_category,
             j.next_id, sn.name AS next_name, sn.category AS next_category,
             (j.bpu_ts - (sp.ts + sp.dur)) AS prev_to_bpu_delay_ns,
             (sn.ts - (j.bpu_ts + j.bpu_dur)) AS bpu_to_next_delay_ns,
             'SELECT s.*, a.key, a.flat_key, a.string_value, a.int_value, a.real_value FROM slice s LEFT JOIN args a ON a.arg_set_id = s.arg_set_id WHERE s.id = ' || j.bpu_id || ' ORDER BY a.flat_key, a.key;' AS locate_sql
      FROM joined j
      LEFT JOIN slice sp ON sp.id = j.prev_id
      LEFT JOIN slice sn ON sn.id = j.next_id
    )
    """


def build_bpu_flow_delay_summary_sql(delay_threshold_ns: int) -> str:
    return build_bpu_flow_delay_ctes() + f"""
    SELECT COUNT(*) AS in_flow_bpu_count,
           SUM(CASE WHEN prev_to_bpu_delay_ns > {int(delay_threshold_ns)} THEN 1 ELSE 0 END) AS dispatch_over_threshold_count,
           SUM(CASE WHEN bpu_to_next_delay_ns > {int(delay_threshold_ns)} THEN 1 ELSE 0 END) AS response_over_threshold_count,
           SUM(CASE WHEN prev_to_bpu_delay_ns > {int(delay_threshold_ns)} OR bpu_to_next_delay_ns > {int(delay_threshold_ns)} THEN 1 ELSE 0 END) AS either_over_threshold_count,
           MAX(prev_to_bpu_delay_ns) AS max_dispatch_delay_ns,
           MAX(bpu_to_next_delay_ns) AS max_response_delay_ns
    FROM metrics
    """


def build_bpu_flow_delay_detail_sql(delay_threshold_ns: int, limit: int) -> str:
    return build_bpu_flow_delay_ctes() + f"""
    SELECT flow_id, flow_position, bpu_id AS id, bpu_name AS name, bpu_dur AS dur,
           prev_id, prev_name, prev_category, next_id, next_name, next_category,
           prev_to_bpu_delay_ns, bpu_to_next_delay_ns, locate_sql
    FROM metrics
    WHERE prev_to_bpu_delay_ns > {int(delay_threshold_ns)}
       OR bpu_to_next_delay_ns > {int(delay_threshold_ns)}
    ORDER BY CASE
               WHEN prev_to_bpu_delay_ns IS NULL THEN bpu_to_next_delay_ns
               WHEN bpu_to_next_delay_ns IS NULL THEN prev_to_bpu_delay_ns
               WHEN prev_to_bpu_delay_ns > bpu_to_next_delay_ns THEN prev_to_bpu_delay_ns
               ELSE bpu_to_next_delay_ns
             END DESC,
             id ASC
    LIMIT {int(limit)}
    """


def build_bpu_effective_occupancy_input_sql() -> str:
    return """
    WITH e AS (
      SELECT trace_id, slice_out, slice_in
      FROM flow
      WHERE slice_out != slice_in
    ),
    deg AS (
      SELECT trace_id, slice_id, SUM(in_deg) AS in_deg, SUM(out_deg) AS out_deg
      FROM (
        SELECT trace_id, slice_in AS slice_id, COUNT(*) AS in_deg, 0 AS out_deg FROM e GROUP BY trace_id, slice_in
        UNION ALL
        SELECT trace_id, slice_out AS slice_id, 0 AS in_deg, COUNT(*) AS out_deg FROM e GROUP BY trace_id, slice_out
      )
      GROUP BY trace_id, slice_id
    ),
    roots AS (
      SELECT trace_id, slice_id AS root_slice
      FROM deg
      WHERE in_deg = 0
    ),
    walk(trace_id, slice_id, flow_position) AS (
      SELECT trace_id, root_slice, 0
      FROM roots
      UNION ALL
      SELECT e.trace_id, e.slice_in, w.flow_position + 1
      FROM walk w
      JOIN e ON e.trace_id = w.trace_id AND e.slice_out = w.slice_id
    ),
    pos AS (
      SELECT trace_id, slice_id, MIN(flow_position) AS flow_position
      FROM walk
      GROUP BY trace_id, slice_id
    ),
    flow_member AS (
      SELECT DISTINCT s.id AS slice_id, e.trace_id AS flow_id
      FROM slice s
      JOIN e ON e.slice_out = s.id OR e.slice_in = s.id
      WHERE s.category = 'bpu' AND s.dur IS NOT NULL AND s.dur > 0
    )
    SELECT s.id, s.name, s.ts, s.dur, s.ts + s.dur AS end_ts,
           s.track_id, tr.name AS track_name, fm.flow_id, p.flow_position,
           CASE WHEN fm.flow_id IS NOT NULL THEN 1 ELSE 0 END AS in_flow,
           'SELECT s.*, a.key, a.flat_key, a.string_value, a.int_value, a.real_value FROM slice s LEFT JOIN args a ON a.arg_set_id = s.arg_set_id WHERE s.id = ' || s.id || ' ORDER BY a.flat_key, a.key;' AS locate_sql
    FROM slice s
    LEFT JOIN track tr ON tr.id = s.track_id
    LEFT JOIN flow_member fm ON fm.slice_id = s.id
    LEFT JOIN pos p ON p.trace_id = fm.flow_id AND p.slice_id = s.id
    WHERE s.category = 'bpu' AND s.dur IS NOT NULL AND s.dur > 0
    ORDER BY s.ts ASC, s.id ASC
    """


def classify_cause(row: dict[str, Any]) -> str:
    utid = row.get("utid")
    state = row.get("dominant_state")
    blocked_function = row.get("blocked_function")
    io_wait = row.get("io_wait")
    if utid is None:
        return "No thread mapping"
    if state is None:
        return "No thread_state overlap"
    if state == "Running":
        return "Running: CPU execution dominates"
    if state in {"R", "R+"}:
        return f"Runnable: waiting for CPU ({state})"
    if state in {"S", "D", "I"}:
        detail = blocked_function or ("io_wait" if io_wait else None)
        if detail:
            return f"Blocked/sleeping: {state} ({detail})"
        return f"Blocked/sleeping: {state}"
    return f"Mixed/other scheduling state: {state}"


def ns_to_ms_str(ns_value: Any) -> str:
    if ns_value is None:
        return "-"
    return f"{float(ns_value) / 1_000_000:.3f}"


def ns_to_ms_float(ns_value: Any) -> float:
    if ns_value is None:
        return 0.0
    return float(ns_value) / 1_000_000


def resolve_conclusion_language(language: str) -> str:
    if language in {"zh", "en"}:
        return language
    lang_env = (
        importlib.import_module("os").environ.get("LC_ALL")
        or importlib.import_module("os").environ.get("LANG")
        or ""
    ).lower()
    if "zh" in lang_env:
        return "zh"
    return "en"


def print_table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> None:
    normalized = [[str(cell) for cell in row] for row in rows]
    widths = [len(header) for header in headers]
    for row in normalized:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(cell))
    header_line = " | ".join(header.ljust(widths[idx]) for idx, header in enumerate(headers))
    sep_line = "-+-".join("-" * widths[idx] for idx in range(len(headers)))
    print(header_line)
    print(sep_line)
    for row in normalized:
        print(" | ".join(cell.ljust(widths[idx]) for idx, cell in enumerate(row)))


def build_markdown_table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    normalized = [[str(cell) for cell in row] for row in rows]
    header_line = "| " + " | ".join(headers) + " |"
    sep_line = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in normalized]
    return "\n".join([header_line, sep_line, *body])


def write_markdown_report(path: str, sections: list[tuple[str, str]]) -> None:
    content_parts = []
    for title, body in sections:
        content_parts.append(f"## {title}\n\n{body}".rstrip())
    Path(path).write_text("\n\n".join(content_parts) + "\n", encoding="utf-8")


def default_markdown_output_path(trace_path: Path) -> str:
    return str(trace_path.with_name(f"{trace_path.stem}_perfetto_report.md"))


def compute_effective_occupancy(slice_rows: list[dict[str, Any]]) -> tuple[dict[int, int], int]:
    starts_by_ts: dict[int, list[dict[str, Any]]] = defaultdict(list)
    boundaries: set[int] = set()
    for row in slice_rows:
        ts = int(row["ts"])
        end_ts = int(row["end_ts"])
        starts_by_ts[ts].append(row)
        boundaries.add(ts)
        boundaries.add(end_ts)

    sorted_boundaries = sorted(boundaries)
    active_heap: list[tuple[int, int]] = []
    active_rows: dict[int, dict[str, Any]] = {}
    effective_ns: dict[int, int] = defaultdict(int)
    total_busy_ns = 0

    for idx, current_ts in enumerate(sorted_boundaries[:-1]):
        while active_heap and active_heap[0][0] <= current_ts:
            _, slice_id = heapq.heappop(active_heap)
            active_rows.pop(slice_id, None)

        for row in starts_by_ts.get(current_ts, []):
            slice_id = int(row["id"])
            active_rows[slice_id] = row
            heapq.heappush(active_heap, (int(row["end_ts"]), slice_id))

        next_ts = sorted_boundaries[idx + 1]
        if next_ts <= current_ts or not active_rows:
            continue

        while active_heap and active_heap[0][1] not in active_rows:
            heapq.heappop(active_heap)

        if not active_heap:
            continue

        segment_ns = next_ts - current_ts
        owner_id = active_heap[0][1]
        effective_ns[owner_id] += segment_ns
        total_busy_ns += segment_ns

    return dict(effective_ns), total_busy_ns


def analyze_bpu_effective_occupancy(slice_rows: list[dict[str, Any]], ratio_threshold: float) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    effective_ns_by_id: dict[int, int] = {}
    total_busy_ns = 0
    rows_by_track_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in slice_rows:
        track_name = str(row.get("track_name") or f"track_id:{row.get('track_id')}")
        rows_by_track_name[track_name].append(row)

    for track_rows in rows_by_track_name.values():
        track_effective_ns_by_id, track_busy_ns = compute_effective_occupancy(track_rows)
        total_busy_ns += track_busy_ns
        for slice_id, effective_ns in track_effective_ns_by_id.items():
            effective_ns_by_id[slice_id] = effective_ns_by_id.get(slice_id, 0) + effective_ns

    flow_rows = [row for row in slice_rows if int(row.get("in_flow", 0)) == 1 and row.get("flow_position") is not None]

    groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in flow_rows:
        row_copy = dict(row)
        row_copy["effective_dur_ns"] = int(effective_ns_by_id.get(int(row["id"]), 0))
        groups[(str(row_copy["name"]), int(row_copy["flow_position"]))].append(row_copy)

    summary_rows: list[dict[str, Any]] = []
    offenders: list[dict[str, Any]] = []
    for (name, flow_position), rows in groups.items():
        effective_values = [int(row["effective_dur_ns"]) for row in rows]
        total_effective_ns = sum(effective_values)
        avg_effective_ns = total_effective_ns / len(rows)
        max_effective_ns = max(effective_values)
        group_ratio = (max_effective_ns / avg_effective_ns) if avg_effective_ns > 0 else None
        over_threshold_count = 0
        for row in rows:
            effective_ns = int(row["effective_dur_ns"])
            ratio = (effective_ns / avg_effective_ns) if avg_effective_ns > 0 else None
            if ratio is not None and ratio > ratio_threshold:
                over_threshold_count += 1
                offenders.append(
                    {
                        "name": row["name"],
                        "id": row["id"],
                        "flow_position": flow_position,
                        "effective_dur_ns": effective_ns,
                        "group_avg_effective_ns": avg_effective_ns,
                        "group_max_effective_ns": max_effective_ns,
                        "effective_ratio": ratio,
                        "bottleneck_rule": f"effective_bpu_time / avg(name, flow_position) > {ratio_threshold:.3f}",
                        "locate_sql": row["locate_sql"],
                    }
                )
        summary_rows.append(
            {
                "name": name,
                "flow_position": flow_position,
                "slice_count": len(rows),
                "avg_effective_ns": avg_effective_ns,
                "max_effective_ns": max_effective_ns,
                "group_ratio": group_ratio,
                "over_threshold_count": over_threshold_count,
            }
        )

    summary_rows.sort(
        key=lambda row: (
            row["group_ratio"] if row["group_ratio"] is not None else -1,
            row["max_effective_ns"],
            row["slice_count"],
        ),
        reverse=True,
    )
    offenders.sort(
        key=lambda row: (row["effective_ratio"], row["effective_dur_ns"], int(row["id"])),
        reverse=True,
    )

    summary = {
        "candidate_bpu_count": len(slice_rows),
        "in_flow_bpu_count": len(flow_rows),
        "assigned_total_busy_ns": total_busy_ns,
        "flagged_group_count": sum(1 for row in summary_rows if row["group_ratio"] is not None and row["group_ratio"] > ratio_threshold),
        "offender_count": len(offenders),
    }
    return summary, summary_rows, offenders


def output_probe(probe: ProbeResult, fmt: str) -> None:
    payload = {
        "resolved_debug_op_type": {
            "flat_key": probe.debug_op_type_flat_key,
            "key": probe.debug_op_type_key,
            "cpu_match_count": probe.debug_op_type_cpu_match_count,
            "has_cpu_op_type": probe.has_cpu_op_type,
        },
        "resolved_debug_task_info": {
            "flat_key": probe.debug_task_info_flat_key,
            "key": probe.debug_task_info_key,
        },
        "opinfer_cpu_count": probe.opinfer_cpu_count,
        "opinfer_cpu_desc_count": probe.opinfer_cpu_desc_count,
        "candidate_debug_keys": probe.candidate_debug_keys,
        "thread_states": probe.thread_states,
        "task_info_samples": probe.task_info_samples,
    }
    if fmt == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    print("[Probe] debug/op_type candidate keys")
    print_table(
        ["flat_key", "key", "value_type", "cnt", "sample"],
        [[row.get("flat_key"), row.get("key"), row.get("value_type"), row.get("cnt"), row.get("sample")] for row in probe.candidate_debug_keys],
    )
    print()
    print("[Probe] thread_state values")
    print_table(["state", "cnt"], [[row.get("state"), row.get("cnt")] for row in probe.thread_states])
    print()
    print("[Probe] resolved debug op_type filter")
    print(f"flat_key={probe.debug_op_type_flat_key!r}, key={probe.debug_op_type_key!r}, cpu_match_count={probe.debug_op_type_cpu_match_count}, has_cpu_op_type={probe.has_cpu_op_type}")
    print(f"[Probe] resolved debug task_info key flat_key={probe.debug_task_info_flat_key!r}, key={probe.debug_task_info_key!r}")
    print(f"[Probe] UCP CPU Operator Slice Analysis candidates={probe.opinfer_cpu_count}, with desc={probe.opinfer_cpu_desc_count}")
    if probe.task_info_samples:
        print()
        print("[Probe] task_info desc samples")
        print_table(["task_desc", "cnt", "sample"], [[row.get("task_desc"), row.get("cnt"), row.get("sample")] for row in probe.task_info_samples])


def build_dnn_direction_report(summary_rows: list[dict[str, Any]], slow_rows: list[dict[str, Any]], threshold_ns: int, conclusion_language: str, limit: int, has_cpu_op_type: bool = True) -> DirectionReport:
    cpu_exclude_zh = "；排除 debug 参数中 op_type 匹配 Cpu 的 slice" if has_cpu_op_type else "（本 trace 中无 CPU 算子，无需排除）"
    cpu_exclude_en = "; exclude slices whose debug op_type matches Cpu" if has_cpu_op_type else " (no CPU operators in this trace, exclusion not applicable)"
    rule_description = (
        f"过滤规则：仅统计 category='dnn' 的 slice；排除 name 后缀为 Wait 的 slice；排除 dur 非法或 <= 0 的 slice{cpu_exclude_zh}；其余结果按 slice name 分组，并按 {threshold_ns / 1_000_000:.3f} ms 阈值标记异常。"
        if conclusion_language == "zh"
        else f"Filter rule: keep only category='dnn' slices; exclude names ending with Wait; exclude invalid or non-positive durations{cpu_exclude_en}; group the remainder by slice name and mark anomalies above the {threshold_ns / 1_000_000:.3f} ms threshold."
    )
    summary_table_rows = [[row["name"], row["slice_count"], row["over_threshold_count"], ns_to_ms_str(row["total_dur_ns"]), ns_to_ms_str(row["avg_dur_ns"]), ns_to_ms_str(row["max_dur_ns"])] for row in summary_rows]
    if not slow_rows:
        conclusion = (
            f"按当前规则未发现命中异常的 slice（已应用配置中的排除条件，阈值为 dur >= {threshold_ns / 1_000_000:.3f} ms）。"
            if conclusion_language == "zh"
            else f"No anomalous slices matched the current rule (dur >= {threshold_ns / 1_000_000:.3f} ms after the configured exclusions)."
        )
        return DirectionReport("UCP Critical Path Slice Analysis (Excluding BPU and CPU Operators)", [ReportTable("Summary Table", ["name", "slice_count", "over_threshold", "total_ms", "avg_ms", "max_ms"], summary_table_rows)], rule_description, conclusion, "no_anomaly")
    detail_table_rows = [[row["name"], row["id"], ns_to_ms_str(row["dur"]), row["cause"], row["locate_sql"]] for row in slow_rows[:limit]]
    top_group = summary_rows[0]
    top_slice = slow_rows[0]
    conclusion = (
        f"当前最主要的热点是 {top_group['name']}，在 {threshold_ns / 1_000_000:.3f} ms 阈值下共有 {top_group['over_threshold_count']} 个 slice 命中；当前最差的样本是 id={top_slice['id']}，耗时 {ns_to_ms_float(top_slice['dur']):.3f} ms，其主导原因是 {top_slice['cause']}。"
        if conclusion_language == "zh"
        else f"The main hotspot is {top_group['name']} with {top_group['over_threshold_count']} slices above {threshold_ns / 1_000_000:.3f} ms; the worst visible slice is id={top_slice['id']} at {ns_to_ms_float(top_slice['dur']):.3f} ms, and its dominant cause is {top_slice['cause']}."
    )
    return DirectionReport("UCP Critical Path Slice Analysis (Excluding BPU and CPU Operators)", [
        ReportTable("Summary Table", ["name", "slice_count", "over_threshold", "total_ms", "avg_ms", "max_ms"], summary_table_rows),
        ReportTable("Detail Table", ["name", "id", "dur_ms", "cause", "locate_sql"], detail_table_rows),
    ], rule_description, conclusion, "ok")


def build_opinfer_direction_report(summary_rows: list[dict[str, Any]], bottleneck_rows: list[dict[str, Any]], ratio_threshold: float, diff_threshold_ns: int, conclusion_language: str, limit: int) -> DirectionReport:
    rule_description = (
        f"过滤规则：仅统计 name='OpInfer' 且 debug.op_type 匹配 Cpu 的 slice；按 task_info.desc 与 flow 位置分组；异常判定为 dur / group_avg > {ratio_threshold:.3f} 且 dur - group_avg > {diff_threshold_ns / 1_000_000:.3f} ms。"
        if conclusion_language == "zh"
        else f"Filter rule: keep only slices where name='OpInfer' and debug.op_type matches Cpu; group by task_info.desc and flow position; classify anomalies when dur / group_avg > {ratio_threshold:.3f} and dur - group_avg > {diff_threshold_ns / 1_000_000:.3f} ms."
    )
    summary_table_rows = [[row["task_desc"], row["flow_position"], row["slice_count"], ns_to_ms_str(row["avg_dur_ns"]), ns_to_ms_str(row["max_dur_ns"]), ns_to_ms_str(row["total_dur_ns"])] for row in summary_rows]
    if not bottleneck_rows:
        conclusion = (
            f"按当前规则未发现命中异常的 slice（dur / avg > {ratio_threshold:.3f} 且 dur - avg > {diff_threshold_ns / 1_000_000:.3f} ms）。"
            if conclusion_language == "zh"
            else f"No anomalous slices matched the current rule (dur / avg > {ratio_threshold:.3f} and dur - avg > {diff_threshold_ns / 1_000_000:.3f} ms)."
        )
        return DirectionReport("UCP CPU Operator Slice Analysis", [ReportTable("Summary Table", ["task_desc", "flow_pos", "slice_count", "avg_ms", "max_ms", "total_ms"], summary_table_rows)], rule_description, conclusion, "no_anomaly")
    detail_table_rows = [[row["task_desc"], row["flow_position"], row["name"], row["id"], ns_to_ms_str(row["dur"]), ns_to_ms_str(row["group_avg_dur_ns"]), f"{float(row['dur_ratio']):.3f}", row["cause"], row["locate_sql"]] for row in bottleneck_rows[:limit]]
    top_row = bottleneck_rows[0]
    conclusion = (
        f"当前最强的离群点是 task_desc={top_row['task_desc']}、flow_pos={top_row['flow_position']}；slice id={top_row['id']} 的耗时为 {ns_to_ms_float(top_row['dur']):.3f} ms，而同组平均值为 {ns_to_ms_float(top_row['group_avg_dur_ns']):.3f} ms，比值为 {float(top_row['dur_ratio']):.3f}。"
        if conclusion_language == "zh"
        else f"The strongest outlier is task_desc={top_row['task_desc']} at flow_pos={top_row['flow_position']}; slice id={top_row['id']} ran for {ns_to_ms_float(top_row['dur']):.3f} ms versus a group average of {ns_to_ms_float(top_row['group_avg_dur_ns']):.3f} ms, with ratio {float(top_row['dur_ratio']):.3f}."
    )
    return DirectionReport("UCP CPU Operator Slice Analysis", [
        ReportTable("Summary Table", ["task_desc", "flow_pos", "slice_count", "avg_ms", "max_ms", "total_ms"], summary_table_rows),
        ReportTable("Detail Table", ["task_desc", "flow_pos", "name", "id", "dur_ms", "avg_ms", "ratio", "cause", "locate_sql"], detail_table_rows),
    ], rule_description, conclusion, "ok")


def build_bpu_delay_direction_report(summary_row: dict[str, Any], detail_rows: list[dict[str, Any]], delay_threshold_ns: int, conclusion_language: str, limit: int) -> DirectionReport:
    rule_description = (
        f"过滤规则：仅统计处于 flow 中的 category='bpu' slice；分别计算 dispatch delay = bpu.start - prev.end 与 response delay = next.start - bpu.end；任一侧 delay > {delay_threshold_ns / 1_000_000:.3f} ms 即标记异常。"
        if conclusion_language == "zh"
        else f"Filter rule: keep only category='bpu' slices that belong to a flow; compute dispatch delay = bpu.start - prev.end and response delay = next.start - bpu.end; mark anomalies when either delay exceeds {delay_threshold_ns / 1_000_000:.3f} ms."
    )
    summary_table_rows = [[summary_row["in_flow_bpu_count"], summary_row["dispatch_over_threshold_count"], summary_row["response_over_threshold_count"], summary_row["either_over_threshold_count"], ns_to_ms_str(summary_row["max_dispatch_delay_ns"]), ns_to_ms_str(summary_row["max_response_delay_ns"])]]
    if not detail_rows:
        conclusion = (
            f"按当前规则未发现命中异常的 bpu flow gap（dispatch delay > {delay_threshold_ns / 1_000_000:.3f} ms 或 response delay > {delay_threshold_ns / 1_000_000:.3f} ms）。"
            if conclusion_language == "zh"
            else f"No anomalous bpu flow gaps matched the current rule (dispatch delay > {delay_threshold_ns / 1_000_000:.3f} ms or response delay > {delay_threshold_ns / 1_000_000:.3f} ms)."
        )
        return DirectionReport("BPU flow dispatch / response delay", [ReportTable("Summary Table", ["in_flow_bpu", "dispatch_over_1ms", "response_over_1ms", "either_over_1ms", "max_dispatch_ms", "max_response_ms"], summary_table_rows)], rule_description, conclusion, "no_anomaly")
    detail_table_rows = [[row["name"], row["id"], ns_to_ms_str(row["dur"]), ns_to_ms_str(row["prev_to_bpu_delay_ns"]), ns_to_ms_str(row["bpu_to_next_delay_ns"]), row["locate_sql"]] for row in detail_rows[:limit]]
    top_row = detail_rows[0]
    dispatch = ns_to_ms_float(top_row["prev_to_bpu_delay_ns"])
    response = ns_to_ms_float(top_row["bpu_to_next_delay_ns"])
    dominant = "dispatch" if dispatch >= response else "response"
    dominant_value = dispatch if dispatch >= response else response
    conclusion = (
        f"当前 flow gap 的主导问题是{'下发' if dominant == 'dispatch' else '回传'}侧延迟；当前最差的样本是 {top_row['name']}（id={top_row['id']}），在 {delay_threshold_ns / 1_000_000:.3f} ms 规则下其{'下发' if dominant == 'dispatch' else '回传'}侧延迟达到 {dominant_value:.3f} ms。"
        if conclusion_language == "zh"
        else f"The dominant flow-gap issue is {dominant} delay; the worst visible offender is {top_row['name']} (id={top_row['id']}) with {dominant_value:.3f} ms on the {dominant} side under the current {delay_threshold_ns / 1_000_000:.3f} ms rule."
    )
    return DirectionReport("BPU flow dispatch / response delay", [
        ReportTable("Summary Table", ["in_flow_bpu", "dispatch_over_1ms", "response_over_1ms", "either_over_1ms", "max_dispatch_ms", "max_response_ms"], summary_table_rows),
        ReportTable("Detail Table", ["name", "id", "dur_ms", "dispatch_delay_ms", "response_delay_ms", "locate_sql"], detail_table_rows),
    ], rule_description, conclusion, "ok")


def build_bpu_occupancy_direction_report(summary: dict[str, Any], summary_rows: list[dict[str, Any]], offender_rows: list[dict[str, Any]], ratio_threshold: float, conclusion_language: str, limit: int) -> DirectionReport:
    rule_description = (
        f"过滤规则：先按 track.name 划分独立硬件池；在每个硬件池内按 end-time 优先原则重建实际 BPU 占用时间；再仅保留 in-flow 的 category='bpu' slice，并按 slice name 与 flow 位置分组；当 effective_bpu_time / avg(name, flow_position) > {ratio_threshold:.3f} 时标记异常。"
        if conclusion_language == "zh"
        else f"Filter rule: first split contenders by track.name as independent hardware pools; reconstruct effective BPU occupancy inside each pool using the end-time-centric ownership rule; keep only in-flow category='bpu' slices and regroup by slice name and flow position; mark anomalies when effective_bpu_time / avg(name, flow_position) > {ratio_threshold:.3f}."
    )
    summary_table_rows = [[summary["candidate_bpu_count"], summary["in_flow_bpu_count"], ns_to_ms_str(summary["assigned_total_busy_ns"]), summary["flagged_group_count"], summary["offender_count"]]]
    group_table_rows = [[row["name"], row["flow_position"], row["slice_count"], ns_to_ms_str(row["avg_effective_ns"]), ns_to_ms_str(row["max_effective_ns"]), f"{float(row['group_ratio']):.3f}" if row["group_ratio"] is not None else "-", row["over_threshold_count"]] for row in summary_rows[:limit]]
    if not offender_rows:
        conclusion = (
            f"按当前规则未发现命中异常的有效硬件占用 slice（effective_bpu_time / avg(name, flow_position) > {ratio_threshold:.3f}）。"
            if conclusion_language == "zh"
            else f"No anomalous effective-occupancy slices matched the current rule (effective_bpu_time / avg(name, flow_position) > {ratio_threshold:.3f})."
        )
        return DirectionReport("Corrected BPU effective occupancy", [
            ReportTable("Summary Table", ["candidate_bpu", "in_flow_bpu", "assigned_busy_ms", "flagged_groups", "offenders"], summary_table_rows),
            ReportTable("Group Table", ["name", "flow_pos", "slice_count", "avg_effective_ms", "max_effective_ms", "max/avg", "over_threshold"], group_table_rows),
        ], rule_description, conclusion, "no_anomaly")
    detail_table_rows = [[row["name"], row["id"], row["flow_position"], ns_to_ms_str(row["effective_dur_ns"]), row["locate_sql"]] for row in offender_rows[:limit]]
    top_group = summary_rows[0]
    top_row = offender_rows[0]
    conclusion = (
        f"当前有效硬件占用偏斜最明显的分组是 {top_group['name']}（flow_pos={top_group['flow_position']}），其 max/avg 达到 {float(top_group['group_ratio']):.3f}；当前最差的样本是 slice id={top_row['id']}，重建后的硬件占用时间为 {ns_to_ms_float(top_row['effective_dur_ns']):.3f} ms。"
        if conclusion_language == "zh"
        else f"The most skewed effective-occupancy group is {top_group['name']} at flow_pos={top_group['flow_position']}, where max/avg reaches {float(top_group['group_ratio']):.3f}; the worst visible offender is slice id={top_row['id']} with {ns_to_ms_float(top_row['effective_dur_ns']):.3f} ms of reconstructed hardware time."
    )
    return DirectionReport("Corrected BPU effective occupancy", [
        ReportTable("Summary Table", ["candidate_bpu", "in_flow_bpu", "assigned_busy_ms", "flagged_groups", "offenders"], summary_table_rows),
        ReportTable("Group Table", ["name", "flow_pos", "slice_count", "avg_effective_ms", "max_effective_ms", "max/avg", "over_threshold"], group_table_rows),
        ReportTable("Detail Table", ["name", "id", "flow_pos", "effective_ms", "locate_sql"], detail_table_rows),
    ], rule_description, conclusion, "ok")


def render_direction_report_to_markdown(report: DirectionReport) -> str:
    parts = [f"**Status:** {report.status}"]
    parts.append("### Filter Rule\n\n" + report.rule_description)
    for table in report.tables:
        parts.append(f"### {table.title}\n\n" + build_markdown_table(table.headers, table.rows))
    parts.append("### Conclusion\n\n" + report.conclusion)
    return "\n\n".join(parts)


def write_combined_report(path: str, reports: list[DirectionReport], metadata: list[tuple[str, str]]) -> None:
    sections: list[tuple[str, str]] = []
    if metadata:
        meta_lines = [f"- **{key}:** {value}" for key, value in metadata]
        sections.append(("Report Metadata", "\n".join(meta_lines)))
    for report in reports:
        sections.append((report.title, render_direction_report_to_markdown(report)))
    write_markdown_report(path, sections)


def run_all_directions_report(
    tp: Any,
    probe: ProbeResult,
    threshold_ns: int,
    bottleneck_diff_threshold_ns: int,
    ratio_threshold: float,
    conclusion_language: str,
    limit: int,
    trace_path: Path,
    markdown_output: str | None,
) -> str:
    dnn_summary_rows = query_dicts(tp, build_summary_sql(probe.debug_op_type_flat_key, threshold_ns, probe.has_cpu_op_type))
    dnn_slow_rows = query_dicts(tp, build_slow_slice_sql(threshold_ns, probe.debug_op_type_flat_key, limit, probe.has_cpu_op_type))
    for row in dnn_slow_rows:
        row["cause"] = classify_cause(row)
    dnn_report = build_dnn_direction_report(dnn_summary_rows, dnn_slow_rows, threshold_ns, conclusion_language, limit, probe.has_cpu_op_type)

    bpu_delay_threshold_ns = 1_000_000
    bpu_delay_summary = query_dicts(tp, build_bpu_flow_delay_summary_sql(bpu_delay_threshold_ns))[0]
    bpu_delay_detail = query_dicts(tp, build_bpu_flow_delay_detail_sql(bpu_delay_threshold_ns, limit))
    bpu_delay_report = build_bpu_delay_direction_report(bpu_delay_summary, bpu_delay_detail, bpu_delay_threshold_ns, conclusion_language, limit)

    occupancy_rows = query_dicts(tp, build_bpu_effective_occupancy_input_sql())
    occupancy_summary, occupancy_summary_rows, occupancy_offender_rows = analyze_bpu_effective_occupancy(occupancy_rows, ratio_threshold)
    occupancy_report = build_bpu_occupancy_direction_report(occupancy_summary, occupancy_summary_rows, occupancy_offender_rows, ratio_threshold, conclusion_language, limit)

    if not probe.has_cpu_op_type:
        opinfer_report = DirectionReport(
            "UCP CPU Operator Slice Analysis",
            [],
            (
                f"过滤规则：仅统计 name='OpInfer' 且 debug.op_type 匹配 Cpu 的 slice；按 task_info.desc 与 flow 位置分组；异常判定为 dur / group_avg > {ratio_threshold:.3f} 且 dur - group_avg > {bottleneck_diff_threshold_ns / 1_000_000:.3f} ms。"
                if conclusion_language == "zh"
                else f"Filter rule: keep only slices where name='OpInfer' and debug.op_type matches Cpu; group by task_info.desc and flow position; classify anomalies when dur / group_avg > {ratio_threshold:.3f} and dur - group_avg > {bottleneck_diff_threshold_ns / 1_000_000:.3f} ms."
            ),
            "已跳过：UCP CPU Operator Slice Analysis 未发现 CPU 算子（debug.op_type 中无匹配 Cpu 的值），本 trace 中所有 OpInfer 均为非 CPU 算子。" if conclusion_language == "zh" else "Skipped: UCP CPU Operator Slice Analysis found no CPU operators (no debug.op_type values matching Cpu); all OpInfer slices in this trace are non-CPU operators.",
            "skipped",
        )
    elif probe.debug_task_info_flat_key is None:
        opinfer_report = DirectionReport(
            "UCP CPU Operator Slice Analysis",
            [],
            (
                f"过滤规则：仅统计 name='OpInfer' 且 debug.op_type 匹配 Cpu 的 slice；按 task_info.desc 与 flow 位置分组；异常判定为 dur / group_avg > {ratio_threshold:.3f} 且 dur - group_avg > {bottleneck_diff_threshold_ns / 1_000_000:.3f} ms。"
                if conclusion_language == "zh"
                else f"Filter rule: keep only slices where name='OpInfer' and debug.op_type matches Cpu; group by task_info.desc and flow position; classify anomalies when dur / group_avg > {ratio_threshold:.3f} and dur - group_avg > {bottleneck_diff_threshold_ns / 1_000_000:.3f} ms."
            ),
            "Skipped because debug.task_info could not be resolved for UCP CPU Operator Slice Analysis." if conclusion_language == "en" else "已跳过：UCP CPU Operator Slice Analysis 未能解析到 debug.task_info。",
            "skipped",
        )
    else:
        opinfer_summary_rows = query_dicts(tp, build_opinfer_desc_flow_summary_sql(probe.debug_op_type_flat_key, probe.debug_task_info_flat_key))
        opinfer_bottleneck_rows = query_dicts(tp, build_opinfer_desc_flow_bottleneck_sql(probe.debug_op_type_flat_key, probe.debug_task_info_flat_key, ratio_threshold, bottleneck_diff_threshold_ns, limit))
        for row in opinfer_bottleneck_rows:
            row["cause"] = classify_cause(row)
        opinfer_report = build_opinfer_direction_report(opinfer_summary_rows, opinfer_bottleneck_rows, ratio_threshold, bottleneck_diff_threshold_ns, conclusion_language, limit)

    report_path = markdown_output or default_markdown_output_path(trace_path)
    write_combined_report(
        report_path,
        [dnn_report, opinfer_report, bpu_delay_report, occupancy_report],
        [
            ("trace_path", str(trace_path)),
            ("analysis_direction", "all"),
            ("threshold_ms", f"{threshold_ns / 1_000_000:.3f}"),
            ("bottleneck_ratio_threshold", f"{ratio_threshold:.3f}"),
            ("bottleneck_diff_ms", f"{bottleneck_diff_threshold_ns / 1_000_000:.3f}"),
            ("bpu_delay_threshold_ms", "1.000"),
            ("has_cpu_op_type", str(probe.has_cpu_op_type)),
        ],
    )

    print("[Report] Exported default four-direction Markdown report")
    print(f"[Report] path={report_path}")
    print("[Report] included=UCP Critical Path Slice Analysis (Excluding BPU and CPU Operators); UCP CPU Operator Slice Analysis; BPU flow dispatch / response delay; Corrected BPU effective occupancy")
    print("[Report] scope complete; deeper follow-up analysis is outside the default skill flow.")
    return report_path


def output_analysis(probe: ProbeResult, summary_rows: list[dict[str, Any]], slow_rows: list[dict[str, Any]], threshold_ns: int, limit: int, fmt: str, conclusion_language: str, markdown_output: str | None) -> None:
    payload = {
        "threshold_ns": threshold_ns,
        "resolved_debug_op_type_flat_key": probe.debug_op_type_flat_key,
        "summary": summary_rows,
        "slow_slices": slow_rows[:limit],
    }
    if fmt == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    print(f"[Config] threshold={threshold_ns} ns ({threshold_ns / 1_000_000:.3f} ms)")
    print(f"[Config] resolved debug op_type flat_key={probe.debug_op_type_flat_key}")
    print(f"[Config] has_cpu_op_type={probe.has_cpu_op_type}")
    print()
    print("[Summary] grouped by slice name")
    summary_table_rows = [[row["name"], row["slice_count"], row["over_threshold_count"], ns_to_ms_str(row["total_dur_ns"]), ns_to_ms_str(row["avg_dur_ns"]), ns_to_ms_str(row["max_dur_ns"])] for row in summary_rows]
    print_table(["name", "slice_count", "over_threshold", "total_ms", "avg_ms", "max_ms"], [[row["name"], row["slice_count"], row["over_threshold_count"], ns_to_ms_str(row["total_dur_ns"]), ns_to_ms_str(row["avg_dur_ns"]), ns_to_ms_str(row["max_dur_ns"])] for row in summary_rows])
    print()
    if not slow_rows:
        if conclusion_language == "zh":
            conclusion = f"按当前规则未发现命中异常的 slice（已应用配置中的排除条件，阈值为 dur >= {threshold_ns / 1_000_000:.3f} ms）。"
        else:
            conclusion = f"No anomalous slices matched the current rule (dur >= {threshold_ns / 1_000_000:.3f} ms after the configured exclusions)."
        print(f"[Conclusion] {conclusion}")
        if markdown_output:
            write_markdown_report(markdown_output, [
                ("Summary Table", build_markdown_table(["name", "slice_count", "over_threshold", "total_ms", "avg_ms", "max_ms"], summary_table_rows)),
                ("Conclusion", conclusion),
            ])
        return
    print(f"[Slow slices] top {min(limit, len(slow_rows))}")
    detail_table_rows = [[row["name"], row["id"], ns_to_ms_str(row["dur"]), row["cause"], row["locate_sql"]] for row in slow_rows[:limit]]
    print_table(["name", "id", "dur_ms", "cause", "locate_sql"], detail_table_rows)
    top_group = summary_rows[0] if summary_rows else None
    top_slice = slow_rows[0] if slow_rows else None
    if top_group and top_slice:
        print()
        if conclusion_language == "zh":
            conclusion = f"当前最主要的热点是 {top_group['name']}，在 {threshold_ns / 1_000_000:.3f} ms 阈值下共有 {top_group['over_threshold_count']} 个 slice 命中；当前最差的样本是 id={top_slice['id']}，耗时 {ns_to_ms_float(top_slice['dur']):.3f} ms，其主导原因是 {top_slice['cause']}。"
        else:
            conclusion = f"The main hotspot is {top_group['name']} with {top_group['over_threshold_count']} slices above {threshold_ns / 1_000_000:.3f} ms; the worst visible slice is id={top_slice['id']} at {ns_to_ms_float(top_slice['dur']):.3f} ms, and its dominant cause is {top_slice['cause']}."
        print(f"[Conclusion] {conclusion}")
        if markdown_output:
            write_markdown_report(markdown_output, [
                ("Summary Table", build_markdown_table(["name", "slice_count", "over_threshold", "total_ms", "avg_ms", "max_ms"], summary_table_rows)),
                ("Offender Table", build_markdown_table(["name", "id", "dur_ms", "cause", "locate_sql"], detail_table_rows)),
                ("Conclusion", conclusion),
            ])


def output_opinfer_desc_flow_analysis(probe: ProbeResult, summary_rows: list[dict[str, Any]], bottleneck_rows: list[dict[str, Any]], ratio_threshold: float, diff_threshold_ns: int, limit: int, fmt: str, conclusion_language: str, markdown_output: str | None) -> None:
    payload = {
        "analysis_direction": "opinfer_desc_flow",
        "bottleneck_ratio_threshold": ratio_threshold,
        "bottleneck_diff_threshold_ns": diff_threshold_ns,
        "resolved_debug_op_type_flat_key": probe.debug_op_type_flat_key,
        "resolved_debug_task_info_flat_key": probe.debug_task_info_flat_key,
        "summary": summary_rows,
        "bottlenecks": bottleneck_rows[:limit],
    }
    if fmt == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    print("[Config] analysis_direction=opinfer_desc_flow")
    print(f"[Config] bottleneck_ratio_threshold={ratio_threshold:.3f}")
    print(f"[Config] bottleneck_diff_threshold={diff_threshold_ns / 1_000_000:.3f} ms")
    print(f"[Config] resolved debug op_type flat_key={probe.debug_op_type_flat_key}")
    print(f"[Config] resolved debug task_info flat_key={probe.debug_task_info_flat_key}")
    print()
    print(
        "[Filter Rule] "
        + (
            f"仅统计 name='OpInfer' 且 debug.op_type 匹配 Cpu 的 slice；按 task_info.desc 与 flow 位置分组；异常判定为 dur / group_avg > {ratio_threshold:.3f} 且 dur - group_avg > {diff_threshold_ns / 1_000_000:.3f} ms。"
            if conclusion_language == "zh"
            else f"Keep only slices where name='OpInfer' and debug.op_type matches Cpu; group by task_info.desc and flow position; classify anomalies when dur / group_avg > {ratio_threshold:.3f} and dur - group_avg > {diff_threshold_ns / 1_000_000:.3f} ms."
        )
    )
    print()
    print("[Summary] grouped by task_info.desc + flow_position")
    summary_table_rows = [[row["task_desc"], row["flow_position"], row["slice_count"], ns_to_ms_str(row["avg_dur_ns"]), ns_to_ms_str(row["max_dur_ns"]), ns_to_ms_str(row["total_dur_ns"])] for row in summary_rows]
    print_table(["task_desc", "flow_pos", "slice_count", "avg_ms", "max_ms", "total_ms"], summary_table_rows)
    print()
    if not bottleneck_rows:
        if conclusion_language == "zh":
            conclusion = f"按当前规则未发现命中异常的 slice（dur / avg > {ratio_threshold:.3f} 且 dur - avg > {diff_threshold_ns / 1_000_000:.3f} ms）。"
        else:
            conclusion = f"No anomalous slices matched the current rule (dur / avg > {ratio_threshold:.3f} and dur - avg > {diff_threshold_ns / 1_000_000:.3f} ms)."
        print(f"[Conclusion] {conclusion}")
        if markdown_output:
            write_markdown_report(markdown_output, [
                ("Summary Table", build_markdown_table(["task_desc", "flow_pos", "slice_count", "avg_ms", "max_ms", "total_ms"], summary_table_rows)),
                ("Conclusion", conclusion),
            ])
        return
    print(f"[Bottlenecks] top {min(limit, len(bottleneck_rows))}")
    detail_table_rows = [[row["task_desc"], row["flow_position"], row["name"], row["id"], ns_to_ms_str(row["dur"]), ns_to_ms_str(row["group_avg_dur_ns"]), f"{float(row['dur_ratio']):.3f}", row["cause"], row["locate_sql"]] for row in bottleneck_rows[:limit]]
    print_table(["task_desc", "flow_pos", "name", "id", "dur_ms", "avg_ms", "ratio", "cause", "locate_sql"], detail_table_rows)
    top_row = bottleneck_rows[0] if bottleneck_rows else None
    if top_row:
        print()
        if conclusion_language == "zh":
            conclusion = f"当前最强的离群点是 task_desc={top_row['task_desc']}、flow_pos={top_row['flow_position']}；slice id={top_row['id']} 的耗时为 {ns_to_ms_float(top_row['dur']):.3f} ms，而同组平均值为 {ns_to_ms_float(top_row['group_avg_dur_ns']):.3f} ms，比值为 {float(top_row['dur_ratio']):.3f}。"
        else:
            conclusion = f"The strongest outlier is task_desc={top_row['task_desc']} at flow_pos={top_row['flow_position']}; slice id={top_row['id']} ran for {ns_to_ms_float(top_row['dur']):.3f} ms versus a group average of {ns_to_ms_float(top_row['group_avg_dur_ns']):.3f} ms, with ratio {float(top_row['dur_ratio']):.3f}."
        print(f"[Conclusion] {conclusion}")
        if markdown_output:
            write_markdown_report(markdown_output, [
                ("Filter Rule", (
                    f"仅统计 name='OpInfer' 且 debug.op_type 匹配 Cpu 的 slice；按 task_info.desc 与 flow 位置分组；异常判定为 dur / group_avg > {ratio_threshold:.3f} 且 dur - group_avg > {diff_threshold_ns / 1_000_000:.3f} ms。"
                    if conclusion_language == "zh"
                    else f"Keep only slices where name='OpInfer' and debug.op_type matches Cpu; group by task_info.desc and flow position; classify anomalies when dur / group_avg > {ratio_threshold:.3f} and dur - group_avg > {diff_threshold_ns / 1_000_000:.3f} ms."
                )),
                ("Summary Table", build_markdown_table(["task_desc", "flow_pos", "slice_count", "avg_ms", "max_ms", "total_ms"], summary_table_rows)),
                ("Offender Table", build_markdown_table(["task_desc", "flow_pos", "name", "id", "dur_ms", "avg_ms", "ratio", "cause", "locate_sql"], detail_table_rows)),
                ("Conclusion", conclusion),
            ])


def output_bpu_flow_delay_analysis(summary_row: dict[str, Any], detail_rows: list[dict[str, Any]], delay_threshold_ns: int, limit: int, fmt: str, conclusion_language: str, markdown_output: str | None) -> None:
    payload = {
        "analysis_direction": "bpu_flow_delay",
        "delay_threshold_ns": delay_threshold_ns,
        "summary": summary_row,
        "offenders": detail_rows[:limit],
    }
    if fmt == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    print("[Config] analysis_direction=bpu_flow_delay")
    print(f"[Config] delay_threshold={delay_threshold_ns / 1_000_000:.3f} ms")
    print()
    print("[Summary] bpu slices in flows")
    summary_table_rows = [[summary_row["in_flow_bpu_count"], summary_row["dispatch_over_threshold_count"], summary_row["response_over_threshold_count"], summary_row["either_over_threshold_count"], ns_to_ms_str(summary_row["max_dispatch_delay_ns"]), ns_to_ms_str(summary_row["max_response_delay_ns"])]]
    print_table(["in_flow_bpu", "dispatch_over_1ms", "response_over_1ms", "either_over_1ms", "max_dispatch_ms", "max_response_ms"], summary_table_rows)
    print()
    if not detail_rows:
        if conclusion_language == "zh":
            conclusion = f"按当前规则未发现命中异常的 bpu flow gap（dispatch delay > {delay_threshold_ns / 1_000_000:.3f} ms 或 response delay > {delay_threshold_ns / 1_000_000:.3f} ms）。"
        else:
            conclusion = f"No anomalous bpu flow gaps matched the current rule (dispatch delay > {delay_threshold_ns / 1_000_000:.3f} ms or response delay > {delay_threshold_ns / 1_000_000:.3f} ms)."
        print(f"[Conclusion] {conclusion}")
        if markdown_output:
            write_markdown_report(markdown_output, [
                ("Summary Table", build_markdown_table(["in_flow_bpu", "dispatch_over_1ms", "response_over_1ms", "either_over_1ms", "max_dispatch_ms", "max_response_ms"], summary_table_rows)),
                ("Conclusion", conclusion),
            ])
        return
    print(f"[Offending bpu slices] top {min(limit, len(detail_rows))}")
    detail_table_rows = [[row["name"], row["id"], ns_to_ms_str(row["dur"]), ns_to_ms_str(row["prev_to_bpu_delay_ns"]), ns_to_ms_str(row["bpu_to_next_delay_ns"]), row["locate_sql"]] for row in detail_rows[:limit]]
    print_table(["name", "id", "dur_ms", "dispatch_delay_ms", "response_delay_ms", "locate_sql"], detail_table_rows)
    top_row = detail_rows[0] if detail_rows else None
    if top_row:
        dispatch = ns_to_ms_float(top_row["prev_to_bpu_delay_ns"])
        response = ns_to_ms_float(top_row["bpu_to_next_delay_ns"])
        dominant = "dispatch" if dispatch >= response else "response"
        dominant_value = dispatch if dispatch >= response else response
        print()
        if conclusion_language == "zh":
            dominant_zh = "下发" if dominant == "dispatch" else "回传"
            conclusion = f"当前 flow gap 的主导问题是{dominant_zh}侧延迟；当前最差的样本是 {top_row['name']}（id={top_row['id']}），在 {delay_threshold_ns / 1_000_000:.3f} ms 规则下其 {dominant_zh}侧延迟达到 {dominant_value:.3f} ms。"
        else:
            conclusion = f"The dominant flow-gap issue is {dominant} delay; the worst visible offender is {top_row['name']} (id={top_row['id']}) with {dominant_value:.3f} ms on the {dominant} side under the current {delay_threshold_ns / 1_000_000:.3f} ms rule."
        print(f"[Conclusion] {conclusion}")
        if markdown_output:
            write_markdown_report(markdown_output, [
                ("Summary Table", build_markdown_table(["in_flow_bpu", "dispatch_over_1ms", "response_over_1ms", "either_over_1ms", "max_dispatch_ms", "max_response_ms"], summary_table_rows)),
                ("Offender Table", build_markdown_table(["name", "id", "dur_ms", "dispatch_delay_ms", "response_delay_ms", "locate_sql"], detail_table_rows)),
                ("Conclusion", conclusion),
            ])


def output_bpu_effective_occupancy_analysis(summary: dict[str, Any], summary_rows: list[dict[str, Any]], offender_rows: list[dict[str, Any]], ratio_threshold: float, limit: int, fmt: str, conclusion_language: str, markdown_output: str | None) -> None:
    payload = {
        "analysis_direction": "bpu_effective_occupancy",
        "bottleneck_ratio_threshold": ratio_threshold,
        "summary": summary,
        "groups": summary_rows,
        "offenders": offender_rows[:limit],
    }
    if fmt == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    print("[Config] analysis_direction=bpu_effective_occupancy")
    print(f"[Config] bottleneck_ratio_threshold={ratio_threshold:.3f}")
    print("[Config] occupancy contenders=all valid bpu slices grouped by exact track_name; reporting=in-flow bpu slices only")
    print()
    print("[Summary] effective occupancy")
    summary_table_rows = [[summary["candidate_bpu_count"], summary["in_flow_bpu_count"], ns_to_ms_str(summary["assigned_total_busy_ns"]), summary["flagged_group_count"], summary["offender_count"]]]
    print_table(["candidate_bpu", "in_flow_bpu", "assigned_busy_ms", "flagged_groups", "offenders"], summary_table_rows)
    print()
    print("[Groups] by name + flow_position")
    group_table_rows = [[row["name"], row["flow_position"], row["slice_count"], ns_to_ms_str(row["avg_effective_ns"]), ns_to_ms_str(row["max_effective_ns"]), f"{float(row['group_ratio']):.3f}" if row["group_ratio"] is not None else "-", row["over_threshold_count"]] for row in summary_rows[:limit]]
    print_table(["name", "flow_pos", "slice_count", "avg_effective_ms", "max_effective_ms", "max/avg", "over_threshold"], group_table_rows)
    print()
    if not offender_rows:
        if conclusion_language == "zh":
            conclusion = f"按当前规则未发现命中异常的有效硬件占用 slice（effective_bpu_time / avg(name, flow_position) > {ratio_threshold:.3f}）。"
        else:
            conclusion = f"No anomalous effective-occupancy slices matched the current rule (effective_bpu_time / avg(name, flow_position) > {ratio_threshold:.3f})."
        print(f"[Conclusion] {conclusion}")
        if markdown_output:
            write_markdown_report(markdown_output, [
                ("Summary Table", build_markdown_table(["candidate_bpu", "in_flow_bpu", "assigned_busy_ms", "flagged_groups", "offenders"], summary_table_rows)),
                ("Group Table", build_markdown_table(["name", "flow_pos", "slice_count", "avg_effective_ms", "max_effective_ms", "max/avg", "over_threshold"], group_table_rows)),
                ("Conclusion", conclusion),
            ])
        return
    print(f"[Offending bpu slices] top {min(limit, len(offender_rows))}")
    detail_table_rows = [[row["name"], row["id"], row["flow_position"], ns_to_ms_str(row["effective_dur_ns"]), row["bottleneck_rule"], row["locate_sql"]] for row in offender_rows[:limit]]
    print_table(["name", "id", "flow_pos", "effective_ms", "rule", "locate_sql"], detail_table_rows)
    top_group = summary_rows[0] if summary_rows else None
    top_row = offender_rows[0] if offender_rows else None
    if top_group and top_row:
        print()
        if conclusion_language == "zh":
            conclusion = f"当前有效硬件占用偏斜最明显的分组是 {top_group['name']}（flow_pos={top_group['flow_position']}），其 max/avg 达到 {float(top_group['group_ratio']):.3f}；当前最差的样本是 slice id={top_row['id']}，重建后的硬件占用时间为 {ns_to_ms_float(top_row['effective_dur_ns']):.3f} ms。"
        else:
            conclusion = f"The most skewed effective-occupancy group is {top_group['name']} at flow_pos={top_group['flow_position']}, where max/avg reaches {float(top_group['group_ratio']):.3f}; the worst visible offender is slice id={top_row['id']} with {ns_to_ms_float(top_row['effective_dur_ns']):.3f} ms of reconstructed hardware time."
        print(f"[Conclusion] {conclusion}")
        if markdown_output:
            write_markdown_report(markdown_output, [
                ("Summary Table", build_markdown_table(["candidate_bpu", "in_flow_bpu", "assigned_busy_ms", "flagged_groups", "offenders"], summary_table_rows)),
                ("Group Table", build_markdown_table(["name", "flow_pos", "slice_count", "avg_effective_ms", "max_effective_ms", "max/avg", "over_threshold"], group_table_rows)),
                ("Offender Table", build_markdown_table(["name", "id", "flow_pos", "effective_ms", "rule", "locate_sql"], detail_table_rows)),
                ("Conclusion", conclusion),
            ])


def main() -> int:
    args = parse_args()
    trace_path = Path(args.trace_path)
    if not trace_path.exists():
        raise SystemExit(f"Trace file not found: {trace_path}")
    if args.trace_processor_bin and not Path(args.trace_processor_bin).exists():
        raise SystemExit(f"trace_processor_shell not found: {args.trace_processor_bin}")

    threshold_ns = ms_to_ns(args.min_duration_ms)
    bottleneck_diff_threshold_ns = ms_to_ns(args.bottleneck_diff_ms)
    conclusion_language = resolve_conclusion_language(args.conclusion_language)
    tp = open_trace_processor(str(trace_path), args.trace_processor_bin)
    try:
        probe = probe_trace(tp)
        if args.probe_only or args.analysis_direction != "all":
            output_probe(probe, args.format)
        if args.probe_only:
            return 0
        if args.analysis_direction == "all":
            run_all_directions_report(
                tp,
                probe,
                threshold_ns,
                bottleneck_diff_threshold_ns,
                args.bottleneck_ratio_threshold,
                conclusion_language,
                args.limit,
                trace_path,
                args.markdown_output,
            )
            return 0
        if args.analysis_direction == "dnn_name":
            summary_rows = query_dicts(tp, build_summary_sql(probe.debug_op_type_flat_key, threshold_ns, probe.has_cpu_op_type))
            slow_rows = query_dicts(tp, build_slow_slice_sql(threshold_ns, probe.debug_op_type_flat_key, args.limit, probe.has_cpu_op_type))
            for row in slow_rows:
                row["cause"] = classify_cause(row)
            print()
            output_analysis(probe, summary_rows, slow_rows, threshold_ns, args.limit, args.format, conclusion_language, args.markdown_output)
            return 0

        if args.analysis_direction == "bpu_flow_delay":
            bpu_delay_threshold_ns = 1_000_000
            summary_row = query_dicts(tp, build_bpu_flow_delay_summary_sql(bpu_delay_threshold_ns))[0]
            detail_rows = query_dicts(tp, build_bpu_flow_delay_detail_sql(bpu_delay_threshold_ns, args.limit))
            print()
            output_bpu_flow_delay_analysis(summary_row, detail_rows, bpu_delay_threshold_ns, args.limit, args.format, conclusion_language, args.markdown_output)
            return 0

        if args.analysis_direction == "bpu_effective_occupancy":
            occupancy_rows = query_dicts(tp, build_bpu_effective_occupancy_input_sql())
            summary, summary_rows, offender_rows = analyze_bpu_effective_occupancy(occupancy_rows, args.bottleneck_ratio_threshold)
            print()
            output_bpu_effective_occupancy_analysis(summary, summary_rows, offender_rows, args.bottleneck_ratio_threshold, args.limit, args.format, conclusion_language, args.markdown_output)
            return 0

        # opinfer_desc_flow direction
        if not probe.has_cpu_op_type:
            print("[Info] No CPU operators found (debug.op_type has no values matching Cpu); skipping UCP CPU Operator Slice Analysis.")
            return 0
        if probe.debug_task_info_flat_key is None:
            print("[Info] Unable to resolve debug.task_info key for UCP CPU Operator Slice Analysis; rerun with --probe-only and inspect args structure.")
            return 0
        summary_rows = query_dicts(tp, build_opinfer_desc_flow_summary_sql(probe.debug_op_type_flat_key, probe.debug_task_info_flat_key))
        bottleneck_rows = query_dicts(tp, build_opinfer_desc_flow_bottleneck_sql(probe.debug_op_type_flat_key, probe.debug_task_info_flat_key, args.bottleneck_ratio_threshold, bottleneck_diff_threshold_ns, args.limit))
        for row in bottleneck_rows:
            row["cause"] = classify_cause(row)
        print()
        output_opinfer_desc_flow_analysis(probe, summary_rows, bottleneck_rows, args.bottleneck_ratio_threshold, bottleneck_diff_threshold_ns, args.limit, args.format, conclusion_language, args.markdown_output)
    finally:
        tp.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
