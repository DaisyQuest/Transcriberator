# mp3-xing-vbri-duration-parser work description

## Summary
- Extended MP3 duration inference in `infrastructure/local-dev/start_transcriberator.py` to read VBR metadata before frame-walk estimation.
- Added `Xing`/`Info` parsing using first-frame side-info positioning (including CRC-aware side-info sizing) to derive duration from `total_frames`.
- Added `VBRI` parsing via known candidate offsets (`0x24` and side-info-derived offset) to derive duration when Xing/Info is unavailable.
- Kept deterministic frame-based fallback for streams without VBR metadata, with relaxed per-frame tolerance and bounded resync attempts.
- Added unit coverage for both Xing and VBRI duration inference paths in `tests/unit/test_local_entrypoints.py`.

## Validation
- `tests/unit/test_local_entrypoints.py` coverage updates for `_estimate_audio_duration_seconds` metadata branches.
