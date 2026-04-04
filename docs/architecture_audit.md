# qubox — Full Structural Overview

**Date**: 2026-04-02
**Version**: 3.0.0
**Python**: 3.12.10
**Hardware**: OPX+ + Octave, QUA API v1.2.6
**Server**: `10.157.36.68`, Cluster `Cluster_2`

> Note: As of 2026-04-04, the standalone `qubox.compile` and
> `qubox.simulation` packages described in parts of this audit were removed
> from `qubox` and are being split toward `cqed_sim`. The older gate-model,
> fidelity, noise, and gate-sequence side of `qubox.gates` was also removed,
> leaving only the runtime hardware gate layer. References to those paths below
> are historical snapshots of the earlier repository state.

---

## 1. What qubox Is

qubox is a Python framework for circuit-QED (cQED) experimental design, execution, analysis, and
extension targeting Quantum Machines hardware. It compiles high-level experiment descriptions into
QUA programs, runs them on real hardware or the QM simulator, and collects results.

Three co-distributed packages live in this repository:

| Package | Role | File count |
|---------|------|------------|
| `qubox` | Core framework: sessions, experiments, calibration, QUA compilation, hardware control | ~181 `.py` |
| `qubox_tools` | Post-experiment analysis: fitting, plotting, algorithms, optimization | ~24 `.py` |
| `qubox_lab_mcp` | Lab MCP server for external tool / agent integration | ~38 `.py` |

---

## 2. Repository Layout

```
e:\qubox\
├── qubox/                      Main Python package
│   ├── __init__.py             Public API (18 symbols)
│   ├── artifacts.py            Persistence helpers
│   ├── preflight.py            Pre-run validation
│   ├── schemas.py              Schema migration
│   │
│   ├── core/                   Foundation: errors, types, protocols, config, persistence
│   ├── session/                Session lifecycle: Session, SessionFactory
│   ├── experiments/            48+ experiment classes across 8 physics domains
│   │   ├── base.py             ExperimentBase ABC
│   │   ├── experiment_base.py  Extended base with build/run/analyze lifecycle
│   │   ├── session.py          SessionManager (infrastructure container)
│   │   ├── result.py           ProgramBuildResult, ExperimentResult
│   │   ├── configs.py          Experiment config helpers
│   │   ├── multi_program.py    Multi-program execution
│   │   ├── templates/          ExperimentLibrary registry
│   │   ├── workflows/          WorkflowLibrary registry
│   │   ├── calibration/        Readout, gate, reset calibration experiments
│   │   ├── cavity/             Fock state, storage experiments
│   │   ├── spectroscopy/       Resonator, qubit spectroscopy
│   │   ├── time_domain/        Rabi, Ramsey, T1, T2, chevron
│   │   ├── tomography/         Qubit, Wigner, Fock tomography
│   │   ├── spa/                SPA flux optimization
│   │   └── custom/             User-defined experiment entry points
│   │
│   ├── programs/               QUA program construction
│   │   ├── builders/           30+ raw QUA builder functions (8 domain modules)
│   │   ├── macros/             measureMacro, sequenceMacros
│   │   ├── gate_lowerers/      GateLowerer protocol + built-in lowerers
│   │   ├── circuit_ir.py       12 frozen IR dataclasses
│   │   ├── circuit_compiler.py CircuitCompiler (generic gate→QUA)
│   │   ├── circuit_runner.py   CircuitRunner (legacy name-dispatch)
│   │   ├── circuit_execution.py Circuit execution helpers
│   │   ├── circuit_display.py  Circuit diagram rendering
│   │   ├── circuit_postprocess.py Result post-processing
│   │   ├── circuit_protocols.py  Circuit-level protocols
│   │   └── sweep_strategies.py Sweep strategy protocol
│   │
│   ├── gates/                  Gate abstraction layer
│   │   ├── model_base.py       GateModel ABC (physics: unitaries, Kraus, superop)
│   │   ├── hardware_base.py    GateHardware ABC (QUA: build + play waveforms)
│   │   ├── gate.py             Gate container (model + hw pairing)
│   │   ├── models/             4 concrete models: Displacement, QubitRotation, SNAP, SQR
│   │   ├── hardware/           4 concrete hardware: Displacement, QubitRotation, SNAP, SQR
│   │   ├── contexts.py         ModelContext, NoiseConfig
│   │   ├── noise.py            QubitT1T2Noise noise model
│   │   ├── liouville.py        Liouville superoperator math
│   │   ├── fidelity.py         Gate fidelity metrics
│   │   ├── sequence.py         GateSequence collections
│   │   ├── cache.py            ModelCache for computed unitaries
│   │   ├── hash_utils.py       Deterministic hashing
│   │   └── free_evolution.py   Idle/free-evolution gate
│   │
│   ├── simulation/             QuTiP-based cQED simulation (standalone, no qubox deps)
│   │   ├── cQED.py             circuitQED class (cavity-transmon model)
│   │   ├── drive_builder.py    DriveGenerator (builds drive dicts for mesolve)
│   │   ├── hamiltonian_builder.py  Rotating-frame Hamiltonian construction
│   │   └── solver.py           solve_lindblad() wrapper around qutip.mesolve
│   │
│   ├── compile/                Numerical gate sequence optimizer
│   │   ├── api.py              compile_with_ansatz() entry point
│   │   ├── templates.py        5 gate templates (displacement, rotation, SNAP, SQR, idle)
│   │   ├── ansatz.py           Ansatz builder (gate sequence structure)
│   │   ├── param_space.py      ParamBlock, ParamSpace (parameter bounds)
│   │   ├── objectives.py       ObjectiveConfig, make_objective()
│   │   ├── evaluators.py       Forward simulation evaluators
│   │   ├── optimizers.py       OptimizerConfig, run_optimization()
│   │   ├── structure_search.py Structure search (optimal gate count)
│   │   ├── gpu_accelerators.py JAX-based GPU acceleration
│   │   └── gpu_utils.py        CuPy array transfer utilities
│   │
│   ├── calibration/            Calibration subsystem
│   │   ├── store.py            CalibrationStore (JSON-backed, transactional, v5.1.0)
│   │   ├── store_models.py     Pydantic store data models
│   │   ├── models.py           CalibrationSnapshot, CalibrationProposal
│   │   ├── orchestrator.py     CalibrationOrchestrator (run→analyze→patch→apply)
│   │   ├── contracts.py        Calibration validation contracts
│   │   ├── transitions.py      State transition utilities
│   │   ├── patch_rules.py      10 patch rules for auto-updating calibration
│   │   ├── history.py          Calibration history tracking
│   │   ├── algorithms.py       Calibration algorithms
│   │   ├── mixer_calibration.py Manual mixer calibration (separate calibration_db.json)
│   │   └── pulse_train_tomo.py Pulse-train tomography helpers
│   │
│   ├── hardware/               QM hardware interface
│   │   ├── controller.py       HardwareController (QM connection, thread-safe RLock)
│   │   ├── config_engine.py    ConfigEngine (5-layer config merger)
│   │   ├── program_runner.py   ProgramRunner (QUA execute + simulate)
│   │   └── queue_manager.py    QueueManager (job queuing)
│   │
│   ├── pulses/                 Pulse/waveform management
│   │   ├── manager.py          PulseOperationManager (dual permanent/volatile store)
│   │   ├── factory.py          PulseFactory (compiles spec → waveforms)
│   │   ├── models.py           PulseOp, waveform data models
│   │   ├── spec_models.py      Pulse specification models
│   │   ├── pulse_registry.py   PulseRegistry (name→spec mapping)
│   │   ├── waveforms.py        Waveform generation utilities
│   │   └── integration_weights.py  Demodulation weights
│   │
│   ├── sequence/               New high-level IR
│   │   ├── models.py           Operation, Condition, Sequence (frozen dataclasses)
│   │   ├── sweeps.py           SweepAxis, SweepPlan, SweepFactory
│   │   └── acquisition.py      AcquisitionSpec
│   │
│   ├── circuit/                Circuit-level IR (thin wrapper on sequence)
│   │   └── models.py           QuantumCircuit, QuantumGate
│   │
│   ├── data/                   Execution data models
│   │   └── models.py           ExecutionRequest, ExperimentResult, RunManifest
│   │
│   ├── backends/               Backend execution engines
│   │   └── qm/
│   │       ├── lowering.py     lower_to_legacy_circuit() (Sequence→IR)
│   │       └── runtime.py      QMRuntime (31 template adapters + custom path)
│   │
│   ├── devices/                External instrument management
│   │   ├── registry.py         SampleRegistry, SampleInfo
│   │   ├── device_manager.py   DeviceManager
│   │   └── context_resolver.py ContextResolver
│   │
│   ├── notebook/               Notebook-facing import surface
│   │   ├── __init__.py         Re-exports ~60 symbols for notebooks
│   │   ├── advanced.py         Infrastructure/debugging exports
│   │   ├── runtime.py          Runtime helpers
│   │   └── workflow.py         Workflow stage management
│   │
│   ├── operations/             Operation factory
│   │   └── library.py          OperationLibrary (x90, x180, displacement, measure, etc.)
│   │
│   ├── workflow/               Multi-stage workflow helpers
│   │   ├── stages.py           StageCheckpoint, save/load
│   │   ├── calibration_helpers.py  Calibration workflow helpers
│   │   ├── fit_gates.py        Fit quality gating
│   │   └── pulse_seeding.py    Pulse template seeding
│   │
│   ├── tools/                  Internal waveform generators
│   │   ├── generators.py       Displacement validation, seeding
│   │   └── waveforms.py        DRAG, Kaiser, Gaussian pulse generators
│   │
│   ├── verification/           Automated verification checks
│   │   ├── schema_checks.py    Schema validation
│   │   ├── waveform_regression.py  Waveform determinism checks
│   │   └── persistence_verifier.py Persistence round-trip verification
│   │
│   ├── gui/                    Optional GUI (stub)
│   ├── migration/              Schema migration (stub)
│   ├── autotune/               Auto-tuning (single script)
│   ├── examples/               3 demo scripts
│   └── tests/                  In-package tests (5 files)
│
├── qubox_tools/                Analysis & fitting package
│   ├── algorithms/             Core, metrics, pipelines, post-processing, transforms
│   ├── data/                   Output, OutputArray containers
│   ├── fitting/                calibration, cqed, models, pulse_train, routines
│   ├── optimization/           bayesian, local, stochastic
│   └── plotting/               common, cqed
│
├── qubox_lab_mcp/              Lab MCP server
│   ├── server.py               MCP server entry point
│   ├── services.py             Service layer
│   ├── adapters/               6 adapters (decomposition, filesystem, JSON, notebook, etc.)
│   ├── models/                 Result models
│   ├── policies/               Path and safety policies
│   ├── resources/              5 resource providers
│   ├── tools/                  6 MCP tools
│   └── tests/                  5 test files
│
├── tools/                      Developer/agent utilities
│   ├── validate_qua.py         Quick QUA structural checks
│   ├── analyze_imports.py      Import graph analysis
│   ├── build_context_notebook.py  Context notebook builder
│   ├── log_prompt.py           Prompt logging
│   └── ...                     8 more validation/conversion scripts
│
├── tests/                      Top-level test suite
│   ├── test_standard_experiments.py
│   ├── test_notebook_runtime.py
│   ├── test_notebook_workflow.py
│   ├── test_qubox_public_api.py
│   ├── test_schemas.py
│   ├── gate_architecture/      Gate architecture tests
│   └── qubox_tools/            qubox_tools tests
│
├── notebooks/                  33 Jupyter notebooks (usage examples)
├── tutorials/                  1 getting-started tutorial
├── docs/                       Extended documentation, SVG diagrams
├── past_prompt/                36 prompt logs (append-only)
├── samples/                    Sample data files
├── site_docs/                  MkDocs source pages
├── site/                       Built MkDocs HTML
│
├── pyproject.toml              Build config, dependencies, ruff/pytest
├── mkdocs.yml                  Documentation site config
├── AGENTS.md                   Agent policy document
├── API_REFERENCE.md            Public API reference
├── CLAUDE.md                   Claude-specific instructions
├── README.md                   Project README
├── standard_experiments.md     Trust gates for QUA validation
└── SURVEY.md                   Codebase survey
```

---

## 3. Dependency Layers

Packages are organized bottom-to-top. Each layer only imports from layers below it.

```
Layer 0 — Foundations (no qubox imports)
├── qubox/core/          Errors, types, protocols, config, persistence, logging
└── qubox/simulation/    circuitQED, DriveGenerator, solver (only uses numpy/qutip/scipy)

Layer 1 — Infrastructure (imports: core)
├── qubox/hardware/      HardwareController, ConfigEngine, ProgramRunner, QueueManager
├── qubox/pulses/        PulseOperationManager, PulseFactory, PulseRegistry
└── qubox/tools/         Waveform generators, validation helpers

Layer 2 — Domain Models (imports: core, pulses)
├── qubox/gates/         GateModel ABC, GateHardware ABC, 4+4 concrete implementations
├── qubox/calibration/   CalibrationStore, Orchestrator, models, patch rules
├── qubox/sequence/      Operation, Condition, Sequence, SweepAxis, SweepPlan
├── qubox/circuit/       QuantumCircuit, QuantumGate (thin wrapper on sequence)
└── qubox/data/          ExecutionRequest, ExperimentResult, RunManifest

Layer 3 — Compilation (imports: core, gates, pulses, tools)
├── qubox/compile/       compile_with_ansatz, templates, evaluators, optimizers, GPU accel
└── qubox/programs/      CircuitCompiler, CircuitRunner, builders, macros, gate_lowerers, IR

Layer 4 — Experiments (imports: everything above)
├── qubox/experiments/   ExperimentBase, SessionManager, 48+ experiment classes
└── qubox/devices/       SampleRegistry, DeviceManager, ContextResolver

Layer 5 — Execution (imports: everything above)
├── qubox/backends/qm/   QMRuntime (31 template adapters), lowering (Sequence→IR)
└── qubox/operations/    OperationLibrary (calibration-aware Operation factory)

Layer 6 — User Surface (imports: everything above)
├── qubox/session/       Session, SessionFactory (top-level entry point)
├── qubox/notebook/      Notebook import surface (~60 re-exports)
└── qubox/__init__.py    Public API (18 symbols)
```

**Known cross-layer imports** (not strictly layered):
- `calibration/orchestrator.py` → `programs/macros/measure.py` (deferred import)
- `programs/` → `experiments/result.py` for `ProgramBuildResult`

---

## 4. Public API (18 symbols)

Exported from `qubox/__init__.py`:

| Symbol | Source | Purpose |
|--------|--------|---------|
| `Session` | `session/session.py` | Primary user entry point; wraps SessionManager |
| `SessionFactory` | `session/session.py` | Programmatic session creation for agents/automation |
| `SessionProtocol` | `core/protocols.py` | Structural typing contract for Session |
| `Operation` | `sequence/models.py` | Frozen intent: "do X to target Y with params Z" |
| `Condition` | `sequence/models.py` | Conditional execution predicate |
| `Sequence` | `sequence/models.py` | Ordered list of Operations |
| `QuantumCircuit` | `circuit/models.py` | Circuit-level wrapper (converts to Sequence) |
| `QuantumGate` | `circuit/models.py` | Circuit-level gate (extends Operation) |
| `SweepAxis` | `sequence/sweeps.py` | Parameter sweep definition |
| `SweepPlan` | `sequence/sweeps.py` | Multi-axis sweep specification |
| `AcquisitionSpec` | `sequence/acquisition.py` | What to measure and how |
| `ExecutionRequest` | `data/models.py` | Immutable execution specification |
| `ExperimentResult` | `data/models.py` | Immutable execution output |
| `RunManifest` | `data/models.py` | Provenance metadata (git SHA, hardware hash, versions) |
| `CalibrationSnapshot` | `calibration/models.py` | Point-in-time calibration capture |
| `CalibrationProposal` | `calibration/models.py` | Proposed calibration update |
| `DeviceMetadata` | `core/device_metadata.py` | Device identification |
| `__version__` | `__init__.py` | `"3.0.0"` |

---

## 5. Core Protocols

All defined in `qubox/core/protocols.py` using `typing.Protocol` (structural subtyping — implementations don't inherit).

| Protocol | Methods | Satisfied by |
|----------|---------|-------------|
| `SessionProtocol` | `hardware`, `config_engine`, `calibration`, `pulse_mgr`, `runner`, `devices`, `orchestrator`, `simulation_mode`, `experiment_path`, `context_snapshot()`, `resolve_alias()`, `resolve_center()`, `resolve_pulse_length()`, `resolve_discrimination()`, `get_thermalization_clks()`, `connect()`, `close()` | `Session`, `SessionManager` |
| `HardwareController` | `set_element_lo()`, `set_element_fq()`, `set_octave_output()`, `set_octave_gain()`, `get_element_lo()`, `get_element_if()`, `calculate_el_if_fq()` | `hardware/controller.py::HardwareController` |
| `ProgramRunner` | `run_program()`, `simulate()`, `halt_job()` | `hardware/program_runner.py::ProgramRunner` |
| `ConfigEngine` | `load_hardware()`, `save_hardware()`, `build_qm_config()`, `apply_changes()` | `hardware/config_engine.py::ConfigEngine` |
| `PulseManager` | `add_waveform()`, `add_pulse()`, `burn_to_config()` | `pulses/manager.py::PulseOperationManager` |
| `DeviceController` | `get()`, `apply()`, `exists()` | `devices/device_manager.py::DeviceManager` |
| `Experiment` | `name`, `build_program()`, `simulate()`, `run()`, `process()` | All experiment classes |

Additional protocols in other modules:

| Protocol | Location | Purpose |
|----------|----------|---------|
| `CompilationContext` | `programs/gate_lowerers/protocol.py` | Exposes compiler internals to gate lowerers |
| `GateLowerer` | `programs/gate_lowerers/protocol.py` | `__call__(ctx, gate, ...)` — pluggable gate→QUA handler |

---

## 6. Key Class Hierarchies

### 6a. Gate Layer (`qubox/gates/`)

The cleanest-designed subsystem. Two parallel hierarchies with auto-registration:

```
GateModel (ABC, model_base.py)          GateHardware (ABC, hardware_base.py)
├── DisplacementModel                   ├── DisplacementHardware
├── QubitRotationModel                  ├── QubitRotationHardware
├── SNAPModel                           ├── SNAPHardware
├── SQRModel                            ├── SQRHardware
└── FreeEvolutionModel                  └── (no hw counterpart)
```

**GateModel** provides physics: `unitary(ctx) → ndarray`, `kraus(ctx)`, `superop(ctx)`, `duration_s()`, `key()`, `to_dict()`/`from_dict()`. Auto-registers via `__init_subclass__` into `_MODEL_REGISTRY[gate_type]`.

**GateHardware** provides QUA: `build(session, *, pulse_mgr, config)` (registers waveforms), `play(session, *, targets)` (emits QUA statements), `waveforms() → dict`. Auto-registers into `_HARDWARE_REGISTRY[gate_type]`.

**Gate** (`gate.py`): Simple container pairing `model: GateModel` + `hw: Optional[GateHardware]`. No conversion logic — just co-location.

**Supporting classes:**
- `ModelContext` (`contexts.py`): Physics parameters (chi, chi2, chi3, Kerr, Nc, Nq — all in Hz)
- `NoiseConfig` (`contexts.py`): T1, T2 decoherence parameters
- `ModelCache` (`cache.py`): LRU cache for computed unitaries/superoperators
- `GateSequence` (`sequence.py`): Ordered list of Gates with aggregate operations
- `QubitT1T2Noise` (`noise.py`): Lindblad noise model for evaluators

### 6b. Simulation Layer (`qubox/simulation/`)

Completely standalone — zero imports from any other qubox package.

**`circuitQED`** (`cQED.py`): Full cavity-transmon system model.
- Constructor: `cavity_freq, qubit_freq, qubit_anharmonicity, cavity_T, qubit_T1, qubit_T2, Nc, Nq, chi, chi2, kerr, kerr2, drives` — all frequencies in **rad/s**
- QuTiP operators: `a`, `adag`, `b`, `bdag`, `nc`, `nq`, projectors, sigma, parity
- Ideal unitaries: `U_displacement(alpha)`, `U_snap(thetas)`, `apply_ideal_sequence()`
- Drive management: `add_drive()`, `_drive_envelope()`, `_collect_terms()`
- Hamiltonian: `construct_hamiltonian()` → `build_rotated_hamiltonian()` (rotating frame + RWA)
- Analysis: `cavity_reduced()`, `get_cavity_populations()`, `get_qubit_populations()`

**`DriveGenerator`** (`drive_builder.py`): Builds drive dicts for `circuitQED._collect_terms()`.
- `cavity_displacement(beta, duration, t0, ...)` — displacement pulse
- `qubit_rotation_tp(theta, phi, duration, t0, ...)` — qubit rotation
- `snap(thetas, T, d_lambda, d_alpha, d_omega, t0, ...)` — multi-tone SNAP
- `sqr_tp(thetas, phis, T, d_lambda, d_alpha, d_omega, t0, ...)` — selective qubit rotation
- `idle(duration, t0, ...)` — zero-amplitude placeholder

All methods return dicts with keys: `{name, channel, carrier_freq, amplitude, envelope_type, envelope_params, encoding, t0, duration}`.

**`solve_lindblad()`** (`solver.py`): Wrapper around `qutip.mesolve()`.

### 6c. Compile Layer (`qubox/compile/`)

Numerical optimizer for gate sequences. Produces `GateModel` lists but does not deploy to hardware.

- `compile_with_ansatz(target, sys_params, ...)` → optimized `list[GateModel]`
- Uses `ModelContext` + `ModelCache` from gates layer
- 5 gate templates: displacement, rotation, SNAP, SQR, idle
- Evaluators: forward simulation of gate sequences → fidelity
- GPU acceleration: JAX-based monkey-patching of evaluator functions

### 6d. Programs Layer (`qubox/programs/`)

QUA program construction. Two compilation paths:

**Path A — Raw QUA Builders** (`programs/builders/`):
8 domain modules with 30+ hand-written QUA builder functions. Each accepts experiment parameters + `ReadoutHandle`, opens `with program() as prog:`, emits QUA statements, returns the program. Battle-tested production code.

| Module | Domains |
|--------|---------|
| `spectroscopy.py` | Resonator spectroscopy, qubit spectroscopy |
| `time_domain.py` | Rabi, Ramsey, T1, T2, chevron, ac Stark, residual photon |
| `calibration.py` | AllXY, randomized benchmarking, DRAG calibration |
| `cavity.py` | Fock state prep, storage experiments |
| `readout.py` | IQ blobs, butterfly measurement |
| `tomography.py` | Qubit, Wigner, Fock tomography |
| `utility.py` | Continuous wave |
| `simulation.py` | Simulation-specific gate builders |

**Path B — CircuitCompiler** (`circuit_compiler.py`):
Generic gate→QUA compilation with pluggable `GateLowerer` registry. Takes `QuantumCircuit` (IR), iterates gates, dispatches each to its registered lowerer.

**Circuit IR** (`circuit_ir.py`): 12 frozen dataclasses forming the compilation intermediate representation:
- `Gate` — `(name, target, params, condition, metadata)`
- `QuantumCircuit` — ordered gates + `MeasurementSchema` + `CircuitBlock`s
- `MeasurementRecord`, `MeasurementSchema`, `StreamSpec` — measurement specification
- `CalibrationReference`, `ParameterSource` — parameter resolution chain
- `GateCondition`, `ConditionalGate` — conditional execution
- `SweepAxis`, `SweepSpec` — sweep parameters
- `CircuitBuildResult` — compilation output

**measureMacro** (`macros/measure.py`, ~1400 lines): Class-level singleton for measurement QUA emission. Recently made instantiable (Phase 2 refactor) but primarily used as classmethod singleton. ~20 class-level attributes mutated during compilation.

### 6e. Experiments Layer (`qubox/experiments/`)

**`ExperimentBase`** (`base.py`): ABC for all experiments.
- `build_program(**params) → ProgramBuildResult`
- `run_program(n_avg, **params) → RunResult`
- `simulate_program(**params) → SimulationResult`
- `analyze(**params)` — post-processing

48+ concrete experiments across 8 physics domains:

| Domain | Experiments |
|--------|------------|
| `spectroscopy/` | `ResonatorSpectroscopy`, `QubitSpectroscopy` |
| `time_domain/` | `Rabi`, `Ramsey`, `T1Relaxation`, `T2Echo`, `Chevron` |
| `calibration/gates` | `AllXYCalibration`, `RandomizedBenchmarking`, `DragCalibration` |
| `calibration/readout` | `IQBlobsExperiment`, `ReadoutOptimization` |
| `calibration/reset` | `ActiveResetCalibration` |
| `cavity/` | `FockStatePreparation`, `NumberSplittingSpectroscopy`, `CavityACStark` |
| `tomography/` | `QubitTomography`, `WignerTomography`, `FockTomography` |
| `spa/` | `SPAFluxOptimization` |

**`SessionManager`** (`session.py`): Heavy infrastructure container that `Session` wraps. Manages all subsystems: `HardwareController`, `ConfigEngine`, `CalibrationStore`, `PulseOperationManager`, `ProgramRunner`, `DeviceManager`, `CalibrationOrchestrator`.

### 6f. Calibration Layer (`qubox/calibration/`)

- **`CalibrationStore`** (`store.py`): JSON-backed typed store (v5.1.0). Transactional: snapshot → patch → commit/rollback. Supports nested key paths, type coercion, version migration.
- **`CalibrationOrchestrator`** (`orchestrator.py`): Lifecycle: run experiment → analyze results → generate patch → apply (with rollback). Uses `PatchRule` pattern.
- **10 patch rules** (`patch_rules.py`): Auto-update calibration values based on experiment results.
- **`CalibrationSnapshot`** (`models.py`): Frozen point-in-time capture. `from_session(session)` factory. `to_dict()` for serialization.
- **`CalibrationProposal`** (`models.py`): Proposed calibration change with validation.
- **`ManualMixerCalibrator`** (`mixer_calibration.py`): Separate calibration_db.json for Octave mixer corrections.

### 6g. Hardware Layer (`qubox/hardware/`)

All depend only on `core/`. Thread-safe.

- **`HardwareController`** (`controller.py`): Live QM connection via `QuantumMachinesManager`. Thread-safe with `RLock`. LO/IF/gain/Octave control.
- **`ConfigEngine`** (`config_engine.py`): 5-layer config merger. Layers: base hardware → calibration overlay → pulse volatile → experiment patch → runtime override.
- **`ProgramRunner`** (`program_runner.py`): QUA execution (`run_program`) + simulation (`simulate`). Job management, result fetching.
- **`QueueManager`** (`queue_manager.py`): Job queuing with priority and timeout.

### 6h. Session Layer (`qubox/session/`)

**`Session`** (`session.py`): Top-level user entry point. Thin facade over `SessionManager`.
- `Session.open(sample_id, cooldown_id, *, simulation_mode, connect, ...)` — factory method
- Properties: `.ops` (OperationLibrary), `.backend` (QMRuntime), `.calibration`, `.hardware`, etc.
- IR constructors: `.sequence()`, `.circuit()`, `.sweep`
- Delegation: most calls forward to `SessionManager._legacy`

**`SessionFactory`** (`session.py`): Frozen config for programmatic/agent session creation.
- `create(*, simulation_mode, connect, **overrides) → Session`

---

## 7. Execution Paths

### Path A: Template Experiments (Production)

```
ExperimentBase subclass
    → build_program(**params)
        → raw QUA builder function (programs/builders/*.py)
            → measureMacro.measure() for readout
            → returns QUA program
    → ProgramRunner.run_program(qua_prog, n_total)
        → QM hardware executes
    → analyze(raw_output)
        → ExperimentResult
```

### Path B: Custom Sequences (New API)

```
Session.ops.x180("qubit") → Operation
Session.sequence().add(op) → Sequence
Session.backend.run(ExecutionRequest)
    → QMRuntime._run_custom()
        → lower_to_legacy_circuit(sequence) → circuit_ir.QuantumCircuit
        → CircuitCompiler(session).compile(circuit) → CircuitBuildResult
            → GateLowerer dispatch per gate type
            → QUA program
        → ProgramRunner.run_program()
    → ExperimentResult
```

### Path C: Numerical Optimization (Offline)

```
compile_with_ansatz(target_unitary, sys_params)
    → Ansatz (gate sequence template)
    → ParamSpace (parameter bounds)
    → run_optimization() → optimal GateModel list
    ⚠ No path to hardware deployment (gap)
```

---

## 8. Data Flow: Experiment Lifecycle

```
┌──────────────────────────────────────────────────────────────────────┐
│  User / Notebook / Agent                                             │
│  ┌──────────────┐                                                    │
│  │ Session.open()│─── Creates SessionManager with all subsystems     │
│  └──────┬───────┘                                                    │
│         │                                                            │
│  ┌──────▼───────────────────────────────────────────────────┐        │
│  │ Session.ops.x180("qubit")  →  Operation(kind="x180")    │        │
│  │ Session.ops.displacement("storage", alpha=2+1j)          │        │
│  │ Session.ops.measure("readout")                           │        │
│  └──────┬───────────────────────────────────────────────────┘        │
│         │                                                            │
│  ┌──────▼───────────────────────────────────────────────────┐        │
│  │ seq = Session.sequence()                                 │        │
│  │ seq.add(op1); seq.add(op2); seq.add(op3)                │        │
│  │                                        → Sequence        │        │
│  └──────┬───────────────────────────────────────────────────┘        │
│         │                                                            │
│  ┌──────▼───────────────────────────────────────────────────┐        │
│  │ sweep = Session.sweep.param("theta").linspace(0, π, 50)  │        │
│  │ acq = AcquisitionSpec(...)                               │        │
│  │ req = ExecutionRequest(sequence=seq, sweep=sweep, acq=acq│)       │
│  └──────┬───────────────────────────────────────────────────┘        │
│         │                                                            │
│  ┌──────▼───────────────────────────────────────────────────┐        │
│  │ Session.backend.run(req)                                 │        │
│  │   → QMRuntime._run_custom(req)                           │        │
│  │     → lower_to_legacy_circuit(req.sequence)              │        │
│  │       → circuit_ir.QuantumCircuit                        │        │
│  │     → CircuitCompiler(session).compile(circuit)          │        │
│  │       → GateLowerer dispatch: displacement_lowerer(...)  │        │
│  │       → GateLowerer dispatch: rotation_lowerer(...)      │        │
│  │       → MeasurementLowerer(...)                          │        │
│  │       → CircuitBuildResult (QUA program + metadata)      │        │
│  │     → ProgramRunner.run_program(qua_prog)                │        │
│  │       → QM hardware / simulator executes                 │        │
│  │     → RunManifest (provenance: git SHA, cal snapshot)    │        │
│  │   → ExperimentResult                                     │        │
│  └──────────────────────────────────────────────────────────┘        │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 9. Three Disconnected Physics Layers

The codebase has three representations of "what a gate does" with **no bridge between them**:

| Layer | Location | Units | Representation | Purpose |
|-------|----------|-------|----------------|---------|
| **Simulation** | `simulation/` | rad/s, continuous time | QuTiP operators, analytical envelopes → `mesolve` | Predict quantum state evolution |
| **Model** | `gates/models/` | Hz, discrete | scipy `expm` unitaries, Kraus operators | Ideal gate math, fidelity computation |
| **Hardware** | `gates/hardware/` | DAC samples, QM config | Discrete I/Q waveforms → QUA `play()` | Emit waveforms on real hardware |

**Parameter mapping example — SNAP gate:**

| Parameter | Simulation (`DriveGenerator.snap`) | Model (`SNAPModel`) | Hardware (`SNAPHardware`) |
|-----------|------------------------------------|---------------------|--------------------------|
| Per-Fock phases | `thetas` | `angles` | `angles` |
| Calibration tweaks | `d_lambda, d_alpha, d_omega` | — | `d_lambda, d_alpha, d_omega` |
| Fock detunings | `n * sys.chi` (rad/s) | `n * ctx.chi` (Hz) | `att.st_chi/chi2/chi3` (Hz) or calibrated `fock_fqs` |
| Duration | Explicit `T` (seconds) | `duration_s()` (computed) | Implicit from calibrated template |
| Envelope | Analytical Gaussian multi-tone (callable) | — | Discrete samples from calibrated template |

No transfer functions exist. The gap is currently bridged by shared parameter names and manual consistency.

---

## 10. External Dependencies

From `pyproject.toml`:

**Core (always required):**
- `numpy>=1.24`, `scipy>=1.10`, `matplotlib>=3.7` — numerical/scientific stack
- `pydantic>=2.0` — data validation models
- `qm-qua>=1.1`, `qualang-tools>=0.15` — Quantum Machines QUA API
- `tqdm>=4.65` — progress bars
- `pandas>=2.0` — data analysis
- `PyYAML>=6.0` — YAML config parsing

**Optional extras:**
- `simulation`: `qutip>=5.0` — quantum state simulation
- `gpu`: `jax[cuda12]>=0.4`, `jaxlib>=0.4` — GPU-accelerated gate compilation
- `gui`: `PyQt5>=5.15` — interactive GUI
- `dev`: `pytest>=7.0`, `pytest-cov`, `ruff`, `ipykernel`, `jupyter`
- `mcp`: `mcp[cli]>=1.2.0` — lab MCP server

---

## 11. Test Coverage

**Test locations:**
- `tests/` — 8 top-level test files (standard experiments, notebooks, public API, schemas, gate architecture, qubox_tools)
- `qubox/tests/` — 5 in-package tests (calibration, parameter resolution, workflow safety)
- `qubox_lab_mcp/tests/` — 5 MCP adapter tests

**Current baseline:** 55 passing, 8 pre-existing failures (DummySession gaps, notebook runtime missing `.hardware`, public API assertion drift).

**Major coverage gaps:**
- Sequence IR construction and validation
- Circuit compilation pipeline end-to-end
- AcquisitionSpec behavior
- DeviceManager lifecycle
- Output save/load round-trip
- CalibrationOrchestrator rollback
- Error paths (connection drop, stale calibration, job failure)

---

## 12. Architectural Patterns

| Pattern | Where | Description |
|---------|-------|-------------|
| Auto-registration via `__init_subclass__` | `GateModel`, `GateHardware` | Subclasses auto-register into type registries by `gate_type` |
| Frozen dataclasses | IR types, configs, results, context objects | Immutability for hardware-controlling data |
| Pydantic v2 models | `HardwareConfig`, pulse specs, calibration store models | Validated config parsing with migration |
| Structural subtyping (Protocol) | `core/protocols.py` | Contracts without inheritance; mockable for testing |
| Dual ResourceStore | `PulseOperationManager` | Permanent (calibrated) + volatile (per-compilation) waveform stores |
| 5-layer config merge | `ConfigEngine` | base → calibration → pulse volatile → experiment → runtime |
| Template adapter | `QMRuntime` (31 adapters) | Maps `ExecutionRequest` to legacy experiment constructors |
| Pluggable gate lowerers | `CircuitCompiler` | Register `GateLowerer` callables per gate type |
| Transactional calibration | `CalibrationStore` | Snapshot → patch → commit/rollback |
| Monkey-patching GPU accel | `compile/gpu_accelerators.py` | Replaces evaluator functions at runtime for JAX speedup |

---

## 13. Known Architectural Gaps

| Gap | Impact | Status |
|-----|--------|--------|
| **No simulation ↔ hardware bridge** | Cannot translate between simulation drives and hardware gates | Planned (`qubox/bridge/`) |
| **measureMacro singleton** | No concurrent compilation, no reproducibility | Partially mitigated (made instantiable); full extraction planned |
| **compile/ output has no deployment path** | `compile_with_ansatz()` produces `GateModel` lists but cannot generate QUA | Planned (Phase 4 of bridge plan) |
| **No SNAP lowerer in CircuitCompiler** | SNAP gates cannot go through the generic compilation path | Planned |
| **Operation ≈ Gate duplication** | `sequence/models.py::Operation` and `circuit_ir.py::Gate` are near-identical | Planned unification |
| **Session typed as Any in experiments** | No static checking of session capabilities | `SessionProtocol` added but not yet universally applied |

---

## 14. Completed Refactoring (Phase 0–5, 2026-04-02)

All 6 phases from the original architecture audit are complete:

| Phase | What was done |
|-------|--------------|
| **Phase 0** | Deleted 4 duplicate modules (`session/context.py`, `session/state.py`, `core/persistence_policy.py`, `devices/sample_registry.py`) |
| **Phase 1** | `SessionProtocol` typing on `ExperimentBase`/`CircuitCompiler`/`Orchestrator`; `CalibrationSnapshot.from_session()` |
| **Phase 2** | `measureMacro` made instantiable; `CircuitCompiler` uses per-instance when `measurement_config` provided |
| **Phase 3** | IR types extracted to `circuit_ir.py` (12 frozen dataclasses); `CircuitRunner.compile()` deprecated; call sites migrated to `CircuitCompiler` |
| **Phase 4** | Version dedup (`qubox.__version__`), `mixer_calibration_path` on `CalibrationSnapshot`, `sanitize_nonfinite` utility |
| **Phase 5** | `SessionFactory` dataclass for agent/programmatic sessions; public API now 18 symbols |

---

## 15. File Statistics

| Category | Count |
|----------|-------|
| Python files in `qubox/` | ~181 |
| Python files in `qubox_tools/` | ~24 |
| Python files in `qubox_lab_mcp/` | ~38 |
| Developer tools (`tools/`) | 12 |
| Test files (all locations) | 18 |
| Jupyter notebooks | 34 |
| Experiment classes | 48+ |
| Raw QUA builders | 30+ |
| Gate model types | 5 (Displacement, QubitRotation, SNAP, SQR, FreeEvolution) |
| Gate hardware types | 4 (Displacement, QubitRotation, SNAP, SQR) |
| Template adapters in QMRuntime | 31 |
| Calibration patch rules | 10 |
| Public API symbols | 18 |
| Core protocols | 7 |
