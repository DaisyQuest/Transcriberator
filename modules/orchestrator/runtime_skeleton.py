"""DT-010 Orchestrator runtime skeleton.

This module intentionally provides a deterministic in-memory runtime that can be
swapped for queue- and persistence-backed implementations in later tasks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable


class JobMode(str, Enum):
    DRAFT = "draft"
    HQ = "hq"


class StageStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class StageDefinition:
    name: str
    required_for_draft: bool = True


@dataclass
class StageExecutionRecord:
    stage_name: str
    status: StageStatus
    attempts: int
    started_at_utc: str
    completed_at_utc: str
    detail: str = ""


@dataclass
class OrchestratorJobRequest:
    job_id: str
    mode: JobMode
    allow_hq_degradation: bool = True


@dataclass
class OrchestratorJobResult:
    job_id: str
    mode: JobMode
    run_id: str
    stage_records: list[StageExecutionRecord] = field(default_factory=list)

    @property
    def final_status(self) -> StageStatus:
        if any(record.status is StageStatus.FAILED for record in self.stage_records):
            return StageStatus.FAILED
        if all(record.status is StageStatus.SKIPPED for record in self.stage_records):
            return StageStatus.SKIPPED
        return StageStatus.SUCCEEDED


class OrchestratorRuntime:
    """Deterministic skeleton runtime for stage sequencing and fallback semantics."""

    STAGES: tuple[StageDefinition, ...] = (
        StageDefinition("decode_normalize"),
        StageDefinition("source_separation", required_for_draft=False),
        StageDefinition("transcription"),
        StageDefinition("quantization"),
        StageDefinition("engraving"),
    )

    def __init__(self, now_provider: Callable[[], datetime] | None = None):
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def run_job(self, request: OrchestratorJobRequest, fail_stages: set[str] | None = None) -> OrchestratorJobResult:
        fail_stages = fail_stages or set()
        result = OrchestratorJobResult(
            job_id=request.job_id,
            mode=request.mode,
            run_id=f"run-{request.job_id}",
        )

        for stage in self.STAGES:
            if request.mode is JobMode.DRAFT and not stage.required_for_draft:
                result.stage_records.append(
                    self._build_record(stage.name, StageStatus.SKIPPED, 0, "skipped for draft mode")
                )
                continue

            if stage.name in fail_stages:
                if stage.name == "source_separation" and request.allow_hq_degradation:
                    result.stage_records.append(
                        self._build_record(stage.name, StageStatus.SKIPPED, 1, "degraded to draft-compatible flow")
                    )
                    continue

                result.stage_records.append(
                    self._build_record(stage.name, StageStatus.FAILED, 1, "simulated stage failure")
                )
                break

            result.stage_records.append(self._build_record(stage.name, StageStatus.SUCCEEDED, 1, "completed"))

        return result

    def _build_record(self, stage_name: str, status: StageStatus, attempts: int, detail: str) -> StageExecutionRecord:
        started_at = self._now_provider().isoformat()
        completed_at = self._now_provider().isoformat()
        return StageExecutionRecord(
            stage_name=stage_name,
            status=status,
            attempts=attempts,
            started_at_utc=started_at,
            completed_at_utc=completed_at,
            detail=detail,
        )
