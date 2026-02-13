# dashboard-previewer-instrument-sliders_work_description

## Summary
- Reworked the local dashboard into a preview-first workspace that surfaces a dedicated generation preview panel, quick job-selection links, and richer transcription visibility for iterative parameter tuning.
- Added slider companions for every numeric tuning field while preserving numeric text input editing, with client-side bidirectional synchronization for usability.
- Added instrument profile radio controls (`auto`, `piano`, `acoustic_guitar`, `electric_guitar`, `violin`, `flute`) and wired profile selection into transcription run processing.
- Introduced deterministic instrument-profile normalization/clamping in the local analysis path and persisted selected profile metadata into job summaries.

## Testing
- Updated and expanded `tests/unit/test_local_entrypoints.py` to cover new instrument-profile helpers, dashboard rendering changes, and server-level transcription/profile persistence behavior.
- Ran full unit/integration/performance suite and branch-coverage gate validation.
