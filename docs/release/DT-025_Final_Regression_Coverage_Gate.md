# DT-025 Final Regression and Branch Coverage Gate

## Scope
This checklist implements **DT-025 Final regression and branch coverage gate** from `Development_Tasks.md`.

- Dependency baseline: DT-024 must be complete.
- Owner scope: `tests/`, CI configs.
- Exit criteria:
  - Full suite green.
  - Branch coverage report meets policy target (>=95%).
  - Windows local runbook validated end-to-end.

## Validation Evidence Map

| Criterion | Evidence Artifact(s) |
|---|---|
| DT-024 completion dependency | `workdescriptions/dt-024-milestone-acceptance-gate-checks_work_description.md`, `Work_Checklist.md` |
| Full regression command and pass | `pytest.ini`, `.github/workflows/ci.yml`, `tests/README.md` |
| Branch coverage gate (>=95%) | `.coveragerc`, `.github/workflows/ci.yml`, `tests/README.md` |
| Windows runbook end-to-end flow retained | `docs/runbooks/DT-016_Local_Dev_Windows_Runbook.md`, `userguide.md`, `userguide.html` |

## Release Gate Execution Order
1. Validate DT-024 completion evidence.
2. Run full regression suite with deterministic import mode.
3. Run branch coverage report and enforce threshold >=95%.
4. Validate Windows local runbook sequence and command mapping.
5. Ensure user-facing guides are current and linked from docs index.

## Commands

### Local (Linux/macOS shell)
```bash
python -m pip install pytest pytest-cov
pytest --cov=. --cov-branch --cov-report=term-missing --cov-report=xml --cov-fail-under=95
```

### Windows (PowerShell)
```powershell
py -m pip install pytest pytest-cov
py -m pytest --cov=. --cov-branch --cov-report=term-missing --cov-report=xml --cov-fail-under=95
```

## Sign-off Checklist
- [x] DT-024 dependency confirmed.
- [x] Full suite command documented and enforced in CI.
- [x] Branch coverage threshold configured at 95% minimum.
- [x] Windows runbook validation path documented and cross-referenced.
- [x] User guide artifacts (`userguide.md` and `userguide.html`) delivered.
