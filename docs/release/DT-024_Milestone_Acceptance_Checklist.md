# DT-024 Milestone Acceptance Checklist (M0/M1/M2/M3)

## Scope
This checklist implements **DT-024 Milestone acceptance (M0/M1/M2/M3 gate checks)** from `Development_Tasks.md`.

- Dependency baseline: DT-020, DT-021, DT-022, DT-023 must be complete.
- Owner scope: `docs/`, release checklists, `tests/`.
- Verification posture: deterministic repository checks + test suite execution + branch coverage gate.

## Dependency Gate (DT-020..DT-023)

| Dependency | Gate criterion | Verification evidence |
|---|---|---|
| DT-020 Observability instrumentation pass | Work description exists and corresponding WC-TASK is checked. | `workdescriptions/dt-020-observability-instrumentation-pass_work_description.md`, `Work_Checklist.md` |
| DT-021 Reliability and recovery pass | Work description exists and corresponding WC-TASK is checked. | `workdescriptions/dt-021_reliability-and-recovery-pass_work_description.md`, `Work_Checklist.md` |
| DT-022 Performance and UX pass | Work description exists and corresponding WC-TASK is checked. | `workdescriptions/dt-022-performance-and-ux-pass_work_description.md`, `Work_Checklist.md` |
| DT-023 Security and privacy pass | Work description exists and corresponding WC-TASK is checked. | `workdescriptions/dt-023-security-privacy-pass_work_description.md`, `Work_Checklist.md` |

## Milestone Gate Matrix

### M0 Gate (FS-060)
**Goal:** schema, upload+normalize, draft monophonic pipeline, minimal editor.

Acceptance checks:
1. Shared contract schemas exist in `modules/shared-contracts/schemas/v1/`.
2. Draft pipeline integration tests pass (`tests/integration/test_draft_pipeline.py`).
3. Minimal editor skeleton and tests exist (`modules/editor-app/src/editor_app_skeleton.py`, `modules/editor-app/tests/test_editor_app_skeleton.py`).
4. Baseline discovery test command passes: `python -m unittest discover -s tests -t .`.

### M1 Gate (FS-061)
**Goal:** notation view, undo/redo, quantize tooling, revision history.

Acceptance checks:
1. Editor skeleton includes note editing + revision behavior validated by module tests.
2. Quantization worker skeleton exists (`modules/worker-quantization/worker_quantization_skeleton.py`) and is validated by pipeline skeleton tests.
3. Revision/export integration tests pass (`tests/integration/test_revision_exports.py`).

### M2 Gate (FS-062)
**Goal:** HQ separation path, stem targeting, improved tempo/barline handling.

Acceptance checks:
1. HQ pipeline adapter exists and deterministic tests pass (`modules/orchestrator/hq_pipeline_adapter.py`, `tests/integration/test_hq_pipeline.py`).
2. Separation worker skeleton exists (`modules/worker-separation/worker_separation_skeleton.py`).
3. Recovery integration tests pass for failure-path handling (`tests/integration/test_recovery.py`).

### M3 Gate (FS-063)
**Goal:** polyphonic modes, voice tools, improved cleanup.

Acceptance checks:
1. Current repo state includes polyphonic-readiness primitives in editor state and score revision/export path tests.
2. Security/privacy and observability suites pass for release-hardening baseline (`tests/integration/test_security.py`, `tests/integration/test_observability.py`).
3. Branch coverage gate is validated at >=95% (`python -m coverage run --branch -m unittest discover -s tests -t .` + `python -m coverage report -m`).

## Release Readiness Execution Order
1. Validate dependency gate (DT-020..DT-023 evidence).
2. Run full unit+integration+performance suites via discovery.
3. Run branch coverage report and enforce >=95%.
4. Mark milestone checklist rows in `Work_Checklist.md` (WC-060..WC-063) as complete.
5. Record DT-024 implementation summary in `/workdescriptions`.

## Commands

```bash
python -m unittest discover -s tests -t .
python -m coverage run --branch -m unittest discover -s tests -t .
python -m coverage report -m
```
