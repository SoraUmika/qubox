# Verification Strategy

`qubox_v2` verification is organized in `qubox_v2/verification/` and focuses on:

- Schema checks
- Persistence-policy checks
- Waveform regression
- Legacy parity checks

## Principles
- Read-only verification by default.
- Deterministic outputs for CI and artifact review.
- Explicit PASS/FAIL summaries with actionable details.

## Core Modules
- `schema_checks.py`
- `persistence_verifier.py`
- `waveform_regression.py`
- `legacy_parity.py`

## CI Guidance
- Run schema checks first.
- Run targeted regression checks for changed modules.
- Persist verification reports as artifacts.
