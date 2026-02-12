## Summary
Expanded local transcription output with a structured reasoning trace so debugging pitch/key/tempo decisions is much easier during dashboard and artifact review.

## Work Performed
- Extended `AudioAnalysisProfile` with a `reasoning_trace` field that stores human-readable diagnostic lines.
- Added `_build_reasoning_trace` to summarize tuning inputs, melodic evidence, contour/tonal evidence, and a confidence hint.
- Added `_derive_reasoning_confidence_hint` to provide deterministic normalized confidence signals across melody-quality branches.
- Wired reasoning generation into `_analyze_audio_bytes` so every produced profile carries explicit reasoning context.
- Updated `_build_transcription_text_with_analysis` to include a dedicated `Reasoning trace` section in output text.
- Added comprehensive unit tests for empty/non-empty reasoning branches, confidence-hint bounds/clamping behavior, and output rendering coverage.

## Validation
- Ran focused unit tests for reasoning trace helpers and transcription text rendering.
- Ran expanded local-entrypoint + worker-transcription test suites.
- Ran full repository test suite with all tests passing.
