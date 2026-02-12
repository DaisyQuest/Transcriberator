# dt-004-dt-006_shared-contracts-v1_work_description

## Scope completed
Implemented DT-004, DT-005, and DT-006 in dependency order under the required ownership boundaries:
- `modules/shared-contracts/`
- `modules/orchestrator/` (contract adapter docs only)

## DT-004: Score IR v1 contract
- Added machine-readable schema `score_ir.schema.json` covering:
  - parts
  - measures
  - voices
  - events (`note` and `rest` discriminated union)
  - global maps (time signatures, tempo, key signatures)
- Added documentation `Score_IR_v1.md` with:
  - field-level shape
  - validation rules
  - compatibility guidance
- Added examples:
  - valid minimal payload
  - intentionally invalid payload for discriminator rejection behavior

## DT-005: Worker RPC contracts v1
- Added schema `worker_rpc.schema.json` defining:
  - required operations: separation/transcription/quantization/engraving
  - request envelope
  - success/failure response envelope
  - error envelope definition
  - idempotency semantics metadata
- Added documentation `Worker_RPC_v1.md` covering:
  - error envelope categories and retry guidance
  - idempotency key pattern, scope, TTL, and collision handling semantics

## DT-006: Orchestrator stage-state contract
- Added schema `stage_state_contract.schema.json` defining:
  - canonical DAG stage order
  - status set
  - transition records
  - retry/backoff policy fields
  - resume semantics
  - degradation policy surface
- Added docs:
  - shared contract spec `Orchestrator_Stage_State_v1.md`
  - orchestrator adapter notes `modules/orchestrator/Contract_Adapter_Notes.md`

## Test updates
- Expanded `tests/unit/test_shared_contracts_v1.py` to validate:
  - all expected schema files for DT-003..DT-006
  - DT-004 schema internals and examples (valid + invalid discriminator path)
  - DT-005 operation coverage, envelope semantics, and idempotency key rules
  - DT-006 state/retry/resume/degradation contract content
  - presence and required sections of all new docs

## Verification
- Ran full repository test command:
  - `python -m unittest discover -s tests -t .`
