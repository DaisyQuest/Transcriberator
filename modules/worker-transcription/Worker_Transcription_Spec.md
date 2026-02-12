# Worker_Transcription_Spec.md

## Scope
Transcription worker for onset/pitch/offset inference and tempo-aligned note event generation.

## Responsibilities
- Monophonic and polyphonic mode support paths.
- Emit intermediate note-event representations.
- Report confidence scores for UI overlays.

## Quality Gates
- Golden fixture coverage for known melodic and chordal patterns.
- Model/version metadata emitted with each output.
