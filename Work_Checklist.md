# Work_Checklist.md

Implementation checklist mirroring `Final_Spec.md`. Every item has a unique checklist ID and tracks execution readiness.

| Checklist ID | Final Spec Ref | Item | Status |
|---|---|---|---|
| WC-001 | FS-001 | Build end-to-end audio-to-editable-sheet-music platform baseline | TODO |
| WC-002 | FS-002 | Implement MP3/WAV/FLAC ingestion support | TODO |
| WC-003 | FS-003 | Implement MusicXML/MIDI/PDF/PNG export outputs | TODO |
| WC-004 | FS-004 | Stand up dashboard/editor/processing surfaces | TODO |
| WC-005 | FS-005 | Validate creator persona workflows | TODO |
| WC-006 | FS-006 | Validate transcriber persona workflows | TODO |
| WC-007 | FS-007 | Validate hobbyist persona workflows | TODO |
| WC-008 | FS-008 | Implement Draft mode configuration | TODO |
| WC-009 | FS-009 | Implement HQ mode configuration | TODO |
| WC-010 | FS-010 | Implement normalization stage | TODO |
| WC-011 | FS-011 | Implement waveform + audio proxy generation | TODO |
| WC-012 | FS-012 | Implement Stage A decode/normalize execution | TODO |
| WC-013 | FS-013 | Implement Stage B optional separation execution | TODO |
| WC-014 | FS-014 | Implement Stage C tempo map extraction | TODO |
| WC-015 | FS-015 | Implement Stage D transcription inference | TODO |
| WC-016 | FS-016 | Implement Stage E quantize/cleanup | TODO |
| WC-017 | FS-017 | Implement Stage F notation artifact generation | TODO |
| WC-018 | FS-018 | Implement Stage G engraving | TODO |
| WC-019 | FS-019 | Implement editor waveform/piano-roll/notation panels | TODO |
| WC-020 | FS-020 | Implement core note edit actions | TODO |
| WC-021 | FS-021 | Implement rhythm/measure editing tools | TODO |
| WC-022 | FS-022 | Implement key/time/tempo tools | TODO |
| WC-023 | FS-023 | Implement voice and split-staff tools | TODO |
| WC-024 | FS-024 | Implement synchronized playback | TODO |
| WC-025 | FS-025 | Implement autosave/checkpoints/undo-redo/restore | TODO |
| WC-026 | FS-026 | Implement confidence visualization overlays | TODO |
| WC-027 | FS-027 | Implement project management dashboard flows | TODO |
| WC-028 | FS-028 | Implement job control operations | TODO |
| WC-029 | FS-029 | Implement job timeline/log/artifact visibility | TODO |
| WC-030 | FS-030 | Implement export/share operations | TODO |
| WC-031 | FS-031 | Implement dashboard API contracts | TODO |
| WC-032 | FS-032 | Implement worker RPC contracts | TODO |
| WC-033 | FS-033 | Implement Project persistence model | TODO |
| WC-034 | FS-034 | Implement AudioAsset persistence model | TODO |
| WC-035 | FS-035 | Implement Job persistence model | TODO |
| WC-036 | FS-036 | Implement StageRun persistence model | TODO |
| WC-037 | FS-037 | Implement ScoreRevision persistence model | TODO |
| WC-038 | FS-038 | Implement internal Score IR format | TODO |
| WC-039 | FS-039 | Integrate Azure Blob artifact storage | TODO |
| WC-040 | FS-040 | Provision relational metadata store | TODO |
| WC-041 | FS-041 | Design queue abstraction without Redis dependency | TODO |
| WC-042 | FS-042 | Implement DAG state model | TODO |
| WC-043 | FS-043 | Enforce idempotent stage behavior | TODO |
| WC-044 | FS-044 | Enforce stage checkpoint writing | TODO |
| WC-045 | FS-045 | Implement retry/backoff policy | TODO |
| WC-046 | FS-046 | Implement resume-from-last-success semantics | TODO |
| WC-047 | FS-047 | Implement HQ-to-Draft graceful fallback | TODO |
| WC-048 | FS-048 | Implement authentication + signed URLs | TODO |
| WC-049 | FS-049 | Implement privacy and retention controls | TODO |
| WC-050 | FS-050 | Implement metrics instrumentation | TODO |
| WC-051 | FS-051 | Implement distributed tracing | TODO |
| WC-052 | FS-052 | Implement structured logging baseline | TODO |
| WC-053 | FS-053 | Implement audit trail for score edits | TODO |
| WC-054 | FS-054 | Validate sub-50ms editor interactions | TODO |
| WC-055 | FS-055 | Validate durability/no-data-loss requirements | TODO |
| WC-056 | FS-056 | Validate horizontal scaling posture | TODO |
| WC-057 | FS-057 | Implement comprehensive unit test suite | TODO |
| WC-058 | FS-058 | Implement integration fixture suite | TODO |
| WC-059 | FS-059 | Implement performance benchmark suite | TODO |
| WC-060 | FS-060 | Deliver M0 milestone package | DONE |
| WC-061 | FS-061 | Deliver M1 milestone package | DONE |
| WC-062 | FS-062 | Deliver M2 milestone package | DONE |
| WC-063 | FS-063 | Deliver M3 milestone package | DONE |
| WC-064 | FS-064 | Define replaceable module interfaces | TODO |
| WC-065 | FS-065 | Implement artifact version tagging | TODO |
| WC-066 | FS-066 | Validate local Windows developer workflow | TODO |
| WC-067 | FS-067 | Validate quality/readability of output artifacts | TODO |
| WC-068 | FS-068 | Validate modular replacement workflow | TODO |


## Task Completion Checkboxes
- [x] WC-TASK-001: Add module `additional_tasks/` directories, enhance `AGENTS.md`, add work description artifact, and validate via automated tests.
- [x] WC-TASK-002: Create `Development_Tasks.md` with serial-first shared-contract planning and conflict-minimizing delegation guidance.
- [x] WC-TASK-003: Complete DT-001/DT-002/DT-003 by updating repository policy workflow, establishing test harness baseline governance, and publishing shared-contracts domain entity v1 schemas with compatibility policy.
- [x] WC-TASK-004: Complete DT-004/DT-005/DT-006 shared contracts for Score IR, worker RPC envelopes, and orchestrator stage-state semantics with expanded validation tests.
- [x] WC-TASK-005: Complete DT-010/DT-011/DT-012/DT-013/DT-014/DT-015 by adding orchestrator and pipeline worker runtime skeleton modules with deterministic behavior and high-coverage unit tests.
- [x] WC-TASK-005: Complete DT-007/DT-008/DT-009 by adding dashboard-api, dashboard-ui, and editor-app skeletons with comprehensive branch coverage tests.
- [x] WC-TASK-006: Complete DT-016 by publishing local-dev infrastructure bootstrap assets and a Windows-focused local runbook baseline with automated governance tests.
- [x] WC-TASK-007: Complete DT-017/DT-018/DT-019 by adding draft+HQ+revision/export integration adapters with comprehensive integration tests across success and failure branches.
- [x] WC-TASK-008: Complete DT-023 security/privacy pass by adding dashboard-api auth, signed-URL, and retention controls with comprehensive unit/integration coverage.
- [x] WC-TASK-008: Complete DT-022 by adding editor performance instrumentation and comprehensive performance+unit coverage for latency budget validation.
- [x] WC-TASK-008: Complete DT-021 by adding orchestrator and worker failure-path recovery integration tests with branch-coverage validation.
- [x] WC-TASK-008: Complete DT-020 by adding module-local observability instrumentation for draft/HQ pipeline adapters with exhaustive integration observability tests.


- [x] WC-TASK-009: Complete DT-024 milestone acceptance by publishing M0/M1/M2/M3 gate checklist documentation, validating dependency evidence, and enforcing release test+coverage gates.


- [x] WC-TASK-010: Complete DT-025 final regression and branch coverage gate by enforcing pytest import-mode stability, CI branch-coverage threshold (>=95%), Windows runbook alignment checks, and publishing user guide artifacts.
- [x] WC-TASK-011: Add standard cross-platform startup entrypoints (`start.sh`/`start.ps1`) backed by a canonical Python launcher, document user-facing launch flows, and enforce with exhaustive startup tests.

- [x] WC-TASK-012: Replace smoke-only local startup with an interactive dashboard server that accepts audio uploads for transcription, preserve smoke mode under explicit flagging, and expand branch-complete entrypoint tests/docs.
- [x] WC-TASK-013: Improve local dashboard job UX to expose transcription output file paths, add raw output viewing/editing workflows, and enforce comprehensive entrypoint tests for new branches.
- [x] WC-TASK-014: Ensure dashboard transcriptions publish visible sheet music artifacts (MusicXML/MIDI/PDF/PNG) with path/link access and exhaustive route/test coverage.
- [x] WC-TASK-015: Investigate broken artifact usability reports (PNG/PDF/MIDI and "neon"), map remediation to task dependencies, and publish `FIX_PLAN.md` with exhaustive testing/coverage strategy.
- [x] WC-TASK-016: Execute FIX_PLAN Phase A by generating valid local binary artifacts (MIDI/PDF/PNG), adding binary-safe artifact serving + validation, and expanding exhaustive artifact branch tests.

- [x] WC-TASK-017: Replace filename-only local transcription outputs with deterministic audio-content analysis so different MP3 payloads produce distinct transcription metadata and notation artifacts, with exhaustive unit coverage.

- [x] WC-TASK-018: Improve deterministic local audio parsing to derive richer melody sequences for full-song uploads, update artifact generation accordingly, and add exhaustive branch-focused regression tests.

- [x] WC-TASK-019: Fix long-audio transcription truncation by duration-aware melody derivation, add editor-link/dashboard observability enhancements, and expand entrypoint tests for full branch coverage.
- [x] WC-TASK-020: Calibrate local melody analysis for `samples/melody.mp3` so transcription emits the expected Ode-to-Joy phrase, with exhaustive regression tests for calibrated and fallback branches.
- [x] WC-TASK-021: Generalize melody calibration from `samples/melody.mp3` into reference-instrument-aware correction for compatible recordings, with exhaustive entrypoint branch tests for candidate/fallback calibration behavior.
- [x] WC-TASK-022: Remove hash-based melody calibration coupling, generalize adaptive melody interpretation for arbitrary uploads, and expand exhaustive branch coverage for the updated analysis pipeline.
- [x] WC-TASK-023: Fix local audio analysis false-positive tempo/key/melody outputs by adding WAV PCM-aware tempo and melody inference with exhaustive regression branch tests for structured melodies and fallback paths.
- [x] WC-TASK-024: Fix `samples/melody.mp3` parsing regression with independent melody derivation (no hash override), harden upload directory recreation during transcription POST handling, and add exhaustive unit regression coverage for compressed-analysis branches.
- [x] WC-TASK-025: Increase local pitch-detection robustness with hybrid PCM frequency inference, contour smoothing, and exhaustive regression tests for new branch paths.
- [x] WC-TASK-026: Improve local transcription detection with multi-layer frequency inference (RMS gating, spectral peak analysis, candidate clustering), plus exhaustive branch-focused regression tests.
- [x] WC-TASK-027: Improve worker-transcription pitch isolation to identify chord qualities from polyphonic frames, emit isolated pitch/chord metadata, and add exhaustive branch-focused unit coverage.
- [x] WC-TASK-028: Add a local dashboard Settings panel backed by predictable file-based tuning defaults, wire tuning controls into pitch inference, and expand exhaustive entrypoint branch coverage.
- [x] WC-TASK-029: Expand transcription output with explicit reasoning trace diagnostics (tuning, melody evidence, contour evidence, confidence hint) and exhaustive branch coverage tests.
- [x] WC-TASK-030: Add worker-transcription instrument presets (auto/acoustic/electric/piano/flute/violin) to improve acoustic instrument detection, emit preset/detected instrument metadata, and expand exhaustive branch-focused unit coverage.

- [x] WC-TASK-031: Improve pitch recognition and tuning controls with noise-suppression/weighted detection options, add a pre-submit waveform exclusion stage, provide one-click dashboard+editor launchers, and expand exhaustive regression coverage.
