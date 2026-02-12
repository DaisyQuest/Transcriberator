import importlib.util
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


api_mod = load_module("dashboard_api_security_unit", "modules/dashboard-api/src/dashboard_api_skeleton.py")
adapter_mod = load_module("dashboard_api_adapter_security_unit", "modules/dashboard-api/revision_export_adapter.py")


class TestDashboardApiSecurityPrivacyUnit(unittest.TestCase):
    def setUp(self):
        self.api = api_mod.DashboardApiSkeleton()

    def test_auth_and_authorized_project_paths(self):
        session = self.api.issue_access_token(owner_id="owner-u")
        self.assertEqual(self.api.require_auth(token=session.token).owner_id, "owner-u")

        with self.assertRaisesRegex(api_mod.DashboardApiError, "Access token is required"):
            self.api.require_auth(token=" ")
        with self.assertRaisesRegex(api_mod.DashboardApiError, "Access token is invalid"):
            self.api.require_auth(token="tok_bad")
        with self.assertRaisesRegex(api_mod.DashboardApiError, "cannot access this owner's resources"):
            self.api.require_auth(token=session.token, owner_id="other")

        project = self.api.create_project_authorized(token=session.token, owner_id="owner-u", name="Secure")
        self.assertEqual(project.owner_id, "owner-u")

    def test_signed_link_generation_and_signature(self):
        signed = self.api.artifact_download_link_signed(artifact_id="artifact-1", ttl_seconds=30)
        expected_sig = self.api._sign_artifact(artifact_id="artifact-1", expires_at=signed.expires_at)
        self.assertEqual(signed.signature, expected_sig)
        self.assertIn("&sig=", signed.url)

    def test_retention_policy_and_naive_datetime_handling(self):
        self.api.configure_retention_policy(max_age_days=1, hard_delete=False)
        self.assertEqual(self.api.retention_policy.max_age_days, 1)

        now = datetime(2026, 1, 2, tzinfo=timezone.utc)
        naive_recent = (now - timedelta(hours=12)).replace(tzinfo=None).isoformat()
        self.assertTrue(self.api.should_retain_artifact(created_at_iso=naive_recent, now=now))

        stale = (now - timedelta(days=5)).isoformat()
        self.assertEqual(self.api.retention_disposition(created_at_iso=stale, now=now), "archive")

        self.api.configure_retention_policy(max_age_days=1, hard_delete=True)
        self.assertEqual(self.api.retention_disposition(created_at_iso=stale, now=now), "delete")

    def test_artifacts_due_default_now_and_validation(self):
        self.api.configure_retention_policy(max_age_days=365, hard_delete=False)
        due = self.api.artifacts_due_for_retention(
            artifacts=[{"id": "a-1", "createdAt": "2000-01-01T00:00:00+00:00"}],
        )
        self.assertEqual(due, ["a-1"])

        with self.assertRaisesRegex(api_mod.DashboardApiError, "Artifact record must include id/createdAt"):
            self.api.artifacts_due_for_retention(artifacts=[{"id": "a-2", "createdAt": 5}])


class TestRevisionExportAdapterUnit(unittest.TestCase):
    def test_default_service_property_and_build_links(self):
        adapter = adapter_mod.DashboardRevisionExportAdapter()
        self.assertTrue(hasattr(adapter.service, "artifact_download_link"))

        built = adapter.build_download_links(
            revision_id="rev-1",
            export_manifest={"pdf": "uri", "midi": "uri"},
            ttl_seconds=5,
        )
        self.assertEqual(sorted(built.links.keys()), ["midi", "pdf"])

    def test_load_module_runtime_error_branch(self):
        with mock.patch.object(adapter_mod.importlib.util, "spec_from_file_location", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "Unable to load module"):
                adapter_mod._load_module("bad_module", "missing.py")


if __name__ == "__main__":
    unittest.main()
