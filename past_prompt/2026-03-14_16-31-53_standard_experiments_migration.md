# Prompt Log — Standard Experiments Migration

**Date:** 2026-03-14 16:31 UTC  
**Task:** Migrate 20 legacy cQED experiments into the new qubox API as the canonical standard experiment suite

---

## Original Prompt (Summary)

Migrate the legacy `cQED_programs` into the new `qubox` API. Do **not** port everything. Instead, select exactly **20 experiments** that are the most representative and standard for this codebase, and make them the canonical initial standard experiment suite of the new API.

### Requirements
- Read docs first (README.md, API_REFERENCE.md, standard_experiments.md)
- Inspect qubox architecture before making changes
- Create a clean standard-experiments layer: refactor, do not copy-paste
- Preserve physics intent and sweep semantics from legacy functions
- Use reusable building blocks (adapter pattern)
- Normalize naming and results
- Update docs, tests, and notebooks
- Generate `standard_experiments_migration_report.md`

### 20 Target Experiments
1. `readout_trace` → `readout.trace`
2. `resonator_spectroscopy` → `resonator.spectroscopy` (existing)
3. `resonator_power_spectroscopy` → `resonator.power_spectroscopy`
4. `qubit_spectroscopy` → `qubit.spectroscopy` (existing)
5. `temporal_rabi` → `qubit.temporal_rabi`
6. `power_rabi` → `qubit.power_rabi` (existing)
7. `time_rabi_chevron` → `qubit.time_rabi_chevron`
8. `power_rabi_chevron` → `qubit.power_rabi_chevron`
9. `T1_relaxation` → `qubit.t1`
10. `T2_ramsey` → `qubit.ramsey` (existing)
11. `T2_echo` → `qubit.echo`
12. `iq_blobs` → `readout.iq_blobs`
13. `all_xy` → `calibration.all_xy`
14. `drag_calibration_YALE` → `calibration.drag`
15. `readout_butterfly_measurement` → `readout.butterfly`
16. `qubit_state_tomography` → `tomography.qubit_state`
17. `storage_spectroscopy` → `storage.spectroscopy`
18. `storage_T1_decay` → `storage.t1_decay`
19. `num_splitting_spectroscopy` → `storage.num_splitting`
20. `storage_wigner_tomography` → `tomography.wigner`

---

## Result Summary

### Files Modified
- `qubox/experiments/templates/library.py` — Expanded from ~110 to ~320 lines; 7 sub-libraries, 21 template methods
- `qubox/experiments/templates/__init__.py` — Updated exports for all 8 library classes
- `qubox/backends/qm/runtime.py` — Added 16 arg_builder functions and 16 adapter entries (21 total)
- `API_REFERENCE.md` — Section 11 expanded from 5 to 20 experiment entries with full signatures
- `standard_experiments.md` — Appended canonical 20-experiment registry table
- `docs/CHANGELOG.md` — New Major entry for the migration

### Files Created
- `tests/test_standard_experiments.py` — 23 tests (22 passed, 1 skipped)
- `standard_experiments_migration_report.md` — Full migration report with mapping table, architecture decisions, validation, and future recommendations
- `past_prompt/2026-03-14_16-31-53_standard_experiments_migration.md` — This prompt log

### Architecture Decisions
- **Adapter pattern**: All 16 new experiments use `LegacyExperimentAdapter` → `_build_*_args()` → legacy class, matching existing 5 adapters
- **storage.t1_decay → FockResolvedT1**: No dedicated `StorageT1Decay` class; mapped to `FockResolvedT1` with single Fock state (physically equivalent)
- **No-sweep experiments**: `readout.trace`, `readout.iq_blobs`, `readout.butterfly`, `calibration.all_xy`, `tomography.qubit_state` use `sweep=None`
- **2D chevron experiments**: Sweeps handled internally by legacy QUA programs; range params passed through
- **Callable state_prep**: `tomography.qubit_state`, `tomography.wigner`, `storage.num_splitting` accept QUA callables (QM-backend-specific limitation documented)

### Test Results
- 22 passed, 1 skipped (adapter registry test needs QM SDK), 0 failures
- No regressions in existing tests (6 passed in `test_qubox_public_api.py`)

### 22 Experiments NOT Ported (with rationale)
See `standard_experiments_migration_report.md` for the complete list and rationale.
