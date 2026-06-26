# UCP Perfetto Inference References

Use this directory as the supporting reference set for the `ucp_perfetto_trace_analysis` skill, which is scoped only to UCP inference bottleneck analysis.

## Recommended reading order

1. `setup.md`
   - dependency installation
   - quick start
   - offline / restricted-network fallback
   - troubleshooting

2. `output.md`
   - default report-first output contract
   - terminal recap vs focused/manual output
   - conclusion language interview
   - report expectations

3. `sql_patterns.md`
   - reusable SQL snippets for probing schema
   - locating slices quickly
   - checking flow shape and common analysis primitives

4. `directions.md`
   - detailed definitions for the four supported UCP inference bottleneck directions

## When to use each file

- Read `setup.md` before first use on a new machine.
- Read `output.md` when you want consistent reporting behavior.
- Read `sql_patterns.md` when you need direct SQL help for one of the supported UCP directions or want to extend the bundled script within this scope.
- Read `directions.md` when you need the exact rule semantics for one of the four supported directions.
