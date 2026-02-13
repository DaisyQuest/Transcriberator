## Summary
Implemented a richer local transcription workflow focused on pitch recognition quality, UI control depth, and one-click local startup for dashboard+editor.

## Work Performed
- Expanded dashboard tuning settings with advanced noise suppression and weighted pitch-estimator controls.
- Added pre-submit cleanup UX with waveform preview and exclusion-range selection before transcription.
- Added server-side exclusion-range parsing/merging and audio-range removal before analysis.
- Improved pitch inference pipeline to include configurable noise suppression and weighted frequency fusion.
- Added one-click dual-surface launcher (`run-all.sh`, `run-all.ps1`, and `run_everything.py`) to run dashboard and editor together.
- Updated runbook guidance and local settings defaults.
- Expanded unit coverage for new branches and launcher behaviors.

## Validation
- Ran full repository test suite with `python -m unittest discover -s tests -t .` and confirmed passing.
