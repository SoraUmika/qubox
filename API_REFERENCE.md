# qubox API Reference

**Version:** 3.0.0  
**Date:** 2026-04-04  
**Status:** Reconciled to the live repository state

This document is the canonical API reference for the active `qubox` package.
It replaces older migration-era descriptions that referred to removed package
layouts or compatibility-only import paths.

---

## 1. Overview

`qubox` is the active cQED experiment framework in this repository. The main
user-facing surfaces are:

- `Session` as the runtime entry point.
- `session.exp.*` for standard experiment templates.
- `session.sequence()` and `session.circuit()` for custom control bodies.
- `session.control_program()` for explicit control IR authoring.
- `session.sweep.*` and `session.acquire.*` for sweep and acquisition specs.
- `qubox.notebook` and `qubox.notebook.advanced` for notebook workflows.
- `qubox_tools` for fitting, plotting, optimization, and post-processing.

Supported stack:

- Hardware target: Quantum Machines OPX+ with Octave
- QM / QUA API: `1.2.6`
- Python: `3.12.10`

---

## 2. Package Architecture

Relevant live package layout:

```text
qubox/                  Main package
qubox/session/          Public Session facade
qubox/experiments/      Template namespaces, workflows, concrete experiment classes
qubox/sequence/         Sequence IR, sweeps, acquisitions
qubox/circuit/          Circuit-friendly IR
qubox/control/          ControlProgram IR and realization helpers
qubox/backends/qm/      QMRuntime and lowering path
qubox/calibration/      Calibration store, proposals, orchestrator, patch rules
qubox/core/             Bindings, measurement config, context, session state
qubox/programs/         QUA builders and compiler path
qubox/notebook/         Notebook-facing import surfaces
qubox/workflow/         Stage, checkpoint, and fit-gate primitives
qubox_tools/            Analysis toolkit
tools/                  Validation and developer utilities
```

Notes on the live layout:

- `qubox/session/` contains `session.py` and `__init__.py`.
- `qubox.gates` contains only the runtime hardware gate layer (`GateHardware`,
  `QubitRotationHardware`, `DisplacementHardware`, `SQRHardware`, `SNAPHardware`).
- Demo scripts, GUI helpers, and command-line workflows live under top-level
  `tools/`, not inside the `qubox` package.
- `ArtifactManager` lives in `qubox.artifacts`.
- `SampleRegistry` lives in `qubox.devices.registry` (re-exported by `qubox.devices`).
- `ExperimentContext` lives in `qubox.core.experiment_context`.
- `SessionState` lives in `qubox.core.session_state`.
- `qubox/gui/` and `qubox/migration/` are empty directory stubs with no code.

---

## 3. Top-Level Public Exports

`qubox.__all__` currently exports:

- `Session`
- `SessionFactory`
- `SessionProtocol`
- `Sequence`
- `Operation`
- `Condition`
- `SweepAxis`
- `SweepPlan`
- `AcquisitionSpec`
- `QuantumCircuit`
- `QuantumGate`
- `ExecutionRequest`
- `ExperimentResult`
- `RunManifest`
- `CalibrationProposal`
- `CalibrationSnapshot`
- `DeviceMetadata`

---

## 4. Session API

### 4.1 Construction

Use `Session.open(...)` to create a session.

Key parameters:

- `sample_id`
- `cooldown_id`
- `registry_base`
- `simulation_mode`
- `connect`
- backend connection kwargs such as `qop_ip` and `cluster_name`

Current behavior:

- `simulation_mode` defaults to `True`.
- In simulation mode, the QMM connection is still established.
- Real hardware execution is intentionally blocked in simulation mode.
- `connect=False` defers `SessionManager.open()`.

`SessionFactory` stores those parameters once and later creates configured
sessions through `.create(...)`.

### 4.2 Session Surfaces

Every `Session` exposes these user-tier surfaces directly:

- `session.ops` and `session.gates`
- `session.exp`
- `session.workflow`
- `session.sweep`
- `session.acquire`
- `session.backend`

### 4.3 Direct Properties

Advanced workflows can access:

- `session.hardware`
- `session.config_engine`
- `session.calibration`
- `session.pulse_mgr`
- `session.runner`
- `session.devices`
- `session.orchestrator`
- `session.bindings`
- `session.context`
- `session.session_manager`

There is no generic attribute forwarding. If something is not surfaced on
`Session`, use `session.session_manager` explicitly.

### 4.4 Builder Helpers

`Session` exposes these builder helpers:

- `session.sequence(name=...)`
- `session.circuit(name=...)`
- `session.control_program(name=...)`
- `session.to_control_program(body, sweep=..., acquisition=...)`
- `session.realize_control_program(body)`
- `session.ensure_sweep_plan(...)`

### 4.5 Resolution Helpers

Current helper methods include:

- `resolve_alias(...)`
- `resolve_center(...)`
- `resolve_pulse_length(...)`
- `resolve_discrimination(...)`
- `get_thermalization_clks(...)`
- `readout_handle(...)`

---

## 5. Experiment Execution And Data Models

### 5.1 `session.exp`

`session.exp` is an `ExperimentLibrary` with these namespaces:

- `session.exp.qubit`
- `session.exp.resonator`
- `session.exp.readout`
- `session.exp.calibration`
- `session.exp.storage`
- `session.exp.tomography`
- `session.exp.reset`

Representative template entry points include:

- `session.exp.qubit.spectroscopy(...)`
- `session.exp.qubit.power_rabi(...)`
- `session.exp.qubit.ramsey(...)`
- `session.exp.qubit.temporal_rabi(...)`
- `session.exp.qubit.t1(...)`
- `session.exp.qubit.echo(...)`
- `session.exp.resonator.spectroscopy(...)`
- `session.exp.resonator.power_spectroscopy(...)`
- `session.exp.readout.trace(...)`
- `session.exp.readout.iq_blobs(...)`
- `session.exp.calibration.all_xy(...)`
- `session.exp.calibration.drag(...)`
- `session.exp.storage.spectroscopy(...)`
- `session.exp.storage.ramsey(...)`
- `session.exp.tomography.qubit_state(...)`
- `session.exp.tomography.wigner(...)`
- `session.exp.reset.active(...)`

### 5.2 `session.exp.custom(...)`

`session.exp.custom(...)` is the canonical custom entry point.

Rules:

- It requires exactly one of `sequence=`, `circuit=`, or `control=`.
- `execute=True` routes through `session.backend.run(...)`.
- `execute=False` routes through `session.backend.build(...)`.
- `analysis` defaults to `raw`.

### 5.3 `ExecutionRequest`

`ExecutionRequest` is the immutable run specification shared by template and
custom execution.

Current fields:

- `kind`
- `template`
- `targets`
- `params`
- `sequence`
- `circuit`
- `control_program`
- `sweep`
- `acquisition`
- `shots`
- `analysis`
- `execute`
- `metadata`

### 5.4 `ExperimentResult`

`ExperimentResult` bundles:

- the originating `ExecutionRequest`
- `build`
- `run`
- `analysis`
- `calibration_snapshot`
- `manifest`
- `artifact_path`
- `compiler_report`
- optional `plotter`

Methods:

- `.inspect()` returns a JSON-friendly summary
- `.plot(...)` delegates to the attached plotter
- `.proposal()` builds a `CalibrationProposal` from `analysis.metadata['proposed_patch_ops']`

### 5.5 `RunManifest`

`RunManifest` is the immutable provenance record attached to a run.

It captures:

- the `ExecutionRequest`
- a `CalibrationSnapshot`
- the hardware config hash
- the qubox version
- a timestamp
- optional git SHA
- session metadata

If a control program is present, `RunManifest.to_dict()` records its name under
`execution_request.control_program`.

---

## 6. QM Backend Runtime

### 6.1 `QMRuntime`

`session.backend` lazily constructs a `QMRuntime` from `qubox.backends.qm`.

Public methods:

- `.run(request)`
- `.build(request)`

### 6.2 Template Path

Template execution uses the adapter registry in `qubox.backends.qm.runtime`.

The live registry currently contains 32 template adapters across these families:

- qubit
- resonator
- readout
- calibration
- storage
- tomography
- reset

### 6.3 Custom Path

Custom execution supports:

- `Sequence`
- `QuantumCircuit`
- `ControlProgram`

The runtime lowers those bodies through `qubox.backends.qm.lowering` into the
compiler path under `qubox.programs`.

### 6.4 Lowering Facts

Current verified backend facts:

- Custom control lowering supports explicit `ControlProgram` bodies.
- Conditional `AcquireInstruction` lowering is not supported yet.
- Explicit readout ownership is required for measurement emission.
- The active measurement path uses `ReadoutHandle` or session-owned `MeasurementConfig`, not hidden singleton state.

### 6.5 Validation Entry Points

QUA-touching work should use the repository validation helpers rather than ad
hoc runtime calls:

- `tools/validate_qua.py`
- `tools/validate_standard_experiments_simulation.py`

---

## 7. Notebook Import Surfaces

### 7.1 `qubox.notebook`

`qubox.notebook` is the primary notebook-facing import surface.

It currently exports:

- shared-session helpers such as `open_shared_session`, `require_shared_session`, `restore_shared_session`, and `close_shared_session`
- notebook stage helpers such as `open_notebook_stage`, `save_stage_checkpoint`, `load_stage_checkpoint`, `preview_or_apply_patch_ops`, `fit_quality_gate`, and `ensure_primitive_rotations`
- experiment classes re-exported from `qubox.experiments`
- calibration essentials such as `CalibrationOrchestrator`, `Patch`, `UpdateOp`, `MixerCalibrationConfig`, and `SAMeasurementHelper`
- `HardwareDefinition`
- `ReadoutHandle`, `ReadoutCal`, `MeasurementConfig`, `PostSelectionConfig`, `continuous_wave`, and `QuboxSimulationConfig`
- waveform helpers such as `drag_gaussian_pulse_waveforms`, `kaiser_pulse_waveforms`, `register_rotations_from_ref_iq`, and `ensure_displacement_ops`
- `RunResult`, `AnalysisResult`, `ProgramBuildResult`, and `save_run_summary`

### 7.2 `qubox.notebook.advanced`

`qubox.notebook.advanced` is the advanced and infrastructure notebook surface.
It exports, among other things:

- `CalibrationStore` and calibration data models
- `SampleRegistry` and `SampleInfo`
- `ArtifactManager`, `save_config_snapshot`, `save_run_summary`, and `cleanup_artifacts`
- `preflight_check`, `validate_config_dir`, and `ValidationResult`
- `ContextMismatchError`
- `ExperimentContext` and `compute_wiring_rev`
- `SessionState`
- `run_all_checks`
- notebook bootstrap helpers such as `get_notebook_session_bootstrap_path` and `save_notebook_session_bootstrap`

---

## 8. Workflow Primitives

### 8.1 `qubox.workflow`

`qubox.workflow` exposes script-friendly workflow primitives used by both
notebooks and automation:

- `StageCheckpoint`
- `WorkflowConfig`
- `build_workflow_config(...)`
- `get_stage_checkpoint_path(...)`
- `load_stage_checkpoint(...)`
- `save_stage_checkpoint(...)`
- `preview_or_apply_patch_ops(...)`
- `fit_center_inside_window(...)`
- `fit_quality_gate(...)`
- `ensure_primitive_rotations(...)`

### 8.2 `session.workflow`

`session.workflow` is the compatibility workflow namespace currently exposed
through `WorkflowLibrary`.

At present the concrete workflow surface is `session.workflow.readout.full(...)`.
Its `.run()` method returns a `WorkflowReport`. Its `.apply()` method is
intentionally unsupported and raises, so staged calibration outputs must still
be promoted through the explicit proposal / patch flow.

---

## 9. Internal Services Worth Knowing

These modules back the public APIs and are stable enough to understand, but they
remain advanced surfaces rather than primary user entry points:

- `qubox.experiments.session.SessionManager`
- `qubox.calibration.store.CalibrationStore`
- `qubox.calibration.orchestrator.CalibrationOrchestrator`
- `qubox.pulses.manager.PulseOperationManager`
- `qubox.hardware.config_engine.ConfigEngine`
- `qubox.hardware.controller.HardwareController`
- `qubox.hardware.program_runner.ProgramRunner`
- `qubox.programs.circuit_runner.CircuitRunner`
- `qubox.programs.circuit_compiler.CircuitCompiler`
- `qubox.artifacts.ArtifactManager`
- `qubox.core.experiment_context.ExperimentContext`
- `qubox.core.session_state.SessionState`

The supported top-level entry points remain:

- `qubox`
- `qubox.notebook`
- `qubox.notebook.advanced`
- `qubox_tools`

---

## 10. qubox_tools

`qubox_tools` is the analysis toolkit that complements runtime execution in
`qubox`.

Use it for:

- fitting and model evaluation
- plotting and post-processing
- optimization helpers
- post-selection utilities such as `PostSelectionConfig`

If a workflow is primarily about data fitting or plotting rather than runtime
execution, prefer `qubox_tools` rather than extending the QM runtime layer.

---

## 11. Current Notes And Limitations

- Sweep-center tokens (`qubit.ge`, `qubit.ef`, `readout`, `storage`) are resolved at execution time.
- The compiled QUA program is the source of truth for QUA-touching work.
- QM-hosted simulation is supported for compiled-QUA validation via `tools/validate_qua.py` and `tools/validate_standard_experiments_simulation.py`.
- Conditional `AcquireInstruction` lowering is not yet supported; see `limitations/qua_related_limitations.md`.
- The live import surfaces are `qubox`, `qubox.notebook`, `qubox.notebook.advanced`, and `qubox_tools`. Any older docs referencing `qubox_v2`, `qubox_v2_legacy`, `qubox.legacy`, `qubox.compile`, or `qubox.simulation` describe removed packages.
