# long-audio-duration-and-editor-link_work_description

## Summary
- Diagnosed long-audio truncation in local transcription generation: melody event count was previously capped to 32 notes and was primarily byte-size driven, which flattened >2 minute uploads into short ~seconds-equivalent outputs.
- Reworked local audio analysis to estimate duration (WAV metadata when available, format-aware byte-rate fallback otherwise) and derive note counts from duration + estimated tempo, lifting the effective cap to support long uploads.
- Added stronger output observability by including estimated duration and derived note count in generated transcription text and by surfacing per-job audio summary metrics directly on dashboard cards.
- Added an explicit editor app URL to dashboard output (global link and per-job deep-link) and CLI/config support via `--editor-url`.
- Expanded unit/integration-like entrypoint tests to cover new duration estimation branches, new melody-scaling behavior, parser default behavior, and updated dashboard rendering fields.

## Files Changed
- `infrastructure/local-dev/start_transcriberator.py`
- `tests/unit/test_local_entrypoints.py`
- `Work_Checklist.md`

## Validation
- `pytest -q tests/unit/test_local_entrypoints.py`
- `pytest -q`
- `pytest --cov=infrastructure/local-dev/start_transcriberator.py --cov-report=term-missing -q tests/unit/test_local_entrypoints.py` *(fails in current environment because pytest-cov is not installed)*
