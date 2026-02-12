# Score_IR_v1.md

## Purpose
Defines the canonical shared **Score IR v1** contract required by DT-004. The IR is richer than MIDI while remaining simpler than full MusicXML.

## Versioning
- Contract family: `shared-contracts/score-ir`
- Current version: `v1`
- Status: `frozen for downstream skeleton implementation`

## Schema Location
- `modules/shared-contracts/schemas/v1/score_ir.schema.json`

## Top-Level Shape
Required top-level fields:
- `irVersion` (`"v1"`)
- `scoreId` (UUID)
- `globalMaps` (tempo/key/time-signature maps)
- `parts` (array of musical parts)

Optional top-level fields:
- `sourceJobId` (UUID)
- `title` (1..300 chars)

## Structure
- `globalMaps`
  - `timeSignatures[]` entries by `measureIndex`.
  - `tempoMap[]` entries by absolute `tick`.
  - `keySignatures[]` entries by `measureIndex`.
- `parts[]`
  - `partId`, `name`, optional `instrument`.
  - `measures[]`
    - `measureIndex`, `startTick`, `durationTicks`.
    - `voices[]`
      - `voiceId`
      - `events[]` where each event is one of:
        - `note` (`tick`, `durationTicks`, `pitchMidi`, `velocity`, optional tie)
        - `rest` (`tick`, `durationTicks`)

## Validation Rules
1. **IR version lock:** `irVersion` must be exactly `v1`.
2. **No unknown fields:** all objects use `additionalProperties: false`.
3. **Map minimums:** `timeSignatures`, `tempoMap`, and `keySignatures` must each have at least one event.
4. **Musical ranges:**
   - `pitchMidi` is `0..127`.
   - `velocity` is `1..127`.
   - `bpm` is greater than 1.
5. **Timeline monotonicity (semantic rule):** within each `voice.events[]`, producers should emit events in ascending `tick` order.
6. **Measure consistency (semantic rule):** events in a measure should not exceed `startTick + durationTicks` unless represented via ties crossing measures.

## Example Payloads
- Valid example: `modules/shared-contracts/examples/v1/score_ir_valid_minimal.json`
- Intentionally invalid example (for documentation/testing): `modules/shared-contracts/examples/v1/score_ir_invalid_unknown_event.json`

## Compatibility Notes
- Adding a new optional event attribute is a **minor** change.
- Adding a new required event field or changing event discriminators is a **major** change.
- Existing event discriminator values (`note`, `rest`) are frozen for v1.
