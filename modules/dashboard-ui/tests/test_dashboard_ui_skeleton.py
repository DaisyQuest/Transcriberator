import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path("modules/dashboard-ui/src/dashboard_ui_skeleton.py")
SPEC = importlib.util.spec_from_file_location("dashboard_ui_skeleton", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class TestDashboardUiSkeleton(unittest.TestCase):
    def test_build_job_row_sets_action_flags(self):
        running = MODULE.build_job_row({"id": "j1", "status": "running"}, project_name="P")
        self.assertFalse(running.can_retry)
        self.assertTrue(running.can_cancel)

        failed = MODULE.build_job_row({"id": "j2", "status": "failed"}, project_name="P")
        self.assertTrue(failed.can_retry)
        self.assertFalse(failed.can_cancel)

    def test_filter_rows_by_status(self):
        rows = [
            MODULE.JobRow(id="1", project_name="P", status="queued", can_retry=False, can_cancel=True),
            MODULE.JobRow(id="2", project_name="P", status="failed", can_retry=True, can_cancel=False),
        ]
        self.assertEqual(len(MODULE.filter_rows_by_status(rows, status_filter="all")), 2)
        self.assertEqual(len(MODULE.filter_rows_by_status(rows, status_filter="  ")), 2)
        filtered = MODULE.filter_rows_by_status(rows, status_filter="FAILED")
        self.assertEqual([r.id for r in filtered], ["2"])

    def test_summarize_dashboard_health_validation_and_levels(self):
        with self.assertRaises(ValueError):
            MODULE.summarize_dashboard_health(poll_interval_ms=0, pending_jobs=0, failed_jobs=0)
        with self.assertRaises(ValueError):
            MODULE.summarize_dashboard_health(poll_interval_ms=1000, pending_jobs=-1, failed_jobs=0)

        healthy = MODULE.summarize_dashboard_health(poll_interval_ms=1000, pending_jobs=1, failed_jobs=1)
        watch = MODULE.summarize_dashboard_health(poll_interval_ms=1000, pending_jobs=4, failed_jobs=1)
        degraded = MODULE.summarize_dashboard_health(poll_interval_ms=1000, pending_jobs=5, failed_jobs=2)

        self.assertEqual(healthy["statusLevel"], "healthy")
        self.assertEqual(watch["statusLevel"], "watch")
        self.assertEqual(degraded["statusLevel"], "degraded")


if __name__ == "__main__":
    unittest.main()
