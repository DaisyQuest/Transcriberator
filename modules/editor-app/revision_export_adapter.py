"""DT-019 revision/export adapter for editor state."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from pathlib import Path
import sys
from typing import Any


_ROOT = Path(__file__).resolve().parents[2]


def _load_module(module_name: str, relative_path: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, _ROOT / relative_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module for path {relative_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


editor_mod = _load_module("editor_app_skeleton_dt019", "modules/editor-app/src/editor_app_skeleton.py")


@dataclass(frozen=True)
class RevisionSnapshot:
    revision_id: str
    note_count: int
    notes: tuple[editor_mod.Note, ...]


class RevisionExportAdapter:
    def __init__(self) -> None:
        self._next_revision = 1

    def create_revision(self, state: editor_mod.EditorState) -> RevisionSnapshot:
        notes = tuple(state.notes)
        revision = RevisionSnapshot(
            revision_id=f"rev-{self._next_revision}",
            note_count=len(notes),
            notes=notes,
        )
        self._next_revision += 1
        return revision

    @staticmethod
    def export_manifest(revision: RevisionSnapshot, *, include_png: bool = True) -> dict[str, str]:
        if revision.note_count < 0:
            raise ValueError("revision.note_count must be >= 0")
        base = f"artifact://{revision.revision_id}"
        manifest = {
            "musicxml": f"{base}/score.musicxml",
            "midi": f"{base}/score.mid",
            "pdf": f"{base}/score.pdf",
        }
        if include_png:
            manifest["png"] = f"{base}/score.png"
        return manifest
