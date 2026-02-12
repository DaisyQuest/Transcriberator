# Transcriberator User Guide

> A fast, production-minded guide for creators, transcribers, and hobbyists using the Transcriberator draft and HQ workflows.

## Table of Contents
1. [Quick Start](#quick-start)
2. [Standard Entrypoints (Windows/Linux)](#standard-entrypoints-windowslinux)
3. [System Modes](#system-modes)
4. [End-to-End Workflow](#end-to-end-workflow)
5. [Observability and Quality Signals](#observability-and-quality-signals)
6. [Security and Privacy Controls](#security-and-privacy-controls)
7. [Windows Local Runbook Alignment](#windows-local-runbook-alignment)
8. [Troubleshooting](#troubleshooting)

## Quick Start
- Upload an audio file in **MP3**, **WAV**, or **FLAC** format.
- Select mode:
  - **Draft** for fastest turnaround.
  - **HQ** for higher-quality processing with optional separation.
- Track stage progress and status from dashboard job rows.
- Open editor views to refine notation and timing.
- Export output artifacts (MusicXML primary; MIDI/PDF/PNG as available in your configured pipeline).


## Standard Entrypoints (Windows/Linux)
Use the repository-root wrappers to launch the system consistently across environments.

### Linux/macOS/Git Bash
```bash
./start.sh --mode draft
```

### Windows PowerShell
```powershell
.\start.ps1 -mode hq
```

Both wrappers call `infrastructure/local-dev/start_transcriberator.py`, which guarantees startup by running a deterministic end-to-end smoke path (token issuance, project creation, job creation, orchestration stage execution).

Helpful flags:
- `--json` for machine-readable startup output.
- `--fail-stage <stage-name>` to simulate startup-stage failures.
- `--no-hq-degradation` to force HQ source-separation failures to surface as hard startup errors.

## System Modes
### Draft
- Minimal-latency default flow.
- Prioritizes fast stage progression and predictable artifacts.
- Recommended for early iterations and rough arrangement edits.

### HQ
- Includes separation-aware behavior and stronger correction paths.
- Applies graceful fallback behavior where configured.
- Recommended for final pass and publishing exports.

## End-to-End Workflow
1. Create a project and issue a processing job.
2. Watch stage progression and retention-safe artifact links.
3. Open the editor to quantize, adjust notes, and checkpoint revisions.
4. Validate confidence overlays and operational metrics.
5. Export and review release artifacts.

## Observability and Quality Signals
- Stage-level metrics are designed to stay deterministic and reviewable.
- Logs and status payloads are intended for branch-complete testing, not opaque black-box output.
- Performance budget targets should be validated with repository performance tests before release tagging.

## Security and Privacy Controls
- Use authenticated owner-scoped access tokens for API surfaces.
- Prefer signed URL patterns for artifact retrieval.
- Respect retention configuration and disposition logic (retain/archive/delete behavior).

## Windows Local Runbook Alignment
Use the canonical runbook at:
- `docs/runbooks/DT-016_Local_Dev_Windows_Runbook.md`

Suggested Windows command sequence:
1. `py -m pip install pytest pytest-cov`
2. `py -m pytest --cov=. --cov-branch --cov-report=term-missing --cov-fail-under=95`

## Troubleshooting
- **Import errors during test discovery**: Ensure pytest import mode is `importlib` (configured in `pytest.ini`).
- **Coverage gate fails**: add missing branch tests before merging.
- **Windows path issues**: run commands from repository root and avoid mixed shell assumptions.

---

For release gate details, see `docs/release/DT-025_Final_Regression_Coverage_Gate.md`.
