# PRODUCT_SPEC.md — Audio-to-Sheet-Music (Editable) Platform

**Document owner:** TBD  
**Last updated:** 2026-02-12  
**Status:** Draft v1

---

## 1. Summary

Build a production-grade system that converts uploaded **MP3** (or other common audio formats) into **editable sheet music** via an end-to-end **Automatic Music Transcription (AMT)** pipeline:

- **Upload audio → optional source separation → transcription → rhythmic/score cleanup → export**
- Outputs:
  - **MusicXML** (primary, for editability and interoperability)
  - **MIDI** (playback + debugging)
  - **PDF/PNG** (engraved sheet music)
- Provide a **feature-rich, highly responsive editor UI** for correcting transcription results and producing publishable notation.

Primary surface areas:
1) **Web Dashboard** (Node + HTML/JS): projects, jobs, status, exports, collaboration, billing/limits.  
2) **Editor App/UI** (HTML + JS, optionally Electron): waveform + piano roll + notation + tools.  
3) **Music Processing Services** (Python and/or Node): separation, transcription, quantization, engraving.

---

## 2. Goals and Non-Goals

### 2.1 Goals
- Convert audio to **editable notation** for:
  - **Solo / monophonic** sources (high accuracy target)
  - **Single polyphonic instrument** (piano/guitar) as a next tier
  - **Separated stems** (vocals/bass/drums/other) when feasible
- **Human-in-the-loop** editing that is:
  - **Low latency** (sub-50ms UI interactions for editing operations)
  - **Non-destructive** (undo/redo, revision history, confidence overlays)
- **Modular and fault-tolerant** processing pipeline:
  - resumable jobs, idempotent stages, retries, partial recompute
- Interop: MusicXML import/export; ability to open in MuseScore, Sibelius, Finale.
- Clear quality modes:
  - **Draft** (fast, lower cost)
  - **HQ** (separation + heavier models)
- Production observability: metrics, traces, job audit logs.

### 2.2 Non-Goals (v1)
- Perfect full-orchestra transcription from dense mixes.
- Fully automated lyric transcription + syllable alignment (possible v2).
- Style/engraving parity with expert engravers without manual cleanup.

---

## 3. Target Users and Use Cases

### 3.1 Personas
- **Creator (musician/teacher):** wants a quick lead sheet or part from an audio recording, then edits.
- **Transcriber:** bulk uploads, refines results, exports MusicXML/PDF.
- **Productive hobbyist:** uploads a piano cover, corrects errors in a web editor.

### 3.2 Core Use Cases
- Upload a guitar solo recording → get notation → correct a few pitches → export.
- Upload a full song → separate into stems → transcribe melody stem → export lead line.
- Upload piano audio → generate polyphonic notation → fix voicing and rhythm → export.

---

## 4. Product Requirements

### 4.1 Functional Requirements
**Ingestion**
- Upload MP3/WAV/FLAC.
- Auto-normalize audio (sample rate + loudness normalization).
- Generate waveform preview and audio proxy for streaming playback.

**Processing**
- Job creation with selectable mode:
  - Draft (no separation)
  - HQ (source separation + improved transcription)
- Pipeline stages:
  1. Decode/normalize
  2. (Optional) source separation
  3. Beat/downbeat + tempo map
  4. Pitch/onset/offset inference
  5. Quantization + score cleanup
  6. MusicXML/MIDI generation
  7. Engraving to PDF/PNG

**Editor**
- Open project → view waveform + piano roll + notation.
- Tools:
  - Add/remove notes
  - Drag note timing/pitch (snap)
  - Quantize (global + selected region)
  - Split/merge notes, ties, tuplets
  - Change key/time signatures
  - Voice assignment (polyphonic)
  - Measures/bars editing
  - Tempo map editor
  - Playback (MIDI synth + aligned audio)
- Export:
  - MusicXML, MIDI, PDF, PNG
- Project revision history:
  - autosave
  - version checkpoints
  - restore prior revision

**Dashboard**
- Project list, uploads, job status, logs, artifacts.
- Download exports and share links (optional).

### 4.2 Non-Functional Requirements
- **Responsiveness:** editor interactions <50ms in normal cases; expensive ops async with progress.
- **Availability:** pipeline continues despite worker crashes; jobs resume.
- **Reliability:** no data loss; durable artifacts.
- **Security:** authenticated access; signed URLs for downloads.
- **Scalability:** horizontal workers; handle spikes in uploads.

---

## 5. High-Level Architecture

### 5.1 Components
- **Web Dashboard API (Node):**
  - authentication, project management, job orchestration, artifact serving
- **Web Dashboard UI (HTML + JS):**
  - project/job management
- **Editor UI (HTML + JS; optionally Electron for best UX):**
  - waveform + notation + piano roll, offline-capable caching optional
- **Processing Orchestrator (Node):**
  - creates jobs, pushes tasks to queue, tracks stage state
- **Worker Services (Python and/or Node):**
  - audio decode/normalize
  - separation
  - transcription
  - quantization/cleanup
  - MusicXML generation
  - engraving

### 5.2 Data Stores
- **Postgres** (or similar): projects, jobs, stage states, revisions, users
- **Object storage** (S3-compatible/Azure Blob): audio, stems, intermediate artifacts, exports
- **Queue**: Redis/BullMQ or RabbitMQ (BullMQ favored if Node-first)

### 5.3 Job Execution Model (Fault Tolerance)
- Each job is a **DAG** of stages.
- Stage execution is:
  - **idempotent** (same inputs → same outputs; safe retry)
  - **checkpointed** (writes artifact + stage metadata)
  - **retryable** with backoff
- Orchestrator records:
  - stage `PENDING | RUNNING | SUCCEEDED | FAILED | SKIPPED`
  - artifact URIs + hashes
  - timing, worker version, model version

---

## 6. Processing Pipeline Specification

### 6.1 Stage A: Decode + Normalize
**Input:** MP3/FLAC/WAV  
**Outputs:**
- WAV (PCM) normalized (e.g., 44.1kHz mono/stereo as required)
- waveform peaks data for UI
- audio proxy for streaming preview (compressed)

**Notes**
- Ensure consistent sample rate to stabilize downstream models.

### 6.2 Stage B: Source Separation (Optional)
**Input:** normalized WAV  
**Outputs:**
- stems: `vocals`, `bass`, `drums`, `other` (or more granular later)
- stem metadata (gain, alignment, confidence)

**Implementation Options**
- Python: high-quality separation libs/models
- Node: call into Python service via RPC (recommended)

**Fallback**
- If separation fails, pipeline can continue without it (HQ degrades to Draft).

### 6.3 Stage C: Beat/Downbeat + Tempo Map
**Input:** selected stem or mix  
**Outputs:**
- tempo curve (time→BPM)
- downbeats + barlines
- time signature candidate(s) with confidence

### 6.4 Stage D: Transcription (Pitch + Onsets/Offsets)
**Modes**
- **Monophonic:** f0 tracking + onset detection
- **Polyphonic:** multi-pitch + onset/offset detection (piano/guitar)

**Outputs**
- event list: `{pitch, onset, offset, velocity?, confidence}`
- per-frame confidence map (for UI overlays)

### 6.5 Stage E: Quantization + Score Cleanup
**Inputs**
- event list + tempo map + meter
**Outputs**
- **Score IR** (internal score representation)
- quantization report (what changed)

**Cleanup Rules**
- snap onsets/offsets to grid (configurable)
- infer ties across barlines
- avoid impossible measures (enforce measure durations)
- detect chord clusters (polyphonic)
- infer key signature (optional v1; v1 can default to C and allow user set)

### 6.6 Stage F: MusicXML/MIDI Generation
**Inputs:** Score IR  
**Outputs:** MusicXML + MIDI

### 6.7 Stage G: Engraving
**Inputs:** MusicXML  
**Outputs:** PDF/PNG with consistent layout

**Preferred Implementation**
- Headless MuseScore or equivalent engraving engine in worker container.

---

## 7. Editor UI Specification (Feature-Rich + Highly Responsive)

### 7.1 Editor Form Factor
**Recommended:** Web app (HTML + JS) with optional **Electron wrapper** to:
- improve file access performance
- enable offline caching
- provide native menus/shortcuts

### 7.2 Core Views (Synchronized)
- **Waveform view** (zoomable, scrollable)
- **Piano roll** (event-level editing, great for quick fixes)
- **Notation view** (WYSIWYG-ish, MusicXML-backed)
- **Timeline/tempo map** (BPM changes, barlines, markers)

All views share a unified time cursor and selection model.

### 7.3 Editing Model
- Non-destructive edits applied to **Score IR** with:
  - command pattern for undo/redo
  - autosave snapshots
- Selections:
  - time range selection
  - note selection (multi-select)
  - measure selection

### 7.4 Responsiveness Techniques
- Render-heavy components (notation, waveform) use:
  - **Web Workers** for CPU-heavy transforms (quantize, reflow)
  - **incremental rendering** (only re-render dirty measures)
  - local caches keyed by `(score_revision, zoom_level, page_layout)`
- Audio playback:
  - WebAudio for aligned playback
  - precomputed click track for metronome alignment

### 7.5 Notation Rendering Library
- Use a mature JS notation renderer for editor display (examples include MusicXML renderers or notation libraries).
- Keep the rendering layer swappable:
  - `NotationRenderer` interface: `render(measures)->canvas/svg`, `hitTest(x,y)->noteId`, `layout(options)->pages`

### 7.6 Feature Requirements (v1)
- **Transport:** play/pause, loop, metronome, scrub
- **Note edits:** add/delete, move pitch/time, stretch duration
- **Quantize tools:** strength slider, grid selection, swing toggle
- **Measure ops:** insert/delete measures, change time signature
- **Key signature:** set/update; transposition helper optional
- **Voices (polyphonic):** assign note to voice 1/2, split staff (piano)
- **Confidence overlay:** highlight low-confidence notes
- **Export:** MusicXML/MIDI/PDF/PNG from current revision

### 7.7 Nice-to-Haves (v2)
- Chord symbol inference + lead-sheet mode
- Guitar tablature view
- Lyrics alignment
- Collaboration (multi-user real-time) with OT/CRDT

---

## 8. Dashboard UI (Node + HTML/JS)

### 8.1 Pages
- **Projects**
  - create project, upload audio, view artifacts
- **Job detail**
  - stage timeline, logs, retry/continue, artifacts
- **Editor launch**
  - open in editor with selected artifact version

### 8.2 Job Controls
- cancel job
- retry failed stage
- “re-run from stage X” (invalidates downstream artifacts)
- quality mode selection (Draft/HQ)

---

## 9. Internal Data Model

### 9.1 Entities
**Project**
- id, owner_id, title, created_at

**AudioAsset**
- id, project_id, original_uri, normalized_uri, duration, sr, channels, hash

**Job**
- id, project_id, mode, status, created_at, updated_at
- model_version(s), worker_version(s)

**StageRun**
- id, job_id, stage_name, status, attempts, started_at, ended_at
- input_artifacts[], output_artifacts[], error_summary

**ScoreRevision**
- id, project_id, parent_revision_id, created_at, created_by
- score_ir_uri, musicxml_uri, midi_uri, render_pdf_uri

### 9.2 Score IR (Internal Representation)
A JSON-ish format that is richer than MIDI but simpler than MusicXML:
- parts → measures → voices → events
- events: note/rest/chord, ties, tuplets, articulations (optional), confidence
- global: tempo map, time signatures, key signatures

---

## 10. APIs and Contracts

### 10.1 Dashboard API (Node)
- `POST /projects`
- `POST /projects/:id/uploads`
- `POST /projects/:id/jobs` (mode + options)
- `GET /jobs/:id` (status + stage runs)
- `POST /jobs/:id/retry` (stage optional)
- `GET /projects/:id/revisions`
- `POST /projects/:id/revisions` (create new revision from editor save)
- `GET /artifacts/:id/download` (signed URLs)

### 10.2 Worker RPC (Recommended)
- Use HTTP/gRPC between Node orchestrator and Python workers:
  - `POST /worker/separate`
  - `POST /worker/transcribe`
  - `POST /worker/quantize`
  - `POST /worker/engrave`

Workers pull inputs from object storage and push outputs back.

---

## 11. Modularity Strategy

### 11.1 Replaceable Modules
- **Separator**: interchangeable models
- **Transcriber**: monophonic vs polyphonic engines
- **Quantizer/Cleaner**: rule-based vs ML-enhanced
- **Engraver**: different render backends

Define interfaces per stage, versioned:
- `ISeparator.v1`
- `ITranscriberMono.v1`
- `ITranscriberPoly.v1`
- `IQuantizer.v1`
- `IEngraver.v1`

### 11.2 Versioning
- Every artifact tagged with:
  - `pipeline_version`
  - `model_version`
  - `config_hash`
Allows reproducibility and regression testing.

---

## 12. Fault Tolerance and Recovery

### 12.1 Failure Modes
- upload corruption
- separation model OOM / timeout
- transient storage/queue failure
- partial artifact write

### 12.2 Mitigations
- stage-level retries with exponential backoff
- artifact writes are atomic:
  - write to temp URI → finalize rename/commit
- idempotency keys for job/stage requests
- dead-letter queue for poisoned jobs
- graceful degradation:
  - HQ falls back to Draft if separation fails

### 12.3 Resume Semantics
- a job can restart from last successful stage using stored artifacts/hashes.

---

## 13. Observability

- Metrics:
  - job throughput, stage durations, failure rates
  - cost per minute of audio (by mode)
- Tracing:
  - orchestrator → worker calls
- Logs:
  - job timeline and error summaries
- Audit:
  - revision history in editor (who changed what)

---

## 14. Security and Privacy

- Authentication for dashboard/editor.
- Signed URLs for artifact download.
- Encrypt data at rest in object storage (provider feature).
- Retention policy configurable per tenant:
  - auto-delete raw uploads after N days (optional)
- Model execution sandboxed in containers.

---

## 15. Testing Strategy

### 15.1 Unit Tests
- Score IR transformations (quantization, tie inference, bar enforcement)
- API contract tests
- Editor state reducers/commands

### 15.2 Integration Tests
- End-to-end job on known fixtures:
  - monophonic scale
  - simple melody with clear tempo
  - piano chords
- Golden files:
  - expected MusicXML excerpts
  - expected measure durations

### 15.3 Performance Tests
- Editor rendering at large scores (10+ pages)
- Pipeline on 5, 15, 60 minute audio

---

## 16. Milestones

### M0 — Foundations (Week 1–2)
- Project/job DB schema
- Upload + normalize + waveform
- Draft monophonic transcription → MusicXML/MIDI
- Minimal editor: waveform + piano roll + export

### M1 — Editor v1 (Week 3–4)
- Notation view (MusicXML render)
- Undo/redo, selection, snapping
- Quantize tool
- Revision history + exports

### M2 — HQ Pipeline (Week 5–6)
- Separation stage
- Stem selection (transcribe chosen stem)
- Better tempo map + barlines

### M3 — Polyphonic (Week 7–10)
- Piano/guitar polyphonic mode
- Voice assignment tools
- Improved cleanup

---

## 17. Open Questions
- Editor runtime: web-only vs Electron-first?
- Which separation/transcription engines meet desired quality/cost tradeoff?
- Desired default output: lead sheet vs full score per stem?
- Licensing considerations for embedding engraving engines.

---

## 18. Appendix — “Editor Must-Feel-Instant” Checklist
- Keep edits local-first; sync in background.
- Re-render only dirty measures; avoid full-score relayout.
- Heavy ops (re-quantize, reflow) run in workers with progress UI.
- Maintain stable playback sync with audio + MIDI.
