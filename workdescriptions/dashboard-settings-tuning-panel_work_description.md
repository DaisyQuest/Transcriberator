## Summary
Added a configurable dashboard Settings panel for local tuning workflows, loading deterministic defaults from a predictable JSON config file and applying those values directly to pitch-detection inference paths.

## Work Performed
- Added `infrastructure/local-dev/dashboard_settings.json` as the canonical predictable defaults file for tuning behavior.
- Extended local entrypoint configuration (`DashboardServerConfig`) and CLI parsing with `--settings-path` support.
- Implemented `DashboardTuningSettings` plus normalization/loading helpers to safely parse, clamp, and reorder tuning ranges from config/user inputs.
- Added a new dashboard `/settings` POST route and UI panel to edit RMS gate, frequency range, cluster tolerance, and MIDI pitch floor/ceiling values.
- Wired active tuning settings into Stage-D local pitch inference pathways (`_analyze_audio_bytes`, PCM melody extraction, frequency estimators, clustering, and MIDI range clamping).
- Hardened artifact/transcription writes by re-creating upload directories at write time to avoid race-related file-missing conditions.
- Updated local-dev infrastructure docs to include the new predictable settings asset and CLI usage.
- Expanded unit tests with exhaustive branch checks for settings defaults, invalid payload fallback, normalization clamping/reordering, render output, settings route behavior, and parser/server config propagation.

## Validation
- Ran targeted local entrypoint unit tests (including new settings coverage).
- Ran full repository test suite to verify no regressions.
- Captured a dashboard screenshot showing the new Settings panel.
