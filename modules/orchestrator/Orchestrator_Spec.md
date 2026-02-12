# Orchestrator_Spec.md

## Scope
Central coordinator for DAG-based stage execution and lifecycle tracking.

## Responsibilities
- Stage scheduling and state transitions.
- Retry/backoff and resume semantics.
- Idempotency and checkpoint enforcement.
- Worker RPC dispatch with traceability.

## Quality Gates
- Stage transitions audited in persistence.
- Recovery tests for worker/stage failure cases.
- Queue implementation abstracted (no Redis hard dependency in initial version).
