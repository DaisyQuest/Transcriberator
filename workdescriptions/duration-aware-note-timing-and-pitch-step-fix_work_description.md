# duration-aware-note-timing-and-pitch-step-fix work description

## Summary
- Fixed local transcription timing capture by passing PCM segment durations through `_derive_melody_pitches` into the audio analysis profile.
- Normalized detected note durations to the estimated song length so emitted durations match source duration and no longer stretch unexpectedly.
- Updated Sheet MusicXML and MIDI generation to consume duration metadata, emitting per-note durations and explicit tempo metadata in both artifact types.
- Corrected MIDI pitch-step mapping to include sharps (`C#`, `D#`, etc.) so pitch names stay accurate.
- Added regression tests for duration normalization and sharp-name mapping, and expanded artifact-generation assertions for tempo + duration behavior.

## Validation
- `python -m pytest tests/unit/test_local_entrypoints.py -q`
