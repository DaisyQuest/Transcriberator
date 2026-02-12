# reference-instrument-calibration-generalization_work_description

## Summary
- Extended local melody calibration so known fixture hashes still resolve to exact calibrated phrases while unknown recordings can reuse reference-instrument calibration heuristics when their melody profile looks instrument-compatible.
- Added reference-instrument candidate detection logic plus adaptive octave/pitch-class correction to reduce octave drift and unstable leap behavior for other recordings from the same instrument.
- Added focused helper utilities for reference pitch-class snapping and branch-safe fallback behavior.
- Expanded entrypoint unit tests to cover new candidate/non-candidate branches, empty and out-of-range reference calibration behavior, and pitch-class snap helper branches.

## Files Changed
- `infrastructure/local-dev/start_transcriberator.py`
- `tests/unit/test_local_entrypoints.py`

## Validation
- `pytest -q`
- `pytest -q tests/unit/test_local_entrypoints.py`
- `pytest --cov=. --cov-branch --cov-report=term-missing -q` *(fails because pytest-cov is unavailable in this environment)*
