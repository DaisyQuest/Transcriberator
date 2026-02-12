# FIX_PLAN.md

## 1) Problem Statement (Current State)

Users report that exported artifacts are unusable:
- PNG does not render.
- PDF does not open.
- MIDI does not import/play.
- "neon" is broken (term currently ambiguous in repo terminology; likely either notation rendering or a UI-related artifact surface).

The current codebase confirms this is expected with the existing skeleton behavior:
- Local dashboard artifact generation writes **text placeholders** for `.mid`, `.pdf`, and `.png` instead of valid binary files.
- Artifact download serving always reads files as UTF-8 text and appends `charset=utf-8`, which corrupts/invalidates binary artifact delivery.
- Pipeline adapters and worker outputs mostly generate URI strings (contract placeholders), not production-grade rendered artifacts.

## 2) Root Cause Summary

### RC-1: Invalid artifact file contents
`infrastructure/local-dev/start_transcriberator.py::_build_sheet_artifacts` creates:
- MIDI as plain text (`"MIDI placeholder..."`),
- PDF as plain text (`"%PDF-1.4 ..."` only header-like fragment),
- PNG as plain text (`"PNG placeholder..."`).

These are not valid media files and will fail in viewers/DAWs.

### RC-2: Incorrect binary serving path
`_serve_artifact_output` reads files with `read_text(...).encode(...)` and returns `Content-Type: <type>; charset=utf-8` for all artifacts.

Binary artifacts must be served via bytes (`read_bytes`) without text transcoding.

### RC-3: Export pipeline is still scaffold-level for artifacts
Adapters in orchestrator/editor/dashboard paths expose references/URIs but do not ensure real rendering/export jobs are executed.

### RC-4: Missing fidelity tests
Current tests validate that files/links exist, but do not validate format integrity (PNG signature, PDF structure, MIDI header/chunks, etc.).

### RC-5: Ambiguous "neon" failure report
No explicit "neon" component/keyword exists in current repository. We need a reproducible definition from telemetry/UI path while implementing broad artifact integrity checks.

## 3) Dependency Mapping to Development_Tasks.md

To respect dependency order and ownership boundaries:

1. **DT-016 track (infrastructure/local dev)**
   - Fix local artifact generation + serving behavior first, because user-visible local failures are immediate.

2. **DT-015 / DT-017 / DT-019 track (workers + orchestration + export adapters)**
   - Replace URI-only scaffolding in export stages with executable artifact-producing behavior (or clear adapter handoff to real exporter).

3. **DT-023 track (dashboard API security/privacy)**
   - Ensure signed URLs/content headers work correctly for binary payloads and support retention-safe download workflows.

4. **DT-024/DT-025 gates (release + regression/coverage)**
   - Add strict format-validation tests and enforce branch coverage for all added failure/success branches.

## 4) Required Fixes (Implementation Plan)

## Phase A — Local Artifact Correctness (highest urgency)

### A1. Generate valid binary artifacts in local-dev dashboard
Update `infrastructure/local-dev/start_transcriberator.py`:
- Produce valid MIDI bytes (minimum compliant header + track chunk).
- Produce valid PDF bytes (real PDF document payload, not text placeholder).
- Produce valid PNG bytes (real PNG image bytes with proper signature/chunks).
- Keep MusicXML as XML text, but validate parseability before write.

Implementation options:
- Preferred: use deterministic helper builders in-module (no heavy runtime dependencies).
- Acceptable: use lightweight libs if already allowed and stable for Windows local dev.

### A2. Serve artifacts as bytes with correct headers
Update artifact response path:
- Use `Path.read_bytes()`.
- Do not append charset for binary media types.
- Send explicit `Content-Type` and optionally `Content-Disposition` (`inline` for PNG/PDF, `attachment` for MIDI/XML if desired).
- Add cache headers if needed for deterministic local UX.

### A3. Add defensive artifact validation before response
Before serving, validate known magic signatures:
- PNG starts with `\x89PNG\r\n\x1a\n`.
- PDF starts with `%PDF-` and has `%%EOF` terminator.
- MIDI starts with `MThd` and has expected chunk lengths.
If invalid, return clear 500-level actionable error message.

## Phase B — Pipeline/Export Robustness Beyond Local Dashboard

### B1. Replace placeholder-only export semantics in adapters
For `modules/editor-app/revision_export_adapter.py`, `modules/orchestrator/draft_pipeline_adapter.py`, and `modules/worker-engraving/worker_engraving_skeleton.py`:
- Introduce explicit exporter interface contract that can materialize artifacts (not only URIs).
- Preserve replaceability (FS-064/FS-068) with a provider abstraction (`ArtifactRenderer` / `ArtifactStore`).
- Ensure stage F/G writes durable artifacts and returns metadata including byte size, checksum, and MIME type.

### B2. Stage checkpoint + metadata integrity
For orchestration/export handoff:
- Add checksum/version metadata tags (FS-065).
- Persist stage run artifact metadata in a checkpoint-friendly structure (FS-044/FS-055).

### B3. Clarify/resolve "neon"
Add a reproducible issue definition path:
- Search telemetry/UI labels and user-facing docs for intended term.
- If "neon" == notation/preview renderer, include it as a validated export surface in the same integrity pipeline.
- If separate component, create dedicated adapter contract + tests.

## Phase C — API Download/Delivery Hardening

### C1. Binary-safe signed URL delivery contract
In dashboard API adapter/service path:
- Confirm content-type propagation and signature validation for all artifact types.
- Ensure signed links resolve to binary-safe responses.

### C2. Error contracts
Return typed, actionable errors when:
- Artifact missing,
- Artifact checksum mismatch,
- Signature expired/invalid,
- Unsupported artifact type.

## 5) Test Plan (Extremely Thorough)

Target: **full branch coverage** for all modified paths (minimum policy: >=95%; requested: strive for 100% on touched code).

### Unit tests
1. `tests/unit/test_local_entrypoints.py`
   - Validate generated artifact bytes are format-correct:
     - PNG signature/chunk presence,
     - PDF header + EOF,
     - MIDI `MThd` + valid track chunk,
     - MusicXML parseable and contains expected score nodes.
   - Validate binary serving path returns exact bytes and content type (no charset for binary).
   - Validate all artifact error branches:
     - missing job,
     - missing artifact,
     - deleted file,
     - invalid/corrupt artifact bytes.

2. Add focused unit tests for new artifact helper/builders (if extracted).
   - Positive + negative branch tests for each validator.

3. Update API security tests if signed URL semantics/content headers change.

### Integration tests
1. Extend `tests/integration/test_revision_exports.py`:
   - End-to-end export flow yields downloadable payloads that pass integrity checks.
   - Include include/exclude PNG branch and malformed revision branch.

2. Add artifact playback/openability checks:
   - Attempt parsing/opening generated MIDI/PDF/PNG via lightweight validators (or deterministic structural checks).

3. Add "neon" reproduction test once component is identified.

### Performance/observability tests
1. Ensure added validation does not regress dashboard responsiveness notably.
2. Add metrics/assertions for artifact generation and download failures (observability coverage).

### Coverage gates
- Run branch coverage with threshold >=95% globally.
- Add per-module expectation for touched files aiming at ~100% branch coverage.

## 6) Acceptance Criteria

A fix is complete when all are true:
1. Downloaded PNG opens in standard image viewer.
2. Downloaded PDF opens in standard PDF viewer.
3. Downloaded MIDI imports/plays in at least one common DAW/player.
4. "Neon" issue is either fixed or decomposed into a separate reproducible tracked fix with explicit owner/tests.
5. Automated tests assert binary integrity and failure handling branches.
6. Coverage gate passes with >=95% branch coverage and no regressions in existing suites.

## 7) Proposed Execution Order (Single PR vs. Split)

Recommended split to reduce risk:
1. **PR-1:** Phase A local-dev artifact generation/serving + tests.
2. **PR-2:** Phase B export pipeline materialization + metadata/checkpointing + tests.
3. **PR-3:** Phase C API delivery hardening + signed-link/content contract tests.
4. **PR-4 (if needed):** "Neon" targeted remediation once exact component is confirmed.

If urgent, PR-1 can be shipped immediately to resolve user-facing broken downloads while deeper pipeline work continues.
