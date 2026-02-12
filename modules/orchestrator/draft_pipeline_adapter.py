"""DT-017 Draft pipeline integration adapter.

This adapter composes phase-2 skeleton workers into a minimal Draft pipeline slice
covering Stage A (decode/normalize), C (tempo map extraction placeholder),
D (transcription), E (quantization), and F (MusicXML + MIDI generation).
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from pathlib import Path
import sys
from typing import Any


_ROOT = Path(__file__).resolve().parents[2]


def _load_module(module_name: str, relative_path: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, _ROOT / relative_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module for path {relative_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


audio_mod = _load_module("worker_audio_skeleton_dt017", "modules/worker-audio/worker_audio_skeleton.py")
transcription_mod = _load_module(
    "worker_transcription_skeleton_dt017", "modules/worker-transcription/worker_transcription_skeleton.py"
)
quantization_mod = _load_module(
    "worker_quantization_skeleton_dt017", "modules/worker-quantization/worker_quantization_skeleton.py"
)
observability_mod = _load_module("orchestrator_observability_dt020", "modules/orchestrator/observability.py")


@dataclass(frozen=True)
class DraftPipelineRequest:
    asset_id: str
    source_uri: str
    audio_format: str
    polyphonic: bool = False
    snap_division: int = 16


@dataclass(frozen=True)
class DraftPipelineResult:
    normalized_uri: str
    waveform_uri: str
    proxy_uri: str
    tempo_map_uri: str
    musicxml_uri: str
    midi_uri: str
    event_count: int
    quantized_event_count: int
    confidence: float
    had_tuplets: bool


class DraftPipelineAdapter:
    """Deterministic composition adapter for the minimal draft vertical slice."""

    def __init__(self, observability: observability_mod.InMemoryPipelineObservability | None = None) -> None:
        self._audio_worker = audio_mod.AudioWorker()
        self._transcription_worker = transcription_mod.TranscriptionWorker()
        self._quantization_worker = quantization_mod.QuantizationWorker()
        self._observability = observability or observability_mod.InMemoryPipelineObservability()

    def run(self, request: DraftPipelineRequest) -> DraftPipelineResult:
        trace_id = self._observability.start_trace("draft_pipeline", request.asset_id)
        try:
            with self._observability.timed_span(trace_id, "stage_a_audio"):
                audio_result = self._audio_worker.process(
                    audio_mod.AudioTaskRequest(
                        asset_id=request.asset_id,
                        source_uri=request.source_uri,
                        audio_format=request.audio_format,
                    )
                )

            with self._observability.timed_span(trace_id, "stage_c_tempo"):
                tempo_map_uri = self._build_tempo_map_uri(audio_result.waveform_uri)

            with self._observability.timed_span(trace_id, "stage_d_transcription"):
                transcription_result = self._transcription_worker.process(
                    transcription_mod.TranscriptionTaskRequest(
                        source_uri=audio_result.normalized_uri,
                        polyphonic=request.polyphonic,
                    )
                )

            with self._observability.timed_span(trace_id, "stage_e_quantization"):
                quantization_result = self._quantization_worker.process(
                    quantization_mod.QuantizationTaskRequest(
                        event_count=transcription_result.event_count,
                        snap_division=request.snap_division,
                    )
                )

            with self._observability.timed_span(trace_id, "stage_f_notation_export"):
                musicxml_uri = self._build_musicxml_uri(request.asset_id, quantization_result.quantized_event_count)
                midi_uri = self._build_midi_uri(request.asset_id, quantization_result.quantized_event_count)

            result = DraftPipelineResult(
                normalized_uri=audio_result.normalized_uri,
                waveform_uri=audio_result.waveform_uri,
                proxy_uri=audio_result.proxy_uri,
                tempo_map_uri=tempo_map_uri,
                musicxml_uri=musicxml_uri,
                midi_uri=midi_uri,
                event_count=transcription_result.event_count,
                quantized_event_count=quantization_result.quantized_event_count,
                confidence=transcription_result.confidence,
                had_tuplets=quantization_result.had_tuplets,
            )
            self._observability.log("info", "pipeline.run.success", trace_id, pipeline="draft_pipeline")
            self._observability.metric("pipeline_run_success_total", 1.0, pipeline="draft_pipeline")
            return result
        except Exception as exc:
            self._observability.log(
                "error",
                "pipeline.run.failure",
                trace_id,
                pipeline="draft_pipeline",
                error_type=type(exc).__name__,
            )
            self._observability.metric("pipeline_run_failures_total", 1.0, pipeline="draft_pipeline")
            raise

    @staticmethod
    def _build_tempo_map_uri(waveform_uri: str) -> str:
        if not waveform_uri.strip():
            raise ValueError("waveform_uri must be non-empty")
        return waveform_uri.replace("waveform://", "tempo-map://").replace(".json", ".tempo.json")

    @staticmethod
    def _build_musicxml_uri(asset_id: str, quantized_event_count: int) -> str:
        if not asset_id.strip():
            raise ValueError("asset_id must be non-empty")
        return f"musicxml://{asset_id}-q{quantized_event_count}.musicxml"

    @staticmethod
    def _build_midi_uri(asset_id: str, quantized_event_count: int) -> str:
        if not asset_id.strip():
            raise ValueError("asset_id must be non-empty")
        return f"midi://{asset_id}-q{quantized_event_count}.mid"
