# Contract_Adapter_Notes.md

## Purpose
Adapter-facing notes for orchestrator module consumers of shared stage-state contracts.

## Source of Truth
- Stage-state contract: `modules/shared-contracts/Orchestrator_Stage_State_v1.md`
- Machine schema: `modules/shared-contracts/schemas/v1/stage_state_contract.schema.json`
- Worker error categories: `modules/shared-contracts/Worker_RPC_v1.md`

## Adapter Expectations
1. **Do not redefine states locally.** Import canonical status names and stage order.
2. **Enforce transition guards** before persistence updates.
3. **Persist retry metadata** (attempt count + next scheduled retry timestamp).
4. **Respect idempotency envelope** for all worker dispatches.
5. **Apply degradation policy** for HQ separation failure when allowed by contract.

## Minimal Runtime Checklist
- Validate inbound worker responses against the shared error envelope contract.
- Emit orchestrator logs with stage, attempt, transition, and idempotency key fields.
- Persist checkpoint artifacts before transitioning stage to `succeeded`.
- Resume workflows only from latest successful stage with durable artifacts.
