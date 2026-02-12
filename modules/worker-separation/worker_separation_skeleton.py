"""DT-012 Worker-separation skeleton."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeparationTaskRequest:
    asset_id: str
    normalized_uri: str
    target_stems: tuple[str, ...] = ("vocals", "other")
    simulate_timeout: bool = False


@dataclass(frozen=True)
class SeparationTaskResult:
    stem_uris: dict[str, str]
    quality_score: float
    degraded: bool


class SeparationWorker:
    def process(self, request: SeparationTaskRequest) -> SeparationTaskResult:
        if not request.target_stems:
            raise ValueError("target_stems cannot be empty")

        if request.simulate_timeout:
            return SeparationTaskResult(stem_uris={}, quality_score=0.0, degraded=True)

        stems = {stem: f"stem://{request.asset_id}/{stem}.wav" for stem in request.target_stems}
        return SeparationTaskResult(stem_uris=stems, quality_score=0.9, degraded=False)
