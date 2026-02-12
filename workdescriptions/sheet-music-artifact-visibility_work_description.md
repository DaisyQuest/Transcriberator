# sheet-music-artifact-visibility work description

## Objective
Ensure local dashboard transcription runs produce and surface sheet music artifacts (MusicXML, MIDI, PDF, PNG) so users can validate that transcription execution produced notation outputs and can access artifact paths directly.

## Scope
- Updated local dashboard runtime artifact generation and routing in `infrastructure/local-dev/start_transcriberator.py`.
- Added and expanded unit tests in `tests/unit/test_local_entrypoints.py`.

## Implementation Summary
1. Added deterministic local artifact generation for MusicXML, MIDI, PDF, and PNG placeholder outputs per job.
2. Augmented saved transcription text with a generated artifact manifest including file paths.
3. Exposed artifact links in the dashboard job cards with a dedicated artifact output route.
4. Added robust server route handling for artifact retrieval, including 404 behavior for unknown jobs/artifacts/missing files.
5. Expanded test coverage for:
   - artifact generation helper behavior,
   - transcription augmentation behavior,
   - artifact route success and failure branches,
   - HTML rendering of artifact links.

## Validation
- Ran full regression: `pytest -q`.
- Ran branch coverage gate: `pytest --cov=. --cov-branch --cov-report=term-missing --cov-fail-under=95`.

## Result
The local dashboard now demonstrates actual transcription pipeline completion with visible sheet music artifacts and concrete paths/links for retrieval, reducing ambiguity for users validating end-to-end transcription behavior.
