# Shared_Contracts_Spec.md

## Scope
Cross-module contracts for data models, API schemas, worker payloads, and score IR.

## Responsibilities
- Versioned interfaces and schema governance.
- Backward compatibility checks for evolving contracts.
- Canonical definitions for Project/AudioAsset/Job/StageRun/ScoreRevision.

## Quality Gates
- Schema validation in CI.
- Change control notes for all breaking contract changes.
