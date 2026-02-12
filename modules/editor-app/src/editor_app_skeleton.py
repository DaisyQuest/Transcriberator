"""DT-009 Editor app skeleton state + core edit operations."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import List, Tuple


@dataclass(frozen=True)
class Note:
    id: str
    start: float
    duration: float
    pitch_midi: int


class EditorState:
    """Minimal in-memory editor model with undo/redo and checkpoints."""

    def __init__(self) -> None:
        self._notes: List[Note] = []
        self._undo: List[Tuple[Note, ...]] = []
        self._redo: List[Tuple[Note, ...]] = []

    @property
    def notes(self) -> List[Note]:
        return list(self._notes)

    def _snapshot(self) -> Tuple[Note, ...]:
        return tuple(self._notes)

    def _record_history(self) -> None:
        self._undo.append(self._snapshot())
        self._redo.clear()

    def add_note(self, note: Note) -> None:
        self._validate_note(note)
        if any(existing.id == note.id for existing in self._notes):
            raise ValueError(f"Duplicate note id '{note.id}'")
        self._record_history()
        self._notes.append(note)

    def delete_note(self, *, note_id: str) -> None:
        for idx, note in enumerate(self._notes):
            if note.id == note_id:
                self._record_history()
                del self._notes[idx]
                return
        raise ValueError(f"Unknown note id '{note_id}'")

    def move_note(self, *, note_id: str, new_start: float) -> None:
        if new_start < 0:
            raise ValueError("new_start must be >= 0")
        for idx, note in enumerate(self._notes):
            if note.id == note_id:
                self._record_history()
                self._notes[idx] = replace(note, start=new_start)
                return
        raise ValueError(f"Unknown note id '{note_id}'")

    def stretch_note(self, *, note_id: str, new_duration: float) -> None:
        if new_duration <= 0:
            raise ValueError("new_duration must be > 0")
        for idx, note in enumerate(self._notes):
            if note.id == note_id:
                self._record_history()
                self._notes[idx] = replace(note, duration=new_duration)
                return
        raise ValueError(f"Unknown note id '{note_id}'")

    def quantize(self, *, grid: float) -> None:
        if grid <= 0:
            raise ValueError("grid must be > 0")
        self._record_history()
        self._notes = [replace(note, start=round(note.start / grid) * grid) for note in self._notes]

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self._snapshot())
        self._notes = list(self._undo.pop())
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self._snapshot())
        self._notes = list(self._redo.pop())
        return True

    def checkpoint(self) -> dict:
        return {
            "noteCount": len(self._notes),
            "undoDepth": len(self._undo),
            "redoDepth": len(self._redo),
        }

    @staticmethod
    def _validate_note(note: Note) -> None:
        if note.start < 0:
            raise ValueError("note.start must be >= 0")
        if note.duration <= 0:
            raise ValueError("note.duration must be > 0")
        if not 0 <= note.pitch_midi <= 127:
            raise ValueError("note.pitch_midi must be in [0, 127]")
