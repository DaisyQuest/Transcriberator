"""DT-009/DT-022 editor state + performance-aware edit operations."""

from __future__ import annotations

from dataclasses import dataclass, replace
from time import perf_counter
from typing import Callable, Dict, List, Tuple


@dataclass(frozen=True)
class OperationMetric:
    """Captures a single measured editor operation runtime."""

    operation: str
    duration_ms: float


@dataclass(frozen=True)
class LatencyBudgetResult:
    """Summarizes pass/fail details for an editor latency budget evaluation."""

    operation: str
    threshold_ms: float
    observed_ms: float
    passed: bool


@dataclass(frozen=True)
class Note:
    id: str
    start: float
    duration: float
    pitch_midi: int


class EditorState:
    """Minimal in-memory editor model with undo/redo and checkpoints."""

    def __init__(self, *, clock: Callable[[], float] | None = None) -> None:
        self._notes: List[Note] = []
        self._undo: List[Tuple[Note, ...]] = []
        self._redo: List[Tuple[Note, ...]] = []
        self._clock = clock or perf_counter
        self._operation_metrics: List[OperationMetric] = []

    @property
    def notes(self) -> List[Note]:
        return list(self._notes)

    def _snapshot(self) -> Tuple[Note, ...]:
        return tuple(self._notes)

    def _record_history(self) -> None:
        self._undo.append(self._snapshot())
        self._redo.clear()

    def add_note(self, note: Note) -> None:
        self._validate_note(note)
        if any(existing.id == note.id for existing in self._notes):
            raise ValueError(f"Duplicate note id '{note.id}'")
        self._record_history()
        self._notes.append(note)

    def delete_note(self, *, note_id: str) -> None:
        for idx, note in enumerate(self._notes):
            if note.id == note_id:
                self._record_history()
                del self._notes[idx]
                return
        raise ValueError(f"Unknown note id '{note_id}'")

    def move_note(self, *, note_id: str, new_start: float) -> None:
        if new_start < 0:
            raise ValueError("new_start must be >= 0")
        for idx, note in enumerate(self._notes):
            if note.id == note_id:
                self._record_history()
                self._notes[idx] = replace(note, start=new_start)
                return
        raise ValueError(f"Unknown note id '{note_id}'")

    def stretch_note(self, *, note_id: str, new_duration: float) -> None:
        if new_duration <= 0:
            raise ValueError("new_duration must be > 0")
        for idx, note in enumerate(self._notes):
            if note.id == note_id:
                self._record_history()
                self._notes[idx] = replace(note, duration=new_duration)
                return
        raise ValueError(f"Unknown note id '{note_id}'")

    def quantize(self, *, grid: float) -> None:
        if grid <= 0:
            raise ValueError("grid must be > 0")
        self._record_history()
        self._notes = [replace(note, start=round(note.start / grid) * grid) for note in self._notes]

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self._snapshot())
        self._notes = list(self._undo.pop())
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self._snapshot())
        self._notes = list(self._redo.pop())
        return True

    def checkpoint(self) -> dict:
        return {
            "noteCount": len(self._notes),
            "undoDepth": len(self._undo),
            "redoDepth": len(self._redo),
            "metricsCaptured": len(self._operation_metrics),
        }

    def execute_timed_operation(self, *, operation: str, action: Callable[[], None]) -> OperationMetric:
        """Executes an editor action and records runtime in milliseconds."""

        if not operation.strip():
            raise ValueError("operation is required")

        started_at = self._clock()
        action()
        ended_at = self._clock()
        metric = OperationMetric(operation=operation, duration_ms=max(0.0, (ended_at - started_at) * 1000.0))
        self._operation_metrics.append(metric)
        return metric

    def summarize_latency(self, *, operation: str) -> Dict[str, float]:
        """Returns count/min/max/avg summary for measured operation timings."""

        matching = [metric.duration_ms for metric in self._operation_metrics if metric.operation == operation]
        if not matching:
            raise ValueError(f"No metrics for operation '{operation}'")
        return {
            "count": float(len(matching)),
            "minMs": min(matching),
            "maxMs": max(matching),
            "avgMs": sum(matching) / len(matching),
        }

    def evaluate_latency_budget(self, *, operation: str, threshold_ms: float) -> LatencyBudgetResult:
        """Checks if the max observed duration for an operation satisfies a threshold."""

        if threshold_ms <= 0:
            raise ValueError("threshold_ms must be > 0")
        summary = self.summarize_latency(operation=operation)
        observed_ms = summary["maxMs"]
        return LatencyBudgetResult(
            operation=operation,
            threshold_ms=threshold_ms,
            observed_ms=observed_ms,
            passed=observed_ms <= threshold_ms,
        )

    @staticmethod
    def _validate_note(note: Note) -> None:
        if note.start < 0:
            raise ValueError("note.start must be >= 0")
        if note.duration <= 0:
            raise ValueError("note.duration must be > 0")
        if not 0 <= note.pitch_midi <= 127:
            raise ValueError("note.pitch_midi must be in [0, 127]")
