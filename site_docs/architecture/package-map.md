# Package Map

A comprehensive map of every subpackage in the qubox ecosystem.

## qubox/ — Core Package

### Core Foundation (`qubox.core`)

| Module | Purpose |
|--------|---------|
| `errors.py` | `QuboxError` hierarchy (8 exception types) |
| `types.py` | `ExecMode`, `PulseType`, `WaveformType`, type aliases |
| `config.py` | Pydantic v2 models: `ControllerConfig`, `OctaveConfig`, `ElementConfig`, `HardwareConfig` |
| `bindings.py` | `ChannelRef`, `OutputBinding`, `InputBinding`, `ReadoutBinding`, `ExperimentBindings` |
| `hardware_definition.py` | `HardwareDefinition` — QM config + Octave generation |
| `device_metadata.py` | `DeviceMetadata` — frozen dataclass replacing legacy `cQED_attributes` |
| `pulse_op.py` | `PulseOp` — pulse operation descriptor |
| `persistence.py` | JSON serialization helpers |
| `protocols.py` | Protocol classes for structural typing |
| `logging.py` | `configure_global_logging()`, `get_logger()` |

### Session (`qubox.session`)

| Module | Purpose |
|--------|---------|
| `session.py` | `Session` — primary user entry point, wraps legacy `SessionManager` |
| `context.py` | `ExperimentContext`, `compute_wiring_rev()` |
| `state.py` | `SessionState` — immutable runtime snapshot |

### Sequence IR (`qubox.sequence`)

Hardware-agnostic intermediate representation for experiment operations.

| Module | Purpose |
|--------|---------|
| `models.py` | `Operation`, `Condition`, `Sequence` |
| `sweeps.py` | `SweepAxis`, `SweepFactory`, `SweepPlan` |
| `acquisition.py` | `AcquisitionSpec` |

### Circuit (`qubox.circuit`)

Gate-level abstraction layer:

| Module | Purpose |
|--------|---------|
| `models.py` | `QuantumCircuit`, `QuantumGate` — gate-sequence view over the Sequence IR |

### Experiments (`qubox.experiments`)

40+ experiment classes organized by physics domain:

| Subpackage | Content |
|-----------|---------|
| `spectroscopy/` | Resonator, qubit, EF spectroscopy |
| `time_domain/` | Rabi, T1, T2, chevrons |
| `calibration/` | IQ blob, AllXY, DRAG, readout optimization, RB |
| `cavity/` | Storage spectroscopy, Fock-resolved, chi-Ramsey |
| `tomography/` | State tomography, Wigner, SNAP |
| `spa/` | SPA flux/pump optimization |
| `custom/` | User-defined experiment base |

Infrastructure:

| Module | Purpose |
|--------|---------|
| `experiment_base.py` | `ExperimentBase` — run/analyze/configure lifecycle |
| `base.py` | `ExperimentRunner` — execution engine |
| `templates.py` | `ExperimentLibrary` (`session.exp.*`) |
| `workflows.py` | `WorkflowLibrary` (`session.workflow.*`) |
| `session.py` | Legacy `SessionManager` (execution backend) |
| `result.py` | `FitResult`, `RunResult`, `AnalysisResult`, `ProgramBuildResult` |

### Programs (`qubox.programs`)

QUA program factories:

| Module | Purpose |
|--------|---------|
| `builders/` | Domain-organized QUA builders |
| `macros/` | QUA template helpers (sequence, measure) |
| `circuit_runner.py` | Sequence → QUA compiler |
| `circuit_compiler.py` | Circuit → QUA lowering |

### Calibration (`qubox.calibration`)

Full calibration lifecycle:

| Module | Purpose |
|--------|---------|
| `store.py` | `CalibrationStore` — JSON-backed, versioned |
| `store_models.py` | 12+ Pydantic v2 data models |
| `orchestrator.py` | `CalibrationOrchestrator` — run → analyze → patch |
| `patch_rules.py` | 11 patch rules (PiAmpRule, FrequencyRule, etc.) |
| `transitions.py` | Pulse name resolution, transition families |
| `history.py` | Snapshot listing, loading, diffing |

### Hardware (`qubox.hardware`)

| Module | Purpose |
|--------|---------|
| `config_engine.py` | `ConfigEngine` — load/save/patch QM config |
| `controller.py` | `HardwareController` — live element control |
| `program_runner.py` | `ProgramRunner` — execute/simulate QUA |
| `queue_manager.py` | `QueueManager` — job queue |

### Backends (`qubox.backends`)

| Module | Purpose |
|--------|---------|
| `qm/runtime.py` | `QMRuntime` — template → legacy → hardware bridge |
| `qm/lowering.py` | Circuit → legacy QUA bridge |

### Workflow (`qubox.workflow`)

Portable workflow primitives (no notebook dependency):

| Module | Purpose |
|--------|---------|
| `stages.py` | `WorkflowConfig`, `StageCheckpoint`, checkpoint save/load |
| `calibration_helpers.py` | `preview_or_apply_patch_ops()` |
| `fit_gates.py` | `fit_quality_gate()`, `fit_center_inside_window()` |
| `pulse_seeding.py` | `ensure_primitive_rotations()` |

### Notebook (`qubox.notebook`)

| Module | Purpose |
|--------|---------|
| `__init__.py` | Essentials (~65 symbols): experiments, session, workflow, calibration basics |
| `advanced.py` | Infrastructure (~45 symbols): store models, artifacts, schemas, verification |
| `runtime.py` | Session bootstrap, shared session management |
| `workflow.py` | Thin wrapper over `qubox.workflow` with notebook session integration |

### Other Subpackages

| Package | Purpose |
|---------|---------|
| `gates/` | Runtime hardware gate implementations used by control realization |
| `pulses/` | Pulse management, waveform generation, integration weights |
| `devices/` | Sample/cooldown registry, device management |
| `tools/` | Waveform generators (DRAG, Kaiser, Slepian) |
| `verification/` | Schema checks, waveform regression |

**Removed packages:** Standalone ansatz compilation (`qubox.compile`) and
numerical cQED simulation (`qubox.simulation`) were removed from `qubox`.
The older gate-model, fidelity, noise, and gate-sequence helpers were also
removed from `qubox.gates`; only the runtime hardware gate layer remains.
`qubox/gui/` and `qubox/migration/` are empty directory stubs with no code.

Demo scripts and the optional GUI runner live under top-level `tools/`.

---

## qubox_tools/ — Analysis Toolkit

| Subpackage | Purpose |
|-----------|---------|
| `data/containers.py` | `Output` — smart result extraction, `.npz` save/load |
| `fitting/routines.py` | `generalized_fit()` — robust fitting with retry, global opt |
| `fitting/models.py` | 10+ model functions (Lorentzian, Gaussian, Voigt, exp decay) |
| `fitting/cqed.py` | cQED-specific models |
| `fitting/calibration.py` | Fitting → CalibrationStore bridge |
| `algorithms/core.py` | Peak finding, threshold estimation |
| `algorithms/post_process.py` | Demodulation, readout error correction |
| `algorithms/transforms.py` | IQ projection, post-selection, encoding |
| `algorithms/post_selection.py` | `PostSelectionConfig` (5 policies) |
| `algorithms/metrics.py` | Wilson CI, Gaussianity scores |
| `optimization/bayesian.py` | GP Bayesian optimization |
| `optimization/local.py` | `scipy.optimize.minimize` wrapper |
| `optimization/stochastic.py` | DE, CMA-ES |
| `plotting/common.py` | Generic 2D heatmap |
| `plotting/cqed.py` | Bloch sphere, IQ scatter, chevrons, tomography |

---

## qubox_lab_mcp/ — Lab MCP Server

| Component | Purpose |
|-----------|---------|
| `server.py` | MCP server entry point |
| `config.py` | `ServerConfig`, `load_server_config` |
| `services.py` | Service orchestration |
| `resources/` | MCP resource handlers |
| `tools/` | MCP tool implementations |
| `adapters/` | External system adapters |
| `models/` | Data transfer objects |
| `policies/` | Access & rate-limiting policies |
