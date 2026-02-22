# QuBox V2 System Architecture

**Version**: 1.0.0
**Date**: 2026-02-21
**Status**: Governing Document

---

## 1. Design Philosophy

1. **Legacy is behavioral ground truth.** Waveform generation, sign conventions, normalization rules, and calibration parameter semantics must match the legacy `qubox_legacy` implementation exactly. Deviations are bugs unless explicitly documented and justified.

2. **No implicit behavior.** Every mutation to hardware state, calibration data, pulse definitions, or QM config must be traceable to an explicit user action in the notebook or a documented API call. Silent side effects are prohibited.

3. **Declarative over imperative.** Persistent state (hardware, pulse specs, calibration) is stored as declarative specifications. Runtime artifacts (waveform arrays, QM config dicts) are compiled from specifications and never persisted as source of truth.

4. **Calibration requires human approval.** The system acquires data, analyzes it, and presents results. The human decides whether to commit. No automatic calibration updates.

5. **Modular layering with strict boundaries.** Each layer has defined responsibilities and dependencies. No circular imports. No layer may implicitly mutate another layer's state.

---

## 2. System Layers

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 9: Notebook / User Interface                         │
│  ─ Jupyter notebooks, CLI, interactive workflows            │
│  ─ Drives the Acquire → Analyze → Plot → Approve cycle     │
├─────────────────────────────────────────────────────────────┤
│  Layer 8: Verification + Legacy Parity Harness              │
│  ─ Waveform regression tests vs legacy generators           │
│  ─ Schema validation, calibration integrity checks          │
│  ─ Module: qubox_v2/verification/                           │
├─────────────────────────────────────────────────────────────┤
│  Layer 7: Artifact Manager                                  │
│  ─ Separates source-of-truth from generated artifacts       │
│  ─ Build-hash-keyed artifact storage                        │
│  ─ Module: qubox_v2/core/artifact_manager.py                │
├─────────────────────────────────────────────────────────────┤
│  Layer 6: Experiment Definitions                            │
│  ─ ExperimentBase subclasses: run() → analyze() → plot()    │
│  ─ Modules: qubox_v2/experiments/{calibration,cavity,...}    │
│  ─ Depends on: Layers 1-5 (via SessionManager context)      │
├─────────────────────────────────────────────────────────────┤
│  Layer 5: Calibration Management                            │
│  ─ CalibrationStore (JSON-backed, Pydantic models)          │
│  ─ CalibrationStateMachine (lifecycle governance)           │
│  ─ CalibrationPatch (explicit diff objects)                 │
│  ─ Module: qubox_v2/calibration/                            │
├─────────────────────────────────────────────────────────────┤
│  Layer 4: ConfigCompiler                                    │
│  ─ Merges hardware + compiled pulses → QM config_dict       │
│  ─ Layered overlay system (hardware → pulses → runtime)     │
│  ─ Module: qubox_v2/hardware/config_engine.py               │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: PulseFactory + Operation Binding                  │
│  ─ Compiles declarative pulse_specs → waveform arrays       │
│  ─ PulseOperationManager binds pulses to elements           │
│  ─ Modules: qubox_v2/pulses/                                │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: Pulse Specification                               │
│  ─ Declarative pulse recipes (pulse_specs.json)             │
│  ─ No waveform sample arrays at rest                        │
│  ─ Module: qubox_v2/pulses/spec_models.py                   │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: Hardware Abstraction                              │
│  ─ hardware.json (controllers, octaves, elements)           │
│  ─ HardwareController (OPX+/Octave operations)             │
│  ─ Module: qubox_v2/hardware/                               │
└─────────────────────────────────────────────────────────────┘
```

### Dependency Rules

- Layers may depend only on layers with **lower** numbers.
- Layer N must not import from Layer N+1 or higher.
- Cross-layer communication uses **explicit interfaces** defined in `core/protocols.py`.
- The only exception is Layer 9 (notebook), which may access any layer through `SessionManager`.

---

## 3. Module Responsibilities

### 3.1 `qubox_v2/core/`

| Module | Responsibility |
|--------|---------------|
| `config.py` | Pydantic models for `hardware.json` (`HardwareConfig`, `ElementConfig`, etc.) |
| `types.py` | Enums (`ExecMode`, `PulseType`, `WaveformType`), type aliases, constants (`MAX_AMPLITUDE`, `CLOCK_CYCLE_NS`) |
| `protocols.py` | `@runtime_checkable` Protocol interfaces for all layer boundaries |
| `errors.py` | Exception hierarchy |
| `session_state.py` | **NEW** — Immutable runtime snapshot (`SessionState`) |
| `schemas.py` | **NEW** — Schema version validators and migration utilities |
| `artifact_manager.py` | **NEW** — Build-hash-keyed artifact storage |
| `artifacts.py` | Config snapshots and run summaries (existing) |
| `preflight.py` | Pre-experiment validation checks |
| `logging.py` | Logging configuration |
| `utils.py` | General utilities |

### 3.2 `qubox_v2/hardware/`

| Module | Responsibility |
|--------|---------------|
| `config_engine.py` | Layered QM config compilation (hardware → pulse overlay → runtime overrides) |
| `controller.py` | `HardwareController` — OPX+/Octave frequency, gain, LO operations |
| `program_runner.py` | `ProgramRunner` — QUA program execution, `RunResult` production |
| `qua_program_manager.py` | QUA program queue and lifecycle management |
| `queue_manager.py` | Job queue for sequential/parallel execution |

### 3.3 `qubox_v2/pulses/`

| Module | Responsibility |
|--------|---------------|
| `manager.py` | `PulseOperationManager` — dual-store (permanent/volatile) pulse, waveform, weight, and element-op mapping management |
| `models.py` | `WaveformSpec`, `PulseSpec` dataclasses |
| `spec_models.py` | **NEW** — Declarative pulse specification models (`PulseSpecEntry`, shape-specific params) |
| `factory.py` | **NEW** — `PulseFactory` — compiles `pulse_specs.json` + calibration → waveform arrays |
| `integration_weights.py` | Integration weight creation and manipulation |
| `waveforms.py` | Low-level waveform sample generation (constant, square, gaussian, normalize) |
| `pulse_registry.py` | Pulse registry for discovery/lookup |

### 3.4 `qubox_v2/calibration/`

| Module | Responsibility |
|--------|---------------|
| `store.py` | `CalibrationStore` — JSON-backed persistence with typed Pydantic access |
| `models.py` | Pydantic models: `CalibrationData`, `DiscriminationParams`, `ElementFrequencies`, `PulseCalibration`, etc. |
| `state_machine.py` | **NEW** — `CalibrationStateMachine` — lifecycle governance (IDLE → ACQUIRED → ANALYZED → COMMITTED) |
| `patch.py` | **NEW** — `CalibrationPatch` — explicit diff objects for calibration updates |
| `history.py` | Snapshot comparison and diff utilities |
| `algorithms.py` | Calibration-specific algorithms |
| `mixer_calibration.py` | IQ mixer calibration (SA-based) |

### 3.5 `qubox_v2/experiments/`

| Module | Responsibility |
|--------|---------------|
| `session.py` | `SessionManager` — central context object, initialization, lifecycle |
| `experiment_base.py` | `ExperimentBase` — base class enforcing `run()/analyze()/plot()` contract |
| `base.py` | `ExperimentRunner` — lower-level hardware runner |
| `result.py` | `RunResult`, `AnalysisResult`, `FitResult` data containers |
| `config_builder.py` | Dynamic QM config construction utilities |
| `calibration/` | Readout, gates, reset calibration experiments |
| `spectroscopy/` | Resonator and qubit spectroscopy |
| `time_domain/` | Rabi, T1, T2, coherence measurements |
| `cavity/` | Storage spectroscopy, Fock-resolved experiments |
| `tomography/` | Qubit state, Wigner, SNAP tomography |
| `spa/` | SPA flux/pump optimization |

### 3.6 `qubox_v2/programs/`

| Module | Responsibility |
|--------|---------------|
| `cQED_programs.py` | QUA program constructors (all experiment programs) |
| `macros/measure.py` | `measureMacro` — global readout macro singleton |
| `macros/sequence.py` | Sequence macro utilities |

### 3.7 `qubox_v2/tools/`

| Module | Responsibility |
|--------|---------------|
| `waveforms.py` | High-level waveform generators: DRAG Gaussian, Kaiser, Slepian, CLEAR, flat-top variants |
| `generators.py` | Pulse registration helpers: `register_rotations_from_ref_iq`, `ensure_displacement_ops` |

---

## 4. Data Flow

### 4.1 Session Initialization

```
hardware.json ──┐
                │
pulse_specs.json ──┤──→ SchemaValidator ──→ SessionState (immutable snapshot)
                │                              │
calibration.json ──┘                           │
                                               ├──→ PulseFactory.compile() ──→ waveform arrays
                                               │
                                               └──→ ConfigCompiler.build() ──→ QM config_dict
                                                                                    │
                                                                              QuantumMachine
```

### 4.2 Experiment Execution

```
Notebook cell
    │
    ▼
ExperimentBase.run(**params)
    │
    ├──→ build QUA program (using measureMacro, element names, pulse ops)
    ├──→ ProgramRunner.run_program(prog, n_total=N)
    │       │
    │       ├──→ QM.execute(prog)
    │       └──→ stream processing → RunResult.output
    │
    ▼
RunResult (raw data + metadata)
    │
    ▼
ExperimentBase.analyze(result)
    │
    ├──→ fitting, metric extraction
    └──→ AnalysisResult (data, fit, metrics, metadata)
            │
            ▼
ExperimentBase.plot(analysis)
    │
    ▼
User reviews → decides → CalibrationPatch → CalibrationStore.commit()
```

### 4.3 Calibration Update Flow

```
analyze(result)
    │
    ▼
CalibrationPatch
    ├── target: "frequencies.resonator.if_freq"
    ├── old_value: -231980828.47
    ├── new_value: -232000000.0
    └── validation: {min_r2: 0.95, bounds: {...}}
    │
    ▼
CalibrationStateMachine
    ├── IDLE → ACQUIRED → ANALYZED → PENDING_APPROVAL
    │                                       │
    │                     user approves ─────┘
    │                                       │
    └── PENDING_APPROVAL → COMMITTING → COMMITTED
                              │
                              ├── CalibrationStore.apply_patch(patch)
                              ├── calibration_history.jsonl (append)
                              └── CalibrationStore.save()
```

---

## 5. Persistent File Ownership

| File | Owner | Schema Version | Mutability |
|------|-------|---------------|------------|
| `hardware.json` | ConfigEngine | v1 | Manual edits only |
| `pulse_specs.json` | PulseFactory | v1 | Session writes via `set_pulse_definition` |
| `calibration.json` | CalibrationStore | v3 | Only via CalibrationPatch during COMMITTING state |
| `cqed_params.json` | cQED_attributes | unversioned | Legacy compat; read-only in v2 |
| `measureConfig.json` | measureMacro | v5 | Written by session lifecycle |
| `devices.json` | DeviceManager | unversioned | Manual edits only |
| `pulses.json` | PulseOperationManager | v2 | **DEPRECATED** — transitional only |

---

## 6. Legacy Compatibility Rules

1. **Waveform generation functions** in `tools/waveforms.py` must produce bit-identical output to legacy `qualang_tools` equivalents for identical parameters.

2. **Sign conventions**: The DRAG quadrature term uses `alpha / (2π × anharmonicity - 2π × detuning)`. This matches the Chen et al. convention used in legacy. Never change denominators.

3. **Rotation gate math**: `register_rotations_from_ref_iq` implements `w_new = amp_scale × w0 × exp(-j × phi_eff)` matching `gates_legacy.QubitRotation.waveforms()`. The negative sign in the exponent is intentional and must not change.

4. **Integration weight naming**: Legacy uses stemless triplet (`cos`, `sin`, `minus_sin`) for readout weights. Optimized weights prefix with `opt_`. Rotated weights prefix with `rot_`. This convention must be preserved.

5. **measureMacro push/restore**: Any experiment that temporarily modifies measureMacro state must call `push_settings()` before and `restore_settings()` after. This matches legacy `cQED_experiments.py` behavior.

6. **Post-processing output keys**: QUA program output key names (`II`, `IQ`, `QI`, `QQ`, `I`, `Q`, `S`, `g_trace`, `e_trace`) must match legacy expectations. Analysis code and notebooks depend on these names.

---

## 7. Extension Guidelines

### Adding a New Experiment

1. Create a subclass of `ExperimentBase` in the appropriate subpackage.
2. Implement `run()` returning `RunResult`, `analyze()` returning `AnalysisResult`, `plot()`.
3. Register in the subpackage `__init__.py` and in `experiments/__init__.py`.
4. Add a notebook cell in `post_cavity_experiment.ipynb` following the `run → analyze → plot` pattern.
5. Do not generate hidden operations. If the experiment needs custom pulses, require them as parameters.
6. Do not auto-update calibration. Use `guarded_calibration_commit()` or produce a `CalibrationPatch`.

### Adding a New Pulse Shape

1. Implement the waveform generator in `tools/waveforms.py` as a pure function returning `(I_wf, Q_wf)`.
2. Add a corresponding shape type in `pulses/spec_models.py`.
3. Register the shape handler in `pulses/factory.py`.
4. Add a legacy parity test in `verification/legacy_parity.py` if the shape has a legacy equivalent.
5. Sign conventions and normalization must match legacy if applicable.

### Adding a New Config File

1. Define a Pydantic model in `core/config.py` or the appropriate module.
2. Add schema version field: `schema_version: int = 1`.
3. Register a schema validator in `core/schemas.py`.
4. Document in `SCHEMA_VERSIONING.md`.
5. Add to the artifact policy (source-of-truth or generated).

---

## 8. Invariants

These conditions must hold at all times during a session:

1. `SessionManager.open()` must complete without errors before any experiment runs.
2. Every element in the QM config must have at least `const` and `zero` operations registered.
3. `calibration.json` is only written during the `COMMITTING` state of the calibration state machine (once enforced).
4. Waveform arrays are never persisted in `pulse_specs.json`. They exist only in memory and in generated artifacts.
5. `SessionState.build_hash` changes if and only if a source-of-truth file changes.
6. No experiment constructor may modify hardware state, pulse definitions, or calibration data. Side effects are confined to `run()`.
