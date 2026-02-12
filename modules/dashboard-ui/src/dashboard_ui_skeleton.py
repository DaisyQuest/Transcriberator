"""DT-008 Dashboard UI skeleton view-model helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List


@dataclass(frozen=True)
class JobRow:
    id: str
    project_name: str
    status: str
    can_retry: bool
    can_cancel: bool


TERMINAL = {"succeeded", "failed", "cancelled"}
RETRYABLE = {"failed", "cancelled"}


def build_job_row(job: dict, *, project_name: str) -> JobRow:
    status = job["status"]
    return JobRow(
        id=job["id"],
        project_name=project_name,
        status=status,
        can_retry=status in RETRYABLE,
        can_cancel=status not in TERMINAL,
    )


def filter_rows_by_status(rows: Iterable[JobRow], *, status_filter: str) -> List[JobRow]:
    normalized = status_filter.strip().lower()
    rows = list(rows)
    if normalized in {"", "all"}:
        return rows
    return [row for row in rows if row.status.lower() == normalized]


def summarize_dashboard_health(*, poll_interval_ms: int, pending_jobs: int, failed_jobs: int) -> dict:
    if poll_interval_ms <= 0:
        raise ValueError("poll_interval_ms must be positive")
    if pending_jobs < 0 or failed_jobs < 0:
        raise ValueError("job counters cannot be negative")

    load_score = pending_jobs + (failed_jobs * 2)
    if load_score <= 3:
        level = "healthy"
    elif load_score <= 8:
        level = "watch"
    else:
        level = "degraded"

    return {
        "statusLevel": level,
        "pollIntervalMs": poll_interval_ms,
        "pendingJobs": pending_jobs,
        "failedJobs": failed_jobs,
    }
