import importlib.util
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


api_mod = load_module("dashboard_api_skeleton_dt023_test", "modules/dashboard-api/src/dashboard_api_skeleton.py")
adapter_mod = load_module("dashboard_api_adapter_dt023_test", "modules/dashboard-api/revision_export_adapter.py")


class TestSecurityAndPrivacyIntegration(unittest.TestCase):
    def setUp(self):
        self.api = api_mod.DashboardApiSkeleton()
        self.adapter = adapter_mod.DashboardRevisionExportAdapter(service=self.api)

    def test_authorized_project_and_signed_export_links(self):
        session = self.api.issue_access_token(owner_id="owner-secure")
        project = self.api.create_project_authorized(token=session.token, owner_id="owner-secure", name="Secure Project")

        links = self.adapter.build_download_links(
            revision_id="rev-secure",
            export_manifest={"midi": "s3://midi", "musicxml": "s3://xml"},
            ttl_seconds=60,
        )

        self.assertEqual(project.owner_id, "owner-secure")
        self.assertEqual(sorted(links.links.keys()), ["midi", "musicxml"])
        for link in links.links.values():
            with self.subTest(link=link):
                self.assertIn("&sig=", link)
                self.assertIn("expires=", link)

    def test_retention_due_artifacts_archive_and_delete_modes(self):
        now = datetime(2026, 2, 1, tzinfo=timezone.utc)
        self.api.configure_retention_policy(max_age_days=7, hard_delete=False)

        due = self.api.artifacts_due_for_retention(
            artifacts=[
                {"id": "artifact-z", "createdAt": (now - timedelta(days=8)).isoformat()},
                {"id": "artifact-a", "createdAt": (now - timedelta(days=12)).isoformat()},
                {"id": "artifact-b", "createdAt": (now - timedelta(days=2)).isoformat()},
            ],
            now=now,
        )
        self.assertEqual(due, ["artifact-a", "artifact-z"])
        self.assertEqual(
            self.api.retention_disposition(created_at_iso=(now - timedelta(days=20)).isoformat(), now=now),
            "archive",
        )

        self.api.configure_retention_policy(max_age_days=7, hard_delete=True)
        self.assertEqual(
            self.api.retention_disposition(created_at_iso=(now - timedelta(days=20)).isoformat(), now=now),
            "delete",
        )


if __name__ == "__main__":
    unittest.main()
