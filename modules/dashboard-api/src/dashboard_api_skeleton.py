"""DT-007 Dashboard API skeleton.

In-memory, deterministic skeleton that models typed request handling and
observable API responses without external infrastructure dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
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


@dataclass(frozen=True)
class AuthSession:
    token: str
    owner_id: str
    issued_at: str


@dataclass(frozen=True)
class RetentionPolicy:
    max_age_days: int
    hard_delete: bool


@dataclass(frozen=True)
class SignedArtifactUrl:
    url: str
    expires_at: str
    signature: str


class DashboardApiSkeleton:
    """Minimal replaceable API service facade for dashboard module skeleton."""

    def __init__(self) -> None:
        self._projects: Dict[str, ProjectRecord] = {}
        self._jobs: Dict[str, JobRecord] = {}
        self._auth_sessions: Dict[str, AuthSession] = {}
        self._retention_policy = RetentionPolicy(max_age_days=30, hard_delete=False)
        self._signing_secret = "dev-signing-secret"

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

    def issue_access_token(self, *, owner_id: str) -> AuthSession:
        owner_id = owner_id.strip()
        if not owner_id:
            raise DashboardApiError(code="invalid_owner", message="Owner id must be non-empty.")

        token = f"tok_{uuid.uuid4().hex}"
        session = AuthSession(token=token, owner_id=owner_id, issued_at=self._now_iso())
        self._auth_sessions[token] = session
        return session

    def require_auth(self, *, token: str, owner_id: str | None = None) -> AuthSession:
        token = token.strip()
        if not token:
            raise DashboardApiError(code="unauthorized", message="Access token is required.")

        session = self._auth_sessions.get(token)
        if session is None:
            raise DashboardApiError(code="unauthorized", message="Access token is invalid.")

        if owner_id is not None and session.owner_id != owner_id:
            raise DashboardApiError(code="forbidden", message="Access token cannot access this owner's resources.")
        return session

    def create_project_authorized(self, *, token: str, owner_id: str, name: str) -> ProjectRecord:
        self.require_auth(token=token, owner_id=owner_id)
        return self.create_project(name=name, owner_id=owner_id)

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
        signed = self.artifact_download_link_signed(artifact_id=artifact_id, ttl_seconds=ttl_seconds)
        return signed.url

    def artifact_download_link_signed(self, *, artifact_id: str, ttl_seconds: int) -> SignedArtifactUrl:
        artifact_id = artifact_id.strip()
        if not artifact_id:
            raise DashboardApiError(code="invalid_artifact", message="Artifact id is required.")
        if ttl_seconds <= 0:
            raise DashboardApiError(code="invalid_ttl", message="TTL must be greater than zero.")

        expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=ttl_seconds)
        signature = self._sign_artifact(artifact_id=artifact_id, expires_at=expires_at.isoformat())
        url = (
            f"https://example.invalid/artifacts/{artifact_id}"
            f"?expires={expires_at.isoformat()}&sig={signature}"
        )
        return SignedArtifactUrl(url=url, expires_at=expires_at.isoformat(), signature=signature)

    def configure_retention_policy(self, *, max_age_days: int, hard_delete: bool) -> RetentionPolicy:
        if max_age_days <= 0:
            raise DashboardApiError(code="invalid_retention", message="Retention max_age_days must be > 0.")
        self._retention_policy = RetentionPolicy(max_age_days=max_age_days, hard_delete=hard_delete)
        return self._retention_policy

    @property
    def retention_policy(self) -> RetentionPolicy:
        return self._retention_policy

    def should_retain_artifact(self, *, created_at_iso: str, now: datetime | None = None) -> bool:
        created_at = self._parse_iso_datetime(created_at_iso)
        reference = now or datetime.now(tz=timezone.utc)
        age = reference - created_at
        return age <= timedelta(days=self._retention_policy.max_age_days)

    def retention_disposition(self, *, created_at_iso: str, now: datetime | None = None) -> str:
        if self.should_retain_artifact(created_at_iso=created_at_iso, now=now):
            return "retain"
        return "delete" if self._retention_policy.hard_delete else "archive"

    def artifacts_due_for_retention(self, *, artifacts: List[dict], now: datetime | None = None) -> List[str]:
        due: List[str] = []
        for artifact in artifacts:
            artifact_id = str(artifact.get("id", "")).strip()
            created_at = artifact.get("createdAt")
            if not artifact_id or not isinstance(created_at, str):
                raise DashboardApiError(code="invalid_artifact_record", message="Artifact record must include id/createdAt.")
            if not self.should_retain_artifact(created_at_iso=created_at, now=now):
                due.append(artifact_id)
        return sorted(due)

    def _sign_artifact(self, *, artifact_id: str, expires_at: str) -> str:
        payload = f"{artifact_id}:{expires_at}".encode("utf-8")
        digest = hmac.new(self._signing_secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        return digest

    @staticmethod
    def _parse_iso_datetime(value: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise DashboardApiError(code="invalid_timestamp", message="Timestamp must be valid ISO format.") from exc

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
