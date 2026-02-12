## Summary
Implemented a layered transcription-detection upgrade in the local dashboard transcription pipeline to substantially improve pitch inference robustness and reduce noisy false positives.

## Work Performed
- Added an RMS energy gate before pitch estimation so low-energy windows are ignored early.
- Added a spectral-peak frequency estimator as a third inference layer alongside zero-crossing and autocorrelation methods.
- Added candidate clustering logic to reconcile multiple inferred frequencies and favor coherent pitch centers.
- Updated segment pitch inference selection logic to combine clustered candidates and deterministic fallbacks.
- Extended unit tests with exhaustive branch coverage for:
  - spectral-peak estimator branches,
  - frequency clustering branches,
  - RMS helper branches,
  - low-RMS short-circuit in pitch inference.

## Validation
- Ran full repository tests to verify no regressions.
- Confirmed all tests pass after layered detection changes.
