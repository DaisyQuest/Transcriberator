# Worker_Audio_Spec.md

## Scope
Decode and normalize audio; generate waveform peaks and streaming proxy artifacts.

## Responsibilities
- Accept source audio references.
- Produce normalized PCM outputs.
- Emit waveform/proxy assets and metadata.

## Quality Gates
- Deterministic processing for identical input/config.
- Format compatibility tests across MP3/WAV/FLAC.
