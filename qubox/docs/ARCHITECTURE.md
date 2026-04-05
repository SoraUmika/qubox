# qubox Internal Architecture Note

> Historical compatibility note. This package-local file exists only to catch
> older links. The canonical architecture docs are [site_docs/architecture/package-map.md](../../site_docs/architecture/package-map.md)
> and [site_docs/architecture/execution-flow.md](../../site_docs/architecture/execution-flow.md).

This document is a compact compatibility index for day-to-day development.
When details here and the root-level docs diverge, the root docs are authoritative.

## Canonical sections

- Package architecture and public surfaces: `API_REFERENCE.md`
- Architecture map: `site_docs/architecture/package-map.md`
- Runtime execution flow: `site_docs/architecture/execution-flow.md`
- Agent and validation policy: `AGENTS.md`

## Layer model (high level)

1. **Core models/config** (`qubox.core`)  
	Context identity, schema validation, immutable-ish state snapshots.

2. **Hardware/runtime** (`qubox.hardware`, `qubox.devices`)  
	Program execution (`ProgramRunner`), instrument/device integration.

3. **Programs/macros** (`qubox.programs`)  
	QUA builders, macro-based measurement, circuit compilation facade.

4. **Experiments** (`qubox.experiments`)  
	Build/run/analyze/plot contract over domain workflows.

5. **Calibration orchestration** (`qubox.calibration`)  
	Artifact-driven patch lifecycle and controlled persistence.

6. **Analysis/tools** (`qubox_tools`, `qubox.tools`)  
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
