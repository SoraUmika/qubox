# Pulse Definitions Migration Plan

## Current state (inspected)
- `config/pulses.json` currently stores concrete resources: `waveforms`, `pulses`, `integration_weights`, `element_operations`.
- Many control pulses are stored as raw arbitrary sample arrays (large JSON, brittle to manual edits).
- `PulseOperationManager.from_json()` previously loaded this raw format directly.

## New schema (backward compatible)
- `pulses.json` now supports additional top-level keys:
  - `_schema_version: 2`
  - `pulse_definitions: { ... }`
- Existing raw keys remain valid and continue to load unchanged.
- New `pulse_definitions` are high-level parametric descriptions; concrete waveforms are materialized deterministically.

### Supported definition types
- `drag_gaussian`
  - required: `element`, `op`
  - typical params: `amplitude`, `length`, `sigma`, `drag_coeff`, `anharmonicity`
- `constant`
  - required: `element`, `op`
  - typical params: `amplitude_I`, `amplitude_Q`, `length`

## Loader behavior
- Old files (no `_schema_version`, no `pulse_definitions`) load exactly as before.
- New files with `pulse_definitions`:
  1. Load raw resources if present.
  2. Load `pulse_definitions`.
  3. Materialize definitions into concrete pulse/waveform entries (non-destructive unless override requested).

## Determinism guarantees
- `drag_gaussian` uses fixed numerical generation from stored scalar params.
- Given identical params, generated I/Q arrays are identical across restarts.
- Recommended to store all physically relevant params in each definition (`length`, `sigma`, `drag_coeff`, `anharmonicity`).

## Rollout steps
1. Keep existing `pulses.json` as source of truth (raw format still valid).
2. Start writing new/updated primitive pulses via `set_pulse_definition(...)`.
3. Save with `session.save_pulses()` so `pulse_definitions` is persisted.
4. Verify restart behavior (`SessionManager.open()` loads, materializes, and compiles).
5. Optionally reduce raw array footprint later by removing regenerated raw entries in a controlled cleanup.

## Notes for notebook workflow
- After modifying primitive pulses, run:
  - `session.burn_pulses()`
  - `session.save_pulses()`
- This ensures updates survive kernel restart and session reopen.
