"""Cross-platform local entrypoint for starting the Transcriberator skeleton system."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import html
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any
from urllib.parse import parse_qs, urlparse
import uuid


class StartupError(RuntimeError):
    """Raised when startup execution cannot complete successfully."""


@dataclass(frozen=True)
class DashboardServerConfig:
    host: str
    port: int
    owner_id: str
    mode: str
    allow_hq_degradation: bool


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


def _validate_mode(mode: str) -> str:
    normalized_mode = mode.strip().lower()
    if normalized_mode not in {"draft", "hq"}:
        raise StartupError("Mode must be either 'draft' or 'hq'.")
    return normalized_mode


def _validate_audio_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    if not name:
        raise StartupError("Uploaded audio file must include a file name.")

    extension = Path(name).suffix.lower()
    if extension not in {".mp3", ".wav", ".flac"}:
        raise StartupError("Uploaded file must use one of: .mp3, .wav, .flac")
    return name


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

    normalized_mode = _validate_mode(mode)

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


def _build_transcription_text(*, audio_file: str, mode: str, stages: list[dict[str, Any]]) -> str:
    stage_lines = "\n".join(
        f"- {stage['stage_name']}: {stage['status']} ({stage['detail']})"
        for stage in stages
    )
    return (
        f"Transcription draft for {audio_file}\n"
        f"Mode: {mode}\n"
        "\n"
        "Pipeline timeline\n"
        f"{stage_lines}\n"
        "\n"
        "Notes\n"
        "- Edit this text directly in the dashboard and save to keep local revisions.\n"
    )


def _render_page(*, owner_id: str, default_mode: str, jobs: list[dict[str, Any]], message: str = "") -> str:
    rows = []
    for job in jobs:
        stage_rows = "".join(
            f"<li><strong>{html.escape(stage['stage_name'])}</strong>: {html.escape(stage['status'])} — {html.escape(stage['detail'])}</li>"
            for stage in job["stages"]
        )
        rows.append(
            "<article class='job-card'>"
            f"<h3>{html.escape(job['audioFile'])}</h3>"
            f"<p><strong>Job:</strong> {html.escape(job['jobId'])} | <strong>Mode:</strong> {html.escape(job['mode'])} | "
            f"<strong>Status:</strong> {html.escape(job['finalStatus'])}</p>"
            f"<p><strong>Submitted:</strong> {html.escape(job['submittedAtUtc'])}</p>"
            f"<p><strong>Transcription output:</strong> <code>{html.escape(job['transcriptionPath'])}</code><br/>"
            f"<a href='/outputs/transcription?job={html.escape(job['jobId'])}' target='_blank' rel='noopener'>View raw output</a></p>"
            "<form action='/edit-transcription' method='post'>"
            f"<input type='hidden' name='job_id' value='{html.escape(job['jobId'])}'/>"
            "<label><strong>Edit transcription:</strong><br/>"
            f"<textarea name='transcription_text' rows='10' style='width:100%;font-family:monospace'>{html.escape(job['transcriptionText'])}</textarea>"
            "</label><br/>"
            "<button type='submit'>Save transcription edits</button>"
            "</form>"
            f"<ol>{stage_rows}</ol>"
            "</article>"
        )

    jobs_markup = "\n".join(rows) if rows else "<p>No transcription jobs submitted yet.</p>"
    selected_draft = "selected" if default_mode == "draft" else ""
    selected_hq = "selected" if default_mode == "hq" else ""

    return f"""<!doctype html>
<html lang='en'>
<head>
  <meta charset='utf-8'>
  <title>Transcriberator Local Dashboard</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2rem auto; max-width: 960px; line-height: 1.4; }}
    h1 {{ margin-bottom: 0.25rem; }}
    .hint {{ color: #555; margin-top: 0; }}
    form {{ border: 1px solid #ddd; padding: 1rem; border-radius: 8px; background: #fafafa; }}
    .notice {{ background: #ecfeff; border: 1px solid #0891b2; padding: 0.75rem; border-radius: 8px; margin-bottom: 1rem; }}
    .job-card {{ border: 1px solid #e5e7eb; border-radius: 8px; padding: 1rem; margin-top: 1rem; }}
    textarea {{ margin-top: 0.5rem; }}
    button {{ padding: 0.5rem 1rem; }}
  </style>
</head>
<body>
  <h1>Transcriberator Dashboard</h1>
  <p class='hint'>Owner: <strong>{html.escape(owner_id)}</strong>. Upload MP3/WAV/FLAC to run a full local transcription pipeline.</p>
  {f"<div class='notice'>{html.escape(message)}</div>" if message else ''}
  <form action='/transcribe' method='post' enctype='multipart/form-data'>
    <label for='audio'>Audio file:</label><br/>
    <input id='audio' type='file' name='audio' accept='.mp3,.wav,.flac,audio/*' required/><br/><br/>
    <label for='mode'>Mode:</label>
    <select id='mode' name='mode'>
      <option value='draft' {selected_draft}>Draft (fast)</option>
      <option value='hq' {selected_hq}>HQ (includes separation)</option>
    </select><br/><br/>
    <button type='submit'>Start transcription</button>
  </form>

  <h2>Recent jobs</h2>
  {jobs_markup}
</body>
</html>
"""


def _redirect(handler: BaseHTTPRequestHandler, location: str) -> None:
    handler.send_response(HTTPStatus.SEE_OTHER)
    handler.send_header("Location", location)
    handler.end_headers()


def serve_dashboard(*, config: DashboardServerConfig) -> None:
    root = _repo_root()
    orchestrator = _load_module("orchestrator_runtime", root / "modules" / "orchestrator" / "runtime_skeleton.py")
    dashboard_api = _load_module(
        "dashboard_api_skeleton", root / "modules" / "dashboard-api" / "src" / "dashboard_api_skeleton.py"
    )

    state: dict[str, Any] = {
        "owner_id": config.owner_id,
        "default_mode": config.mode,
        "jobs": [],
        "uploads_dir": Path(tempfile.mkdtemp(prefix="transcriberator_uploads_")),
        "messages": {},
    }
    api_service = dashboard_api.DashboardApiSkeleton()
    session = api_service.issue_access_token(owner_id=config.owner_id)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/outputs/transcription":
                self._serve_transcription_output(parsed.query)
                return

            if parsed.path != "/":
                self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
                return

            query = parse_qs(parsed.query)
            message_id = query.get("msg", [""])[0]
            message = state["messages"].pop(message_id, "")
            html_content = _render_page(
                owner_id=state["owner_id"],
                default_mode=state["default_mode"],
                jobs=list(reversed(state["jobs"][-10:])),
                message=message,
            )
            payload = html_content.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _serve_transcription_output(self, query: str) -> None:
            params = parse_qs(query)
            job_id = params.get("job", [""])[0]
            job = next((candidate for candidate in state["jobs"] if candidate["jobId"] == job_id), None)
            if not job:
                self.send_error(HTTPStatus.NOT_FOUND, "Job transcription not found")
                return

            payload = job["transcriptionText"].encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/edit-transcription":
                self._handle_edit_transcription()
                return

            if parsed.path != "/transcribe":
                self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
                return

            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                content_length = 0
            if content_length <= 0:
                self.send_error(HTTPStatus.BAD_REQUEST, "Missing form payload")
                return

            body = self.rfile.read(content_length)
            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type or "boundary=" not in content_type:
                self.send_error(HTTPStatus.BAD_REQUEST, "Expected multipart form data")
                return

            boundary = content_type.split("boundary=", maxsplit=1)[1].strip().encode("utf-8")
            message = self._handle_transcribe(body=body, boundary=boundary)
            msg_id = uuid.uuid4().hex
            state["messages"][msg_id] = message
            _redirect(self, f"/?msg={msg_id}")

        def _handle_edit_transcription(self) -> None:
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                content_length = 0
            if content_length <= 0:
                self.send_error(HTTPStatus.BAD_REQUEST, "Missing form payload")
                return

            body = self.rfile.read(content_length).decode("utf-8", errors="ignore")
            fields = parse_qs(body, keep_blank_values=True)
            job_id = fields.get("job_id", [""])[0]
            transcription_text = fields.get("transcription_text", [""])[0]
            job = next((candidate for candidate in state["jobs"] if candidate["jobId"] == job_id), None)
            if not job:
                self.send_error(HTTPStatus.NOT_FOUND, "Unknown job id")
                return

            transcription_path = Path(job["transcriptionPath"])
            transcription_path.write_text(transcription_text, encoding="utf-8")
            job["transcriptionText"] = transcription_text

            msg_id = uuid.uuid4().hex
            state["messages"][msg_id] = f"Saved transcription edits for {job['audioFile']}."
            _redirect(self, f"/?msg={msg_id}")

        def _handle_transcribe(self, *, body: bytes, boundary: bytes) -> str:
            parts = [part for part in body.split(b"--" + boundary) if part and part not in {b"--\r\n", b"--"}]
            mode = state["default_mode"]
            filename = ""
            file_bytes = b""

            for part in parts:
                header_blob, _, value = part.partition(b"\r\n\r\n")
                if not value:
                    continue
                headers = header_blob.decode("utf-8", errors="ignore")
                value = value.rstrip(b"\r\n")
                if 'name="mode"' in headers:
                    mode = value.decode("utf-8", errors="ignore").strip().lower() or state["default_mode"]
                if 'name="audio"' in headers:
                    marker = 'filename="'
                    start = headers.find(marker)
                    if start != -1:
                        end = headers.find('"', start + len(marker))
                        filename = headers[start + len(marker):end]
                    file_bytes = value

            normalized_mode = _validate_mode(mode)
            safe_filename = _validate_audio_filename(filename)
            audio_path = state["uploads_dir"] / f"{uuid.uuid4().hex}_{safe_filename}"
            with audio_path.open("wb") as output:
                output.write(file_bytes)

            project_name = f"{safe_filename} transcription"
            project = api_service.create_project_authorized(
                token=session.token,
                owner_id=state["owner_id"],
                name=project_name,
            )
            job = api_service.create_job(project_id=project.id, mode=normalized_mode)
            mode_enum = orchestrator.JobMode.HQ if normalized_mode == "hq" else orchestrator.JobMode.DRAFT
            runtime = orchestrator.OrchestratorRuntime()
            result = runtime.run_job(
                orchestrator.OrchestratorJobRequest(
                    job_id=job.id,
                    mode=mode_enum,
                    allow_hq_degradation=config.allow_hq_degradation,
                )
            )

            summary = {
                "ownerId": state["owner_id"],
                "projectId": project.id,
                "jobId": job.id,
                "audioFile": safe_filename,
                "audioPath": str(audio_path),
                "mode": normalized_mode,
                "submittedAtUtc": datetime.now(timezone.utc).isoformat(),
                "finalStatus": result.final_status.value,
                "stages": [{**asdict(record), "status": record.status.value} for record in result.stage_records],
            }
            transcription_text = _build_transcription_text(
                audio_file=safe_filename,
                mode=normalized_mode,
                stages=summary["stages"],
            )
            transcription_path = state["uploads_dir"] / f"{job.id}_transcription.txt"
            transcription_path.write_text(transcription_text, encoding="utf-8")
            summary["transcriptionPath"] = str(transcription_path)
            summary["transcriptionText"] = transcription_text
            state["jobs"].append(summary)
            return (
                f"Transcription complete for {safe_filename}. "
                f"Job {job.id} finished with status {summary['finalStatus']}. "
                f"Output: {summary['transcriptionPath']}"
            )

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            print(f"[dashboard] {self.address_string()} - {format % args}")

    server = ThreadingHTTPServer((config.host, config.port), Handler)
    host, port = server.server_address
    print("[entrypoint] Dashboard started.")
    print(f"[entrypoint] Open http://{host}:{port} in your browser to upload audio and transcribe.")
    print(f"[entrypoint] Uploads directory: {state['uploads_dir']}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[entrypoint] Shutting down dashboard...")
    finally:
        server.server_close()
        shutil.rmtree(state["uploads_dir"], ignore_errors=True)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch local Transcriberator dashboard and transcription pipeline.")
    parser.add_argument("--mode", default="draft", choices=["draft", "hq"], help="Default pipeline mode for UI submissions.")
    parser.add_argument("--owner-id", default="local-owner", help="Owner id used for local dashboard sessions.")
    parser.add_argument("--project-name", default="Local Startup", help="Project name used during smoke-run mode.")
    parser.add_argument(
        "--fail-stage",
        action="append",
        default=[],
        help="Optional stage name(s) to simulate failure for smoke-run troubleshooting.",
    )
    parser.add_argument(
        "--no-hq-degradation",
        action="store_true",
        help="Disable HQ degradation fallback for source separation failures.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output in smoke-run mode.")
    parser.add_argument("--smoke-run", action="store_true", help="Run one startup smoke job and exit.")
    parser.add_argument("--host", default="127.0.0.1", help="Dashboard bind host.")
    parser.add_argument("--port", type=int, default=4173, help="Dashboard bind port.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.smoke_run:
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

    try:
        config = DashboardServerConfig(
            host=args.host,
            port=args.port,
            owner_id=args.owner_id,
            mode=_validate_mode(args.mode),
            allow_hq_degradation=not args.no_hq_degradation,
        )
        serve_dashboard(config=config)
    except StartupError as exc:
        print(f"[entrypoint] ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
