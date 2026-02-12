$ErrorActionPreference = 'Stop'

Set-Location -Path $PSScriptRoot
Write-Host '[entrypoint] Launching Transcriberator (PowerShell wrapper)...' -ForegroundColor Cyan

$pythonExe = 'python'
if (Test-Path '.venv\Scripts\python.exe') {
    $pythonExe = '.venv\Scripts\python.exe'
}

& $pythonExe 'infrastructure/local-dev/start_transcriberator.py' @args
