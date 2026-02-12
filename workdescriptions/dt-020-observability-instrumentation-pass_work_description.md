## Summary
Implemented DT-020 observability instrumentation for the DT-017/DT-018 orchestrator integration adapters, with high-coverage integration tests focused on telemetry success/failure/degradation branches.

## Work Performed
- Added `modules/orchestrator/observability.py` with dependency-free in-memory telemetry primitives:
  - metrics (`MetricPoint`)
  - trace spans (`SpanRecord`)
  - structured logs (`LogRecord`)
  - immutable snapshots (`ObservabilitySnapshot`)
  - timing context manager support for stage spans.
- Updated `modules/orchestrator/draft_pipeline_adapter.py` to:
  - emit pipeline start/success/failure events
  - instrument stage A/C/D/E/F spans
  - track per-stage success/failure counters and pipeline-level counters/logs.
- Updated `modules/orchestrator/hq_pipeline_adapter.py` to:
  - emit HQ pipeline start/success/failure events
  - instrument stage B span
  - record degradation-specific metric/log output
  - preserve degradation-policy exception behavior while emitting failure telemetry.
- Added `tests/integration/test_observability.py` with comprehensive branch coverage over:
  - span success/error outcomes
  - draft pipeline success/failure telemetry
  - HQ success/degraded/failure telemetry.
- Updated `Work_Checklist.md` with a DT-020 completion checkbox.

## Validation
- Ran full test discovery suite via `python -m unittest discover -v`.
- Attempted branch coverage execution, but `coverage` CLI is unavailable in the current environment.
