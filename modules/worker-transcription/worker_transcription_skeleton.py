"""DT-013 Worker-transcription skeleton.

This module intentionally remains deterministic and lightweight while simulating
core stage-D responsibilities (pitch/onset/offset inference).
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Iterable


@dataclass(frozen=True)
class TranscriptionTaskRequest:
    source_uri: str
    polyphonic: bool
    model_version: str = "skeleton-v1"
    # Optional deterministic analysis fixture. Each frame contains one or more
    # simultaneous MIDI pitches that should be interpreted as active notes.
    analysis_frames: tuple[tuple[int, ...], ...] = ()
    instrument_preset: str = "auto"


@dataclass(frozen=True)
class TranscriptionTaskResult:
    event_count: int
    confidence: float
    model_version: str
    isolated_pitches: tuple[int, ...] = ()
    detected_chords: tuple[str, ...] = ()
    detected_instrument: str = "unknown"
    applied_preset: str = "auto"


class TranscriptionWorker:
    _INSTRUMENT_PRESETS: dict[str, dict[str, float]] = {
        "auto": {"min_pitch": 0, "max_pitch": 127, "chord_affinity": 0.0, "polyphony_affinity": 0.0},
        "acoustic_guitar": {"min_pitch": 40, "max_pitch": 88, "chord_affinity": 0.28, "polyphony_affinity": 0.2},
        "electric_guitar": {"min_pitch": 36, "max_pitch": 96, "chord_affinity": 0.24, "polyphony_affinity": 0.16},
        "piano": {"min_pitch": 21, "max_pitch": 108, "chord_affinity": 0.18, "polyphony_affinity": 0.24},
        "flute": {"min_pitch": 60, "max_pitch": 96, "chord_affinity": -0.3, "polyphony_affinity": -0.4},
        "violin": {"min_pitch": 55, "max_pitch": 103, "chord_affinity": -0.12, "polyphony_affinity": -0.2},
    }
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
        self._validate_preset(request.instrument_preset)

        self._validate_frames(request.analysis_frames)
        normalized_frames = self._normalize_frames(request.analysis_frames)
        isolated_pitches = self._isolate_prominent_pitches(normalized_frames)

        if normalized_frames:
            event_count = sum(len(frame) for frame in normalized_frames)
            detected_chords = self._identify_chords(normalized_frames)
            confidence = self._score_confidence(
                polyphonic=request.polyphonic,
                frame_count=len(normalized_frames),
                chord_count=len(detected_chords),
                isolated_pitch_count=len(isolated_pitches),
                harmonic_density=self._estimate_harmonic_density(normalized_frames),
            )
            detected_instrument, applied_preset = self._detect_instrument(
                analysis_frames=normalized_frames,
                preset_name=request.instrument_preset,
                chord_count=len(detected_chords),
                polyphonic=request.polyphonic,
            )
        else:
            # Backward-compatible deterministic fallback for empty fixture data.
            event_count = 32 if request.polyphonic else 12
            detected_chords = ()
            confidence = 0.82 if request.polyphonic else 0.91
            detected_instrument = "unknown"
            applied_preset = request.instrument_preset

        return TranscriptionTaskResult(
            event_count=event_count,
            confidence=confidence,
            model_version=request.model_version,
            isolated_pitches=isolated_pitches,
            detected_chords=detected_chords,
            detected_instrument=detected_instrument,
            applied_preset=applied_preset,
        )

    def _validate_preset(self, preset_name: str) -> None:
        if preset_name not in self._INSTRUMENT_PRESETS:
            supported = ", ".join(sorted(self._INSTRUMENT_PRESETS))
            raise ValueError(f"instrument_preset must be one of: {supported}")

    def _validate_frames(self, analysis_frames: tuple[tuple[int, ...], ...]) -> None:
        for frame in analysis_frames:
            if not frame:
                raise ValueError("analysis_frames cannot contain empty frames")
            for pitch in frame:
                if not 0 <= pitch <= 127:
                    raise ValueError("analysis_frames pitches must be in [0, 127]")

    def _normalize_frames(self, analysis_frames: tuple[tuple[int, ...], ...]) -> tuple[tuple[int, ...], ...]:
        """Normalize frame content to reduce duplicate/noisy activations.

        - Sort each frame for deterministic processing.
        - Remove duplicate pitches within a frame while preserving temporal frame count.
        """
        normalized: list[tuple[int, ...]] = []
        for frame in analysis_frames:
            normalized.append(tuple(sorted(set(frame))))
        return tuple(normalized)

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
        harmonic_density: float,
    ) -> float:
        if frame_count <= 0:
            return 0.0

        base = 0.6 if polyphonic else 0.75
        chord_bonus = min(0.2, chord_count * 0.05)
        stability_bonus = min(0.15, isolated_pitch_count / (frame_count * 2))
        density_bonus = min(0.08, max(0.0, harmonic_density - 1.0) * 0.04)
        confidence = base + chord_bonus + stability_bonus + density_bonus
        return round(min(0.99, confidence), 3)

    def _estimate_harmonic_density(self, analysis_frames: tuple[tuple[int, ...], ...]) -> float:
        if not analysis_frames:
            return 0.0

        frame_sizes = [len(frame) for frame in analysis_frames]
        return float(median(frame_sizes))

    def _detect_instrument(
        self,
        *,
        analysis_frames: tuple[tuple[int, ...], ...],
        preset_name: str,
        chord_count: int,
        polyphonic: bool,
    ) -> tuple[str, str]:
        flattened = [pitch for frame in analysis_frames for pitch in frame]
        if not flattened:
            return "unknown", preset_name

        if preset_name != "auto":
            return preset_name, preset_name

        candidate_scores: dict[str, float] = {}
        for candidate, profile in self._INSTRUMENT_PRESETS.items():
            if candidate == "auto":
                continue
            score = self._score_instrument_candidate(
                pitches=flattened,
                profile=profile,
                chord_count=chord_count,
                polyphonic=polyphonic,
            )
            candidate_scores[candidate] = score

        # Deterministic tie-breaking favors narrow-range instruments first to
        # improve robustness for sparse monophonic passages.
        detected = max(
            sorted(candidate_scores),
            key=lambda candidate: (candidate_scores[candidate], -self._profile_pitch_span(candidate)),
        )
        return detected, "auto"

    def _profile_pitch_span(self, profile_name: str) -> int:
        profile = self._INSTRUMENT_PRESETS[profile_name]
        return int(profile["max_pitch"] - profile["min_pitch"])

    def _score_instrument_candidate(
        self,
        *,
        pitches: list[int],
        profile: dict[str, float],
        chord_count: int,
        polyphonic: bool,
    ) -> float:
        min_pitch = int(profile["min_pitch"])
        max_pitch = int(profile["max_pitch"])
        in_range = sum(1 for pitch in pitches if min_pitch <= pitch <= max_pitch)
        range_score = in_range / len(pitches)

        chord_bonus = profile["chord_affinity"] * min(1.0, chord_count / 4)
        polyphony_bonus = profile["polyphony_affinity"] if polyphonic else -profile["polyphony_affinity"]
        return range_score + chord_bonus + polyphony_bonus
