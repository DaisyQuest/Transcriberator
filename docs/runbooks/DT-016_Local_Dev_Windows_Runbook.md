# DT-016 Local Dev and Windows Runbook Baseline

This runbook establishes the **minimum reliable local development baseline** for Transcriberator, with explicit first-class guidance for Windows contributors.

## Objectives

- Keep local setup repeatable on Windows, macOS, and Linux.
- Keep command examples shell-agnostic when possible.
- Ensure every developer can run lint/tests without hidden dependencies.
- Provide high-signal troubleshooting with observable outcomes.

## Prerequisites

| Capability | Required Version | Windows Notes |
|---|---|---|
| Python | 3.11+ | Install from python.org and enable `Add python.exe to PATH`. |
| Git | 2.40+ | Use Git for Windows with long-path support enabled. |
| Optional: Docker Desktop | Latest stable | Required only for future containerized local stacks. |

## Repository Bootstrap

### PowerShell (Windows)

```powershell
git clone <repo-url> Transcriberator
cd Transcriberator
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

### Bash (macOS/Linux/Git Bash)

```bash
git clone <repo-url> Transcriberator
cd Transcriberator
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

> If script execution policy blocks activation on Windows, run `Set-ExecutionPolicy -Scope Process Bypass` in the current PowerShell session.

## Local Validation Workflow

Run from repository root:

```text
python -m unittest discover -s tests -t .
```

Expected observable signal:
- Test runner exits with code `0`.
- Output includes discovered unit tests across `tests/unit/` and module-level test folders.

## Windows Friction Prevention

1. **Path length safety**
   - Configure Git long paths once:
     ```powershell
git config --global core.longpaths true
```
2. **Line endings**
   - Recommended global config:
     ```powershell
git config --global core.autocrlf true
```
3. **Shell parity**
   - All canonical commands in this repository must run with default PowerShell syntax and plain Python invocations.
4. **No hidden Unix-only dependencies**
   - Avoid `sed`, `awk`, or GNU-only flags in required workflows unless a PowerShell equivalent is documented.

## Troubleshooting Matrix

| Symptom | Likely Cause | Resolution |
|---|---|---|
| `python` not found | PATH not configured | Reinstall Python and enable PATH option. |
| Activation script blocked | Execution policy restriction | Use process-scoped bypass and retry activation. |
| Unit tests fail during discovery | Wrong working directory | Re-run command from repository root. |
| Inconsistent line-ending diffs | Git CRLF mismatch | Align `core.autocrlf` and re-checkout file. |

## Definition of Done for DT-016

- Baseline runbook exists in `docs/` for cross-platform local execution.
- Infrastructure local-dev helper docs exist in `infrastructure/`.
- Automated tests assert runbook presence and required Windows guidance text.
- Checklist and work description artifacts are updated.
