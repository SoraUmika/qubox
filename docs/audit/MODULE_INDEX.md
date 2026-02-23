# Module Index (by responsibility)

## Session builder / session state

- `qubox_v2/experiments/session.py`
  - `SessionManager` (service wiring: hardware, runner, pulse manager, calibration store, devices)
  - `open`, `close`, `burn_pulses`, `save_output`, `override_readout_operation`
- `qubox_v2/experiments/base.py`
  - `ExperimentRunner` (alternate infrastructure entry)
- `qubox_v2/experiments/experiment_base.py`
  - `ExperimentBase` (common run/analyze/plot protocol + `guarded_calibration_commit`)
- `qubox_v2/core/session_state.py`
  - `SessionState`, `SessionState.from_config_dir`

## Calibration store / DB

- `qubox_v2/calibration/store.py`
  - `CalibrationStore`
  - mutators: `set_frequencies`, `set_coherence`, `set_pulse_calibration`, `set_discrimination`, `set_readout_quality`
- `qubox_v2/calibration/models.py`
  - typed calibration data models
- `qubox_v2/calibration/patch.py`
  - patch application helpers against `CalibrationStore`
- `qubox_v2/calibration/state_machine.py`
  - calibration lifecycle/state machinery
- `qubox_v2/calibration/mixer_calibration.py`
  - mixer calibration flow and `calibration_db.json` persistence helpers
- `qubox_v2/hardware/controller.py`
  - mixer calibration entry that routes to mixer calibration DB path

## Artifact store / saving

- `qubox_v2/core/artifact_manager.py`
  - `ArtifactManager` (`save_session_state`, `save_generated_config`, `save_report`, `save_artifact`)
- `qubox_v2/core/artifacts.py`
  - `save_config_snapshot`, `save_run_summary`
- `qubox_v2/core/persistence_policy.py`
  - `split_output_for_persistence`, `sanitize_mapping_for_json`
- `qubox_v2/experiments/session.py`
  - `SessionManager.save_output`
- `qubox_v2/experiments/base.py`
  - `ExperimentRunner.save_output`
- `qubox_v2/experiments/experiment_base.py`
  - `guarded_calibration_commit` artifact writes under `artifacts/calibration_runs`

## Pulse/operation manager + waveform generation

- `qubox_v2/pulses/manager.py`
  - `PulseOperationManager`
  - pulse/weight registration, mapping, materialization, and `pulses.json` persistence
- `qubox_v2/pulses/factory.py`
  - `PulseFactory` (compile declarative pulse specs to I/Q arrays)
- `qubox_v2/pulses/spec_models.py`
  - declarative pulse schema models
- `qubox_v2/pulses/waveforms.py`
  - waveform helper wrappers (pulse package)
- `qubox_v2/tools/waveforms.py`
  - imperative waveform generators (DRAG, kaiser, slepian, flattop, etc.)
- `qubox_v2/tools/generators.py`
  - runtime pulse constructors/helpers (`register_rotations_from_ref_iq`, `ensure_displacement_ops`)
- `qubox_v2/hardware/config_engine.py`
  - merges pulse-manager resources into compiled QM config

## Analysis / fit functions

- `qubox_v2/analysis/fitting.py`
  - `generalized_fit`, `fit_and_wrap`, `build_fit_legend`
- `qubox_v2/analysis/cQED_models.py`
  - model equations used by experiment fits
- `qubox_v2/analysis/post_process.py`
  - stream post-processing functions used in `run_program(...)`
- `qubox_v2/analysis/output.py`
  - `Output` container
- `qubox_v2/analysis/metrics.py`, `analysis_tools.py`, `algorithms.py`
  - shared numerical helpers/metrics

## Experiment modules (where run/analyze/plot live)

- `qubox_v2/experiments/spectroscopy/*.py`
- `qubox_v2/experiments/time_domain/*.py`
- `qubox_v2/experiments/calibration/*.py`
- `qubox_v2/experiments/cavity/*.py`
- `qubox_v2/experiments/tomography/*.py`
- `qubox_v2/experiments/spa/*.py`

## User-facing workflow entry notebooks/scripts

- `notebooks/post_cavity_experiment.ipynb` (primary workflow)
- `notebooks/post_cavity_calibrations.ipynb`
- `audit_offline.py`
- `smoke_test_const_pulse.py`
- `smoke_test_rabi.py`
- `smoke_test_readout.py`
