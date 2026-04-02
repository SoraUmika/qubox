# qubox — API Reference

**Version**: 3.0.0
**Date**: 2026-03-14
**Status**: Governing Document

**Changelog**:
- v3.0.0 — Package migration from `qubox_v2` to `qubox`. New user-facing API
  with `Session`, `Sequence`, `QuantumCircuit`, `SweepFactory`,
  `OperationLibrary`, `ExperimentLibrary`, `CalibrationProposal`, and
  `ExperimentResult`. The legacy `qubox_v2` runtime is preserved as
  `qubox_v2_legacy` and drives the QM backend adapter internally.
  All public imports now originate from `qubox`.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Package Architecture](#2-package-architecture)
3. [Main User Workflow](#3-main-user-workflow)
4. [Public Entry Points](#4-public-entry-points)
5. [Session](#5-session)
6. [Sequence IR](#6-sequence-ir)
7. [Sweep System](#7-sweep-system)
8. [Acquisition System](#8-acquisition-system)
9. [Operation Library](#9-operation-library)
10. [Circuit IR](#10-circuit-ir)
11. [Experiment Library](#11-experiment-library)
12. [Workflow Library](#12-workflow-library)
13. [Execution & Results](#13-execution--results)
14. [Calibration](#14-calibration)
15. [Analysis Pipelines](#15-analysis-pipelines)
16. [QM Backend Runtime](#16-qm-backend-runtime)
17. [Notebook Import Surface (qubox.notebook)](#17-notebook-import-surface-quboxnotebook)
18. [Workflow Primitives (qubox.workflow)](#18-workflow-primitives-quboxworkflow)
19. [qubox_tools — Analysis Toolkit](#19-qubox_tools--analysis-toolkit)
20. [Legacy Internals (qubox_v2_legacy)](#20-legacy-internals-qubox_v2_legacy)
21. [Examples and Minimal Usage Patterns](#21-examples-and-minimal-usage-patterns)
22. [Known Gaps and Inconsistencies](#22-known-gaps-and-inconsistencies)

**Appendices:**

- [Appendix A: Top-Level Exports](#appendix-a-top-level-exports)
- [Appendix B: Quick-Reference Cheat Sheet](#appendix-b-quick-reference-cheat-sheet)
- [Appendix C: Migration Guide from qubox\_v2](#appendix-c-migration-guide-from-qubox_v2)

---

## 1. Overview

### 1.1 What is qubox?

`qubox` is the canonical user-facing Python package for cQED (circuit quantum
electrodynamics) experiment orchestration. It provides a high-level,
composable API for:

- defining pulse sequences and quantum circuits,
- sweeping experiment parameters,
- running experiments on Quantum Machines OPX+ / Octave hardware,
- collecting and inspecting results,
- performing calibration and applying parameter patches,
- and analyzing experiment outputs.

`qubox` v3.0.0 replaces the earlier `qubox_v2` package. The runtime backend
still delegates to the rename-preserved `qubox_v2_legacy` package, but all
user-facing imports and workflows now originate from `qubox`.

### 1.2 Repository Surface

The repository contains three relevant Python packages:

| Package | Purpose |
|---------|---------|
| `qubox` | **Primary user-facing API** — sessions, experiments, sequences, circuits, calibration, results |
| `qubox_tools` | **Analysis toolkit** — fitting, plotting, post-processing, optimization helpers |
| `qubox_v2_legacy` | **Internal backend** — legacy runtime, hardware drivers, QUA compilation (not for direct user import) |

### 1.3 Supported Stack

- **Hardware target**: Quantum Machines OPX+ with Octave
- **QUA / QM API version**: `1.2.6`
- **Python**: 3.12.10 via the workspace `.venv` or a global 3.12.10 interpreter (required), 3.11.8 (fallback)

---

## 2. Package Architecture

### 2.1 Full Repository Structure

```
qubox/                          ─── Main package (public API + implementation)
├── __init__.py                      Top-level exports (Session, Sequence, etc.)
│
├── session/                         Session lifecycle
│   ├── context.py                     Session runtime context
│   ├── session.py                     Session class — the main entry point
│   └── state.py                       Session state tracking
│
├── experiments/                     High-level experiment classes
│   ├── experiment_base.py             ExperimentBase lifecycle (build → run → analyze)
│   ├── result.py                      ProgramBuildResult, AnalysisResult, FitResult
│   ├── session.py                     Session management for experiments
│   ├── configs.py                     Experiment configuration models
│   ├── config_builder.py              Configuration builder utilities
│   ├── multi_program.py               Multi-program orchestration
│   │
│   ├── spectroscopy/                  Spectroscopy experiments
│   │   ├── resonator.py                 ResonatorSpectroscopy, ResonatorPowerSpectroscopy
│   │   └── qubit.py                     QubitSpectroscopy, QubitSpectroscopyEF
│   ├── time_domain/                   Time-domain experiments
│   │   ├── rabi.py                      PowerRabi, TemporalRabi
│   │   ├── relaxation.py               T1Relaxation
│   │   ├── coherence.py                T2Ramsey, T2Echo
│   │   └── chevron.py                  TimeRabiChevron, PowerRabiChevron, RamseyChevron
│   ├── calibration/                   Calibration experiments
│   │   ├── gates.py                     AllXY, DRAGCalibration
│   │   ├── readout.py                   IQBlob, ReadoutGEDiscrimination, ReadoutButterflyMeasurement
│   │   ├── readout_config.py            Readout configuration models
│   │   └── reset.py                     QubitResetBenchmark, ActiveQubitResetBenchmark
│   ├── cavity/                        Cavity / storage experiments
│   │   ├── storage.py                   StorageSpectroscopy, StorageCoherence, ...
│   │   └── fock.py                      Fock-manifold-resolved measurements
│   ├── tomography/                    Tomography experiments
│   │   ├── qubit_tomo.py               QubitStateTomography
│   │   ├── fock_tomo.py                FockResolvedStateTomography
│   │   └── wigner_tomo.py              StorageWignerTomography
│   ├── spa/                           SPA readout experiments
│   │   └── flux_optimization.py         SPAFluxOptimization
│   ├── templates/
│   │   └── library.py                  ExperimentLibrary (20 template experiments)
│   ├── workflows/
│   │   └── library.py                  WorkflowLibrary (readout workflows)
│   └── custom/                        Custom experiment stubs
│
├── programs/                        QUA program compilation
│   ├── api.py                         Stable builder export surface
│   ├── measurement.py                 Measurement emission and state rules
│   ├── spectroscopy.py                Spectroscopy program runners
│   ├── time_domain.py                 Time-domain protocol runners (Rabi, echo, ...)
│   ├── readout.py                     Readout pulse play and data collection
│   ├── tomography.py                  Tomography protocol runners
│   ├── calibration.py                 Calibration protocol runners
│   ├── cavity.py                      Storage cavity manipulation programs
│   ├── gate_tuning.py                 Gate parameter tuning runners
│   ├── circuit_compiler.py            Quantum circuit → QUA compilation
│   ├── circuit_runner.py              Circuit runner with legacy compatibility
│   ├── circuit_display.py             Circuit visualization
│   ├── circuit_execution.py           Circuit execution runners
│   ├── circuit_postprocess.py         Post-execution circuit analysis
│   ├── circuit_protocols.py           Circuit protocol definitions
│   │
│   ├── builders/                      QUA program builders (per-domain)
│   │   ├── spectroscopy.py              Resonator/qubit spectroscopy builders
│   │   ├── time_domain.py               temporal_rabi(), power_rabi(), chevron, echo
│   │   ├── readout.py                   iq_blobs(), readout_trace()
│   │   ├── calibration.py               sequential_qb_rotations()
│   │   ├── cavity.py                    storage_spectroscopy()
│   │   ├── tomography.py               qubit_state_tomography()
│   │   ├── simulation.py               Simulation-specific QUA builders
│   │   └── utility.py                  Shared builder utilities
│   │
│   └── macros/                        Reusable QUA code snippets
│       ├── measure.py                   measureMacro class + emit_measurement()
│       └── sequence.py                  sequenceMacros — Ramsey, echo, conditional reset
│
├── calibration/                     Calibration orchestration
│   ├── orchestrator.py                CalibrationOrchestrator — runs calibration, applies patches
│   ├── patch_rules.py                 Patch rule definitions and application logic
│   ├── store.py                       CalibrationStore — persists calibration data (JSON)
│   ├── store_models.py                CalibrationSnapshot, CalibratedElementSnapshot
│   ├── history.py                     CalibrationHistory — audit trail and versioning
│   ├── transitions.py                 Transition — frequency transition definitions (ge, ef)
│   ├── algorithms.py                  Calibration algorithms
│   ├── mixer_calibration.py           Mixer correction workflows
│   ├── contracts.py                   FitResult contract enforcement
│   ├── pulse_train_tomo.py            Pulse train tomography for gate calibration
│   └── models.py                      Calibration data models
│
├── core/                            Infrastructure: bindings, schemas, logging, state
│   ├── bindings.py                    ChannelRef, ReadoutHandle, ExperimentBindings
│   ├── hardware_definition.py         HardwareDefinition — notebook-facing hardware setup
│   ├── experiment_context.py          Experiment runtime context
│   ├── hardware_context.py            Hardware state and connectivity
│   ├── session_state.py               Session lifecycle state
│   ├── measurement_config.py          Measurement protocol configuration
│   ├── config.py                      Configuration management
│   ├── schemas.py                     JSON schema versioning and migration
│   ├── device_metadata.py             External device metadata
│   ├── persistence.py                 File I/O and data persistence
│   ├── persistence_policy.py          Persistence contract enforcement
│   ├── artifacts.py                   Artifact management
│   ├── artifact_manager.py            Artifact lifecycle and versioning
│   ├── protocols.py                   Protocol definitions
│   ├── errors.py                      QuboxError, ConfigError, ConnectionError, ...
│   ├── preflight.py                   Pre-execution validation
│   ├── logging.py                     Logging utilities
│   └── types.py                       Core type annotations
│
├── hardware/                        OPX+ / Octave control
│   ├── controller.py                  HardwareController — hardware command execution
│   ├── program_runner.py              ProgramRunner — QUA execution (real + simulated)
│   ├── queue_manager.py               Job queuing and orchestration
│   └── config_engine.py               QM config generation from hardware definition
│
├── pulses/                          Pulse management and waveform generation
│   ├── manager.py                     PulseOp — pulse operation and orchestration
│   ├── factory.py                     Pulse creation factories
│   ├── pulse_registry.py              Pulse registration and lookup
│   ├── models.py                      Pulse data models (Gaussian, DRAG, ...)
│   ├── spec_models.py                 Pulse specification models
│   ├── waveforms.py                   Waveform generation (sin, cos, envelope, ...)
│   └── integration_weights.py         Per-pulse integration weight definitions
│
├── gates/                           Gate physics and caching
│   ├── gate.py                        Gate base class and protocols
│   ├── hardware_base.py               Base hardware gate class
│   ├── model_base.py                  Base mathematical model class
│   ├── fidelity.py                    Fidelity prediction and fitting
│   ├── free_evolution.py              Free-evolution gate models
│   ├── liouville.py                   Liouville superoperator channels
│   ├── noise.py                       Noise models for gate operations
│   ├── cache.py                       Gate fidelity caching
│   ├── contexts.py                    Gate context (hardware state, calibration point)
│   ├── sequence.py                    Gate sequences and chains
│   ├── hash_utils.py                  Gate parameterization hashing
│   │
│   ├── hardware/                      Hardware gate implementations
│   │   ├── displacement.py              Displacement gate
│   │   ├── qubit_rotation.py            Qubit XY-plane rotations
│   │   ├── snap.py                      SNAP gate
│   │   └── sqr.py                       SQR gate (context-aware)
│   │
│   └── models/                        Mathematical gate models
│       ├── displacement.py              Displacement models
│       ├── qubit_rotation.py            Rotation models
│       ├── snap.py                      SNAP models
│       └── sqr.py                       SQR models
│
├── simulation/                      cQED simulation
│   ├── cQED.py                        cQED Hamiltonian and system definitions
│   ├── drive_builder.py               Drive Hamiltonian construction
│   ├── hamiltonian_builder.py         Full Hamiltonian assembly
│   └── solver.py                      ODE solver for cQED dynamics
│
├── compile/                         Circuit compilation and optimization
│   ├── api.py                         Public compilation API
│   ├── ansatz.py                      Ansatz specification
│   ├── evaluators.py                  Compilation objective evaluators
│   ├── objectives.py                  Compilation objective functions
│   ├── optimizers.py                  Circuit optimization algorithms
│   ├── param_space.py                 Parameter space definitions
│   ├── structure_search.py            Automated circuit structure search
│   ├── templates.py                   Compilation templates
│   ├── gpu_accelerators.py            GPU-accelerated compilation (CUDA)
│   └── gpu_utils.py                   GPU utilities and device detection
│
├── sequence/                        Sweep plans, acquisitions, sequence control
│   ├── models.py                      Operation, Condition, Sequence
│   ├── sweeps.py                      SweepAxis, SweepPlan, SweepFactory
│   └── acquisition.py                 AcquisitionSpec, AcquisitionFactory
│
├── circuit/                         Higher-level circuit model
│   └── models.py                      QuantumCircuit, QuantumGate
│
├── data/                            Execution requests and results
│   └── models.py                      ExecutionRequest, ExperimentResult
│
├── backends/                        Backend adapters
│   └── qm/
│       ├── lowering.py                  Lowers circuit → legacy IR
│       └── runtime.py                   LegacyExperimentAdapter
│
├── devices/                         External device integration
│   ├── device_manager.py              DeviceManager — multi-device orchestration
│   ├── registry.py                    Device registration and lookup
│   ├── context_resolver.py            Device parameter resolution
│   └── sample_registry.py             Sample-specific device configuration
│
├── verification/                    Validation and regression
│   ├── schema_checks.py              JSON schema validation
│   ├── persistence_verifier.py        Persistence contract verification
│   └── waveform_regression.py         Waveform generation regression tests
│
├── workflow/                        Multi-stage orchestration
│   ├── stages.py                      Stage checkpoints, workflow config
│   ├── calibration_helpers.py         Calibration workflow helpers
│   ├── fit_gates.py                   fit_quality_gate(), fit_center_inside_window()
│   └── pulse_seeding.py               Initial pulse parameter seeding
│
├── notebook/                        Notebook-facing import surface
│   ├── __init__.py                    30+ experiment re-exports, session helpers
│   ├── advanced.py                    Infrastructure imports
│   ├── runtime.py                     Notebook runtime integration
│   └── workflow.py                    Workflow orchestration for notebooks
│
├── autotune/                        Automated tuning
│   └── run_post_cavity_autotune_v1_1.py  Post-cavity autotune workflow
│
├── gui/                             Visualization
│   └── program_gui.py                Program/circuit visualization
│
└── examples/                        Reference implementations
    ├── quickstart.py                  Basic session startup demo
    ├── session_startup_demo.py        Session initialization demo
    └── circuit_architecture_demo.py   Circuit model demonstration
```

```
qubox_tools/                    ─── Analysis & Fitting Toolkit
├── algorithms/
│   ├── core.py                      Core algorithm utilities
│   ├── metrics.py                   Fidelity and quality metrics
│   ├── pipelines.py                 Named analysis pipelines (raw, iq_magnitude, ...)
│   ├── post_process.py              Signal post-processing
│   ├── post_selection.py            Post-selection filtering
│   ├── readout_analysis.py          Readout data analysis (Pe, posteriors, IQ consistency)
│   └── transforms.py               Signal transformations
├── fitting/
│   ├── cqed.py                      cQED model fits (T1, T2, Rabi, qubit_spec, ...)
│   ├── calibration.py               Calibration-specific fits
│   ├── models.py                    Fit model definitions (Lorentzian, Gaussian, ...)
│   ├── pulse_train.py               Pulse sequence fitting
│   └── routines.py                  fit_and_wrap(), generalized_fit()
├── optimization/
│   ├── bayesian.py                  Bayesian optimization
│   ├── local.py                     Local optimization (Nelder-Mead, ...)
│   └── stochastic.py               Stochastic optimization
├── plotting/
│   ├── common.py                    Common plotting utilities (plot_hm, ...)
│   └── cqed.py                      cQED visualizations (Bloch, Wigner, Fock)
└── data/
    └── containers.py                Output, OutputArray — data containers
```

```
qubox_lab_mcp/                  ─── Lab MCP Server
├── server.py                        MCP server implementation
├── config.py                        Server configuration
├── services.py                      Core services
├── errors.py                        Error classes
├── prompts.py                       MCP prompt definitions
├── adapters/                        Protocol adapters
│   ├── decomposition_adapter.py       Circuit decomposition
│   ├── filesystem_adapter.py          Filesystem browsing
│   ├── json_adapter.py                JSON data
│   ├── notebook_adapter.py            Jupyter notebook
│   ├── python_index_adapter.py        Python code indexing
│   └── run_adapter.py                 Experiment run
├── models/
│   └── results.py                   Result models
├── policies/
│   ├── path_policy.py               Filesystem path safety
│   └── safety_policy.py             General safety policies
├── resources/                       Resource loaders
└── tools/                           MCP tool definitions
```

```
tools/                          ─── Developer Utilities
├── test_all_simulations.py          Master simulation test suite (24 experiments)
├── validate_qua.py                  Compile + simulate QUA against hosted server
├── validate_standard_experiments_simulation.py  Standard experiment trust gates
├── log_prompt.py                    Log agent prompts to past_prompt/
├── analyze_imports.py               Import graph analysis
├── build_context_notebook.py        Notebook context builder
├── validate_circuit_runner_serialization.py  Circuit serialization validator
├── validate_gate_tuning_visualization.py  Gate tuning visualization
├── validate_notebooks.py            Notebook health checks
└── strip_raw_artifacts.py           Artifact cleaning utility
```

```
notebooks/                      ─── Sequential Experiment Workflows (00–27)
├── 00_hardware_defintion.ipynb      Hardware definition and session setup
├── 01_mixer_calibrations.ipynb      Mixer correction calibration
├── 02_time_of_flight.ipynb          Digital signal delay measurement
├── 03_resonator_spectroscopy.ipynb  Readout resonator characterization
├── 04_resonator_power_chevron.ipynb Power-dependent resonator shift
├── 05_qubit_spectroscopy_pulse_calibration.ipynb  Qubit freq + pulse calibration
├── 06_coherence_experiments.ipynb   T1 and T2 measurements
├── 07_cw_diagnostics.ipynb          Continuous-wave diagnostics
├── 08_pulse_waveform_definition.ipynb  Pulse envelope and waveform design
├── 09_qutrit_spectroscopy_calibration.ipynb  e-f transition frequency
├── 10_sideband_transitions.ipynb    Cavity-qubit sideband transitions
├── 11_coherence_2d_pump_sweeps.ipynb  2D pump-probe coherence
├── 12_chevron_experiments.ipynb     2D Rabi/Ramsey chevron plots
├── 13_dispersive_shift_measurement.ipynb  Qubit-cavity coupling parameter
├── 14_gate_calibration_benchmarking.ipynb  AllXY gate error benchmarking
├── 15_qubit_state_tomography.ipynb  Qubit state reconstruction
├── 16_readout_calibration.ipynb     Readout discriminator tuning
├── 17_readout_bayesian_optimization.ipynb  Bayesian readout optimization
├── 18_active_reset_benchmarking.ipynb  Active qubit reset validation
├── 19_spa_optimization.ipynb        SPA readout optimization
├── 20_readout_leakage_benchmarking.ipynb  Readout leakage measurement
├── 21_storage_cavity_characterization.ipynb  Storage cavity characterization
├── 22_fock_resolved_experiments.ipynb  Fock-number-resolved spectroscopy
├── 23_quantum_state_preparation.ipynb  Deterministic Fock state prep
├── 24_free_evolution_tomography.ipynb  Coherence over free evolution
├── 25_context_aware_sqr_calibration.ipynb  Context-dependent SQR calibration
├── 26_sequential_simulation.ipynb   Sequential simulator-only experiments
└── 27_cluster_state_evolution.ipynb Cluster state entanglement evolution
```

### 2.2 Subpackage Summary

| Subpackage | Purpose |
|------------|---------|
| `qubox.session` | `Session` — runtime entry point; owns sweep/acquire factories, operation and experiment libraries |
| `qubox.experiments` | `ExperimentBase` and 24+ experiment subclasses organized by physics domain (spectroscopy, time-domain, calibration, cavity, tomography, SPA) |
| `qubox.programs` | QUA program compilation: domain-specific builders, measurement/sequence macros, circuit compiler/runner |
| `qubox.programs.builders` | Per-domain QUA builder functions: `spectroscopy`, `time_domain`, `readout`, `calibration`, `cavity`, `tomography` |
| `qubox.programs.macros` | Reusable QUA snippets: `measureMacro` (readout singleton + `emit_measurement()`), `sequenceMacros` (Ramsey, echo, reset) |
| `qubox.calibration` | `CalibrationOrchestrator`, `CalibrationStore`, patch rules, history, transitions — full calibration lifecycle |
| `qubox.core` | Infrastructure: `ReadoutHandle`, `ExperimentBindings`, hardware definition, schemas, persistence, error hierarchy |
| `qubox.hardware` | `HardwareController`, `ProgramRunner`, `QueueManager`, `ConfigEngine` — OPX+/Octave control layer |
| `qubox.pulses` | `PulseOp`, waveform generation (Gaussian, DRAG, Kaiser, ...), integration weights, pulse registry |
| `qubox.gates` | Gate physics: displacement, SNAP, SQR, qubit rotations — hardware implementations + mathematical models + fidelity/noise |
| `qubox.simulation` | cQED Hamiltonian construction and ODE solver for numerical simulation |
| `qubox.compile` | Circuit compilation: ansatz specs, parameter-space optimizers, GPU-accelerated structure search |
| `qubox.sequence` | Intermediate representation: `Operation`, `Condition`, `Sequence`, `SweepAxis`, `SweepPlan`, `AcquisitionSpec` |
| `qubox.circuit` | `QuantumCircuit` and `QuantumGate` — gate-sequence view over the Sequence IR |
| `qubox.data` | `ExecutionRequest` and `ExperimentResult` — run specification and result containers |
| `qubox.backends.qm` | `QMRuntime` — lowers sequences/circuits to QUA programs via legacy adapter |
| `qubox.devices` | `DeviceManager` — external device orchestration (SignalCore, OctoDac), sample registry |
| `qubox.verification` | Schema checks, persistence verification, waveform regression tests |
| `qubox.workflow` | Portable workflow primitives: stage checkpoints, fit gates, patch preview, pulse seeding |
| `qubox.notebook` | Primary notebook import surface: 30+ experiment re-exports, session helpers, waveform tools |
| `qubox.autotune` | Automated post-cavity tuning workflow |
| `qubox.gui` | Program/circuit visualization |
| `qubox_tools` | **Separate package** — fitting (cQED models), plotting (Bloch/Wigner), signal processing, optimization |
| `qubox_lab_mcp` | **Separate package** — Lab MCP server: adapters, resources, tools for external tool integration |

### 2.3 Layering

```
┌──────────────────────────────────────────────────────────────┐
│  User Notebook / Script                                      │
│    from qubox import Session / from qubox.notebook import ... │
├──────────────────────────────────────────────────────────────┤
│  qubox.session         (Session — public API entry point)     │
│  qubox.experiments     (ExperimentLibrary + 24 templates)     │
│  qubox.sequence        (Operation, Sequence, SweepAxis)       │
│  qubox.circuit         (QuantumCircuit, QuantumGate)          │
├──────────────────────────────────────────────────────────────┤
│  qubox.programs        (QUA builders, macros, circuit runner) │
│  qubox.calibration     (CalibrationOrchestrator, Store)       │
│  qubox.pulses          (PulseOp, waveform generation)         │
│  qubox.hardware        (HardwareController, ProgramRunner)    │
├──────────────────────────────────────────────────────────────┤
│  qubox.gates           (gate physics, fidelity, models)       │
│  qubox.simulation      (cQED Hamiltonian, ODE solver)         │
│  qubox.compile         (circuit optimization, GPU accel)      │
├──────────────────────────────────────────────────────────────┤
│  qubox.backends.qm     (QMRuntime — lowers to QUA)           │
│  qubox.core            (bindings, schemas, persistence)       │
├──────────────────────────────────────────────────────────────┤
│  Quantum Machines QUA / OPX+ / Octave                        │
└──────────────────────────────────────────────────────────────┘
           │                                    │
    qubox_tools                          qubox_lab_mcp
    (fitting, plotting,                  (MCP server for
     optimization)                        external tools)
```

Users should only import from `qubox` and `qubox_tools`.
Access to `qubox_v2_legacy` internals is available through
`session.legacy_session` for advanced or transitional use cases.

---

## 3. Main User Workflow

The intended workflow through the `qubox` API:

```
1. Open a session           →  Session.open(...)
2. Build sweep / acquire    →  session.sweep.linspace(...)
                               session.acquire.iq(...)
3. Run a template experiment→  session.exp.qubit.spectroscopy(...)
   — OR — compose a custom  →  seq = session.sequence()
   sequence / circuit           seq.add(session.ops.x180("qubit"))
                               session.exp.custom(sequence=seq, ...)
4. Inspect results          →  result.inspect(), result.plot()
5. Propose calibration      →  proposal = result.proposal()
   updates                     proposal.review()
6. Apply patch              →  proposal.apply(session)
7. Close session            →  session.close()
```

### Diagram

```
Session.open()
    │
    ├── session.exp.qubit.spectroscopy(...)  ─────┐
    │                                             │
    ├── session.sequence()                        │
    │     .add(session.ops.x180(...))             │
    │     session.exp.custom(sequence=...)  ──────┤
    │                                             │
    ├── session.circuit()                         │
    │     .add(session.ops.displacement(...))     │
    │     session.exp.custom(circuit=...)   ──────┤
    │                                             ▼
    │                                      ExperimentResult
    │                                          │
    │                                    .inspect() / .plot()
    │                                    .proposal()
    │                                          │
    │                                  CalibrationProposal
    │                                    .review() / .apply(session)
    │
Session.close()
```

---

## 4. Public Entry Points

All user-facing objects are importable directly from `qubox`:

```python
from qubox import (
    # Session
    Session,
    # Sequence IR
    Sequence,
    Operation,
    Condition,
    # Sweep
    SweepAxis,
    SweepPlan,
    # Acquisition
    AcquisitionSpec,
    # Circuit
    QuantumCircuit,
    QuantumGate,
    # Data
    ExecutionRequest,
    ExperimentResult,
    # Calibration
    CalibrationSnapshot,
    CalibrationProposal,
)
```

The package version is available as `qubox.__version__` (currently `"3.0.0"`).

---

## 5. Session

### 5.1 Import

```python
from qubox import Session
```

### 5.2 Opening a Session

```python
session = Session.open(
    sample_id="post_cavity_sample_A",
    cooldown_id="cd_2025_02_22",
    registry_base="E:/qubox",
    qop_ip="10.157.36.68",
    cluster_name="Cluster_2",
)
# Default: simulation_mode=True (safe, no RF outputs)
# For real hardware: simulation_mode=False
```

**`Session.open()` Signature:**

```python
@classmethod
def open(
    cls,
    *,
    sample_id: str,
    cooldown_id: str,
    registry_base: str | Path | None = None,
    simulation_mode: bool = True,
    connect: bool = True,
    **kwargs,
) -> Session
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `sample_id` | `str` | Identifier for the sample (maps to a directory under `samples/`) |
| `cooldown_id` | `str` | Identifier for the cooldown cycle |
| `registry_base` | `str \| Path \| None` | Root directory of the registry (defaults to cwd) |
| `simulation_mode` | `bool` | If `True` (default), no `QuantumMachine` is created and RF outputs stay off.  Pass `False` for real hardware execution. |
| `connect` | `bool` | If `True`, opens the QM connection immediately. If `False`, the session is created but not connected. |
| `**kwargs` | | Forwarded to the legacy `SessionManager` (e.g. `qop_ip`, `cluster_name`, `load_devices`, `auto_save_calibration`) |

**Returns:** `Session` instance.

### 5.3 Session Properties and Methods

| Member | Type | Description |
|--------|------|-------------|
| `session.sweep` | `SweepFactory` | Factory for building sweep axes and plans |
| `session.acquire` | `AcquisitionFactory` | Factory for building acquisition specs |
| `session.ops` | `OperationLibrary` | Semantic operations (gates, waits, measures, resets) |
| `session.gates` | `OperationLibrary` | Alias for `session.ops` |
| `session.exp` | `ExperimentLibrary` | Template-based experiment runners |
| `session.workflow` | `WorkflowLibrary` | Multi-step workflows (e.g. full readout calibration) |
| `session.backend` | `QMRuntime` | Backend runtime (lazily initialized) |
| `session.legacy_session` | `SessionManager` | Access to the underlying legacy runtime *(advanced use)* |
| `session.hardware` | `HardwareController` | Element LO/IF/gain, QM instance |
| `session.config_engine` | `ConfigEngine` | Load / save / build QM config dicts |
| `session.calibration` | `CalibrationStore` | Frequency, coherence, discrimination data |
| `session.pulse_mgr` | `PulseOperationManager` | Pulse operation registry |
| `session.runner` | `ProgramRunner` | Execute / simulate QUA programs |
| `session.devices` | `DeviceManager` | External device lifecycle |
| `session.orchestrator` | `CalibrationOrchestrator` | Experiment → calibration pipeline |
| `session.simulation_mode` | `bool` | True if session was opened in simulation mode |

**Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `session.sequence()` | `(name="sequence", **metadata) → Sequence` | Create a new empty `Sequence` |
| `session.circuit()` | `(name="circuit", **metadata) → QuantumCircuit` | Create a new empty `QuantumCircuit` |
| `session.connect()` | `() → Session` | Open the QM connection (if not already open) |
| `session.close()` | `() → None` | Teardown: close QM connection, save state |
| `session.resolve_alias()` | `(alias, *, role_hint=None) → str` | Map a role alias (e.g. `"qubit"`) to a hardware element name |
| `session.resolve_center()` | `(center) → float` | Map a frequency token (e.g. `"q0.ge"`) to a frequency in Hz |
| `session.ensure_sweep_plan()` | `(value, *, averaging=1) → SweepPlan` | Normalize a `SweepAxis` or `SweepPlan` into a `SweepPlan` |
| `session.resolve_pulse_length()` | `(target, op, *, default) → int \| None` | Look up the pulse length (ns) for a registered operation |
| `session.resolve_discrimination()` | `(readout) → DiscriminationParams \| None` | Get discrimination parameters for a readout element |
| `session.get_thermalization_clks()` | `(channel, default=None) → int \| None` | Get the thermalization wait in clock cycles for a channel |

### 5.4 Frequency Token Resolution

`session.resolve_center()` accepts string tokens to look up calibrated frequencies:

| Token | Resolves To |
|-------|-------------|
| `"qubit.ge"`, `"qb.ge"`, `"q0.ge"` | Qubit GE transition frequency (Hz) |
| `"qubit.ef"`, `"qb.ef"`, `"q0.ef"` | Qubit EF transition frequency (Hz) |
| `"readout"`, `"resonator"`, `"rr0"`, `"rr0.ro"` | Readout resonator frequency (Hz) |
| `"storage"`, `"st"`, `"storage.ge"` | Storage cavity frequency (Hz) |

### 5.5 Role Alias Resolution

`session.resolve_alias()` maps semantic role names to hardware element names
by querying the session context:

| Alias / role_hint | Maps to |
|-------------------|---------|
| `"qubit"`, `"qb"`, strings starting with `"q"` | `ctx.qb_el` |
| `"readout"`, `"ro"`, `"resonator"`, strings starting with `"rr"` | `ctx.ro_el` |
| `"storage"`, `"st"` | `ctx.st_el` |
| Any string already in `hardware_elements` | Returned as-is |

### 5.6 Legacy Session Access

For advanced use cases that require direct access to the underlying
`SessionManager` runtime:

```python
legacy = session.legacy_session

# Examples:
ctx = legacy.context_snapshot()
```

Common sub-systems are exposed as direct properties on `Session` itself
(`session.hardware`, `session.calibration`, `session.pulse_mgr`, etc.).
Use `session.legacy_session` only for attributes not surfaced directly.

---

## 6. Sequence IR

The core intermediate representation for composing experiment control sequences.

### 6.1 Operation

```python
from qubox import Operation
```

A frozen dataclass representing a single semantic control intent.

```python
@dataclass(frozen=True)
class Operation:
    kind: str                               # Operation type (e.g. "qubit_rotation", "measure", "idle")
    target: str | tuple[str, ...]           # Target element(s)
    params: dict[str, Any] = {}             # Type-specific parameters
    duration_clks: int | None = None        # Duration in clock cycles (4 ns each)
    tags: tuple[str, ...] = ()              # Annotation tags
    condition: Condition | None = None       # Conditional execution
    metadata: dict[str, Any] = {}           # Arbitrary metadata
    label: str | None = None                # Human-readable label
```

**Properties:**

| Property | Returns | Description |
|----------|---------|-------------|
| `.targets` | `tuple[str, ...]` | Always returns a tuple of target strings |

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `.with_condition(condition)` | `Operation` | Return a copy with the given condition attached |
| `.to_text_line(*, index)` | `str` | Human-readable single-line representation |

### 6.2 Condition

```python
from qubox import Condition
```

A frozen dataclass for conditional execution based on measurement outcomes.

```python
@dataclass(frozen=True)
class Condition:
    measurement_key: str            # Which measurement result to check
    source: str = "state"           # Data source within the measurement ("state", "I", etc.)
    comparator: str = "truthy"      # Comparison operator ("truthy", ">", "<", "==", etc.)
    value: Any = True               # Value to compare against
```

### 6.3 Sequence

```python
from qubox import Sequence
```

An ordered, mutable container for control operations.

```python
@dataclass
class Sequence:
    name: str = "sequence"
    operations: list[Operation] = []
    metadata: dict[str, Any] = {}
```

**Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `.add(operation)` | `(Operation) → Sequence` | Append one operation; returns self for chaining |
| `.extend(operations)` | `(list[Operation]) → Sequence` | Append multiple operations |
| `.repeat(count, operations, *, label=None)` | `→ Sequence` | Append `count` copies of the operation list |
| `.conditional(condition, operations, *, label=None)` | `→ Sequence` | Append operations with a condition attached |
| `.inspect()` | `() → str` | Human-readable text dump of the sequence |
| `.to_text()` | `() → str` | Same as `.inspect()` |

**Example:**

```python
seq = session.sequence("my_experiment")
seq.add(session.ops.x180("qubit"))
seq.add(session.ops.wait("qubit", 100))
seq.add(session.ops.measure("readout"))
print(seq.inspect())
```

---

## 7. Sweep System

### 7.1 SweepAxis

```python
from qubox import SweepAxis
```

A frozen dataclass representing a single swept parameter.

```python
@dataclass(frozen=True)
class SweepAxis:
    parameter: str                          # Name of the swept parameter
    values: tuple[Any, ...]                 # Sweep values
    spacing: str = "custom"                 # "custom", "linspace", "geomspace"
    center: str | float | None = None       # Optional center offset (token or Hz)
    unit: str | None = None                 # Physical unit label
    metadata: dict[str, Any] = {}
```

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `.as_array()` | `np.ndarray` | Convert values to a numpy array |

### 7.2 SweepPlan

```python
from qubox import SweepPlan
```

A frozen dataclass grouping one or more sweep axes with an averaging count.

```python
@dataclass(frozen=True)
class SweepPlan:
    axes: tuple[SweepAxis, ...] = ()
    averaging: int = 1
```

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `.primary_axis()` | `SweepAxis \| None` | Returns the first axis, or `None` if empty |

### 7.3 SweepFactory

Available on `session.sweep`.

```python
session.sweep  # → SweepFactory instance
```

**Methods:**

| Method | Signature | Returns |
|--------|-----------|---------|
| `.param(parameter)` | `(str) → SweepParameterBuilder` | Start building a sweep for the named parameter |
| `.values(values, *, parameter, center, unit)` | `→ SweepAxis` | Create axis from explicit values |
| `.linspace(start, stop, num, *, parameter, center, unit)` | `→ SweepAxis` | Create axis from linspace |
| `.geomspace(start, stop, num, *, parameter, center, unit)` | `→ SweepAxis` | Create axis from geomspace |
| `.grid(*axes, averaging=1)` | `→ SweepPlan` | Bundle axes into a multi-dimensional sweep plan |
| `.plan(*axes, averaging=1)` | `→ SweepPlan` | Alias for `.grid()` |

#### SweepParameterBuilder

Returned by `session.sweep.param("name")`. Provides typed constructors:

| Method | Signature | Returns |
|--------|-----------|---------|
| `.values(values, *, center, unit)` | `→ SweepAxis` | From explicit values |
| `.linspace(start, stop, num, *, center, unit)` | `→ SweepAxis` | From linspace |
| `.geomspace(start, stop, num, *, center, unit)` | `→ SweepAxis` | From geomspace |

**Example — centered frequency sweep:**

```python
freq_axis = session.sweep.linspace(-30e6, 30e6, 241, parameter="freq", center="q0.ge")
```

**Example — amplitude sweep with explicit values:**

```python
amp_axis = session.sweep.param("amplitude").linspace(0.01, 1.0, 50)
```

**Example — multi-axis grid:**

```python
plan = session.sweep.grid(
    session.sweep.linspace(0, 100, 51, parameter="delay"),
    session.sweep.linspace(0.0, 0.5, 20, parameter="amplitude"),
    averaging=500,
)
```

---

## 8. Acquisition System

### 8.1 AcquisitionSpec

```python
from qubox import AcquisitionSpec
```

A frozen dataclass specifying what kind of data to collect and from which target.

```python
@dataclass(frozen=True)
class AcquisitionSpec:
    kind: str                    # "iq", "classified", "population", "trace"
    target: str                  # Target element (e.g. "readout")
    operation: str = "readout"   # Pulse operation used for measurement
    key: str | None = None       # Custom key for the measurement record
```

### 8.2 AcquisitionFactory

Available on `session.acquire`.

```python
session.acquire  # → AcquisitionFactory instance
```

**Methods:**

| Method | Signature | Returns |
|--------|-----------|---------|
| `.iq(target, *, operation, key)` | `→ AcquisitionSpec` | Raw IQ data acquisition |
| `.classified(target, *, operation, key)` | `→ AcquisitionSpec` | State-classified acquisition |
| `.population(target, *, operation, key)` | `→ AcquisitionSpec` | Population (averaged state) |
| `.trace(target, *, operation, key)` | `→ AcquisitionSpec` | Full ADC trace |

**Example:**

```python
acquire = session.acquire.iq("readout")
result = session.exp.custom(sequence=seq, acquire=acquire, n_avg=500)
```

---

## 9. Operation Library

### 9.1 Import

Available on `session.ops` (and aliased as `session.gates`).

```python
session.ops  # → OperationLibrary instance
```

The `OperationLibrary` provides calibration-aware semantic operations. All
methods resolve target aliases through `session.resolve_alias()` and return
`Operation` or `QuantumGate` objects that can be added to a `Sequence` or
`QuantumCircuit`.

### 9.2 Qubit Rotations

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `.x90(target, *, op="x90")` | `→ QuantumGate` | π/2 rotation about X |
| `.x180(target, *, op="x180")` | `→ QuantumGate` | π rotation about X |
| `.y90(target, *, op="y90")` | `→ QuantumGate` | π/2 rotation about Y |
| `.y180(target, *, op="y180")` | `→ QuantumGate` | π rotation about Y |
| `.virtual_z(target, *, phase)` | `→ Operation` | Virtual Z rotation (frame update) |

**Example:**

```python
seq = session.sequence()
seq.add(session.ops.x90("qubit"))
seq.add(session.ops.virtual_z("qubit", phase=0.5))
seq.add(session.ops.x90("qubit"))
```

### 9.3 Idle / Wait

| Method | Signature | Returns |
|--------|-----------|---------|
| `.wait(target, duration, *, unit="clks")` | `→ Operation` |

The `unit` parameter can be `"clks"` (4 ns clock cycles) or `"ns"`.

### 9.4 Measurement

| Method | Signature | Returns |
|--------|-----------|---------|
| `.measure(target, *, mode="iq", operation="readout", key=None)` | `→ Operation` |

| Parameter | Description |
|-----------|-------------|
| `target` | Readout element alias (e.g. `"readout"`) |
| `mode` | Measurement mode: `"iq"`, `"classified"`, `"population"` |
| `operation` | Pulse operation name registered on the readout element |
| `key` | Custom key for the measurement record |

### 9.5 Generic Play

| Method | Signature | Returns |
|--------|-----------|---------|
| `.play(target, *, operation, amplitude=None, duration_clks=None, detune=None)` | `→ Operation` |

Plays a named pulse operation on any target element.

### 9.6 Cavity Operations

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `.displacement(target, *, amp, phase=0.0)` | `→ QuantumGate` | Cavity displacement gate |
| `.sqr(target, *, thetas, phis)` | `→ QuantumGate` | Selective Quantum Rotation gate |

### 9.7 Reset

```python
session.ops.reset(
    target,
    *,
    mode="passive",           # "passive" or "active"
    readout=None,             # Readout element (required for active)
    threshold=None,           # Discrimination threshold (or "calibrated")
    max_attempts=1,           # Number of feedback rounds for active reset
    real_time=False,
    operation="readout",
    pi_op="x180",
) → Operation
```

- **Passive mode**: emits a `wait()` for the configured thermalization time.
- **Active mode**: emits measure + conditional pi-pulse pairs.

### 9.8 Example: Building a Custom Sequence

```python
seq = session.sequence("T2_ramsey_custom")

# State preparation: active reset
seq.add(session.ops.reset("qubit", mode="active", readout="readout", threshold="calibrated"))

# Ramsey protocol
seq.add(session.ops.x90("qubit"))
seq.add(session.ops.wait("qubit", 50))  # ~200 ns delay
seq.add(session.ops.x90("qubit"))

# Measurement
seq.add(session.ops.measure("readout", mode="classified"))

print(seq.inspect())
```

---

## 10. Circuit IR

### 10.1 QuantumGate

```python
from qubox import QuantumGate
```

A frozen dataclass that extends `Operation` with circuit-friendly semantics.
Identical to `Operation` in structure; the type distinction enables
circuit-level reasoning.

### 10.2 QuantumCircuit

```python
from qubox import QuantumCircuit
```

A gate-sequence container.

```python
@dataclass
class QuantumCircuit:
    name: str = "circuit"
    gates: list[Operation] = []
    metadata: dict[str, Any] = {}
```

**Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `.add(gate)` | `(Operation) → QuantumCircuit` | Append a gate; returns self |
| `.add_gate(gate)` | `(Operation) → QuantumCircuit` | Alias for `.add()` |
| `.to_sequence()` | `() → Sequence` | Convert to a `Sequence` |
| `.inspect()` | `() → str` | Human-readable text dump |

**Example:**

```python
circ = session.circuit("displacement_test")
circ.add(session.ops.displacement("storage", amp=0.5, phase=0.0))
circ.add(session.ops.measure("readout"))

result = session.exp.custom(circuit=circ, acquire=session.acquire.iq("readout"), n_avg=100)
```

---

## 11. Experiment Library

### 11.1 Access

Available on `session.exp`.

```python
session.exp              # → ExperimentLibrary
session.exp.qubit        # → QubitExperimentLibrary
session.exp.resonator    # → ResonatorExperimentLibrary
session.exp.readout      # → ReadoutExperimentLibrary
session.exp.calibration  # → CalibrationExperimentLibrary
session.exp.storage      # → StorageExperimentLibrary
session.exp.tomography   # → TomographyExperimentLibrary
session.exp.reset        # → ResetExperimentLibrary
```

### 11.2 Standard Experiment Suite (20 experiments)

All template experiments return an `ExperimentResult`.

---

#### Readout Trace — `readout.trace`

Acquires raw ADC readout traces.

```python
result = session.exp.readout.trace(readout="rr0", drive_frequency=8.61e9, n_avg=1000)
```

**Signature:**

```python
session.exp.readout.trace(
    *,
    readout: str,              # Readout element alias
    drive_frequency: float,    # Drive frequency for the readout tone (Hz)
    **kwargs,                  # Additional: n_avg, ro_therm_clks
) → ExperimentResult
```

---

#### Resonator Spectroscopy — `resonator.spectroscopy`

```python
result = session.exp.resonator.spectroscopy(
    readout="rr0",
    freq=session.sweep.linspace(-5e6, 5e6, 201, center="readout"),
    n_avg=200,
)
```

**Signature:**

```python
session.exp.resonator.spectroscopy(
    *,
    readout: str,        # Readout element alias
    freq: SweepAxis,     # Frequency sweep axis
    **kwargs,            # Additional: n_avg, readout_op, ro_therm_clks
) → ExperimentResult
```

---

#### Resonator Power Spectroscopy — `resonator.power_spectroscopy`

2D sweep: frequency × readout gain, for characterizing resonator response as a function of power.

```python
result = session.exp.resonator.power_spectroscopy(
    readout="rr0",
    freq=session.sweep.linspace(-5e6, 5e6, 201, center="readout"),
    gain_min=1e-3,
    gain_max=0.5,
    n_gain_points=50,
    n_avg=200,
)
```

**Signature:**

```python
session.exp.resonator.power_spectroscopy(
    *,
    readout: str,
    freq: SweepAxis,                 # Frequency sweep axis
    gain_min: float = 1e-3,          # Minimum readout gain
    gain_max: float = 0.5,           # Maximum readout gain
    **kwargs,                        # Additional: n_gain_points/N_a, n_avg, readout_op, ro_therm_clks
) → ExperimentResult
```

---

#### Qubit Spectroscopy — `qubit.spectroscopy`

```python
result = session.exp.qubit.spectroscopy(
    qubit="q0",
    readout="rr0",
    freq=session.sweep.linspace(-30e6, 30e6, 241, center="q0.ge"),
    drive_amp=0.02,
    n_avg=200,
)
```

**Signature:**

```python
session.exp.qubit.spectroscopy(
    *,
    qubit: str,          # Qubit element alias
    readout: str,        # Readout element alias
    freq: SweepAxis,     # Frequency sweep axis
    drive_amp: float,    # Drive amplitude
    **kwargs,            # Additional: n_avg, pulse, transition, qb_len, qb_therm_clks
) → ExperimentResult
```

---

#### Temporal Rabi — `qubit.temporal_rabi`

Sweeps drive pulse duration at fixed amplitude.

```python
result = session.exp.qubit.temporal_rabi(
    qubit="q0",
    readout="rr0",
    duration=session.sweep.linspace(4, 200, 50, parameter="duration"),
    pulse="x180",
    n_avg=1000,
)
```

**Signature:**

```python
session.exp.qubit.temporal_rabi(
    *,
    qubit: str,
    readout: str,
    duration: SweepAxis,       # Pulse duration sweep (clock cycles)
    pulse: str = "x180",      # Pulse operation name
    **kwargs,                  # Additional: n_avg, pulse_gain, qb_therm_clks
) → ExperimentResult
```

---

#### Power Rabi — `qubit.power_rabi`

```python
result = session.exp.qubit.power_rabi(
    qubit="q0",
    readout="rr0",
    amplitude=session.sweep.linspace(0.01, 1.0, 50, parameter="amplitude"),
    n_avg=500,
)
```

**Signature:**

```python
session.exp.qubit.power_rabi(
    *,
    qubit: str,
    readout: str,
    amplitude: SweepAxis,   # Amplitude sweep axis
    **kwargs,               # Additional: n_avg, pulse/op, length, truncate_clks,
                            #   qb_therm_clks, use_circuit_runner
) → ExperimentResult
```

---

#### Time Rabi Chevron — `qubit.time_rabi_chevron`

2D sweep: pulse duration × frequency detuning.

```python
result = session.exp.qubit.time_rabi_chevron(
    qubit="q0",
    readout="rr0",
    freq_span=10e6,
    df=100e3,
    max_duration=200,
    dt=4,
    n_avg=500,
)
```

**Signature:**

```python
session.exp.qubit.time_rabi_chevron(
    *,
    qubit: str,
    readout: str,
    freq_span: float,          # IF frequency span (Hz)
    df: float,                 # Frequency step (Hz)
    max_duration: int,         # Maximum pulse duration (clock cycles)
    dt: int = 4,               # Duration step (clock cycles)
    **kwargs,                  # Additional: n_avg, pulse, pulse_gain, qb_therm_clks
) → ExperimentResult
```

---

#### Power Rabi Chevron — `qubit.power_rabi_chevron`

2D sweep: drive amplitude × frequency detuning.

```python
result = session.exp.qubit.power_rabi_chevron(
    qubit="q0",
    readout="rr0",
    freq_span=10e6,
    df=100e3,
    max_gain=1.0,
    dg=0.01,
    n_avg=500,
)
```

**Signature:**

```python
session.exp.qubit.power_rabi_chevron(
    *,
    qubit: str,
    readout: str,
    freq_span: float,          # IF frequency span (Hz)
    df: float,                 # Frequency step (Hz)
    max_gain: float,           # Maximum amplitude gain
    dg: float = 0.01,          # Gain step
    **kwargs,                  # Additional: n_avg, pulse, pulse_duration, qb_therm_clks
) → ExperimentResult
```

---

#### T1 Relaxation — `qubit.t1`

Measures energy relaxation time. Applies π-pulse then waits variable delay.

```python
result = session.exp.qubit.t1(
    qubit="q0",
    readout="rr0",
    delay=session.sweep.linspace(4, 40000, 100, parameter="delay"),
    n_avg=1000,
)
```

**Signature:**

```python
session.exp.qubit.t1(
    *,
    qubit: str,
    readout: str,
    delay: SweepAxis,          # Delay sweep (clock cycles)
    **kwargs,                  # Additional: n_avg, r180/pulse, qb_therm_clks, use_circuit_runner
) → ExperimentResult
```

---

#### T2 Ramsey — `qubit.ramsey`

```python
result = session.exp.qubit.ramsey(
    qubit="q0",
    readout="rr0",
    delay=session.sweep.linspace(4, 2000, 100, parameter="delay"),
    detuning=0.5e6,
    n_avg=500,
)
```

**Signature:**

```python
session.exp.qubit.ramsey(
    *,
    qubit: str,
    readout: str,
    delay: SweepAxis,        # Delay sweep axis (clock cycles)
    detuning: float = 0.0,   # Artificial detuning (Hz)
    **kwargs,                # Additional: n_avg, prep/r90, qb_therm_clks, qb_detune_MHz
) → ExperimentResult
```

---

#### T2 Echo — `qubit.echo`

Spin-echo (Hahn echo) sequence: π/2 — τ — π — τ — π/2 — measure.

```python
result = session.exp.qubit.echo(
    qubit="q0",
    readout="rr0",
    delay=session.sweep.linspace(8, 4000, 100, parameter="delay"),
    n_avg=1000,
)
```

**Signature:**

```python
session.exp.qubit.echo(
    *,
    qubit: str,
    readout: str,
    delay: SweepAxis,          # Half-echo delay sweep (clock cycles)
    **kwargs,                  # Additional: n_avg, r180, r90, qb_therm_clks
) → ExperimentResult
```

---

#### IQ Blobs — `readout.iq_blobs`

Per-shot IQ blob separation (ground/excited states, optionally f-state).

```python
result = session.exp.readout.iq_blobs(
    qubit="q0",
    readout="rr0",
    n_runs=2000,
)
```

**Signature:**

```python
session.exp.readout.iq_blobs(
    *,
    qubit: str,
    readout: str,
    **kwargs,                  # Additional: n_runs/n_avg, r180/pulse, qb_therm_clks
) → ExperimentResult
```

---

#### AllXY — `calibration.all_xy`

Runs all 21 AllXY gate-pair sequences for gate calibration validation.

```python
result = session.exp.calibration.all_xy(qubit="q0", readout="rr0", n_avg=1000)
```

**Signature:**

```python
session.exp.calibration.all_xy(
    *,
    qubit: str,
    readout: str,
    **kwargs,                  # Additional: n_avg, gate_indices, prefix, qb_detuning, qb_therm_clks
) → ExperimentResult
```

---

#### DRAG Calibration — `calibration.drag`

DRAG pulse amplitude calibration (Yale method: X180·Y90 and Y180·X90).

```python
result = session.exp.calibration.drag(
    qubit="q0",
    readout="rr0",
    amps=np.linspace(-0.5, 0.5, 51),
    n_avg=1000,
)
```

**Signature:**

```python
session.exp.calibration.drag(
    *,
    qubit: str,
    readout: str,
    amps: SweepAxis | array,   # DRAG amplitude sweep
    **kwargs,                  # Additional: n_avg, base_alpha, calibration_op,
                               #   x180, x90, y180, y90, qb_therm_clks
) → ExperimentResult
```

---

#### Readout Butterfly Measurement — `readout.butterfly`

Post-selection-based readout fidelity measurement (triple measurement M0-M1-M2).

```python
result = session.exp.readout.butterfly(qubit="q0", readout="rr0", n_samples=10_000)
```

**Signature:**

```python
session.exp.readout.butterfly(
    *,
    qubit: str,
    readout: str,
    **kwargs,                  # Additional: n_samples/n_avg, prep_policy/policy,
                               #   prep_kwargs, r180, threshold, max_trials, qb_therm_clks
) → ExperimentResult
```

---

#### Qubit State Tomography — `tomography.qubit_state`

Single-qubit state tomography (X, Y, Z projections).

```python
def my_state_prep():
    play("x90", "qubit")

result = session.exp.tomography.qubit_state(
    qubit="q0",
    readout="rr0",
    state_prep=my_state_prep,
    n_avg=1000,
)
```

**Signature:**

```python
session.exp.tomography.qubit_state(
    *,
    qubit: str,
    readout: str,
    state_prep: Callable | list[Callable],   # QUA-compatible state preparation callable(s)
    **kwargs,                                # Additional: n_avg, x90_pulse, yn90_pulse,
                                             #   therm_clks/qb_therm_clks
) → ExperimentResult
```

---

#### Storage Spectroscopy — `storage.spectroscopy`

Displacement → selective π → measure, sweeping frequency to find Fock-dependent qubit transitions.

```python
result = session.exp.storage.spectroscopy(
    qubit="q0",
    readout="rr0",
    storage="st0",
    freq=session.sweep.linspace(-5e6, 5e6, 201, center="q0.ge"),
    disp="disp_n1",
    storage_therm_time=50000,
    n_avg=1000,
)
```

**Signature:**

```python
session.exp.storage.spectroscopy(
    *,
    qubit: str,
    readout: str,
    storage: str,                          # Storage/cavity element alias
    freq: SweepAxis,                       # Frequency sweep axis
    disp: str,                             # Displacement pulse name
    storage_therm_time: int,               # Storage cooldown (clock cycles)
    **kwargs,                              # Additional: n_avg, sel_r180
) → ExperimentResult
```

---

#### Storage T1 Decay — `storage.t1_decay`

Fock-state energy relaxation: displace → wait → selective π → measure.
Uses `FockResolvedT1` backend; for single-Fock T1 pass a one-element `fock_fqs` list.

```python
result = session.exp.storage.t1_decay(
    qubit="q0",
    readout="rr0",
    storage="st0",
    delay=session.sweep.linspace(4, 40000, 100, parameter="delay"),
    fock_fqs=[5.123e9],
    fock_disps=["disp_n1"],
    n_avg=1000,
)
```

**Signature:**

```python
session.exp.storage.t1_decay(
    *,
    qubit: str,
    readout: str,
    storage: str,
    delay: SweepAxis,          # Delay sweep (clock cycles)
    **kwargs,                  # Additional: n_avg, fock_fqs, fock_disps, sel_r180,
                               #   st_therm_clks/storage_therm_clks
) → ExperimentResult
```

---

#### Number Splitting Spectroscopy — `storage.num_splitting`

Resolves photon-number-dependent qubit frequency shifts.

```python
result = session.exp.storage.num_splitting(
    qubit="q0",
    readout="rr0",
    storage="st0",
    rf_centers=[5.1e9, 5.09e9, 5.08e9],
    rf_spans=[2e6, 2e6, 2e6],
    df=50e3,
    n_avg=500,
)
```

**Signature:**

```python
session.exp.storage.num_splitting(
    *,
    qubit: str,
    readout: str,
    storage: str,
    rf_centers: list[float],       # Center frequencies per Fock state (Hz)
    rf_spans: list[float],         # Frequency span per Fock state (Hz)
    df: float = 50e3,              # Frequency step (Hz)
    **kwargs,                      # Additional: n_avg, sel_r180, state_prep,
                                   #   st_therm_clks/storage_therm_clks
) → ExperimentResult
```

---

#### Wigner Tomography — `tomography.wigner`

Storage Wigner function tomography via displaced parity measurement.

```python
result = session.exp.tomography.wigner(
    qubit="q0",
    readout="rr0",
    storage="st0",
    state_prep=my_state_prep,
    x_vals=np.linspace(-3, 3, 61),
    p_vals=np.linspace(-3, 3, 61),
    base_alpha=10.0,
    n_avg=200,
)
```

**Signature:**

```python
session.exp.tomography.wigner(
    *,
    qubit: str,
    readout: str,
    storage: str,
    state_prep: Callable | list[Callable],   # QUA state-preparation callable(s)
    x_vals: array,                           # Phase-space x grid
    p_vals: array,                           # Phase-space p grid
    **kwargs,                                # Additional: n_avg, base_alpha, r90_pulse, qb_therm_clks
) → ExperimentResult
```

---

#### Active Reset Benchmark — `reset.active`

```python
result = session.exp.reset.active(
    qubit="q0",
    readout="rr0",
    threshold="calibrated",
    n_avg=200,
)
```

**Signature:**

```python
session.exp.reset.active(
    *,
    qubit: str,
    readout: str,
    threshold: float | str = "calibrated",
    **kwargs,                # Additional: n_avg, policy, show_analysis, max_attempts, qb_therm_clks
) → ExperimentResult
```

### 11.3 Custom Experiments

```python
session.exp.custom(
    *,
    sequence=None,           # A Sequence object
    circuit=None,            # A QuantumCircuit object (mutually exclusive with sequence)
    sweep=None,              # SweepAxis or SweepPlan
    acquire=None,            # AcquisitionSpec
    analysis="raw",          # Named analysis pipeline
    n_avg=1,                 # Number of averages / shots
    name=None,               # Name for the experiment
    execute=True,            # If False, returns the build without executing
) → ExperimentResult
```

Either `sequence` or `circuit` must be provided. The body is lowered to
QUA through the `QMRuntime` backend (see [Section 16](#16-qm-backend-runtime)).

**Example — custom Ramsey with active reset:**

```python
delay_axis = session.sweep.linspace(4, 500, 50, parameter="delay")

seq = session.sequence("custom_ramsey")
seq.add(session.ops.reset("qubit", mode="active", readout="readout"))
seq.add(session.ops.x90("qubit"))
seq.add(session.ops.wait("qubit", 100))
seq.add(session.ops.x90("qubit"))
seq.add(session.ops.measure("readout", mode="iq"))

result = session.exp.custom(
    sequence=seq,
    sweep=delay_axis,
    acquire=session.acquire.iq("readout"),
    analysis="iq_magnitude",
    n_avg=500,
)

print(result.inspect())
```

---

## 12. Workflow Library

### 12.1 Access

```python
session.workflow          # → WorkflowLibrary
session.workflow.readout  # → ReadoutWorkflowLibrary
```

### 12.2 Readout Full Calibration Workflow

```python
wf = session.workflow.readout.full(
    qubit="q0",
    readout="rr0",
    update_store=False,
)

report = wf.run()
print(report.review())
```

Returns a `WorkflowReport` with:

| Member | Type | Description |
|--------|------|-------------|
| `.name` | `str` | Workflow identifier (`"readout.full"`) |
| `.payload` | `dict` | Workflow outputs (steps, targets, etc.) |
| `.review()` | `→ str` | Human-readable summary |

> **Note:** `WorkflowReport.apply()` is intentionally disabled. Calibration
> updates from workflows must be promoted through the canonical
> `CalibrationProposal` flow.

---

## 13. Execution & Results

### 13.1 ExecutionRequest

```python
from qubox import ExecutionRequest
```

A frozen dataclass capturing the full specification required to execute or
replay an experiment.

```python
@dataclass(frozen=True)
class ExecutionRequest:
    kind: str                    # "template" or "custom"
    template: str                # Template name or experiment name
    targets: dict[str, str]      # Role → element mapping
    params: dict[str, Any]       # Experiment parameters
    sequence: Any = None         # Sequence body (custom experiments)
    circuit: Any = None          # Circuit body (custom experiments)
    sweep: Any = None            # SweepPlan
    acquisition: Any = None      # AcquisitionSpec
    shots: int | None = None     # Number of shots / averages
    analysis: str | None = None  # Named analysis pipeline
    execute: bool = True         # Whether to execute or just build
    metadata: dict[str, Any]     # Arbitrary metadata
```

### 13.2 ExperimentResult

```python
from qubox import ExperimentResult
```

The primary result container returned by all experiment runs.

```python
@dataclass
class ExperimentResult:
    request: ExecutionRequest              # The original request
    build: Any = None                      # Build artifact (ProgramBuildResult from legacy)
    run: Any = None                        # Run result (RunResult from legacy)
    analysis: Any = None                   # Analysis output (dict or AnalysisResult)
    calibration_snapshot: CalibrationSnapshot | None = None
    artifact_path: str | None = None       # Path to saved output artifacts
    compiler_report: dict[str, Any] = {}   # Compilation metadata
    plotter: Any = None                    # Callable for plotting (template experiments)
    source: Any = None                     # Underlying experiment or circuit object
```

**Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `.plot(*args, **kwargs)` | `→ Any` | Invoke the experiment's plot function (template experiments only) |
| `.inspect()` | `→ dict[str, Any]` | Return a summary dict of the result |
| `.proposal()` | `→ CalibrationProposal \| None` | Extract a calibration proposal from analysis metadata, if present |

### 13.3 Usage Pattern

```python
# Run experiment
result = session.exp.qubit.spectroscopy(
    qubit="q0", readout="rr0",
    freq=session.sweep.linspace(-30e6, 30e6, 241, center="q0.ge"),
    drive_amp=0.02, n_avg=200,
)

# Inspect result
summary = result.inspect()
print(summary["artifact_path"])
print(summary["compiler_report"])

# Plot (template experiments with analysis)
result.plot()

# Extract calibration proposal
proposal = result.proposal()
if proposal is not None:
    print(proposal.review())
```

---

## 14. Calibration

### 14.1 CalibrationSnapshot

```python
from qubox import CalibrationSnapshot
```

A frozen, point-in-time copy of the calibration store state.

```python
@dataclass(frozen=True)
class CalibrationSnapshot:
    source_path: str                   # Path to the calibration.json file
    data: dict[str, Any]               # Full calibration data (merged with overrides)
    overrides: dict[str, Any] = {}     # Any overrides applied at snapshot time
```

**Class method:**

```python
CalibrationSnapshot.from_session(session, *, overrides=None) → CalibrationSnapshot
```

Creates a snapshot from the current session state, optionally applying overrides.

### 14.2 CalibrationProposal

```python
from qubox import CalibrationProposal
```

A mutable container for proposed calibration updates.

```python
@dataclass
class CalibrationProposal:
    updates: list[dict[str, Any]]      # List of update operations
    reason: str = ""                   # Human-readable reason
    preview: dict[str, Any] | None     # Preview data (optional)
```

**Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `.review()` | `→ str` | Human-readable summary of proposed changes |
| `.apply(session, *, dry_run=False)` | `→ dict[str, Any]` | Apply the proposal to the session's calibration store |

**Workflow:**

```python
result = session.exp.qubit.power_rabi(...)

# Check if the experiment produced a calibration proposal
proposal = result.proposal()
if proposal is not None:
    # Review before applying
    print(proposal.review())

    # Dry run (preview only, no changes)
    preview = proposal.apply(session, dry_run=True)

    # Apply for real
    outcome = proposal.apply(session, dry_run=False)
```

### 14.3 Direct Calibration Store Access

For advanced use, the underlying `CalibrationStore` from `qubox_v2_legacy` is
available through the legacy session:

```python
cal = session.legacy_session.calibration

# Read calibration data
transmon = cal.get_cqed_params("transmon")
discrimination = cal.get_discrimination("readout_element")
frequencies = cal.get_frequencies("qubit_element")
pulse_cal = cal.get_pulse_calibration("ref_r180")

# Inspect as dict
print(transmon.model_dump(exclude_none=True))
```

### 14.4 CalibrationOrchestrator (Legacy)

The full `run → analyze → patch → apply` lifecycle is available through
the legacy compatibility layer:

```python
from qubox.notebook import CalibrationOrchestrator, Patch

orch = CalibrationOrchestrator(session.legacy_session)
cycle = orch.run_analysis_patch_cycle(experiment_cls, **kwargs)

# Or manual patch
patch = Patch(reason="Manual update")
patch.add("SetCalibration", target="transmon", key="pi_amp", value=0.42)
orch.apply_patch(patch, dry_run=False)
```

---

## 15. Analysis Pipelines

### 15.1 Named Pipelines

The `qubox_tools.algorithms.pipelines.run_named_pipeline()` function provides
lightweight analysis for custom experiments.

```python
from qubox_tools.algorithms.pipelines import run_named_pipeline
```

> **Note:** The `qubox.analysis` shim package has been removed.  Import
> analysis utilities directly from `qubox_tools`.

**Signature:**

```python
run_named_pipeline(name: str | None, *, run_result, build=None) → dict[str, Any]
```

**Supported pipeline names:**

| Pipeline | Description | Output keys |
|----------|-------------|-------------|
| `"raw"` | Pass through raw output | `mode`, `data` |
| `"iq_magnitude"` | IQ magnitude + phase extraction | `I`, `Q`, `signal`, `magnitude`, `phase`, (optional: `state`, `population_e`) |
| `"ramsey_like"` | Same as `iq_magnitude` | Same as above |
| `"classified"` | Same as `iq_magnitude` | Same as above |

For template experiments, analysis is handled internally by the legacy
experiment class's `.analyze()` method.

### 15.2 qubox_tools Analysis

For more sophisticated analysis (curve fitting, plotting, post-processing),
use the `qubox_tools` package (see [Section 18](#18-qubox_tools--analysis-toolkit)).

---

## 16. QM Backend Runtime

### 16.1 QMRuntime

The `QMRuntime` class executes `ExecutionRequest` objects against the
Quantum Machines backend. It is lazily instantiated on `session.backend`.

Users typically do not interact with `QMRuntime` directly — it is invoked
by `session.exp.*` methods.

**Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `.run(request)` | `(ExecutionRequest) → ExperimentResult` | Build + execute + analyze |
| `.build(request)` | `(ExecutionRequest) → ExperimentResult` | Build only (no execution) |

### 16.2 Template Execution

For template experiments (`kind="template"`), `QMRuntime` delegates to a
**legacy experiment adapter**. The adapter maps the `ExecutionRequest`
parameters into the legacy experiment class's `build_program()` / `run_program()`
/ `analyze()` methods.

Currently registered template adapters:

| Template name | Legacy class | Description |
|---------------|--------------|-------------|
| `qubit.spectroscopy` | `QubitSpectroscopy` | Qubit spectroscopy (GE/EF) |
| `resonator.spectroscopy` | `ResonatorSpectroscopy` | Resonator spectroscopy |
| `qubit.power_rabi` | `PowerRabi` | Power Rabi oscillation |
| `qubit.ramsey` | `T2Ramsey` | T2 Ramsey / Ramsey-like |
| `reset.active` | `ActiveQubitResetBenchmark` | Active reset benchmarking |

Additional template adapters can be added by extending `_ADAPTERS` in
`qubox.backends.qm.runtime`.

### 16.3 Custom Execution

For custom experiments (`kind="custom"`), `QMRuntime`:

1. **Lowers** the `Sequence` or `QuantumCircuit` into the legacy
   `CircuitRunner` IR (gates, measurement records, metadata).
2. **Compiles** the lowered circuit into a QUA program via `CircuitRunner.compile_program()` (formerly `compile_v2`).
3. **Executes** the QUA program via `ProgramRunner`.
4. **Analyzes** the output via `run_named_pipeline()`.

### 16.4 Lowering Details

The lowering step (`qubox.backends.qm.lowering.lower_to_legacy_circuit`)
translates:

- `Operation(kind="qubit_rotation")` → `LegacyGate(name="qubit_rotation")`
- `Operation(kind="measure")` → `LegacyGate(name="measure_iq")` + `MeasurementRecord`
- `Operation(kind="idle"/"wait")` → `LegacyGate(name="idle")`
- `Operation(kind="play")` → `LegacyGate(name="play")`
- `Operation(kind="reset")` → expanded into measure + conditional-pi sequences
- `Condition` → `LegacyGateCondition`

If an `AcquisitionSpec` is provided and no explicit measure operation exists
in the body, a measurement is automatically appended.

---

## 17. Notebook Import Surface (qubox.notebook)

### 17.1 Purpose

`qubox.notebook` is the primary import surface for notebook-based
experiment workflows.  It is split into two tiers:

- **`qubox.notebook`** (essentials): experiments, session management, workflow helpers, waveform generators, and basic calibration tools.
- **`qubox.notebook.advanced`**: infrastructure symbols — `CalibrationStore`, data models (`CQEDParams`, `FitRecord`, …), `ArtifactManager`, schemas, device registry, verification.

Core workflow primitives (stage checkpoints, fit gates, patch preview, pulse seeding) are also available from `qubox.workflow` for scripts and CI without a notebook kernel.

`qubox.notebook` exposes:
- **Experiment classes** (30+) for spectroscopy, time-domain, readout, gate calibration, storage/cavity, and tomography.
- **Calibration essentials:** `CalibrationOrchestrator`, `Patch`, `UpdateOp`, `MixerCalibrationConfig`, `SAMeasurementHelper`.
- **Hardware authoring:** `HardwareDefinition` for generating sample-level config files.
- **Session lifecycle:** `open_shared_session()`, `require_shared_session()`, `close_shared_session()`, `restore_shared_session()` for multi-notebook shared sessions.
- **Stage workflow:** `open_notebook_stage()`, `save_stage_checkpoint()`, `load_stage_checkpoint()`, `preview_or_apply_patch_ops()`, `fit_quality_gate()`, `fit_center_inside_window()`, `ensure_primitive_rotations()`.
- **Waveform tools:** `drag_gaussian_pulse_waveforms`, `kaiser_pulse_waveforms`, `register_rotations_from_ref_iq`, `ensure_displacement_ops`.
- **Program utilities:** `measureMacro`, `continuous_wave`, `QuboxSimulationConfig`.

`qubox.notebook.advanced` exposes:
- **Calibration data models:** `CalibrationStore`, `CQEDParams`, `FitRecord`, `PulseTrainResult`, `DiscriminationParams`, `ReadoutQuality`, `CoherenceParams`, `ElementFrequencies`, `PulseCalibration`, `CalibrationData`, `CalibrationContext`, `Transition`, calibration snapshot functions, etc.
- **Device/artifact management:** `SampleRegistry`, `SampleInfo`, `ArtifactManager`, `save_config_snapshot`, `save_run_summary`, `cleanup_artifacts`.
- **Preflight/schemas:** `preflight_check`, `validate_config_dir`, `ValidationResult`.
- **Core internals:** `ContextMismatchError`, `ExperimentContext`, `SessionState`.
- **Verification:** `run_all_checks`.

### 17.2 Usage

```python
from qubox.notebook import (
    # Experiment classes
    ResonatorSpectroscopy,
    QubitSpectroscopy,
    PowerRabi,
    T1Relaxation,
    T2Ramsey,
    T2Echo,
    AllXY,
    DRAGCalibration,
    RandomizedBenchmarking,
    IQBlob,
    ReadoutGEDiscrimination,
    StorageSpectroscopy,
    StorageWignerTomography,
    # ... and many more

    # Calibration essentials
    CalibrationOrchestrator,
    Patch,

    # Hardware authoring
    HardwareDefinition,

    # Shared notebook runtime
    open_shared_session,
    require_shared_session,
    get_notebook_session_bootstrap_path,
    resolve_active_mixer_targets,

    # Stage workflow helpers
    open_notebook_stage,
    load_stage_checkpoint,
    save_stage_checkpoint,
    preview_or_apply_patch_ops,
    fit_quality_gate,
    fit_center_inside_window,
    ensure_primitive_rotations,

    # Session / Core
    RunResult,
    AnalysisResult,
    ProgramBuildResult,

    # Tools
    register_rotations_from_ref_iq,
    ensure_displacement_ops,
    kaiser_pulse_waveforms,
    drag_gaussian_pulse_waveforms,

    # Hardware / Programs
    measureMacro,
    QuboxSimulationConfig,
)

# For infrastructure symbols, use the advanced submodule:
from qubox.notebook.advanced import (
    CalibrationStore,
    SampleRegistry,
    ArtifactManager,
    SessionState,
    ExperimentContext,
    save_config_snapshot,
    save_run_summary,
)

# Or for portable (non-notebook) workflow use:
from qubox.workflow import (
    save_stage_checkpoint,
    load_stage_checkpoint,
    fit_quality_gate,
    preview_or_apply_patch_ops,
)
```

### 17.3 Available Legacy Classes

The full list of re-exported names includes:

**Experiments (30+):**
`ResonatorSpectroscopy`, `ResonatorPowerSpectroscopy`,
`ResonatorSpectroscopyX180`, `ReadoutTrace`, `QubitSpectroscopy`,
`QubitSpectroscopyEF`, `PowerRabi`, `TemporalRabi`, `T1Relaxation`,
`T2Ramsey`, `T2Echo`, `IQBlob`, `ReadoutGEDiscrimination`,
`ReadoutWeightsOptimization`, `ReadoutButterflyMeasurement`,
`CalibrateReadoutFull`, `AllXY`, `DRAGCalibration`,
`RandomizedBenchmarking`, `PulseTrainCalibration`,
`StorageSpectroscopy`, `NumSplittingSpectroscopy`,
`StorageChiRamsey`, `FockResolvedSpectroscopy`, `FockResolvedT1`,
`FockResolvedRamsey`, `FockResolvedPowerRabi`, `QubitStateTomography`,
`StorageWignerTomography`, `SNAPOptimization`, `SPAFluxOptimization`,
`SPAPumpFrequencyOptimization`

**Calibration / Core:**
`CalibrationOrchestrator`, `CalibrationStore`, `Patch`,
`MixerCalibrationConfig`, `SAMeasurementHelper`, `SampleRegistry`,
`SampleInfo`, `SessionState`, `ExperimentContext`, `ArtifactManager`,
`ContextMismatchError`

**Results:**
`RunResult`, `AnalysisResult`, `ProgramBuildResult`

**Tools / Waveforms:**
`register_rotations_from_ref_iq`, `ensure_displacement_ops`,
`kaiser_pulse_waveforms`, `drag_gaussian_pulse_waveforms`,
`save_config_snapshot`, `save_run_summary`, `validate_config_dir`,
`cleanup_artifacts`, `preflight_check`

**Hardware / Programs:**
`measureMacro`, `continuous_wave`, `QuboxSimulationConfig`

> **Note:** These re-exports provide a single-import convenience for notebooks.
> For programmatic workflows, prefer the `qubox` API (`Session`, `session.exp.*`,
> `session.ops.*`, etc.).

### 17.4 Simulation Mode

All session-opening helpers (`open_shared_session`, `require_shared_session`,
`Session.open`) accept a `simulation_mode: bool` keyword argument that
**defaults to `True`** — sessions open safely in simulation mode by default.

When `simulation_mode=True` (the default):

- `hardware.open_qm()` is **skipped** — no `QuantumMachine` instance is created
  and RF outputs are **never enabled**.
- The `QuantumMachinesManager` (QMM) connection is still established, so
  `experiment.simulate()` and `runner.simulate()` work normally via
  `qmm.simulate()`.
- `runner.exec_mode` is locked to `ExecMode.SIMULATE` at construction time.
- Any call to `runner.run_program()` raises `JobError` with a clear message.
- `session.simulation_mode` returns `True`.

Pass `simulation_mode=False` explicitly to enable real hardware execution.

```python
from qubox.notebook import open_shared_session, QuboxSimulationConfig, PowerRabi

# Default: simulation mode (safe, no RF outputs)
session = open_shared_session(
    registry_base="./samples",
    sample_id="post_cavity_sample_A",
    cooldown_id="cd_2026_03",
    qop_ip="10.157.36.68",
    cluster_name="Cluster_2",
)

# For real hardware execution:
# session = open_shared_session(..., simulation_mode=False)

exp = PowerRabi(session)
exp.simulate(
    QuboxSimulationConfig(duration_ns=10_000, plot=True),
    element="qubit",
    pulse="x180",
    amp_start=0.0,
    amp_stop=0.5,
    amp_step=0.01,
    n_avg=1,
)
```

`NotebookSessionBootstrap` also stores the `simulation_mode` flag, so
`restore_shared_session()` reopens in the same mode automatically.

---

## 18. Workflow Primitives (qubox.workflow)

### 18.1 Purpose

`qubox.workflow` provides portable stage management, checkpoint persistence,
fit quality gates, calibration patch helpers, and pulse seeding — without
requiring a notebook kernel.  These are the same primitives used by
`qubox.notebook.workflow`, but importable from scripts and CI.

### 18.2 Modules

| Module | Exports |
|--------|---------|
| `qubox.workflow.stages` | `WorkflowConfig`, `StageCheckpoint`, `build_workflow_config()`, `get_stage_checkpoint_path()`, `save_stage_checkpoint()`, `load_stage_checkpoint()`, `load_legacy_reference()` |
| `qubox.workflow.calibration_helpers` | `preview_or_apply_patch_ops()` |
| `qubox.workflow.fit_gates` | `fit_quality_gate()`, `fit_center_inside_window()` |
| `qubox.workflow.pulse_seeding` | `ensure_primitive_rotations()` |

### 18.3 Usage

```python
from qubox.workflow import (
    save_stage_checkpoint,
    load_stage_checkpoint,
    fit_quality_gate,
    fit_center_inside_window,
    preview_or_apply_patch_ops,
    ensure_primitive_rotations,
)

# Save a stage checkpoint (works from any Python context)
save_stage_checkpoint(
    registry_base="./samples",
    sample_id="post_cavity_sample_A",
    cooldown_id="cd_2026_03_31",
    stage_name="resonator_spectroscopy",
    status="complete",
    summary="Found resonator at 7.245 GHz",
)

# Check fit quality
passed, reason = fit_quality_gate(analysis, r_squared_min=0.8)
```

---

## 19. qubox_tools — Analysis Toolkit

### 19.1 Import

```python
import qubox_tools as qt
```

### 18.2 Purpose

`qubox_tools` is the canonical home for reusable fitting, plotting,
post-processing, and optimization helpers. It is separate from `qubox`
because analysis utilities are backend-independent.

### 18.3 Top-Level Exports

| Name | Import Path | Description |
|------|-------------|-------------|
| `generalized_fit` | `qubox_tools.fitting.routines` | General-purpose curve fitting |
| `fit_and_wrap` | `qubox_tools.fitting.routines` | Fit and wrap result into FitResult |
| `build_fit_legend` | `qubox_tools.fitting.routines` | Generate plot legend from fit |
| `Output` | `qubox_tools.data.containers` | Experiment output container |
| `OutputArray` | `qubox_tools.data.containers` | Array-based output container |
| `PostSelectionConfig` | `qubox_tools.algorithms.post_selection` | Post-selection configuration |
| `plot_hm` | `qubox_tools.plotting.common` | Heatmap plotting helper |

### 18.4 Submodules

| Submodule | Description |
|-----------|-------------|
| `qubox_tools.fitting` | Fitting models and routines |
| `qubox_tools.plotting` | Plotting helpers for common experiment types |
| `qubox_tools.algorithms` | Post-processing algorithms (post-selection, etc.) |
| `qubox_tools.data` | Data containers (`Output`, `OutputArray`) |
| `qubox_tools.optimization` | Optimization utilities |

### 18.5 Example

```python
import numpy as np
import qubox_tools as qt

x = np.linspace(-1.0, 1.0, 101)
y = qt.fitting.models.gaussian_model(x, 0.15, 0.2, 0.8, 0.1)
popt, pcov = qt.generalized_fit(
    x, y,
    qt.fitting.models.gaussian_model,
    p0=[0.0, 0.25, 1.0, 0.0],
)
print(f"Fitted center: {popt[0]:.4f}")
```

---

## 20. Legacy Internals (qubox_v2_legacy)

The `qubox_v2_legacy` package (renamed from the original `qubox_v2`) remains
the execution engine behind `qubox`. It contains:

| Component | Module | Role |
|-----------|--------|------|
| `SessionManager` | `qubox_v2_legacy.experiments.session` | Full session lifecycle (hardware, calibration, pulses) |
| `CalibrationStore` | `qubox_v2_legacy.calibration.store` | Typed `calibration.json` persistence (schema v5.0.0) |
| `CalibrationOrchestrator` | `qubox_v2_legacy.calibration` | Owns `run → analyze → patch → apply` lifecycle |
| `Patch` | `qubox_v2_legacy.calibration.contracts` | Calibration update transaction |
| `PulseOperationManager` | `qubox_v2_legacy.pulses.manager` | Waveform/pulse/weight binding |
| `PulseFactory` | `qubox_v2_legacy.pulses.factory` | Spec → I/Q waveform compilation |
| `ConfigEngine` | `qubox_v2_legacy.hardware.config_engine` | QM config dict assembly |
| `HardwareController` | `qubox_v2_legacy.hardware` | OPX+ / Octave live state |
| `ProgramRunner` | `qubox_v2_legacy.hardware.program_runner` | QUA program submission |
| `CircuitRunner` | `qubox.programs.circuit_runner` | IR-based QUA compilation |
| `CircuitCompiler` | `qubox.programs.circuit_compiler` | Gate → QUA compiler (renamed from `CircuitRunnerV2`) |
| `SampleRegistry` | `qubox_v2_legacy.devices` | Filesystem sample/cooldown management |
| `ExperimentContext` | `qubox_v2_legacy.core.experiment_context` | Immutable experiment identity |
| `ArtifactManager` | `qubox_v2_legacy.core.artifact_manager` | Build-hash-keyed artifact storage |
| 30+ experiment classes | `qubox_v2_legacy.experiments` | Physics-specific experiment implementations |

> **Users should not import directly from `qubox_v2_legacy`** in new code.
> Use `qubox` for the public API, and `qubox.notebook` for experiment
> classes and calibration helpers.

### 20.1 Key Internal Concepts

These are internal concepts that may appear in result objects or documentation:

- **SessionState**: Immutable SHA-256 hash over all source-of-truth config
  files. Computed at session open time.
- **CalibrationStore**: Typed JSON persistence for calibration parameters
  (frequencies, coherence, discrimination, pulse calibration, etc.).
  Schema version 5.0.0.
- **PulseFactory**: Compiles declarative pulse specs (from `pulse_specs.json`)
  into I/Q waveform sample arrays (12+ built-in shapes).
- **PulseOperationManager (POM)**: Dual-store binding layer that maps
  `(element, operation)` → waveform/weights.
- **ExperimentContext**: Frozen dataclass with `sample_id`, `cooldown_id`,
  `wiring_rev`, element names, and calibrated frequencies.
- **measureMacro**: Singleton QUA readout generator used by legacy experiments.
- **ProgramBuildResult**: Container returned by experiment `.build_program()`.
- **RunResult**: Container returned by experiment `.run_program()`.
- **AnalysisResult**: Container with fitted parameters, metadata, and
  proposed patch operations.

### 20.2 Calibration JSON Structure (v5.0.0)

The `calibration.json` file managed by `CalibrationStore` contains:

```json
{
    "version": "5.0.0",
    "context": {
        "sample_id": "...",
        "cooldown_id": "...",
        "wiring_rev": "..."
    },
    "alias_index": { "qubit": "element_name", ... },
    "discrimination": { ... },
    "readout_quality": { ... },
    "frequencies": { ... },
    "coherence": { ... },
    "pulse_calibrations": { ... },
    "cqed_params": { ... },
    "fit_history": [ ... ]
}
```

### 20.3 Sample / Cooldown Filesystem Layout

```
samples/
└── {sample_id}/
    ├── config/                  # Sample-level config (hardware.json, etc.)
    │   ├── hardware.json
    │   ├── pulse_specs.json
    │   └── calibration.json
    ├── cooldowns/
    │   └── {cooldown_id}/
    │       ├── config/          # Cooldown-level overrides
    │       │   └── calibration.json
    │       ├── data/            # Runtime artifacts (.npz, .meta.json)
    │       └── artifacts/       # Build-hash artifacts
    └── metadata.json            # Sample description
```

---

## 21. Examples and Minimal Usage Patterns

### 21.1 Quick Start — Template Experiment

```python
from qubox import Session

# Open session
session = Session.open(
    sample_id="post_cavity_sample_A",
    cooldown_id="cd_2025_02_22",
    registry_base="E:/qubox",
    qop_ip="10.157.36.68",
    cluster_name="Cluster_2",
)

# Run qubit spectroscopy
result = session.exp.qubit.spectroscopy(
    qubit="q0",
    readout="rr0",
    freq=session.sweep.linspace(-30e6, 30e6, 241, center="q0.ge"),
    drive_amp=0.02,
    n_avg=200,
)

# Inspect and plot
print(result.inspect())
result.plot()

# Calibration proposal
proposal = result.proposal()
if proposal:
    print(proposal.review())

session.close()
```

### 21.2 Custom Sequence Experiment

```python
from qubox import Session

session = Session.open(
    sample_id="sampleA",
    cooldown_id="cd_2026_03_13",
    registry_base="E:/qubox",
    qop_ip="10.157.36.68",
    cluster_name="Cluster_2",
)

# Build sequence
seq = session.sequence("spin_echo")
seq.add(session.ops.reset("qubit", mode="passive"))
seq.add(session.ops.x90("qubit"))
seq.add(session.ops.wait("qubit", 100))
seq.add(session.ops.x180("qubit"))
seq.add(session.ops.wait("qubit", 100))
seq.add(session.ops.x90("qubit"))
seq.add(session.ops.measure("readout", mode="iq"))

# Run with sweep
delay_axis = session.sweep.linspace(4, 1000, 100, parameter="delay")
result = session.exp.custom(
    sequence=seq,
    sweep=delay_axis,
    acquire=session.acquire.iq("readout"),
    analysis="iq_magnitude",
    n_avg=500,
)
```

### 21.3 Custom Circuit Experiment

```python
circ = session.circuit("cat_state_prep")
circ.add(session.ops.displacement("storage", amp=2.0, phase=0.0))
circ.add(session.ops.x90("qubit"))
circ.add(session.ops.wait("qubit", 50))
circ.add(session.ops.x90("qubit"))
circ.add(session.ops.measure("readout"))

result = session.exp.custom(
    circuit=circ,
    acquire=session.acquire.iq("readout"),
    n_avg=100,
)
```

### 21.4 Notebook Pattern with Legacy Compatibility

This is the pattern used in the tutorial notebook. It mixes the new `qubox`
session API with legacy experiment classes imported through `qubox.notebook`:

```python
from qubox.notebook import (
    get_notebook_session_bootstrap_path,
    open_shared_session,
    ResonatorSpectroscopy,
    QubitSpectroscopy,
    PowerRabi,
    SampleRegistry,
    Patch,
    save_config_snapshot,
)

# Open or reuse the shared session opened by notebook 00
bootstrap_path = get_notebook_session_bootstrap_path(
    sample_id="post_cavity_sample_A",
    cooldown_id="cd_2025_02_22",
    registry_base="E:/qubox",
)
session = open_shared_session(
    sample_id="post_cavity_sample_A",
    cooldown_id="cd_2025_02_22",
    registry_base="E:/qubox",
    qop_ip="10.157.36.68",
    cluster_name="Cluster_2",
)

# Use legacy experiment directly
resonator_spec = ResonatorSpectroscopy(session.legacy_session)
build = resonator_spec.build_program(
    readout_op="readout",
    rf_begin=8.590e9,
    rf_end=8.600e9,
    df=2.0e5,
    n_avg=1,
)

# Or use new API
result = session.exp.resonator.spectroscopy(
    readout="rr0",
    freq=session.sweep.linspace(-5e6, 5e6, 201, center="readout"),
)
```

### 21.5 Analysis with qubox_tools

```python
import numpy as np
import qubox_tools as qt

# Load saved run data
output = qt.Output.from_file("path/to/resonator_spectroscopy.npz")

# Fit a resonator dip
freqs = output.extract("frequencies")
signal = output.extract("signal_magnitude")

popt, pcov = qt.generalized_fit(
    freqs, signal,
    qt.fitting.models.lorentzian_model,
    p0=[freqs[np.argmin(signal)], 1e6, float(np.min(signal)), float(np.max(signal))],
)
print(f"Resonance: {popt[0] / 1e9:.6f} GHz")
```

---

## 22. Known Gaps and Inconsistencies

### 22.1 README.md Alignment

> **Status:** Resolved. The `README.md` now correctly documents `qubox` as
> the canonical user-facing package with `from qubox import Session` examples.

### 22.2 Limited Template Adapter Coverage

Only five experiment templates are currently registered in `QMRuntime`:
- `qubit.spectroscopy`
- `resonator.spectroscopy`
- `qubit.power_rabi`
- `qubit.ramsey`
- `reset.active`

The 25+ other experiments (T1, AllXY, DRAG, Fock-resolved, tomography, etc.)
are accessible only through:
- Legacy compatibility imports (`qubox.notebook`), or
- Custom sequence/circuit composition (`session.exp.custom()`).

### 22.3 qubox_v2_legacy Naming

The legacy package was renamed from `qubox_v2` to `qubox_v2_legacy` as part
of the migration. All internal references (compat layer, tests, tools) now
correctly use `qubox_v2_legacy` as the import target.

> **Status:** Resolved. The compat layer (`qubox.notebook`) and all
> internal code reference `qubox_v2_legacy` consistently.

### 22.4 Sweep Axis Center Resolution

When a `SweepAxis` has a `center` token (e.g. `"q0.ge"`), the center offset
is resolved and added to the sweep values at execution time inside
`QMRuntime`, not at construction time. This means `axis.values` contains
*relative* values until the request is run.

### 22.5 Custom Experiment Sweep Integration

Sweep axes provided to `session.exp.custom()` are stored in circuit metadata
as `"sweep_axes"` but are not yet used to drive actual QUA loop sweeps.
The current implementation passes sweep metadata through and uses the
averaging count from `SweepPlan.averaging`, but the sweep variable is not
looped over in the generated QUA program. Multi-point sweeps in custom
experiments require further backend work.

### 22.6 Analysis Pipeline Simplicity

The built-in named analysis pipelines (`"raw"`, `"iq_magnitude"`,
`"ramsey_like"`, `"classified"`) are quite basic — they extract I/Q data
and compute magnitude/phase. More sophisticated analysis (curve fitting,
peak finding, T1/T2 extraction) should use `qubox_tools` or be handled
by legacy experiment `.analyze()` methods.

---

## Appendix A: Top-Level Exports

Complete list of `qubox.__all__`:

```python
[
    "__version__",        # str: "3.0.0"
    "AcquisitionSpec",    # qubox.sequence.acquisition
    "CalibrationProposal",# qubox.calibration.models
    "CalibrationSnapshot",# qubox.calibration.models
    "Condition",          # qubox.sequence.models
    "ExecutionRequest",   # qubox.data.models
    "ExperimentResult",   # qubox.data.models
    "Operation",          # qubox.sequence.models
    "QuantumCircuit",     # qubox.circuit.models
    "QuantumGate",        # qubox.circuit.models
    "Sequence",           # qubox.sequence.models
    "Session",            # qubox.session.session
    "SweepAxis",          # qubox.sequence.sweeps
    "SweepPlan",          # qubox.sequence.sweeps
]
```

---

## Appendix B: Quick-Reference Cheat Sheet

```python
# ── Imports ──────────────────────────────────────────────
from qubox import Session

# ── Open Session ─────────────────────────────────────────
session = Session.open(
    sample_id="sampleA",
    cooldown_id="cd_2026_03_13",
    registry_base="E:/qubox",
    qop_ip="10.157.36.68",
    cluster_name="Cluster_2",
)

# ── Sweep ────────────────────────────────────────────────
freq = session.sweep.linspace(-30e6, 30e6, 241, center="q0.ge")
amps = session.sweep.param("amplitude").linspace(0.01, 1.0, 50)

# ── Template Experiments ─────────────────────────────────
result = session.exp.resonator.spectroscopy(readout="rr0", freq=freq)
result = session.exp.qubit.spectroscopy(qubit="q0", readout="rr0", freq=freq, drive_amp=0.02)
result = session.exp.qubit.power_rabi(qubit="q0", readout="rr0", amplitude=amps)
result = session.exp.qubit.ramsey(qubit="q0", readout="rr0", delay=delays)
result = session.exp.reset.active(qubit="q0", readout="rr0")

# ── Custom Sequence ──────────────────────────────────────
seq = session.sequence("my_exp")
seq.add(session.ops.x90("qubit"))
seq.add(session.ops.wait("qubit", 100))
seq.add(session.ops.x90("qubit"))
seq.add(session.ops.measure("readout"))
result = session.exp.custom(sequence=seq, acquire=session.acquire.iq("readout"), n_avg=500)

# ── Custom Circuit ───────────────────────────────────────
circ = session.circuit("my_circuit")
circ.add(session.ops.displacement("storage", amp=1.0))
circ.add(session.ops.measure("readout"))
result = session.exp.custom(circuit=circ, acquire=session.acquire.iq("readout"))

# ── Results ──────────────────────────────────────────────
result.inspect()
result.plot()

# ── Calibration ──────────────────────────────────────────
proposal = result.proposal()
if proposal:
    print(proposal.review())
    proposal.apply(session, dry_run=True)   # preview
    proposal.apply(session, dry_run=False)  # commit

# ── Close ────────────────────────────────────────────────
session.close()
```

---

## Appendix C: Migration Guide from qubox\_v2

### Import Changes

| Old (`qubox_v2`) | New (`qubox`) |
|-------------------|---------------|
| `from qubox_v2.experiments.session import SessionManager` | `from qubox import Session` |
| `SessionManager(...).open()` | `Session.open(...)` |
| `from qubox_v2.experiments import PowerRabi` | `session.exp.qubit.power_rabi(...)` or `from qubox.notebook import PowerRabi` |
| `from qubox_v2.calibration import CalibrationOrchestrator` | `from qubox.notebook import CalibrationOrchestrator` |
| `from qubox_v2.devices import SampleRegistry` | `from qubox.notebook import SampleRegistry` |
| Direct experiment `run()` calls | Template experiments via `session.exp.*` or legacy via `qubox.notebook` |

### Workflow Changes

| Old Pattern | New Pattern |
|-------------|-------------|
| `experiment = PowerRabi(session)` / `experiment.run(...)` | `session.exp.qubit.power_rabi(...)` returns `ExperimentResult` |
| `orch.run_analysis_patch_cycle(...)` | `result = session.exp.qubit.*(...); proposal = result.proposal(); proposal.apply(session)` |
| Manual `PulseOperationManager` interaction | `session.ops.*` for semantic operations |
| `session.legacy_session.pulse_mgr` | `session.pulse_mgr` (direct property) |
| `session.legacy_session.hw` | `session.hardware` (direct property) |
| `session.legacy_session.calibration` | `session.calibration` (direct property) |
| `session.context_snapshot()` | `session.legacy_session.context_snapshot()` |
| `from qubox.analysis import ...` | `from qubox_tools.algorithms.pipelines import ...` |
| `from qubox.optimization import ...` | `from qubox_tools.optimization import ...` |
| `QuaProgramManager(...)` | Use `HardwareController`, `ConfigEngine`, `ProgramRunner`, `QueueManager` |

### What Stays the Same

- The underlying hardware interaction (OPX+ / Octave) is unchanged.
- Calibration JSON schema (v5.0.0) is unchanged.
- `qubox_tools` for analysis is unchanged.
- Sample/cooldown filesystem layout is unchanged.
- All 30+ legacy experiment classes are still available via `qubox.notebook`.

---

*End of API Reference.*
