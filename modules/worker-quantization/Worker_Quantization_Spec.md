# Worker_Quantization_Spec.md

## Scope
Quantization/cleanup worker that transforms raw note events into score-legal structures.

## Responsibilities
- Barline enforcement and measure duration correctness.
- Tie/tuplet inference and rhythm cleanup.
- Voice-aware cleanup hooks for polyphonic content.

## Quality Gates
- Deterministic transformations.
- High branch coverage for rhythm edge cases.
