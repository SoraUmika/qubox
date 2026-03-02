# qubox_v2 Architecture

This document is a compact architecture index for day-to-day development.
The full canonical architecture guide is maintained in root `README.md`.

## Canonical sections

- System architecture and layering: `README.md` section 2
- Core API and lifecycle contracts: `README.md` section 3
- Calibration lifecycle/orchestration: `README.md` section 13
- Binding-driven API model: `README.md` section 24
- Program build/provenance model: `README.md` section 26

## Layer model (high level)

1. **Core models/config** (`qubox_v2.core`)  
	Context identity, schema validation, immutable-ish state snapshots.

2. **Hardware/runtime** (`qubox_v2.hardware`, `qubox_v2.devices`)  
	Program execution (`ProgramRunner`), instrument/device integration.

3. **Programs/macros** (`qubox_v2.programs`)  
	QUA builders, macro-based measurement, circuit compilation facade.

4. **Experiments** (`qubox_v2.experiments`)  
	Build/run/analyze/plot contract over domain workflows.

5. **Calibration orchestration** (`qubox_v2.calibration`)  
	Artifact-driven patch lifecycle and controlled persistence.

6. **Analysis/tools** (`qubox_v2.analysis`, `qubox_v2.tools`)  
	Fitting, metrics, post-processing, plotting support.

## Stable execution contract

Experiments derive from `ExperimentBase` and follow:

- `build_program(**params) -> ProgramBuildResult`
- `run(**params) -> RunResult`
- `analyze(result, *, update_calibration=False, **params) -> AnalysisResult`
- `plot(analysis, *, ax=None, **kwargs)`

Design intent:

- build phase is provenance-friendly and side-effect minimized
- run phase performs acquisition/runtime operations
- analyze phase computes metrics/fits and emits optional calibration proposals

## Calibration architecture

`CalibrationOrchestrator` is the recommended write path:

- consumes analysis/artifacts
- validates and previews patch operations
- commits through controlled ops (`SetCalibration`, `SetPulseParam`,
  `SetMeasureWeights`, `SetMeasureDiscrimination`, `PersistMeasureConfig`, etc.)

Avoid direct ad-hoc mutation patterns in notebook code when reproducibility matters.

### Calibration schema semantics (v5.1.0)

- `cqed_params` is the canonical home for Hamiltonian/device physical parameters.
- `pulse_calibrations` stores control-pulse primitive parameters only.
- `discrimination` stores readout classifier parameters.
- `readout_quality` stores readout quality metrics.

Physical parameters (e.g. `qubit_freq`, `resonator_freq`, `kappa`, `T1`, `T2_*`) are
written via `SetCalibration` paths under `cqed_params.<alias>.<field>` using alias names
(`transmon`, `resonator`, `storage`) instead of raw hardware keys.

Legacy `frequencies`/`coherence` entries are supported for load compatibility and are
migrated into `cqed_params` during calibration-store load.

## Measurement and readout architecture

- Measurement macro state remains widely used for runtime readout behavior.
- Newer design direction favors explicit measurement snapshots/specs in build provenance.
- Both paths coexist; gradual migration is expected.

## Execution modes

- `RunResult.mode` uses `ExecMode` (`HARDWARE`, `SIMULATE`)
- Simulation/provenance surfaces via `QuboxSimulationConfig` and `SimulationResult`

## Compatibility note

This file remains at `qubox_v2/docs/ARCHITECTURE.md` for legacy links.
If there is any mismatch with root `README.md`, treat `README.md` as authoritative.
