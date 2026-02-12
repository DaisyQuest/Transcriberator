"""Cross-platform local entrypoint for starting the Transcriberator skeleton system."""

from __future__ import annotations

import argparse
import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import html
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any
from urllib.parse import parse_qs, urlparse
import uuid
import wave
import xml.etree.ElementTree as ET


class StartupError(RuntimeError):
    """Raised when startup execution cannot complete successfully."""


@dataclass(frozen=True)
class DashboardServerConfig:
    host: str
    port: int
    owner_id: str
    mode: str
    allow_hq_degradation: bool
    editor_base_url: str = "http://127.0.0.1:3000"


@dataclass(frozen=True)
class AudioAnalysisProfile:
    """Deterministic audio-derived profile used to produce unique transcription output."""

    fingerprint: str
    byte_count: int
    estimated_duration_seconds: int
    estimated_tempo_bpm: int
    estimated_key: str
    melody_pitches: tuple[int, ...]


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


def _analyze_audio_bytes(*, audio_file: str, audio_bytes: bytes) -> AudioAnalysisProfile:
    if not audio_bytes:
        raise StartupError("Uploaded audio payload was empty.")

    digest = hashlib.sha256(audio_bytes).digest()
    fingerprint = digest.hex()[:16]
    estimated_duration_seconds = _estimate_audio_duration_seconds(audio_file=audio_file, audio_bytes=audio_bytes)
    estimated_tempo_bpm = _estimate_tempo_bpm(audio_bytes=audio_bytes, digest=digest)
    melody = _derive_melody_pitches(
        audio_bytes=audio_bytes,
        digest=digest,
        estimated_duration_seconds=estimated_duration_seconds,
        estimated_tempo_bpm=estimated_tempo_bpm,
    )
    estimated_key = _estimate_key(melody_pitches=melody, digest=digest)

    return AudioAnalysisProfile(
        fingerprint=f"{Path(audio_file).stem}-{fingerprint}",
        byte_count=len(audio_bytes),
        estimated_duration_seconds=estimated_duration_seconds,
        estimated_tempo_bpm=estimated_tempo_bpm,
        estimated_key=estimated_key,
        melody_pitches=tuple(melody),
    )


def _estimate_audio_duration_seconds(*, audio_file: str, audio_bytes: bytes) -> int:
    suffix = Path(audio_file).suffix.lower()

    if suffix == ".wav":
        try:
            with wave.open(io.BytesIO(audio_bytes), "rb") as wav_file:
                frame_rate = wav_file.getframerate()
                frame_count = wav_file.getnframes()
                if frame_rate > 0 and frame_count > 0:
                    return max(1, int(round(frame_count / frame_rate)))
        except (wave.Error, EOFError):
            pass

    bytes_per_second_by_format = {
        ".mp3": 16_000,
        ".flac": 24_000,
        ".wav": 176_000,
    }
    fallback_bps = bytes_per_second_by_format.get(suffix, 16_000)
    return max(1, int(round(len(audio_bytes) / fallback_bps)))


def _estimate_tempo_bpm(*, audio_bytes: bytes, digest: bytes) -> int:
    transitions = 0
    prior_above_midpoint = audio_bytes[0] >= 128
    for raw in audio_bytes[1:]:
        current_above_midpoint = raw >= 128
        if current_above_midpoint != prior_above_midpoint:
            transitions += 1
        prior_above_midpoint = current_above_midpoint

    activity_ratio = transitions / max(1, len(audio_bytes) - 1)
    seed = int.from_bytes(digest[:2], "big") / 65535
    weighted_activity = min(1.0, (activity_ratio * 2.8) + (seed * 0.35))
    return 72 + int(weighted_activity * 88)  # 72..160 BPM


def _derive_melody_pitches(
    *,
    audio_bytes: bytes,
    digest: bytes,
    estimated_duration_seconds: int,
    estimated_tempo_bpm: int,
) -> tuple[int, ...]:
    notes_per_second = max(1.0, estimated_tempo_bpm / 60.0)
    projected_note_count = int(round(estimated_duration_seconds * notes_per_second))
    note_count = min(1024, max(8, projected_note_count))
    window_size = max(64, len(audio_bytes) // note_count)
    melody: list[int] = []

    for note_index in range(note_count):
        window_start = (note_index * len(audio_bytes)) // note_count
        window_end = min(len(audio_bytes), window_start + window_size)
        window = audio_bytes[window_start:window_end] or audio_bytes[-window_size:]

        intensity = sum(abs(sample - 128) for sample in window)
        crossings = 0
        previous_above_midpoint = window[0] >= 128
        for sample in window[1:]:
            current_above_midpoint = sample >= 128
            if current_above_midpoint != previous_above_midpoint:
                crossings += 1
            previous_above_midpoint = current_above_midpoint

        seed = digest[note_index % len(digest)]
        pitch = 48 + ((intensity + crossings * 7 + seed) % 36)  # C3..B5
        if melody and pitch == melody[-1]:
            pitch = 48 + ((pitch - 48 + (seed % 11) + 5) % 36)
        melody.append(pitch)

    minimum_unique_pitches = max(4, note_count // 4)
    if len(set(melody)) < minimum_unique_pitches:
        for index in range(0, note_count, 3):
            injected_seed = digest[(index * 5) % len(digest)]
            melody[index] = 48 + ((melody[index] - 48 + injected_seed + 3) % 36)

    return tuple(melody)


def _estimate_key(*, melody_pitches: tuple[int, ...], digest: bytes) -> str:
    pitch_class_histogram = [0] * 12
    for pitch in melody_pitches:
        pitch_class_histogram[pitch % 12] += 1

    if sum(pitch_class_histogram) == 0:
        keys = ["C", "G", "D", "A", "E", "B", "F#", "C#", "F", "Bb", "Eb", "Ab"]
        return keys[digest[2] % len(keys)]

    major_scale_template = (0, 2, 4, 5, 7, 9, 11)
    scores: list[tuple[int, int]] = []
    for tonic in range(12):
        score = sum(pitch_class_histogram[(interval + tonic) % 12] for interval in major_scale_template)
        scores.append((score, tonic))

    _, winning_tonic = max(scores, key=lambda item: (item[0], -item[1]))
    names = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
    return names[winning_tonic]


def _build_transcription_text_with_analysis(
    *,
    audio_file: str,
    mode: str,
    stages: list[dict[str, Any]],
    profile: AudioAnalysisProfile,
) -> str:
    base = _build_transcription_text(audio_file=audio_file, mode=mode, stages=stages)
    return (
        f"{base}\n"
        "Audio analysis\n"
        f"- Fingerprint: {profile.fingerprint}\n"
        f"- Byte count: {profile.byte_count}\n"
        f"- Estimated duration: {profile.estimated_duration_seconds} seconds\n"
        f"- Estimated tempo: {profile.estimated_tempo_bpm} BPM\n"
        f"- Estimated key: {profile.estimated_key} major\n"
        f"- Derived note count: {len(profile.melody_pitches)}\n"
        f"- Melody MIDI pitches: {', '.join(str(p) for p in profile.melody_pitches)}\n"
    )


def _build_sheet_artifacts(
    *,
    job_id: str,
    uploads_dir: Path,
    audio_file: str,
    profile: AudioAnalysisProfile | None = None,
) -> list[dict[str, str]]:
    stem = Path(audio_file).stem
    if profile is None:
        profile = _analyze_audio_bytes(audio_file=audio_file, audio_bytes=audio_file.encode("utf-8"))

    note_block = "\n".join(
        (
            "      <note><pitch><step>{step}</step><octave>{octave}</octave></pitch>"
            "<duration>1</duration><type>quarter</type></note>"
        ).format(step=_midi_pitch_to_step(pitch), octave=_midi_pitch_to_octave(pitch))
        for pitch in profile.melody_pitches
    )
    musicxml_payload = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<!DOCTYPE score-partwise PUBLIC \"-//Recordare//DTD MusicXML 4.0 Partwise//EN\" "
        "\"http://www.musicxml.org/dtds/partwise.dtd\">\n"
        "<score-partwise version=\"4.0\">\n"
        "  <part-list><score-part id=\"P1\"><part-name>Transcription</part-name></score-part></part-list>\n"
        "  <part id=\"P1\">\n"
        "    <measure number=\"1\">\n"
        "      <attributes><divisions>1</divisions><key><fifths>0</fifths></key>"
        "<time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>\n"
        f"{note_block}\n"
        "    </measure>\n"
        "  </part>\n"
        "</score-partwise>\n"
    )
    _validate_musicxml_payload(musicxml_payload)

    artifact_specs = [
        (
            "musicxml",
            ".musicxml",
            "application/vnd.recordare.musicxml+xml",
            musicxml_payload.encode("utf-8"),
        ),
        (
            "midi",
            ".mid",
            "audio/midi",
            _build_minimal_midi_payload(profile.melody_pitches),
        ),
        (
            "pdf",
            ".pdf",
            "application/pdf",
            _build_minimal_pdf_payload(),
        ),
        (
            "png",
            ".png",
            "image/png",
            _build_minimal_png_payload(),
        ),
    ]

    artifacts: list[dict[str, str]] = []
    for artifact_name, extension, content_type, content in artifact_specs:
        artifact_path = uploads_dir / f"{job_id}_{stem}{extension}"
        artifact_path.write_bytes(content)
        artifacts.append(
            {
                "name": artifact_name,
                "path": str(artifact_path),
                "contentType": content_type,
                "downloadPath": f"/outputs/artifact?job={job_id}&name={artifact_name}",
            }
        )
    return artifacts


def _build_minimal_midi_payload(melody_pitches: tuple[int, ...] = (60, 64, 67, 72)) -> bytes:
    header = b"MThd" + (6).to_bytes(4, "big") + (0).to_bytes(2, "big") + (1).to_bytes(2, "big") + (96).to_bytes(2, "big")
    events = bytearray()
    for pitch in melody_pitches:
        pitch_byte = max(0, min(127, pitch))
        events.extend(b"\x00\x90")
        events.append(pitch_byte)
        events.append(0x40)
        events.extend(b"\x30\x80")
        events.append(pitch_byte)
        events.append(0x40)
    events.extend(b"\x00\xff\x2f\x00")
    track_events = bytes(events)
    track = b"MTrk" + len(track_events).to_bytes(4, "big") + track_events
    return header + track


def _midi_pitch_to_step(pitch: int) -> str:
    names = ["C", "C", "D", "D", "E", "F", "F", "G", "G", "A", "A", "B"]
    return names[pitch % 12]


def _midi_pitch_to_octave(pitch: int) -> int:
    return (pitch // 12) - 1


def _build_minimal_pdf_payload() -> bytes:
    return (
        b"%PDF-1.1\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]/Contents 4 0 R>>endobj\n"
        b"4 0 obj<</Length 36>>stream\nBT /F1 12 Tf 72 120 Td (Transcriberator) Tj ET\nendstream endobj\n"
        b"xref\n0 5\n0000000000 65535 f \n"
        b"0000000010 00000 n \n0000000062 00000 n \n0000000116 00000 n \n0000000203 00000 n \n"
        b"trailer<</Root 1 0 R/Size 5>>\nstartxref\n289\n%%EOF"
    )


def _build_minimal_png_payload() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDAT\x08\x1dc````\x00\x00\x00\x04\x00\x01\xf6\x178U"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def _validate_musicxml_payload(payload: str) -> None:
    ET.fromstring(payload)


def _validate_midi_payload(payload: bytes) -> str | None:
    if not payload.startswith(b"MThd"):
        return "MIDI payload missing MThd header chunk."
    if len(payload) < 14:
        return "MIDI payload is too short to include a complete header."
    header_len = int.from_bytes(payload[4:8], "big")
    if header_len != 6:
        return "MIDI header chunk length must be exactly 6 bytes."
    track_offset = 8 + header_len
    if len(payload) < track_offset + 8:
        return "MIDI payload missing required track chunk header."
    if payload[track_offset:track_offset + 4] != b"MTrk":
        return "MIDI payload missing MTrk track chunk."
    declared_track_len = int.from_bytes(payload[track_offset + 4:track_offset + 8], "big")
    actual_track_len = len(payload) - (track_offset + 8)
    if declared_track_len != actual_track_len:
        return "MIDI track chunk length does not match payload size."
    return None


def _validate_pdf_payload(payload: bytes) -> str | None:
    if not payload.startswith(b"%PDF-"):
        return "PDF payload missing %PDF- header."
    if b"%%EOF" not in payload.rstrip():
        return "PDF payload missing %%EOF trailer."
    return None


def _validate_png_payload(payload: bytes) -> str | None:
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG payload missing standard signature bytes."
    if not payload.endswith(b"IEND\xaeB`\x82"):
        return "PNG payload missing IEND trailer chunk."
    return None


def _validate_artifact_payload(*, artifact_name: str, payload: bytes) -> str | None:
    if artifact_name == "midi":
        return _validate_midi_payload(payload)
    if artifact_name == "pdf":
        return _validate_pdf_payload(payload)
    if artifact_name == "png":
        return _validate_png_payload(payload)
    return None


def _content_disposition_for_artifact(artifact_name: str, artifact_path: Path) -> str:
    mode = "inline" if artifact_name in {"pdf", "png"} else "attachment"
    return f'{mode}; filename="{artifact_path.name}"'


def _augment_transcription_with_artifacts(*, transcription_text: str, artifacts: list[dict[str, str]]) -> str:
    artifact_lines = "\n".join(f"- {artifact['name']}: {artifact['path']}" for artifact in artifacts)
    return (
        f"{transcription_text}\n"
        "Generated sheet music artifacts\n"
        f"{artifact_lines}\n"
    )


def _render_page(
    *,
    owner_id: str,
    default_mode: str,
    jobs: list[dict[str, Any]],
    editor_base_url: str,
    message: str = "",
) -> str:
    rows = []
    for job in jobs:
        stage_rows = "".join(
            f"<li><strong>{html.escape(stage['stage_name'])}</strong>: {html.escape(stage['status'])} — {html.escape(stage['detail'])}</li>"
            for stage in job["stages"]
        )
        artifact_rows = "".join(
            f"<li><strong>{html.escape(artifact['name'])}</strong>: "
            f"<code>{html.escape(artifact['path'])}</code> "
            f"(<a href='{html.escape(artifact['downloadPath'])}' target='_blank' rel='noopener'>open</a>)</li>"
            for artifact in job.get("sheetArtifacts", [])
        )
        rows.append(
            "<article class='job-card'>"
            f"<h3>{html.escape(job['audioFile'])}</h3>"
            f"<p><strong>Job:</strong> {html.escape(job['jobId'])} | <strong>Mode:</strong> {html.escape(job['mode'])} | "
            f"<strong>Status:</strong> {html.escape(job['finalStatus'])}</p>"
            f"<p><strong>Submitted:</strong> {html.escape(job['submittedAtUtc'])}</p>"
            f"<p><strong>Estimated duration:</strong> {html.escape(str(job['estimatedDurationSeconds']))} sec | "
            f"<strong>Estimated tempo:</strong> {html.escape(str(job['estimatedTempoBpm']))} BPM | "
            f"<strong>Estimated key:</strong> {html.escape(job['estimatedKey'])} major | "
            f"<strong>Derived notes:</strong> {html.escape(str(job['derivedNoteCount']))}</p>"
            f"<p><strong>Transcription output:</strong> <code>{html.escape(job['transcriptionPath'])}</code><br/>"
            f"<a href='/outputs/transcription?job={html.escape(job['jobId'])}' target='_blank' rel='noopener'>View raw output</a></p>"
            f"<p><strong>Editor:</strong> <a href='{html.escape(job['editorUrl'])}' target='_blank' rel='noopener'>Open editor for this job</a></p>"
            f"<p><strong>Sheet music artifacts:</strong></p><ul>{artifact_rows or '<li>No artifacts recorded.</li>'}</ul>"
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
  <p class='hint'>Editor app: <a href='{html.escape(editor_base_url)}' target='_blank' rel='noopener'>{html.escape(editor_base_url)}</a></p>
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

            if parsed.path == "/outputs/artifact":
                self._serve_artifact_output(parsed.query)
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
                editor_base_url=config.editor_base_url,
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

        def _serve_artifact_output(self, query: str) -> None:
            params = parse_qs(query)
            job_id = params.get("job", [""])[0]
            artifact_name = params.get("name", [""])[0]
            job = next((candidate for candidate in state["jobs"] if candidate["jobId"] == job_id), None)
            if not job:
                self.send_error(HTTPStatus.NOT_FOUND, "Job artifacts not found")
                return

            artifact = next(
                (candidate for candidate in job.get("sheetArtifacts", []) if candidate["name"] == artifact_name),
                None,
            )
            if not artifact:
                self.send_error(HTTPStatus.NOT_FOUND, "Artifact not found")
                return

            artifact_path = Path(artifact["path"])
            if not artifact_path.exists():
                self.send_error(HTTPStatus.NOT_FOUND, "Artifact file missing")
                return

            payload = artifact_path.read_bytes()
            validation_error = _validate_artifact_payload(artifact_name=artifact_name, payload=payload)
            if validation_error:
                self.send_error(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    f"Artifact validation failed for '{artifact_name}': {validation_error}",
                )
                return

            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", artifact["contentType"])
            self.send_header("Content-Disposition", _content_disposition_for_artifact(artifact_name, artifact_path))
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
            profile = _analyze_audio_bytes(audio_file=safe_filename, audio_bytes=file_bytes)
            transcription_text = _build_transcription_text_with_analysis(
                audio_file=safe_filename,
                mode=normalized_mode,
                stages=summary["stages"],
                profile=profile,
            )
            artifacts = _build_sheet_artifacts(
                job_id=job.id,
                uploads_dir=state["uploads_dir"],
                audio_file=safe_filename,
                profile=profile,
            )
            transcription_text = _augment_transcription_with_artifacts(
                transcription_text=transcription_text,
                artifacts=artifacts,
            )
            transcription_path = state["uploads_dir"] / f"{job.id}_transcription.txt"
            transcription_path.write_text(transcription_text, encoding="utf-8")
            summary["transcriptionPath"] = str(transcription_path)
            summary["transcriptionText"] = transcription_text
            summary["sheetArtifacts"] = artifacts
            summary["estimatedDurationSeconds"] = profile.estimated_duration_seconds
            summary["estimatedTempoBpm"] = profile.estimated_tempo_bpm
            summary["estimatedKey"] = profile.estimated_key
            summary["derivedNoteCount"] = len(profile.melody_pitches)
            summary["editorUrl"] = f"{config.editor_base_url.rstrip('/')}/?job={job.id}"
            state["jobs"].append(summary)
            return (
                f"Transcription complete for {safe_filename}. "
                f"Job {job.id} finished with status {summary['finalStatus']}. "
                f"Output: {summary['transcriptionPath']}. "
                f"Sheet music: {', '.join(artifact['path'] for artifact in artifacts)}. "
                f"Editor: {summary['editorUrl']}"
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
    parser.add_argument("--editor-url", default="http://127.0.0.1:3000", help="Base URL for the editor app.")
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
            editor_base_url=args.editor_url,
        )
        serve_dashboard(config=config)
    except StartupError as exc:
        print(f"[entrypoint] ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
