# Perfetto SQL Patterns

## Quick locate a slice

```sql
SELECT s.*, a.key, a.flat_key, a.string_value, a.int_value, a.real_value
FROM slice s
LEFT JOIN args a ON a.arg_set_id = s.arg_set_id
WHERE s.id = <slice_id>
ORDER BY a.flat_key, a.key;
```

## Probe debug argument keys

```sql
SELECT a.flat_key, a.key, a.value_type, COUNT(*) AS cnt
FROM slice s
JOIN args a ON a.arg_set_id = s.arg_set_id
WHERE s.category = '<category>'
GROUP BY 1, 2, 3
ORDER BY cnt DESC;
```

## Probe thread states

```sql
SELECT state, COUNT(*) AS cnt
FROM thread_state
GROUP BY state
ORDER BY cnt DESC;
```

## Check whether flows are linear

```sql
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
)
SELECT
  SUM(CASE WHEN in_deg > 1 THEN 1 ELSE 0 END) AS multi_in_nodes,
  SUM(CASE WHEN out_deg > 1 THEN 1 ELSE 0 END) AS multi_out_nodes,
  COUNT(*) AS total_nodes
FROM deg;
```
