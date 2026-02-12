# Worker_RPC_v1.md

## Purpose
Defines DT-005 shared worker RPC contracts for:
- `separation`
- `transcription`
- `quantization`
- `engraving`

## Schema Location
- `modules/shared-contracts/schemas/v1/worker_rpc.schema.json`

## Contract Envelope
Each operation uses a common envelope:
- `request`
  - `idempotencyKey`
  - `jobId`
  - `stageRunId`
  - `inputArtifactUris[]`
  - `config` (operation-specific object)
  - optional `traceContext`
- `response`
  - `ok` boolean discriminator
  - when `ok=true`: `outputArtifactUris[]` required
  - when `ok=false`: `error` envelope required

## Error Envelope (v1)
Required fields:
- `code`
- `message`
- `retryable`
- `category` (`validation`, `dependency`, `timeout`, `resource`, `internal`)

Optional field:
- `details` object

Guidance:
- `validation` errors are non-retryable unless producer bug is fixed.
- `dependency`, `timeout`, and `resource` may be retryable according to orchestrator policy.

## Idempotency Key Semantics
- Pattern: `^[A-Za-z0-9:_\-]{16,128}$`
- Scope: unique per `jobId + stageRunId + operation`.
- TTL: 1..168 hours (`ttlHours` in schema definition metadata).
- Collision behavior:
  1. `return_cached_success` if exact matching successful request exists.
  2. `reject_mismatched_payload` when key is reused with a non-equivalent payload.
  3. `allow_retry_if_failed` for previously failed attempts when policy permits.

## Operation Notes
- `separation`: input expected to be normalized full-mix audio artifacts.
- `transcription`: input may be full-mix or separated stems.
- `quantization`: input expected to be raw note-event IR.
- `engraving`: input expected to be cleaned notation IR/MusicXML candidate.

## Compatibility Notes
- Adding optional operation config fields is minor.
- Changing idempotency scope semantics or key format is major.
- Changing error category enum values is major.
