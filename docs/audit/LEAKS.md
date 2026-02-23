# Responsibility Leak Report

Scope: `qubox_v2/experiments` modular workflow (plus explicit legacy hotspot note).

## A) Direct calibration/config mutation from experiment code

| File | Symbol | What it mutates/saves | Recommended fix |
|---|---|---|---|
| `qubox_v2/experiments/spectroscopy/resonator.py` | `ResonatorSpectroscopy.analyze` | Calls `calibration_store.set_frequencies(...)` directly when `update_calibration=True`. | Route through a dedicated calibration service/command object; keep `analyze()` pure and return patch intent. |
| `qubox_v2/experiments/spectroscopy/resonator.py` | `ResonatorSpectroscopyX180.analyze` | Direct `set_frequencies(..., chi=...)`. | Same: emit patch/intention; commit in orchestrator. |
| `qubox_v2/experiments/spectroscopy/resonator.py` | `ReadoutFrequencyOptimization.analyze` | Direct `set_frequencies(...)` update. | Move persistence to calibration pipeline layer. |
| `qubox_v2/experiments/spectroscopy/qubit.py` | `QubitSpectroscopy.analyze` | Direct `set_frequencies(..., qubit_freq=...)`. | Use patch/commit boundary outside experiment class. |
| `qubox_v2/experiments/spectroscopy/qubit.py` | `QubitSpectroscopyCoarse.analyze` | Direct `set_frequencies(..., qubit_freq=...)`. | Same. |
| `qubox_v2/experiments/cavity/storage.py` | `StorageSpectroscopy.analyze` | Direct `set_frequencies(...)` write. | Same. |
| `qubox_v2/experiments/cavity/storage.py` | `StorageChiRamsey.analyze` | Direct `set_frequencies(..., chi=...)` write. | Same. |
| `qubox_v2/experiments/time_domain/relaxation.py` | `T1Relaxation.analyze` | Commits via `guarded_calibration_commit(... set_coherence ...)`. | Keep guarded gate, but move actual commit execution to orchestration layer. |
| `qubox_v2/experiments/time_domain/coherence.py` | `T2Ramsey.analyze` | Commits via `guarded_calibration_commit(... set_coherence ...)`. | Same. |
| `qubox_v2/experiments/time_domain/coherence.py` | `T2Echo.analyze` | Commits via `guarded_calibration_commit(... set_coherence ...)`. | Same. |
| `qubox_v2/experiments/time_domain/rabi.py` | `TemporalRabi.analyze` | Commits via `guarded_calibration_commit(... set_pulse_calibration ...)`. | Same. |
| `qubox_v2/experiments/time_domain/rabi.py` | `PowerRabi.analyze` | Commits via `guarded_calibration_commit(... set_pulse_calibration ...)`. | Same. |
| `qubox_v2/experiments/calibration/gates.py` | `DRAGCalibration.analyze` | Commits via `guarded_calibration_commit(... set_pulse_calibration for ref_r180/x180 ...)`. | Same. |
| `qubox_v2/experiments/calibration/readout.py` | `ReadoutGEDiscrimination.analyze` | Commits discrimination params (`set_discrimination`) and mutates `measureMacro` state. | Split into: (1) compute-only analysis result, (2) explicit apply step owned by pipeline service. |
| `qubox_v2/experiments/calibration/readout.py` | `ReadoutButterflyMeasurement.analyze` | Commits readout quality (`set_readout_quality`) and mutates `measureMacro._ro_quality_params`. | Same split; avoid private macro state writes inside analysis. |
| `qubox_v2/experiments/calibration/readout.py` | `CalibrateReadoutFull.run` | Calls `calibration_store.save()`, `measureMacro.save_json(...)`, `save_pulses()`, `save_attributes()` directly from `run()`. | Move persistence to dedicated pipeline orchestrator `commit()` stage. |

## B) Pulse/weight config mutation and internal pulse compilation inside experiments

| File | Symbol | What it mutates/creates | Recommended fix |
|---|---|---|---|
| `qubox_v2/experiments/calibration/readout.py` | `ReadoutGEDiscrimination._build_rotated_weights` | Creates rotated integration weights and updates pulse weight mappings in `PulseOperationManager`; may `burn_pulses()`. | Replace with declarative weight recipe output; apply via single config-apply service. |
| `qubox_v2/experiments/calibration/readout.py` | `ReadoutGEDiscrimination._apply_rotated_measure_macro` | Rebinds active measure weights in `measureMacro`. | Keep analysis pure; apply measure mapping in runtime policy layer. |
| `qubox_v2/experiments/calibration/readout.py` | `ReadoutGEDiscrimination._persist_measure_macro_state` | Writes `config/measureConfig.json`. | Centralize under session-level persistence policy, not experiment internals. |
| `qubox_v2/experiments/calibration/readout.py` | `ReadoutWeightsOptimization._register_optimized_weights` | Registers segmented weights, updates pulse mapping, mutates `measureMacro`, burns pulses. | Emit `WeightUpdatePatch` object; let orchestrator apply in one place. |
| `qubox_v2/experiments/calibration/gates.py` | `DRAGCalibration.run` | Compiles DRAG waveforms (`drag_gaussian_pulse_waveforms`), creates temp pulse ops (`register_pulse_op`), then burns pulses. | Use declarative pulse spec + factory compile path; avoid ad-hoc temporary pulse synthesis in experiment `run()`. |

## C) Analysis embedded in run path (run/analyze boundary leak)

| File | Symbol | Leak | Recommended fix |
|---|---|---|---|
| `qubox_v2/experiments/calibration/readout.py` | `CalibrateReadoutFull.run` | Calls `wopt.analyze(...)`, `ge_disc.analyze(...)`, and optionally `bfly.analyze(...)` inside `run()`. | Keep `run()` acquisition-only; move iterative decision logic to explicit pipeline controller that consumes `analyze()` outputs. |

## D) Large raw shot-array persistence audit

### Findings
- **Current modular persistence path is guarded**:
  - `SessionManager.save_output` and `ExperimentRunner.save_output` both call `split_output_for_persistence(...)`.
  - `split_output_for_persistence` drops arrays with `size > 8192` and raw-like keys (`raw|shot|samples|buffer|acq...`).
- **High-risk producers** (large shot arrays are generated in memory, but filtered at persistence boundary):
  - `qubox_v2/experiments/calibration/readout.py::ReadoutGEDiscrimination.run` (`S_g`, `S_e` shot clouds)
  - `qubox_v2/experiments/calibration/readout.py::ReadoutButterflyMeasurement.run` (`states`, `I0/Q0/I1/Q1/I2/Q2`)

### Net assessment
- No confirmed modular location writes *large raw shot arrays* directly to disk without passing the persistence policy.
- Risk remains architectural: many experiment classes call `save_output(...)` internally, so data-retention policy is implicit and distributed rather than explicit per experiment.

## E) Legacy hotspot note

| File | Symbol | Note |
|---|---|---|
| `qubox_v2/experiments/legacy_experiment.py` | `cQED_Experiment` methods (monolithic) | Centralizes execution + analysis + config mutation + persistence in one class; highest responsibility concentration. Use only for compatibility and avoid adding new features here. |
