## Summary
Implemented DT-021 reliability and recovery hardening for orchestrator and worker failure paths via a dedicated integration test suite focused on failure semantics, degradation behavior, and recovery retries.

## Work Performed
- Added `tests/integration/test_recovery.py`.
- Added orchestrator recovery assertions for:
  - HQ failure behavior when degradation is disallowed.
  - Draft-mode stage skipping precedence over failure injection.
  - Short-circuit behavior after first failed stage.
  - Empty-record terminal status behavior.
- Added worker failure/recovery path assertions for:
  - audio format validation failure followed by successful rerun.
  - separation timeout degradation followed by successful rerun.
  - transcription model-version validation failure followed by successful rerun.
  - quantization invalid request failures followed by successful rerun.
  - engraving validation failures followed by successful rerun.
- Added HQ adapter recovery assertions for separation-timeout behavior under both disallowed and allowed degradation policies.
- Updated `Work_Checklist.md` with a DT-021 completion checkbox.

## Validation
- Ran the full repository test suite.
- Ran branch coverage with threshold enforcement (>=95%).
