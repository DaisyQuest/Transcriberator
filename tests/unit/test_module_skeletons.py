import importlib.util
import sys
import unittest
from pathlib import Path


def load_module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, Path(path))
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


api = load_module("dashboard_api_skeleton", "modules/dashboard-api/src/dashboard_api_skeleton.py")
ui = load_module("dashboard_ui_skeleton", "modules/dashboard-ui/src/dashboard_ui_skeleton.py")
editor = load_module("editor_app_skeleton", "modules/editor-app/src/editor_app_skeleton.py")


class TestDashboardApiSkeleton(unittest.TestCase):
    def setUp(self):
        self.service = api.DashboardApiSkeleton()
        self.project = self.service.create_project(name="Project A", owner_id="owner-1")

    def test_api_paths(self):
        with self.assertRaises(api.DashboardApiError):
            self.service.create_project(name="", owner_id="owner")
        with self.assertRaises(api.DashboardApiError):
            self.service.create_project(name="ok", owner_id="")

        with self.assertRaises(api.DashboardApiError):
            self.service.create_job(project_id="missing", mode="draft")
        with self.assertRaises(api.DashboardApiError):
            self.service.create_job(project_id=self.project.id, mode="invalid")

        job = self.service.create_job(project_id=self.project.id, mode="draft")
        self.assertEqual(self.service.get_job(job_id=job.id).id, job.id)
        with self.assertRaises(api.DashboardApiError):
            self.service.retry_job(job_id=job.id)

        self.service.cancel_job(job_id=job.id)
        self.service.retry_job(job_id=job.id)
        job.status = "succeeded"
        with self.assertRaises(api.DashboardApiError):
            self.service.cancel_job(job_id=job.id)

        with self.assertRaises(api.DashboardApiError) as ctx:
            self.service.get_job(job_id="404")
        self.assertEqual(ctx.exception.to_response(trace_id="t")["error"]["traceId"], "t")

        with self.assertRaises(api.DashboardApiError):
            self.service.artifact_download_link(artifact_id="", ttl_seconds=1)
        with self.assertRaises(api.DashboardApiError):
            self.service.artifact_download_link(artifact_id="a", ttl_seconds=0)
        self.assertIn("artifacts/a", self.service.artifact_download_link(artifact_id="a", ttl_seconds=5))

        p2 = self.service.create_project(name="Project B", owner_id="owner-2")
        self.assertEqual(len(self.service.list_projects()), 2)
        self.assertEqual([p.id for p in self.service.list_projects(owner_id="owner-1")], [self.project.id])
        self.assertIn(p2.id, {p.id for p in self.service.list_projects()})


class TestDashboardUiSkeleton(unittest.TestCase):
    def test_ui_helpers(self):
        row_running = ui.build_job_row({"id": "j1", "status": "running"}, project_name="P")
        self.assertTrue(row_running.can_cancel)
        self.assertFalse(row_running.can_retry)

        row_failed = ui.build_job_row({"id": "j2", "status": "failed"}, project_name="P")
        self.assertFalse(row_failed.can_cancel)
        self.assertTrue(row_failed.can_retry)

        rows = [row_running, row_failed]
        self.assertEqual(len(ui.filter_rows_by_status(rows, status_filter="")), 2)
        self.assertEqual(len(ui.filter_rows_by_status(rows, status_filter="all")), 2)
        self.assertEqual([r.id for r in ui.filter_rows_by_status(rows, status_filter="FAILED")], ["j2"])

        with self.assertRaises(ValueError):
            ui.summarize_dashboard_health(poll_interval_ms=0, pending_jobs=0, failed_jobs=0)
        with self.assertRaises(ValueError):
            ui.summarize_dashboard_health(poll_interval_ms=1, pending_jobs=-1, failed_jobs=0)

        self.assertEqual(
            ui.summarize_dashboard_health(poll_interval_ms=1, pending_jobs=1, failed_jobs=1)["statusLevel"],
            "healthy",
        )
        self.assertEqual(
            ui.summarize_dashboard_health(poll_interval_ms=1, pending_jobs=4, failed_jobs=1)["statusLevel"],
            "watch",
        )
        self.assertEqual(
            ui.summarize_dashboard_health(poll_interval_ms=1, pending_jobs=5, failed_jobs=2)["statusLevel"],
            "degraded",
        )


class TestEditorAppSkeleton(unittest.TestCase):
    def test_editor_paths(self):
        state = editor.EditorState()
        n1 = editor.Note(id="n1", start=0.24, duration=0.5, pitch_midi=60)
        state.add_note(n1)

        with self.assertRaises(ValueError):
            state.add_note(n1)
        with self.assertRaises(ValueError):
            state.add_note(editor.Note(id="b1", start=-1, duration=1, pitch_midi=60))
        with self.assertRaises(ValueError):
            state.add_note(editor.Note(id="b2", start=0, duration=0, pitch_midi=60))
        with self.assertRaises(ValueError):
            state.add_note(editor.Note(id="b3", start=0, duration=1, pitch_midi=128))

        with self.assertRaises(ValueError):
            state.delete_note(note_id="missing")

        with self.assertRaises(ValueError):
            state.move_note(note_id="n1", new_start=-1)
        state.move_note(note_id="n1", new_start=0.5)
        with self.assertRaises(ValueError):
            state.move_note(note_id="missing", new_start=0.5)

        with self.assertRaises(ValueError):
            state.stretch_note(note_id="n1", new_duration=0)
        state.stretch_note(note_id="n1", new_duration=1.0)
        with self.assertRaises(ValueError):
            state.stretch_note(note_id="missing", new_duration=1.0)

        state.add_note(editor.Note(id="n2", start=0.49, duration=0.5, pitch_midi=62))
        with self.assertRaises(ValueError):
            state.quantize(grid=0)
        state.quantize(grid=0.25)
        self.assertEqual([n.start for n in state.notes], [0.5, 0.5])
        self.assertTrue(state.undo())
        self.assertTrue(state.redo())
        self.assertFalse(editor.EditorState().undo())
        self.assertFalse(editor.EditorState().redo())

        snapshot = state.checkpoint()
        self.assertEqual(snapshot["noteCount"], 2)

        state.delete_note(note_id="n1")
        self.assertEqual(len(state.notes), 1)


if __name__ == "__main__":
    unittest.main()
