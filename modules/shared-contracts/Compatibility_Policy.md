# Compatibility_Policy.md

## Scope
This policy governs compatibility for all schemas in `modules/shared-contracts/schemas/`.

## Compatibility Contract
1. **Patch changes** may tighten documentation only (no schema semantics changes).
2. **Minor changes** may add optional fields and optional enum values only.
3. **Major changes** are required for:
   - required field additions
   - field removals
   - type changes
   - enum value removals
   - stronger validation that can invalidate existing payloads

## Deprecation Rules
- Mark fields as deprecated in documentation for at least one minor release before removal.
- Deprecated fields must remain accepted by validators until the next major release.

## Validation and Change Control
Any shared contract PR must include:
- Updated schema files.
- Documentation updates in `Domain_Entities_v1.md` (or successor version doc).
- Test updates in `tests/unit/test_shared_contracts_v1.py`.
- A compatibility note in the PR body summarizing whether change is patch/minor/major.

## Consumer Expectations
- Producers must emit payloads valid against the currently published major version.
- Consumers must ignore unknown fields to support forward-compatible optional additions.
- All timestamps must remain RFC3339-compatible strings.
