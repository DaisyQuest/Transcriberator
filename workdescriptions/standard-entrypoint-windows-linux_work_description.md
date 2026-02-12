## Summary
Implemented a standard, guaranteed startup entrypoint for both Windows and Linux/macOS, including wrapper scripts, canonical startup orchestration logic, and comprehensive branch-complete tests.

## Work Performed
- Added `infrastructure/local-dev/start_transcriberator.py` as the canonical startup entrypoint.
  - Dynamically loads dashboard API and orchestrator skeleton modules.
  - Creates an auth session, project, and job through dashboard APIs.
  - Executes orchestrator stages in Draft or HQ mode.
  - Fails fast with actionable errors when startup simulation fails.
  - Supports JSON output, simulated stage-failure drills, and HQ degradation toggling.
- Added root-level wrappers:
  - `start.sh` for Linux/macOS/Git Bash.
  - `start.ps1` for Windows PowerShell.
- Updated user-facing documentation:
  - `userguide.md`
  - `userguide.html`
  - `infrastructure/local-dev/README.md`
  - `docs/runbooks/DT-016_Local_Dev_Windows_Runbook.md`
  - `docs/README.md`
  - `infrastructure/README.md`
- Added deep test coverage in `tests/unit/test_local_entrypoints.py` covering:
  - Runtime success and failure branches.
  - HQ degradation and hard-failure semantics.
  - CLI human and JSON output paths.
  - Wrapper script delegation assertions.
  - Documentation assertions for standard entrypoint discoverability.

## Validation
- `python -m pytest tests/unit/test_local_entrypoints.py -q`
- `python -m pytest --cov=. --cov-branch --cov-report=term-missing --cov-fail-under=95`
