# mp3-musicxml-duration-and-parser-fix work description

## Summary
- Fixed MusicXML note-duration conversion to scale note seconds to quarter-note beats with `duration_seconds * 60 / tempo`, which prevents `MusicXML` output from doubling recording time.
- Hardened `_estimate_mp3_duration_seconds` to tolerate VBR and frame-header rate changes while walking MP3 frames instead of assuming constant bitrate/frame format.
- Kept parser fallback behavior for invalid/short MP3 streams so non-MP3/unknown formats fall back to byte-rate heuristics.
- Updated regression tests that were asserting old legacy note names/durations so the suite reflects corrected pitch-step mapping and realistic MP3 fixture behavior.

## Validation
- `C:\Users\tabur\AppData\Local\Programs\Python\Python311\python.exe -m unittest tests.unit.test_local_entrypoints`
