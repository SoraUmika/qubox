# Calibration + Readout + Fock-Resolved Pipeline Stabilisation

## Verification Report

This document describes the changes made to stabilise the qubox_v2 calibration,
readout, and Fock-resolved experiment pipelines. Each bug fix and robustness
upgrade is listed with the rationale, affected files, and verification steps.

---

## A. Mixer Calibration DB Write (PermissionError on Windows)

### Root Cause

`ManualMixerCalibrator._write_db()` used `pathlib.Path.replace()` after writing
to a temporary file created by `tempfile.NamedTemporaryFile`. On Windows, the
target file can be locked by antivirus scanners or background processes, causing
an intermittent `PermissionError`. Additionally, `_apply_iq_correction()` was
writing the full JSON database on **every grid point** during `scan_2d`, causing
hundreds of unnecessary disk writes.

### Changes

| File | Change |
|------|--------|
| `qubox_v2/calibration/mixer_calibration.py` | `_write_db()` rewritten to use `tempfile.mkstemp()` + `os.fdopen()` + `_replace_with_retry()` with exponential backoff (max 5 attempts) |
| | New `_replace_with_retry()` static method handles Windows `PermissionError` |
| | New `_get_db()` / `_db_cache` in-memory cache avoids redundant reads |
| | New `_write_scratch_db()` writes trial values to `.scratch.json` |
| | New `_cleanup_scratch()` removes scratch file on completion |
| | `write_db_mode` config field: `"final_only"` (default), `"per_stage"`, `"per_point"` |
| | `scan_2d` and `minimizer` pass `write_db=False` through to `_apply_iq_correction` during search |

### Verification

1. **Windows atomic replace**: The `_replace_with_retry()` loop runs up to 5
   attempts with exponential backoff (~1.6 s total). Confirm no
   `PermissionError` crashes during long calibrations.
2. **Reduced I/O**: With `write_db_mode="final_only"` (the default), the
   canonical database is written only once at the end. Verify via file
   modification timestamps.
3. **Scratch file cleanup**: After `scan_2d` completes, the `*.scratch.json`
   file must not remain on disk.
4. **Backward compatibility**: `save_to_db=False` still prevents any canonical
   DB writes. `save_to_db=True` preserves existing behaviour.

---

## B. ReadoutGEDiscrimination Rotated Weights Validation

### Root Cause

`ReadoutGEDiscrimination.analyze()` computed rotated integration weights and
called `pulse_mgr.update_integration_weights()`, but there was **no post-check**
to verify the weights were:
1. Actually stored in the PulseOperationManager
2. Referenced by the measurement pulse mapping
3. Present in the compiled QM config

Silent failures (e.g. wrong element name, missing pulse mapping) caused
subsequent experiments to use stale or default weights.

### Changes

| File | Change |
|------|--------|
| `qubox_v2/experiments/calibration/readout.py` | `run()` accepts `apply_rotated_weights: bool = True` parameter |
| | `analyze()` checks flag — logs "computed AND applied" vs "computed but NOT applied" |
| | `analyze()` calls `verify_rotated_weights()` after applying and stores validation in metadata |
| | New `verify_rotated_weights()` method validates weights in store, mapping, and compiled config |

### Verification

1. **Flag test**: Call `run(apply_rotated_weights=False)` — confirm weights are
   computed but NOT written to POM.
2. **Validation dict**: After `analyze()`, check
   `analysis.metadata["rotated_weights_validation"]["all_valid"]` is `True`.
3. **Failure case**: Temporarily corrupt the element name — `verify_rotated_weights()`
   should return `all_valid=False` with descriptive error strings.

---

## C. Fock-Resolved Displacement Pulses

### Root Cause

Fock-resolved experiments (`FockResolvedT1`, `FockResolvedRamsey`,
`FockResolvedPowerRabi`) generate QUA programs referencing `disp_n0`, `disp_n1`,
etc. on the storage element. These operations must be registered in the
`PulseOperationManager` **before** program compilation. There was no automatic
generation path and no fail-fast validation — the result was a cryptic
`KeyError` deep inside the QUA compiler.

### Changes

| File | Change |
|------|--------|
| `qubox_v2/tools/generators.py` | New `ensure_displacement_ops()` — generates `disp_n{k}` control pulses from calibrated storage parameters |
| | New `validate_displacement_ops()` — returns list of missing op names for an element |
| `qubox_v2/experiments/cavity/fock.py` | All three experiment `run()` methods now call `validate_displacement_ops()` with fail-fast `RuntimeError` including remediation instructions |
| `notebooks/post_cavity_experiment.ipynb` | New cell 8.4b registers displacement pulses before Fock-resolved section |

### Verification

1. **Happy path**: Run the notebook cell 8.4b then `FockResolvedT1.run()` —
   should succeed without errors.
2. **Fail-fast**: Skip cell 8.4b and call `FockResolvedT1.run()` — must raise
   `RuntimeError` listing the missing ops and showing the fix command.
3. **Override**: Pass `fock_disps=["disp_n0"]` explicitly to verify the
   user-provided list is validated, not just the auto-generated one.

---

## D.1. Preflight Validation

### Purpose

Catch common session configuration problems **before** running experiments,
replacing ad-hoc checks scattered across experiment classes.

### Changes

| File | Change |
|------|--------|
| `qubox_v2/core/preflight.py` | New module with `preflight_check(session)` function |
| `notebooks/post_cavity_experiment.ipynb` | New cell 1.1 runs preflight after `session.open()` |

### Checks Performed

| Check | Severity | Description |
|-------|----------|-------------|
| `qm_connection` | ERROR | QM instance is opened |
| `element_{name}` | ERROR | Required elements (qubit, readout, ...) exist in config |
| `op_{el}_{op}` | ERROR | Baseline operations (const, ...) are mapped |
| `readout_weights` | WARN | Readout integration weights are present |
| `calibration_file` | WARN | Calibration JSON is readable |
| `experiment_path` | ERROR | Experiment directory is writable |
| `measure_config` | WARN | measureConfig.json exists |

### Verification

1. Call `preflight_check(session)` after `open()` — all checks should pass on
   a properly configured system.
2. Set `session.hardware.qm = None` then call — `qm_connection` must fail.
3. Pass `require_elements=["nonexistent"]` — must report element missing.

---

## D.2. Logging & Artifacts

### Purpose

Provide reproducible experiment records by saving config snapshots and run
summaries to a dedicated `artifacts/` directory.

### Changes

| File | Change |
|------|--------|
| `qubox_v2/core/artifacts.py` | New module with `save_config_snapshot()` and `save_run_summary()` |
| `notebooks/post_cavity_experiment.ipynb` | Cell 1.1 saves initial config snapshot |

### Artifact Contents

**Config Snapshot** (`config_snapshot_*.json`):
- Timestamp and tag
- Element names + operations (from QM config)
- POM element-op mappings (permanent + volatile stores)
- cQED attributes summary (frequencies, coherent params)
- Calibration store metadata

**Run Summary** (`run_summary_*.json`):
- Timestamp, tag, experiment path
- Result metadata (success, n_avg, execution time, output keys)
- Optional extra key-value pairs

### Verification

1. Run `save_config_snapshot(session)` — check that
   `<experiment_path>/artifacts/config_snapshot_*.json` is created and valid JSON.
2. Run `save_run_summary(session, result)` after an experiment — verify the summary
   file contains correct output keys.

---

## Files Modified (Complete List)

| File | Status |
|------|--------|
| `qubox_v2/calibration/mixer_calibration.py` | Modified — Bug A |
| `qubox_v2/experiments/calibration/readout.py` | Modified — Bug B |
| `qubox_v2/tools/generators.py` | Modified — Bug C (new functions) |
| `qubox_v2/experiments/cavity/fock.py` | Modified — Bug C (fail-fast) |
| `qubox_v2/core/preflight.py` | **New** — Section D.1 |
| `qubox_v2/core/artifacts.py` | **New** — Section D.2 |
| `notebooks/post_cavity_experiment.ipynb` | Modified — new cells |
| `qubox_v2/docs/VERIFICATION.md` | **New** — this document |
