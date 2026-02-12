# Development_Tasks.md

This plan is designed for delegation with **near-zero merge conflicts** by enforcing strict file-ownership boundaries, sequencing shared contracts first, and parallelizing only work that can proceed independently.

## Planning Principles

1. **Contracts first, implementations second**: shared models/interfaces are finalized before feature implementation.
2. **Single-writer file ownership**: each task owns a clearly bounded file/folder set.
3. **One-direction dependency flow**: upstream deliverables are merged before dependent tasks begin.
4. **Parallel only when boundaries are hard**: parallel tracks must not edit the same files.
5. **Small, mergeable increments**: each task ends in passing tests and reviewable artifacts.

## Branching and Ownership Rules

- Use one short-lived branch per task ID (e.g., `task/DT-014-dashboard-api-projects`).
- A task may edit only the files/folders listed in its ownership scope.
- Changes outside scope require either:
  - a separate prerequisite task, or
  - explicit coordinator approval and a scope amendment.
- Shared files (`modules/shared-contracts`, central config schemas) are edited only in the **foundation phases**.
- Any task that changes contracts must:
  - bump contract version notes,
  - update contract tests,
  - and merge before dependent tasks start.

---

## Phase 0 — Foundation Setup (Serial, No Parallelism)

### DT-001 Repository policy bootstrap
**Depends on:** none  
**Owner scope:**
- `AGENTS.md`
- `Work_Checklist.md` (task checkbox area only)
- `workdescriptions/`

**Deliverables:**
- Confirm workflow policy is current and explicit.
- Add current task completion record.
- Add work description artifact.

### DT-002 Test harness baseline
**Depends on:** DT-001  
**Owner scope:**
- `tests/`

**Deliverables:**
- Stable test discovery and execution conventions.
- Baseline governance tests for scaffold integrity.
- Guidance for unit/integration/performance suite layout.

---

## Phase 1 — Shared Contracts and Interfaces (Serial by Design)

> No downstream module work starts until this phase is merged.

### DT-003 Canonical domain entities v1
**Depends on:** DT-002  
**Owner scope:**
- `modules/shared-contracts/`

**Deliverables:**
- Versioned schemas/interfaces for Project, AudioAsset, Job, StageRun, ScoreRevision.
- Compatibility policy notes.

### DT-004 Score IR v1 contract
**Depends on:** DT-003  
**Owner scope:**
- `modules/shared-contracts/`

**Deliverables:**
- Score IR schema for parts/measures/voices/events and global maps.
- Validation rules and examples.

### DT-005 Worker RPC contracts v1
**Depends on:** DT-004  
**Owner scope:**
- `modules/shared-contracts/`

**Deliverables:**
- Contract definitions for separation/transcription/quantization/engraving calls.
- Error envelope and idempotency key semantics.

### DT-006 Orchestrator stage-state contract
**Depends on:** DT-005  
**Owner scope:**
- `modules/shared-contracts/`
- `modules/orchestrator/` (contract adapter docs only)

**Deliverables:**
- DAG stage status/state machine spec.
- Retry/backoff/resume semantics as shared contract.

---

## Phase 2 — Module Skeletons Against Frozen Contracts (Parallelizable)

> After DT-006 merges, module skeleton implementation can run in parallel with strict ownership.

### Parallel Track A (User-facing web)

#### DT-007 Dashboard API skeleton
**Depends on:** DT-006  
**Owner scope:** `modules/dashboard-api/`

#### DT-008 Dashboard UI skeleton
**Depends on:** DT-006  
**Owner scope:** `modules/dashboard-ui/`

#### DT-009 Editor app skeleton
**Depends on:** DT-006  
**Owner scope:** `modules/editor-app/`

### Parallel Track B (Pipeline core)

#### DT-010 Orchestrator runtime skeleton
**Depends on:** DT-006  
**Owner scope:** `modules/orchestrator/`

#### DT-011 Worker-audio skeleton
**Depends on:** DT-006  
**Owner scope:** `modules/worker-audio/`

#### DT-012 Worker-separation skeleton
**Depends on:** DT-006  
**Owner scope:** `modules/worker-separation/`

#### DT-013 Worker-transcription skeleton
**Depends on:** DT-006  
**Owner scope:** `modules/worker-transcription/`

#### DT-014 Worker-quantization skeleton
**Depends on:** DT-006  
**Owner scope:** `modules/worker-quantization/`

#### DT-015 Worker-engraving skeleton
**Depends on:** DT-006  
**Owner scope:** `modules/worker-engraving/`

### Parallel Track C (Environment enablement)

#### DT-016 Local dev and Windows runbook baseline
**Depends on:** DT-006  
**Owner scope:**
- `infrastructure/`
- `docs/`

---

## Phase 3 — Vertical Slices (Constrained Parallelism)

> Each slice integrates API + orchestrator + one worker path while preserving ownership boundaries by using adapter files.

### DT-017 Draft pipeline slice (A + C + D + E + F minimal)
**Depends on:** DT-007, DT-010, DT-011, DT-013, DT-014, DT-015  
**Owner scope:**
- Adapter/integration files only in module roots (pre-declared paths)
- Integration tests in `tests/integration/`

### DT-018 HQ separation slice
**Depends on:** DT-017, DT-012  
**Owner scope:**
- HQ adapter files + integration tests

### DT-019 Revision/export slice
**Depends on:** DT-017  
**Owner scope:**
- dashboard-api/editor adapter paths + integration tests

---

## Phase 4 — Quality, Observability, and Hardening (Parallelizable by concern)

### DT-020 Observability instrumentation pass
**Depends on:** DT-017  
**Owner scope:** module-local observability files + `tests/integration/`

### DT-021 Reliability and recovery pass
**Depends on:** DT-018  
**Owner scope:** orchestrator + worker failure-path tests

### DT-022 Performance and UX pass
**Depends on:** DT-019  
**Owner scope:** editor performance paths + `tests/performance/`

### DT-023 Security and privacy pass
**Depends on:** DT-019  
**Owner scope:** dashboard-api auth/signed-URL/retention surfaces + tests

---

## Phase 5 — Release Readiness (Serial)

### DT-024 Milestone acceptance (M0/M1/M2/M3 gate checks)
**Depends on:** DT-020..DT-023  
**Owner scope:** `docs/`, release checklists, `tests/`

### DT-025 Final regression and branch coverage gate
**Depends on:** DT-024  
**Owner scope:** `tests/`, CI configs

**Exit criteria:**
- Full suite green.
- Branch coverage report meets policy target (>=95%).
- Windows local runbook validated end-to-end.

---

## Conflict-Avoidance Matrix (Delegation Cheat Sheet)

| Zone | Primary Owners | Parallel-safe with |
|---|---|---|
| `modules/shared-contracts/` | DT-003..DT-006 | none (serial only) |
| `modules/dashboard-api/` | DT-007 (+ slice adapters) | dashboard-ui/editor/workers |
| `modules/dashboard-ui/` | DT-008 | dashboard-api/editor/workers |
| `modules/editor-app/` | DT-009 | dashboard-api/ui/workers |
| `modules/orchestrator/` | DT-010 | ui/editor/individual workers |
| `modules/worker-*/` | DT-011..DT-015 | other workers + ui modules |
| `infrastructure/`, `docs/` | DT-016 | all module skeleton tasks |
| `tests/integration/` | DT-017..DT-023 | with careful file partitioning by slice |
| `tests/performance/` | DT-022 | all except same benchmark files |

## File Partitioning Convention for Parallel Test Work

- Integration tests:
  - `tests/integration/test_draft_pipeline.py` (DT-017)
  - `tests/integration/test_hq_pipeline.py` (DT-018)
  - `tests/integration/test_revision_exports.py` (DT-019)
  - `tests/integration/test_observability.py` (DT-020)
  - `tests/integration/test_recovery.py` (DT-021)
  - `tests/integration/test_security.py` (DT-023)
- Performance tests:
  - `tests/performance/test_editor_latency.py` (DT-022)
  - `tests/performance/test_pipeline_throughput.py` (DT-022)

This one-file-per-task convention minimizes edit collisions while preserving review clarity.
