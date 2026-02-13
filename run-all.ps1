$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot
$pythonExe = 'python'
if (Test-Path '.venv\Scripts\python.exe') {
    $pythonExe = '.venv\Scripts\python.exe'
}
& $pythonExe 'infrastructure/local-dev/run_everything.py' @args
