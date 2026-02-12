"""DT-013 Worker-transcription skeleton.

This module intentionally remains deterministic and lightweight while simulating
core stage-D responsibilities (pitch/onset/offset inference).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class TranscriptionTaskRequest:
    source_uri: str
    polyphonic: bool
    model_version: str = "skeleton-v1"
    # Optional deterministic analysis fixture. Each frame contains one or more
    # simultaneous MIDI pitches that should be interpreted as active notes.
    analysis_frames: tuple[tuple[int, ...], ...] = ()


@dataclass(frozen=True)
class TranscriptionTaskResult:
    event_count: int
    confidence: float
    model_version: str
    isolated_pitches: tuple[int, ...] = ()
    detected_chords: tuple[str, ...] = ()


class TranscriptionWorker:
    _CHORD_INTERVALS: tuple[tuple[str, frozenset[int]], ...] = (
        ("major", frozenset({0, 4, 7})),
        ("minor", frozenset({0, 3, 7})),
        ("diminished", frozenset({0, 3, 6})),
        ("augmented", frozenset({0, 4, 8})),
        ("suspended2", frozenset({0, 2, 7})),
        ("suspended4", frozenset({0, 5, 7})),
    )
    _PITCH_CLASS_NAMES: tuple[str, ...] = (
        "C",
        "C#",
        "D",
        "D#",
        "E",
        "F",
        "F#",
        "G",
        "G#",
        "A",
        "A#",
        "B",
    )

    def process(self, request: TranscriptionTaskRequest) -> TranscriptionTaskResult:
        if not request.source_uri:
            raise ValueError("source_uri is required")
        if not request.model_version:
            raise ValueError("model_version is required")

        self._validate_frames(request.analysis_frames)
        isolated_pitches = self._isolate_prominent_pitches(request.analysis_frames)

        if request.analysis_frames:
            event_count = sum(len(frame) for frame in request.analysis_frames)
            detected_chords = self._identify_chords(request.analysis_frames)
            confidence = self._score_confidence(
                polyphonic=request.polyphonic,
                frame_count=len(request.analysis_frames),
                chord_count=len(detected_chords),
                isolated_pitch_count=len(isolated_pitches),
            )
        else:
            # Backward-compatible deterministic fallback for empty fixture data.
            event_count = 32 if request.polyphonic else 12
            detected_chords = ()
            confidence = 0.82 if request.polyphonic else 0.91

        return TranscriptionTaskResult(
            event_count=event_count,
            confidence=confidence,
            model_version=request.model_version,
            isolated_pitches=isolated_pitches,
            detected_chords=detected_chords,
        )

    def _validate_frames(self, analysis_frames: tuple[tuple[int, ...], ...]) -> None:
        for frame in analysis_frames:
            if not frame:
                raise ValueError("analysis_frames cannot contain empty frames")
            for pitch in frame:
                if not 0 <= pitch <= 127:
                    raise ValueError("analysis_frames pitches must be in [0, 127]")

    def _isolate_prominent_pitches(self, analysis_frames: tuple[tuple[int, ...], ...]) -> tuple[int, ...]:
        if not analysis_frames:
            return ()

        counts: dict[int, int] = {}
        for frame in analysis_frames:
            for pitch in frame:
                counts[pitch] = counts.get(pitch, 0) + 1

        peak = max(counts.values())
        # Keep only frequent pitches to suppress transient noise.
        threshold = max(2, peak // 2)
        isolated = [pitch for pitch, count in counts.items() if count >= threshold]
        return tuple(sorted(isolated))

    def _identify_chords(self, analysis_frames: tuple[tuple[int, ...], ...]) -> tuple[str, ...]:
        detected: list[str] = []

        for frame in analysis_frames:
            if len(frame) < 3:
                continue
            label = self._match_chord(frame)
            if label and label not in detected:
                detected.append(label)

        return tuple(detected)

    def _match_chord(self, frame: Iterable[int]) -> str | None:
        frame_tuple = tuple(frame)
        pitch_classes = sorted({pitch % 12 for pitch in frame_tuple})
        if len(pitch_classes) < 3:
            return None

        preferred_root = min(frame_tuple) % 12
        ordered_roots = [preferred_root] + [root for root in pitch_classes if root != preferred_root]

        for root in ordered_roots:
            intervals = frozenset((pc - root) % 12 for pc in pitch_classes)
            for quality_name, reference in self._CHORD_INTERVALS:
                if reference.issubset(intervals):
                    root_name = self._PITCH_CLASS_NAMES[root]
                    return f"{root_name}:{quality_name}"
        return None

    def _score_confidence(
        self,
        *,
        polyphonic: bool,
        frame_count: int,
        chord_count: int,
        isolated_pitch_count: int,
    ) -> float:
        if frame_count <= 0:
            return 0.0

        base = 0.6 if polyphonic else 0.75
        chord_bonus = min(0.2, chord_count * 0.05)
        stability_bonus = min(0.15, isolated_pitch_count / (frame_count * 2))
        confidence = base + chord_bonus + stability_bonus
        return round(min(0.99, confidence), 3)
