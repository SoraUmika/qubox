# Current Workflow Architecture Map (qubox_v2)

## 1) Execution entry points

### Primary interactive entry
- `notebooks/post_cavity_experiment.ipynb`
  - Builds `SessionManager` and runs modular experiment classes from `qubox_v2.experiments`.

### Programmatic entry points
- `qubox_v2/experiments/session.py` → `SessionManager`
- `qubox_v2/experiments/base.py` → `ExperimentRunner` (alternate infrastructure entry)
- `qubox_v2/experiments/legacy_experiment.py` → legacy monolith (`cQED_Experiment`, backward-compat path)

### Typical execution path
1. Construct session/infrastructure (`SessionManager.__init__`).
2. Open QM + load measure macro config (`SessionManager.open`, `_load_measure_config`).
3. Instantiate experiment class (inherits `ExperimentBase`).
4. `run()` builds/executes QUA program via `ExperimentBase.run_program`.
5. Optional auto-save of run output via `ExperimentBase.save_output` → `SessionManager.save_output`.
6. `analyze()` computes metrics/fit (`AnalysisResult`).
7. Optional calibration commit via `ExperimentBase.guarded_calibration_commit` + `CalibrationStore` mutators.
8. `plot()` visualizes analysis.

---

## 2) Where artifacts are created/saved

### Run outputs
- `qubox_v2/experiments/session.py` → `SessionManager.save_output`
- `qubox_v2/experiments/base.py` → `ExperimentRunner.save_output`
- Format: `data/<tag>_<timestamp>.npz` + `<tag>_<timestamp>.meta.json`
- Raw-array filtering: delegated to `core/persistence_policy.py::split_output_for_persistence`

### Calibration-run artifacts (quality gate records)
- `qubox_v2/experiments/experiment_base.py` → `guarded_calibration_commit`
- Writes JSON audit records to: `artifacts/calibration_runs/<tag>_<timestamp>.json`

### Session/build artifacts (declarative architecture)
- `qubox_v2/core/artifact_manager.py` → `ArtifactManager`
  - `save_session_state`, `save_generated_config`, `save_report`, `save_artifact`
- `qubox_v2/core/artifacts.py` → `save_config_snapshot`, `save_run_summary`

### Config-like persistence from runtime code
- `SessionManager.save_pulses` → `config/pulses.json`
- `SessionManager.override_readout_operation(..., persist_measure_config=True)` → `config/measureConfig.json`
- `SessionManager.close` persists pulses + runtime settings + calibration

---

## 3) Where analysis happens

### Standard pattern
- In each experiment module (`spectroscopy`, `time_domain`, `calibration`, `cavity`, `tomography`, `spa`):
  - `run()` acquires data
  - `analyze()` computes metrics/fits
  - `plot()` visualizes

### Shared analysis utilities
- `qubox_v2/analysis/fitting.py` (`generalized_fit`, `fit_and_wrap`, `build_fit_legend`)
- `qubox_v2/analysis/cQED_models.py` (model functions)
- `qubox_v2/analysis/post_process.py` (processor pipeline used during `run_program`)

### Known mixed-responsibility hotspot
- `qubox_v2/experiments/calibration/readout.py::CalibrateReadoutFull.run`
  - Calls sub-experiment `analyze()` from inside `run()` (workflow coupling).

---

## 4) Where calibrations are stored

### Primary calibration store (JSON)
- `qubox_v2/calibration/store.py` → `CalibrationStore`
- Backing file: `config/calibration.json`
- Mutators used by experiments:
  - `set_frequencies`
  - `set_coherence`
  - `set_pulse_calibration`
  - `set_discrimination`
  - `set_readout_quality`

### Mixer calibration DB (Octave)
- `qubox_v2/calibration/mixer_calibration.py`
- Backing file: `calibration_db.json`
- Triggered from hardware calibration flow (`hardware/controller.py`), not typical T1/T2/run-analyze-plot path.

---

## 5) Where primitive pulses are defined and updated

### Definition sources
- Legacy/operational pulse store: `config/pulses.json` through `PulseOperationManager`
  - `qubox_v2/pulses/manager.py`
- Declarative recipe source: `pulse_specs.json` compiled by:
  - `qubox_v2/pulses/factory.py` (`PulseFactory`)

### Runtime updates
- Session-level persistence and application:
  - `SessionManager.burn_pulses`, `SessionManager.save_pulses`
- Experiment-level weight/pulse mapping mutations:
  - `qubox_v2/experiments/calibration/readout.py`
- Explicit waveform construction helpers (imperative path):
  - `qubox_v2/tools/waveforms.py`
  - `qubox_v2/tools/generators.py` (`register_rotations_from_ref_iq`, `ensure_displacement_ops`)

### Important boundary observation
- The current system supports both declarative (`PulseFactory`) and imperative (direct waveform synthesis + registration) pulse paths in parallel.
