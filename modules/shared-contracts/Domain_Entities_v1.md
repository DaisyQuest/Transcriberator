# Domain_Entities_v1.md

## Purpose
This document defines canonical v1 shared contracts for:
- `Project`
- `AudioAsset`
- `Job`
- `StageRun`
- `ScoreRevision`

These contracts satisfy DT-003 and are designed as frozen shared interfaces for downstream modules.

## Versioning
- Contract family: `shared-contracts/domain-entities`
- Current version: `v1`
- Status: `frozen for downstream skeleton implementation`

## Entities

### Project
Represents a user-owned transcription workspace.

Required fields:
- `id` (string UUID)
- `ownerId` (string)
- `name` (string, 1..200 chars)
- `createdAt` (RFC3339 timestamp)
- `updatedAt` (RFC3339 timestamp)

Optional fields:
- `description` (string, <= 2000 chars)
- `tags` (string[])

### AudioAsset
Represents uploaded and normalized audio plus technical metadata.

Required fields:
- `id` (string UUID)
- `projectId` (string UUID)
- `sourceBlobUri` (string URI)
- `normalizedBlobUri` (string URI)
- `format` (`mp3` | `wav` | `flac`)
- `durationMs` (integer > 0)
- `sampleRateHz` (integer > 0)
- `channels` (integer > 0)
- `createdAt` (RFC3339 timestamp)

Optional fields:
- `loudnessLufs` (number)
- `peakDbfs` (number)

### Job
Represents one pipeline execution against a project/audio pair.

Required fields:
- `id` (string UUID)
- `projectId` (string UUID)
- `audioAssetId` (string UUID)
- `mode` (`draft` | `hq`)
- `status` (`queued` | `running` | `succeeded` | `failed` | `cancelled`)
- `pipelineVersion` (string)
- `configVersion` (string)
- `createdAt` (RFC3339 timestamp)
- `updatedAt` (RFC3339 timestamp)

Optional fields:
- `requestedBy` (string)
- `startedAt` (RFC3339 timestamp)
- `finishedAt` (RFC3339 timestamp)

### StageRun
Represents one execution attempt of a pipeline stage for a job.

Required fields:
- `id` (string UUID)
- `jobId` (string UUID)
- `stageName` (`decode_normalize` | `source_separation` | `tempo_map` | `transcription` | `quantization_cleanup` | `notation_generation` | `engraving`)
- `attempt` (integer >= 1)
- `status` (`queued` | `running` | `succeeded` | `failed` | `skipped`)
- `inputArtifactUris` (string[] URI)
- `outputArtifactUris` (string[] URI)
- `createdAt` (RFC3339 timestamp)
- `updatedAt` (RFC3339 timestamp)

Optional fields:
- `errorCode` (string)
- `errorSummary` (string)
- `startedAt` (RFC3339 timestamp)
- `finishedAt` (RFC3339 timestamp)

### ScoreRevision
Represents editable score state and lineage over time.

Required fields:
- `id` (string UUID)
- `projectId` (string UUID)
- `parentRevisionId` (string UUID or null)
- `jobId` (string UUID)
- `musicXmlUri` (string URI)
- `midiUri` (string URI)
- `pdfUri` (string URI)
- `pngUri` (string URI)
- `irVersion` (string)
- `createdAt` (RFC3339 timestamp)

Optional fields:
- `notes` (string)
- `isCheckpoint` (boolean)

## Schema Mapping
Each entity has a machine-validated JSON Schema in `schemas/v1/`:
- `project.schema.json`
- `audio_asset.schema.json`
- `job.schema.json`
- `stage_run.schema.json`
- `score_revision.schema.json`
