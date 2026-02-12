"""DT-007 Dashboard API skeleton.

In-memory, deterministic skeleton that models typed request handling and
observable API responses without external infrastructure dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List
import uuid


ALLOWED_MODES = {"draft", "hq"}
TERMINAL_JOB_STATUSES = {"succeeded", "failed", "cancelled"}


class DashboardApiError(ValueError):
    """Typed, actionable API error."""

    def __init__(self, *, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def to_response(self, trace_id: str) -> dict:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "traceId": trace_id,
            }
        }


@dataclass(frozen=True)
class ProjectRecord:
    id: str
    name: str
    owner_id: str
    created_at: str


@dataclass
class JobRecord:
    id: str
    project_id: str
    mode: str
    status: str
    attempt: int
    updated_at: str


class DashboardApiSkeleton:
    """Minimal replaceable API service facade for dashboard module skeleton."""

    def __init__(self) -> None:
        self._projects: Dict[str, ProjectRecord] = {}
        self._jobs: Dict[str, JobRecord] = {}

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(tz=timezone.utc).isoformat()

    def create_project(self, *, name: str, owner_id: str) -> ProjectRecord:
        if not name.strip():
            raise DashboardApiError(code="invalid_project_name", message="Project name must be non-empty.")
        if not owner_id.strip():
            raise DashboardApiError(code="invalid_owner", message="Owner id must be non-empty.")

        project = ProjectRecord(
            id=f"proj_{uuid.uuid4().hex[:10]}",
            name=name.strip(),
            owner_id=owner_id.strip(),
            created_at=self._now_iso(),
        )
        self._projects[project.id] = project
        return project

    def list_projects(self, *, owner_id: str | None = None) -> List[ProjectRecord]:
        projects = list(self._projects.values())
        if owner_id is None:
            return sorted(projects, key=lambda p: p.created_at)
        return sorted((p for p in projects if p.owner_id == owner_id), key=lambda p: p.created_at)

    def create_job(self, *, project_id: str, mode: str) -> JobRecord:
        if project_id not in self._projects:
            raise DashboardApiError(code="project_not_found", message=f"Unknown project: {project_id}")
        normalized_mode = mode.strip().lower()
        if normalized_mode not in ALLOWED_MODES:
            raise DashboardApiError(code="invalid_mode", message=f"Mode must be one of {sorted(ALLOWED_MODES)}")

        job = JobRecord(
            id=f"job_{uuid.uuid4().hex[:10]}",
            project_id=project_id,
            mode=normalized_mode,
            status="queued",
            attempt=1,
            updated_at=self._now_iso(),
        )
        self._jobs[job.id] = job
        return job

    def get_job(self, *, job_id: str) -> JobRecord:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise DashboardApiError(code="job_not_found", message=f"Unknown job: {job_id}") from exc

    def retry_job(self, *, job_id: str) -> JobRecord:
        job = self.get_job(job_id=job_id)
        if job.status not in TERMINAL_JOB_STATUSES:
            raise DashboardApiError(
                code="retry_not_allowed",
                message=f"Job in status '{job.status}' cannot be retried until it reaches a terminal state.",
            )
        job.status = "queued"
        job.attempt += 1
        job.updated_at = self._now_iso()
        return job

    def cancel_job(self, *, job_id: str) -> JobRecord:
        job = self.get_job(job_id=job_id)
        if job.status in {"succeeded", "failed", "cancelled"}:
            raise DashboardApiError(
                code="cancel_not_allowed",
                message=f"Job in status '{job.status}' cannot be cancelled.",
            )
        job.status = "cancelled"
        job.updated_at = self._now_iso()
        return job

    def artifact_download_link(self, *, artifact_id: str, ttl_seconds: int) -> str:
        artifact_id = artifact_id.strip()
        if not artifact_id:
            raise DashboardApiError(code="invalid_artifact", message="Artifact id is required.")
        if ttl_seconds <= 0:
            raise DashboardApiError(code="invalid_ttl", message="TTL must be greater than zero.")

        expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=ttl_seconds)
        return f"https://example.invalid/artifacts/{artifact_id}?expires={expires_at.isoformat()}"
