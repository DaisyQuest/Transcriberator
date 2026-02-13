# worker-transcription-robustness-hardening work description

## Summary
Implemented a robustness hardening pass for `modules/worker-transcription/worker_transcription_skeleton.py` with stronger deterministic preprocessing and scoring resilience:

1. Added frame normalization to sort and deduplicate per-frame pitches before all downstream analysis.
2. Routed chord identification, event counting, pitch isolation, and instrument detection through normalized frames for noise resistance.
3. Added harmonic-density estimation and integrated it into confidence scoring to better differentiate sparse versus harmonically-rich passages.
4. Added deterministic tie-breaking in auto instrument detection using profile pitch span.
5. Added helper utility for instrument profile span introspection.

## Testing
Expanded and hardened `tests/unit/test_worker_transcription_chords.py` with comprehensive branch-focused coverage of:

- normalization behavior and deduplication impact,
- harmonic-density confidence path,
- empty-frame instrument detection helper path,
- zero-frame confidence guard branch,
- harmonic-density estimator branches,
- profile pitch-span helper,
- existing chord/instrument/validation regression paths.

Ran full repository tests to ensure no regressions.
