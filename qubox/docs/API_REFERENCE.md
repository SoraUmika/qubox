# qubox Internal API Reference

> Historical compatibility note. This package-local file exists only to catch
> older links. The canonical public API reference is [API_REFERENCE.md](../../API_REFERENCE.md).

This document is a concise compatibility quick-reference for common workflows.
When details here and the root-level docs diverge, the root docs are authoritative.

## Canonical sections

- Public API and package architecture: `API_REFERENCE.md`
- Architecture map: `site_docs/architecture/package-map.md`
- Runtime execution flow: `site_docs/architecture/execution-flow.md`
- Calibration/orchestration policies: `AGENTS.md`

## Core result types

### `RunResult` (`qubox.hardware.program_runner`)

- Fields: `mode`, `output`, `sim_samples`, `metadata`
- `mode` is an `ExecMode` enum (`HARDWARE` / `SIMULATE`)
- `output` is dict-like (`Output`) and is the source for downstream analysis

### `AnalysisResult` (`qubox.experiments.result`)

- Fields: `data`, `fit`, `fits`, `metrics`, `source`, `metadata`
- Construct via `AnalysisResult.from_run(...)`
- `analyze()` should be idempotent and side-effect free by default

### `ProgramBuildResult` (`qubox.experiments.result`)

- Build-time provenance container returned by `build_program()` / `_build_impl()`
- Includes compiled program inputs, processors, resolved frequencies, sweep axes,
	measurement snapshot state, and run kwargs

## Experiment contract (stable)

All experiments inherit from `ExperimentBase` and follow:

1. `build_program(**params) -> ProgramBuildResult`
2. `run(**params) -> RunResult`
3. `analyze(result, *, update_calibration=False, **params) -> AnalysisResult`
4. `plot(analysis, *, ax=None, **kwargs)`

Contract notes:

- `run()` executes acquisition only; no hidden calibration writes
- `analyze()` may prepare proposed calibration updates in metadata and should not
	perform hardware mutations unless explicitly requested
- `plot()` consumes analysis outputs and should tolerate missing optional fields

## Calibration API (recommended path)

Use `CalibrationOrchestrator` for patch lifecycle and persistence:

- `CalibrationOrchestrator.apply_patch(...)`
- `CalibrationOrchestrator.persist_artifact(...)`

Do not perform ad-hoc calibration writes inside experiment `run()` paths.

### Physical-parameter write targets

- Canonical physical calibration writes use `SetCalibration` paths under:
	- `cqed_params.resonator.*`
	- `cqed_params.transmon.*`
	- `cqed_params.storage.*`
- Typical fields: `resonator_freq`, `qubit_freq`, `ef_freq`, `kappa`, `T1`,
	`T1_us`, `T2_ramsey`, `T2_star_us`, `T2_echo`, `T2_echo_us`.
- `frequencies` and `coherence` remain load-compatible legacy maps and are
	migrated to `cqed_params` during calibration-store load.

## Readout/discrimination output conventions

- GE/readout discrimination pipelines expose complex blobs as `S_g` / `S_e`
- `two_state_discriminator(...)` returns dict-like output (e.g. key `fidelity`)
	rather than a positional tuple

## Compatibility note

This file remains in `qubox/docs/` to preserve older internal links.
When details here and the root-level canonical docs diverge, the root docs are authoritative.
