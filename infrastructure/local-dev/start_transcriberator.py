"""Cross-platform local entrypoint for starting the Transcriberator skeleton system."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


class StartupError(RuntimeError):
    """Raised when startup smoke execution cannot complete successfully."""


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise StartupError(f"Unable to load module spec for {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _parse_fail_stages(raw_stages: list[str]) -> set[str]:
    return {stage.strip() for stage in raw_stages if stage.strip()}


def run_startup(
    *,
    mode: str,
    owner_id: str,
    project_name: str,
    fail_stages: set[str] | None = None,
    allow_hq_degradation: bool = True,
) -> dict[str, Any]:
    root = _repo_root()

    dashboard_api = _load_module(
        "dashboard_api_skeleton", root / "modules" / "dashboard-api" / "src" / "dashboard_api_skeleton.py"
    )
    orchestrator = _load_module("orchestrator_runtime", root / "modules" / "orchestrator" / "runtime_skeleton.py")

    normalized_mode = mode.strip().lower()
    if normalized_mode not in {"draft", "hq"}:
        raise StartupError("Mode must be either 'draft' or 'hq'.")

    api_service = dashboard_api.DashboardApiSkeleton()
    session = api_service.issue_access_token(owner_id=owner_id)
    project = api_service.create_project_authorized(token=session.token, owner_id=owner_id, name=project_name)
    job = api_service.create_job(project_id=project.id, mode=normalized_mode)

    mode_enum = orchestrator.JobMode.HQ if normalized_mode == "hq" else orchestrator.JobMode.DRAFT
    runtime = orchestrator.OrchestratorRuntime()
    fail_stages = fail_stages or set()

    result = runtime.run_job(
        orchestrator.OrchestratorJobRequest(
            job_id=job.id,
            mode=mode_enum,
            allow_hq_degradation=allow_hq_degradation,
        ),
        fail_stages=fail_stages,
    )

    if result.final_status is orchestrator.StageStatus.FAILED:
        raise StartupError(
            "System startup smoke run failed. "
            "Review stage records for errors and rerun without simulated failure flags."
        )

    return {
        "ownerId": owner_id,
        "projectId": project.id,
        "jobId": job.id,
        "mode": normalized_mode,
        "finalStatus": result.final_status.value,
        "stages": [
            {
                **asdict(record),
                "status": record.status.value,
            }
            for record in result.stage_records
        ],
    }


def _format_summary(summary: dict[str, Any]) -> str:
    lines = [
        "[entrypoint] Transcriberator startup smoke run succeeded.",
        f"[entrypoint] owner={summary['ownerId']} project={summary['projectId']} job={summary['jobId']}",
        f"[entrypoint] mode={summary['mode']} finalStatus={summary['finalStatus']}",
        "[entrypoint] stage timeline:",
    ]
    lines.extend(
        f"  - {stage['stage_name']}: {stage['status']} ({stage['detail']})" for stage in summary["stages"]
    )
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch local Transcriberator skeleton with deterministic smoke run.")
    parser.add_argument("--mode", default="draft", choices=["draft", "hq"], help="Pipeline mode to execute.")
    parser.add_argument("--owner-id", default="local-owner", help="Owner id used for startup smoke project/job creation.")
    parser.add_argument("--project-name", default="Local Startup", help="Project name used during startup smoke run.")
    parser.add_argument(
        "--fail-stage",
        action="append",
        default=[],
        help="Optional stage name(s) to simulate failure for local troubleshooting.",
    )
    parser.add_argument(
        "--no-hq-degradation",
        action="store_true",
        help="Disable HQ degradation fallback for source separation failures.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output instead of human-friendly summary.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        summary = run_startup(
            mode=args.mode,
            owner_id=args.owner_id,
            project_name=args.project_name,
            fail_stages=_parse_fail_stages(args.fail_stage),
            allow_hq_degradation=not args.no_hq_degradation,
        )
    except StartupError as exc:
        print(f"[entrypoint] ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(_format_summary(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
