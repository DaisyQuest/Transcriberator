# Worker_Separation_Spec.md

## Scope
Optional HQ separation worker for stem extraction.

## Responsibilities
- Separate input into target stems.
- Emit per-stem artifacts with provenance metadata.
- Return quality metadata for downstream selection.

## Quality Gates
- Failure handling supports HQ graceful fallback.
- Resource limits and timeout protections enforced.
