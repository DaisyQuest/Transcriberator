"""One-click launcher for local dashboard + editor surfaces."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run dashboard and editor together.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--dashboard-port", type=int, default=4173)
    parser.add_argument("--editor-port", type=int, default=3000)
    parser.add_argument("--mode", choices=["draft", "hq"], default="draft")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    root = _repo_root()

    editor_cmd = [sys.executable, "-m", "http.server", str(args.editor_port), "--bind", args.host, "--directory", str(root)]
    dashboard_cmd = [
        sys.executable,
        str(root / "infrastructure" / "local-dev" / "start_transcriberator.py"),
        "--host",
        args.host,
        "--port",
        str(args.dashboard_port),
        "--mode",
        args.mode,
        "--editor-url",
        f"http://{args.host}:{args.editor_port}",
    ]

    print(f"[run-all] Starting editor on http://{args.host}:{args.editor_port}")
    editor_proc = subprocess.Popen(editor_cmd, cwd=root)
    time.sleep(0.5)
    print(f"[run-all] Starting dashboard on http://{args.host}:{args.dashboard_port}")
    dashboard_proc = subprocess.Popen(dashboard_cmd, cwd=root)

    try:
        return dashboard_proc.wait()
    except KeyboardInterrupt:
        print("\n[run-all] Shutting down...")
        return 130
    finally:
        for proc in (dashboard_proc, editor_proc):
            if proc.poll() is None:
                proc.terminate()
        for proc in (dashboard_proc, editor_proc):
            if proc.poll() is None:
                proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
