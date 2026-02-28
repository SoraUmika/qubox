# Pulse Spec Schema

This document defines the declarative pulse specification contract used by `pulse_specs.json`.

## Goal
Represent pulse intent declaratively so waveform generation is reproducible and migration-friendly.

## Top-Level Keys
- `schema_version`
- `specs`
- `integration_weights`
- `element_operations`

## Invariants
- `rotation_derived` entries must reference an existing `reference_spec`.
- Integration weight segmented lengths must be divisible by 4.
- Element operation mappings must reference defined specs.

## Migration Notes
- Legacy `pulses.json` may be converted via `qubox_v2.migration.pulses_converter`.
- Unknown or non-reconstructible waveforms may be preserved as fallback blobs.
