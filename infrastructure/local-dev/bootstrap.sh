#!/usr/bin/env bash
set -euo pipefail

echo "[dt-016] Starting local bootstrap (bash)..."

if ! command -v python >/dev/null 2>&1; then
  echo "python executable not found on PATH. Install Python 3.11+ and retry." >&2
  exit 1
fi

if [[ ! -d .venv ]]; then
  echo "[dt-016] Creating virtual environment at .venv"
  python -m venv .venv
else
  echo "[dt-016] Reusing existing .venv"
fi

.venv/bin/python -m pip install --upgrade pip

echo "[dt-016] Bootstrap complete. Activate with 'source .venv/bin/activate'"
