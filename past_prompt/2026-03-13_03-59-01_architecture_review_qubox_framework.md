# Prompt Log

- Timestamp: 2026-03-13T03:59:01.0619057-05:00
- Repository: `E:\qubox`
- Task: Architectural overview and refactor proposal for a user-friendly qubox experiment framework

## Original Request

Perform a deep architectural review of the current cQED experimental software stack and propose an enterprise-grade refactor that makes experiment design, calibration, execution, and analysis much easier for experimental physicists.

Required scope:

1. Explain how experiments, pulse sequences, calibration logic, QM / QUA integration, analysis, and artifacts are currently structured.
2. Judge the current design from the point of view of a lab user who wants to define experiments quickly and safely.
3. Propose a target architecture with clearer separation between user-facing experiment design, gate / protocol abstractions, compilation, backend execution, calibration, analysis, and documentation.
4. Critically evaluate whether `QuantumCircuit`, `QuantumGate`, and a circuit compiler should be the primary abstraction.
5. Provide user-facing API examples for spectroscopy, Rabi, Ramsey, active reset, and custom composed sequences.
6. Recommend a concrete directory layout, documentation plan, and staged migration roadmap.

## Result

### Executive Summary

The current repository is not missing capability. It is missing a single dominant mental model.

Today the codebase contains four partially overlapping architectures:

1. A mature experiment-class layer built around `SessionManager`, `ExperimentBase`, and direct QUA builder functions.
2. A notebook-first configuration and sample / cooldown context layer with strong reproducibility intent.
3. A newer binding-driven and roleless API (`DriveTarget`, `ReadoutHandle`, `MeasurementConfig`, `HardwareDefinition`) that is only partly adopted.
4. A newer gate -> protocol -> circuit compiler stack (`QuantumCircuit`, `Gate`, `CircuitRunnerV2`) that is architecturally promising but not yet the main production path.

For a new experimentalist, the main problem is not "too little abstraction". It is "too many overlapping abstractions with no obvious default path".

My main recommendation is:

- Do not make `QuantumCircuit` the only top-level user abstraction.
- Make `ExperimentTemplate + SweepPlan + AcquisitionSpec` the primary user-facing model.
- Use `QuantumCircuit` or `Sequence` as the body IR for sequence-shaped experiments and custom protocols.
- Treat spectroscopy, calibration workflows, and multi-stage tune-up flows as experiment/workflow objects, not as circuits.

That gives you a cleaner split:

- experiments describe physics intent and sweeps,
- sequences / circuits describe ordered control bodies,
- calibration resolves operation references into backend-ready pulses,
- the backend adapter emits QUA,
- analysis and patch proposals stay outside the compiler.

### Current Architecture Overview

#### 1. Session, context, and startup

The real entry point today is `qubox_v2.experiments.session.SessionManager`.

In practice, `SessionManager` is strict context mode:

- it requires `sample_id` and `cooldown_id`,
- resolves sample-level vs cooldown-level config via `SampleRegistry` and `ContextResolver`,
- loads `hardware.json`, `devices.json`, `cqed_params.json`, `pulses.json`, `calibration.json`, and optionally `measureConfig.json`,
- creates `ConfigEngine`, `HardwareController`, `ProgramRunner`, `QueueManager`, `PulseOperationManager`, `CalibrationStore`, `DeviceManager`, and `CalibrationOrchestrator`.

This is a strong reproducibility design. It gives you sample / cooldown scoping, alias registration, and calibration context checking. From a lab workflow perspective, that is one of the best parts of the codebase.

The friction is that the startup path is heavy, and the documentation is inconsistent:

- there is no root `README.md`,
- `SessionManager` docstrings and some docs still show legacy `experiment_path` usage,
- but the constructor now effectively enforces sample / cooldown context mode.

#### 2. Experiment definition

Experiments are mostly concrete `ExperimentBase` subclasses under:

- `experiments/spectroscopy`
- `experiments/time_domain`
- `experiments/calibration`
- `experiments/cavity`
- `experiments/tomography`
- `experiments/spa`

This layer is physically meaningful. Class names map well to what a physicist thinks in terms of:

- `QubitSpectroscopy`
- `PowerRabi`
- `T2Ramsey`
- `ReadoutGEDiscrimination`
- `StorageSpectroscopy`
- `FockResolvedRamsey`

The canonical per-experiment lifecycle is:

1. resolve parameters,
2. build a QUA program in `_build_impl()`,
3. wrap it in `ProgramBuildResult`,
4. execute it with `run_program()`,
5. analyze it into `AnalysisResult`,
6. optionally emit calibration patch proposals.

This part is conceptually good.

The problem is ergonomics and duplication:

- each experiment has its own `run(...)` signature with many kwargs,
- parameter resolution helpers are repeated across files,
- sweeps are represented ad hoc in each class,
- several experiments bypass `build_program()` because they are multi-segment or multi-stage,
- workflow experiments such as `CalibrateReadoutFull` behave more like orchestration pipelines than single experiments.

#### 3. Pulse sequence and protocol representation

The dominant production representation is still direct QUA builder code in `qubox_v2.programs.builders.*`.

Those builder functions:

- import `from qm.qua import *`,
- directly emit QUA loops and play / measure statements,
- rely heavily on the global `measureMacro` singleton for readout behavior.

There is also a macro layer:

- `measureMacro` for measurement and discriminator state,
- `sequenceMacros` for reusable fragments such as Ramsey, echo, tomography, and reset-like flows.

This means the practical pulse / protocol model today is:

- builder functions + global readout state + helper macros.

That is powerful, but it is not easy to inspect from the outside, and it is difficult to reason about because the measurement state is hidden in mutable class variables.

#### 4. Quantum Machines bridge

The QM / QUA bridge is structurally separated into useful layers:

- `ConfigEngine` merges hardware base, pulse overlay, element-operation overlay, and runtime overrides into a QM config.
- `HardwareController` owns the live QM / Octave connection and LO / IF / gain control.
- `ProgramRunner` executes or simulates QUA programs and applies post-processors.

This split is one of the strongest architectural parts of the repo. It is a reasonable backend boundary.

The main weakness is that backend compilation is still split across two paths:

1. direct legacy builder functions in `programs/builders/*`,
2. the newer circuit compiler stack in `programs/circuit_runner.py` and `programs/circuit_compiler.py`.

The old `CircuitRunner.compile(...)` is not a real generic compiler. It mostly name-dispatches a few circuit names back into legacy builder functions:

- power Rabi,
- T1,
- GE discrimination,
- butterfly,
- XY pair.

The newer `CircuitRunnerV2.compile(...)` is much closer to a real intent-level compiler, but it is not the dominant path used by experiment classes.

#### 5. Calibration logic

Calibration persistence is centered on `CalibrationStore`, which is a good design:

- typed Pydantic models,
- atomic JSON writes,
- physical-channel keyed readout records with alias mapping,
- separate sections for discrimination, readout quality, cQED params, and pulse calibrations.

Patch application is handled by `CalibrationOrchestrator` and `patch_rules.py`, which is also a good idea in principle:

- analysis can propose patch ops,
- rules translate fit results into calibration mutations,
- apply is transactional.

The problem is that the runtime still has several calibration-adjacent truth sources:

- `CalibrationStore`,
- `cQED_attributes`,
- `measureMacro`,
- session runtime settings,
- `PulseOperationManager` state.

So the store is conceptually the source of truth, but not yet operationally the only truth.

#### 6. Analysis

Analysis is mostly experiment-local:

- each experiment's `analyze()` chooses models, guesses initial parameters, calls `fit_and_wrap()`, and returns `AnalysisResult`,
- plotting is also implemented per experiment,
- general helpers live in `analysis/`.

This is workable, but it leads to repeated logic:

- projection of IQ data,
- fit guess heuristics,
- metric naming,
- calibration proposal construction.

There is not yet a strong analysis-pipeline layer or reusable "experiment family" analysis contract.

#### 7. Results, artifacts, and metadata

Result types exist and are useful:

- `RunResult`
- `ProgramBuildResult`
- `SimulationResult`
- `AnalysisResult`

Persistence exists in several places:

- `SessionManager.save_output()`,
- `ExperimentRunner.save_output()`,
- `CalibrationOrchestrator.persist_artifact()`,
- `ArtifactManager`,
- `core.artifacts.save_config_snapshot()` and `save_run_summary()`.

Filesystem layout is also split well by sample vs cooldown:

- sample level for hardware and quasi-static config,
- cooldown level for calibration, pulses, runtime settings, data, and artifacts.

But artifact strategy is fragmented:

- build-hash artifact storage exists,
- runtime artifact storage exists,
- NPZ output saving exists,
- config snapshot helpers exist,
- `SessionState` exists,
- yet these are not unified into one default run repository contract.

### Current Pain Points

#### What is intuitive

- Physics-level experiment class names are good.
- Session-scoped sample / cooldown context is appropriate for real lab work.
- `ProgramBuildResult` and `simulate()` are good moves toward inspectability.
- `CalibrationStore` is strong and should remain central.

#### What is overly coupled

- Measurement behavior is globally coupled through `measureMacro`.
- Experiment code is coupled to both `cQED_attributes` and `CalibrationStore`.
- Circuit support is coupled back into legacy builders through `CircuitRunner.compile(...)`.
- Several workflow concepts are mixed inside single monolithic files.

#### What is too low level

- Many user-facing flows still require understanding pulse ops, active readout state, weight mapping, and measure macro lifecycle.
- Standard spectroscopy and time-domain experiments still expose backend-shaped kwargs rather than a smaller domain language.

#### What is difficult to discover

- There is no short root onboarding document.
- `API_REFERENCE.md` is comprehensive but too large to serve as the first contact document.
- New abstractions (`MeasurementConfig`, config dataclasses, roleless primitives, `SessionState`, `ArtifactManager`) exist but are not the obvious path users are taught to follow.

#### What is hard to extend

- The readout calibration stack is spread across `measureMacro`, giant experiment files, patch rules, and session startup sync.
- Adding a new experiment often means copying the same parameter-resolution and save / analyze patterns.
- There is no single "experiment family" abstraction for shared sweep, acquisition, and analysis logic.

#### What will slow down a new lab member

- They must understand sample registry, cooldown layout, calibration JSON, pulse manager, measure macro, experiment classes, and sometimes circuit code before doing simple work.
- The docstrings still imply older workflows that the current code no longer supports.
- It is not obvious which abstraction is the preferred one for new development.

### Specific Architectural Friction Points Confirmed In The Repo

1. No root `README.md` exists, despite the repo policy expecting one.
2. `SessionManager` documentation still shows legacy path-based startup, but the constructor now requires `sample_id` and `cooldown_id`.
3. `experiments/configs.py` exists and documents immutable config objects, but the experiment APIs still primarily accept raw kwargs.
4. `MeasurementConfig`, `DriveTarget`, `ReadoutHandle`, and `FrequencyPlan` exist but are barely used by production experiment code.
5. `SessionState` and `ArtifactManager` exist but are optional/manual rather than the default session artifact path.
6. `measureMacro` appears throughout the stack and still dominates measurement runtime state.
7. The new circuit compiler (`CircuitRunnerV2`) is mostly exercised by examples/tests, not by the main experiment catalog.
8. There is no executable simulator-backed implementation of the `standard_experiments.md` trust protocol in the main test suite.
9. The biggest files are responsibility magnets:
   - `experiments/calibration/readout.py` ~3247 lines
   - `programs/macros/measure.py` ~1874 lines
   - `pulses/manager.py` ~2173 lines
   - `experiments/session.py` ~1079 lines
   - `programs/circuit_compiler.py` ~1064 lines

### Design Goals For The Refactor

1. One obvious top-level user path.
2. Physics intent must stay separate from hardware lowering.
3. Parameter sweeps must be first-class, not improvised.
4. Calibrated operations should be referenced semantically, not by raw waveform ownership.
5. Readout configuration should be session-owned, not global mutable singleton state.
6. Standard experiments should be short to write and easy to inspect.
7. Advanced users must still have an escape hatch for custom QUA behavior.
8. Migration must preserve existing working experiments while new layers come online.

### Proposed Target Architecture

#### Recommendation: make experiments primary, circuits secondary

Use this layered model:

1. `Session`
   Owns sample / cooldown context, calibration store, pulse registry, backend adapter, and artifact repository.

2. `TargetRegistry`
   Resolves aliases like `qubit`, `readout`, `storage`, `ef_qubit`, `q1`, `rr1` into typed target handles.

3. `OperationLibrary`
   Exposes calibrated, physics-level operations by reference:
   - `x90`, `x180`, `drag_x90`, `ef_x180`
   - `readout.acquire()`
   - `displace(alpha)`
   - `snap(...)`
   - `wait(ns)`
   - `frame(phase)`

4. `Sequence` / `QuantumCircuit`
   Ordered, single-shot body IR for composed control logic.
   Good for:
   - Ramsey,
   - echo,
   - active reset body,
   - custom state prep + control + readout,
   - cavity control sequences.

5. `SweepPlan`
   Orthogonal description of what varies:
   - frequency,
   - amplitude,
   - duration,
   - detuning,
   - multi-axis sweeps,
   - segmented coarse sweeps,
   - averaging,
   - loop ordering policy.

6. `AcquisitionSpec`
   Describes what to acquire and how:
   - IQ,
   - state labels,
   - ADC traces,
   - post-selection channels,
   - discriminator policy.

7. `ExperimentTemplate`
   Combines:
   - targets,
   - sequence body or direct backend sweep body,
   - sweep plan,
   - acquisition spec,
   - analysis contract,
   - calibration patch contract.

8. `Workflow`
   Multi-stage orchestration for:
   - readout calibration,
   - gate calibration,
   - active reset benchmarking,
   - autotune flows.

9. `Compiler`
   Resolves parameters and calibrated operation references into backend-neutral IR or directly into backend build plans.

10. `BackendAdapter`
    For now, the only production backend is QM.
    It should own:
    - QUA emission,
    - QM config application,
    - execution,
    - simulation,
    - backend capability reporting.

#### cQED-specific modeling requirements

The target architecture should explicitly model:

- multiple element families,
- multiple transitions (`ge`, `ef`, selective vs unselective),
- readout and discriminator state,
- active reset and readout-conditioned control,
- storage cavity displacements and number-selective operations,
- experiment families that differ only in sweep axis or state prep,
- physically meaningful operation references instead of raw pulse objects.

### Circuit / Gate Abstraction Analysis

#### Should `QuantumCircuit` be the main entry point?

Not by itself.

It is the right abstraction for sequence-shaped bodies, but it is not the right abstraction for the whole cQED workload.

A circuit works naturally for:

- Ramsey,
- echo,
- T1,
- active reset bodies,
- custom gate sequences,
- composed qubit + cavity protocols,
- tomography state-prep/readout skeletons.

It works less naturally as the only abstraction for:

- resonator spectroscopy,
- qubit spectroscopy,
- coarse multi-LO scans,
- power-frequency chevrons,
- multi-stage calibration workflows,
- adaptive readout calibration loops.

Those are better thought of as:

- a body template,
- plus one or more sweep axes,
- plus acquisition and analysis behavior.

#### What should count as a gate?

A gate should mean a physics-level operation with stable semantic identity.

Good examples:

- single-qubit rotation,
- frame update,
- idle,
- displacement,
- SNAP,
- SQR,
- calibrated readout acquisition.

Do not let "gate" become a synonym for any backend instruction.

I would use this terminology:

- `Operation` for all circuit nodes,
- `GateOperation` for unitary-like calibrated controls,
- `AcquireOperation` for readout,
- `ControlFlowOperation` for repeats / branches / labels if needed.

#### Should measurement be a gate?

It should be an operation in the sequence, but not treated as an ordinary unitary gate.

Measurement changes data flow, not just quantum state flow. It should carry:

- acquisition mode,
- output names,
- discriminator policy,
- backend capability requirements,
- whether branching is real-time or post-run.

So yes, it belongs in the sequence body, but it should be a distinct operation type such as `Acquire`.

#### How should sweeps be represented?

Not as fake gates.

Use symbolic parameters in the sequence body and bind them through `SweepPlan`.

Example:

- the sequence contains `wait("tau")`,
- the sweep plan defines `tau = linspace(...)`,
- the compiler decides loop nesting and backend lowering.

This is much clearer than encoding sweep behavior into ad hoc circuit metadata.

#### How should calibration-aware gates behave?

They should reference calibrated operation definitions, not own waveform samples.

For example:

- `Rotation(target="qubit", axis="x", angle=pi, transition="ge", family="ref")`
- `OperationRef("ge_ref_r180")`

The compiler resolves that against a calibration-backed operation library.

Waveforms belong in:

- pulse specs,
- pulse factory,
- pulse registry / backend pulse library,
- calibration store for primitive parameters.

They should not live inside user-facing gate objects.

#### How to support custom sequences without becoming too rigid

Provide two authoring levels:

1. Template-level APIs for common experiments.
2. A lightweight sequence builder for custom protocols.

Also provide one explicit escape hatch for backend-specific custom logic, for example:

- `backend_block(...)`,
- `qua_inline(...)`,
- or `CustomBackendStep`.

That keeps the system serious and practical instead of over-abstracted.

### Proposed User-Facing API Style

The API should be session-namespaced and task-oriented. Users should not need to import dozens of experiment classes for routine work.

#### 1. Qubit spectroscopy

```python
session = Session.open(
    sample="post_cavity_sample_A",
    cooldown="cd_2025_02_22",
    backend=QMBackend(host="10.157.36.68", cluster="Cluster_2"),
)

spec = session.exp.qubit.spectroscopy(
    frequency=sweep.linspace(6.13e9, 6.17e9, 81),
    drive_op="saturation",
    drive_amp=0.25,
    drive_duration_ns=2000,
    avg=1000,
)

result = spec.run()
analysis = spec.analyze(result)
```

#### 2. Power Rabi

```python
rabi = session.exp.qubit.power_rabi(
    op="ge_ref_r180",
    amplitude=sweep.linspace(-0.35, 0.35, 101),
    avg=2000,
)

result = rabi.run()
fit = rabi.analyze(result)
fit.commit_calibration()
```

#### 3. Ramsey

```python
ramsey = session.exp.qubit.ramsey(
    delay=sweep.linspace(16, 12000, 121, unit="ns"),
    detune_hz=0.2e6,
    avg=4000,
)

result = ramsey.run()
analysis = ramsey.analyze(result)
```

#### 4. Active reset

```python
reset = session.exp.reset.active(
    readout="resonator",
    qubit="qubit",
    pi_op="ge_ref_r180",
    iterations=4,
    branch="real_time_if_supported",
    avg=5000,
)

build = reset.build()
print(build.report.backend_capability)
result = reset.run()
```

#### 5. Custom composed sequence

```python
seq = (
    session.sequence("custom_probe")
    .rotate("qubit", axis="x", angle="pi/2")
    .wait("tau")
    .displace("storage", alpha=0.35 + 0.0j)
    .frame("qubit", phase="phi")
    .rotate("qubit", axis="x", angle="pi/2")
    .acquire("m0", readout="resonator", mode="iq")
)

exp = session.exp.from_sequence(
    seq,
    sweep={
        "tau": sweep.linspace(16, 6000, 101, unit="ns"),
        "phi": sweep.linspace(0.0, np.pi, 9),
    },
    avg=512,
    analysis="ramsey_like",
)
```

#### 6. Multi-parameter sweep

```python
chevron = session.exp.qubit.chevron(
    duration=sweep.linspace(16, 800, 80, unit="ns"),
    detune=sweep.linspace(-10e6, 10e6, 81),
    avg=500,
)

result = chevron.run()
chevron.plot(result)
```

### Proposed Directory / Module Layout

I would refactor toward this structure while keeping a `compat/` bridge for old imports:

```text
qubox_v2/
  api/
    __init__.py
    session.py
    experiments.py
    sequence.py
    sweep.py
  session/
    session.py
    sample_registry.py
    runtime.py
    artifacts.py
  targets/
    refs.py
    bindings.py
    frequency_plan.py
  operations/
    base.py
    drive.py
    cavity.py
    readout.py
    control_flow.py
  sequence/
    circuit.py
    parameters.py
    sweeps.py
    protocols.py
    visualization.py
  experiments/
    templates/
      spectroscopy.py
      time_domain.py
      readout.py
      cavity.py
      tomography.py
      reset.py
    workflows/
      readout_calibration.py
      gate_calibration.py
      autotune.py
    analysis_contracts.py
  compiler/
    ir.py
    resolver.py
    lowering.py
    reports.py
  backends/
    base.py
    qm/
      adapter.py
      qua_lowering.py
      config.py
      execution.py
      simulation.py
      capabilities.py
  calibration/
    store.py
    models.py
    operation_library.py
    measurement.py
    patches.py
    workflows.py
  analysis/
    fitters.py
    models.py
    pipelines/
    plotting/
  data/
    models.py
    repository.py
    artifacts.py
  compat/
    legacy_experiments.py
    legacy_measurement.py
    legacy_session.py
```

Key intent:

- one stable public surface under `api/`,
- backend-neutral experiment model above `backends/`,
- readout / calibration separated from compiler,
- workflows separated from single experiments,
- compatibility isolated instead of mixed through the core path.

### Documentation Strategy

#### 1. Add a short root README

It should answer only:

1. What is qubox?
2. What problem does it solve?
3. What is the primary user workflow?
4. How do I start a session?
5. How do I run one standard experiment?
6. Where do I go next?

#### 2. Split docs by user intent

Recommended doc set:

- Getting Started
- Concepts: session, targets, operations, sequences, sweeps, workflows
- Experiment Cookbook: "I want to run X"
- Calibration Workflows
- Backend Behavior: QM / QUA specifics and limitations
- Custom Experiment Authoring
- Data, Artifacts, and Reproducibility
- Migration Guide from legacy experiment classes

#### 3. Add a cookbook index by physics task

This is the most important adoption document. It should be a direct mapping:

- I want resonator spectroscopy
- I want qubit spectroscopy
- I want power Rabi
- I want Ramsey
- I want T1
- I want readout GE discrimination
- I want butterfly
- I want active reset
- I want storage spectroscopy
- I want a custom sequence

Each page should show:

- the API call,
- required calibrations,
- expected outputs,
- common pitfalls,
- how to inspect the compiled QUA.

#### 4. Document calibration workflows as workflows, not loose experiments

Readout calibration, gate calibration, and reset benchmarking should each have:

- prerequisite state,
- recommended order,
- expected artifact files,
- what gets patched,
- how to preview before commit,
- what to do when quality gates fail.

#### 5. Document backend-specific behavior explicitly

The QM backend docs should explain:

- what is compiled at build time,
- what is resolved from calibration at compile time,
- what requires real-time branching support,
- what remains analysis-only,
- how simulator-backed validation works,
- known QUA-related limitations.

Also create the missing `limitations/qua_related_limitations.md` when real issues are confirmed.

### Migration Roadmap

#### Quick wins

1. Add a root `README.md`.
2. Declare one official top-level API path and mark everything else as compatibility or advanced.
3. Make `SessionManager` docs match its actual strict context-mode constructor.
4. Either adopt `experiments/configs.py` for real or remove it from the advertised API.
5. Stop silent fallback from circuit path to legacy builder path in experiments such as `PowerRabi` and `T1Relaxation`; fail loudly when a requested path is unavailable.
6. Create an executable simulator-backed trust suite from `standard_experiments.md`.
7. Unify run artifact saving behind one default repository contract.

#### Medium-term structural changes

1. Introduce `ExperimentTemplate`, `SweepPlan`, and `AcquisitionSpec`.
2. Wrap `measureMacro` behind a session-owned measurement runtime object, then route all new code through that wrapper.
3. Make `CalibrationStore` the only accepted calibration truth for new code.
4. Convert a small representative set of experiments to the new model first:
   - qubit spectroscopy,
   - resonator spectroscopy,
   - power Rabi,
   - Ramsey,
   - GE discrimination,
   - active reset.
5. Move multi-stage calibrations into `experiments/workflows/`.
6. Merge or retire overlapping pulse management surfaces (`PulseOperationManager` vs `PulseRegistry`) behind one canonical operation library.

#### Long-term redesign steps

1. Retire the old `CircuitRunner.compile(...)` dispatch path.
2. Promote the new compiler path so sequence-shaped experiments all compile through one lowering engine.
3. Replace `cQED_attributes` with a pure compatibility snapshot generated from `CalibrationStore`.
4. Make `MeasurementConfig` or its successor the only readout configuration object for new code.
5. Keep a backend escape hatch, but make the backend adapter boundary explicit enough that future backends are possible.

### Risks / Tradeoffs

1. If you over-center the design on circuits, spectroscopy and calibration workflows will become awkward and verbose.
2. If you over-center the design on backend agnosticism too early, you will weaken QM correctness and inspectability.
3. If you remove `measureMacro` abruptly, you risk breaking mature readout workflows before the replacement is proven.
4. If you keep too many compatibility layers alive for too long, the refactor will not actually simplify the user experience.
5. If typed config objects are made mandatory too early, notebook iteration may feel slower. Provide config objects and ergonomic keyword sugar together during migration.

### Final Recommendations

1. Keep the current sample / cooldown context and `CalibrationStore` foundation. Those are worth preserving.
2. Promote a single primary user API based on experiment templates, not dozens of directly imported classes.
3. Use `QuantumCircuit` as the sequence-body abstraction for custom and sequence-shaped protocols, not as the universal top-level abstraction.
4. Model sweeps, acquisition, and workflows explicitly instead of smuggling them through circuit metadata or giant experiment classes.
5. Make calibrated operations references, not waveform owners.
6. Replace the global measurement singleton with a session-owned measurement runtime as the default path for all new code.
7. Consolidate on one compiler path and one artifact path.
8. Make the `standard_experiments.md` trust protocol executable and simulator-backed before expanding the abstraction surface further.

## Bottom Line

The refactor should not start by inventing a new grand abstraction. It should start by choosing which of the existing good ideas become canonical.

The most defensible target is:

- `Session` as the lab/runtime entry point,
- experiment templates as the main user API,
- sequences / circuits for ordered custom protocols,
- sweeps and acquisition as first-class orthogonal objects,
- calibration-backed operation references,
- one QM backend adapter,
- one consistent artifact and analysis pipeline.

That will make the framework easier for experimentalists without sacrificing the backend faithfulness that matters for real cQED work.
