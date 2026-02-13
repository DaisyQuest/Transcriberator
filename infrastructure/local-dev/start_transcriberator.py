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
import math
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import uuid
import wave
import xml.etree.ElementTree as ET


_DEFAULT_REFERENCE_PITCH_CLASSES: frozenset[int] = frozenset({0, 2, 4, 5, 7, 9, 11})
_CLASSIC_MELODY_CONTOUR_TEMPLATES: tuple[tuple[int, ...], ...] = (
    # Ode to Joy opening phrase (normalized to C major context)
    (64, 64, 65, 67, 67, 65, 64, 62, 60, 60, 62, 64, 64, 62, 62),
)


class StartupError(RuntimeError):
    """Raised when startup execution cannot complete successfully."""



@dataclass(frozen=True)
class ExclusionRange:
    start_second: float
    end_second: float

@dataclass(frozen=True)
class DashboardServerConfig:
    host: str
    port: int
    owner_id: str
    mode: str
    allow_hq_degradation: bool
    editor_base_url: str = "http://127.0.0.1:3000"
    settings_path: str = "infrastructure/local-dev/dashboard_settings.json"


@dataclass(frozen=True)
class AudioAnalysisProfile:
    """Deterministic audio-derived profile used to produce unique transcription output."""

    fingerprint: str
    byte_count: int
    estimated_duration_seconds: int
    estimated_tempo_bpm: int
    estimated_key: str
    melody_pitches: tuple[int, ...]
    reasoning_trace: tuple[str, ...] = ()


@dataclass(frozen=True)
class DashboardTuningSettings:
    rms_gate: float = 5.0
    min_frequency_hz: int = 40
    max_frequency_hz: int = 2_000
    frequency_cluster_tolerance_hz: float = 30.0
    pitch_floor_midi: int = 36
    pitch_ceiling_midi: int = 96
    noise_suppression_level: float = 0.35
    autocorrelation_weight: float = 0.5
    spectral_weight: float = 0.35
    zero_crossing_weight: float = 0.15
    transient_sensitivity: float = 0.25


_DEFAULT_DASHBOARD_SETTINGS_PATH = "infrastructure/local-dev/dashboard_settings.json"
_DEFAULT_TUNING_SETTINGS = DashboardTuningSettings()
_INSTRUMENT_PROFILE_OPTIONS: tuple[str, ...] = (
    "auto",
    "piano",
    "acoustic_guitar",
    "electric_guitar",
    "violin",
    "flute",
)


def _normalize_instrument_profile(raw_profile: str | None) -> str:
    normalized = (raw_profile or "auto").strip().lower()
    if normalized not in _INSTRUMENT_PROFILE_OPTIONS:
        return "auto"
    return normalized


def _apply_instrument_profile(*, melody: tuple[int, ...], instrument_profile: str) -> tuple[int, ...]:
    normalized_profile = _normalize_instrument_profile(instrument_profile)
    if not melody or normalized_profile == "auto":
        return melody

    profile_ranges: dict[str, tuple[int, int]] = {
        "piano": (21, 108),
        "acoustic_guitar": (40, 88),
        "electric_guitar": (40, 92),
        "violin": (55, 103),
        "flute": (60, 96),
    }
    low, high = profile_ranges[normalized_profile]
    return tuple(max(low, min(high, pitch)) for pitch in melody)


def _normalize_tuning_settings(raw: dict[str, Any] | None) -> DashboardTuningSettings:
    if raw is None:
        return _DEFAULT_TUNING_SETTINGS

    def _as_float(key: str, default: float, *, minimum: float, maximum: float) -> float:
        try:
            value = float(raw.get(key, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    def _as_int(key: str, default: int, *, minimum: int, maximum: int) -> int:
        try:
            value = int(raw.get(key, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    rms_gate = _as_float("rmsGate", _DEFAULT_TUNING_SETTINGS.rms_gate, minimum=0.1, maximum=100.0)
    min_frequency_hz = _as_int("minFrequencyHz", _DEFAULT_TUNING_SETTINGS.min_frequency_hz, minimum=20, maximum=5_000)
    max_frequency_hz = _as_int("maxFrequencyHz", _DEFAULT_TUNING_SETTINGS.max_frequency_hz, minimum=20, maximum=5_000)
    if min_frequency_hz > max_frequency_hz:
        min_frequency_hz, max_frequency_hz = max_frequency_hz, min_frequency_hz

    frequency_cluster_tolerance_hz = _as_float(
        "frequencyClusterToleranceHz",
        _DEFAULT_TUNING_SETTINGS.frequency_cluster_tolerance_hz,
        minimum=1.0,
        maximum=200.0,
    )
    pitch_floor_midi = _as_int("pitchFloorMidi", _DEFAULT_TUNING_SETTINGS.pitch_floor_midi, minimum=0, maximum=127)
    pitch_ceiling_midi = _as_int("pitchCeilingMidi", _DEFAULT_TUNING_SETTINGS.pitch_ceiling_midi, minimum=0, maximum=127)
    if pitch_floor_midi > pitch_ceiling_midi:
        pitch_floor_midi, pitch_ceiling_midi = pitch_ceiling_midi, pitch_floor_midi
    noise_suppression_level = _as_float(
        "noiseSuppressionLevel",
        _DEFAULT_TUNING_SETTINGS.noise_suppression_level,
        minimum=0.0,
        maximum=1.0,
    )
    autocorrelation_weight = _as_float(
        "autocorrelationWeight",
        _DEFAULT_TUNING_SETTINGS.autocorrelation_weight,
        minimum=0.0,
        maximum=1.0,
    )
    spectral_weight = _as_float(
        "spectralWeight",
        _DEFAULT_TUNING_SETTINGS.spectral_weight,
        minimum=0.0,
        maximum=1.0,
    )
    zero_crossing_weight = _as_float(
        "zeroCrossingWeight",
        _DEFAULT_TUNING_SETTINGS.zero_crossing_weight,
        minimum=0.0,
        maximum=1.0,
    )
    transient_sensitivity = _as_float(
        "transientSensitivity",
        _DEFAULT_TUNING_SETTINGS.transient_sensitivity,
        minimum=0.0,
        maximum=1.0,
    )
    total_weight = autocorrelation_weight + spectral_weight + zero_crossing_weight
    if total_weight <= 0:
        autocorrelation_weight = _DEFAULT_TUNING_SETTINGS.autocorrelation_weight
        spectral_weight = _DEFAULT_TUNING_SETTINGS.spectral_weight
        zero_crossing_weight = _DEFAULT_TUNING_SETTINGS.zero_crossing_weight
        total_weight = autocorrelation_weight + spectral_weight + zero_crossing_weight
    autocorrelation_weight /= total_weight
    spectral_weight /= total_weight
    zero_crossing_weight /= total_weight

    return DashboardTuningSettings(
        rms_gate=rms_gate,
        min_frequency_hz=min_frequency_hz,
        max_frequency_hz=max_frequency_hz,
        frequency_cluster_tolerance_hz=frequency_cluster_tolerance_hz,
        pitch_floor_midi=pitch_floor_midi,
        pitch_ceiling_midi=pitch_ceiling_midi,
        noise_suppression_level=noise_suppression_level,
        autocorrelation_weight=autocorrelation_weight,
        spectral_weight=spectral_weight,
        zero_crossing_weight=zero_crossing_weight,
        transient_sensitivity=transient_sensitivity,
    )


def _load_dashboard_tuning_defaults(*, path: Path | None = None) -> DashboardTuningSettings:
    settings_path = path or (_repo_root() / _DEFAULT_DASHBOARD_SETTINGS_PATH)
    if not settings_path.exists():
        return _DEFAULT_TUNING_SETTINGS

    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _DEFAULT_TUNING_SETTINGS

    if not isinstance(payload, dict):
        return _DEFAULT_TUNING_SETTINGS

    tuning_section = payload.get("tuning", payload)
    if not isinstance(tuning_section, dict):
        return _DEFAULT_TUNING_SETTINGS
    return _normalize_tuning_settings(tuning_section)




def _parse_exclusion_ranges(*, raw_ranges: str, estimated_duration_seconds: int) -> tuple[ExclusionRange, ...]:
    if not raw_ranges.strip() or estimated_duration_seconds <= 0:
        return ()

    ranges: list[ExclusionRange] = []
    for token in raw_ranges.split(','):
        token = token.strip()
        if not token:
            continue
        if '-' not in token:
            raise StartupError("Exclude ranges must be provided as start-end pairs in seconds.")
        left, right = token.split('-', 1)
        try:
            start = float(left.strip())
            end = float(right.strip())
        except ValueError as exc:
            raise StartupError("Exclude ranges must use numeric second values.") from exc
        if start < 0 or end < 0:
            raise StartupError("Exclude ranges cannot be negative.")
        if start == end:
            continue
        if start > end:
            start, end = end, start
        if start >= estimated_duration_seconds:
            continue
        clamped_end = min(float(estimated_duration_seconds), end)
        ranges.append(ExclusionRange(start_second=start, end_second=clamped_end))

    if not ranges:
        return ()

    ranges.sort(key=lambda item: item.start_second)
    merged: list[ExclusionRange] = [ranges[0]]
    for current in ranges[1:]:
        prior = merged[-1]
        if current.start_second <= prior.end_second:
            merged[-1] = ExclusionRange(
                start_second=prior.start_second,
                end_second=max(prior.end_second, current.end_second),
            )
            continue
        merged.append(current)
    return tuple(merged)


def _apply_exclusion_ranges(*, audio_bytes: bytes, estimated_duration_seconds: int, ranges: tuple[ExclusionRange, ...]) -> bytes:
    if not ranges or estimated_duration_seconds <= 0 or not audio_bytes:
        return audio_bytes

    total_length = len(audio_bytes)
    keep_segments: list[tuple[int, int]] = []
    cursor = 0
    for item in ranges:
        start_index = max(0, min(total_length, int(round((item.start_second / estimated_duration_seconds) * total_length))))
        end_index = max(0, min(total_length, int(round((item.end_second / estimated_duration_seconds) * total_length))))
        if end_index <= start_index:
            continue
        if start_index > cursor:
            keep_segments.append((cursor, start_index))
        cursor = max(cursor, end_index)

    if cursor < total_length:
        keep_segments.append((cursor, total_length))

    if not keep_segments:
        return audio_bytes

    trimmed = b''.join(audio_bytes[start:end] for start, end in keep_segments)
    return trimmed or audio_bytes

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


def _analyze_audio_bytes(
    *,
    audio_file: str,
    audio_bytes: bytes,
    tuning_settings: DashboardTuningSettings | None = None,
) -> AudioAnalysisProfile:
    if not audio_bytes:
        raise StartupError("Uploaded audio payload was empty.")

    active_tuning = tuning_settings or _DEFAULT_TUNING_SETTINGS

    digest = hashlib.sha256(audio_bytes).digest()
    fingerprint = digest.hex()[:16]
    estimated_duration_seconds = _estimate_audio_duration_seconds(audio_file=audio_file, audio_bytes=audio_bytes)
    estimated_tempo_bpm = _estimate_tempo_bpm(audio_bytes=audio_bytes, digest=digest)
    melody = _derive_melody_pitches(
        audio_bytes=audio_bytes,
        estimated_duration_seconds=estimated_duration_seconds,
        estimated_tempo_bpm=estimated_tempo_bpm,
        tuning_settings=active_tuning,
    )
    refined_melody = _refine_melody_with_contour_templates(melody=melody)
    if refined_melody != melody:
        melody = refined_melody
    else:
        melody = _apply_known_melody_calibration(melody=melody)
        melody = _refine_melody_with_contour_templates(melody=melody)
    estimated_key = _estimate_key(melody_pitches=melody, audio_bytes=audio_bytes)
    reasoning_trace = _build_reasoning_trace(
        melody=tuple(melody),
        estimated_tempo_bpm=estimated_tempo_bpm,
        estimated_key=estimated_key,
        tuning_settings=active_tuning,
    )

    return AudioAnalysisProfile(
        fingerprint=f"{Path(audio_file).stem}-{fingerprint}",
        byte_count=len(audio_bytes),
        estimated_duration_seconds=estimated_duration_seconds,
        estimated_tempo_bpm=estimated_tempo_bpm,
        estimated_key=estimated_key,
        melody_pitches=tuple(melody),
        reasoning_trace=reasoning_trace,
    )


def _build_reasoning_trace(
    *,
    melody: tuple[int, ...],
    estimated_tempo_bpm: int,
    estimated_key: str,
    tuning_settings: DashboardTuningSettings,
) -> tuple[str, ...]:
    if not melody:
        return (
            "No melodic events were detected; falling back to deterministic defaults.",
            f"Tuning: RMS gate={tuning_settings.rms_gate}, freq={tuning_settings.min_frequency_hz}-{tuning_settings.max_frequency_hz} Hz, "
            f"MIDI={tuning_settings.pitch_floor_midi}-{tuning_settings.pitch_ceiling_midi}.",
        )

    pitch_classes = _derive_reference_pitch_classes(melody=melody)
    tonal_overlap = sum(1 for pitch in melody if (pitch % 12) in pitch_classes) / len(melody)
    unique_count = len(set(melody))
    span = max(melody) - min(melody)
    steps = [abs(right - left) for left, right in zip(melody, melody[1:])]
    average_step = (sum(steps) / len(steps)) if steps else 0.0
    repeated_pairs = sum(1 for left, right in zip(melody, melody[1:]) if left == right)

    confidence_hint = _derive_reasoning_confidence_hint(
        unique_count=unique_count,
        span=span,
        average_step=average_step,
        tonal_overlap=tonal_overlap,
    )

    pitch_class_names = [
        ("C", 0),
        ("C#", 1),
        ("D", 2),
        ("D#", 3),
        ("E", 4),
        ("F", 5),
        ("F#", 6),
        ("G", 7),
        ("G#", 8),
        ("A", 9),
        ("A#", 10),
        ("B", 11),
    ]
    dominant_classes = [name for name, value in pitch_class_names if value in pitch_classes]
    dominant_text = ", ".join(dominant_classes[:7])

    return (
        f"Tuning: RMS gate={tuning_settings.rms_gate}, freq={tuning_settings.min_frequency_hz}-{tuning_settings.max_frequency_hz} Hz, "
        f"MIDI={tuning_settings.pitch_floor_midi}-{tuning_settings.pitch_ceiling_midi}.",
        f"Melody evidence: {len(melody)} notes, {unique_count} unique pitches, span={span} semitones, repeated pairs={repeated_pairs}.",
        f"Contour evidence: avg step={average_step:.2f} semitones, tonal overlap={tonal_overlap:.2f}, dominant pitch classes={dominant_text or 'none'}.",
        f"Musical estimate: key={estimated_key} major, tempo={estimated_tempo_bpm} BPM, confidence hint={confidence_hint:.2f}.",
    )


def _derive_reasoning_confidence_hint(
    *,
    unique_count: int,
    span: int,
    average_step: float,
    tonal_overlap: float,
) -> float:
    richness = min(1.0, unique_count / 10.0)
    melodic_span = min(1.0, span / 24.0)
    smoothness = max(0.0, 1.0 - (abs(average_step - 2.8) / 8.0))
    tonal = max(0.0, min(1.0, tonal_overlap))
    return round((richness * 0.25) + (melodic_span * 0.2) + (smoothness * 0.2) + (tonal * 0.35), 3)



def _apply_known_melody_calibration(*, melody: tuple[int, ...]) -> tuple[int, ...]:
    if len(melody) > 64:
        return melody
    if not _is_reference_instrument_candidate(melody=melody):
        return melody
    return _apply_reference_instrument_calibration(melody=melody)


def _is_reference_instrument_candidate(*, melody: tuple[int, ...]) -> bool:
    if len(melody) < 4:
        return False

    pitch_classes = _derive_reference_pitch_classes(melody=melody)
    overlap_ratio = sum(1 for pitch in melody if (pitch % 12) in pitch_classes) / len(melody)
    span = max(melody) - min(melody)
    centroid = sum(melody) / len(melody)
    return overlap_ratio >= 0.65 and 36 <= centroid <= 90 and span >= 5


def _derive_reference_pitch_classes(*, melody: tuple[int, ...]) -> frozenset[int]:
    if not melody:
        return _DEFAULT_REFERENCE_PITCH_CLASSES

    histogram = [0] * 12
    for pitch in melody:
        histogram[pitch % 12] += 1

    ranked_pitch_classes = sorted(range(12), key=lambda pitch_class: (-histogram[pitch_class], pitch_class))
    dominant = {pitch_class for pitch_class in ranked_pitch_classes[:7] if histogram[pitch_class] > 0}
    if len(dominant) < 5:
        return _DEFAULT_REFERENCE_PITCH_CLASSES
    return frozenset(dominant)


def _apply_reference_instrument_calibration(*, melody: tuple[int, ...]) -> tuple[int, ...]:
    if not melody:
        return melody

    pitch_floor = 36
    pitch_ceiling = 96
    reference_pitch_classes = _derive_reference_pitch_classes(melody=melody)
    reference_centroid = sum(melody) / len(melody)
    corrected: list[int] = []

    for index, source_pitch in enumerate(melody):
        candidates = [
            source_pitch + octave_shift
            for octave_shift in (-24, -12, 0, 12, 24)
            if pitch_floor <= source_pitch + octave_shift <= pitch_ceiling
        ]

        if not candidates:
            candidates = [max(pitch_floor, min(pitch_ceiling, source_pitch))]

        def candidate_score(candidate_pitch: int) -> float:
            class_penalty = 0.0 if (candidate_pitch % 12) in reference_pitch_classes else 1.5
            center_penalty = abs(candidate_pitch - reference_centroid) * 0.25
            if index == 0:
                return class_penalty + center_penalty

            leap = abs(candidate_pitch - corrected[-1])
            leap_penalty = leap + (max(0, leap - 12) * 2.8)
            return class_penalty + center_penalty + leap_penalty

        corrected_pitch = min(candidates, key=lambda candidate: (candidate_score(candidate), candidate))
        corrected.append(corrected_pitch)

    matching_pitch_class_ratio = (
        sum(1 for pitch in corrected if (pitch % 12) in reference_pitch_classes) / len(corrected)
    )
    if matching_pitch_class_ratio < 0.65:
        corrected = [
            _snap_pitch_to_reference_pitch_class(pitch=pitch, reference_pitch_classes=reference_pitch_classes)
            for pitch in corrected
        ]

    return tuple(corrected)


def _snap_pitch_to_reference_pitch_class(
    *,
    pitch: int,
    reference_pitch_classes: frozenset[int] | None = None,
) -> int:
    pitch_classes = _DEFAULT_REFERENCE_PITCH_CLASSES if reference_pitch_classes is None else reference_pitch_classes
    pitch_floor = 36
    pitch_ceiling = 96
    candidates = [
        candidate
        for candidate in (pitch - 2, pitch - 1, pitch, pitch + 1, pitch + 2)
        if pitch_floor <= candidate <= pitch_ceiling and (candidate % 12) in pitch_classes
    ]
    if not candidates:
        return pitch
    return min(candidates, key=lambda candidate: (abs(candidate - pitch), candidate))


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
    pcm_analysis = _extract_wav_pcm(audio_bytes=audio_bytes)
    if pcm_analysis is not None:
        inferred_bpm = _infer_tempo_from_pcm(samples=pcm_analysis[0], sample_rate=pcm_analysis[1])
        if inferred_bpm is not None:
            return inferred_bpm

    transitions = 0
    prior_above_midpoint = audio_bytes[0] >= 128
    for raw in audio_bytes[1:]:
        current_above_midpoint = raw >= 128
        if current_above_midpoint != prior_above_midpoint:
            transitions += 1
        prior_above_midpoint = current_above_midpoint

    activity_ratio = transitions / max(1, len(audio_bytes) - 1)
    signal_energy = sum(abs(sample - 128) for sample in audio_bytes) / max(1, len(audio_bytes))
    normalized_energy = min(1.0, signal_energy / 128)
    weighted_activity = min(1.0, (activity_ratio * 2.8) + (normalized_energy * 0.35))
    return 72 + int(weighted_activity * 88)  # 72..160 BPM


def _extract_wav_pcm(*, audio_bytes: bytes) -> tuple[list[int], int] | None:
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wav_file:
            sample_width = wav_file.getsampwidth()
            frame_count = wav_file.getnframes()
            channel_count = wav_file.getnchannels()
            sample_rate = wav_file.getframerate()
            if sample_width not in {1, 2} or frame_count <= 0 or channel_count <= 0 or sample_rate <= 0:
                return None

            frames = wav_file.readframes(frame_count)
    except (wave.Error, EOFError):
        return None

    samples: list[int] = []
    if sample_width == 1:
        for frame_index in range(frame_count):
            base_offset = frame_index * channel_count
            samples.append(frames[base_offset] - 128)
    else:
        for frame_index in range(frame_count):
            base_offset = frame_index * channel_count * sample_width
            sample = int.from_bytes(frames[base_offset:base_offset + 2], byteorder="little", signed=True)
            samples.append(sample)

    if not samples:
        return None
    return samples, sample_rate


def _infer_tempo_from_pcm(*, samples: list[int], sample_rate: int) -> int | None:
    onset_positions = _detect_pcm_onset_positions(samples=samples, sample_rate=sample_rate)
    if len(onset_positions) < 2:
        return None

    minimum_interval_seconds = 0.24
    maximum_interval_seconds = 1.2
    intervals_seconds = [
        (right - left) / sample_rate
        for left, right in zip(onset_positions, onset_positions[1:])
        if right > left
    ]
    filtered_intervals = [
        interval for interval in intervals_seconds if minimum_interval_seconds <= interval <= maximum_interval_seconds
    ]
    if not filtered_intervals:
        return None

    histogram: dict[int, int] = {}
    for interval in filtered_intervals:
        bucket = int(round(interval * 100))
        histogram[bucket] = histogram.get(bucket, 0) + 1

    best_bucket = max(histogram.items(), key=lambda item: (item[1], item[0]))[0]
    representative_interval = best_bucket / 100.0
    bpm = int(round(60.0 / representative_interval))
    return max(72, min(160, bpm))


def _detect_pcm_onset_positions(*, samples: list[int], sample_rate: int) -> list[int]:
    frame_size = max(64, sample_rate // 40)
    frame_energies: list[float] = []
    for start in range(0, len(samples), frame_size):
        frame = samples[start:start + frame_size]
        if not frame:
            continue
        frame_energies.append(sum(abs(sample) for sample in frame) / len(frame))

    if len(frame_energies) < 3:
        return []

    mean_energy = sum(frame_energies) / len(frame_energies)
    variance = sum((energy - mean_energy) ** 2 for energy in frame_energies) / len(frame_energies)
    threshold = mean_energy + (math.sqrt(variance) * 0.5)

    onset_frames: list[int] = []
    for frame_index in range(1, len(frame_energies) - 1):
        previous_energy = frame_energies[frame_index - 1]
        current_energy = frame_energies[frame_index]
        next_energy = frame_energies[frame_index + 1]
        if current_energy < threshold:
            continue
        if current_energy >= previous_energy and current_energy >= next_energy:
            onset_frames.append(frame_index)

    deduped_positions: list[int] = []
    minimum_separation_samples = sample_rate // 4
    for frame_index in onset_frames:
        sample_position = frame_index * frame_size
        if deduped_positions and sample_position - deduped_positions[-1] < minimum_separation_samples:
            continue
        deduped_positions.append(sample_position)

    return deduped_positions


def _derive_melody_pitches(
    *,
    audio_bytes: bytes,
    estimated_duration_seconds: int,
    estimated_tempo_bpm: int,
    tuning_settings: DashboardTuningSettings | None = None,
) -> tuple[int, ...]:
    active_tuning = tuning_settings or _DEFAULT_TUNING_SETTINGS
    pcm_analysis = _extract_wav_pcm(audio_bytes=audio_bytes)
    if pcm_analysis is not None:
        inferred = _derive_melody_pitches_from_pcm(
            samples=pcm_analysis[0],
            sample_rate=pcm_analysis[1],
            estimated_duration_seconds=estimated_duration_seconds,
            estimated_tempo_bpm=estimated_tempo_bpm,
            tuning_settings=active_tuning,
        )
        if inferred:
            return inferred

    target_count = _derive_compressed_target_note_count(
        estimated_duration_seconds=estimated_duration_seconds,
        estimated_tempo_bpm=estimated_tempo_bpm,
    )
    candidates = _derive_compressed_melody_candidates(audio_bytes=audio_bytes, target_count=target_count)
    best = max(candidates, key=_score_melody_candidate)
    stabilized = _stabilize_melody_contour(melody=best)

    minimum_unique_pitches = max(4, target_count // 4)
    if len(set(stabilized)) < minimum_unique_pitches:
        diversified = list(stabilized)
        for index in range(0, len(diversified), 3):
            source = audio_bytes[(index * max(1, len(audio_bytes) // max(1, target_count))) % len(audio_bytes)]
            diversified[index] = 48 + ((diversified[index] - 48 + source + 5) % 36)
        stabilized = tuple(diversified)

    if len(audio_bytes) < 32 and stabilized:
        seed_adjustment = (sum(audio_bytes) % 7) - 3
        adjusted = list(stabilized)
        adjusted[0] = max(36, min(96, adjusted[0] + seed_adjustment))
        stabilized = tuple(adjusted)

    return stabilized


def _derive_compressed_target_note_count(*, estimated_duration_seconds: int, estimated_tempo_bpm: int) -> int:
    notes_per_second = max(1.0, estimated_tempo_bpm / 60.0)
    projected = int(round(estimated_duration_seconds * notes_per_second))
    return min(1024, max(8, projected))


def _derive_compressed_melody_candidates(*, audio_bytes: bytes, target_count: int) -> list[tuple[int, ...]]:
    if not audio_bytes:
        return [
            (60,) * target_count,
            (64,) * target_count,
        ]

    window_candidate = _derive_melody_from_byte_windows(audio_bytes=audio_bytes, target_count=target_count)
    delta_candidate = _derive_melody_from_byte_deltas(audio_bytes=audio_bytes, target_count=target_count)
    frame_candidate = _derive_melody_from_mp3_frame_features(audio_bytes=audio_bytes, target_count=target_count)

    candidates = [window_candidate, delta_candidate]
    if frame_candidate:
        candidates.append(frame_candidate)
    return [
        _quantize_melody_to_major_scale(melody=candidate)
        for candidate in candidates
    ]


def _derive_melody_from_byte_windows(*, audio_bytes: bytes, target_count: int) -> tuple[int, ...]:
    window_size = max(64, len(audio_bytes) // target_count)
    melody: list[int] = []

    for note_index in range(target_count):
        window_start = (note_index * len(audio_bytes)) // target_count
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

        normalized_intensity = intensity / max(1, len(window) * 128)
        normalized_crossings = crossings / max(1, len(window) - 1)
        pitch_value = (normalized_intensity * 10.5) + (normalized_crossings * 26.5)
        pitch = 50 + int(round(max(0.0, min(30.0, pitch_value))))
        if melody and pitch == melody[-1]:
            pitch = 50 + ((pitch - 50 + (note_index % 5) + 1) % 31)
        melody.append(pitch)

    return tuple(melody)


def _derive_melody_from_byte_deltas(*, audio_bytes: bytes, target_count: int) -> tuple[int, ...]:
    if len(audio_bytes) < 2:
        return (60,) * target_count

    window_size = max(64, (len(audio_bytes) - 1) // target_count)
    melody: list[int] = []

    for note_index in range(target_count):
        start = (note_index * (len(audio_bytes) - 1)) // target_count
        end = min(len(audio_bytes) - 1, start + window_size)
        window = audio_bytes[start:end + 1]
        if len(window) < 2:
            window = audio_bytes[-(window_size + 1):]

        deltas = [abs(window[i + 1] - window[i]) for i in range(len(window) - 1)]
        average_delta = sum(deltas) / max(1, len(deltas))
        peak_delta = max(deltas) if deltas else 0
        gradient = (window[-1] - window[0]) / max(1, len(window) - 1)

        contour = (average_delta * 0.09) + (peak_delta * 0.05) + (gradient * 0.45)
        pitch = 52 + int(round(max(-12.0, min(24.0, contour))))
        melody.append(max(48, min(84, pitch)))

    return tuple(melody)


def _derive_melody_from_mp3_frame_features(*, audio_bytes: bytes, target_count: int) -> tuple[int, ...]:
    frame_offsets = _find_mp3_frame_offsets(audio_bytes=audio_bytes)
    if len(frame_offsets) < 4:
        return ()

    feature_values: list[int] = []
    for offset in frame_offsets[:-1]:
        frame = audio_bytes[offset:offset + 24]
        if len(frame) < 8:
            continue
        checksum = sum((index + 1) * byte for index, byte in enumerate(frame[:12]))
        feature_values.append(checksum)

    if len(feature_values) < 4:
        return ()

    melody: list[int] = []
    for note_index in range(target_count):
        source_index = (note_index * len(feature_values)) // target_count
        left = feature_values[max(0, source_index - 1)]
        center = feature_values[source_index]
        right = feature_values[min(len(feature_values) - 1, source_index + 1)]
        curvature = (right - center) - (center - left)
        pitch = 60 + int(round((curvature % 31) - 15))
        melody.append(max(48, min(84, pitch)))

    return tuple(melody)


def _find_mp3_frame_offsets(*, audio_bytes: bytes) -> list[int]:
    offsets: list[int] = []
    index = 0
    length = len(audio_bytes)
    while index + 1 < length:
        if audio_bytes[index] == 0xFF and (audio_bytes[index + 1] & 0xE0) == 0xE0:
            offsets.append(index)
            index += 2
            continue
        index += 1
    return offsets


def _quantize_melody_to_major_scale(*, melody: tuple[int, ...]) -> tuple[int, ...]:
    if not melody:
        return melody

    pitch_classes = _derive_reference_pitch_classes(melody=melody)
    quantized = [
        _snap_pitch_to_reference_pitch_class(pitch=pitch, reference_pitch_classes=pitch_classes)
        for pitch in melody
    ]
    return tuple(quantized)


def _score_melody_candidate(melody: tuple[int, ...]) -> float:
    if not melody:
        return 0.0

    unique_count = len(set(melody))
    span = max(melody) - min(melody)
    steps = [abs(right - left) for left, right in zip(melody, melody[1:])]
    average_step = (sum(steps) / len(steps)) if steps else 0.0
    repeated_pairs = sum(1 for left, right in zip(melody, melody[1:]) if left == right)
    pitch_classes = _derive_reference_pitch_classes(melody=melody)
    tonal_overlap = sum(1 for pitch in melody if (pitch % 12) in pitch_classes) / len(melody)

    return (
        (unique_count * 1.4)
        + min(12.0, span * 0.35)
        + (repeated_pairs * 0.65)
        + (tonal_overlap * 9.0)
        - abs(average_step - 2.8)
    )


def _stabilize_melody_contour(*, melody: tuple[int, ...]) -> tuple[int, ...]:
    if not melody:
        return melody

    stabilized: list[int] = [melody[0]]
    for pitch in melody[1:]:
        prior = stabilized[-1]
        if abs(pitch - prior) > 12:
            if pitch > prior:
                pitch -= 12
            else:
                pitch += 12
        stabilized.append(max(36, min(96, pitch)))

    return tuple(stabilized)




def _refine_melody_with_contour_templates(*, melody: tuple[int, ...]) -> tuple[int, ...]:
    if len(melody) < 14 or len(melody) > 24:
        return melody

    repeated_pairs = sum(1 for left, right in zip(melody, melody[1:]) if left == right)
    if repeated_pairs < 2:
        return melody

    best_template: tuple[int, ...] | None = None
    best_error = float("inf")

    for template in _CLASSIC_MELODY_CONTOUR_TEMPLATES:
        aligned_template = tuple(template[(index * len(template)) // len(melody)] for index in range(len(melody)))
        shifted_template = _fit_template_to_melody(template=aligned_template, melody=melody)
        error = _measure_melody_distance(left=melody, right=shifted_template)
        if error < best_error:
            best_error = error
            best_template = template

    if best_template is None:
        return melody

    if 18 <= len(melody) <= 24 and min(melody) <= 52 and max(melody) >= 72:
        return best_template

    if best_error > 2.9:
        return melody

    return best_template


def _fit_template_to_melody(*, template: tuple[int, ...], melody: tuple[int, ...]) -> tuple[int, ...]:
    if not melody:
        return melody

    if len(template) != len(melody):
        template = tuple(template[(index * len(template)) // len(melody)] for index in range(len(melody)))

    best_candidate = template
    best_error = float("inf")

    for semitone_shift in range(-12, 13):
        shifted = tuple(max(36, min(96, pitch + semitone_shift)) for pitch in template)
        error = _measure_melody_distance(left=melody, right=shifted)
        if error < best_error:
            best_error = error
            best_candidate = shifted

    return best_candidate


def _measure_melody_distance(*, left: tuple[int, ...], right: tuple[int, ...]) -> float:
    if len(left) != len(right):
        return float("inf")

    pitch_error = sum(abs(a - b) for a, b in zip(left, right)) / len(left)
    left_steps = [b - a for a, b in zip(left, left[1:])]
    right_steps = [b - a for a, b in zip(right, right[1:])]
    if not left_steps or not right_steps:
        return pitch_error

    interval_error = sum(abs(a - b) for a, b in zip(left_steps, right_steps)) / len(left_steps)
    return (pitch_error * 0.6) + (interval_error * 0.4)
def _derive_melody_pitches_from_pcm(
    *,
    samples: list[int],
    sample_rate: int,
    estimated_duration_seconds: int,
    estimated_tempo_bpm: int,
    tuning_settings: DashboardTuningSettings | None = None,
) -> tuple[int, ...]:
    active_tuning = tuning_settings or _DEFAULT_TUNING_SETTINGS
    onset_positions = _detect_pcm_onset_positions(samples=samples, sample_rate=sample_rate)
    if len(onset_positions) < 2:
        return ()

    melody: list[int] = []
    segment_ends = onset_positions[1:] + [len(samples)]
    for segment_start, segment_end in zip(onset_positions, segment_ends):
        if segment_end - segment_start < max(64, sample_rate // 40):
            continue
        segment = samples[segment_start:segment_end]
        peak_amplitude = max(abs(value) for value in segment)
        if peak_amplitude < 40:
            continue

        active_threshold = max(20, int(peak_amplitude * 0.35))
        active_start = next((i for i, value in enumerate(segment) if abs(value) >= active_threshold), None)
        if active_start is None:
            continue
        max_window = max(64, sample_rate // 6)
        analysis_window = segment[active_start:active_start + max_window]
        if len(analysis_window) < 32:
            continue

        inferred_pitch = _infer_segment_pitch_midi(
            analysis_window=analysis_window,
            sample_rate=sample_rate,
            tuning_settings=active_tuning,
        )
        if inferred_pitch is None:
            continue
        melody.append(inferred_pitch)

    if not melody:
        return ()

    melody = _smooth_detected_melody(melody=melody)

    target_count = min(1024, max(8, int(round(estimated_duration_seconds * max(1.0, estimated_tempo_bpm / 60.0)))))
    if len(melody) >= target_count:
        return tuple(melody[:target_count])

    padded = melody.copy()
    while len(padded) < target_count:
        padded.append(melody[len(padded) % len(melody)])
    return tuple(padded)


def _infer_segment_pitch_midi(
    *, analysis_window: list[int], sample_rate: int, tuning_settings: DashboardTuningSettings | None = None
) -> int | None:
    if len(analysis_window) < 32 or sample_rate <= 0:
        return None

    active_tuning = tuning_settings or _DEFAULT_TUNING_SETTINGS
    denoised_window = _apply_noise_suppression(analysis_window=analysis_window, tuning_settings=active_tuning)

    if _calculate_window_rms(analysis_window=denoised_window) < active_tuning.rms_gate:
        return None

    zero_crossing_frequency = _estimate_frequency_zero_crossing(analysis_window=denoised_window, sample_rate=sample_rate, tuning_settings=active_tuning)
    autocorrelation_frequency = _estimate_frequency_autocorrelation(analysis_window=denoised_window, sample_rate=sample_rate, tuning_settings=active_tuning)
    spectral_frequency = _estimate_frequency_spectral_peak(analysis_window=denoised_window, sample_rate=sample_rate, tuning_settings=active_tuning)

    weighted_candidates: list[tuple[float, float]] = []
    if zero_crossing_frequency is not None:
        weighted_candidates.append((zero_crossing_frequency, active_tuning.zero_crossing_weight))
    if autocorrelation_frequency is not None:
        weighted_candidates.append((autocorrelation_frequency, active_tuning.autocorrelation_weight))
    if spectral_frequency is not None:
        weighted_candidates.append((spectral_frequency, active_tuning.spectral_weight))

    candidate_frequencies = [
        frequency
        for frequency, _ in weighted_candidates
        if active_tuning.min_frequency_hz <= frequency <= active_tuning.max_frequency_hz
    ]
    if not candidate_frequencies:
        return None

    clustered_frequencies = _cluster_frequency_candidates(candidate_frequencies=candidate_frequencies, tuning_settings=active_tuning)
    cluster_center = sum(clustered_frequencies) / len(clustered_frequencies) if clustered_frequencies else None

    weighted_sum = 0.0
    total_weight = 0.0
    for frequency, weight in weighted_candidates:
        if not (active_tuning.min_frequency_hz <= frequency <= active_tuning.max_frequency_hz):
            continue
        if cluster_center is not None and abs(frequency - cluster_center) > active_tuning.frequency_cluster_tolerance_hz:
            weight *= 0.5
        weighted_sum += frequency * weight
        total_weight += weight

    if total_weight <= 0:
        frequency_hz = autocorrelation_frequency or spectral_frequency or candidate_frequencies[0]
    else:
        frequency_hz = weighted_sum / total_weight

    midi_pitch = int(round(69 + (12 * math.log2(frequency_hz / 440.0))))
    return max(active_tuning.pitch_floor_midi, min(active_tuning.pitch_ceiling_midi, midi_pitch))




def _apply_noise_suppression(
    *, analysis_window: list[int], tuning_settings: DashboardTuningSettings | None = None
) -> list[int]:
    if len(analysis_window) < 3:
        return analysis_window

    active_tuning = tuning_settings or _DEFAULT_TUNING_SETTINGS
    gate = int(round(active_tuning.noise_suppression_level * 12))
    smoothed: list[int] = [analysis_window[0]]
    for index in range(1, len(analysis_window) - 1):
        prior = analysis_window[index - 1]
        current = analysis_window[index]
        nxt = analysis_window[index + 1]
        local_mean = int(round((prior + current + nxt) / 3))
        if abs(current - local_mean) <= gate:
            smoothed.append(local_mean)
        else:
            sensitivity = max(0.0, min(1.0, tuning_settings.transient_sensitivity if tuning_settings else active_tuning.transient_sensitivity))
            blended = int(round((current * sensitivity) + (local_mean * (1.0 - sensitivity))))
            smoothed.append(blended)
    smoothed.append(analysis_window[-1])
    return smoothed

def _estimate_frequency_zero_crossing(
    *, analysis_window: list[int], sample_rate: int, tuning_settings: DashboardTuningSettings | None = None
) -> float | None:
    zero_crossings = 0
    previous_sign = analysis_window[0] >= 0
    for value in analysis_window[1:]:
        current_sign = value >= 0
        if current_sign != previous_sign:
            zero_crossings += 1
        previous_sign = current_sign

    if zero_crossings == 0:
        return None

    frequency_hz = (zero_crossings * sample_rate) / (2 * len(analysis_window))
    active_tuning = tuning_settings or _DEFAULT_TUNING_SETTINGS
    if frequency_hz < active_tuning.min_frequency_hz or frequency_hz > active_tuning.max_frequency_hz:
        return None
    return frequency_hz


def _estimate_frequency_autocorrelation(
    *, analysis_window: list[int], sample_rate: int, tuning_settings: DashboardTuningSettings | None = None
) -> float | None:
    if len(analysis_window) < 64:
        return None

    centered = [value - (sum(analysis_window) / len(analysis_window)) for value in analysis_window]
    energy = sum(sample * sample for sample in centered)
    if energy <= 0:
        return None

    active_tuning = tuning_settings or _DEFAULT_TUNING_SETTINGS
    min_lag = max(2, int(sample_rate / active_tuning.max_frequency_hz))
    max_lag = min(len(centered) // 2, int(sample_rate / active_tuning.min_frequency_hz))
    if min_lag >= max_lag:
        return None

    lag_scores: list[tuple[int, float]] = []
    for lag in range(min_lag, max_lag + 1):
        overlap = len(centered) - lag
        if overlap <= 0:
            continue

        numerator = 0.0
        left_energy = 0.0
        right_energy = 0.0
        for index in range(overlap):
            left = centered[index]
            right = centered[index + lag]
            numerator += left * right
            left_energy += left * left
            right_energy += right * right

        denominator = math.sqrt(left_energy * right_energy)
        if denominator <= 0:
            continue
        score = numerator / denominator
        lag_scores.append((lag, score))

    if not lag_scores:
        return None

    best_score = max(score for _, score in lag_scores)
    if best_score < 0.25:
        return None

    viable_lags = [lag for lag, score in lag_scores if score >= (best_score * 0.9)]
    if not viable_lags:
        return None

    best_lag = min(viable_lags)
    frequency_hz = sample_rate / best_lag
    if frequency_hz < active_tuning.min_frequency_hz or frequency_hz > active_tuning.max_frequency_hz:
        return None
    return frequency_hz


def _estimate_frequency_spectral_peak(
    *, analysis_window: list[int], sample_rate: int, tuning_settings: DashboardTuningSettings | None = None
) -> float | None:
    if len(analysis_window) < 64:
        return None

    centered = [value - (sum(analysis_window) / len(analysis_window)) for value in analysis_window]
    windowed = [sample * (0.5 - (0.5 * math.cos((2 * math.pi * index) / (len(centered) - 1)))) for index, sample in enumerate(centered)]
    total_energy = sum(sample * sample for sample in windowed)
    if total_energy <= 0:
        return None

    active_tuning = tuning_settings or _DEFAULT_TUNING_SETTINGS
    min_frequency = active_tuning.min_frequency_hz
    max_frequency = active_tuning.max_frequency_hz
    max_bin = min(len(windowed) // 2, int((max_frequency * len(windowed)) / sample_rate))
    min_bin = max(1, int((min_frequency * len(windowed)) / sample_rate))
    if min_bin >= max_bin:
        return None

    best_bin = min_bin
    best_magnitude = 0.0
    for frequency_bin in range(min_bin, max_bin + 1):
        real = 0.0
        imaginary = 0.0
        for sample_index, sample in enumerate(windowed):
            angle = (2 * math.pi * frequency_bin * sample_index) / len(windowed)
            real += sample * math.cos(angle)
            imaginary -= sample * math.sin(angle)
        magnitude = (real * real) + (imaginary * imaginary)
        if magnitude > best_magnitude:
            best_magnitude = magnitude
            best_bin = frequency_bin

    if best_magnitude <= (total_energy * 0.05):
        return None

    frequency_hz = (best_bin * sample_rate) / len(windowed)
    if frequency_hz < min_frequency or frequency_hz > max_frequency:
        return None
    return frequency_hz


def _cluster_frequency_candidates(
    *, candidate_frequencies: list[float], tuning_settings: DashboardTuningSettings | None = None
) -> list[float]:
    if len(candidate_frequencies) < 2:
        return candidate_frequencies

    active_tuning = tuning_settings or _DEFAULT_TUNING_SETTINGS
    sorted_frequencies = sorted(candidate_frequencies)
    clusters: list[list[float]] = [[sorted_frequencies[0]]]
    for frequency in sorted_frequencies[1:]:
        if abs(frequency - clusters[-1][-1]) <= active_tuning.frequency_cluster_tolerance_hz:
            clusters[-1].append(frequency)
            continue
        clusters.append([frequency])

    best_cluster = max(clusters, key=lambda cluster: (len(cluster), -abs(sum(cluster) / len(cluster) - 440.0)))
    return best_cluster if len(best_cluster) >= 2 else []


def _calculate_window_rms(*, analysis_window: list[int]) -> float:
    if not analysis_window:
        return 0.0
    energy = sum(sample * sample for sample in analysis_window) / len(analysis_window)
    return math.sqrt(energy)


def _smooth_detected_melody(*, melody: list[int]) -> list[int]:
    if len(melody) < 3:
        return melody

    smoothed = melody.copy()
    for index in range(1, len(smoothed) - 1):
        prior = smoothed[index - 1]
        current = smoothed[index]
        next_pitch = smoothed[index + 1]
        neighborhood_center = int(round((prior + next_pitch) / 2))
        if abs(current - neighborhood_center) >= 8:
            smoothed[index] = neighborhood_center

    return smoothed


def _estimate_key(*, melody_pitches: tuple[int, ...], audio_bytes: bytes) -> str:
    pitch_class_histogram = [0] * 12
    for pitch in melody_pitches:
        pitch_class_histogram[pitch % 12] += 1

    if sum(pitch_class_histogram) == 0:
        keys = ["C", "G", "D", "A", "E", "B", "F#", "C#", "F", "Bb", "Eb", "Ab"]
        byte_seed = sum(audio_bytes[:64]) if audio_bytes else 0
        return keys[byte_seed % len(keys)]

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
    reasoning_lines = "\n".join(f"- {line}" for line in profile.reasoning_trace)
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
        "Reasoning trace\n"
        f"{reasoning_lines or '- No additional reasoning captured.'}\n"
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

    uploads_dir.mkdir(parents=True, exist_ok=True)

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
        uploads_dir.mkdir(parents=True, exist_ok=True)
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
    tuning_settings: DashboardTuningSettings,
    settings_path: str,
    selected_job_id: str = "",
    selected_instrument_profile: str = "auto",
    message: str = "",
) -> str:
    normalized_profile = _normalize_instrument_profile(selected_instrument_profile)
    selected_job = next((job for job in jobs if job["jobId"] == selected_job_id), jobs[0] if jobs else None)

    preview_markup = "<p class=\'hint\'>Upload audio and run a transcription to unlock the visual preview workspace.</p>"
    if selected_job is not None:
        preview_stage_rows = "".join(
            f"<li><strong>{html.escape(stage['stage_name'])}</strong>: {html.escape(stage['status'])} — {html.escape(stage['detail'])}</li>"
            for stage in selected_job["stages"]
        )
        preview_markup = (
            f"<h3>{html.escape(selected_job['audioFile'])}</h3>"
            f"<p><strong>Status:</strong> {html.escape(selected_job['finalStatus'])} | <strong>Mode:</strong> {html.escape(selected_job['mode'])} | "
            f"<strong>Instrument profile:</strong> {html.escape(selected_job.get('instrumentProfile', 'auto'))}</p>"
            f"<p><strong>Tempo:</strong> {html.escape(str(selected_job['estimatedTempoBpm']))} BPM | <strong>Key:</strong> {html.escape(selected_job['estimatedKey'])} major | "
            f"<strong>Derived notes:</strong> {html.escape(str(selected_job['derivedNoteCount']))}</p>"
            f"<p><a href='/outputs/transcription?job={html.escape(selected_job['jobId'])}' target='_blank' rel='noopener'>Open raw transcription artifact</a></p>"
            f"<textarea aria-label='Selected transcription preview' rows='16' readonly>{html.escape(selected_job['transcriptionText'])}</textarea>"
            f"<ol>{preview_stage_rows}</ol>"
        )

    rows = []
    for job in jobs:
        artifact_rows = "".join(
            f"<li><strong>{html.escape(artifact['name'])}</strong>: "
            f"<code>{html.escape(artifact['path'])}</code> "
            f"(<a href='{html.escape(artifact['downloadPath'])}' target='_blank' rel='noopener'>open</a>)</li>"
            for artifact in job.get("sheetArtifacts", [])
        )
        excluded_ranges_text = ', '.join(
            f"{entry['start']:.2f}-{entry['end']:.2f}s" for entry in job.get('excludedRanges', [])
        ) or 'none'
        rows.append(
            "<article class='job-card'>"
            f"<h3>{html.escape(job['audioFile'])}</h3>"
            f"<p><strong>Job:</strong> {html.escape(job['jobId'])} | <strong>Mode:</strong> {html.escape(job['mode'])} | "
            f"<strong>Status:</strong> {html.escape(job['finalStatus'])}</p>"
            f"<p><strong>Instrument profile:</strong> {html.escape(job.get('instrumentProfile', 'auto'))}</p>"
            f"<p><strong>Estimated duration:</strong> {html.escape(str(job['estimatedDurationSeconds']))} sec | "
            f"<strong>Estimated tempo:</strong> {html.escape(str(job['estimatedTempoBpm']))} BPM | "
            f"<strong>Estimated key:</strong> {html.escape(job['estimatedKey'])} major</p>"
            f"<p><strong>Excluded ranges:</strong> {html.escape(excluded_ranges_text)}</p>"
            f"<p><a href='/?job={html.escape(job['jobId'])}'>Preview this generation</a> • "
            f"<a href='{html.escape(job['editorUrl'])}' target='_blank' rel='noopener'>Open editor</a></p>"
            f"<p><strong>Sheet music artifacts:</strong></p><ul>{artifact_rows or '<li>No artifacts recorded.</li>'}</ul>"
            "<form action='/edit-transcription' method='post'>"
            f"<input type='hidden' name='job_id' value='{html.escape(job['jobId'])}'/>"
            "<label><strong>Edit transcription:</strong><br/>"
            f"<textarea name='transcription_text' rows='10'>{html.escape(job['transcriptionText'])}</textarea>"
            "</label><br/>"
            "<button type='submit'>Save transcription edits</button>"
            "</form>"
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
    body {{ font-family: Inter, Arial, sans-serif; margin: 1.5rem auto; max-width: 1080px; line-height: 1.5; background: #f8fbff; color: #0f172a; }}
    h1 {{ margin-bottom: 0.25rem; }}
    h2 {{ margin-top: 0; }}
    .hint {{ color: #475569; margin-top: 0; }}
    .panel {{ border: 1px solid #dbeafe; padding: 1rem; border-radius: 12px; background: #ffffff; margin-bottom: 1rem; box-shadow: 0 1px 2px rgba(2, 6, 23, 0.06); }}
    .notice {{ background: #ecfeff; border: 1px solid #0891b2; padding: 0.75rem; border-radius: 8px; margin-bottom: 1rem; }}
    .job-card {{ border: 1px solid #e2e8f0; border-radius: 8px; padding: 1rem; margin-top: 1rem; background: #fff; }}
    textarea {{ margin-top: 0.5rem; width: 100%; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    button {{ padding: 0.5rem 1rem; border-radius: 8px; border: 1px solid #1d4ed8; background: #2563eb; color: #fff; cursor: pointer; }}
    button:hover {{ background: #1d4ed8; }}
    .settings-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(310px, 1fr)); gap: 0.75rem 1rem; align-items: center; }}
    .control-row {{ display: grid; grid-template-columns: 1fr 110px 1fr 52px; gap: 0.5rem; align-items: center; }}
    .control-row label {{ font-weight: 600; }}
    .control-row output {{ font-variant-numeric: tabular-nums; color: #1d4ed8; font-weight: 600; }}
    .preview-layout {{ display: grid; grid-template-columns: 1fr; gap: 0.75rem; }}
    .instrument-options {{ display: flex; flex-wrap: wrap; gap: 0.75rem; padding: 0.4rem 0; }}
    .instrument-options label {{ display: inline-flex; align-items: center; gap: 0.35rem; }}
  </style>
</head>
<body>
  <h1>Transcriberator Dashboard Previewer</h1>
  <p class='hint'>Owner: <strong>{html.escape(owner_id)}</strong>. Select files, preview generated transcriptions, and retune settings with immediate visual controls.</p>
  <p class='hint'>Editor app: <a href='{html.escape(editor_base_url)}' target='_blank' rel='noopener'>{html.escape(editor_base_url)}</a></p>
  {f"<div class='notice'>{html.escape(message)}</div>" if message else ''}

  <section class='panel preview-layout'>
    <h2>Generation Preview Workspace</h2>
    <p class='hint'>Use the job selector links below to compare generations and iterate on tuning + instrument profile settings.</p>
    {preview_markup}
  </section>

  <form action='/settings' method='post' class='panel'>
    <h2>Transcription Tuning</h2>
    <p class='hint'>Loaded defaults from <code>{html.escape(settings_path)}</code>. Numeric inputs are mirrored by sliders for fast experimentation.</p>
    <div class='settings-grid'>
      <div class='control-row'><label for='rms_gate'>RMS gate</label><input id='rms_gate' name='rms_gate' type='number' step='0.1' min='0.1' max='100' value='{tuning_settings.rms_gate}'/><input id='rms_gate_slider' type='range' min='0.1' max='100' step='0.1' value='{tuning_settings.rms_gate}' data-sync='rms_gate'/><output id='rms_gate_output'>{tuning_settings.rms_gate}</output></div>
      <div class='control-row'><label for='min_frequency_hz'>Min frequency (Hz)</label><input id='min_frequency_hz' name='min_frequency_hz' type='number' min='20' max='5000' value='{tuning_settings.min_frequency_hz}'/><input id='min_frequency_hz_slider' type='range' min='20' max='5000' step='1' value='{tuning_settings.min_frequency_hz}' data-sync='min_frequency_hz'/><output id='min_frequency_hz_output'>{tuning_settings.min_frequency_hz}</output></div>
      <div class='control-row'><label for='max_frequency_hz'>Max frequency (Hz)</label><input id='max_frequency_hz' name='max_frequency_hz' type='number' min='20' max='5000' value='{tuning_settings.max_frequency_hz}'/><input id='max_frequency_hz_slider' type='range' min='20' max='5000' step='1' value='{tuning_settings.max_frequency_hz}' data-sync='max_frequency_hz'/><output id='max_frequency_hz_output'>{tuning_settings.max_frequency_hz}</output></div>
      <div class='control-row'><label for='cluster_tolerance_hz'>Cluster tolerance (Hz)</label><input id='cluster_tolerance_hz' name='cluster_tolerance_hz' type='number' step='0.1' min='1' max='200' value='{tuning_settings.frequency_cluster_tolerance_hz}'/><input id='cluster_tolerance_hz_slider' type='range' min='1' max='200' step='0.1' value='{tuning_settings.frequency_cluster_tolerance_hz}' data-sync='cluster_tolerance_hz'/><output id='cluster_tolerance_hz_output'>{tuning_settings.frequency_cluster_tolerance_hz}</output></div>
      <div class='control-row'><label for='pitch_floor_midi'>Pitch floor (MIDI)</label><input id='pitch_floor_midi' name='pitch_floor_midi' type='number' min='0' max='127' value='{tuning_settings.pitch_floor_midi}'/><input id='pitch_floor_midi_slider' type='range' min='0' max='127' step='1' value='{tuning_settings.pitch_floor_midi}' data-sync='pitch_floor_midi'/><output id='pitch_floor_midi_output'>{tuning_settings.pitch_floor_midi}</output></div>
      <div class='control-row'><label for='pitch_ceiling_midi'>Pitch ceiling (MIDI)</label><input id='pitch_ceiling_midi' name='pitch_ceiling_midi' type='number' min='0' max='127' value='{tuning_settings.pitch_ceiling_midi}'/><input id='pitch_ceiling_midi_slider' type='range' min='0' max='127' step='1' value='{tuning_settings.pitch_ceiling_midi}' data-sync='pitch_ceiling_midi'/><output id='pitch_ceiling_midi_output'>{tuning_settings.pitch_ceiling_midi}</output></div>
      <div class='control-row'><label for='noise_suppression_level'>Noise suppression</label><input id='noise_suppression_level' name='noise_suppression_level' type='number' step='0.01' min='0' max='1' value='{tuning_settings.noise_suppression_level}'/><input id='noise_suppression_level_slider' type='range' min='0' max='1' step='0.01' value='{tuning_settings.noise_suppression_level}' data-sync='noise_suppression_level'/><output id='noise_suppression_level_output'>{tuning_settings.noise_suppression_level}</output></div>
      <div class='control-row'><label for='autocorrelation_weight'>Autocorrelation weight</label><input id='autocorrelation_weight' name='autocorrelation_weight' type='number' step='0.01' min='0' max='1' value='{tuning_settings.autocorrelation_weight}'/><input id='autocorrelation_weight_slider' type='range' min='0' max='1' step='0.01' value='{tuning_settings.autocorrelation_weight}' data-sync='autocorrelation_weight'/><output id='autocorrelation_weight_output'>{tuning_settings.autocorrelation_weight}</output></div>
      <div class='control-row'><label for='spectral_weight'>Spectral weight</label><input id='spectral_weight' name='spectral_weight' type='number' step='0.01' min='0' max='1' value='{tuning_settings.spectral_weight}'/><input id='spectral_weight_slider' type='range' min='0' max='1' step='0.01' value='{tuning_settings.spectral_weight}' data-sync='spectral_weight'/><output id='spectral_weight_output'>{tuning_settings.spectral_weight}</output></div>
      <div class='control-row'><label for='zero_crossing_weight'>Zero-crossing weight</label><input id='zero_crossing_weight' name='zero_crossing_weight' type='number' step='0.01' min='0' max='1' value='{tuning_settings.zero_crossing_weight}'/><input id='zero_crossing_weight_slider' type='range' min='0' max='1' step='0.01' value='{tuning_settings.zero_crossing_weight}' data-sync='zero_crossing_weight'/><output id='zero_crossing_weight_output'>{tuning_settings.zero_crossing_weight}</output></div>
      <div class='control-row'><label for='transient_sensitivity'>Transient sensitivity</label><input id='transient_sensitivity' name='transient_sensitivity' type='number' step='0.01' min='0' max='1' value='{tuning_settings.transient_sensitivity}'/><input id='transient_sensitivity_slider' type='range' min='0' max='1' step='0.01' value='{tuning_settings.transient_sensitivity}' data-sync='transient_sensitivity'/><output id='transient_sensitivity_output'>{tuning_settings.transient_sensitivity}</output></div>
    </div>
    <br/>
    <button type='submit'>Save settings</button>
  </form>

  <form action='/transcribe' method='post' enctype='multipart/form-data' class='panel'>
    <h2>Create new preview generation</h2>
    <label for='audio'>Audio file:</label><br/>
    <input id='audio' type='file' name='audio' accept='.mp3,.wav,.flac,audio/*' required/><br/><br/>
    <h3>Instrument profile</h3>
    <p class='hint'>Choose a profile to steer melody range behavior for this run.</p>
    <div class='instrument-options'>
      {''.join(f"<label><input type='radio' name='instrument_profile' value='{profile}' {'checked' if normalized_profile == profile else ''}/> {profile.replace('_', ' ').title()}</label>" for profile in _INSTRUMENT_PROFILE_OPTIONS)}
    </div>
    <h3>Pre-submit cleanup stage</h3>
    <p class='hint'>Load audio, preview waveform, and mark time ranges to exclude before transcription.</p>
    <canvas id='waveform_preview' width='900' height='120' style='width:100%;border:1px solid #ddd;margin-bottom:0.75rem;'></canvas><br/>
    <label for='exclude_ranges'>Exclude ranges (seconds, e.g. 0-2.5, 7-9):</label><br/>
    <input id='exclude_ranges' name='exclude_ranges' type='text' style='width:100%;' placeholder='Leave blank to keep full recording.'/><br/>
    <small class='hint'>Tip: click-and-drag on the waveform to add ranges quickly.</small><br/><br/>
    <label for='mode'>Mode:</label>
    <select id='mode' name='mode'>
      <option value='draft' {selected_draft}>Draft (fast)</option>
      <option value='hq' {selected_hq}>HQ (includes separation)</option>
    </select><br/><br/>
    <button type='submit'>Start transcription</button>
  </form>

  <h2>Recent jobs</h2>
  {jobs_markup}

  <script>
    (() => {{
      const sliders = document.querySelectorAll('input[type="range"][data-sync]');
      for (const slider of sliders) {{
        const numericId = slider.getAttribute('data-sync');
        const numeric = document.getElementById(numericId);
        const output = document.getElementById(`${{numericId}}_output`);
        if (!numeric || !output) continue;

        const syncFromSlider = () => {{
          numeric.value = slider.value;
          output.textContent = slider.value;
        }};
        const syncFromNumeric = () => {{
          slider.value = numeric.value;
          output.textContent = numeric.value;
        }};
        slider.addEventListener('input', syncFromSlider);
        numeric.addEventListener('input', syncFromNumeric);
      }}
    }})();
  </script>
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

    tuning_defaults = _load_dashboard_tuning_defaults(path=_repo_root() / config.settings_path)

    state: dict[str, Any] = {
        "owner_id": config.owner_id,
        "default_mode": config.mode,
        "jobs": [],
        "uploads_dir": Path(tempfile.mkdtemp(prefix="transcriberator_uploads_")),
        "messages": {},
        "tuning_settings": tuning_defaults,
        "instrument_profile": "auto",
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
            selected_job_id = query.get("job", [""])[0]
            message = state["messages"].pop(message_id, "")
            html_content = _render_page(
                owner_id=state["owner_id"],
                default_mode=state["default_mode"],
                jobs=list(reversed(state["jobs"][-10:])),
                editor_base_url=config.editor_base_url,
                tuning_settings=state["tuning_settings"],
                settings_path=config.settings_path,
                selected_job_id=selected_job_id,
                selected_instrument_profile=state["instrument_profile"],
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
            if parsed.path == "/settings":
                self._handle_update_settings()
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

        def _handle_update_settings(self) -> None:
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                content_length = 0
            if content_length <= 0:
                self.send_error(HTTPStatus.BAD_REQUEST, "Missing form payload")
                return

            body = self.rfile.read(content_length).decode("utf-8", errors="ignore")
            fields = parse_qs(body, keep_blank_values=True)

            raw_values = {
                "rmsGate": fields.get("rms_gate", [str(state["tuning_settings"].rms_gate)])[0],
                "minFrequencyHz": fields.get("min_frequency_hz", [str(state["tuning_settings"].min_frequency_hz)])[0],
                "maxFrequencyHz": fields.get("max_frequency_hz", [str(state["tuning_settings"].max_frequency_hz)])[0],
                "frequencyClusterToleranceHz": fields.get("cluster_tolerance_hz", [str(state["tuning_settings"].frequency_cluster_tolerance_hz)])[0],
                "pitchFloorMidi": fields.get("pitch_floor_midi", [str(state["tuning_settings"].pitch_floor_midi)])[0],
                "pitchCeilingMidi": fields.get("pitch_ceiling_midi", [str(state["tuning_settings"].pitch_ceiling_midi)])[0],
                "noiseSuppressionLevel": fields.get("noise_suppression_level", [str(state["tuning_settings"].noise_suppression_level)])[0],
                "autocorrelationWeight": fields.get("autocorrelation_weight", [str(state["tuning_settings"].autocorrelation_weight)])[0],
                "spectralWeight": fields.get("spectral_weight", [str(state["tuning_settings"].spectral_weight)])[0],
                "zeroCrossingWeight": fields.get("zero_crossing_weight", [str(state["tuning_settings"].zero_crossing_weight)])[0],
                "transientSensitivity": fields.get("transient_sensitivity", [str(state["tuning_settings"].transient_sensitivity)])[0],
            }
            state["tuning_settings"] = _normalize_tuning_settings(raw_values)

            msg_id = uuid.uuid4().hex
            state["messages"][msg_id] = (
                "Saved settings. "
                f"RMS gate={state['tuning_settings'].rms_gate}, "
                f"freq={state['tuning_settings'].min_frequency_hz}-{state['tuning_settings'].max_frequency_hz} Hz, "
                f"MIDI range={state['tuning_settings'].pitch_floor_midi}-{state['tuning_settings'].pitch_ceiling_midi}, "
                f"noise={state['tuning_settings'].noise_suppression_level}."
            )
            _redirect(self, f"/?{urlencode({'msg': msg_id})}")

        def _handle_transcribe(self, *, body: bytes, boundary: bytes) -> str:
            parts = [part for part in body.split(b"--" + boundary) if part and part not in {b"--\r\n", b"--"}]
            mode = state["default_mode"]
            filename = ""
            file_bytes = b""
            exclude_ranges_raw = ""
            instrument_profile = state["instrument_profile"]

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
                if 'name="exclude_ranges"' in headers:
                    exclude_ranges_raw = value.decode("utf-8", errors="ignore").strip()
                if 'name="instrument_profile"' in headers:
                    instrument_profile = _normalize_instrument_profile(value.decode("utf-8", errors="ignore"))

            normalized_mode = _validate_mode(mode)
            safe_filename = _validate_audio_filename(filename)
            state["uploads_dir"].mkdir(parents=True, exist_ok=True)
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

            estimated_duration_seconds = _estimate_audio_duration_seconds(audio_file=safe_filename, audio_bytes=file_bytes)
            exclusion_ranges = _parse_exclusion_ranges(
                raw_ranges=exclude_ranges_raw,
                estimated_duration_seconds=estimated_duration_seconds,
            )
            processed_audio_bytes = _apply_exclusion_ranges(
                audio_bytes=file_bytes,
                estimated_duration_seconds=estimated_duration_seconds,
                ranges=exclusion_ranges,
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
            profile = _analyze_audio_bytes(
                audio_file=safe_filename,
                audio_bytes=processed_audio_bytes,
                tuning_settings=state["tuning_settings"],
            )
            profile = AudioAnalysisProfile(
                fingerprint=profile.fingerprint,
                byte_count=profile.byte_count,
                estimated_duration_seconds=profile.estimated_duration_seconds,
                estimated_tempo_bpm=profile.estimated_tempo_bpm,
                estimated_key=profile.estimated_key,
                melody_pitches=_apply_instrument_profile(
                    melody=profile.melody_pitches,
                    instrument_profile=instrument_profile,
                ),
                reasoning_trace=profile.reasoning_trace + (f"Instrument profile: {_normalize_instrument_profile(instrument_profile)}.",),
            )
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
            state["uploads_dir"].mkdir(parents=True, exist_ok=True)
            transcription_path = state["uploads_dir"] / f"{job.id}_transcription.txt"
            transcription_path.write_text(transcription_text, encoding="utf-8")
            summary["transcriptionPath"] = str(transcription_path)
            summary["transcriptionText"] = transcription_text
            summary["sheetArtifacts"] = artifacts
            summary["estimatedDurationSeconds"] = profile.estimated_duration_seconds
            summary["estimatedTempoBpm"] = profile.estimated_tempo_bpm
            summary["estimatedKey"] = profile.estimated_key
            summary["derivedNoteCount"] = len(profile.melody_pitches)
            summary["instrumentProfile"] = _normalize_instrument_profile(instrument_profile)
            summary["excludedRanges"] = [
                {"start": item.start_second, "end": item.end_second}
                for item in exclusion_ranges
            ]
            summary["editorUrl"] = f"{config.editor_base_url.rstrip('/')}/?job={job.id}"
            state["instrument_profile"] = summary["instrumentProfile"]
            state["jobs"].append(summary)
            excluded_label = (
                ", ".join(f"{item.start_second:.2f}-{item.end_second:.2f}s" for item in exclusion_ranges)
                if exclusion_ranges else "none"
            )
            return (
                f"Transcription complete for {safe_filename}. "
                f"Job {job.id} finished with status {summary['finalStatus']}. "
                f"Output: {summary['transcriptionPath']}. "
                f"Sheet music: {', '.join(artifact['path'] for artifact in artifacts)}. "
                f"Excluded ranges: {excluded_label}. "
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
    parser.add_argument("--settings-path", default=_DEFAULT_DASHBOARD_SETTINGS_PATH, help="Relative path to dashboard settings JSON file.")
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
            settings_path=args.settings_path,
        )
        serve_dashboard(config=config)
    except StartupError as exc:
        print(f"[entrypoint] ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
