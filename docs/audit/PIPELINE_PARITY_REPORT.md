# Orchestrator Pipeline Parity Report

Date: 2026-02-22

## Scope
Applied to:
- `QubitSpectroscopy`
- `PowerRabi`
- `T1Relaxation`
- `T2Ramsey`
- `T2Echo`
- `DRAGCalibration`
- `StorageSpectroscopy`

## Patch Fields by Experiment

| Experiment | Calibration kind | Patch fields (preview/apply via orchestrator) |
|---|---|---|
| QubitSpectroscopy | `qubit_freq` | `frequencies.<qb_el>.qubit_freq` |
| PowerRabi (`op=ref_r180`) | `pi_amp` | `pulse_calibrations.ref_r180.amplitude`, primitive family amplitudes (`x180,y180,x90,xn90,y90,yn90`), pulse params + recompile |
| T1Relaxation | `t1` | `coherence.<qb_el>.T1`, `coherence.<qb_el>.T1_us`, optional `coherence.<qb_el>.qb_therm_clks` |
| T2Ramsey | `t2_ramsey` | `coherence.<qb_el>.T2_ramsey`, `coherence.<qb_el>.T2_star_us`, optional `frequencies.<qb_el>.qubit_freq` correction |
| T2Echo | `t2_echo` | `coherence.<qb_el>.T2_echo`, `coherence.<qb_el>.T2_echo_us` |
| DRAGCalibration | `drag_alpha` | `pulse_calibrations.<pulse>.drag_coeff` for ref/primitive family, pulse recompile |
| StorageSpectroscopy | `storage_freq` | `frequencies.<st_el>.qubit_freq`, `frequencies.<st_el>.kappa` |

## Unit Conventions

- Frequency reporting in analysis metrics: **MHz**
  - `f0_MHz`, `f_storage_MHz`, `f_det_MHz`
- Time reporting in analysis metrics: **us**
  - `T1_us`, `T2_star_us`, `T2_echo_us`
- Internal fit/state values preserved in native units where required by existing models (e.g., Hz/ns paths), with explicit converted metrics added for user-facing parity.

## Legacy-Parity Notes

- `T1Relaxation`, `T2Ramsey`, `T2Echo` continue to fit/plot on `Re(S)` (not `|S|`).
- Sign-sensitive Ramsey correction is optional and configurable via `freq_correction_sign` (default `-1.0`) to match legacy convention.
- DRAG workflow keeps Yale zero-crossing method and symmetric alpha sweep behavior.

## State-Mutation Policy

- Experiment `analyze()` methods in scope now emit patch intent metadata (`proposed_patch_ops`) and `calibration_kind`.
- Patch application is orchestrator-only (`run_analysis_patch_cycle(..., apply=False)` + `apply_patch(..., dry_run=False)`).
- No direct calibration/pulse/macro/config commits are required in notebook workflow for these steps.

## Persistence Policy

- Artifact persistence remains routed through orchestrator policy (`split_output_for_persistence`), keeping shot-level arrays out of persisted artifacts.

## Deviations from Legacy

- None intentional in fit models/sign conventions/derived definitions for scoped experiments.
- Workflow changed from inline mutation to explicit preview/commit patch cycle by design.
