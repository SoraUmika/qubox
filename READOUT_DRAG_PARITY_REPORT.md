# DRAG + Readout Full Pipeline Parity Report

## Scope
Compared and aligned behavior across:
- `post_cavity_experiment.ipynb`
- `post_cavity_experiment_legacy.ipynb`
- `qubox_legacy/cQED_experiments.py`
- `qubox_v2/experiments/calibration/gates.py`
- `qubox_v2/experiments/calibration/readout.py`
- `qubox_v2/programs/cQED_programs.py`

## Part I — DRAG Calibration Parity

### Verified parity points
1. **Pulse construction order**
   - Temporary pulses are generated and registered in the same order: `x180_tmp`, `y180_tmp`, `x90_tmp`, `y90_tmp`.
2. **Sign and IQ conventions**
   - `z = I + 1jQ` construction and `pi/2` complex rotation for Y pulses are consistent.
   - QUA matrix scaling convention in `drag_calibration_YALE` is identical:
     - `play(x180 * amp(1,0,0,a), qb_el)`
     - `play(y90  * amp(a,0,0,1), qb_el)`
     - `play(y180 * amp(a,0,0,1), qb_el)`
     - `play(x90  * amp(1,0,0,a), qb_el)`
3. **Sweep and fit semantics**
   - Symmetric alpha sweep is caller-defined and unchanged.
   - Extraction uses zero-crossings of `Re(S1)-Re(S2)` first, fallback to argmin of absolute difference.
4. **Update policy**
   - No automatic write-back unless explicitly requested (`update_calibration=True`).
   - Guarded commit remains in place.

### Clarification on “no pre-applied DRAG”
Legacy parity uses a basis waveform where derivative components are present in temporary pulse definitions and the effective DRAG term is controlled during sweep by QUA amp-matrix coefficients. This remains unchanged to preserve exact parity.

## Part II — Readout Full Pipeline Refactor

## Implemented unified object
- Added **`CalibrationReadoutFull`** in `qubox_v2/experiments/calibration/readout.py`.
- This is a config-first wrapper over `CalibrateReadoutFull`:
  - `CalibrationReadoutFull.run(readoutConfig=ReadoutConfig(...))`
  - Rejects ad-hoc kwargs to prevent hidden behavior drift.

## Config schema (`ReadoutConfig`) additions
Added explicit controls:
- aliases: `measure_op`, `n_samples`
- behavior: `update_weights`, `update_threshold`, `rotation_method`, `weight_extraction_method`, `histogram_fitting`, `threshold_extraction`, `overwrite_policy`
- persistence: `save_to_config`, `save_calibration_json`, `save_calibration_db`, `save_measure_config`, `save_session_state`

Validation enforces parity-safe values for:
- `rotation_method='optimal'`
- `weight_extraction_method='legacy_ge_diff_norm'`
- `histogram_fitting='two_state_discriminator'`
- `threshold_extraction='legacy_discriminator'`

## Flow semantics preserved
Execution order remains:
1. `ReadoutWeightsOptimization` (optional)
2. `ReadoutGEDiscrimination`
3. `ReadoutButterflyMeasurement`

No change was made to physics algorithms, matrix conventions, thresholds, or F/Q/V computation logic.

## Save behavior (explicit)
When `save_to_config=True`, pipeline now applies explicit destination control:
- `save_calibration_json=True` → `calibration.save()`
- `save_measure_config=True` → `config/measureConfig.json`
- `save_session_state=True` → session `save_pulses()` and `save_attributes()`
- `save_calibration_db=True` → currently logged as unsupported for readout pipeline (see deviations)

## Notebook integration
`notebooks/post_cavity_experiment.ipynb` Section 6.4 now drives full calibration through:
- `readoutConfig = ReadoutConfig(...)`
- `CalibrationReadoutFull(session).run(readoutConfig=readoutConfig)`

It still prints parity diagnostics, confusion matrix, transition matrix, and `GE/100 - F`.

## Unavoidable deviations
1. **`calibration_db.json` write path**
   - Readout calibration pipeline does not produce Octave mixer calibration artifacts, so direct `calibration_db.json` write is not executed.
   - Behavior is explicit: requesting `save_calibration_db=True` emits a warning and no-ops.

## Summary
- DRAG calibration workflow parity with legacy is preserved.
- Full readout flow is now explicitly config-driven through `ReadoutConfig` and `CalibrationReadoutFull`.
- Save/update behavior is explicit and non-silent, with unsupported destination behavior documented.
