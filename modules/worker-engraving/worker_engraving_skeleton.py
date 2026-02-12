"""DT-015 Worker-engraving skeleton."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EngravingTaskRequest:
    musicxml_uri: str
    dpi: int = 300


@dataclass(frozen=True)
class EngravingTaskResult:
    pdf_uri: str
    png_uri: str
    readable: bool


class EngravingWorker:
    def process(self, request: EngravingTaskRequest) -> EngravingTaskResult:
        if not request.musicxml_uri:
            raise ValueError("musicxml_uri is required")
        if request.dpi < 72:
            raise ValueError("dpi must be >= 72")

        slug = request.musicxml_uri.replace('://', '_').replace('/', '_')
        return EngravingTaskResult(
            pdf_uri=f"pdf://{slug}.pdf",
            png_uri=f"png://{slug}.png",
            readable=request.dpi >= 150,
        )
