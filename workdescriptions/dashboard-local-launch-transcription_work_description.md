# dashboard-local-launch-transcription_work_description

## Context
Users reported that the standard local entrypoint only executed a smoke run and exited, which blocked real interactive dashboard usage and end-user audio transcription workflows.

## What Changed
1. Reworked `infrastructure/local-dev/start_transcriberator.py` so default behavior starts a local HTTP dashboard server (instead of only running smoke mode).
2. Added upload/transcription web flow:
   - HTML dashboard with MP3/WAV/FLAC upload form.
   - Mode selector (Draft/HQ).
   - Job history cards with stage timeline output.
3. Kept deterministic smoke-run behavior behind `--smoke-run` for CI and diagnostics.
4. Added host/port flags for easier local/Windows startup control.
5. Expanded unit tests to cover:
   - New mode and filename validation branches.
   - Dashboard server startup path from `main`.
   - End-to-end GET + multipart POST submission behavior.
   - Existing smoke-run and wrapper/doc expectations.
6. Updated user-facing docs/runbook to describe dashboard-first startup and smoke-run troubleshooting flags.

## Validation
- Full repository pytest suite run successfully after changes.
- Added screenshot artifact of the new dashboard surface.

## Dependency Mapping
- `DT-016` (Local dev + Windows runbook): updated startup UX and runbook commands.
- `DT-008` (Dashboard UI skeleton surface intent): provided a user-friendly local dashboard launch experience.
- `DT-017` (Draft vertical flow): preserved and exposed end-to-end stage execution in interactive local flow.
