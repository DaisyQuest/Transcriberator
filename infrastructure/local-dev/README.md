# Local Development Infrastructure Baseline (DT-016)

This folder hosts infrastructure-facing assets that define the local development baseline and Windows-ready execution affordances.

## Included Assets

- `bootstrap.ps1`: PowerShell bootstrap helper for Windows.
- `bootstrap.sh`: Bash bootstrap helper for Unix-like systems.
- `env.example`: canonical environment variable template for local development.
- `start_transcriberator.py`: canonical cross-platform Python startup entrypoint.

## Usage

### Windows (PowerShell)

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\infrastructure\local-dev\bootstrap.ps1
```

### Bash

```bash
bash infrastructure/local-dev/bootstrap.sh
```

## Standard System Entrypoints

After bootstrap, launch the local skeleton system using one of the repository-root wrappers:

### Linux/macOS/Git Bash

```bash
./start.sh --mode draft --host 127.0.0.1 --port 4173
```

### Windows PowerShell

```powershell
.\start.ps1 -mode hq -host 127.0.0.1 -port 4173
```

Both wrappers delegate to:

```text
python infrastructure/local-dev/start_transcriberator.py
```

Use `--smoke-run --json` for machine-readable one-shot validation and `--smoke-run --fail-stage <stage-name>` for startup troubleshooting drills.

## Guardrails

- Scripts are intentionally idempotent and safe to re-run.
- Scripts avoid platform-specific package manager assumptions.
- Scripts print high-signal status messages for observability.

## Future Expansion

As DT-017+ lands, this folder can add local service composition (`docker-compose`) and queue/storage emulation setup while preserving Windows parity.
