# twinkle-tempo-melody-pcm-fix work description

## Summary
- Added WAV PCM-aware analysis in the local startup entrypoint so deterministic tempo and melody extraction can use structured signal features when byte-level heuristics are misleading.
- Implemented onset detection and PCM-tempo inference helpers, then integrated them as the preferred path with safe fallback to existing byte-activity logic.
- Implemented PCM melody extraction from detected onsets using active-window zero-crossing pitch estimation, with controlled padding/truncation to preserve note-count behavior.
- Expanded unit tests to cover PCM tempo/melody branches, unsupported WAV sample-width branch handling, and regression behavior for synthetic pulse-based melody inputs resembling Twinkle-like patterns.

## Validation
- `python -m pytest tests/unit/test_local_entrypoints.py -q`
- `python -m pytest -q`
