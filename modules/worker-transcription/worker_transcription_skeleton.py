"""DT-013 Worker-transcription skeleton."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptionTaskRequest:
    source_uri: str
    polyphonic: bool
    model_version: str = "skeleton-v1"


@dataclass(frozen=True)
class TranscriptionTaskResult:
    event_count: int
    confidence: float
    model_version: str


class TranscriptionWorker:
    def process(self, request: TranscriptionTaskRequest) -> TranscriptionTaskResult:
        if not request.model_version:
            raise ValueError("model_version is required")

        event_count = 32 if request.polyphonic else 12
        confidence = 0.82 if request.polyphonic else 0.91
        return TranscriptionTaskResult(
            event_count=event_count,
            confidence=confidence,
            model_version=request.model_version,
        )
