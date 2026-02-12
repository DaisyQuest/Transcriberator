"""DT-011 Worker-audio skeleton."""

from __future__ import annotations

from dataclasses import dataclass


SUPPORTED_AUDIO_FORMATS = {"mp3", "wav", "flac"}


@dataclass(frozen=True)
class AudioTaskRequest:
    asset_id: str
    source_uri: str
    audio_format: str
    sample_rate_hz: int = 44100


@dataclass(frozen=True)
class AudioTaskResult:
    normalized_uri: str
    waveform_uri: str
    proxy_uri: str
    deterministic_fingerprint: str


class AudioWorker:
    """Decode/normalize skeleton with deterministic output addressing."""

    def process(self, request: AudioTaskRequest) -> AudioTaskResult:
        if request.audio_format not in SUPPORTED_AUDIO_FORMATS:
            raise ValueError(f"Unsupported audio format: {request.audio_format}")
        if request.sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be > 0")

        base = f"{request.asset_id}-{request.audio_format}-{request.sample_rate_hz}"
        return AudioTaskResult(
            normalized_uri=f"normalized://{base}.pcm",
            waveform_uri=f"waveform://{base}.json",
            proxy_uri=f"proxy://{base}.aac",
            deterministic_fingerprint=base,
        )
