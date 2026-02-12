"""DT-014 Worker-quantization skeleton."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QuantizationTaskRequest:
    event_count: int
    snap_division: int = 16


@dataclass(frozen=True)
class QuantizationTaskResult:
    quantized_event_count: int
    had_tuplets: bool
    deterministic: bool


class QuantizationWorker:
    def process(self, request: QuantizationTaskRequest) -> QuantizationTaskResult:
        if request.event_count < 0:
            raise ValueError("event_count must be >= 0")
        if request.snap_division not in {4, 8, 16, 32}:
            raise ValueError("snap_division must be one of 4, 8, 16, 32")

        had_tuplets = request.snap_division == 32 and request.event_count > 0
        return QuantizationTaskResult(
            quantized_event_count=request.event_count,
            had_tuplets=had_tuplets,
            deterministic=True,
        )
