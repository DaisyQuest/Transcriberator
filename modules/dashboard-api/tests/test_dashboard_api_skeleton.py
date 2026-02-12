import importlib.util
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


MODULE_PATH = Path("modules/dashboard-api/src/dashboard_api_skeleton.py")
SPEC = importlib.util.spec_from_file_location("dashboard_api_skeleton", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

DashboardApiError = MODULE.DashboardApiError
DashboardApiSkeleton = MODULE.DashboardApiSkeleton


class TestDashboardApiSkeleton(unittest.TestCase):
    def setUp(self):
        self.api = DashboardApiSkeleton()
        self.project = self.api.create_project(name="Project A", owner_id="owner-1")

    def test_create_project_validates_input(self):
        with self.assertRaises(DashboardApiError):
            self.api.create_project(name="   ", owner_id="owner")
        with self.assertRaises(DashboardApiError):
            self.api.create_project(name="Valid", owner_id="  ")

    def test_auth_issue_require_and_authorized_creation_paths(self):
        with self.assertRaisesRegex(DashboardApiError, "Owner id must be non-empty"):
            self.api.issue_access_token(owner_id="   ")

        session = self.api.issue_access_token(owner_id="owner-1")
        self.assertTrue(session.token.startswith("tok_"))

        with self.assertRaisesRegex(DashboardApiError, "Access token is required"):
            self.api.require_auth(token="   ")
        with self.assertRaisesRegex(DashboardApiError, "Access token is invalid"):
            self.api.require_auth(token="tok_missing")
        with self.assertRaisesRegex(DashboardApiError, "cannot access this owner's resources"):
            self.api.require_auth(token=session.token, owner_id="owner-2")

        authed = self.api.require_auth(token=session.token, owner_id="owner-1")
        self.assertEqual(authed.owner_id, "owner-1")

        p2 = self.api.create_project_authorized(token=session.token, owner_id="owner-1", name="Authorized")
        self.assertEqual(p2.owner_id, "owner-1")

    def test_list_projects_supports_optional_owner_filter(self):
        p2 = self.api.create_project(name="Project B", owner_id="owner-2")
        all_projects = self.api.list_projects()
        self.assertEqual({p.id for p in all_projects}, {self.project.id, p2.id})

        owner_projects = self.api.list_projects(owner_id="owner-1")
        self.assertEqual([p.id for p in owner_projects], [self.project.id])

    def test_create_job_validates_project_and_mode(self):
        with self.assertRaises(DashboardApiError):
            self.api.create_job(project_id="missing", mode="draft")
        with self.assertRaises(DashboardApiError):
            self.api.create_job(project_id=self.project.id, mode="speedrun")

    def test_get_retry_cancel_job_paths(self):
        job = self.api.create_job(project_id=self.project.id, mode="draft")
        self.assertEqual(self.api.get_job(job_id=job.id).id, job.id)

        with self.assertRaises(DashboardApiError):
            self.api.retry_job(job_id=job.id)

        cancelled = self.api.cancel_job(job_id=job.id)
        self.assertEqual(cancelled.status, "cancelled")

        retried = self.api.retry_job(job_id=job.id)
        self.assertEqual(retried.status, "queued")
        self.assertEqual(retried.attempt, 2)

        job.status = "succeeded"
        with self.assertRaises(DashboardApiError):
            self.api.cancel_job(job_id=job.id)

    def test_get_job_and_error_to_response(self):
        with self.assertRaises(DashboardApiError) as ctx:
            self.api.get_job(job_id="missing")
        payload = ctx.exception.to_response(trace_id="trace-123")
        self.assertEqual(payload["error"]["traceId"], "trace-123")
        self.assertEqual(payload["error"]["code"], "job_not_found")

    def test_artifact_download_link_validation_and_signature(self):
        with self.assertRaises(DashboardApiError):
            self.api.artifact_download_link(artifact_id=" ", ttl_seconds=60)
        with self.assertRaises(DashboardApiError):
            self.api.artifact_download_link(artifact_id="file-1", ttl_seconds=0)

        signed = self.api.artifact_download_link_signed(artifact_id="file-1", ttl_seconds=120)
        self.assertIn("https://example.invalid/artifacts/file-1?expires=", signed.url)
        self.assertIn("&sig=", signed.url)
        self.assertEqual(len(signed.signature), 64)

        unsigned_compat = self.api.artifact_download_link(artifact_id="file-1", ttl_seconds=120)
        self.assertIn("&sig=", unsigned_compat)

    def test_retention_configuration_and_disposition_paths(self):
        with self.assertRaisesRegex(DashboardApiError, "max_age_days must be > 0"):
            self.api.configure_retention_policy(max_age_days=0, hard_delete=False)

        policy = self.api.configure_retention_policy(max_age_days=5, hard_delete=False)
        self.assertEqual(policy.max_age_days, 5)
        self.assertFalse(policy.hard_delete)
        self.assertEqual(self.api.retention_policy.max_age_days, 5)

        now = datetime(2026, 1, 10, tzinfo=timezone.utc)
        recent = (now - timedelta(days=2)).isoformat()
        stale = (now - timedelta(days=10)).isoformat()

        self.assertTrue(self.api.should_retain_artifact(created_at_iso=recent, now=now))
        self.assertFalse(self.api.should_retain_artifact(created_at_iso=stale, now=now))
        self.assertEqual(self.api.retention_disposition(created_at_iso=recent, now=now), "retain")
        self.assertEqual(self.api.retention_disposition(created_at_iso=stale, now=now), "archive")

        self.api.configure_retention_policy(max_age_days=5, hard_delete=True)
        self.assertEqual(self.api.retention_disposition(created_at_iso=stale, now=now), "delete")

    def test_retention_timestamp_and_artifact_record_validation(self):
        with self.assertRaisesRegex(DashboardApiError, "Timestamp must be valid ISO format"):
            self.api.should_retain_artifact(created_at_iso="not-a-timestamp")

        self.api.configure_retention_policy(max_age_days=2, hard_delete=False)
        now = datetime(2026, 1, 5, tzinfo=timezone.utc)
        due = self.api.artifacts_due_for_retention(
            artifacts=[
                {"id": " a2 ", "createdAt": (now - timedelta(days=3)).isoformat()},
                {"id": "a1", "createdAt": (now - timedelta(days=10)).isoformat()},
                {"id": "a3", "createdAt": (now - timedelta(days=1)).isoformat()},
            ],
            now=now,
        )
        self.assertEqual(due, ["a1", "a2"])

        with self.assertRaisesRegex(DashboardApiError, "Artifact record must include id/createdAt"):
            self.api.artifacts_due_for_retention(artifacts=[{"id": "a4"}], now=now)


if __name__ == "__main__":
    unittest.main()
