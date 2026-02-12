# Orchestrator_Stage_State_v1.md

## Purpose
Defines DT-006 shared contract for orchestrator DAG stage state transitions, retries, backoff, and resume semantics.

## Schema Location
- `modules/shared-contracts/schemas/v1/stage_state_contract.schema.json`

## Canonical Stage Order
1. `decode_normalize`
2. `source_separation`
3. `tempo_map`
4. `transcription`
5. `quantization_cleanup`
6. `notation_generation`
7. `engraving`

## Stage Status Set
- `pending`
- `queued`
- `running`
- `succeeded`
- `failed`
- `retry_wait`
- `cancelled`
- `skipped`

## Allowed Transition Semantics
Required transition intents include:
- `pending -> queued`
- `queued -> running`
- `running -> succeeded`
- `running -> failed`
- `failed -> retry_wait` (retryable and attempt budget remains)
- `retry_wait -> queued` (backoff timer elapsed)
- `running -> cancelled` (external cancellation)
- `running -> skipped` (stage bypass under policy, e.g., Draft mode for separation)

Terminal statuses for a stage run:
- `succeeded`
- `cancelled`
- `skipped`
- `failed` when retry budget exhausted

## Retry/Backoff Contract
- `backoffStrategy`: exponential
- bounded by `baseDelaySeconds` and `maxDelaySeconds`
- `jitter`: full or decorrelated
- retries apply only to retryable categories (`dependency`, `timeout`, `resource`) and while `attempt < maxAttempts`

## Resume Semantics
- Resume anchor: `latest_successful_stage`
- Checkpoint requirement: prior successful stages must have durable output artifact references.
- Re-entry requirement: repeated execution for a stage/input tuple must be idempotent.

## Graceful Degradation (HQ -> Draft-like)
When `source_separation` fails in HQ mode and degradation policy permits:
- mark separation as `skipped` after failure handling,
- continue downstream stages with full-mix input artifacts.

## Compatibility Notes
- Adding optional metadata fields is minor.
- Changing status enum, transition graph meaning, or retry policy behavior is major.
