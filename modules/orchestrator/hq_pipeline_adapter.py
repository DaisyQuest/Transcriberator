"""DT-018 HQ pipeline integration adapter.

Builds on the draft adapter by optionally invoking source separation and
falling back to draft-compatible behavior when degradation is permitted.
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


draft_adapter_mod = _load_module("draft_pipeline_adapter_dt018", "modules/orchestrator/draft_pipeline_adapter.py")
separation_mod = _load_module("worker_separation_skeleton_dt018", "modules/worker-separation/worker_separation_skeleton.py")
observability_mod = _load_module("orchestrator_observability_dt020_hq", "modules/orchestrator/observability.py")


@dataclass(frozen=True)
class HQPipelineRequest:
    asset_id: str
    source_uri: str
    audio_format: str
    polyphonic: bool = True
    snap_division: int = 16
    allow_hq_degradation: bool = True
    simulate_separation_timeout: bool = False


@dataclass(frozen=True)
class HQPipelineResult:
    draft_result: draft_adapter_mod.DraftPipelineResult
    stem_uris: dict[str, str]
    separation_quality_score: float
    degraded_to_draft: bool


class HQPipelineAdapter:
    def __init__(self, observability: observability_mod.InMemoryPipelineObservability | None = None) -> None:
        self._observability = observability or observability_mod.InMemoryPipelineObservability()
        self._draft_adapter = draft_adapter_mod.DraftPipelineAdapter(observability=self._observability)
        self._separation_worker = separation_mod.SeparationWorker()

    def run(self, request: HQPipelineRequest) -> HQPipelineResult:
        trace_id = self._observability.start_trace("hq_pipeline", request.asset_id)
        try:
            with self._observability.timed_span(trace_id, "stage_b_separation"):
                separation_result = self._separation_worker.process(
                    separation_mod.SeparationTaskRequest(
                        asset_id=request.asset_id,
                        normalized_uri=f"normalized://{request.asset_id}",
                        simulate_timeout=request.simulate_separation_timeout,
                    )
                )

            if separation_result.degraded and not request.allow_hq_degradation:
                raise RuntimeError("HQ separation failed and degradation is disabled")

            if separation_result.degraded:
                self._observability.metric("hq_pipeline_degraded_total", 1.0, pipeline="hq_pipeline")
                self._observability.log("warning", "pipeline.hq.degraded", trace_id, pipeline="hq_pipeline")

            draft_result = self._draft_adapter.run(
                draft_adapter_mod.DraftPipelineRequest(
                    asset_id=request.asset_id,
                    source_uri=request.source_uri,
                    audio_format=request.audio_format,
                    polyphonic=request.polyphonic,
                    snap_division=request.snap_division,
                )
            )

            result = HQPipelineResult(
                draft_result=draft_result,
                stem_uris=separation_result.stem_uris,
                separation_quality_score=separation_result.quality_score,
                degraded_to_draft=separation_result.degraded,
            )
            self._observability.log("info", "pipeline.run.success", trace_id, pipeline="hq_pipeline")
            self._observability.metric("pipeline_run_success_total", 1.0, pipeline="hq_pipeline")
            return result
        except Exception as exc:
            self._observability.log(
                "error",
                "pipeline.run.failure",
                trace_id,
                pipeline="hq_pipeline",
                error_type=type(exc).__name__,
            )
            self._observability.metric("pipeline_run_failures_total", 1.0, pipeline="hq_pipeline")
            raise
