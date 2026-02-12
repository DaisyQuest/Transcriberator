## Summary
Added deterministic instrument presets in the worker-transcription skeleton so detection can better differentiate common acoustic profiles (acoustic guitar, electric guitar, piano, flute, violin) and produce explicit instrument metadata for downstream workflows.

## Work Performed
- Extended `TranscriptionTaskRequest` with `instrument_preset` to allow caller-directed instrument targeting (`auto` by default).
- Extended `TranscriptionTaskResult` with `detected_instrument` and `applied_preset` for observability/debugging and clearer downstream behavior.
- Added preset validation with strict allow-listing to prevent silent fallback when invalid presets are supplied.
- Implemented deterministic auto-instrument detection using pitch-range fit plus chord/polyphony affinity scoring across preset profiles.
- Preserved backward-compatible empty-analysis behavior while still surfacing preset metadata in fallback results.
- Expanded `tests/unit/test_worker_transcription_chords.py` to cover:
  - new result metadata fields,
  - invalid preset validation failures,
  - auto-detection for flute and acoustic guitar scenarios,
  - manual preset override behavior,
  - candidate scoring mono vs polyphonic branch behavior,
  - compatibility with existing chord/pitch-isolation tests.

## Validation
- Ran focused worker-transcription and dependent skeleton/integration tests.
- Ran full repository test suite (`pytest -q`) to ensure no regressions.
- Attempted branch coverage run with `pytest --cov` flags; command is unsupported in this environment because `pytest-cov` options are unavailable.
