# Local Development Infrastructure Baseline (DT-016)

This folder hosts infrastructure-facing assets that define the local development baseline and Windows-ready execution affordances.

## Included Assets

- `bootstrap.ps1`: PowerShell bootstrap helper for Windows.
- `bootstrap.sh`: Bash bootstrap helper for Unix-like systems.
- `env.example`: canonical environment variable template for local development.

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

## Guardrails

- Scripts are intentionally idempotent and safe to re-run.
- Scripts avoid platform-specific package manager assumptions.
- Scripts print high-signal status messages for observability.

## Future Expansion

As DT-017+ lands, this folder can add local service composition (`docker-compose`) and queue/storage emulation setup while preserving Windows parity.
