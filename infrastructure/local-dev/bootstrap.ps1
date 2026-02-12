$ErrorActionPreference = 'Stop'

Write-Host '[dt-016] Starting local bootstrap (PowerShell)...' -ForegroundColor Cyan

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'python executable not found on PATH. Install Python 3.11+ and retry.'
}

if (-not (Test-Path '.venv')) {
    Write-Host '[dt-016] Creating virtual environment at .venv' -ForegroundColor Yellow
    python -m venv .venv
} else {
    Write-Host '[dt-016] Reusing existing .venv' -ForegroundColor DarkYellow
}

$pythonExe = '.venv\Scripts\python.exe'
& $pythonExe -m pip install --upgrade pip | Out-Host

Write-Host '[dt-016] Bootstrap complete. Activate with .\.venv\Scripts\Activate.ps1' -ForegroundColor Green
