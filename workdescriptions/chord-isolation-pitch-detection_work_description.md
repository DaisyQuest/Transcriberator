## Summary
Improved worker-transcription pitch detection so deterministic analysis frames can isolate stable pitches and identify chord qualities suitable for downstream notation/edit workflows.

## Work Performed
- Extended `TranscriptionTaskRequest` with optional `analysis_frames` to model per-frame polyphonic pitch activation.
- Extended `TranscriptionTaskResult` to emit `isolated_pitches` and `detected_chords` metadata in addition to legacy result fields.
- Added robust request/frame validation for missing source URI, empty model version, empty frames, and out-of-range MIDI pitches.
- Implemented stable pitch isolation using per-pitch frame counts and thresholding to suppress transient noise.
- Implemented chord matching for major/minor/diminished/augmented/suspended2/suspended4 qualities with root preference based on the frame bass note.
- Added deterministic confidence scoring for analysis-frame execution paths while preserving backward-compatible fallback behavior when no frames are supplied.
- Added a dedicated unit test module with exhaustive branch assertions for default behavior, chord detection variants, invalid/unrecognized shapes, monophonic/polyphonic confidence paths, and validation failures.

## Validation
- Ran focused unit tests for worker-transcription and phase-2 pipeline skeleton compatibility.
- Ran full repository test suite to verify no regressions.
- Attempted branch-coverage command; environment lacks pytest-cov plugin support for `--cov` flags in this setup.
