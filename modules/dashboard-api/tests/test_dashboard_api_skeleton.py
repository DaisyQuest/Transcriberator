import importlib.util
import sys
import unittest
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

    def test_artifact_download_link_validation(self):
        with self.assertRaises(DashboardApiError):
            self.api.artifact_download_link(artifact_id=" ", ttl_seconds=60)
        with self.assertRaises(DashboardApiError):
            self.api.artifact_download_link(artifact_id="file-1", ttl_seconds=0)

        url = self.api.artifact_download_link(artifact_id="file-1", ttl_seconds=120)
        self.assertIn("https://example.invalid/artifacts/file-1?expires=", url)


if __name__ == "__main__":
    unittest.main()
