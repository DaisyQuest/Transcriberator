"""DT-020 module-local observability primitives for integration adapters.

The goal of this module is to provide deterministic, dependency-free
instrumentation helpers that can be swapped with production telemetry sinks
without changing pipeline adapter behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import itertools
from time import perf_counter
from typing import Any


@dataclass(frozen=True)
class MetricPoint:
    name: str
    value: float
    tags: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SpanRecord:
    trace_id: str
    span_name: str
    status: str
    duration_ms: float
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class LogRecord:
    level: str
    message: str
    trace_id: str
    context: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ObservabilitySnapshot:
    metrics: tuple[MetricPoint, ...]
    spans: tuple[SpanRecord, ...]
    logs: tuple[LogRecord, ...]


class InMemoryPipelineObservability:
    """Collects metrics/spans/logs in-memory for deterministic testing."""

    def __init__(self) -> None:
        self._trace_counter = itertools.count(1)
        self._metrics: list[MetricPoint] = []
        self._spans: list[SpanRecord] = []
        self._logs: list[LogRecord] = []

    def start_trace(self, pipeline_name: str, request_id: str) -> str:
        trace_id = f"trace-{next(self._trace_counter)}"
        self.log(
            "info",
            "pipeline.run.start",
            trace_id,
            pipeline=pipeline_name,
            request_id=request_id,
        )
        self.metric("pipeline_runs_total", 1.0, pipeline=pipeline_name)
        return trace_id

    def metric(self, name: str, value: float, **tags: str) -> None:
        self._metrics.append(MetricPoint(name=name, value=value, tags=tags))

    def log(self, level: str, message: str, trace_id: str, **context: str) -> None:
        self._logs.append(LogRecord(level=level, message=message, trace_id=trace_id, context=context))

    def record_span(self, trace_id: str, span_name: str, status: str, duration_ms: float, **attributes: str) -> None:
        self._spans.append(
            SpanRecord(
                trace_id=trace_id,
                span_name=span_name,
                status=status,
                duration_ms=duration_ms,
                attributes=attributes,
            )
        )

    def timed_span(self, trace_id: str, span_name: str):
        return _TimedSpanContext(self, trace_id, span_name)

    def snapshot(self) -> ObservabilitySnapshot:
        return ObservabilitySnapshot(metrics=tuple(self._metrics), spans=tuple(self._spans), logs=tuple(self._logs))


class _TimedSpanContext:
    def __init__(self, sink: InMemoryPipelineObservability, trace_id: str, span_name: str) -> None:
        self._sink = sink
        self._trace_id = trace_id
        self._span_name = span_name
        self._started_at = 0.0

    def __enter__(self) -> "_TimedSpanContext":
        self._started_at = perf_counter()
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, _tb: Any) -> bool:
        elapsed_ms = (perf_counter() - self._started_at) * 1000
        status = "error" if exc else "ok"
        self._sink.record_span(self._trace_id, self._span_name, status, elapsed_ms)
        if exc is not None:
            self._sink.metric("pipeline_stage_failures_total", 1.0, stage=self._span_name)
        else:
            self._sink.metric("pipeline_stage_success_total", 1.0, stage=self._span_name)
        return False
