# Final_Spec.md

This document is derived from `PRODUCT_SPEC.md` and reorganized into an implementation-oriented, itemized specification. Redis is explicitly deferred for now; queueing and artifacts should target Azure-compatible services, with Blob Storage as the canonical object store.

## FS-001 Platform Objective
Build a production-grade audio-to-editable-sheet-music platform that transforms uploaded audio into editable notation and publishable outputs.

## FS-002 Input Audio Support
Support MP3, WAV, and FLAC uploads.

## FS-003 Output Artifact Support
Generate MusicXML (primary), MIDI, PDF, and PNG outputs.

## FS-004 Product Surfaces
Deliver three major surfaces:
- Dashboard (project/job/admin workflows)
- Editor (waveform, piano roll, notation editing)
- Processing services (transcription pipeline)

## FS-005 User Persona: Creator
Enable musicians/teachers to quickly transcribe and refine recordings.

## FS-006 User Persona: Transcriber
Enable high-throughput upload/refinement/export workflows.

## FS-007 User Persona: Hobbyist
Enable approachable upload-to-edit-to-export flow for non-experts.

## FS-008 Mode: Draft
Provide a fast Draft mode without separation.

## FS-009 Mode: HQ
Provide an HQ mode that includes source separation and stronger transcription behavior.

## FS-010 Ingestion Normalization
Decode and normalize audio (sample rate + loudness).

## FS-011 Waveform/Proxy Generation
Produce waveform peaks and streaming-friendly audio proxy artifacts.

## FS-012 Pipeline Stage A
Implement decode + normalize as stage A.

## FS-013 Pipeline Stage B
Implement optional source separation as stage B.

## FS-014 Pipeline Stage C
Implement beat/downbeat and tempo map extraction as stage C.

## FS-015 Pipeline Stage D
Implement pitch/onset/offset inference as stage D.

## FS-016 Pipeline Stage E
Implement quantization and score cleanup as stage E.

## FS-017 Pipeline Stage F
Implement MusicXML and MIDI generation as stage F.

## FS-018 Pipeline Stage G
Implement engraving to PDF/PNG as stage G.

## FS-019 Editor Core Views
Editor must provide waveform, piano roll, and notation views.

## FS-020 Editor Note Editing
Support add/delete/move/stretch note operations with snapping.

## FS-021 Editor Rhythm/Structure Tools
Support quantize tools, split/merge, ties, tuplets, bar/measure editing.

## FS-022 Editor Musical Context Tools
Support key signature, time signature, tempo map, and transposition helpers.

## FS-023 Editor Polyphonic Tools
Support voice assignment and split-staff handling for polyphonic use cases.

## FS-024 Editor Playback
Provide synchronized audio + MIDI playback controls.

## FS-025 Editor Revisioning
Provide autosave, checkpointing, undo/redo, restore prior revision.

## FS-026 Confidence UX
Expose low-confidence overlays for human-in-the-loop correction.

## FS-027 Dashboard Project Management
Support create/list/open project workflows.

## FS-028 Dashboard Job Operations
Support create/cancel/retry/re-run-from-stage job control operations.

## FS-029 Dashboard Job Visibility
Expose stage timeline, status, logs, and artifact links.

## FS-030 Dashboard Export Operations
Support export download and optional sharing workflows.

## FS-031 API Contracts
Provide HTTP contracts for projects, uploads, jobs, revisions, and artifact download links.

## FS-032 Worker Contracts
Provide worker RPC endpoints for separation, transcription, quantization, and engraving.

## FS-033 Core Data Entity: Project
Persist project metadata with ownership and timestamps.

## FS-034 Core Data Entity: AudioAsset
Persist original/normalized asset references + audio metadata.

## FS-035 Core Data Entity: Job
Persist mode/status/version fields for pipeline execution.

## FS-036 Core Data Entity: StageRun
Persist per-stage status, attempts, I/O artifacts, and error summaries.

## FS-037 Core Data Entity: ScoreRevision
Persist revision tree and current artifact pointers.

## FS-038 Internal Score IR
Define canonical internal score representation richer than MIDI, simpler than MusicXML.

## FS-039 Storage Strategy
Use Azure Blob Storage for raw uploads, intermediates, and exports.

## FS-040 Database Strategy
Use Postgres (or equivalent relational store) for project/job/revision metadata.

## FS-041 Queue Strategy (No Redis for now)
Do not require Redis in initial implementation; design queue abstraction so Azure-native queueing can be introduced cleanly.

## FS-042 DAG Execution Model
Represent jobs as DAG stages with strict state transitions.

## FS-043 Idempotent Stage Execution
All stages must be idempotent with deterministic inputs/outputs.

## FS-044 Checkpointed Stage Artifacts
Each stage must write durable artifacts and metadata checkpoints.

## FS-045 Retry Policy
Apply retries with exponential backoff for transient failures.

## FS-046 Resume Semantics
Allow job resume from latest successful stage.

## FS-047 Graceful Degradation
Allow HQ execution to degrade to Draft-like behavior when separation fails.

## FS-048 Security Baseline
Require authentication and signed download URLs.

## FS-049 Privacy Baseline
Support encryption-at-rest and configurable retention policies.

## FS-050 Observability Baseline
Collect metrics for throughput/failures/durations/cost.

## FS-051 Tracing Baseline
Trace orchestrator-to-worker calls and stage lifecycles.

## FS-052 Logging Baseline
Maintain detailed job timeline logs and concise error summaries.

## FS-053 Audit Baseline
Track revision history and user actions relevant to score changes.

## FS-054 Performance Requirement: Editor Responsiveness
Target sub-50ms editor interactions for standard edit operations.

## FS-055 Reliability Requirement
Prevent data loss and guarantee durable artifact storage.

## FS-056 Scalability Requirement
Support horizontal scaling for workers and bursty upload traffic.

## FS-057 Test Strategy: Unit
Unit test score transforms, API contracts, and editor state logic.

## FS-058 Test Strategy: Integration
Run end-to-end fixture pipelines and assert golden outputs.

## FS-059 Test Strategy: Performance
Benchmark editor rendering and pipeline processing durations.

## FS-060 Milestone M0
Deliver schema, upload+normalize, draft monophonic pipeline, minimal editor.

## FS-061 Milestone M1
Deliver notation view, undo/redo, quantize tooling, revision history.

## FS-062 Milestone M2
Deliver HQ separation path, stem targeting, improved tempo/barline handling.

## FS-063 Milestone M3
Deliver polyphonic modes, voice tools, improved cleanup.

## FS-064 Modular Interface Contracts
Define replaceable interfaces for separator, transcriber(s), quantizer, and engraver.

## FS-065 Versioning and Reproducibility
Tag artifacts with pipeline/model/config versions to enable repeatability.

## FS-066 Local Development Requirement
Entire system must be runnable and testable locally on Windows with minimal friction.

## FS-067 UX Quality Requirement
Output must be beautiful, readable, and confidence-inspiring for end users.

## FS-068 Extensibility Requirement
Design modules so implementation details are replaceable without broad rewrites.
