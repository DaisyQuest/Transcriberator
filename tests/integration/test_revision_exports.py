import importlib.util
import unittest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


editor_skeleton_mod = load_module("editor_skeleton_dt019_test", "modules/editor-app/src/editor_app_skeleton.py")
editor_adapter_mod = load_module("editor_adapter_dt019_test", "modules/editor-app/revision_export_adapter.py")
api_adapter_mod = load_module("api_adapter_dt019_test", "modules/dashboard-api/revision_export_adapter.py")


class TestRevisionExportIntegration(unittest.TestCase):
    def setUp(self):
        self.editor_state = editor_skeleton_mod.EditorState()
        self.editor_state.add_note(editor_skeleton_mod.Note(id="n1", start=0.0, duration=0.5, pitch_midi=60))
        self.editor_state.add_note(editor_skeleton_mod.Note(id="n2", start=1.0, duration=0.5, pitch_midi=64))
        self.editor_adapter = editor_adapter_mod.RevisionExportAdapter()
        self.api_adapter = api_adapter_mod.DashboardRevisionExportAdapter()

    def test_revision_export_manifest_and_download_links(self):
        revision = self.editor_adapter.create_revision(self.editor_state)
        manifest = self.editor_adapter.export_manifest(revision, include_png=True)
        links = self.api_adapter.build_download_links(
            revision_id=revision.revision_id,
            export_manifest=manifest,
            ttl_seconds=120,
        )

        self.assertEqual(revision.revision_id, "rev-1")
        self.assertEqual(revision.note_count, 2)
        self.assertEqual(set(manifest), {"musicxml", "midi", "pdf", "png"})
        self.assertEqual(set(links.links), {"midi", "musicxml", "pdf", "png"})
        for key, link in links.links.items():
            with self.subTest(key=key):
                self.assertIn(f"{revision.revision_id}-{key}", link)

    def test_revision_adapter_branches(self):
        revision_1 = self.editor_adapter.create_revision(self.editor_state)
        revision_2 = self.editor_adapter.create_revision(self.editor_state)
        self.assertEqual(revision_2.revision_id, "rev-2")

        manifest_no_png = self.editor_adapter.export_manifest(revision_1, include_png=False)
        self.assertNotIn("png", manifest_no_png)

        bad_revision = editor_adapter_mod.RevisionSnapshot(revision_id="bad", note_count=-1, notes=tuple())
        with self.assertRaisesRegex(ValueError, "note_count must be >= 0"):
            self.editor_adapter.export_manifest(bad_revision)

    def test_dashboard_adapter_validation_errors(self):
        revision = self.editor_adapter.create_revision(self.editor_state)
        manifest = self.editor_adapter.export_manifest(revision)

        with self.assertRaisesRegex(Exception, "Revision id is required"):
            self.api_adapter.build_download_links(revision_id="", export_manifest=manifest, ttl_seconds=1)

        with self.assertRaisesRegex(Exception, "Export manifest cannot be empty"):
            self.api_adapter.build_download_links(revision_id=revision.revision_id, export_manifest={}, ttl_seconds=1)

        with self.assertRaisesRegex(Exception, "TTL must be greater than zero"):
            self.api_adapter.build_download_links(
                revision_id=revision.revision_id,
                export_manifest=manifest,
                ttl_seconds=0,
            )


if __name__ == "__main__":
    unittest.main()
