# Schema Versioning

This document defines schema ownership and versioning policy for configuration and calibration files used by `qubox_v2`.

## Owned Schemas
- `hardware.json`
- `calibration.json`
- `pulse_specs.json` / `pulses.json` compatibility input
- `measureConfig.json`
- `devices.json`

## Versioning Rules
- Bump schema version on breaking structural change.
- Provide backward-compatible migration when practical.
- Keep migrations idempotent and safe to re-run.
- Validate on load; fail fast on incompatible major versions.

## Runtime Policy
- `SessionState` and `ExperimentContext` should capture schema version metadata.
- `CalibrationStore` is the canonical owner for calibration schema upgrades.
- Verification checks must validate schema compatibility before execution.
