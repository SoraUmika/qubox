# qubox\_v2 — API Reference & Architecture Guide

**Version**: 2.1.0
**Date**: 2026-03-02
**Status**: Governing Document
**Changelog**:
- v2.1.0 — Workflow safety refactoring (P0.1–P2.1): FitResult.success
  contract (no silent failures), transactional apply\_patch with rollback
  and dry\_run=True default, heuristic unit conversion removal,
  CalibrationStore as single source of truth (verify\_consistency,
  from\_calibration\_store), session-scoped MeasurementConfig frozen
  dataclass, MultiProgramExperiment base class.
- v2.0.0 — Binding-driven API redesign: explicit `ChannelRef` / `OutputBinding`
  / `ReadoutBinding` / `ExperimentBindings` types replace implicit element-name
  coupling.  CalibrationStore schema v5.0.0 with `alias_index` and physical
  channel ID keying.  `measure_with_binding()` free function.  `PulseRegistry`
  `_RESERVED_OPS` cleared.  Session `.bindings` property.  Preflight bindings
  validation.  See CHANGELOG.md for full details.
- v1.8.0 — Audit-driven bug fixes and hardening: Wigner negativity formula,
  T1Rule heuristic, QubitStateTomography plot, SPA exception logging, patch
  rule deduplication, missing resonator\_freq FrequencyRule, dead
  update\_calibration warnings, StorageSpectroscopyCoarse calibration pattern,
  FockResolvedSpectroscopy peak extraction, SPAFluxOptimization2 dead params.
- v1.7.0 — Renamed DeviceRegistry -> SampleRegistry, device_id -> sample_id
  throughout.  Backward-compat aliases preserved.  On-disk migration from
  devices/ to samples/.  See CHANGELOG.md for details.
- v1.6.0 — Schema refactor: calibration schema version 4.0.0 is now canonical.
  `ElementFrequencies.lo_freq`/`if_freq` made optional; `rf_freq` field added.
  `PulseCalibration.element` made optional.  Readout metadata fields added to
  `DiscriminationParams` and `ReadoutQuality` (`n_shots`, `integration_time_ns`,
  `demod_weights`, `state_prep_ops`).  Derived primitive pulses (`x180`, `y180`,
  etc.) removed from `calibration.json` — only true calibration primitives
  (`ref_r180`, `sel_ref_r180`) are stored.  Null-handling policy: unset optional
  fields are omitted from persisted JSON via `exclude_none=True`.  Frequency
  convention documented: LO+IF pair or explicit `rf_freq`.  Readout calibration
  pipeline requires explicit patch step (no hidden in-place mutation).
  `DragAlphaRule` now patches only `ref_r180` — derived pulses inherit via
  `PulseFactory`.  CHANGELOG.md introduced with append-only change-log policy.
- v1.5.0 — Added section 23: Writing Custom Experiments.  Added usage examples
  throughout sections 2-9 and 13 (drawn from `post_cavity_experiment_context.ipynb`).
  Expanded sections 8 (Gate System) and Appendix A with gate-legacy API.
  Added Appendix C: Quick-Reference Cheat Sheet.
- v1.4.0 — Implemented macro refactor (Phases 1-3). Sections 13, 14, 15,
  20-22 updated to reflect: (a) cQED\_programs split into 8 builder
  sub-modules under `programs/builders/`, (b) new orchestrator patch ops
  `SetMeasureDiscrimination` / `SetMeasureQuality`, (c) `sync_from_calibration()`
  resolving the dual-truth problem, (d) analyze() purity enforced (no direct
  macro mutation), (e) `SessionManager.close()` now persists measureConfig.json,
  (f) `ExperimentBase.get_confusion_matrix()` added.
- v1.3.0 — Added sections 20-22: Macro System Architecture (measureMacro,
  sequenceMacros, cQED_programs), Experiment ↔ Macro Interaction Rules,
  Macro State Ownership & Persistence Boundaries.
- v1.2.0 — Added sections 16-19: ExperimentContext & SampleRegistry,
  CalibrationContext & ContextResolver, context-mode SessionManager,
  migration guide.  Updated section 15 with resolution status.
- v1.1.0 — Added sections 11-15: SessionManager lifecycle detail,
  artifact saving, CalibrationOrchestrator, measureConfig persistence, known gaps.

---

## Table of Contents

1. [High-Level Architecture Overview](#1-high-level-architecture-overview)
2. [End-to-End Workflow (Execution Lifecycle)](#2-end-to-end-workflow-execution-lifecycle)
3. [Core Object Model](#3-core-object-model)
4. [Calibration Architecture](#4-calibration-architecture)
5. [Declarative Pulse System](#5-declarative-pulse-system)
6. [Hardware Abstraction Layer](#6-hardware-abstraction-layer)
7. [State & Persistence Model](#7-state--persistence-model)
8. [Gate System](#8-gate-system)
9. [Experiment Registry](#9-experiment-registry)
10. [Comparison with Legacy](#10-comparison-with-legacy)
11. [SessionManager Lifecycle (Detailed)](#11-sessionmanager-lifecycle-detailed)
12. [Artifact Saving (Detailed)](#12-artifact-saving-detailed)
13. [CalibrationOrchestrator](#13-calibrationorchestrator)
14. [measureConfig / Readout Macro Persistence](#14-measureconfig--readout-macro-persistence)
15. [Known Gaps and Risks](#15-known-gaps-and-risks)
16. [ExperimentContext & SampleRegistry](#16-experimentcontext--sampleregistry)
17. [CalibrationContext & ContextResolver](#17-calibrationcontext--contextresolver)
18. [Context-Mode SessionManager](#18-context-mode-sessionmanager)
19. [Migration Guide: Legacy → Context Mode](#19-migration-guide-legacy--context-mode)
20. [Macro System Architecture](#20-macro-system-architecture)
21. [Experiment ↔ Macro Interaction Rules](#21-experiment--macro-interaction-rules)
22. [Macro State Ownership & Persistence Boundaries](#22-macro-state-ownership--persistence-boundaries)
23. [Writing Custom Experiments](#23-writing-custom-experiments)
24. [Binding-Driven API](#24-binding-driven-api)
25. [Roleless Experiment Primitives (v2.1)](#25-roleless-experiment-primitives-v21)
26. [Program Build & Simulation (v2.2)](#26-program-build--simulation-v22)
27. [HardwareDefinition Builder (v2.3)](#27-hardwaredefinition-builder-v23)
28. [Gate → Protocol → Circuit Architecture (v2.4)](#28-gate--protocol--circuit-architecture-v24)

**Appendices:**

- [Appendix A: Utility Functions](#appendix-a-utility-functions)
- [Appendix B: Known Inconsistencies](#appendix-b-known-inconsistencies)
- [Appendix C: Quick-Reference Cheat Sheet](#appendix-c-quick-reference-cheat-sheet)

---

## 1. High-Level Architecture Overview

### 1.1 What is qubox\_v2?

`qubox_v2` is a modular experiment orchestration framework for circuit-QED
systems built on Quantum Machines OPX+ hardware.  It replaces the legacy
monolithic `qubox` package with a layered architecture that enforces:

- **Declarative pulses** — persistent state stores *recipes*, never raw
  waveform arrays.
- **SessionState ownership** — an immutable snapshot of every configuration
  file is computed at startup; any source-of-truth change produces a new
  build hash.
- **Calibration-DB persistence** — calibration parameters live in a typed,
  versioned JSON store (`calibration.json`) governed by a state machine that
  requires human approval before writes.
- **No hidden experiment-side waveform mutation** — experiments consume
  declared operations; they never generate or register waveforms implicitly.
- **Notebook-first state-prep philosophy** — the Jupyter notebook is the
  single authoritative site for pulse declaration, state preparation, and
  calibration approval.

### 1.2 Module-Level Architecture

```
SessionManager                        ← Layer 9 entry point
    ├── ConfigEngine                  ← Layer 4: QM config compilation
    │       └── HardwareConfig        ← Layer 1: hardware.json model
    ├── HardwareController            ← Layer 1: OPX+/Octave live control
    ├── ProgramRunner                 ← Layer 1: QUA program execution
    ├── PulseOperationManager         ← Layer 3: dual-store pulse binding
    │       └── PulseFactory          ← Layer 3: spec → waveform compiler
    ├── PulseRegistry                 ← Layer 3: simplified registration API
    ├── CalibrationStore              ← Layer 5: typed JSON persistence
    ├── DeviceManager                 ← Layer 1: external instrument fleet
    ├── ArtifactManager               ← Layer 7: build-hash artifact storage
    ├── cQED_attributes               ← Physics parameters (frequencies, etc.)
    └── QueueManager                  ← Layer 1: job queue
```

### 1.3 Layer Dependency Rule

Layers may depend **only** on layers with lower numbers.  The notebook
(Layer 9) may access any layer through `SessionManager`.

```
Layer 9  Notebook / User Interface
Layer 8  Verification + Legacy Parity Harness
Layer 7  Artifact Manager
Layer 6  Experiment Definitions  (ExperimentBase subclasses)
Layer 5  Calibration Management  (CalibrationStore, StateMachine, Patch)
Layer 4  ConfigCompiler          (ConfigEngine)
Layer 3  PulseFactory + Operation Binding  (POM, PulseFactory, PulseRegistry)
Layer 2  Pulse Specification     (pulse_specs.json, spec_models)
Layer 1  Hardware Abstraction    (hardware.json, HardwareController, ProgramRunner)
```

### 1.4 Ownership Table

| Component | Owns | Must NOT Own |
|-----------|------|--------------|
| `SessionManager` | Infrastructure lifecycle, context wiring | Experiment logic, calibration decisions |
| `ConfigEngine` | QM config dict assembly | Hardware connections, pulse sample data |
| `HardwareController` | Live OPX+/Octave state (LO, gain, IF) | Calibration parameters, pulse definitions |
| `ProgramRunner` | QUA program submission and result capture | Config building, analysis |
| `PulseOperationManager` | Waveform/pulse/weight/op-mapping stores | Hardware state, calibration decisions |
| `CalibrationStore` | `calibration.json` read/write | Pulse registration, hardware control |
| `DeviceManager` | External instrument connections | QM elements, pulse definitions |
| `ArtifactManager` | Build-hash-keyed generated artifacts | Source-of-truth files |
| `ExperimentBase` | Experiment run/analyze/plot lifecycle | Session infrastructure, auto-calibration |

---

## 2. End-to-End Workflow (Execution Lifecycle)

### Step 1 — Session Initialization

**Legacy mode** (flat directory):

```python
session = SessionManager(experiment_path="seq_1_device/")
session.open()
```

**Context mode** (sample + cooldown scoping):

```python
from qubox_v2.devices import SampleRegistry
from qubox_v2.experiments.session import SessionManager

REGISTRY_BASE = Path("E:/qubox")
registry = SampleRegistry(REGISTRY_BASE)

# One-time: create sample and cooldown
registry.create_sample(
    "post_cavity_sample_A",
    description="Transmon qubit A — 3D cavity sample",
    config_source=Path("E:/qubox/seq_1_device/config"),
    metadata={"chip": "Q1-2025A", "fridge": "BlueFors-LD400"},
)
registry.create_cooldown(
    "post_cavity_sample_A", "cd_2025_02_22",
    seed_from=Path("E:/qubox/seq_1_device/config"),
)

# Open session
session = SessionManager(
    sample_id="post_cavity_sample_A",
    cooldown_id="cd_2025_02_22",
    registry_base=REGISTRY_BASE,
    qop_ip="10.157.36.68",
    cluster_name="Cluster_2",
    auto_save_calibration=True,
)
session.open()

# Inspect context
ctx = session.context
print(f"Sample: {ctx.sample_id}, Cooldown: {ctx.cooldown_id}")
print(f"Wiring Rev: {ctx.wiring_rev}, Config Hash: {ctx.config_hash}")
```

**What happens internally:**

1. **Load `hardware.json`** → `ConfigEngine` parses into `HardwareConfig`
   Pydantic model; validates schema version.
2. **Load `calibration.json`** → `CalibrationStore` constructs typed
   `CalibrationData` model (Pydantic v2, schema v3.0.0).
3. **Load `pulse_specs.json`** → `PulseFactory` ingests declarative recipes.
4. **Compile waveforms** → `PulseFactory.compile_all()` converts specs into
   I/Q sample arrays; `PulseFactory.register_all(pom)` binds them to
   elements.
5. **Construct runtime element objects** → `ConfigEngine.build_qm_config()`
   merges hardware + pulse overlay → QM config dict.
6. **Bind declared pulses to elements** → `PulseOperationManager.burn_to_config()`
   injects waveforms, pulses, weights, and element-op mappings.
7. **Register default operations** → every element receives `const` and `zero`.
8. **Open QM connection** → `HardwareController.open_qm(config_dict)`.
9. **Compute `SessionState`** → immutable SHA-256 build hash over all
   source-of-truth files.
10. **Initialize devices** → `DeviceManager.instantiate_all()` connects
    external instruments.

> **Invariant**: `SessionManager.open()` must complete before any experiment
> can run.

### Step 2 — Notebook-Level Operation Declaration

The user explicitly declares state-preparation pulses in notebook cells:

```python
from qubox_v2.tools.generators import register_rotations_from_ref_iq

# Register derived rotation gates from a reference IQ pair
register_rotations_from_ref_iq(
    session.pulse_mgr,
    ref_I=ref_I_wf,
    ref_Q=ref_Q_wf,
    element="qubit",
    ops={"x180": (pi, 0), "x90": (pi/2, 0), "y90": (pi/2, pi/2)},
)
session.burn_pulses()
```

**Example — register selective and displacement pulses for cavity experiments:**

```python
from qubox_v2.tools.waveforms import kaiser_pulse_waveforms
from qubox_v2.tools.generators import register_rotations_from_ref_iq, ensure_displacement_ops

# Selective pi pulse (Kaiser-windowed, spectrally narrow)
sel_I, sel_Q = kaiser_pulse_waveforms(
    amplitude=0.0013, length=1000, beta=7.967,
    detuning=0.0, subtracted=True, alpha=0.0,
    anharmonicity=-200e6,
)
sel_ops = register_rotations_from_ref_iq(
    session.pulse_mgr,
    ref_I=sel_I, ref_Q=sel_Q,
    element=attr.qb_el,
    prefix="sel_",
    rotations="all",            # x180, y180, x90, xn90, y90, yn90
    override=True, persist=False,
)

# Constant displacement pulse on storage cavity
session.pulse_mgr.create_control_pulse(
    element=attr.st_el,
    op="const_alpha",
    length=48,
    I_samples=[0.01958] * 48,
    Q_samples=[0.0] * 48,
    override=True, persist=False,
)

# Fock-resolved displacement pulses (disp_n0, disp_n1, ...)
created = ensure_displacement_ops(
    session.pulse_mgr,
    element=attr.st_el,
    n_max=3,
    coherent_amp=0.01958,
    coherent_len=48,
    b_alpha=1.0,
)

session.burn_pulses()  # Push all new operations to the live QM config
```

**Rules:**

- Every operation the experiment will `play()` must be registered before
  `run()`.
- There is no hidden `ensure_displacement_ops()`.  Displacement operations
  must be explicitly created.
- `burn_pulses()` pushes the current POM state into the live QM config.

### Step 3 — Experiment Construction

```python
from qubox_v2.experiments import PowerRabi

rabi = PowerRabi(session)
```

**Rules:**

- The experiment object stores a reference to the session context.
- **No waveform auto-generation is permitted.** The constructor must not
  create, register, or modify any pulse or waveform.
- Experiments consume only operations that were previously declared in
  Step 2 or during session initialization.

### Step 4 — Program Build & Execution

```python
result = rabi.run(max_gain=1.2, dg=0.04, op="ref_r180", n_avg=5000)
```

Internally, `run()`:

1. Calls `set_standard_frequencies()` to align element IF/LO to calibrated
   values.
2. Builds a QUA program via `build_program()`.
3. `PulseOperationManager` resolves `(element, op)` → pulse name → waveform
   samples.
4. Calibration parameters are injected where needed (e.g., readout threshold,
   discrimination angle).

**More experiment `run()` examples:**

```python
from qualang_tools.units import unit
u = unit()

# Resonator spectroscopy
spec = ResonatorSpectroscopy(session)
result = spec.run(
    readout_op="readout",
    rf_begin=8560 * u.MHz,
    rf_end=8640 * u.MHz,
    df=200 * u.kHz,
    n_avg=10000,
)

# T1 relaxation
t1 = T1Relaxation(session)
result = t1.run(delay_end=50 * u.us, dt=500, n_avg=2000)

# T2 Ramsey with detuning
t2r = T2Ramsey(session)
result = t2r.run(
    qb_detune=int(0.2e6),
    delay_end=40 * u.us,
    dt=100,
    n_avg=4000,
    qb_detune_MHz=0.2,
)

# IQ blob acquisition
iq = IQBlob(session)
result = iq.run("x180", n_runs=5000)

# Randomized benchmarking
rb = RandomizedBenchmarking(session)
result = rb.run(
    m_list=[1, 5, 10, 20, 50, 100, 200],
    num_sequence=20,
    n_avg=1000,
)

# Storage spectroscopy (requires const_alpha pulse registered)
st_spec = StorageSpectroscopy(session)
result = st_spec.run(
    disp="const_alpha",
    rf_begin=5200 * u.MHz,
    rf_end=5280 * u.MHz,
    df=200 * u.kHz,
    storage_therm_time=500,
    n_avg=50,
)
```

### Step 5 — Execution Details

```python
# Already called inside run():
# runner.run_program(qua_prog, n_total=n_avg)
```

- `ProgramRunner` submits the job to QM via `qm.execute()`.
- Optional progress reporting via `tqdm` handle or custom callback.
- SPA pump is managed via context manager (on before execute, off after).
- Execution metadata (duration, job ID, mode) captured in `RunResult`.

### Step 6 — Analysis & Calibration

```python
analysis = rabi.analyze(result, update_calibration=True, p0=[0.0001, 1, 0])
rabi.plot(analysis)
print(f"g_pi = {analysis.metrics['g_pi']:.6f}")
```

- `analyze()` processes raw data → fits → populates `AnalysisResult.metrics`.
- `analyze()` is **idempotent** — calling it twice yields the same result.
- `analyze()` **never** contacts hardware.
- If `update_calibration=True`, uses `guarded_calibration_commit()`:
  - Phase A: always saves an artifact (candidate).
  - Phase B: applies update only if all validation gates pass.
- The user inspects the plot and metrics.
- Manual calibration approval: explicit `CalibrationPatch` → state machine →
  `CalibrationStore.save()`.

**More analysis examples:**

```python
# T1 with custom initial guess and unit conversion
analysis = t1.analyze(
    result,
    update_calibration=True,
    p0=[0, 10, 0],
    p0_time_unit="us",
    derive_qb_therm_clks=True,
    clock_period_ns=4.0,
)
print(f"T1 = {analysis.metrics['T1_us']:.2f} us")

# T2 Ramsey with frequency correction
analysis = t2r.analyze(
    result,
    update_calibration=True,
    p0=[0, 20, 1.0, 0.2, 0.0, 0],
    p0_time_unit="us",
    p0_freq_unit="MHz",
    apply_frequency_correction=True,
    freq_correction_sign=-1.0,
)
print(f"T2* = {analysis.metrics['T2_star_us']:.2f} us")

# Resonator spectroscopy with fit
analysis = spec.analyze(result, update_calibration=True)
spec.plot(analysis)
print(f"f0 = {analysis.metrics['f0_MHz']:.4f} MHz")
print(f"kappa = {analysis.metrics['kappa'] / 1e3:.1f} kHz")

# RB analysis
analysis = rb.analyze(result, p0=[0.99, 0.5, 0.5])
rb.plot(analysis)
print(f"Avg gate fidelity = {analysis.metrics['avg_gate_fidelity']}")
```

### Step 7 — Orchestrator-Driven Calibration Lifecycle

For production calibration workflows, use the `CalibrationOrchestrator` to
manage the full artifact → patch → commit lifecycle with dry-run preview:

```python
from qubox_v2.calibration import CalibrationOrchestrator

orch = CalibrationOrchestrator(session)

# Full cycle: run → analyze → build patch → preview → (optional apply)
rabi_cycle = orch.run_analysis_patch_cycle(
    rabi,
    run_kwargs={"max_gain": 1.2, "dg": 0.04, "op": "ref_r180", "n_avg": 5000},
    analyze_kwargs={"update_calibration": True, "p0": [0.0001, 1, 0]},
    apply=False,              # dry-run: don't commit yet
    persist_artifact=True,    # save raw data
)

# Inspect the patch before committing
print(f"g_pi = {rabi_cycle['calibration_result'].params['g_pi']:.6f}")
for item in rabi_cycle["dry_run"]["preview"]:
    print(f"  {item}")

# Commit only after review
orch.apply_patch(rabi_cycle["patch"], dry_run=False)
```

---

## 3. Core Object Model

### 3.1 `SessionManager`

**Module**: `qubox_v2.experiments.session`  
**Purpose**: Central service container; wires together all infrastructure.
Replaces the legacy monolithic `cQED_Experiment`.

```python
class SessionManager:
    def __init__(
        self,
        experiment_path: str | Path,
        *,
        qop_ip: str | None = None,
        cluster_name: str | None = None,
        load_devices: bool | list[str] = True,
        oct_cal_path: str | Path | None = None,
        auto_save_calibration: bool = False,
        **kwargs: Any,
    ) -> None
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `experiment_path` | `str \| Path` | Root directory for the experiment (contains `config/`) |
| `qop_ip` | `str \| None` | OPX+ IP/hostname; resolved from `hardware.json` if `None` |
| `cluster_name` | `str \| None` | QM cluster identifier |
| `load_devices` | `bool \| list[str]` | Which external instruments to initialize on startup |
| `oct_cal_path` | `str \| Path \| None` | Octave calibration DB path |
| `auto_save_calibration` | `bool` | Auto-save calibration on every mutation (default `False`) |

**Owned components** (set during `__init__` / `open()`):

| Attribute | Type | Description |
|-----------|------|-------------|
| `config_engine` | `ConfigEngine` | QM config compilation |
| `hardware` | `HardwareController` | Live OPX+/Octave control |
| `runner` | `ProgramRunner` | QUA program execution |
| `queue` | `QueueManager` | Job queue |
| `pulse_mgr` | `PulseOperationManager` | Dual-store pulse management |
| `pulses` | `PulseRegistry` | Simplified pulse registration API |
| `calibration` | `CalibrationStore` | Typed calibration persistence |
| `devices` | `DeviceManager` | External instrument fleet |
| `attributes` | `cQED_attributes` | Physics parameters |

**New in v2.0.0** — Binding-related members:

| Attribute / Property | Type | Description |
|----------------------|------|-------------|
| `bindings` | `ExperimentBindings` | Lazily computed binding bundle (qubit, readout, storage) from `hardware.json` + `cqed_params.json`.  Cached; call `invalidate_bindings()` to recompute. |
| `invalidate_bindings()` | method | Clears the cached `ExperimentBindings` so the next access re-derives them. |
| `from_sample(cls, ...)` | classmethod | Convenience constructor for context-mode with bindings. |

**Public Methods:**

| Method | Signature | Return | Side Effects |
|--------|-----------|--------|--------------|
| `open` | `() -> SessionManager` | `SessionManager` | Opens QM connection, inits elements, validates config, creates directories |
| `close` | `() -> None` | `None` | Releases hardware/device connections, persists state |
| `burn_pulses` | `(include_volatile: bool = True) -> None` | `None` | Pushes POM state into live QM config |
| `save_attributes` | `() -> None` | `None` | Writes `cqed_params.json` |
| `save_pulses` | `(path: str \| Path \| None = None) -> Path` | `Path` | Writes `pulses.json` |
| `save_output` | `(output: Output \| dict, tag: str = "") -> Path` | `Path` | Writes `.npz` + `.meta.json` |
| `save_runtime_settings` | `() -> Path` | `Path` | Writes `session_runtime.json` |
| `get_runtime_setting` | `(key: str, default: Any = None) -> Any` | `Any` | Pure read |
| `set_runtime_setting` | `(key: str, value: Any, *, persist: bool = True) -> None` | `None` | Writes JSON if `persist=True` |
| `get_therm_clks` | `(channel: str, default: int \| None = None) -> int \| None` | `int \| None` | Pure read |
| `get_displacement_reference` | `() -> dict[str, Any]` | `dict` | Pure read |
| `validate_runtime_elements` | `(*, auto_map: bool = True, verbose: bool = True) -> dict[str, Any]` | `dict` | May auto-map missing elements |
| `override_readout_operation` | `(*, element, operation, weights, drive_frequency, demod, threshold, weight_len, apply_to_runtime_context, persist_measure_config) -> dict[str, Any]` | `dict` | Modifies live readout op, optionally persists |

**Context Manager:**

```python
with SessionManager("seq_1_device/") as session:
    # session.open() called automatically
    ...
# session.close() called automatically
```

**Legacy aliases:** `hw` → `hardware`, `pulseOpMngr` → `pulse_mgr`,
`quaProgMngr` → `hardware`, `device_manager` → `devices`.

---

### 3.2 `SessionState`

**Module**: `qubox_v2.core.session_state`  
**Purpose**: Frozen, hashable runtime snapshot for reproducibility tracking.

```python
@dataclass(frozen=True)
class SessionState:
    hardware: dict = field(default_factory=dict)
    pulse_specs: dict = field(default_factory=dict)
    calibration: dict = field(default_factory=dict)
    cqed_params: dict = field(default_factory=dict)
    schemas: tuple[SchemaInfo, ...] = ()
    build_hash: str = ""
    build_timestamp: str = ""
    git_commit: str | None = None
```

| Class Method | Signature | Return | Side Effects |
|--------------|-----------|--------|--------------|
| `from_config_dir` | `(cls, config_dir: str \| Path) -> SessionState` | `SessionState` | Reads all config files; computes SHA-256 hash. Raises `FileNotFoundError` if required files missing. |

| Instance Method | Signature | Return |
|-----------------|-----------|--------|
| `summary` | `() -> str` | Human-readable summary |
| `to_dict` | `() -> dict[str, Any]` | JSON-serializable dict |

**Invariant**: `build_hash` changes if and only if any source-of-truth file
changes.

---

### 3.3 `CalibrationStore`

**Module**: `qubox_v2.calibration.store`  
**Purpose**: Typed, versioned calibration data store with JSON persistence,
auto-save capability, and snapshot history.

```python
class CalibrationStore:
    def __init__(
        self,
        path: str | Path,
        *,
        auto_save: bool = False,
    ) -> None
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `path` | `str \| Path` | Path to `calibration.json` |
| `auto_save` | `bool` | If `True`, every `set_*` call triggers atomic save |

**Typed accessors** (get returns model or `None`; set merges or replaces):

| Get Method | Set Method | Model Type |
|------------|------------|------------|
| `get_discrimination(element)` | `set_discrimination(element, params?, **kw)` | `DiscriminationParams` |
| `get_readout_quality(element)` | `set_readout_quality(element, params?, **kw)` | `ReadoutQuality` |
| `get_frequencies(element)` | `set_frequencies(element, freqs?, **kw)` | `ElementFrequencies` |
| `get_coherence(element)` | `set_coherence(element, params?, **kw)` | `CoherenceParams` |
| `get_pulse_calibration(name)` | `set_pulse_calibration(name, cal?, **kw)` | `PulseCalibration` |
| `get_pulse_train_result(element)` | `set_pulse_train_result(element, result)` | `PulseTrainResult` |
| `get_fock_sqr_calibrations(element)` | `set_fock_sqr_calibrations(element, cals)` | `list[FockSQRCalibration]` |
| `get_multi_state_calibration(element)` | `set_multi_state_calibration(element, cal)` | `MultiStateCalibration` |

**Fit history:**

| Method | Signature | Return |
|--------|-----------|--------|
| `store_fit` | `(record: FitRecord) -> None` | `None` |
| `get_latest_fit` | `(experiment: str) -> FitRecord \| None` | `FitRecord \| None` |
| `get_fit_history` | `(experiment: str) -> list[FitRecord]` | `list[FitRecord]` |
| `store_weight_snapshot` | `(element: str, weight_info: dict) -> None` | `None` |

**Persistence:**

| Method | Signature | Return | Side Effects |
|--------|-----------|--------|--------------|
| `save` | `() -> None` | `None` | Atomic write (temp file + `os.replace`) |
| `snapshot` | `(tag: str = "") -> Path` | `Path` | Creates timestamped backup copy |
| `reload` | `() -> None` | `None` | Discards in-memory state; re-reads disk |

| Property | Return | Description |
|----------|--------|-------------|
| `data` | `CalibrationData` | Direct underlying Pydantic model |

**Side effects**: All `set_*` methods call `_touch()`, which auto-saves if
`auto_save=True`.

**New in v2.0.0** — Alias index and dual-lookup:

| Method | Signature | Return | Description |
|--------|-----------|--------|-------------|
| `register_alias` | `(alias: str, physical_id: str) -> None` | `None` | Add an entry to `alias_index` mapping an element name to a physical channel ID |
| `_resolve_key` | `(key: str) -> str` | `str` | Internal: resolve a key via alias_index if not found directly |
| `_dual_lookup` | `(section: str, key: str) -> Any` | `Any` | Internal: look up in a calibration section by direct key first, then alias fallback |

The alias index is persisted inside `calibration.json` under the `alias_index`
field (schema v5.0.0).  Auto-migration from v4.0.0 adds an empty `alias_index`.
`SessionManager.bindings` automatically calls `register_alias()` on first access.

---

### 3.4 `PulseOperationManager`

**Module**: `qubox_v2.pulses.manager`  
**Purpose**: Full-featured pulse, waveform, integration weight, and
element-op mapping management with a **dual-store** architecture
(permanent + volatile).

```python
class PulseOperationManager:
    def __init__(self, elements: list[str] | None = None) -> None
```

**Constants:**

| Name | Value | Description |
|------|-------|-------------|
| `READOUT_PULSE_NAME` | `"readout_pulse"` | Reserved readout pulse name |
| `MAX_AMPLITUDE` | `0.45` | Maximum analog amplitude |
| `BASE_AMPLITUDE` | `0.24` | Default base amplitude |

**Core pulse methods:**

| Method | Signature | Return | Side Effects |
|--------|-----------|--------|--------------|
| `create_control_pulse` | `(element, op, *, length, pulse_name, I_wf_name, Q_wf_name, I_samples, Q_samples, digital_marker, persist, override) -> PulseOp` | `PulseOp` | Registers waveforms + pulse + op mapping |
| `create_measurement_pulse` | `(element, op, *, length, pulse_name, ..., persist, override) -> PulseOp` | `PulseOp` | Registers measurement pulse with weight mapping |
| `add_waveform` | `(name, kind, sample, *, persist=True) -> None` | `None` | Stores waveform samples |
| `add_pulse` | `(name, op_type, length, I_wf_name, Q_wf_name, *, ...) -> None` | `None` | Stores pulse definition |
| `add_operation` | `(op_id, pulse_name) -> None` | `None` | Maps op → pulse |
| `register_pulse_op` | `(p: PulseOp, *, override, persist, warning_flag) -> None` | `None` | Full PulseOp registration |
| `remove_pulse` | `(pulse_name, *, persist) -> None` | `None` | Removes pulse and mappings |
| `modify_pulse` | `(pulse_name, *, new_length, ...) -> PulseOp` | `PulseOp` | Modifies existing pulse |
| `modify_waveform` | `(name, new_samples, *, persist, allow_type_change) -> None` | `None` | Replaces waveform data |

**Integration weight methods:**

| Method | Signature | Return |
|--------|-----------|--------|
| `add_int_weight` | `(name, cos_w, sin_w, length, *, persist) -> None` | `None` |
| `add_int_weight_segments` | `(name, cosine_segments, sine_segments, *, persist) -> None` | `None` |
| `get_integration_weights` | `(name, *, include_volatile, strict) -> tuple` | `(cosine_segs, sine_segs)` |
| `update_integration_weight` | `(name, *, cos_w, sin_w, length, ...) -> None` | `None` |
| `modify_integration_weights` | `(pulse_name, new_mapping, ...) -> dict` | Updated mapping |

**Query methods:**

| Method | Signature | Return |
|--------|-----------|--------|
| `get_pulseOp_by_element_op` | `(element, op, *, include_volatile, strict) -> PulseOp \| None` | `PulseOp \| None` |
| `get_pulse_waveforms` | `(pulse_name, *, include_volatile) -> tuple` | `(I_samples, Q_samples)` |
| `get_pulse_definitions` | `() -> dict[str, dict]` | All high-level definitions |

**Config integration:**

| Method | Signature | Return | Side Effects |
|--------|-----------|--------|--------------|
| `burn_to_config` | `(cfg: dict, *, include_volatile) -> dict` | `dict` | Merges both stores into QM config |
| `save_json` | `(path: str) -> None` | `None` | Persists permanent store to disk |
| `from_json` | `(cls, path: str) -> PulseOperationManager` | `PulseOperationManager` | Classmethod; loads from JSON |
| `clear_temporary` | `() -> None` | `None` | Clears volatile store |

**Visualization:**

| Method | Signature | Return |
|--------|-----------|--------|
| `display_op` | `(target, op, domain, ...) -> np.ndarray` | Waveform array (also plots) |
| `display_pulse` | `(pulse, domain, ...) -> np.ndarray` | Waveform array |

**Design**: Reserved readout pulse/waveform/weight names are protected from
accidental creation or deletion.  The volatile store is for
session-transient pulses that should not survive a `save_json()`.

---

### 3.5 `ProgramRunner`

**Module**: `qubox_v2.hardware.program_runner`  
**Purpose**: Execute and simulate QUA programs.  Thread-safe (`RLock`).

```python
class ProgramRunner:
    def __init__(
        self,
        qmm: QuantumMachinesManager,
        controller: HardwareController,
        config_engine: ConfigEngine,
    ) -> None
```

**Enums:**

```python
class ExecMode(str, Enum):
    HARDWARE = "hardware"
    SIMULATE = "simulate"
```

**Return type:**

```python
@dataclass
class RunResult:
    mode: ExecMode
    output: Any
    sim_samples: Any | None = None
    metadata: dict | None = None
```

**Public methods:**

| Method | Signature | Return | Side Effects |
|--------|-----------|--------|--------------|
| `run_program` | `(qua_prog, n_total, print_report, show_progress, processors, progress_handle, auto_job_halt, process_in_sim, *, use_queue, queue_to_start, queue_only, **kwargs) -> RunResult` | `RunResult` | Submits to QM; manages SPA pump; halts job in `finally` |
| `simulate` | `(program, *, duration, plot, plot_params, controllers, t_begin, t_end, compiler_options) -> SimulatorSamples` | `SimulatorSamples` | Pure simulation, plots waveforms |
| `set_exec_mode` | `(mode: ExecMode \| str) -> None` | `None` | Switches hardware/simulate mode |
| `get_exec_mode` | `() -> ExecMode` | `ExecMode` | Pure read |
| `halt_job` | `() -> None` | `None` | Halts currently running job |
| `serialize_program` | `(qua_prog, path, filename, *, use_last_snapshot) -> str` | `str` | Writes QUA program to `.py` file |
| `run_continuous_wave` | `(elements, el_freqs, pulses, gain) -> None` | `None` | CW output for debug |
| `register_processor` | `(processor: Callable) -> None` | `None` | Adds post-processor |

**Failure modes:**

- `ConnectionError` if QM not reachable.
- `JobError` if execution fails or times out.
- `RuntimeError` if called before `SessionManager.open()`.

---

### 3.6 `ExperimentBase`

**Module**: `qubox_v2.experiments.experiment_base`  
**Purpose**: Abstract base class for all modular experiment types.  Provides
unified context accessors working with both legacy `cQED_Experiment` and
new `SessionManager`.

```python
class ExperimentBase:
    def __init__(self, ctx: Any) -> None
```

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `name` | `str` | Class name |
| `attr` | `cQED_attributes` | Physics parameters |
| `pulse_mgr` | `PulseOperationManager` | Pulse manager |
| `hw` | `HardwareController` | Hardware controller |
| `device_manager` | `DeviceManager \| None` | Device manager |
| `measure_macro` | `measureMacro` | Readout macro singleton |
| `calibration_store` | `CalibrationStore \| None` | Calibration store |
| `bindings` | `ExperimentBindings` | Binding bundle derived from session (v2.0.0) |

**Abstract methods** (must be overridden by subclasses):

| Method | Signature | Return | Contract |
|--------|-----------|--------|----------|
| `build_program` | `(**params) -> Any` | QUA program | Build QUA program from parameters |
| `run` | `(**params) -> RunResult` | `RunResult` | Execute experiment; no calibration writes |
| `analyze` | `(result, *, update_calibration=False, **params) -> AnalysisResult` | `AnalysisResult` | Post-process; idempotent; no hardware ops |
| `plot` | `(analysis, *, ax=None, **kwargs) -> Figure \| None` | `Figure \| None` | Visualization; create own figure if `ax=None` |

**Concrete helper methods:**

| Method | Signature | Return | Description |
|--------|-----------|--------|-------------|
| `set_standard_frequencies` | `(*, qb_fq: float \| None = None) -> None` | `None` | Set IFs to calibrated values |
| `get_readout_lo` | `() -> float` | `float` | Readout LO frequency |
| `get_qubit_lo` | `() -> float` | `float` | Qubit LO frequency |
| `burn_pulses` | `(include_volatile: bool = True) -> None` | `None` | Push pulses to QM config |
| `get_therm_clks` | `(channel, *, fallback) -> int \| None` | `int \| None` | Thermalization clocks |
| `get_displacement_reference` | `() -> dict[str, Any]` | `dict` | Displacement reference params |
| `run_program` | `(prog, *, n_total, processors, process_in_sim, **kw) -> RunResult` | `RunResult` | Delegates to ProgramRunner |
| `save_output` | `(output, tag="") -> None` | `None` | Persist via session |
| `guarded_calibration_commit` | `(*, analysis, run_result, calibration_tag, apply_update, require_fit, min_r2, required_metrics, extra_metadata) -> bool` | `bool` | Two-phase validated calibration persistence |

**`guarded_calibration_commit` protocol:**

- **Phase A** (always): save candidate artifact with metrics + metadata.
- **Phase B** (conditional): apply update only if *all* validation gates
  pass (`require_fit`, `min_r2`, `required_metrics` checks).
- Returns `True` if update was applied.

---

### 3.7 `AnalysisResult`

**Module**: `qubox_v2.experiments.result`  
**Purpose**: Container for post-processed experiment results.

```python
@dataclass
class AnalysisResult:
    data: dict[str, Any]
    fit: FitResult | None = None
    fits: dict[str, FitResult] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    source: RunResult | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

| Class Method | Signature | Return |
|--------------|-----------|--------|
| `from_run` | `(cls, run_result, *, fit, fits, metrics, metadata) -> AnalysisResult` | `AnalysisResult` |

| Instance Method | Signature | Return |
|-----------------|-----------|--------|
| `get` | `(key, default=None) -> Any` | Value from `data` dict |
| `__getitem__` | `(key) -> Any` | `data[key]` |
| `__contains__` | `(key) -> bool` | `key in data` |

**Companion type:**

```python
@dataclass
class FitResult:
    model_name: str
    params: dict[str, float]
    uncertainties: dict[str, float] = field(default_factory=dict)
    r_squared: float | None = None
    residuals: np.ndarray | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

---

### 3.8 `ArtifactManager`

**Module**: `qubox_v2.core.artifact_manager`  
**Purpose**: Build-hash-keyed artifact storage under
`<experiment_path>/artifacts/<build_hash>/`.

```python
class ArtifactManager:
    def __init__(
        self,
        experiment_path: str | Path,
        build_hash: str,
    ) -> None
```

| Method | Signature | Return | Description |
|--------|-----------|--------|-------------|
| `save_session_state` | `(state_dict: dict) -> Path` | `Path` | Save `SessionState` snapshot |
| `save_generated_config` | `(config: dict) -> Path` | `Path` | Save compiled QM config |
| `save_report` | `(name, content, *, ext=".md") -> Path` | `Path` | Save text report |
| `save_artifact` | `(name, data: dict) -> Path` | `Path` | Save arbitrary JSON |
| `list_artifacts` | `() -> list[Path]` | `list[Path]` | List all artifacts |

| Function | Signature | Return | Description |
|----------|-----------|--------|-------------|
| `cleanup_artifacts` | `(experiment_path, *, keep_latest=10, current_hash=None) -> list[Path]` | `list[Path]` | Prune old build-hash dirs |

---

### 3.9 `DeviceManager`

**Module**: `qubox_v2.devices.device_manager`  
**Purpose**: Manage a fleet of external instruments declared in
`devices.json`.  Thread-safe.

```python
class DeviceManager:
    def __init__(self, config_path: str | Path) -> None
```

| Method | Signature | Return | Side Effects |
|--------|-----------|--------|--------------|
| `load` | `() -> None` | `None` | Reads specs from JSON |
| `save` | `() -> None` | `None` | Writes specs to JSON |
| `instantiate` | `(*names) -> None` | `None` | Connects specific devices |
| `instantiate_all` | `() -> None` | `None` | Connects all declared devices |
| `add_or_update` | `(name, **spec_fields) -> Any \| None` | instance | Add/update spec and connect |
| `get` | `(name, connect=True) -> Any \| None` | instance | Get device instance |
| `exists` | `(name: str) -> bool` | `bool` | Check spec existence |
| `apply` | `(name, persist=True, **settings) -> None` | `None` | Apply settings to device |
| `remove` | `(name, disconnect=True) -> None` | `None` | Remove device |
| `reload` | `() -> None` | `None` | Reload from disk, reconnect changed |
| `snapshot` | `() -> dict` | `dict` | Full fleet snapshot |
| `ramp` | `(name, param, to, step, delay_s=0.1) -> None` | `None` | Gradually ramp parameter |

**Device specification:**

```python
@dataclass
class DeviceSpec:
    name: str
    driver: str          # "module:Class" format
    backend: str = "qcodes"
    connect: dict = field(default_factory=dict)
    settings: dict = field(default_factory=dict)
    enabled: bool = True
```

---

## 4. Calibration Architecture

### 4.1 Philosophy

**Calibration parameters must NEVER auto-update.**  Every change follows:

```
Acquire  →  Analyze  →  Plot  →  User Confirm  →  Commit
```

### 4.2 CalibrationOrchestrator

**Module**: `qubox_v2.calibration.orchestrator`

The `CalibrationOrchestrator` owns the full calibration lifecycle:

```
run_experiment -> Artifact
persist_artifact
analyze -> CalibrationResult
build_patch -> Patch
apply_patch (dry_run=True for preview, False to commit)
```

```python
class CalibrationOrchestrator:
    def __init__(self, session, *, patch_rules=None) -> None
    def run_experiment(self, exp, **run_kwargs) -> Artifact
    def analyze(self, exp, artifact, **analyze_kwargs) -> CalibrationResult
    def build_patch(self, result: CalibrationResult) -> Patch
    def apply_patch(self, patch: Patch, dry_run: bool = False) -> dict
    def run_analysis_patch_cycle(self, exp, *, run_kwargs=None,
        analyze_kwargs=None, persist_artifact=True, apply=False) -> dict
    def persist_artifact(self, artifact: Artifact) -> Path
    def list_applied_patches(self) -> list[str]
```

Convenience method `run_analysis_patch_cycle()` runs the full flow in one
call and returns a dict with `artifact`, `calibration_result`, `patch`,
`dry_run` preview, and optional `apply_result`.

### 4.3 Calibration Contracts

**Module**: `qubox_v2.calibration.contracts`

| Dataclass | Purpose | Key Fields |
|-----------|---------|------------|
| `Artifact` | Raw experiment output snapshot | `name`, `data`, `raw`, `meta`, `artifact_id` |
| `CalibrationResult` | Typed analysis result for patch rules | `kind`, `params`, `uncertainties`, `quality`, `evidence` |
| `Patch` | Ordered list of calibration updates | `reason`, `updates: list[UpdateOp]`, `provenance` |
| `UpdateOp` | Single calibration mutation | `op` (str), `payload` (dict) |

Supported `UpdateOp.op` values:
- `SetCalibration` — write to calibration store via dotted path
- `SetPulseParam` — update a pulse parameter
- `SetMeasureWeights` — update integration weights
- `SetMeasureDiscrimination` — update discrimination params
- `SetMeasureQuality` — update readout quality params
- `PersistMeasureConfig` — write measureConfig.json
- `TriggerPulseRecompile` — rebuild pulse waveforms

### 4.4 Calibration Data Models

**Module**: `qubox_v2.calibration.models`
All models are Pydantic v2 `BaseModel` subclasses.

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `DiscriminationParams` | Single-shot readout discrimination | `threshold`, `angle`, `mu_g`, `mu_e`, `sigma_g`, `sigma_e`, `fidelity?`, `confusion_matrix?`, `n_shots?`, `integration_time_ns?`, `demod_weights?`, `state_prep_ops?` |
| `ReadoutQuality` | Butterfly measurement metrics | `F?`, `Q?`, `V?`, `t01?`, `t10?`, `confusion_matrix?`, `n_shots?`, `integration_time_ns?`, `demod_weights?`, `state_prep_ops?` |
| `ElementFrequencies` | Calibrated frequencies (Hz) | `lo_freq?`, `if_freq?`, `rf_freq?`, `qubit_freq?`, `anharmonicity?`, `fock_freqs?`, `chi?`, `kappa?`, `kerr?` |
| `CoherenceParams` | Coherence times | `T1?`, `T2_ramsey?`, `T2_echo?` |
| `PulseCalibration` | Calibrated pulse params | `pulse_name`, `element?`, `amplitude?`, `length?`, `sigma?`, `drag_coeff?` |
| `FitRecord` | Generic fit result | `experiment`, `model_name`, `params`, `uncertainties?`, `reduced_chi2?` |
| `PulseTrainResult` | Pulse-train tomography | `amp_err`, `phase_err`, `delta`, `zeta` |
| `FockSQRCalibration` | Per-Fock SQR gate | `fock_number`, `model_type`, `params`, `fidelity?` |
| `MultiStateCalibration` | Multi-alpha affine calibration | `alpha_values`, `affine_matrix`, `offset_vector` |
| `CalibrationData` | **Root container** (schema v5.0.0) | All of the above, plus `version`, `context?`, `alias_index?`, `created`, `last_modified` |

**Null-handling policy:**

- Unset optional fields default to `None` in the Pydantic model.
- The `CalibrationStore` serializes with `exclude_none=True` — fields that are
  `None` are **omitted entirely** from the persisted JSON.
- This ensures calibration records reflect actual pipeline outputs only.
- When loading, Pydantic fills absent optional fields with `None` automatically.
- Placeholder values like `0.0` or `""` must **never** be used as stand-ins
  for unset data.  Use `None` (which is omitted on write).

**Frequency convention:**

- `ElementFrequencies` supports two frequency representations:
  1. **LO + IF pair**: `rf_freq = lo_freq + if_freq`.
     Standard for OPX elements driven through an Octave up-converter.
     `if_freq` may be negative (lower sideband convention).
  2. **Explicit rf\_freq**: absolute RF frequency in Hz.
- Both may coexist; when all three are present, `rf_freq == lo_freq + if_freq` must hold.
- `qubit_freq` stores the calibrated qubit transition frequency (independent of the hardware mixing chain).
- Elements that do not use LO+IF mixing (e.g. direct RF drive) should omit `lo_freq`/`if_freq`.

**Pulse calibration storage policy:**

- Only **true calibration primitives** (`ref_r180`, `sel_ref_r180`) are stored
  in `pulse_calibrations`.
- **Derived pulses** (`x180`, `y180`, `x90`, `xn90`, `y90`, `yn90`) are
  generated programmatically from the reference pulse via `PulseFactory`
  `rotation_derived` and must **not** appear in `calibration.json`.

### 4.5 Calibration Flow Examples

**Direct `run → analyze` pattern (simple experiments):**

```python
# Power Rabi → stores g_pi amplitude
rabi = PowerRabi(session)
result = rabi.run(max_gain=1.2, dg=0.04, op="ref_r180", n_avg=5000)
analysis = rabi.analyze(result, update_calibration=True, p0=[0.0001, 1, 0])
rabi.plot(analysis)
# → updates PulseCalibration("ref_r180").amplitude

# DRAG → stores optimal alpha
drag = DRAGCalibration(session)
result = drag.run(amps=np.linspace(-0.5, 0.5, 20), n_avg=5000, base_alpha=1.0)
analysis = drag.analyze(result, update_calibration=True)
drag.plot(analysis)
# → updates PulseCalibration("ref_r180").drag_coeff; derived pulses inherit via PulseFactory

# GE Discrimination → stores threshold, angle, fidelity, rotated weights
ge = ReadoutGEDiscrimination(session)
result = ge.run("readout", attr.ro_fq, r180="x180", n_samples=50000,
                update_measure_macro=True, apply_rotated_weights=True, persist=True)
analysis = ge.analyze(result, update_calibration=True)
ge.plot(analysis, show_rotated=True)
# → updates DiscriminationParams.{threshold, angle, fidelity}
```

**Orchestrator pattern (production calibration with dry-run preview):**

```python
orch = CalibrationOrchestrator(session)

# T1 with full lifecycle
t1_cycle = orch.run_analysis_patch_cycle(
    T1Relaxation(session),
    run_kwargs={"delay_end": 50 * u.us, "dt": 500, "n_avg": 2000},
    analyze_kwargs={
        "update_calibration": True,
        "p0": [0, 10, 0],
        "p0_time_unit": "us",
        "derive_qb_therm_clks": True,
    },
    apply=False, persist_artifact=True,
)
print(f"T1 = {t1_cycle['calibration_result'].params['T1_us']:.2f} us")

# Preview patch before committing
for item in t1_cycle["dry_run"]["preview"]:
    print(f"  {item}")

# Commit after review
# orch.apply_patch(t1_cycle["patch"], dry_run=False)
```

**Full readout calibration pipeline (explicit patch model):**

```python
from qubox_v2.experiments.calibration.readout import CalibrateReadoutFull, ReadoutConfig

readoutConfig = ReadoutConfig(
    measure_op="readout",
    drive_frequency=attr.ro_fq,
    ro_el=attr.ro_el,
    r180="x180",
    n_avg_weights=200_000,
    n_samples=50_000,
    n_shots_butterfly=50_000,
    skip_weights_optimization=False,
    persist_weights=True,
    rotation_method="optimal",
    threshold_extraction="legacy_discriminator",
)

# Step 1: Run pipeline — acquire data
cal = CalibrationReadoutFull(session)
result = cal.run(readoutConfig=readoutConfig)

# Step 2: Analyze — compute metrics (NO inline calibration mutation)
analysis = cal.analyze(result, update_calibration=False)

# Step 3: Explicit patch — apply calibration after review
ge_metrics = analysis.metadata["ge_analysis"].metrics
bfly_metrics = analysis.metadata["bfly_analysis"].metrics

session.calibration.set_discrimination(attr.ro_el,
    threshold=ge_metrics["threshold"],
    angle=ge_metrics["angle"],
    fidelity=ge_metrics["fidelity"],
    n_shots=readoutConfig.n_samples,
    state_prep_ops=["identity", readoutConfig.r180],
)
session.calibration.set_readout_quality(attr.ro_el,
    F=bfly_metrics["F"],
    Q=bfly_metrics["Q"],
    V=bfly_metrics["V"],
    n_shots=readoutConfig.n_shots_butterfly,
)
session.calibration.save()
```

### 4.6 When `calibration.json` is Written

1. Via `CalibrationOrchestrator.apply_patch(patch, dry_run=False)` — the recommended path.
2. **Or** via `CalibrationStore.save()` / auto-save after `set_*()`.
3. **Never** during `__init__()` or `analyze()` without validation gates.

### 4.7 Validation Gates

Standard gates: `min_r2`, `bounds_check`, `monotonic_check`,
`relative_residual`, `stale_check`, `type_check`.

Override path: `patch.override_validation(gate_name, reason, user)`.

---

## 5. Declarative Pulse System

### 5.1 Design Principle

> **Experiments never generate waveforms.  They consume declared
> operations.**

Persistent state stores *recipes* (`pulse_specs.json`), never raw waveform
arrays.  Waveform arrays are compiled at runtime and exist only in memory.

### 5.2 Pulse Definition vs Pulse Instance

| Concept | Storage | Content | Lifetime |
|---------|---------|---------|----------|
| **Pulse spec** | `pulse_specs.json` | Shape name + parameters + constraints | Persistent across sessions |
| **Pulse instance** | POM (permanent store) | Waveform samples + element-op binding | Session (written to `pulses.json` for compat) |
| **Volatile pulse** | POM (volatile store) | Same as instance | Single session; cleared by `clear_temporary()` |

### 5.3 `PulseFactory`

**Module**: `qubox_v2.pulses.factory`  
**Purpose**: Compiles declarative pulse specs into concrete I/Q waveform
arrays.

```python
class PulseFactory:
    def __init__(self, specs_data: dict[str, Any]) -> None
```

| Method | Signature | Return | Description |
|--------|-----------|--------|-------------|
| `spec_names` | `-> list[str]` (property) | `list[str]` | All spec names |
| `compile_one` | `(spec_name: str) -> tuple[list[float], list[float], dict]` | `(I, Q, meta)` | Compile single spec |
| `compile_all` | `() -> dict[str, tuple]` | `dict` | Compile all specs |
| `register_all` | `(pom, *, persist=True, override=True) -> int` | `int` | Register compiled specs in POM |

**Built-in shapes** (12):

`constant`, `zero`, `drag_gaussian`, `drag_cosine`, `kaiser`, `slepian`,
`flattop_gaussian`, `flattop_cosine`, `flattop_tanh`, `flattop_blackman`,
`clear`, `arbitrary_blob`

Plus the meta-shape `rotation_derived` which derives a pulse from an
existing spec by applying `(theta, phi)` rotation.

**Determinism guarantee**: identical specs → bit-identical waveforms.

### 5.4 `PulseRegistry`

**Module**: `qubox_v2.pulses.pulse_registry`  
**Purpose**: Simplified pulse registration API wrapping the dual
permanent/volatile `ResourceStore`.

```python
class PulseRegistry:
    def __init__(
        self,
        elements: list[str] | None = None,
        readout_length: int = 1000,
    ) -> None
```

| Method | Signature | Return |
|--------|-----------|--------|
| `add_control_pulse` | `(element, op, *, I_wf, Q_wf=0.0, length, ...) -> str` | pulse name |
| `add_measurement_pulse` | `(element, op, *, I_wf, Q_wf=0.0, length, ...) -> str` | pulse name |
| `modify_pulse` | `(pulse_name, *, I_wf, Q_wf, length, ...) -> None` | `None` |
| `remove_pulse` | `(pulse_name, *, persist) -> None` | `None` |
| `get_pulse` | `(name) -> dict` | pulse dict |
| `list_pulses` | `(*, element=None) -> list[str]` | names |
| `get_element_ops` | `(element) -> dict[str, str]` | op → pulse mapping |
| `burn_to_config` | `(cfg, *, include_volatile=True) -> dict` | merged config |

### 5.5 Op Binding Rules

- Every element must have at minimum: `const` and `zero`.
- Qubit elements additionally require: `x180`, `x90`, `y180`, `y90`.
- Operations are bound to pulses via
  `PulseOperationManager.add_operation(op_id, pulse_name)`.
- The same pulse can be bound to multiple ops (aliasing).
- Reserved readout pulse/waveform/weight names are protected.

### 5.6 Pulse Spec Schema (`pulse_specs.json`)

```json
{
  "schema_version": 1,
  "specs": {
    "<name>": {
      "shape": "drag_gaussian",
      "element": "qubit",
      "op": "x180",
      "params": { "amplitude": 0.24, "length": 40, "sigma": 10, ... },
      "constraints": { "max_amplitude": 0.45, "clip": true },
      "metadata": { ... }
    }
  },
  "integration_weights": { ... },
  "element_operations": { ... }
}
```

**Spec model types** (Pydantic v2):

`PulseSpecEntry`, `PulseConstraints`, `ConstantParams`, `ZeroParams`,
`DragGaussianParams`, `DragCosineParams`, `KaiserParams`, `SlepianParams`,
`FlattopParams`, `CLEARParams`, `RotationDerivedParams`,
`ArbitraryBlobParams`, `MeasurementMetadata`.

**Compilation flow:**

```
pulse_specs.json
    → PulseFactory.compile_all()
        → resolve shape handler
        → call waveform generator
        → apply constraints (clip, normalize, pad)
        → return (I_samples, Q_samples, metadata)
    → PulseFactory.register_all(pom)
        → POM.create_control_pulse() / create_measurement_pulse()
```

### 5.7 Invariants

1. No waveform arrays may appear in `pulse_specs.json`.
2. Every shape must map to a registered handler in `PulseFactory`.
3. Every element referenced must exist in `hardware.json`.
4. `rotation_derived` must reference an existing spec.
5. All amplitudes ≤ `MAX_AMPLITUDE` (0.45).
6. Integration weight segment lengths must be divisible by 4.

---

## 6. Hardware Abstraction Layer

### 6.1 `ConfigEngine`

**Module**: `qubox_v2.hardware.config_engine`  
**Purpose**: Layered QM config compilation.

```
hardware_base → hardware_extras → pulse_overlay → element_ops → runtime_overrides
```

```python
class ConfigEngine:
    def __init__(
        self,
        hardware_path: str | Path | None = None,
        *,
        hardware_extras_keys: set[str] | None = None,
        override_octave_json_mode: RFOutputMode | None = None,
    ) -> None
```

| Method | Signature | Return | Description |
|--------|-----------|--------|-------------|
| `load_hardware` | `(path?) -> None` | `None` | Parse `hardware.json` |
| `save_hardware` | `(path?) -> None` | `None` | Write `hardware.json` |
| `build_qm_config` | `() -> dict` | `dict` | Compile full QM config |
| `merge_pulses` | `(pom, *, include_volatile=True) -> None` | `None` | Overlay POM into config |
| `patch_hardware` | `(patch_fn) -> None` | `None` | Apply hardware-level patch |
| `patch_runtime` | `(overrides: dict) -> None` | `None` | Apply runtime overrides |
| `clear_runtime_overrides` | `() -> None` | `None` | Reset runtime layer |

### 6.2 `HardwareController`

**Module**: `qubox_v2.hardware.controller`  
**Purpose**: Owns the QM connection and provides live hardware control.

```python
class HardwareController:
    def __init__(
        self,
        qmm: QuantumMachinesManager,
        config_engine: ConfigEngine,
        *,
        default_output_mode: RFOutputMode | None = RFOutputMode.on,
    ) -> None
```

| Method | Signature | Return | Description |
|--------|-----------|--------|-------------|
| `open_qm` | `(config_dict?, *, close_other_machines=True) -> None` | `None` | Open QM connection |
| `close` | `() -> None` | `None` | Release QM connection |
| `apply_changes` | `(*, save_hardware=False) -> None` | `None` | Apply frequency/gain/LO changes |
| `set_device_manager` | `(dm) -> None` | `None` | Wire device manager |
| `set_spa_pump` | `(spa_pump_sc) -> None` | `None` | Configure SPA pump |

### 6.3 `HardwareConfig`

**Module**: `qubox_v2.core.config`  
**Purpose**: Complete typed representation of `hardware.json` (Pydantic v2).

```python
class HardwareConfig(BaseModel):
    version: int = 1
    controllers: Dict[str, ControllerConfig]
    octaves: Dict[str, OctaveConfig]
    elements: Dict[str, ElementConfig]
    qubox_extras: Optional[QuboxExtras]     # alias: "__qubox"
```

| Method | Signature | Return |
|--------|-----------|--------|
| `from_json` | `(cls, path) -> HardwareConfig` | classmethod |
| `from_dict` | `(cls, d) -> HardwareConfig` | classmethod |
| `save_json` | `(path) -> None` | |
| `to_qm_dict` | `() -> dict` | Strips `__qubox` for QM compatibility |

**Sub-models:** `ControllerConfig`, `AnalogPort`, `OctaveRFOutput`,
`OctaveRFInput`, `OctaveConfig`, `ElementConfig`, `ExternalLOEntry`,
`OctaveLink`, `QuboxExtras`.

### 6.4 Device Integration

External instruments are managed by `DeviceManager` (§3.9).  Drivers use
the `"module:Class"` format, supporting QCoDeS and InstrumentServer backends.

### 6.5 Hardware vs Simulation

| Capability | Hardware Required | Simulation Safe |
|------------|:-----------------:|:---------------:|
| QUA program execution | ✓ | ✓ (`ExecMode.SIMULATE`) |
| Config compilation | — | ✓ |
| Pulse waveform inspection | — | ✓ |
| External device control | ✓ | — |
| Spectrum analyzer calibration | ✓ | — |
| Readout discrimination | ✓ | — |
| Gate unitary computation | — | ✓ |
| Waveform regression tests | — | ✓ |

---

## 7. State & Persistence Model

### 7.1 What Lives Where

| Data | Storage | Mutability |
|------|---------|------------|
| QM config dict | **Memory only** | Rebuilt every `burn_pulses()` / `build_qm_config()` |
| Waveform sample arrays | **Memory only** | Compiled from specs; never persisted as source of truth |
| `hardware.json` | **Disk** (source of truth) | Manual edits only |
| `pulse_specs.json` | **Disk** (source of truth) | Written via `set_pulse_definition()` |
| `calibration.json` | **Disk** (source of truth) | Only via `CalibrationStore`; serialized with `exclude_none=True` |
| `cqed_params.json` | **Disk** (legacy compat) | Legacy fallback only; SessionManager does not mutate it in the v2 path |
| `measureConfig.json` | **Disk** | Written by measureMacro lifecycle |
| `devices.json` | **Disk** | Manual edits; written by `DeviceManager.save()` |
| `pulses.json` | **Disk** (deprecated) | Transitional compatibility; will be removed |
| `calibration_history.jsonl` | **Disk** | Append-only; never truncated |
| Session artifacts | **Disk** (`artifacts/<build_hash>/`) | Immutable after creation |

### 7.2 `calibration.json` Structure

```json
{
  "version": "5.0.0",
  "context": {
    "sample_id": "...",
    "cooldown_id": "...",
    "wiring_rev": "...",
    "schema_version": "5.0.0",
    "config_hash": "...",
    "created": "..."
  },
  "alias_index": {
    "<element_alias>": "<physical_channel_id>"
  },
  "discrimination": {
    "<element>": {
      "threshold": ..., "angle": ..., "mu_g": [...], "mu_e": [...],
      "sigma_g": ..., "sigma_e": ..., "fidelity": ...,
      "confusion_matrix": [[...], [...]],
      "n_shots": ..., "integration_time_ns": ...,
      "demod_weights": ["..."], "state_prep_ops": ["..."]
    }
  },
  "readout_quality": {
    "<element>": {
      "F": ..., "Q": ..., "V": ..., "t01": ..., "t10": ...,
      "confusion_matrix": [[...], [...]],
      "n_shots": ..., "state_prep_ops": ["..."]
    }
  },
  "frequencies": {
    "<resonator_element>": { "lo_freq": ..., "if_freq": ... },
    "<qubit_element>":     { "qubit_freq": ... }
  },
  "coherence": {
    "<element>": { "T1": ..., "T2_ramsey": ..., "T2_echo": ... }
  },
  "pulse_calibrations": {
    "ref_r180":     { "pulse_name": "ref_r180", "element": "qubit", "amplitude": ..., "length": ..., "sigma": ..., "drag_coeff": ... },
    "sel_ref_r180": { "pulse_name": "sel_ref_r180", "element": "qubit", "amplitude": ... }
  },
  "fit_history": { ... },
  "pulse_train_results": { ... },
  "fock_sqr_calibrations": { ... },
  "multi_state_calibration": { ... },
  "created": "...",
  "last_modified": "..."
}
```

**Important conventions:**

- Fields with `None` / unset values are **omitted** from the JSON (not stored as `null`).
- Only calibration primitives (`ref_r180`, `sel_ref_r180`) appear in `pulse_calibrations`.
  Derived pulses (`x180`, `y180`, etc.) are computed by `PulseFactory` at runtime.
- The `context` block is present in v4.0.0+; absent (or `null`) in legacy v3.0.0 files.
- The `alias_index` block (v5.0.0) maps human-friendly element names to physical
  channel IDs (e.g. `"resonator"` → `"oct1:RF_in:1"`).  This enables dual-lookup
  in `CalibrationStore` — keys can be either physical IDs or legacy aliases.
- `discrimination` and `readout_quality` entries should only contain fields that
  were actually produced by the calibration pipeline.  Do not include `confusion_matrix`
  unless one was computed.
- Readout metadata (`n_shots`, `integration_time_ns`, `demod_weights`, `state_prep_ops`)
  ensures reproducibility across cooldowns.
- Frequency blocks store only physically relevant parameters per element:
  a resonator stores `lo_freq`/`if_freq`; a qubit stores `qubit_freq`.

### 7.3 Relationship Between Config Files

```
hardware.json          — Physical topology (controllers, octaves, elements)
    ↓ read by ConfigEngine
pulse_specs.json       — Declarative pulse recipes
    ↓ compiled by PulseFactory
calibration.json       — Calibrated parameters (thresholds, amplitudes, ...)
    ↓ read by experiments + CalibrationStore
cqed_params.json       — Legacy physics params (frequencies, anharmonicity)
    ↓ read-only in v2
```

**Source-of-truth hierarchy** (higher overrides lower):

1. `calibration.json`
2. `cqed_params.json`
3. `hardware.json`

### 7.4 Schema Versioning

**Module**: `qubox_v2.core.schemas`

Every persisted JSON file must include a schema version.  The system refuses
unsupported versions and never silently upgrades.

| File | Version Field | Current Version |
|------|---------------|-----------------|
| `hardware.json` | `version` | 1 |
| `pulse_specs.json` | `schema_version` | 1 |
| `calibration.json` | `version` | `"5.0.0"` |
| `measureConfig.json` | `_version` | 5 |
| `devices.json` | `schema_version` | 1 |
| `pulses.json` (deprecated) | `_schema_version` | 2 |

**Migration machinery:**

```python
# Register a migration step
register_migration("calibration", target_version=4, func=migrate_3_to_4)
register_migration("calibration", target_version=5, func=migrate_4_to_5)

# Apply migration chain
migrate(data, "calibration", from_version=3, to_version=5) -> dict

# Validate any config file
validate_schema(file_path, file_type) -> ValidationResult

# Validate all config files in a directory
validate_config_dir(config_dir) -> list[ValidationResult]
```

### 7.5 What Must Never Auto-Overwrite

1. `calibration.json` — only written via `CalibrationOrchestrator.apply_patch()` or explicit `CalibrationStore.save()`.
2. `hardware.json` — manual edits only.
3. `calibration_history.jsonl` — append-only, never truncated.

---

## 8. Gate System

### 8.1 Architecture

Gates have a clean separation between **pure mathematical models** and
**hardware backends**.

```
Gate  ──┬── GateModel (ABC)     — pure unitary / superoperator math
        └── GateHardware (ABC)  — QUA play / waveform build
```

Both sides have auto-registration via `__init_subclass__`:
`_MODEL_REGISTRY` and `_HARDWARE_REGISTRY`.

### 8.2 `GateModel` (ABC)

**Module**: `qubox_v2.gates.model_base`

| Abstract Method | Signature | Return |
|-----------------|-----------|--------|
| `key` | `() -> GateKey` | Immutable `(gate_type, target, param_hash)` |
| `to_dict` | `() -> dict` | Serialization |
| `from_dict` | `(cls, d) -> GateModel` | Deserialization |
| `duration_s` | `(ctx: ModelContext) -> float` | Gate duration in seconds |
| `unitary` | `(*, n_max, ctx) -> np.ndarray` | Ideal unitary matrix |

| Concrete Method | Signature | Return |
|-----------------|-----------|--------|
| `kraus` | `(*, n_max, ctx, noise, noise_model) -> list[np.ndarray]` | Kraus operators (noisy) |
| `superop` | `(*, n_max, ctx, noise, noise_model) -> np.ndarray` | Liouville superoperator |

### 8.3 Concrete Gate Models

| Class | Gate | Constructor Key Params |
|-------|------|------------------------|
| `DisplacementModel` | $\exp(\alpha a^\dagger - \alpha^* a)$ | `alpha: complex`, `target: str` |
| `QubitRotationModel` | $R(\theta, \phi)$ | `theta: float`, `phi: float` |
| `SNAPModel` | Selective Number-dependent Arbitrary Phase | `angles: np.ndarray` |
| `SQRModel` | Selective Qubit Rotation | `thetas`, `phis`, `d_lambda`, `d_alpha`, `d_omega` |

### 8.4 Contexts

| Context | Purpose | Key Fields |
|---------|---------|------------|
| `ModelContext` | Physics parameters for ideal gate math | `dt_s`, `st_chi`, `st_kerr`, `qubit_dim`, `gate_durations_s` |
| `NoiseConfig` | Noise parameters | `T1`, `T2`, `order` |
| `HardwareContext` | QUA/hardware references (kept separate) | `mgr`, `attributes` |

### 8.5 `GateSequence`

```python
@dataclass
class GateSequence:
    gates: list[GateModel]

    def superop(self, *, n_max, ctx, noise, noise_model, cache) -> np.ndarray
```

Computes the composed super-operator for ordered gate sequences, with
optional caching via `ModelCache`.

### 8.6 Hardware Gate Backends (`qubox_v2.gates`)

**Module**: `qubox_v2.gates`

Legacy experiment gate classes were removed. Use modern gate model/hardware
objects under `qubox_v2.gates.*`, or use explicit operation-level wrappers in
notebook code for pulse-train and calibration experiments.

| Component | Purpose | Key API |
|----------|---------|---------|
| `Gate` | Combined model + optional hardware backend | `Gate(model=..., hw=...)`, `to_dict()`, `from_dict()` |
| `QubitRotationModel` | Ideal qubit rotation model | model-only simulation/compile flows |
| `QubitRotationHardware` | QUA emission backend for rotation operations | `build(hw_ctx=...)`, `play(hw_ctx=...)`, `waveforms(hw_ctx=...)` |
| `GateSequence` | Ordered composition for simulation/evaluation | `superop(...)` |

**Usage example — pulse-train tomography with QubitRotation:**

```python
from dataclasses import dataclass
from qubox_v2.experiments import PulseTrainCalibration

# Create a non-legacy gate wrapper under test
@dataclass
class NotebookRotationGate:
    op: str
    element: str
    pulse_len: int

    def play(self):
        play(self.op, self.element)

    def waveforms(self):
        return [0.0] * self.pulse_len, [0.0] * self.pulse_len, self.pulse_len, True

arb_rot = NotebookRotationGate(
    op="x180",
    element=attr.qb_el,
    pulse_len=int(getattr(attr, "ge_rlen", 16) or 16),
)

# Define state preparations using QUA primitives
from qm.qua import play, align

def prep_e():  play("x180", attr.qb_el)
def prep_px(): play("y90",  attr.qb_el)
def prep_mx(): play("yn90", attr.qb_el)

prep_defs = {
    "g": None, "e": prep_e,
    "+x": prep_px, "-x": prep_mx,
}

# Run pulse-train calibration
pt = PulseTrainCalibration(session)
result = pt.run(
    arb_rot=arb_rot, prep_defs=prep_defs,
    N_values=np.arange(0, 80, 8),
    n_avg=20000, theta=np.pi, phi=0.0,
)

# Extract rotation error knobs
_Iw, _Qw, waveform_len, marker = arb_rot.waveforms()
analysis = pt.analyze(
    result, fit_zeta=True, multi_seed=True,
    dt_s=1e-9, n_samp=int(waveform_len),
)
pt.plot(analysis, residual_mode="both")
print(f"amp_err   = {analysis.metrics['amp_err']:+.4%}")
print(f"phase_err = {analysis.metrics['phase_err']:+.6f} rad")
print(f"d_lambda  = {analysis.metrics.get('d_lambda', 'N/A')}")
```

**Usage example — serialize/restore gate objects:**

```python
import json
from qubox_v2.gates.gate import Gate

payload = [gate.to_dict() for gate in gate_sequence]
with open("my_gates.json", "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2)

with open("my_gates.json", "r", encoding="utf-8") as f:
    loaded_payload = json.load(f)

loaded = [Gate.from_dict(item, hw_ctx=hw_ctx) for item in loaded_payload]
```

---

## 9. Experiment Registry

### 9.1 Complete Experiment Listing

All experiments inherit from `ExperimentBase` and implement the
`run() → analyze() → plot()` contract.

**Spectroscopy:**

| Class | Purpose |
|-------|---------|
| `ResonatorSpectroscopy` | Resonator frequency scan |
| `ResonatorPowerSpectroscopy` | Power-dependent resonator scan |
| `ResonatorSpectroscopyX180` | Two-tone resonator spectroscopy |
| `ReadoutTrace` | Raw readout trace acquisition |
| `ReadoutFrequencyOptimization` | Optimize readout frequency for SNR |
| `QubitSpectroscopy` | Qubit frequency scan |
| `QubitSpectroscopyCoarse` | Coarse qubit frequency search |
| `QubitSpectroscopyEF` | E-F transition spectroscopy |

**Time Domain:**

| Class | Purpose |
|-------|---------|
| `TemporalRabi` | Time Rabi oscillation |
| `PowerRabi` | Power Rabi oscillation |
| `SequentialQubitRotations` | Multi-pulse rotation sequences |
| `T1Relaxation` | T1 energy relaxation measurement |
| `T2Ramsey` | T2* Ramsey measurement |
| `T2Echo` | T2 Hahn echo measurement |
| `ResidualPhotonRamsey` | Thermal photon-induced dephasing |
| `TimeRabiChevron` | 2-D time Rabi vs frequency |
| `PowerRabiChevron` | 2-D power Rabi vs frequency |
| `RamseyChevron` | 2-D Ramsey vs frequency |

**Calibration:**

| Class | Purpose |
|-------|---------|
| `IQBlob` | Simple g/e IQ blob acquisition |
| `ReadoutGERawTrace` | Raw time-domain g/e traces |
| `ReadoutGEIntegratedTrace` | Time-sliced integrated traces |
| `ReadoutGEDiscrimination` | G/E state discrimination with rotated weights |
| `ReadoutWeightsOptimization` | Optimize integration weights |
| `ReadoutButterflyMeasurement` | Three-measurement butterfly (F, Q, QND) |
| `CalibrateReadoutFull` | End-to-end readout pipeline (optional wopt → GE → butterfly) |
| `ReadoutAmpLenOpt` | 2-D readout amplitude × length optimization |
| `AllXY` | 21-gate-pair error benchmarking |
| `DRAGCalibration` | DRAG coefficient optimization |
| `RandomizedBenchmarking` | Standard and interleaved RB |
| `QubitResetBenchmark` | Reset fidelity benchmark |
| `ActiveQubitResetBenchmark` | Active reset measurement |
| `ReadoutLeakageBenchmarking` | Readout leakage to higher states |

**Cavity:**

| Class | Purpose |
|-------|---------|
| `StorageSpectroscopy` | Storage cavity frequency scan |
| `StorageSpectroscopyCoarse` | Coarse storage cavity search |
| `NumSplittingSpectroscopy` | Number-splitting spectroscopy |
| `StorageRamsey` | Storage Ramsey measurement |
| `StorageChiRamsey` | Chi-dependent Ramsey |
| `StoragePhaseEvolution` | Phase evolution characterization |
| `FockResolvedSpectroscopy` | Fock-number-resolved spectroscopy |
| `FockResolvedT1` | Fock-resolved T1 |
| `FockResolvedRamsey` | Fock-resolved Ramsey |
| `FockResolvedPowerRabi` | Fock-resolved power Rabi |

**Tomography:**

| Class | Purpose |
|-------|---------|
| `QubitStateTomography` | Three-axis Bloch vector reconstruction |
| `FockResolvedStateTomography` | Fock-resolved state tomography |
| `StorageWignerTomography` | Wigner function reconstruction |
| `SNAPOptimization` | SNAP gate angle optimization |

**SPA:**

| Class | Purpose |
|-------|---------|
| `SPAFluxOptimization` | SPA flux bias optimization |
| `SPAFluxOptimization2` | SPA flux optimization (scout / refine / lock modes) |
| `SPAPumpFrequencyOptimization` | SPA pump frequency optimization |

### 9.2 Experiment Contract Summary

Every experiment must satisfy:

1. **`run()`**: Returns `RunResult`.  No calibration writes.  No hidden
   pulse registration.  Must call `set_standard_frequencies()`.
2. **`analyze()`**: Idempotent.  No hardware ops.  Populate
   `AnalysisResult.{metrics, fit, metadata}`.
3. **`plot()`**: Accept `AnalysisResult` + optional `ax`.  Create own
   figure if `ax=None`.  Return `Figure`.

### 9.3 Usage Examples by Category

**Spectroscopy:**

```python
# Resonator spectroscopy with orchestrator
spec = ResonatorSpectroscopy(session)
cycle = orch.run_analysis_patch_cycle(
    spec,
    run_kwargs={
        "readout_op": "readout",
        "rf_begin": 8560 * u.MHz, "rf_end": 8640 * u.MHz,
        "df": 200 * u.kHz, "n_avg": 10000,
    },
    analyze_kwargs={"update_calibration": True},
    apply=False, persist_artifact=True,
)

# Resonator with X180 (dispersive shift measurement)
spec_x180 = ResonatorSpectroscopyX180(session)
result = spec_x180.run(
    rf_begin=8560 * u.MHz, rf_end=8640 * u.MHz,
    df=200 * u.kHz, n_avg=10000,
)
analysis = spec_x180.analyze(result, update_calibration=True)
print(f"chi = {analysis.metrics['chi'] / 1e3:.1f} kHz")

# Qubit spectroscopy
qb_spec = QubitSpectroscopy(session)
result = qb_spec.run(
    pulse="saturation",
    rf_begin=6130 * u.MHz, rf_end=6170 * u.MHz,
    df=500 * u.kHz, qb_gain=1.0, qb_len=1000, n_avg=1000,
)
analysis = qb_spec.analyze(result, update_calibration=True)
print(f"f_qubit = {analysis.metrics['f0_MHz']:.4f} MHz")

# Readout trace (raw ADC)
trace = ReadoutTrace(session)
result = trace.run(attr.ro_fq, n_avg=10000)
analysis = trace.analyze(result)
trace.plot(analysis)
```

**Time domain:**

```python
# Power Rabi
rabi = PowerRabi(session)
result = rabi.run(max_gain=1.2, dg=0.04, op="ref_r180", n_avg=5000)
analysis = rabi.analyze(result, update_calibration=True, p0=[0.0001, 1, 0])
print(f"g_pi = {analysis.metrics['g_pi']:.6f}")

# Temporal Rabi
trabi = TemporalRabi(session)
result = trabi.run(
    pulse="const",
    pulse_len_begin=16, pulse_len_end=500, dt=4, n_avg=5000,
)
analysis = trabi.analyze(result)
print(f"f_Rabi = {analysis.metrics['f_Rabi']} Hz")

# T1
t1 = T1Relaxation(session)
result = t1.run(delay_end=50 * u.us, dt=500, n_avg=2000)
analysis = t1.analyze(result, update_calibration=True,
                      p0=[0, 10, 0], p0_time_unit="us")
print(f"T1 = {analysis.metrics['T1_us']:.2f} us")

# T2 Echo
t2e = T2Echo(session)
result = t2e.run(delay_end=40 * u.us, dt=100, n_avg=4000)
analysis = t2e.analyze(result, update_calibration=True,
                       p0=[-1, 40, 1.0, 0], p0_time_unit="us")
print(f"T2_echo = {analysis.metrics['T2_echo_us']:.2f} us")
```

**Calibration:**

```python
# AllXY gate error diagnostic
allxy = AllXY(session)
result = allxy.run(n_avg=5000)
analysis = allxy.analyze(result)
allxy.plot(analysis)
print(f"Gate error = {analysis.metrics['gate_error']:.4f}")

# DRAG calibration
drag = DRAGCalibration(session)
result = drag.run(amps=np.linspace(-0.5, 0.5, 20), n_avg=5000, base_alpha=1.0)
analysis = drag.analyze(result, update_calibration=True)
print(f"Optimal alpha = {analysis.metrics['optimal_alpha']}")

# Randomized benchmarking
rb = RandomizedBenchmarking(session)
result = rb.run(m_list=[1, 5, 10, 20, 50, 100, 200], num_sequence=20, n_avg=1000)
analysis = rb.analyze(result, p0=[0.99, 0.5, 0.5])
print(f"Error per gate = {analysis.metrics['error_per_gate']}")
```

**Cavity / Fock:**

```python
# Storage spectroscopy
st = StorageSpectroscopy(session)
result = st.run(
    disp="const_alpha",
    rf_begin=5200 * u.MHz, rf_end=5280 * u.MHz,
    df=200 * u.kHz, storage_therm_time=500, n_avg=50,
)
analysis = st.analyze(result, update_calibration=True)
print(f"f_storage = {analysis.metrics['f_storage'] / 1e6:.4f} MHz")

# Chi Ramsey
chi = StorageChiRamsey(session)
result = chi.run(
    fock_fq=attr.qb_fq,
    delay_ticks=np.arange(4, 2000, 10),
    disp_pulse="const_alpha",
    x90_pulse="x90", n_avg=20,
)
analysis = chi.analyze(result, update_calibration=True,
                       p0=[0.5, 0.5, 35000, 0.1, 0.0028, 400])
print(f"chi = {analysis.metrics['chi'] / 1e3:.1f} kHz")

# Fock-resolved T1
fock_t1 = FockResolvedT1(session)
fock_fqs = attr.get_fock_frequencies(2)
result = fock_t1.run(
    fock_fqs=fock_fqs,
    fock_disps=["disp_n0", "disp_n1"],
    delay_end=40000, dt=200, n_avg=20,
)
analysis = fock_t1.analyze(result)
for key, val in analysis.metrics.items():
    if key.startswith("T1_fock_"):
        print(f"{key} = {val / 1e3:.2f} us")
```

**Tomography:**

```python
from qm.qua import play

# Qubit state tomography with custom state prep
def prep_x_plus():
    play("x90", attr.qb_el)

tomo = QubitStateTomography(session)
result = tomo.run(state_prep=prep_x_plus, n_avg=10000)
analysis = tomo.analyze(result)
tomo.plot(analysis)
print(f"Bloch vector: ({analysis.metrics['sx']:.3f}, "
      f"{analysis.metrics['sy']:.3f}, {analysis.metrics['sz']:.3f})")
print(f"Purity = {analysis.metrics['purity']:.3f}")
```

**SPA:**

```python
spa_flux = SPAFluxOptimization(session)
result = spa_flux.run(
    dc_list=np.linspace(-0.5, 0.5, 51),
    sample_fqs=np.linspace(8.5e9, 8.7e9, 21),
    n_avg=1000,
)
analysis = spa_flux.analyze(result)
print(f"Best DC = {analysis.metrics['best_dc']:.4f} V")
```

### 9.4 `ReadoutConfig` (Full Pipeline Configuration)

**Module**: `qubox_v2.experiments.calibration.readout_config`

```python
@dataclass
class ReadoutConfig:
    ro_op: str = "readout"
    drive_frequency: float | None = None
    ro_el: str = "readout_element"
    r180: str = "x180"
    skip_weights_optimization: bool = False
    n_avg_weights: int = 200_000
    persist_weights: bool = True
    n_samples_disc: int = 50_000
    burn_rot_weights: bool = True
    blob_k_g: float = 2.0
    blob_k_e: float | None = None
    k: float | None = None
    n_shots_butterfly: int = 50_000
    M0_MAX_TRIALS: int = 16
    max_iterations: int = 1
    fidelity_tolerance: float = 0.01
    adaptive_samples: bool = False
    min_samples_disc: int = 10_000
    gaussianity_warn_threshold: float = 2.0
    cv_split_ratio: float = 0.2
    display_analysis: bool = False
    save: bool = True
    # ... plus kwargs dicts for sub-experiments
```

---

## 10. Comparison with Legacy

### 10.1 What Changed

| Aspect | Legacy (`qubox`) | Current (`qubox_v2`) |
|--------|------------------|----------------------|
| Entry point | `cQED_Experiment` monolith | `SessionManager` + modular experiments |
| Pulse storage | Raw waveform arrays in `pulses.json` | Declarative specs in `pulse_specs.json` |
| Calibration | Ad-hoc attribute writes | Typed `CalibrationStore` with state machine |
| Experiment API | Varied, no contract | `ExperimentBase.run()/analyze()/plot()` |
| Config building | Single-pass merge | Layered `ConfigEngine` with overlays |
| State tracking | None | `SessionState` with build hash |
| Artifact management | Scattered files | Build-hash-keyed `ArtifactManager` |
| Schema versioning | None | Mandatory version field + migration chain |

### 10.2 Why Hidden Waveform Mutation Was Removed

In legacy `qubox`, some experiments internally called
`ensure_displacement_ops()` or registered waveforms inside their
constructors.  This made it impossible to:

- Know which operations existed before running an experiment.
- Reproduce results without re-running the exact same notebook sequence.
- Validate that the QM config was self-consistent.

In `qubox_v2`, all pulse/waveform registration happens explicitly in the
notebook *before* the experiment is constructed.

### 10.3 Why SessionState Exists

`SessionState` captures a cryptographic hash of every source-of-truth file
at session open.  This enables:

- **Reproducibility**: same hash → same experiment conditions.
- **Artifact tagging**: generated files are stored under the build hash.
- **Drift detection**: if a file changes mid-session, the hash changes.

### 10.4 Why Notebook-First Workflow is Required

The notebook is the single authoritative site for:

1. **Pulse declaration** — which operations exist.
2. **State preparation** — which sequence prepares the target state.
3. **Calibration approval** — the human decides whether to commit.

This eliminates hidden side effects and ensures every experimental
configuration is visible, auditable, and reproducible.

---

## 11. SessionManager Lifecycle (Detailed)

### 11.1 Initialization Sequence (`__init__`)

**Module**: `qubox_v2/experiments/session.py:69-146`

The constructor performs the following in order:

1. **Create experiment directory** (line 81):
   `experiment_path.mkdir(parents=True, exist_ok=True)`

2. **Load hardware** (lines 86-88):
   `ConfigEngine(hardware_path=.../hardware.json)` → parses into layered
   config (hardware_base + hardware_extras).

3. **QM connection** (lines 91-98):
   `QuantumMachinesManager(host=qop_ip, ...)` — does NOT open a machine
   yet; just creates the manager.

4. **Hardware controller** (lines 100-104):
   `HardwareController(qmm, config_engine)` — wraps QM connection.

5. **Program runner + queue** (lines 107-112):
   `ProgramRunner(qmm, controller, config_engine)` + `QueueManager`.

6. **Pulse management** (lines 115-120):
   - If `pulses.json` exists: `PulseOperationManager.from_json(path)`.
   - Otherwise: empty `PulseOperationManager()`.
   - Also creates empty `PulseRegistry()`.

7. **Calibration store** (lines 122-126):
   `CalibrationStore(cal_path, auto_save=auto_save_calibration)`.
   - Path: `{experiment_path}/config/calibration.json`.
   - Creates default file if absent.

8. **External devices** (lines 129-138):
   `DeviceManager(devices_path)` + optional `instantiate_all()`.

9. **Physics attributes** (line 141):
   `cQED_attributes.load(experiment_path)` from `cqed_params.json`.

10. **Runtime settings** (line 142):
    `_load_runtime_settings()` from `session_runtime.json` with fallback
    to `cqed_params.json` deprecated fields.

11. **Orchestrator** (line 144):
    `CalibrationOrchestrator(self)` — wired with default patch rules.

### 11.2 Open Sequence (`open()`)

**Module**: `qubox_v2/experiments/session.py:331-337`

1. **Merge pulses** (line 333):
   `config_engine.merge_pulses(self.pulse_mgr)` — generates pulse overlay
   from POM.

2. **Open QM** (line 334):
   `hardware.open_qm()` — passes compiled QM config to
   `QuantumMachinesManager.open_qm()`.

3. **Load measureConfig** (line 335):
   `_load_measure_config()` → `measureMacro.load_json(path)` if
   `measureConfig.json` exists.

4. **Validate elements** (line 336):
   `validate_runtime_elements(auto_map=True)` — checks element names
   from `cqed_params.json` against live QM config.

### 11.3 Close Sequence (`close()`)

**Module**: `qubox_v2/experiments/session.py:482-502`

1. `hardware.close()` — releases QM connection.
2. Device handles disconnected (loop over `devices.handles`).
3. `save_pulses()` → writes `pulses.json`.
4. `save_runtime_settings()` → writes `session_runtime.json`.
5. `calibration.save()` → writes `calibration.json`.

Each step is wrapped in try/except to ensure teardown completes even if
individual saves fail.

### 11.4 Session Setup Utilities

**Preflight validation, session state, and config snapshots:**

```python
from qubox_v2.core.session_state import SessionState
from qubox_v2.core.artifact_manager import ArtifactManager
from qubox_v2.core.preflight import preflight_check
from qubox_v2.core.artifacts import save_config_snapshot
from qubox_v2.core.schemas import validate_config_dir

# Session state (frozen config hash for reproducibility)
config_dir = Path(session.experiment_path) / "config"
ss = SessionState.from_config_dir(
    config_dir,
    sample_config_dir=sample_config_dir,
    sample_id="post_cavity_sample_A",
    cooldown_id="cd_2025_02_22",
    wiring_rev=ctx.wiring_rev,
)
print(ss.summary())
print(f"Build hash: {ss.build_hash}")

# Artifact manager (build-hash-keyed storage)
am = ArtifactManager(session.experiment_path, ss.build_hash)
am.save_session_state(ss.to_dict())

# Preflight validation
report = preflight_check(session)
if report["all_ok"]:
    print("All preflight checks PASSED.")
else:
    for err in report["errors"]:
        print(f"  ERROR: {err}")

# Config snapshot (frozen copy for future reference)
snapshot_path = save_config_snapshot(session, tag="session_open")

# Schema validation
results = validate_config_dir(config_dir)
for r in results:
    status = "PASS" if r.valid else "FAIL"
    print(f"  {status} v={r.version}")
```

**Runtime readout override:**

```python
# Override readout operation at runtime (e.g., switch demod strategy)
override_info = session.override_readout_operation(
    element=attr.ro_el,
    operation="readout",
    weights=None,                     # use current weights
    demod="dual_demod.full",
    threshold=None,                   # use calibrated threshold
    weight_len=None,
    apply_to_runtime_context=True,
    persist_measure_config=True,
    drive_frequency=attr.ro_fq,
)
print(f"Readout override: {override_info['element']} / {override_info['operation']}")
```

---

## 12. Artifact Saving (Detailed)

### 12.1 Experiment Output Saving

**Module**: `qubox_v2/experiments/session.py:296-326`

`SessionManager.save_output(output, tag)`:

- **Path**: `{experiment_path}/data/{tag}_{timestamp}.npz`
- **Companion**: `{experiment_path}/data/{tag}_{timestamp}.meta.json`
- **Filter**: `split_output_for_persistence(data)` from
  `core/persistence_policy.py:35-68` — drops arrays > 8192 elements and
  arrays whose key matches raw-like patterns (`raw`, `shot`, `buffer`,
  `acq`, etc.).
- **Side effect**: Does not mutate `cqed_params.json`; runtime provenance is captured in metadata/artifacts.

### 12.2 Persistence Policy

**Module**: `qubox_v2/core/persistence_policy.py`

| Function | Purpose |
|----------|---------|
| `is_raw_like_key(key)` (line 18-21) | Returns `True` if key matches raw/shot/buffer pattern |
| `should_persist_array(key, arr)` (line 24-32) | Returns `False` if raw-like or > 8192 elements |
| `split_output_for_persistence(data)` (line 35-68) | Splits into `(arrays, meta, dropped)` |
| `sanitize_mapping_for_json(data)` (line 89-108) | Recursively sanitize for JSON; drops large arrays |

Dropped fields are recorded in `_persistence.dropped_fields` metadata.

### 12.3 Calibration Run Artifacts

**Module**: `qubox_v2/experiments/experiment_base.py:390-488`

`guarded_calibration_commit()` always writes an artifact regardless of
validation outcome:

- **Path**: `{experiment_path}/artifacts/calibration_runs/{tag}_{timestamp}.json`
- **Content**: timestamp, experiment name, validation errors, fit params,
  metrics, run metadata.
- **Phase A**: Artifact always saved.
- **Phase B**: Calibration update applied only if all gates pass AND
  `allow_inline_mutations=True`.

### 12.4 Orchestrator Artifacts

**Module**: `qubox_v2/calibration/orchestrator.py:226-252`

`CalibrationOrchestrator.persist_artifact(artifact)`:

- **Path**: `{experiment_path}/artifacts/runtime/{name}_{timestamp}.npz`
- **Companion**: `.../{name}_{timestamp}.meta.json`
- **Filter**: Same `split_output_for_persistence()` policy.

### 12.5 Build-Hash Artifacts

**Module**: `qubox_v2/core/artifact_manager.py:41-175`

`ArtifactManager(experiment_path, build_hash)`:

- **Directory**: `{experiment_path}/artifacts/{build_hash}/`
- **Files**: `session_state.json`, `generated_config.json`, reports.
- **Cleanup**: `cleanup_artifacts(keep_latest=10)` prunes old hash dirs.

---

## 13. CalibrationOrchestrator

### 13.1 Overview

**Module**: `qubox_v2/calibration/orchestrator.py`
**Purpose**: Owns the full calibration lifecycle from experiment execution
through artifact persistence to state mutation.

```python
class CalibrationOrchestrator:
    def __init__(self, session, *, patch_rules=None) -> None
```

**Created by**: `SessionManager.__init__()` at `session.py:144`.
**Patch rules**: `default_patch_rules(session)` from `patch_rules.py:246-274`.

### 13.2 Lifecycle Methods

| Method | Signature | Return | Side Effects |
|--------|-----------|--------|--------------|
| `run_experiment` | `(exp, **kwargs) -> Artifact` | `Artifact` | Executes experiment `run()` |
| `analyze` | `(exp, artifact, **kwargs) -> CalibrationResult` | `CalibrationResult` | Calls experiment `analyze()` |
| `build_patch` | `(result) -> Patch` | `Patch` | Applies patch rules |
| `apply_patch` | `(patch, dry_run=False) -> dict` | Preview dict | Mutates calibration store + pulses |
| `run_analysis_patch_cycle` | `(exp, *, run_kwargs, analyze_kwargs, persist_artifact, apply) -> dict` | Full result dict | Full lifecycle in one call |
| `persist_artifact` | `(artifact) -> Path` | Data path | Writes `.npz` + `.meta.json` |

### 13.3 Patch Operations

`apply_patch()` (orchestrator.py:148-224) supports these operation types:

| Op Type | Effect | Code Path |
|---------|--------|-----------|
| `SetCalibration` | Update calibration store via dotted path | `_set_calibration_path()` (line 270-302) |
| `SetPulseParam` | Update pulse calibration entry | `_set_pulse_param()` (line 304-308) |
| `SetMeasureWeights` | Register integration weights in POM or measureMacro | Lines 170-204 |
| `SetMeasureDiscrimination` | Update `measureMacro._ro_disc_params` via `_update_readout_discrimination()` | Patch-only entry point (v1.4.0) |
| `SetMeasureQuality` | Update `measureMacro._ro_quality_params` via `_update_readout_quality()` | Patch-only entry point (v1.4.0) |
| `PersistMeasureConfig` | Save measureMacro to JSON | Lines 206-210 |
| `TriggerPulseRecompile` | Call `session.burn_pulses()` | Lines 212-214 |

After all ops (non-dry-run): `session.calibration.save()`,
`session.save_pulses()`, and `measureMacro.sync_from_calibration()`
(lines 217-227).  The sync step ensures `measureMacro` remains
consistent with the canonical `CalibrationStore` after every patch.

### 13.4 Patch Rules

**Module**: `qubox_v2/calibration/patch_rules.py`

| Rule | Result Kind | What It Patches |
|------|-------------|-----------------|
| `PiAmpRule` | `pi_amp` | Reference pulse amplitude + primitive family (x180, y180, x90, etc.) |
| `T1Rule` | `t1` | `coherence.<element>.T1` (unit heuristic: values > 1e-3 treated as ns, converted to s) |
| `T2RamseyRule` | `t2_ramsey` | `coherence.<element>.T2_ramsey` + optional frequency correction |
| `T2EchoRule` | `t2_echo` | `coherence.<element>.T2_echo` |
| `FrequencyRule` | `qubit_freq` / `resonator_freq` / `storage_freq` | `frequencies.<element>.<field>` + optional kappa |
| `DragAlphaRule` | `drag_alpha` | `pulse_calibrations.<pulse>.drag_coeff` for all primitives |
| `DiscriminationRule` | `ReadoutGEDiscrimination` | `discrimination.<element>.*` |
| `ReadoutQualityRule` | `ReadoutButterflyMeasurement` | `readout_quality.<element>.*` |
| `WeightRegistrationRule` | Any (with metadata) | Promotes proposed ops from analysis metadata |
| `PulseTrainRule` | `pulse_train` | Reference pulse corrected amplitude + phase via pulse-train tomography |

**Default rule mapping** (`default_patch_rules(session)`, patch_rules.py:282-313):

| Kind | Rules |
|------|-------|
| `pi_amp` | `PiAmpRule` |
| `t1` | `T1Rule`, `WeightRegistrationRule` |
| `t2_ramsey` | `T2RamseyRule`, `WeightRegistrationRule` |
| `t2_echo` | `T2EchoRule`, `WeightRegistrationRule` |
| `resonator_freq` | `FrequencyRule(field="resonator_freq")`, `WeightRegistrationRule` |
| `qubit_freq` | `FrequencyRule`, `WeightRegistrationRule` |
| `storage_freq` | `FrequencyRule`, `WeightRegistrationRule` |
| `drag_alpha` | `DragAlphaRule`, `WeightRegistrationRule` |
| `pulse_train` | `PulseTrainRule` |
| `ReadoutGEDiscrimination` | `DiscriminationRule`, `WeightRegistrationRule` |
| `ReadoutWeightsOptimization` | `WeightRegistrationRule` |
| `ReadoutButterflyMeasurement` | `ReadoutQualityRule`, `WeightRegistrationRule` |

---

## 14. measureConfig / Readout Macro Persistence

### 14.1 The measureMacro Singleton

**Module**: `qubox_v2/programs/macros/measure.py`
**Type**: Module-level singleton instance.

The `measureMacro` manages:

- **Current pulse operation** binding (element, op, pulse, length, I/Q
  waveform names, integration weight mapping).
- **Demodulation config** (dual_demod.full, weight_len).
- **Discrimination params** (threshold, angle, rotated/unrotated blob
  centroids, sigma, fidelity).
- **Quality params** (F, Q, V, t01, t10, confusion matrix, transition
  matrix, affine_n).
- **Post-selection config** (policy, blob radii, exclusivity).
- **State stack** for push/restore snapshots.

### 14.2 JSON Persistence

**Format version**: 5 (`_version` field).

**Save**: `measureMacro.save_json(path)` → writes full state snapshot.
**Load**: `measureMacro.load_json(path)` → restores from JSON.

**When saved**:
- `SessionManager.override_readout_operation(persist_measure_config=True)`
  (session.py:451-453).
- `CalibrationOrchestrator.apply_patch()` with `PersistMeasureConfig` op
  (orchestrator.py:206-210).
- `SessionManager.close()` — saves `measureConfig.json` on session
  teardown (session.py, v1.4.0).

**When loaded**:
- `SessionManager.open()` → `_load_measure_config()` (session.py:335,
  465-477).  After loading, `sync_from_calibration()` is called to pull
  canonical values from `CalibrationStore` (v1.4.0).

### 14.3 How Readout Values Flow into Downstream Experiments

1. **measureMacro** is a module-level singleton imported by all QUA
   program factories via `from ..programs.macros.measure import measureMacro`.

2. Programs call `measureMacro.measure(...)` which builds the QUA
   `measure()` statement using the current discrimination params.

3. The threshold and angle from `measureMacro._ro_disc_params` are used
   for real-time state discrimination in QUA programs.

4. Experiments like `AllXY` use `measureMacro` confusion matrix for
   error correction (via `apply_affine_correction()`).

5. The integration weights referenced in `measureMacro._int_weights_mapping`
   must exist in the POM (registered during readout calibration).

### 14.4 Dual-Truth Problem — **RESOLVED in v1.4.0**

~~Discrimination params exist in both:~~

~~- `calibration.json` → `discrimination.<element>.*`
  (canonical typed store)~~
~~- `measureConfig.json` → `current.ro_disc_params.*`
  (runtime macro state)~~

~~These can diverge.  See `STALE_CALIBRATION_RISK_REPORT.md` Risk R3.~~

**Resolution**: `measureMacro.sync_from_calibration(cal_store, element)`
establishes a one-way sync direction: `CalibrationStore → measureMacro`.
This sync is triggered:

1. At session open (`_load_measure_config()`, after loading `measureConfig.json`).
2. After every `CalibrationOrchestrator.apply_patch()` commit.

`CalibrationStore` is canonical for discrimination and quality
parameters.  `measureConfig.json` is a persistence cache only.

---

## 15. Known Gaps and Risks

### 15.1 No Sample Identity — **RESOLVED in v1.2.0**

~~There is no `sample_id`, `cooldown_id`, or `wiring_revision` in any
config file.~~  Now addressed by `ExperimentContext` (Section 16) and
`CalibrationContext` (Section 17).  Sample identity is embedded in
calibration files as of schema v4.0.0.

### 15.2 No Cooldown Scoping — **RESOLVED in v1.2.0**

~~Calibrations from previous cooldowns are silently reused.~~
Now addressed by `SampleRegistry` cooldown directories (Section 16.2)
and `ContextMismatchError` enforcement (Section 17.2).  Each cooldown
gets its own `config/` subtree.

### 15.3 No Hardware-Calibration Coupling — **RESOLVED in v1.2.0**

~~Changes to `hardware.json` do not invalidate `calibration.json`.~~
Now addressed by `wiring_rev` (SHA-256 of hardware.json) embedded in
`ExperimentContext` and validated on `CalibrationStore` load
(Section 17.2).

### 15.4 Dual-Truth Stores — **RESOLVED in v1.4.0**

~~Discrimination params and frequencies exist in multiple files without
enforced sync.~~
~~See `docs/audit/PATHS_AND_OWNERSHIP.md` Observations 1 and 2.~~
~~See `docs/audit/MACRO_ENTANGLEMENT_REPORT.md` entries D1, D2, D3.~~

Now resolved by `measureMacro.sync_from_calibration()` which establishes
one-way sync `CalibrationStore → measureMacro`.  Sync is triggered at
session open and after every orchestrator patch commit.  See Section 14.4.

### 15.5 Direct Calibration Mutation in analyze() — **RESOLVED in v1.4.0**

~~Several experiment `analyze()` methods directly mutate the calibration
store, bypassing the state machine and orchestrator.~~
~~See `docs/audit/LEAKS.md` Section A.~~
~~See `docs/audit/MACRO_ENTANGLEMENT_REPORT.md` entries A1, A2, C1.~~

Now resolved:
- `_update_readout_discrimination()` removed from `_apply_rotated_measure_macro()`.
- `_update_readout_quality()` replaced by `SetMeasureQuality` patch op
  (proposed via `metadata["proposed_patch_ops"]`).
- `save_json()` calls removed from analyze paths; persistence routed
  through `PersistMeasureConfig` orchestrator op with legacy fallback.
- Both `_update_readout_discrimination()` and `_update_readout_quality()`
  emit `DeprecationWarning` when called directly.
- `legacy_experiment.py` retains direct mutations (accepted legacy debt).

### 15.6 Non-Transactional Session Close

`SessionManager.close()` writes multiple files sequentially without
transactional guarantees.
See `docs/audit/STALE_CALIBRATION_RISK_REPORT.md` Risk R9.
**Status**: Open.

### 15.7 Modularity Roadmap — **IMPLEMENTED in v1.2.0**

~~Concrete proposals for sample/cooldown scoping are documented in
`docs/audit/MODULARITY_RECOMMENDATIONS.md`.~~
All modularity recommendations have been implemented.  See Sections 16-19.

---

## 16. ExperimentContext & SampleRegistry

### 16.1 ExperimentContext

**Module**: `qubox_v2/core/experiment_context.py`
**Type**: `@dataclass(frozen=True)`

An immutable identity token that pins a session to a specific sample,
cooldown, and hardware wiring.  Created once during `SessionManager` init
and never mutated.

```python
@dataclass(frozen=True)
class ExperimentContext:
    sample_id:      str
    cooldown_id:    str
    wiring_rev:     str            # SHA-256[:8] of hardware.json
    schema_version: str = "4.0.0"
    config_hash:    str = ""       # SHA-256[:12] of merged config
```

#### Methods

| Method | Signature | Return | Description |
|--------|-----------|--------|-------------|
| `to_dict` | `() -> dict` | `dict` | Serialise to plain dict |
| `from_dict` | `(d: dict) -> ExperimentContext` | `ExperimentContext` | Deserialise from dict (classmethod) |
| `matches_sample` | `(other: ExperimentContext) -> bool` | `bool` | Same `sample_id` |
| `matches_cooldown` | `(other: ExperimentContext) -> bool` | `bool` | Same `sample_id` *and* `cooldown_id` |
| `matches_wiring` | `(other: ExperimentContext) -> bool` | `bool` | Same `wiring_rev` |
| `compute_wiring_rev` | `(hw_path: Path) -> str` | `str` | Static: SHA-256[:8] of file (staticmethod) |

#### Typical Flow

```text
SampleRegistry ─resolve_config_paths()─▶ file system paths
                                           │
ContextResolver ─resolve()─────────────────▶ ExperimentContext
                                           │
SessionManager.__init__() ◀────────────────┘
  │
  ├─▶ CalibrationStore(path, context=ctx)  ← validates on load
  └─▶ session.context                      ← exposed property
```

### 16.2 SampleRegistry

**Module**: `qubox_v2/devices/sample_registry.py`
**Type**: `class SampleRegistry`

Manages the filesystem tree for multi-sample, multi-cooldown experiments.

```python
class SampleRegistry:
    def __init__(self, base_path: Path) -> None
```

**Directory layout created by registry operations:**

```text
{base_path}/samples/
  {sample_id}/
    sample.json            ← SampleInfo metadata
    config/                ← sample-level: hardware.json, cqed_params.json,
    │                         devices.json, pulse_specs.json
    cooldowns/
      {cooldown_id}/
        config/            ← cooldown-level: calibration.json, pulses.json,
        │                     measureConfig.json
        data/              ← experiment raw data
        artifacts/         ← build-hash keyed artifacts
```

#### Methods

| Method | Signature | Return | Description |
|--------|-----------|--------|-------------|
| `create_sample` | `(sample_id, *, description, config_source, metadata)` | `Path` | Create sample dir + copy config |
| `create_cooldown` | `(sample_id, cooldown_id, *, seed_from)` | `Path` | Create cooldown dir, seed calibration |
| `list_samples` | `()` | `list[str]` | All sample IDs |
| `list_cooldowns` | `(sample_id)` | `list[str]` | All cooldown IDs for a sample |
| `sample_exists` | `(sample_id) -> bool` | `bool` | Check sample dir exists |
| `cooldown_exists` | `(sample_id, cooldown_id) -> bool` | `bool` | Check cooldown dir exists |
| `sample_path` | `(sample_id) -> Path` | `Path` | Absolute path to sample dir |
| `cooldown_path` | `(sample_id, cooldown_id) -> Path` | `Path` | Absolute path to cooldown dir |
| `load_sample_info` | `(sample_id) -> SampleInfo` | `SampleInfo` | Read `sample.json` |
| `resolve_config_paths` | `(sample_id, cooldown_id) -> dict` | `dict` | Merged sample-level + cooldown-level paths |

### 16.3 SampleInfo

**Module**: `qubox_v2/devices/sample_registry.py`
**Type**: `@dataclass`

```python
@dataclass
class SampleInfo:
    sample_id:   str
    description: str   = ""
    created:     str   = ""          # ISO-8601
    metadata: dict  = field(default_factory=dict)
```

---

## 17. CalibrationContext & ContextResolver

### 17.1 CalibrationContext

**Module**: `qubox_v2/calibration/models.py`
**Type**: `class CalibrationContext(BaseModel)` (Pydantic v2)

Embedded context block inside `calibration.json`, stamped on every save
to record which sample, cooldown, and wiring revision produced the data.

```python
class CalibrationContext(BaseModel):
    sample_id:      str
    cooldown_id:    str
    wiring_rev:     str
    schema_version: str  = "4.0.0"
    config_hash:    str  = ""
    created:        str  = ""   # ISO-8601
```

The `CalibrationData` model (root of `calibration.json`) now includes:

```python
class CalibrationData(BaseModel):
    version: str = "5.0.0"
    context: CalibrationContext | None = None   # NEW in v4.0.0
    alias_index: dict[str, str] = {}            # NEW in v5.0.0
    # ... existing fields ...
```

#### Schema Migration v3 → v4 → v5

On load, `CalibrationStore._load_or_create()` detects `version < "4.0.0"`
and calls `_migrate_calibration_3_to_4()` (registered in `core/schemas.py`),
which:

1. Sets `version = "4.0.0"`.
2. Adds an empty `context: null` block.
3. The migration is in-memory only; the file is updated on next
   `calibration.save()`.

Migration v4 → v5 (`_migrate_calibration_4_to_5()`):

1. Sets `version = "5.0.0"`.
2. Adds an empty `alias_index: {}` dict.
3. Existing element-name keys in calibration sections continue to work
   via dual-lookup.

### 17.2 Context Validation in CalibrationStore

**Module**: `qubox_v2/calibration/store.py`

```python
class CalibrationStore:
    def __init__(
        self,
        path: Path,
        *,
        context: ExperimentContext | None = None,
        strict_context: bool = True,
    ) -> None
```

**New parameters** (v1.2.0):

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `context` | `ExperimentContext \| None` | `None` | Active session context |
| `strict_context` | `bool` | `True` | Raise on mismatch vs. warn |

**Validation flow** (`_validate_context()`, called from `_load_or_create()`):

1. If no context provided → skip (legacy mode).
2. If calibration file has no `context` block → skip (pre-v4 file).
3. Compare `context.sample_id` with `data.context.sample_id`.
4. Compare `context.wiring_rev` with `data.context.wiring_rev`.
5. On mismatch:
   - `strict_context=True` → raise `ContextMismatchError`.
   - `strict_context=False` → log warning.

**Stamping** (`stamp_context(ctx)`):

Called by `CalibrationStore.save()` to update the context block before
writing.  Ensures every save records the authoring context.

### 17.3 ContextResolver

**Module**: `qubox_v2/devices/context_resolver.py`

```python
class ContextResolver:
    def __init__(self, registry: SampleRegistry) -> None

    def resolve(
        self,
        sample_id: str,
        cooldown_id: str,
    ) -> ExperimentContext
```

Resolves a `(sample_id, cooldown_id)` pair into a full
`ExperimentContext` by:

1. Looking up `hardware.json` in the sample config directory.
2. Computing `wiring_rev` via `ExperimentContext.compute_wiring_rev()`.
3. Computing `config_hash` from the merged set of sample-level +
   cooldown-level config files.
4. Setting `schema_version = "4.0.0"`.

### 17.4 ContextMismatchError

**Module**: `qubox_v2/core/errors.py`

```python
class ContextMismatchError(ConfigError):
    """Calibration data was produced by a different sample or wiring revision."""
```

Raised by `CalibrationStore._validate_context()` in strict mode.

---

## 18. Context-Mode SessionManager

### 18.1 New Constructor Parameters

**Module**: `qubox_v2/experiments/session.py`

```python
class SessionManager:
    def __init__(
        self,
        experiment_path: str | None = None,
        *,
        # Legacy mode (positional)
        qop_ip: str = "",
        cluster_name: str = "",
        auto_save_calibration: bool = True,
        # Context mode (v1.2.0)
        sample_id: str | None = None,
        cooldown_id: str | None = None,
        registry_base: Path | None = None,
        strict_context: bool = True,
    ) -> None
```

**New keyword-only parameters** (v1.2.0):

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sample_id` | `str \| None` | `None` | Sample identifier in the registry |
| `cooldown_id` | `str \| None` | `None` | Cooldown identifier |
| `registry_base` | `Path \| None` | `None` | Root path containing `samples/` tree |
| `strict_context` | `bool` | `True` | Pass to `CalibrationStore` for mismatch enforcement |

### 18.2 Mode Selection

| Condition | Mode | `experiment_path` | `context` |
|-----------|------|--------------------|-----------|
| `sample_id` + `cooldown_id` provided | **Context** | Auto-resolved to cooldown dir | `ExperimentContext(...)` |
| Only `experiment_path` provided | **Legacy** | As provided | `None` |

In context mode, the session:

1. Creates a `SampleRegistry(registry_base)`.
2. Resolves `config_paths = registry.resolve_config_paths(sample_id, cooldown_id)`.
3. Sets `experiment_path` to the cooldown root directory.
4. Builds `ExperimentContext` via `ContextResolver(registry).resolve(...)`.
5. Passes `context` and `strict_context` to `CalibrationStore`.
6. Populates `SessionState` with `sample_id`, `cooldown_id`, `wiring_rev`.

### 18.3 New Properties and Methods

| Member | Type | Description |
|--------|------|-------------|
| `session.context` | `ExperimentContext \| None` | Active context (None in legacy mode) |
| `SessionManager.from_sample(cls, ...)` | classmethod | Convenience for context-mode construction |

### 18.4 SessionState Updates

**Module**: `qubox_v2/core/session_state.py`

New fields added to `SessionState`:

| Field | Type | Default | Source |
|-------|------|---------|--------|
| `sample_id` | `str \| None` | `None` | `ExperimentContext.sample_id` |
| `cooldown_id` | `str \| None` | `None` | `ExperimentContext.cooldown_id` |
| `wiring_rev` | `str \| None` | `None` | `ExperimentContext.wiring_rev` |

These are included in `to_dict()` output, `summary()` text, and
`from_config_dir()` factory when the corresponding kwargs are supplied.

### 18.5 Orchestrator Context Stamping

`CalibrationOrchestrator.persist_artifact()` (orchestrator.py) now stamps
`experiment_context` into artifact metadata when `session.context` is
available:

```python
meta["experiment_context"] = session.context.to_dict()
```

---

## 19. Migration Guide: Legacy → Context Mode

### 19.1 Overview

Existing notebooks using `SessionManager("./seq_1_device")` continue to
work unchanged.  Context mode is opt-in — activate it by passing `sample_id`
and `cooldown_id`.

### 19.2 Step-by-Step Migration

1. **Import `SampleRegistry`**:

```python
from qubox_v2.devices import SampleRegistry
```

2. **Create a sample from existing config** (one-time setup):

```python
registry = SampleRegistry(Path("E:/qubox"))
registry.create_sample(
    "my_device",
    config_source=Path("./seq_1_device/config"),
    description="3D cavity transmon A",
)
```

3. **Create a cooldown** (per thermal cycle):

```python
registry.create_cooldown(
    "my_device", "cd_2025_03_15",
    seed_from=Path("./seq_1_device/config"),
)
```

4. **Open session in context mode**:

```python
session = SessionManager(
    sample_id="my_device",
    cooldown_id="cd_2025_03_15",
    registry_base=Path("E:/qubox"),
    qop_ip="10.157.36.68",
    cluster_name="Cluster_2",
)
session.open()
```

5. **Replace `experiment_path` references**:

```python
# Before (legacy):
config_dir = Path("./seq_1_device/config")

# After (context):
config_dir = Path(session.experiment_path) / "config"
```

6. **All experiment cells are unchanged** — they use `session` object:

```python
spec = ResonatorSpectroscopy(session)
result = spec.run(...)
analysis = spec.analyze(result, update_calibration=True)
spec.plot(analysis)
```

### 19.3 Switching Cooldowns

```python
# Start a new cooldown for the same sample
registry.create_cooldown("my_device", "cd_2025_04_01")

session = SessionManager(
    sample_id="my_device",
    cooldown_id="cd_2025_04_01",
    registry_base=Path("E:/qubox"),
    qop_ip="10.157.36.68",
)
session.open()
# All calibrations start fresh — no stale data from previous cooldown
```

### 19.4 Running Notebooks from Any Directory

Add this to the first code cell of any notebook:

```python
import sys
sys.path.insert(0, r"E:\qubox")
```

This ensures `qubox_v2` is importable regardless of the working directory.

### 19.5 Compatibility Matrix

| Feature | Legacy Mode | Context Mode |
|---------|-------------|--------------|
| Session constructor | `SessionManager("./seq_1_device")` | `SessionManager(sample_id=..., cooldown_id=...)` |
| Calibration path | `{experiment_path}/config/calibration.json` | `samples/{id}/cooldowns/{cd}/config/calibration.json` |
| Schema version | v3.0.0 (auto-migrated in memory) | v4.0.0 |
| Stale-cal protection | None | `ContextMismatchError` |
| `session.context` | `None` | `ExperimentContext(...)` |
| Experiment API | Unchanged | Unchanged |
| Orchestrator API | Unchanged | + context metadata in artifacts |
| Backward compatible | N/A | Yes — no breaking changes to experiment code |

### 19.6 Reference Notebook

See `notebooks/post_cavity_experiment_context.ipynb` for a complete
working example with all experiments migrated to context mode.

---

## 20. Macro System Architecture

### 20.1 Overview

The macro system provides QUA code-generation primitives that bridge the gap
between high-level experiment logic and low-level QUA program construction.
It consists of three components:

| Component | Module | Type | Purpose |
|-----------|--------|------|---------|
| `measureMacro` | `programs/macros/measure.py` | Global singleton class | QUA readout code generation + readout calibration state |
| `sequenceMacros` | `programs/macros/sequence.py` | Stateless helper class | QUA sequence code-generation utilities |
| `builders/` | `programs/builders/*.py` (8 sub-modules) | Function library (47 functions) | QUA program factories for all experiment types |

### 20.2 measureMacro

**Type**: Module-level singleton (non-instantiable; all methods are `@classmethod`).

**State model**: All state is stored as mutable class variables.  Key state groups:

| Group | Variables | Persistence |
|-------|-----------|-------------|
| Pulse binding | `_pulse_op`, `_active_op` | `measureConfig.json` |
| Demodulation | `_demod_weight_sets`, `_demod_fn`, `_demod_args`, `_demod_kwargs`, `_demod_weight_len` | `measureConfig.json` |
| Gain/frequency | `_gain`, `_drive_frequency` | `measureConfig.json` |
| Discrimination | `_ro_disc_params` (threshold, angle, fidelity, mu_g/e, sigma_g/e) | `measureConfig.json` (cache) + `calibration.json` (canonical) |
| Quality | `_ro_quality_params` (F, Q, V, confusion_matrix, transition_matrix, affine_n) | `measureConfig.json` (cache) + `calibration.json` (canonical) |
| Post-selection | `_post_select_config` | `measureConfig.json` |
| State stack | `_state_stack`, `_state_index`, `_state_counter` | Not persisted |

**New in v1.4.0**:

- `sync_from_calibration(cal_store, element)` — One-way sync from
  `CalibrationStore` to `measureMacro`.  Called at session open and after
  every orchestrator patch commit.
- `_update_readout_discrimination()` and `_update_readout_quality()` are
  deprecated.  Use `CalibrationOrchestrator.apply_patch()` with
  `SetMeasureDiscrimination` / `SetMeasureQuality` instead.

**QUA code generation**: The `measure()` method emits a QUA `measure()`
statement using the currently configured pulse operation, demodulation
weights, and discrimination threshold.  This is a **compile-time** operation
that must be called inside a `with program()` block.

**JSON persistence**: `measureConfig.json` (schema version 5).  Saved via
`save_json(path)`; loaded via `load_json(path)`.  Supports backward
compatibility with versions 3 and 4.

**State stack**: `push_settings()` / `restore_settings()` provides a LIFO
stack for experiments that need to temporarily modify readout configuration.
The `using_defaults()` context manager provides automatic push/restore.

### 20.3 sequenceMacros

**Type**: Stateless class (all `@classmethod`).  No persistent state.

| Method | Purpose | Depends on measureMacro? |
|--------|---------|:---:|
| `qubit_ramsey` | Ramsey pulse pair | No |
| `qubit_echo` | Hahn echo sequence | No |
| `conditional_reset_ground` | Conditional π on I > thr | No |
| `conditional_reset_excited` | Conditional π on I < thr | No |
| `qubit_state_tomography` | Full tomography with optional selective pulse | **Yes** |
| `num_splitting_spectroscopy` | Number-splitting frequency scan | **Yes** |
| `fock_resolved_spectroscopy` | Fock-resolved frequency scan | **Yes** |
| `prepare_state` | Active qubit reset with acceptance policies | **Yes** |
| `post_select` | Post-selection acceptance rule | **Yes** |

### 20.4 Program Builders (`programs/builders/`)

**Type**: 8 domain-specific modules containing 47 QUA program factory functions.

**Refactored in v1.4.0** from the monolithic `cQED_programs.py` (2914 lines).
The original file is retained as a backward-compatible re-export shim.

**Module layout:**

| Module | Functions | Description |
|--------|-----------|-------------|
| `builders/spectroscopy.py` | 6 | `readout_trace`, `resonator_spectroscopy`, `resonator_power_spectroscopy`, `qubit_spectroscopy`, `qubit_spectroscopy_ef`, `resonator_spectroscopy_x180` |
| `builders/time_domain.py` | 10 | `temporal_rabi`, `power_rabi`, `time_rabi_chevron`, `power_rabi_chevron`, `ramsey_chevron`, `T1_relaxation`, `T2_ramsey`, `T2_echo`, `ac_stark_shift`, `residual_photon_ramsey` |
| `builders/readout.py` | 8 | `iq_blobs`, `readout_ge_raw_trace`, `readout_ge_integrated_trace`, `readout_core_efficiency_calibration`, `readout_butterfly_measurement`, `readout_leakage_benchmarking`, `qubit_reset_benchmark`, `active_qubit_reset_benchmark` |
| `builders/calibration.py` | 5 | `sequential_qb_rotations`, `all_xy`, `randomized_benchmarking`, `drag_calibration_YALE`, `drag_calibration_GOOGLE` |
| `builders/cavity.py` | 11 | `storage_spectroscopy`, `num_splitting_spectroscopy`, `sel_r180_calibration0`, `fock_resolved_spectroscopy`, `fock_resolved_T1_relaxation`, `fock_resolved_power_rabi`, `fock_resolved_qb_ramsey`, `storage_wigner_tomography`, `phase_evolution_prog`, `storage_chi_ramsey`, `storage_ramsey` |
| `builders/tomography.py` | 2 | `qubit_state_tomography`, `fock_resolved_state_tomography` |
| `builders/utility.py` | 2 | `continuous_wave`, `SPA_flux_optimization` |
| `builders/simulation.py` | 1 | `sequential_simulation` |

**Import structure** (each builder module):
```python
from ..macros.measure import measureMacro
from ..macros.sequence import sequenceMacros
```

**Backward-compatible shim** (`cQED_programs.py`):
```python
from .builders.spectroscopy import *    # noqa: F401,F403
from .builders.time_domain import *     # noqa: F401,F403
from .builders.readout import *         # noqa: F401,F403
from .builders.calibration import *     # noqa: F401,F403
from .builders.cavity import *          # noqa: F401,F403
from .builders.tomography import *      # noqa: F401,F403
from .builders.utility import *         # noqa: F401,F403
from .builders.simulation import *      # noqa: F401,F403
```

**Re-export wrappers** in `programs/spectroscopy.py`,
`programs/time_domain.py`, `programs/readout.py`, `programs/calibration.py`,
`programs/cavity.py`, and `programs/tomography.py` now import directly from
`builders/` sub-modules (not from `cQED_programs`).

All functions except `continuous_wave` depend on `measureMacro` for readout
code generation.

---

## 21. Experiment ↔ Macro Interaction Rules

### 21.1 How Experiments Should Interact with Macros

**Permitted interactions:**

| Action | Method | When |
|--------|--------|------|
| Read readout element | `measureMacro.active_element()` | Inside `run()`, during program construction |
| Read readout op | `measureMacro.active_op()` | Inside `run()`, during program construction |
| Emit QUA measure | `measureMacro.measure(...)` | Inside `with program()` block |
| Temporary macro config | `measureMacro.using_defaults(...)` context manager | Around program construction in `run()` |
| Push/restore | `measureMacro.push_settings()` / `restore_settings()` | Around program construction in `run()` |
| Read confusion matrix | `self.get_confusion_matrix()` | Inside `analyze()` |
| Read calibration values | `self.measure_macro.get_readout_calibration()` | Inside `analyze()` |

**Prohibited interactions:**

| Action | Why Prohibited | Status |
|--------|----------------|--------|
| Calling `_update_readout_discrimination()` | Bypasses orchestrator; deprecated with `DeprecationWarning` | **Removed** from readout.py; routed via `SetMeasureDiscrimination` patch |
| Calling `_update_readout_quality()` | Bypasses orchestrator; deprecated with `DeprecationWarning` | **Removed** from readout.py; routed via `SetMeasureQuality` patch |
| Calling `save_json()` from `analyze()` | Violates analyze idempotency | **Removed**; routed via `PersistMeasureConfig` patch |
| Mutating `_ro_disc_params` directly | Untracked state change | Use `sync_from_calibration()` or orchestrator patch |
| Accessing `_ro_quality_params["confusion_matrix"]` directly | Bypasses CalibrationStore | Use `self.get_confusion_matrix()` |
| Calling `set_pulse_op()` without push/restore | Leaks config to subsequent cells | (partially guarded) |

### 21.2 Correct Pattern: Readout Configuration Before Program Build

```python
# In ExperimentBase.run() — CORRECT pattern
def run(self, **params):
    self.set_standard_frequencies()
    mm = self.measure_macro
    with mm.using_defaults(pulse_op=ro_info, active_op=readout_op):
        prog = cQED_programs.some_program(physics_params...)
        return self.run_program(prog, n_total=n_avg)
```

### 21.3 Correct Pattern: Calibration Update After Analysis

```python
# In ExperimentBase.analyze() — CORRECT pattern
def analyze(self, result, *, update_calibration=False, **kw):
    metrics = self._compute_metrics(result)
    analysis = AnalysisResult.from_run(result, metrics=metrics)

    if update_calibration:
        self.guarded_calibration_commit(
            analysis=analysis,
            run_result=result,
            calibration_tag="my_experiment",
            apply_update=lambda: self.calibration_store.set_*(element, **metrics),
            required_metrics=["key_metric"],
            min_r2=0.95,
        )
    return analysis
```

### 21.4 Correct Pattern: Confusion Matrix Access

```python
# In ExperimentBase.analyze() — CORRECT pattern (v1.4.0)
confusion = kw.get("confusion", None)
if confusion is None:
    confusion = self.get_confusion_matrix()
```

`ExperimentBase.get_confusion_matrix(element=None)` (added in v1.4.0)
prefers `CalibrationStore` and falls back to `measureMacro._ro_quality_params`.
All call sites in `gates.py` and `qubit_tomo.py` have been migrated.

---

## 22. Macro State Ownership & Persistence Boundaries

### 22.1 State Ownership Table

| State | Owner | Canonical Store | Secondary Store | Sync Direction |
|-------|-------|-----------------|-----------------|----------------|
| Discrimination (threshold, angle) | `CalibrationStore` | `calibration.json` | `measureConfig.json` | CalibrationStore → measureMacro |
| Readout quality (F, Q, V) | `CalibrationStore` | `calibration.json` | `measureConfig.json` | CalibrationStore → measureMacro |
| Confusion matrix | `CalibrationStore` | `calibration.json` | `measureConfig.json` | CalibrationStore → measureMacro |
| Integration weight labels | `measureMacro` | `measureConfig.json` | — | — |
| Demod function/args | `measureMacro` | `measureConfig.json` | — | — |
| Pulse operation binding | `measureMacro` | `measureConfig.json` | — | — |
| Drive frequency | `CalibrationStore` | `calibration.json` | `measureConfig.json`, `cqed_params.json` | CalibrationStore → measureMacro |
| Post-selection config | `measureMacro` | `measureConfig.json` | — | — |

### 22.2 Persistence Boundaries

**Where `measureConfig.json` must be written:**

| Site | Method | Trigger |
|------|--------|---------|
| `SessionManager.override_readout_operation()` | `measureMacro.save_json()` | Explicit user action |
| `CalibrationOrchestrator.apply_patch()` | `PersistMeasureConfig` op | Orchestrator-driven |
| `SessionManager.close()` | `measureMacro.save_json()` | Session teardown (v1.4.0) |

**Where `measureConfig.json` must NOT be written:**

| Site | Why |
|------|-----|
| `ExperimentBase.analyze()` | Violates idempotency contract |
| `cQED_programs.*()` | Program factories must be side-effect-free |

**Where `calibration.json` is written:**

Only via `CalibrationStore.save()`, triggered by:
- `CalibrationOrchestrator.apply_patch()` (line 217)
- `guarded_calibration_commit()` Phase B (experiment_base.py)
- `SessionManager.close()` (line 599)
- Direct `CalibrationStore.save()` call (when `auto_save=True`)

### 22.3 Dual-Truth Resolution Status

| Pair | Status | Resolution |
|------|--------|------------|
| `calibration.json` ↔ `measureConfig.json` (discrimination) | **Resolved** in v1.4.0 | `sync_from_calibration()`: CalibrationStore → measureMacro on session open + after each patch commit |
| `calibration.json` ↔ `measureConfig.json` (quality) | **Resolved** in v1.4.0 | Same |
| `calibration.json` ↔ `cqed_params.json` (frequencies) | **Partially resolved** | `cqed_params.json` is read-only in v2; `calibration.json` is canonical |

### 22.4 Macro System Audit Documents

The following audit documents provide detailed analysis of the macro system:

| Document | Path | Content |
|----------|------|---------|
| Architecture Summary | `docs/audit/MACRO_PROGRAM_ARCHITECTURE.md` | Data model, public methods, program families, data flow |
| Entanglement Report | `docs/audit/MACRO_ENTANGLEMENT_REPORT.md` | Specific coupling points with file paths and line numbers |
| Refactor Proposal | `docs/audit/MACRO_REFACTOR_PROPOSAL.md` | Modularization plan, clean interfaces, 4-phase migration |

---

## 23. Writing Custom Experiments

This section is a guide for users who want to write their own experiment
classes beyond the built-in experiments provided by the API.

### 23.1 Architecture Overview

Every experiment in `qubox_v2` inherits from `ExperimentBase` and follows
a four-method contract:

```
build_program(**params)  →  QUA program
run(**params)            →  RunResult
analyze(result, ...)     →  AnalysisResult
plot(analysis, ...)      →  Figure
```

The experiment class is a **thin wrapper** around:

1. A **QUA program builder** — generates the quantum program to execute.
2. A **post-processor** — extracts and fits the returned data.
3. A **plotter** — visualizes results.

The `ExperimentBase` base class provides infrastructure accessors
(`self.attr`, `self.pulse_mgr`, `self.hw`, `self.measure_macro`,
`self.calibration_store`) so that custom experiments have direct access
to the session without needing to reimplement session wiring.

### 23.2 Minimal Custom Experiment (Step-by-Step)

Below is a complete example of a custom experiment that performs a Ramsey
experiment with a parametric detuning sweep.  This demonstrates the full
lifecycle from class definition through execution and analysis.

**Step 1 — Define the class:**

```python
from __future__ import annotations
from typing import Any
import numpy as np
from qm.qua import *

from qubox_v2.experiments.experiment_base import ExperimentBase, create_clks_array
from qubox_v2.experiments.result import AnalysisResult, FitResult
from qubox_v2.hardware.program_runner import RunResult
from qubox_v2.analysis import post_process as pp


class CustomDetuningRamsey(ExperimentBase):
    """Ramsey experiment with a parametric detuning sweep.

    Measures T2* and detuning-dependent dephasing by varying the qubit
    detuning across a range while performing a Ramsey sequence at a
    fixed free-evolution time.
    """

    def build_program(
        self,
        *,
        x90_op: str = "x90",
        detune_list: np.ndarray,
        wait_clks: int = 100,
        n_avg: int = 1000,
    ) -> Any:
        """Build the QUA program.

        Parameters
        ----------
        x90_op : str
            Name of the pi/2 pulse operation (must already be registered).
        detune_list : np.ndarray
            Array of IF detunings in Hz.
        wait_clks : int
            Free-evolution time in clock cycles (4 ns each).
        n_avg : int
            Number of averages per detuning point.
        """
        ro_el = self.attr.ro_el
        qb_el = self.attr.qb_el
        mm = self.measure_macro

        with program() as prog:
            n = declare(int)
            detune = declare(int)
            I = declare(fixed)
            Q = declare(fixed)
            state = declare(bool)
            I_stream = declare_stream()
            Q_stream = declare_stream()
            state_stream = declare_stream()

            with for_(n, 0, n < n_avg, n + 1):
                with for_each_(detune, detune_list.astype(int).tolist()):
                    # Set detuning
                    update_frequency(qb_el, detune)

                    # Ramsey sequence: X90 — wait — X90
                    play(x90_op, qb_el)
                    wait(wait_clks, qb_el)
                    play(x90_op, qb_el)

                    # Align and measure
                    align(qb_el, ro_el)
                    mm.measure(I=I, Q=Q, state=state)

                    save(I, I_stream)
                    save(Q, Q_stream)
                    save(state, state_stream)

            with stream_processing():
                I_stream.buffer(len(detune_list)).average().save("I")
                Q_stream.buffer(len(detune_list)).average().save("Q")
                state_stream.boolean_to_int().buffer(
                    len(detune_list)
                ).average().save("state")

        return prog

    def run(
        self,
        *,
        x90_op: str = "x90",
        detune_list: np.ndarray,
        wait_clks: int = 100,
        n_avg: int = 1000,
    ) -> RunResult:
        """Build and execute the detuning Ramsey program.

        Returns
        -------
        RunResult
            Raw data with keys 'I', 'Q', 'state'.
        """
        self.set_standard_frequencies()
        self.burn_pulses()

        prog = self.build_program(
            x90_op=x90_op,
            detune_list=detune_list,
            wait_clks=wait_clks,
            n_avg=n_avg,
        )

        result = self.run_program(prog, n_total=n_avg)
        # Stash sweep params for analyze()
        result.metadata["detune_list"] = detune_list
        result.metadata["wait_clks"] = wait_clks
        return result

    def analyze(
        self,
        result: RunResult,
        *,
        update_calibration: bool = False,
        **kw,
    ) -> AnalysisResult:
        """Analyze the detuning Ramsey data.

        Extracts the detuning-dependent Ramsey fringe and optionally fits
        to a sinusoidal decay.

        Returns
        -------
        AnalysisResult
            Contains 'detune_list', 'state', 'I', 'Q' in data,
            and 'visibility' in metrics.
        """
        detune_list = result.metadata["detune_list"]
        state = np.array(result.output["state"])
        I_data = np.array(result.output["I"])
        Q_data = np.array(result.output["Q"])

        # Compute visibility
        visibility = float(np.max(state) - np.min(state))

        # Optional: fit a Lorentzian to the fringe envelope
        fit = None
        try:
            from scipy.optimize import curve_fit

            def lorentzian(x, a, x0, gamma, offset):
                return a / (1 + ((x - x0) / gamma) ** 2) + offset

            p0 = [visibility, np.mean(detune_list), 1e6, 0.5]
            popt, pcov = curve_fit(lorentzian, detune_list, state, p0=p0)
            perr = np.sqrt(np.diag(pcov))
            fit = FitResult(
                model_name="lorentzian",
                params=dict(zip(["a", "x0", "gamma", "offset"], popt)),
                uncertainties=dict(zip(["a", "x0", "gamma", "offset"], perr)),
            )
        except Exception:
            pass

        return AnalysisResult(
            data={
                "detune_list": detune_list,
                "state": state,
                "I": I_data,
                "Q": Q_data,
            },
            fit=fit,
            metrics={"visibility": visibility},
            source=result,
        )

    def plot(self, analysis: AnalysisResult, *, ax=None, **kw):
        """Plot the detuning Ramsey fringe."""
        import matplotlib.pyplot as plt

        if ax is None:
            fig, ax = plt.subplots()
        else:
            fig = ax.figure

        detune = analysis.data["detune_list"]
        state = analysis.data["state"]
        ax.plot(detune / 1e6, state, "o-", label="Data")

        if analysis.fit is not None:
            x_fit = np.linspace(detune.min(), detune.max(), 500)

            def lorentzian(x, a, x0, gamma, offset):
                return a / (1 + ((x - x0) / gamma) ** 2) + offset

            p = analysis.fit.params
            y_fit = lorentzian(
                x_fit, p["a"], p["x0"], p["gamma"], p["offset"]
            )
            ax.plot(x_fit / 1e6, y_fit, "-r", label="Fit")

        ax.set_xlabel("Detuning (MHz)")
        ax.set_ylabel("P(e)")
        ax.set_title(f"Detuning Ramsey — visibility={analysis.metrics['visibility']:.3f}")
        ax.legend()
        return fig
```

**Step 2 — Use it in a notebook:**

```python
# Prerequisites: session is open, x90 pulse is registered
ramsey = CustomDetuningRamsey(session)

result = ramsey.run(
    x90_op="x90",
    detune_list=np.linspace(-5e6, 5e6, 101),
    wait_clks=250,    # 1 us free evolution
    n_avg=2000,
)

analysis = ramsey.analyze(result)
ramsey.plot(analysis)
print(f"Visibility = {analysis.metrics['visibility']:.3f}")
```

### 23.3 Contract Rules Your Experiment Must Follow

1. **Constructor (`__init__`)**: Must accept `ctx` (the session) and call
   `super().__init__(ctx)`.  Must **not** register or modify any pulses.

2. **`run()`**:
   - Must call `self.set_standard_frequencies()` before building the program.
   - Must call `self.burn_pulses()` if any new ops were registered in the
     notebook before this experiment.
   - Must return `RunResult` from `self.run_program(...)`.
   - Must **not** write calibration values or contact external instruments
     beyond what the hardware runner does.
   - Stash sweep metadata in `result.metadata` for `analyze()` to use.

3. **`analyze()`**:
   - Must be **idempotent** — same input → same output.
   - Must **not** contact hardware.
   - Must return `AnalysisResult` with at minimum `data` and `metrics`.
   - If `update_calibration=True`, use `self.guarded_calibration_commit()`
     for safe two-phase persistence.

4. **`plot()`**:
   - Must accept `AnalysisResult` and an optional `ax` kwarg.
   - Must create a figure if `ax=None`.
   - Must return `Figure`.

5. **Naming**: By convention, use `self.name` (auto-derived from the class
   name) for logging and artifact tagging.

### 23.4 Using `measureMacro` in Custom Programs

The `measureMacro` singleton emits the QUA `measure` + `assign` block.
All custom experiments should use it instead of raw QUA `measure()`:

```python
from qubox_v2.programs.macros.measure import measureMacro

mm = self.measure_macro  # Shortcut property from ExperimentBase

# Inside a QUA program block:
with program() as prog:
    I = declare(fixed)
    Q = declare(fixed)
    state = declare(bool)

    # Standard state-discriminated readout
    mm.measure(I=I, Q=Q, state=state)

    # Advanced: measure with specific targets
    mm.measure(
        I=I, Q=Q, state=state,
        targets=["resonator"],
        with_state=True,
    )
```

**Why use `measureMacro`?**  It automatically:
- Selects the correct readout element, operation, and weights.
- Applies the calibrated discrimination threshold and rotation angle.
- Handles demodulation strategy (sliced, full, accumulated).
- Manages the `wait_for_trigger` / active reset flow if configured.

### 23.5 Accessing Calibrated Parameters

Custom experiments often need calibrated values for sweep ranges, initial
guesses, or reference amplitudes:

```python
class MyExperiment(ExperimentBase):
    def run(self, **kw):
        # Readout parameters
        ro_el = self.attr.ro_el        # resonator element name
        ro_fq = self.attr.ro_fq        # calibrated resonator frequency
        ro_lo = self.get_readout_lo()   # LO frequency

        # Qubit parameters
        qb_el = self.attr.qb_el        # qubit element name
        qb_fq = self.attr.qb_fq        # calibrated qubit frequency
        qb_lo = self.get_qubit_lo()     # LO frequency

        # Thermalization clocks
        qb_therm = self.get_therm_clks("qubit", fallback=2500)
        ro_therm = self.get_therm_clks("readout", fallback=500)

        # Storage / cavity parameters (if applicable)
        st_el = self.attr.st_el        # storage element name
        st_fq = self.attr.st_fq        # storage frequency

        # Pulse calibrations from CalibrationStore
        cal = self.calibration_store
        if cal is not None:
            pi_amp = cal.get_pulse("ref_r180")
            if pi_amp:
                print(f"Pi amplitude = {pi_amp.amplitude}")

        # Confusion matrix for readout correction
        cm = self.get_confusion_matrix()
        if cm is not None:
            # Apply readout correction to measured populations
            corrected = np.linalg.solve(cm, raw_populations)
```

### 23.6 Writing a Custom Program Builder (Advanced)

For complex or reusable QUA programs, extract the program-generation logic
into a standalone builder function under `qubox_v2/programs/builders/`:

```python
# qubox_v2/programs/builders/my_custom.py
from qm.qua import *
from ..macros.measure import measureMacro

def custom_echo_train(
    qb_el: str,
    x180_op: str,
    x90_op: str,
    n_echoes: int,
    delay_clks_list: list[int],
    n_avg: int,
):
    """Build a Hahn-echo train with variable delay.

    Parameters
    ----------
    qb_el : str
        Qubit element name.
    x180_op, x90_op : str
        Registered operation names for pi and pi/2 pulses.
    n_echoes : int
        Number of echo refocusing pulses.
    delay_clks_list : list[int]
        Interpulse delay values (in clock cycles).
    n_avg : int
        Averaging count.

    Returns
    -------
    program
        The compiled QUA program.
    """
    mm = measureMacro

    with program() as prog:
        n = declare(int)
        delay = declare(int)
        echo_idx = declare(int)
        I = declare(fixed)
        Q = declare(fixed)
        state = declare(bool)
        I_st = declare_stream()
        Q_st = declare_stream()
        state_st = declare_stream()

        with for_(n, 0, n < n_avg, n + 1):
            with for_each_(delay, delay_clks_list):
                # X90
                play(x90_op, qb_el)

                # Echo train: (wait — X180) x n_echoes
                with for_(echo_idx, 0, echo_idx < n_echoes, echo_idx + 1):
                    wait(delay, qb_el)
                    play(x180_op, qb_el)

                # Final wait
                wait(delay, qb_el)

                # X90 (closing)
                play(x90_op, qb_el)

                # Measure
                align(qb_el, mm.active_element())
                mm.measure(I=I, Q=Q, state=state)
                save(I, I_st)
                save(Q, Q_st)
                save(state, state_st)

        with stream_processing():
            I_st.buffer(len(delay_clks_list)).average().save("I")
            Q_st.buffer(len(delay_clks_list)).average().save("Q")
            state_st.boolean_to_int().buffer(
                len(delay_clks_list)
            ).average().save("state")

    return prog
```

Then in your experiment class:

```python
from qubox_v2.programs.builders.my_custom import custom_echo_train

class EchoTrainExperiment(ExperimentBase):

    def build_program(self, *, n_echoes=1, delay_clks_list, n_avg=1000, **kw):
        return custom_echo_train(
            qb_el=self.attr.qb_el,
            x180_op="x180",
            x90_op="x90",
            n_echoes=n_echoes,
            delay_clks_list=delay_clks_list,
            n_avg=n_avg,
        )

    def run(self, *, n_echoes=1, delay_end=40000, dt=200, n_avg=1000, **kw):
        self.set_standard_frequencies()
        self.burn_pulses()
        clks = create_clks_array(0, delay_end, dt).tolist()
        prog = self.build_program(
            n_echoes=n_echoes, delay_clks_list=clks, n_avg=n_avg,
        )
        result = self.run_program(prog, n_total=n_avg)
        result.metadata["delay_clks"] = clks
        result.metadata["n_echoes"] = n_echoes
        return result

    def analyze(self, result, *, update_calibration=False, **kw):
        clks = result.metadata["delay_clks"]
        state = np.array(result.output["state"])
        times_us = np.array(clks) * 4e-3  # clks → us

        from scipy.optimize import curve_fit
        def decay(t, A, T, C):
            return A * np.exp(-t / T) + C

        popt, pcov = curve_fit(decay, times_us, state,
                               p0=[1.0, 20.0, 0.5])
        fit = FitResult(
            model_name="exp_decay",
            params=dict(zip(["A", "T2_echo_us", "C"], popt)),
            uncertainties=dict(zip(
                ["A", "T2_echo_us", "C"], np.sqrt(np.diag(pcov))
            )),
        )
        return AnalysisResult(
            data={"times_us": times_us, "state": state},
            fit=fit,
            metrics={"T2_echo_us": popt[1]},
            source=result,
        )
```

### 23.7 Calibration Commit from Custom Experiments

If your experiment produces a calibrated value (e.g., a corrected
frequency, g_pi amplitude, T2), use the two-phase commit:

```python
def analyze(self, result, *, update_calibration=False, **kw):
    # ... compute analysis ...

    if update_calibration:
        def apply_update():
            cal = self.calibration_store
            if cal is not None:
                # Write to the typed CalibrationStore
                cal.update_coherence(CoherenceParams(
                    T2_echo=analysis.metrics["T2_echo_us"] * 1e-6,
                ))
                cal.save()

        self.guarded_calibration_commit(
            analysis=analysis,
            run_result=result,
            calibration_tag="T2_echo_custom",
            apply_update=apply_update,
            require_fit=True,
            min_r2=0.8,
            required_metrics={
                "T2_echo_us": (0.1, 500.0),   # sanity bounds
            },
        )

    return analysis
```

The `guarded_calibration_commit()` method:
- **Phase A** (always): Saves a timestamped artifact under
  `artifacts/calibration_runs/`.
- **Phase B** (conditional): Calls `apply_update()` only if all validation
  gates pass (fit exists, R² meets threshold, metrics within bounds).

### 23.8 Using Gate Objects in Custom Experiments

For cavity QED or multi-qubit experiments, compose pulse sequences using
registered operations and explicit QUA primitives:

```python
class SNAPEchoExperiment(ExperimentBase):
    """Apply displacement/SNAP-style operations with an echo wait."""

    def run(self, *, alpha=1.0, snap_angles=None, wait_ns=1000, n_avg=1000):
        self.set_standard_frequencies()

        if snap_angles is None:
            snap_angles = [0.0, np.pi, 0.0]

        # Build QUA program using registered operations
        with program() as prog:
            n = declare(int)
            I = declare(fixed)
            Q = declare(fixed)
            state = declare(bool)
            I_st = declare_stream()
            state_st = declare_stream()

            with for_(n, 0, n < n_avg, n + 1):
                play("disp_plus", self.attr.st_el)
                play("snap_core", self.attr.qb_el)
                play("disp_minus", self.attr.st_el)
                wait(wait_ns // 4, self.attr.qb_el)
                align()
                self.measure_macro.measure(I=I, Q=Q, state=state)
                save(state, state_st)
                save(I, I_st)

            with stream_processing():
                state_st.boolean_to_int().average().save("state")
                I_st.average().save("I")

        result = self.run_program(prog, n_total=n_avg)
        result.metadata["alpha"] = alpha
        result.metadata["snap_angles"] = snap_angles
        return result
```

### 23.9 Complete Notebook Workflow Example

This puts all the pieces together — from session setup through custom
experiment execution — in a single notebook flow:

```python
# ── Cell 1: Imports ──
from pathlib import Path
import numpy as np
from qualang_tools.units import unit
from qubox_v2.devices import SampleRegistry
from qubox_v2.experiments.session import SessionManager
from qubox_v2.experiments import *
from qubox_v2.tools.generators import register_rotations_from_ref_iq
from qubox_v2.tools.waveforms import drag_gaussian_pulse_waveforms
u = unit()

# ── Cell 2: Session Setup ──
registry = SampleRegistry(Path("E:/qubox"))
session = SessionManager(
    sample_id="my_device",
    cooldown_id="cd_001",
    registry_base=Path("E:/qubox"),
    qop_ip="10.157.36.68",
    cluster_name="Cluster_2",
)
session.open()
attr = session.context_snapshot()

# ── Cell 3: Register Pulses ──
ref_I, ref_Q = drag_gaussian_pulse_waveforms(
    amplitude=attr.r180_amp,
    length=attr.r180_len,
    sigma=attr.r180_len / 5,
    alpha=attr.drag_coeff,
    anharmonicity=attr.anharmonicity,
)
register_rotations_from_ref_iq(
    session.pulse_mgr,
    ref_I=ref_I, ref_Q=ref_Q,
    element=attr.qb_el,
    rotations="all",
)
session.burn_pulses()

# ── Cell 4: Built-in Experiment ──
rabi = PowerRabi(session)
rabi_result = rabi.run(max_gain=1.2, dg=0.04, op="ref_r180", n_avg=5000)
rabi_analysis = rabi.analyze(rabi_result, update_calibration=True, p0=[0.0001, 1, 0])
rabi.plot(rabi_analysis)
print(f"g_pi = {rabi_analysis.metrics['g_pi']:.6f}")

# ── Cell 5: Custom Experiment ──
class MyRamseyDetuning(ExperimentBase):
    def build_program(self, *, freqs, wait_clks, n_avg):
        qb_el, ro_el = self.attr.qb_el, self.attr.ro_el
        mm = self.measure_macro
        with program() as prog:
            n = declare(int)
            f = declare(int)
            I, Q, state = declare(fixed), declare(fixed), declare(bool)
            I_st, state_st = declare_stream(), declare_stream()
            with for_(n, 0, n < n_avg, n + 1):
                with for_each_(f, freqs.astype(int).tolist()):
                    update_frequency(qb_el, f)
                    play("x90", qb_el)
                    wait(wait_clks, qb_el)
                    play("x90", qb_el)
                    align(qb_el, ro_el)
                    mm.measure(I=I, Q=Q, state=state)
                    save(I, I_st); save(state, state_st)
            with stream_processing():
                I_st.buffer(len(freqs)).average().save("I")
                state_st.boolean_to_int().buffer(len(freqs)).average().save("state")
        return prog

    def run(self, *, freqs, wait_clks=250, n_avg=2000):
        self.set_standard_frequencies()
        prog = self.build_program(freqs=freqs, wait_clks=wait_clks, n_avg=n_avg)
        result = self.run_program(prog, n_total=n_avg)
        result.metadata["freqs"] = freqs
        return result

    def analyze(self, result, **kw):
        freqs = result.metadata["freqs"]
        state = np.array(result.output["state"])
        return AnalysisResult(
            data={"freqs": freqs, "state": state},
            metrics={"visibility": float(np.ptp(state))},
            source=result,
        )

    def plot(self, analysis, *, ax=None, **kw):
        import matplotlib.pyplot as plt
        fig, ax = (ax.figure, ax) if ax else plt.subplots()
        ax.plot(analysis.data["freqs"] / 1e6, analysis.data["state"], "o-")
        ax.set(xlabel="Detuning (MHz)", ylabel="P(e)",
               title=f"Vis={analysis.metrics['visibility']:.3f}")
        return fig

ramsey = MyRamseyDetuning(session)
result = ramsey.run(freqs=np.linspace(-5e6, 5e6, 81), wait_clks=250, n_avg=2000)
analysis = ramsey.analyze(result)
ramsey.plot(analysis)

# ── Cell 6: Cleanup ──
session.close()
```

### 23.10 Tips and Best Practices

1. **Keep programs small.**  A QUA program should do one thing.  If your
   experiment needs multiple scans, run multiple programs sequentially.

2. **Use `create_clks_array()` and `create_if_frequencies()`** from
   `experiment_base` for proper grid snapping and IF boundary validation.

3. **Stash metadata in `result.metadata`** — sweep arrays, parameter
   choices, etc., so that `analyze()` can reconstruct context.

4. **Use `FitResult`** for structured fit storage — model name, parameter
   dictionary, uncertainties, and R² all feed into `guarded_calibration_commit()`
   validation gates.

5. **Never call `qm.execute()` directly.**  Always use
   `self.run_program(prog, n_total=...)` which handles SPA pump management,
   progress reporting, and metadata capture.

6. **Prefer `measureMacro.measure()`** over raw QUA `measure()`.  The macro
   handles element selection, demodulation weights, threshold rotation, and
   state discrimination in one call.

7. **Test with simulation first.**  Pass `process_in_sim=True` to
   `run_program()` to execute the program in the QM simulator without
   hardware:

   ```python
   result = self.run_program(prog, n_total=100, process_in_sim=True)
   ```

8. **Save artifacts** for traceability:

   ```python
   self.save_output(result.output, tag="my_experiment_v1")
   ```

9. **For multi-element alignment**, always call `align()` between
   operations on different elements.  QM executes element programs
   independently and `align()` is the synchronization barrier.

10. **Register pulses in the notebook, not in the experiment.**
    The experiment class should be pure logic; waveform creation belongs
    in the notebook cells before the experiment is constructed.

---

## 24. Binding-Driven API

*New in v2.0.0.*

The binding-driven API replaces the implicit element-name coupling that
previously permeated the codebase.  Physical channels (`ChannelRef`) are the
stable identity layer; human-friendly aliases map to physical channels, not
to QM element definitions.

**Module**: `qubox_v2.core.bindings`

### 24.1 Core Types

#### `ChannelRef`

Immutable identifier for a physical hardware port.

```python
@dataclass(frozen=True)
class ChannelRef:
    device: str          # controller or octave name
    port_type: str       # "analog_out", "analog_in", "RF_out", "RF_in", "digital_out"
    port_number: int
```

| Property | Type | Description |
|----------|------|-------------|
| `canonical_id` | `str` | Stable key `"{device}:{port_type}:{port_number}"` for calibration/artifact storage |

Examples:

```python
ChannelRef("con1", "analog_out", 3).canonical_id  # "con1:analog_out:3"
ChannelRef("oct1", "RF_out", 1).canonical_id       # "oct1:RF_out:1"
ChannelRef("con1", "analog_in", 1).canonical_id    # "con1:analog_in:1"
```

#### `OutputBinding`

A bound control output channel.

```python
@dataclass
class OutputBinding:
    channel: ChannelRef
    intermediate_frequency: float = 0.0
    lo_frequency: float | None = None
    gain: float | None = None
    digital_inputs: dict[str, ChannelRef] = field(default_factory=dict)
    operations: dict[str, str] = field(default_factory=dict)
```

#### `InputBinding`

A bound acquisition input channel.

```python
@dataclass
class InputBinding:
    channel: ChannelRef
    lo_frequency: float | None = None
    time_of_flight: int = 24
    smearing: int = 0
    weight_keys: list[list[str]] = field(
        default_factory=lambda: [["cos", "sin"], ["minus_sin", "cos"]]
    )
    weight_length: int | None = None
```

#### `ReadoutBinding`

Paired output + input for readout/measurement.  Encapsulates everything
`measure_with_binding()` needs: the drive output, the acquisition input,
and all DSP configuration.

```python
@dataclass
class ReadoutBinding:
    drive_out: OutputBinding
    acquire_in: InputBinding
    pulse_op: Any = None          # PulseOp | None
    active_op: str | None = None  # QUA operation handle
    demod_weight_sets: list[list[str]] = ...
    discrimination: dict[str, Any] = ...  # threshold, angle, fidelity, etc.
    quality: dict[str, Any] = ...         # F, Q, V, confusion_matrix, etc.
    drive_frequency: float | None = None
    gain: float | None = None
```

| Property | Type | Description |
|----------|------|-------------|
| `physical_id` | `str` | Canonical key for calibration storage (keyed to acquisition ADC) |
| `drive_channel_id` | `str` | Canonical key for the drive output |

| Method | Signature | Return | Description |
|--------|-----------|--------|-------------|
| `sync_from_calibration` | `(cal_store) -> None` | `None` | One-way sync: CalibrationStore → ReadoutBinding discrimination + quality dicts |

#### `ExperimentBindings`

Named collection of bindings passed to experiments.

```python
@dataclass
class ExperimentBindings:
    qubit: OutputBinding
    readout: ReadoutBinding
    storage: OutputBinding | None = None
    extras: dict[str, OutputBinding | ReadoutBinding] = field(default_factory=dict)
```

#### `AliasMap`

```python
AliasMap = dict[str, ChannelRef]
```

Mapping from human-friendly alias (e.g. `"qubit"`) to physical `ChannelRef`.

### 24.2 `ConfigBuilder`

Synthesizes ephemeral QM element dicts from bindings at compile time.  This
is the ONLY place where element dicts should be created from bindings.

```python
class ConfigBuilder:
    _QB_NAME = "__qb"
    _RO_NAME = "__ro"
    _ST_NAME = "__st"
```

| Method | Signature | Return | Description |
|--------|-----------|--------|-------------|
| `build_element` | `(name, binding) -> dict` | element dict | Build a single QM element from a binding |
| `build_elements` | `(bindings: ExperimentBindings) -> dict[str, dict]` | elements dict | Build a complete elements dict from a bindings bundle |
| `ephemeral_names` | `(bindings: ExperimentBindings) -> dict[str, str]` | name map | Return `{"qubit": "__qb", "readout": "__ro", ...}` |

### 24.3 Factory Functions

| Function | Signature | Return | Description |
|----------|-----------|--------|-------------|
| `bindings_from_hardware_config` | `(hw: HardwareConfig, attr: cQED_attributes) -> ExperimentBindings` | `ExperimentBindings` | Backward-compatible: derive bindings from existing hardware.json + cqed_params |
| `build_alias_map` | `(hw: HardwareConfig, attr: cQED_attributes) -> AliasMap` | `AliasMap` | Build element-name → ChannelRef mapping |
| `validate_binding` | `(binding, hw=None) -> list[str]` | error strings | Check consistency (e.g. drive/acquire on same octave, LO match) |

### 24.4 `measure_with_binding()`

**Module**: `qubox_v2.programs.macros.measure`

A binding-aware free function that replaces the `measureMacro.measure()`
singleton for new binding-driven code.

```python
def measure_with_binding(
    ro: ReadoutBinding,
    *,
    I: Any,
    Q: Any,
    state: Any | None = None,
    demod_fn: str = "dual_demod.full",
    **kwargs,
) -> None:
    """Emit a QUA measure() statement from a ReadoutBinding.

    This is the binding-aware replacement for measureMacro.measure().
    Must be called inside a `with program()` block.
    """
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `ro` | `ReadoutBinding` | The readout binding to measure |
| `I`, `Q` | QUA variables | I/Q demod result variables |
| `state` | QUA variable \| None | State discrimination result (optional) |
| `demod_fn` | `str` | Demodulation function name |

### 24.5 Session Integration

The `SessionManager.bindings` property is the primary entry point for the
binding-driven API.  It is **lazily computed** on first access and cached.

```python
# Access bindings from session
b = session.bindings            # ExperimentBindings
qb_id = b.qubit.channel.canonical_id  # e.g. "oct1:RF_out:3"
ro_id = b.readout.physical_id          # e.g. "oct1:RF_in:1"

# Invalidate and recompute (e.g. after hardware config change)
session.invalidate_bindings()
```

On first access, `SessionManager.bindings`:

1. Calls `bindings_from_hardware_config(hw, attr)` to derive bindings.
2. Calls `readout.sync_from_calibration(cal_store)` to populate
   discrimination/quality state from the canonical `CalibrationStore`.
3. Calls `_register_alias_index()` to register element-name → physical-ID
   mappings in the `CalibrationStore` alias index.

### 24.6 `ExperimentBase.bindings`

All experiments have access to bindings via the `.bindings` property:

```python
class ExperimentBase:
    @property
    def bindings(self) -> ExperimentBindings:
        """Access to binding bundle from session."""
```

### 24.7 Preflight Validation

The preflight system (check #8) validates bindings on session open:

```python
from qubox_v2.core.preflight import preflight_check

report = preflight_check(session)
# Validates:
# - Qubit OutputBinding channel type is RF_out or analog_out
# - ReadoutBinding drive/acquire on same device
# - ReadoutBinding LO frequency match
# - Storage binding (if present) consistency
```

### 24.8 CalibrationStore v5.0.0 Changes

The `CalibrationStore` now supports dual-lookup via `alias_index`:

- **Direct lookup**: key is a physical channel ID (e.g. `"oct1:RF_in:1"`).
- **Alias fallback**: if the direct key is not found, check `alias_index`
  for a mapping from the alias (e.g. `"resonator"` → `"oct1:RF_in:1"`).
- The alias index is populated automatically by `SessionManager.bindings`.
- All `get_*` / `set_*` methods on `CalibrationStore` pass through
  `_resolve_key()` which handles both lookup paths transparently.

### 24.9 Sequence Macro Integration

Sequence macros in `programs/macros/sequence.py` accept an optional
`bindings` parameter (v2.0.0).  When provided, element names are resolved
from the bindings via `ConfigBuilder.ephemeral_names()`:

```python
from qubox_v2.programs.macros.sequence import sequenceMacros

# With explicit bindings
sequenceMacros.qubit_state_tomography(
    ..., bindings=session.bindings,
)

# Without bindings (legacy — uses default element names)
sequenceMacros.qubit_state_tomography(...)
```

Updated methods: `qubit_state_tomography`, `num_splitting_spectroscopy`,
`fock_resolved_spectroscopy`, `prepare_state`.

### 24.10 `PulseRegistry` Changes

The `PulseRegistry` `_RESERVED_OPS` set is now `frozenset()` (empty).  The
wildcard readout operation previously auto-mapped to all elements has been
removed.  Readout operations must be explicitly registered via bindings or
the standard `PulseOperationManager` API.

### 24.11 Migration from Legacy Element-Name API

The binding-driven API is backward-compatible.  Existing code that uses
element names (e.g. `"qubit"`, `"resonator"`) continues to work because:

1. `bindings_from_hardware_config()` derives bindings from the same
   `hardware.json` + `cqed_params.json` files.
2. `CalibrationStore` dual-lookup resolves element-name keys via
   `alias_index`.
3. `measureMacro` remains available for legacy program builders.
4. Sequence macros default to legacy behavior when `bindings=None`.

**Recommended migration path:**

```python
# Before (v1.x — implicit element names):
ro_el = attr.ro_el              # "resonator"
cal.get_discrimination(ro_el)   # keyed by element name

# After (v2.0 — explicit bindings):
b = session.bindings
ro_id = b.readout.physical_id   # "oct1:RF_in:1"
cal.get_discrimination(ro_id)   # keyed by physical channel ID
# OR: cal.get_discrimination("resonator")  # still works via alias_index
```

### 24.12 `ReadoutConfig.from_binding()`

**Module**: `qubox_v2.experiments.calibration.readout_config`

The `ReadoutConfig` dataclass has a new classmethod for constructing a
readout config from a `ReadoutBinding`:

```python
@classmethod
def from_binding(cls, ro: ReadoutBinding, *, r180: str = "x180", **overrides) -> ReadoutConfig:
    """Construct a ReadoutConfig from a ReadoutBinding.

    Derives ro_el, measure_op, drive_frequency from the binding's
    physical channel ID and active operation.
    """
```

### 24.13 `cQED_attributes.to_bindings()`

**Module**: `qubox_v2.analysis.cQED_attributes`

Convenience method to derive bindings directly from physics attributes:

```python
attr = session.context_snapshot()
bindings = attr.to_bindings(session.config_engine.hardware)
```

---

## 25. Roleless Experiment Primitives (v2.1)

> **Module**: `qubox_v2.core.bindings`, `qubox_v2.experiments.session`,
> `qubox_v2.experiments.configs`, `qubox_v2.programs.macros.measure`

The v2.1 API introduces **frozen, role-free types** that decouple experiment
code from the mutable `ExperimentBindings` role vocabulary.  Experiments
type-check for generic `DriveTarget` and `ReadoutHandle` — never
for "qubit" or "storage" specifically.

### 25.1 Design Principles

1. **No role vocabulary** — `DriveTarget` describes any control output
   (qubit, storage, pump) with the same type.
2. **Frozen/immutable** — all dataclasses use `@dataclass(frozen=True)`.
   No snapshot/restore lifecycle needed.
3. **Pure functions** — `emit_measurement()` replaces `measureMacro.measure()`
   with no class-level state.
4. **Typed configs** — per-experiment `*Config` dataclasses capture physics
   parameters as immutable snapshots.

### 25.2 `DriveTarget`

**Module**: `qubox_v2.core.bindings`

Frozen dataclass for a single control output channel.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `element` | `str` | — | QM element name (ephemeral at runtime) |
| `lo_freq` | `float` | — | LO frequency in Hz |
| `rf_freq` | `float` | — | Target RF frequency in Hz |
| `therm_clks` | `int` | `250_000` | Thermalization wait in clock cycles |

**Properties:**

| Name | Returns | Description |
|------|---------|-------------|
| `if_freq` | `float` | `rf_freq - lo_freq` |

**Class methods:**

```python
@classmethod
def from_output_binding(
    cls,
    binding: OutputBinding,
    *,
    element: str,
    rf_freq: float | None = None,
    therm_clks: int | None = None,
) -> DriveTarget:
    """Construct from an OutputBinding."""
```

### 25.3 `ReadoutCal`

**Module**: `qubox_v2.core.bindings`

Frozen calibration artifact snapshot.  Contains all tunable parameters from
readout calibration (thresholds, weights, confusion matrices).  Physical
wiring identity lives in `ReadoutBinding`, not here.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `drive_frequency` | `float` | — | RF drive frequency in Hz |
| `demod_method` | `str` | `"dual_demod.full"` | Demodulation method |
| `weight_keys` | `tuple[str, ...]` | `("cos", "sin", "minus_sin")` | Integration weight keys |
| `threshold` | `float \| None` | `None` | Discrimination threshold |
| `rotation_angle` | `float \| None` | `None` | IQ rotation angle |
| `confusion_matrix` | `tuple[tuple[float,...],...]  \| None` | `None` | Readout confusion matrix |
| `fidelity` | `float \| None` | `None` | Readout assignment fidelity |

**Class methods:**

```python
@classmethod
def from_calibration_store(
    cls, store, physical_id: str, *, drive_freq: float,
) -> ReadoutCal:
    """Build from CalibrationStore using physical channel ID."""

@classmethod
def from_readout_binding(
    cls, rb: ReadoutBinding, *, drive_freq: float | None = None,
) -> ReadoutCal:
    """Build from a ReadoutBinding with sensible defaults."""
```

**Instance methods:**

```python
def with_discrimination(
    self, *, threshold: float, rotation_angle: float,
) -> ReadoutCal:
    """Return a copy with updated discrimination parameters."""
```

### 25.4 `ReadoutHandle`

**Module**: `qubox_v2.core.bindings`

Frozen dataclass combining physical identity (`ReadoutBinding`) with
calibration artifacts (`ReadoutCal`).  Experiments type-check for this type.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `binding` | `ReadoutBinding` | — | Physical wiring |
| `cal` | `ReadoutCal` | — | Calibration artifacts |
| `element` | `str` | — | QM element name |
| `operation` | `str` | `"readout"` | Pulse operation |

### 25.5 `ElementFreq`

**Module**: `qubox_v2.core.bindings`

Frozen dataclass for the resolved frequency of one element.

| Field | Type | Description |
|-------|------|-------------|
| `element` | `str` | QM element name |
| `rf_freq` | `float` | Target RF frequency in Hz |
| `lo_freq` | `float` | LO frequency in Hz |
| `if_freq` | `float` | Intermediate frequency in Hz |
| `source` | `str` | Provenance tag: `"explicit"`, `"calibration"`, or `"sample_default"` |

**Class methods:**

```python
@classmethod
def from_drive_target(cls, dt: DriveTarget) -> ElementFreq:
    """Construct from a DriveTarget (source='explicit')."""

@classmethod
def from_readout_handle(cls, rh: ReadoutHandle) -> ElementFreq:
    """Construct from a ReadoutHandle (source='explicit')."""
```

### 25.6 `FrequencyPlan`

**Module**: `qubox_v2.core.bindings`

Immutable frequency configuration for one experiment run.  Computed once at
`run()` entry, applied atomically before program execution, and recorded in
`RunResult` metadata for reproducibility.

| Field | Type | Description |
|-------|------|-------------|
| `entries` | `tuple[ElementFreq, ...]` | One entry per element |

**Instance methods:**

```python
def get(self, element: str) -> ElementFreq:
    """Look up the frequency entry for *element*. Raises KeyError."""

def to_metadata(self) -> dict[str, dict[str, Any]]:
    """Serialize for RunResult provenance recording."""

def apply(self, hw) -> None:
    """Set IF frequencies on QM hardware.  Called once, atomically."""
```

**Class methods:**

```python
@classmethod
def from_targets(
    cls,
    *,
    drive: DriveTarget | None = None,
    readout: ReadoutHandle | None = None,
    storage: DriveTarget | None = None,
    extras: dict[str, DriveTarget] | None = None,
) -> FrequencyPlan:
    """Build a FrequencyPlan from roleless primitives."""
```

### 25.7 `emit_measurement()`

**Module**: `qubox_v2.programs.macros.measure`

Pure function replacement for `measureMacro.measure()`.  Takes a
`ReadoutHandle`, builds demod statements from `cal.weight_keys`, returns
QUA variables.

```python
def emit_measurement(
    readout: ReadoutHandle,
    *,
    targets: list | None = None,
    state: Any | None = None,
    gain: float | None = None,
    timestamp_stream: Any | None = None,
    adc_stream: Any | None = None,
) -> tuple:
    """Emit a QUA measure() statement using a ReadoutHandle.

    Returns (I, Q) when state is None; (I, Q, state) otherwise.
    """
```

**Key differences from `measureMacro.measure()`:**

| Aspect | `measureMacro.measure()` | `emit_measurement()` |
|--------|--------------------------|----------------------|
| State | Class-level singleton | Pure function |
| Configuration | Mutable `_ro_disc_params` | Immutable `ReadoutHandle.cal` |
| Lifecycle | snapshot/restore needed | No lifecycle |
| Weights | Resolved at call time | From `cal.weight_keys` |

### 25.8 Session Factory Methods

**Module**: `qubox_v2.experiments.session.SessionManager`

Ergonomic methods that resolve hardware aliases into v2.1 primitives.

```python
def drive_target(
    self, alias: str, *, rf_freq: float | None = None,
    therm_clks: int | None = None,
) -> DriveTarget:
    """Resolve alias to a DriveTarget from hardware config + calibration."""

def readout_handle(
    self, alias: str = "resonator", operation: str = "readout",
) -> ReadoutHandle:
    """Resolve alias to a ReadoutHandle from hardware config + calibration."""

# Ergonomic shortcuts
def qubit(self, alias="qubit", **kw) -> DriveTarget: ...
def storage(self, alias="storage", **kw) -> DriveTarget: ...
def readout(self, alias="resonator", **kw) -> ReadoutHandle: ...
```

**Resolution order for `drive_target()`:**

1. RF frequency: `rf_freq` kwarg > calibration store > `attr.<alias>_fq`
2. LO frequency: from `OutputBinding.lo_frequency`
3. Thermalization: `therm_clks` kwarg > `attr.<alias>_therm_clks` > 250,000

### 25.9 Per-Experiment Config Dataclasses

**Module**: `qubox_v2.experiments.configs`

All are frozen dataclasses with sensible defaults.  Compose with
`dataclasses.replace()` for parameter sweeps.

#### Time-domain configs

| Config | Key Fields |
|--------|------------|
| `PowerRabiConfig` | `op`, `max_gain`, `dg`, `n_avg`, `length`, `truncate_clks` |
| `TemporalRabiConfig` | `pulse`, `pulse_len_begin`, `pulse_len_end`, `dt`, `pulse_gain`, `n_avg` |
| `T1RelaxationConfig` | `delay_end`, `dt`, `n_avg`, `clock_period_ns`, `derive_therm_clks` |
| `T2RamseyConfig` | `qb_detune`, `delay_end`, `dt`, `n_avg`, `apply_frequency_correction`, `freq_correction_sign` |
| `T2EchoConfig` | `delay_end`, `dt`, `n_avg` |

#### Spectroscopy configs

| Config | Key Fields |
|--------|------------|
| `ResonatorSpectroscopyConfig` | `rf_begin`, `rf_end`, `df`, `n_avg`, `readout_op` |
| `QubitSpectroscopyConfig` | `pulse`, `rf_begin`, `rf_end`, `df`, `qb_gain`, `qb_len`, `n_avg` |
| `StorageSpectroscopyConfig` | `disp`, `rf_begin`, `rf_end`, `df`, `storage_therm_time`, `sel_r180`, `n_avg` |

**Usage pattern:**

```python
from qubox_v2.experiments.configs import PowerRabiConfig
from dataclasses import replace

cfg = PowerRabiConfig(max_gain=0.4, n_avg=2000)
result = rabi.run(cfg, drive=qb, readout=ro)

# Parameter sweep via replace
for gain in [0.1, 0.2, 0.3]:
    result = rabi.run(replace(cfg, max_gain=gain), drive=qb, readout=ro)
```

### 25.10 Migration from v2.0 Bindings

| v2.0 (role-based) | v2.1 (roleless) |
|--------------------|-----------------|
| `bindings = session.bindings` | `qb = session.qubit()` |
| `qb_binding = bindings.qubit` | `qb = session.drive_target("qubit")` |
| `ro_binding = bindings.readout` | `ro = session.readout_handle()` |
| `measureMacro.measure(...)` | `emit_measurement(ro, ...)` |
| `session.hw.set_intermediate_frequency(...)` | `FrequencyPlan.from_targets(...).apply(hw)` |
| `run(gain=0.4, n_avg=2000, ...)` | `run(PowerRabiConfig(max_gain=0.4, n_avg=2000), ...)` |

The v2.0 binding API remains fully supported.  v2.1 types are additive —
no existing code needs to change.

---

## 26. Program Build & Simulation (v2.2)

> **Modules**: `qubox_v2.experiments.result`, `qubox_v2.experiments.experiment_base`,
> `qubox_v2.hardware.program_runner`

The v2.2 API adds first-class `build_program()` → `ProgramBuildResult` and
`simulate()` → `SimulationResult` support to all experiment classes, enabling
program introspection and offline waveform simulation without touching
hardware.

### 26.1 Design Principles

1. **Program-as-artifact** — `build_program()` returns an immutable
   `ProgramBuildResult` snapshot containing the QUA program, resolved
   parameters, frequency assignments, and provenance metadata.
2. **`run()` unchanged externally** — existing experiment `run()` calls
   continue to work identically.  Internally, `run()` delegates to
   `build_program()` then `run_program()`.
3. **`_build_impl()` is the subclass override point** — subclasses override
   `_build_impl(**params)` to return `ProgramBuildResult`.  The base class
   `build_program()` calls `_build_impl()` then applies
   `resolved_frequencies` to the hardware config.
4. **Pure resolvers** — `_resolve_readout_frequency()` and
   `_resolve_qubit_frequency(detune=)` compute frequencies without side
   effects, replacing the legacy `set_standard_frequencies()` + attribute
   pattern.

### 26.2 `ProgramBuildResult`

**Module**: `qubox_v2.experiments.result`
**Type**: `@dataclass(frozen=True)`

```python
@dataclass(frozen=True)
class ProgramBuildResult:
    # Core payload
    program: Any                          # QUA program object
    n_total: int                          # Shot count
    processors: tuple[Callable, ...] = () # Post-processing pipeline

    # Provenance
    experiment_name: str = ""
    params: dict[str, Any] = {}           # Resolved build parameters
    resolved_frequencies: dict[str, float] = {}  # {element: freq_hz}
    bindings_snapshot: dict[str, Any] | None = None

    # Optional metadata
    builder_function: str | None = None   # e.g. "cQED_programs.power_rabi"
    sweep_axes: dict[str, Any] | None = None
    measure_macro_state: dict[str, Any] | None = None
    timestamp: str = ""                   # ISO-8601
    run_program_kwargs: dict[str, Any] = {}  # Extra kwargs for run_program()
```

| Field | Type | Description |
|-------|------|-------------|
| `program` | QUA program | The compiled QUA program object |
| `n_total` | `int` | Total shot count for progress reporting |
| `processors` | `tuple[Callable, ...]` | Post-processing pipeline (immutable tuple) |
| `experiment_name` | `str` | Class name for artifact tagging |
| `params` | `dict` | Frozen copy of resolved build parameters |
| `resolved_frequencies` | `dict[str, float]` | Element → frequency (Hz) to apply before execution |
| `bindings_snapshot` | `dict \| None` | JSON-safe serialization of active bindings |
| `builder_function` | `str \| None` | Program factory function name |
| `sweep_axes` | `dict \| None` | Swept parameter arrays for provenance |
| `measure_macro_state` | `dict \| None` | measureMacro config snapshot at build time |
| `timestamp` | `str` | ISO-8601 build timestamp |
| `run_program_kwargs` | `dict` | Extra kwargs forwarded to `run_program()` |

### 26.3 `QuboxSimulationConfig`

**Module**: `qubox_v2.hardware.program_runner`
**Type**: `@dataclass`

```python
@dataclass
class QuboxSimulationConfig:
    duration_ns: int = 4000
    plot: bool = True
    plot_params: dict[str, Any] | None = None
    controllers: tuple[str, ...] = ("con1",)
    t_begin: float | None = None
    t_end: float | None = None
    compiler_options: Any = None
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `duration_ns` | `int` | `4000` | Simulation duration in nanoseconds |
| `plot` | `bool` | `True` | Auto-plot simulated waveforms |
| `plot_params` | `dict \| None` | `None` | Override default plot parameters |
| `controllers` | `tuple[str, ...]` | `("con1",)` | Controller names in plots |
| `t_begin` | `float \| None` | `None` | Plot time window start |
| `t_end` | `float \| None` | `None` | Plot time window end |
| `compiler_options` | `Any` | `None` | Forwarded to QM simulator |

### 26.4 `SimulationResult`

**Module**: `qubox_v2.experiments.result`
**Type**: `@dataclass`

```python
@dataclass
class SimulationResult:
    samples: Any                    # SimulatorSamples
    build: ProgramBuildResult       # Full build provenance
    config_snapshot: dict = {}      # QM config at sim time
    sim_config: Any = None          # QuboxSimulationConfig used
    duration_ns: int = 4000

    def analog_channels(self) -> dict[str, np.ndarray]:
        """Flatten all analog channels into {controller:name → array}."""
```

### 26.5 Base Class Methods

**Module**: `qubox_v2.experiments.experiment_base.ExperimentBase`

| Method | Signature | Return | Description |
|--------|-----------|--------|-------------|
| `build_program` | `(**params) -> ProgramBuildResult` | `ProgramBuildResult` | Calls `_build_impl()`, applies resolved frequencies |
| `_build_impl` | `(**params) -> ProgramBuildResult` | `ProgramBuildResult` | **Subclass override point** — returns program + metadata without side effects |
| `simulate` | `(sim_config=None, **params) -> SimulationResult` | `SimulationResult` | Calls `build_program()` then `runner.simulate()` |
| `_resolve_readout_frequency` | `() -> float` | `float` | Pure resolver: bindings → measureMacro → attributes |
| `_resolve_qubit_frequency` | `(detune=0.0) -> float` | `float` | Pure resolver: `get_qubit_frequency() + detune` |
| `_serialize_bindings` | `() -> dict \| None` | `dict \| None` | JSON-safe snapshot of active bindings |

### 26.6 Subclass Migration Pattern

Every experiment `run()` is refactored to delegate to `build_program()`:

```python
class PowerRabi(ExperimentBase):

    def _build_impl(self, max_gain=0.5, dg=0.01, op="ref_r180",
                    n_avg=1000, **kw) -> ProgramBuildResult:
        ro_fq = self._resolve_readout_frequency()
        qb_fq = self._resolve_qubit_frequency()
        # ... build QUA program ...
        return ProgramBuildResult(
            program=prog,
            n_total=n_avg,
            processors=(pp.proc_default, pp.proc_magnitude, ...),
            experiment_name="PowerRabi",
            params={"max_gain": max_gain, "dg": dg, "op": op, "n_avg": n_avg},
            resolved_frequencies={attr.ro_el: ro_fq, attr.qb_el: qb_fq},
            bindings_snapshot=self._serialize_bindings(),
            builder_function="cQED_programs.power_rabi",
        )

    def run(self, max_gain=0.5, dg=0.01, op="ref_r180",
            n_avg=1000, **kw) -> RunResult:
        build = self.build_program(
            max_gain=max_gain, dg=dg, op=op, n_avg=n_avg, **kw,
        )
        result = self.run_program(
            build.program, n_total=build.n_total,
            processors=list(build.processors),
        )
        self.save_output(result.output, "powerRabi")
        return result
```

**Key rules:**

- `_build_impl()` must not call `run_program()` or `set_standard_frequencies()`.
- Resolved frequencies go into `resolved_frequencies`; the base class applies them.
- Processors are stored as immutable tuples; converted to lists in `run()`.
- Non-serializable objects (callables, large arrays) are excluded from `params`.

### 26.7 measureMacro Context Pattern

Experiments that configure `measureMacro` (readout-based spectroscopy) add
a `_setup_measure_context()` helper and wrap both `build_program()` and
`simulate()`:

```python
class ResonatorSpectroscopy(ExperimentBase):

    def _setup_measure_context(self, readout_op: str):
        ro_info = self.pulse_mgr.get_pulseOp_by_element_op(
            self.attr.ro_el, readout_op,
        )
        weight_len = int(ro_info.length) if ro_info.length else None
        return measureMacro.using_defaults(
            pulse_op=ro_info, active_op=readout_op, weight_len=weight_len,
        )

    def run(self, readout_op, **kw) -> RunResult:
        with self._setup_measure_context(readout_op):
            build = self.build_program(readout_op=readout_op, **kw)
            result = self.run_program(build.program, ...)
        return result

    def simulate(self, sim_config=None, **params):
        readout_op = params.get("readout_op")
        with self._setup_measure_context(readout_op):
            return super().simulate(sim_config, **params)
```

### 26.8 Multi-Program Experiments

Three experiments iterate over multiple LO segments and cannot produce a
single `ProgramBuildResult`.  They override `_build_impl()` with an explicit
`NotImplementedError`:

| Experiment | Module | Reason |
|------------|--------|--------|
| `QubitSpectroscopyCoarse` | `spectroscopy/qubit.py` | Multi-LO segment loop |
| `ReadoutFrequencyOptimization` | `spectroscopy/resonator.py` | Multi-frequency discrimination loop |
| `StorageSpectroscopyCoarse` | `cavity/storage.py` | Multi-LO segment loop |

These experiments must be used via `run()` directly.

### 26.9 Usage Examples

**Build a program without executing it:**

```python
rabi = PowerRabi(session)
build = rabi.build_program(max_gain=0.5, dg=0.01, op="ref_r180", n_avg=1000)

# Inspect the build
print(f"Experiment: {build.experiment_name}")
print(f"Params: {build.params}")
print(f"Resolved frequencies: {build.resolved_frequencies}")
print(f"Builder: {build.builder_function}")
print(f"N_total: {build.n_total}")
print(f"Processors: {len(build.processors)}")
```

**Simulate without hardware:**

```python
from qubox_v2.hardware.program_runner import QuboxSimulationConfig

sim_cfg = QuboxSimulationConfig(duration_ns=10000, plot=True)
sim = rabi.simulate(sim_cfg, max_gain=0.5, dg=0.01, op="ref_r180", n_avg=100)

# Inspect simulated waveforms
channels = sim.analog_channels()
for name, arr in channels.items():
    print(f"{name}: {arr.shape}")
```

**Run normally (unchanged):**

```python
result = rabi.run(max_gain=0.5, dg=0.01, op="ref_r180", n_avg=5000)
```

### 26.10 Migration Status

All 26 experiment classes are migrated:

| Category | Experiments | Status |
|----------|-------------|--------|
| Spectroscopy | ResonatorSpectroscopy, ResonatorSpectroscopyX180, ReadoutTrace, ResonatorPowerSpectroscopy, QubitSpectroscopy, QubitSpectroscopyEF | `_build_impl()` |
| Time Domain | PowerRabi, TemporalRabi, SequentialQubitRotations, T1Relaxation, T2Ramsey, T2Echo, ResidualPhotonRamsey, TimeRabiChevron, PowerRabiChevron, RamseyChevron | `_build_impl()` |
| Cavity | StorageSpectroscopy, NumSplittingSpectroscopy, StorageRamsey, StorageChiRamsey, StoragePhaseEvolution, FockResolvedSpectroscopy, FockResolvedT1, FockResolvedRamsey, FockResolvedPowerRabi | `_build_impl()` |
| Multi-program | QubitSpectroscopyCoarse, ReadoutFrequencyOptimization, StorageSpectroscopyCoarse | `NotImplementedError` |

---

## 27. HardwareDefinition Builder (v2.3)

`qubox_v2.core.hardware_definition.HardwareDefinition` is the notebook-first
builder for generating all sample-level config files from Python code.

**Module:** `qubox_v2.core.hardware_definition`

### 27.1 Overview

`HardwareDefinition` generates three config files from a single Python
definition block:

| File | Builder method | Generated by |
|------|---------------|-------------|
| `hardware.json` | `to_hardware_dict()` / `save_hardware()` | `add_readout()`, `add_control()`, `set_external_lo()`, `set_adc_offsets()` |
| `cqed_params.json` | `to_cqed_seed()` / `save_cqed_params()` | `set_aliases()` + element frequencies |
| `devices.json` | `to_devices_dict()` / `save_devices()` | `set_instrument_server()`, `add_device()` |

When passed to `SessionManager.from_sample(..., hardware=hw_def)`, all three
files are written automatically via `_apply_hardware_definition()`.

### 27.2 Constructor

```python
HardwareDefinition(controller: str = "con1", octave: str = "oct1")
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `controller` | `str` | `"con1"` | OPX+ controller name |
| `octave` | `str` | `"oct1"` | Octave unit name |

### 27.3 Element Builder Methods

#### `add_readout()`

```python
def add_readout(
    self, name: str, *,
    rf_out: int, rf_in: int, lo_frequency: float,
    frequency: float | None = None,
    intermediate_frequency: float = -50e6,
    gain: float = 0.0,
    time_of_flight: int = 280,
    digital_inputs: dict[str, int | tuple[int, int, int]] | None = None,
    lo_source: Literal["internal", "external"] = "internal",
) -> HardwareDefinition
```

Adds a readout element (paired drive output + acquisition input).

#### `add_control()`

```python
def add_control(
    self, name: str, *,
    rf_out: int, lo_frequency: float,
    frequency: float | None = None,
    intermediate_frequency: float = -50e6,
    gain: float = 0.0,
    digital_inputs: dict[str, int | tuple[int, int, int]] | None = None,
    lo_source: Literal["internal", "external"] = "internal",
) -> HardwareDefinition
```

Adds a control-only element (drive output, no acquisition).

| Parameter | Description |
|-----------|-------------|
| `name` | Human-friendly element name |
| `rf_out` | Octave RF output port (1–5) |
| `rf_in` | Octave RF input port (readout only) |
| `lo_frequency` | LO frequency in Hz |
| `frequency` | Absolute RF frequency (IF = frequency − lo_frequency) |
| `intermediate_frequency` | Default IF when `frequency` not given (−50 MHz) |
| `gain` | Octave output gain in dB |
| `time_of_flight` | Time-of-flight in ns (readout only, default 280) |
| `digital_inputs` | Dict of digital input mappings: bare `int` port (uses delay=57, buffer=18) or `(port, delay, buffer)` tuple |
| `lo_source` | `"internal"` or `"external"` LO source |

### 27.4 Wiring & Alias Methods

#### `set_external_lo()`

```python
def set_external_lo(
    self, rf_out: int, *, device: str, lo_port: str
) -> HardwareDefinition
```

Registers an external LO device for an RF output port.

#### `set_aliases()`

```python
def set_aliases(
    self,
    aliases: dict[str, str] | None = None,
    **kwargs: str,
) -> HardwareDefinition
```

Maps human-friendly alias names to element names.  Accepts a dict,
keyword arguments, or both (merged, kwargs win).  Alias names are
arbitrary.

Well-known alias names are mapped to legacy `cqed_params.json` fields:

| Alias name | `cqed_params` field |
|------------|---------------------|
| `"qubit"` | `qb_el` / `qb_fq` |
| `"readout"` | `ro_el` / `ro_fq` |
| `"storage"` | `st_el` / `st_fq` |

All aliases (including custom ones) are also stored under the
`__aliases` key in `cqed_params.json` for forward-compatible readers.

#### `set_adc_offsets()`

```python
def set_adc_offsets(self, offsets: dict[int, float]) -> HardwareDefinition
```

Sets ADC analog input DC offsets (port number → volts).

### 27.5 Device Builder Methods

These methods generate `devices.json` for external instruments (LO
generators, spectrum analyzers, DC sources, etc.).

#### `set_instrument_server()`

```python
def set_instrument_server(
    self, host: str, port: int, timeout: int = 60000
) -> HardwareDefinition
```

Sets shared InstrumentServer connection defaults.  Devices added after
this call inherit these connection parameters unless `connect=` is
explicitly provided.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `host` | `str` | — | InstrumentServer hostname or IP |
| `port` | `int` | — | InstrumentServer port |
| `timeout` | `int` | `60000` | Connection timeout in ms |

#### `add_device()`

```python
def add_device(
    self, name: str, *,
    driver: str = "instrumentserver:Instrument",
    backend: str | None = None,
    connect: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
    enabled: bool = True,
    instrument_name: str | None = None,
) -> HardwareDefinition
```

Adds an external device definition.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | — | Device identifier |
| `driver` | `str` | `"instrumentserver:Instrument"` | Python class path `"module:ClassName"` |
| `backend` | `str \| None` | `None` | `"instrumentserver"` (auto when server set) or `"qcodes"` |
| `connect` | `dict \| None` | `None` | Connection parameters (auto-populated from shared server when `None`) |
| `settings` | `dict \| None` | `None` | Initial device settings applied on connect |
| `enabled` | `bool` | `True` | Include in `DeviceManager.instantiate_all()` |
| `instrument_name` | `str \| None` | `None` | Shorthand for `connect["instrument_name"]` (defaults to `name`) |

**Smart defaults** when `set_instrument_server()` has been called and
`connect=None`:
- `backend` → `"instrumentserver"`
- `connect` → `{host, port, timeout, instrument_name}` from shared server
- `instrument_name` → `name` if not explicitly provided

### 27.6 Generation & Persistence

| Method | Returns | Description |
|--------|---------|-------------|
| `to_hardware_dict()` | `dict` | Full `hardware.json` content (validates first) |
| `to_cqed_seed()` | `dict` | Seed `cqed_params.json` (element names + frequencies) |
| `to_devices_dict()` | `dict` | `devices.json` content (empty dict if no devices) |
| `save_hardware(path)` | `Path` | Write `hardware.json` |
| `save_cqed_params(path, merge_existing=True)` | `Path` | Write/merge `cqed_params.json` |
| `save_devices(path, merge_existing=True)` | `Path \| None` | Write/merge `devices.json`; returns `None` if no devices defined |

`save_devices(merge_existing=True)` preserves manually-added devices in an
existing file.  Devices with matching names are overwritten by the builder.

### 27.7 Validation

`validate()` returns a list of error strings (empty = valid):

| Check | Description |
|-------|-------------|
| 1 | Alias element names must exist |
| 2 | Readout alias target must use `add_readout()` with `rf_in` (only if `"readout"` alias set) |
| 3 | No duplicate RF output ports |
| 4 | RF output ports in range 1–5 |
| 5 | IF frequencies within ±400 MHz |
| 6 | External LO references must match element `lo_source` |
| 7 | LO frequencies must be positive |
| 8 | Digital input ports in range 1–10 |
| 9 | Cross-reference: `set_external_lo(device=X)` warns if `X` not defined via `add_device()` (warning only) |

### 27.8 Session Integration

When passed to `SessionManager.from_sample(..., hardware=hw_def)`, the
session calls `_apply_hardware_definition()` which:

1. Validates the definition
2. Writes `hardware.json` → sample config dir
3. Writes/merges `cqed_params.json` → sample config dir
4. Writes/merges `devices.json` → sample config dir (if devices defined)

### 27.9 Usage Example

```python
from qubox_v2.core.hardware_definition import HardwareDefinition

hw_def = HardwareDefinition(controller="con1", octave="oct1")

# ── Elements ──
hw_def.add_readout("resonator",
    rf_out=1, rf_in=1, lo_frequency=8.8e9,
    intermediate_frequency=-50e6, gain=-10, time_of_flight=280,
    digital_inputs={"switch": (1, 0, 0), "pump": (2, 114, 18)},
)
hw_def.add_control("transmon",
    rf_out=3, lo_frequency=6.2e9,
    intermediate_frequency=-50e6,
    digital_inputs={"switch": (3, 57, 18)},
)
hw_def.add_control("storage",
    rf_out=5, lo_frequency=5.4e9,
    intermediate_frequency=-50e6,
    digital_inputs={"switch": (5, 57, 18)},
)
hw_def.add_control("storage_gf",
    rf_out=4, lo_frequency=7.0e9,
    intermediate_frequency=-50e6, lo_source="external",
    digital_inputs={"switch": (2, 57, 18)},
)
hw_def.add_control("resonator_gf",
    rf_out=2, lo_frequency=3.5e9,
    intermediate_frequency=-50e6, lo_source="external",
    digital_inputs={"switch": (2, 57, 18)},
)

# ── External LO wiring ──
hw_def.set_external_lo(rf_out=2, device="octave_external_lo2", lo_port="LO2")
hw_def.set_external_lo(rf_out=4, device="octave_external_lo4", lo_port="LO4")

# ── Aliases & ADC offsets ──
hw_def.set_aliases(qubit="transmon", readout="resonator", storage="storage")
hw_def.set_adc_offsets({1: 0.00947713, 2: 0.00962465})

# ── External Devices (generates devices.json) ──
hw_def.set_instrument_server("10.157.36.75", 50183)

hw_def.add_device("octave_external_lo2", instrument_name="sc_34F3",
    settings={"frequency": 3.5e9, "power": 8.5, "output_status": True})
hw_def.add_device("octave_external_lo4", instrument_name="sc_38B5",
    settings={"frequency": 7.0e9, "power": 10.0, "output_status": True})
hw_def.add_device("octodac_bf", instrument_name="octodac_bf")
hw_def.add_device("sa124b", instrument_name="sa124b_20234880")

# ── Validate ──
errors = hw_def.validate()
if errors:
    raise RuntimeError(f"Validation failed: {errors}")

# Pass to session — all config files generated automatically
session = SessionManager.from_sample(..., hardware=hw_def)
```

---

## 28. Gate → Protocol → Circuit Architecture (v2.4)

> **Modules**: `qubox_v2.programs.circuit_runner`,
> `qubox_v2.programs.circuit_compiler`, `qubox_v2.programs.circuit_protocols`,
> `qubox_v2.programs.circuit_display`, `qubox_v2.programs.circuit_execution`,
> `qubox_v2.programs.circuit_postprocess`, `qubox_v2.programs.measurement`

The v2.4 API introduces a gate-driven circuit pipeline that sits alongside
the legacy program-builder flows.  Experiments are expressed as ordered
sequences of **intent gates** (`Gate`), grouped into a **`QuantumCircuit`**
with an explicit **`MeasurementSchema`**.  A protocol layer builds circuits
from high-level descriptions (Ramsey, Echo, Active Reset), and the v2
compiler lowers them to QUA programs.

### 28.1 Design Principles

1. **Single IR** — `Gate` is the sole intent gate; `QuantumCircuit` is the
   sole circuit type.  Aliases `IntentGate = Gate` and `Circuit =
   QuantumCircuit` exist for back-compat.
2. **IQ-only measurement** — `compile_v2` emits IQ acquisition at QUA
   program time.  State derivation is a post-run analysis step via
   `StateRule` + `derive_state()`, never baked into the QUA program.
3. **Protocol purity** — Protocol builders (`RamseyProtocol.build()`, etc.)
   are zero-side-effect factories that return fully-formed circuits.
4. **Cluster safety** — Only `Cluster_1` is accepted for execution.
   `Cluster_2` is rejected immediately.  Default mode is dry-run (compile +
   diagram only).
5. **Display honesty** — Analysis-only blocks render with `[analysis-only]`
   annotations.  Conditional gates that cannot compile to real-time QUA
   branches are documented honestly in diagrams and raise at compile time.

### 28.2 Canonical IR Types

**Module**: `qubox_v2.programs.circuit_runner`

#### `Gate`

```python
@dataclass(frozen=True)
class Gate:
    name: str
    target: str | tuple[str, ...]
    params: dict[str, Any] = field(default_factory=dict)
    duration_clks: int | None = None
    tags: tuple[str, ...] = ()
    instance_name: str | None = None
    condition: GateCondition | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

| Property | Return | Description |
|----------|--------|-------------|
| `gate_type` | `str` | Normalised name: `measure_iq` for any measure variant, `idle` for `wait`, else lowercase `name` |
| `targets` | `tuple[str, ...]` | Always-tuple form of `target` |
| `resolved_name(index)` | `str` | `instance_name` if set, else `f"{name}_{index}"` |

#### `QuantumCircuit`

```python
@dataclass(frozen=True)
class QuantumCircuit:
    name: str
    gates: tuple[Gate, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    measurement_schema: MeasurementSchema | None = None
    blocks: tuple[CircuitBlock, ...] = ()
```

| Method | Signature | Return |
|--------|-----------|--------|
| `with_stable_gate_names()` | `() -> QuantumCircuit` | Copy with `instance_name` set on every gate |
| `to_text()` | `() -> str` | Compact text listing |
| `lane_names()` | `() -> list[str]` | Unique targets in gate order |
| `to_diagram_text(cell_width=20)` | `() -> str` | Full ASCII diagram |
| `draw(…)` | `(figsize, save_path, include_gate_names) -> Figure` | Matplotlib timeline |
| `display(…)` | Same as `draw()` | Alias |
| `draw_logical(…)` | Same as `draw()` | Alias |
| `draw_pulses(runner)` | `(runner, **kw) -> Figure` | Delegates to `CircuitRunner.visualize_pulses()` |

#### `ParameterSource`

```python
@dataclass(frozen=True)
class ParameterSource:
    calibration: CalibrationReference | None = None
    override: Any = _UNSET
    attr_fallback: str | None = None
    default: Any = _UNSET
    required: bool = False
```

Resolution order: **override → calibration → cQED_attributes → default → error**.

#### `CalibrationReference`

```python
@dataclass(frozen=True)
class CalibrationReference:
    namespace: str   # "pulse_calibration", "cqed_params", "frequencies", etc.
    key: str         # Element or calibration key
    field: str       # Attribute name on the calibration object
```

#### `MeasurementSchema` & `MeasurementRecord`

```python
@dataclass(frozen=True)
class MeasurementRecord:
    key: str
    kind: str = "iq"
    operation: str = "readout"
    with_state: bool = False
    streams: tuple[StreamSpec, ...] = ()
    state_rule: StateRule | None = None
    derived_state_name: str = "state"

    def output_name(self, stream_name: str) -> str:
        return f"{self.key}.{stream_name}"

    def state_output_name(self) -> str:
        return f"{self.key}.{self.derived_state_name}"

@dataclass(frozen=True)
class MeasurementSchema:
    records: tuple[MeasurementRecord, ...] = ()

    def validate(self) -> MeasurementSchema  # raises ValueError on violations
    def to_payload(self) -> dict[str, Any]
```

Validation rules enforced by `validate()`:
- Record keys must be unique.
- `StreamSpec.qua_type` must be in `{"fixed", "int", "bool"}`.
- `StreamSpec.aggregate` must be in `{"save", "save_all", "average", "buffer"}`.
- IQ records (`kind="iq"`) must have both `I` and `Q` streams.
- `with_state=True` is rejected (compilation never produces real-time state).

#### `StreamSpec`

```python
@dataclass(frozen=True)
class StreamSpec:
    name: str
    qua_type: str = "fixed"
    shape: tuple[str, ...] = ("shots",)
    aggregate: str = "save_all"
```

#### Supporting Types

| Type | Fields |
|------|--------|
| `GateCondition` | `measurement_key`, `source`, `comparator` (`"truthy"`, `"=="`, `">"`, `"<"`), `value` |
| `ConditionalGate` | `gate: Gate`, `condition: GateCondition` — helper, calls `to_gate()` |
| `CircuitBlock` | `label`, `start`, `stop`, `block_type` (`"protocol"`, `"repeat"`, …), `lanes`, `metadata` |

### 28.3 Protocol Builders

**Module**: `qubox_v2.programs.circuit_protocols`

#### `RamseyProtocol`

```python
class RamseyProtocol:
    def __init__(
        self,
        qubit: str = "qubit",
        readout: str = "readout",
        tau_clks: int = 10,
        r90_op: str = "x90",
        measure_operation: str = "readout",
        n_shots: int = 100,
    ): ...

    def build(self) -> QuantumCircuit:
        """X90 → Idle(τ) → X90 → MeasureIQ"""
```

#### `EchoProtocol`

```python
class EchoProtocol:
    def __init__(
        self,
        qubit: str = "qubit",
        readout: str = "readout",
        tau_clks: int = 10,
        r90_op: str = "x90",
        r180_op: str = "x180",
        measure_operation: str = "readout",
        n_shots: int = 100,
    ): ...

    def build(self) -> QuantumCircuit:
        """X90 → Idle(τ/2) → X180 → Idle(τ/2) → X90 → MeasureIQ"""
```

#### `ActiveResetProtocol`

```python
class ActiveResetProtocol:
    def __init__(
        self,
        qubit: str = "qubit",
        readout: str = "readout",
        pi_op: str = "x180",
        measure_operation: str = "readout",
        iterations: int = 3,
        n_shots: int = 100,
        enable_real_time_branching: bool = False,
        state_rule: StateRule | None = None,
    ): ...

    def build(self) -> QuantumCircuit:
        """
        Default (analysis-only): MeasureIQ with StateRule metadata.
        State derived post-run via derive_state().

        enable_real_time_branching=True: Adds ConditionalGate(pi_op)
        that correctly raises RuntimeError at compile time because
        compile_v2 cannot emit real-time QUA branches on derived state.
        """
```

#### Convenience Wrappers

```python
def make_ramsey_circuit(**kwargs) -> QuantumCircuit
def make_echo_circuit(**kwargs) -> QuantumCircuit
def make_active_reset_circuit(**kwargs) -> QuantumCircuit
```

### 28.4 Compiler

**Module**: `qubox_v2.programs.circuit_compiler`

```python
class CircuitRunnerV2:
    def __init__(self, session: Any): ...

    def compile(
        self, circuit: QuantumCircuit, n_shots: int | None = None
    ) -> ProgramBuildResult:
        """
        Lower an intent circuit to a QUA program.

        Returns ProgramBuildResult with:
        - program: QUA program object
        - processors: tuple of post-run processors (state derivation)
        - metadata: diagram_text, measurement_schema, instruction_trace,
                    resolution_report_text, post_processing, compiler_warnings
        - resolved_frequencies: {element: freq_hz}
        - resolved_parameter_sources: {gate.param: {value, source, reference}}
        """
```

**Supported gate types**:

| `gate_type` | Lowering | Notes |
|-------------|----------|-------|
| `measure_iq` | `measureMacro.measure()` → IQ streams | Configures readout pulse via `_configure_measure_macro()` |
| `idle` / `wait` | `wait(clks, target)` | |
| `frame_update` | `update_frequency()` | Only `kind="if_hz"` currently supported |
| `play` / `play_pulse` | `play(op, target)` | Supports `amplitude`, `duration_clks`, `detune`, `condition` |
| `qubit_rotation` / `X` / `Y` | Policy-dispatched | `implementation_policy` selects: `"op"` (named op), `"hardware_reference"` (`QubitRotationHardware`), `"gaussian"` / `"drag_gaussian"` / `"square"` (waveform synthesis) |
| `displacement` | `DisplacementHardware.build()` | |
| `sqr` | `SQRHardware.build()` | |

**Parameter resolution**:

The compiler resolves each `ParameterSource` field through:
1. `override` (if set)
2. `CalibrationReference` lookup: `namespace` → calibration store method → `getattr(obj, field)`
3. `attr_fallback` → `getattr(cQED_attributes, fallback_name)`
4. `default`
5. Raise `ValueError` if required

**Legacy bridge** (in `CircuitRunner`):

```python
# Both delegate to CircuitRunnerV2(session).compile()
runner.compile_v2(circuit, n_shots=None)
runner.compile_program(circuit, n_shots=None)
```

### 28.5 Target Aliases

The compiler resolves symbolic target names to physical element names via
`cQED_attributes`:

| Alias | Resolves To |
|-------|-------------|
| `"qubit"`, `"qb"` | `attr.qb_el` |
| `"readout"`, `"ro"`, `"resonator"` | `attr.ro_el` |
| `"storage"`, `"st"` | `attr.st_el` |

Any other target name is passed through unchanged.

### 28.6 Display & Diagrams

**Module**: `qubox_v2.programs.circuit_display`

```python
def circuit_to_diagram_text(
    circuit: QuantumCircuit, *, cell_width: int = 20
) -> str

def draw_circuit(
    circuit: QuantumCircuit,
    figsize: tuple[float, float] | None = None,
    save_path: str | None = None,
    include_gate_names: bool = False,
) -> matplotlib.figure.Figure
```

The text diagram includes:
- **Gate order** header row
- **Lane rows** per target element
- **Protocol block** rows (e.g. `[Ramsey]`)
- **Analysis** rows for `state_rule` derivations
- **Branch** rows for conditional gates
- **Warnings** for analysis-only blocks
- **Measurement schema** summary

### 28.7 Execution

**Module**: `qubox_v2.programs.circuit_execution`

```python
SAFE_OPX_CLUSTER = "Cluster_1"

@dataclass
class CompiledCircuitExecution:
    build: ProgramBuildResult
    diagram_text: str
    cluster_name: str
    dry_run: bool
    connection: Any | None = None
    run_result: Any | None = None

def run_compiled_circuit(
    session: Any,
    circuit: QuantumCircuit,
    cluster: str = SAFE_OPX_CLUSTER,
    run_on_opx: bool = False,
    n_shots: int | None = None,
    execution_kwargs: dict[str, Any] | None = None,
) -> CompiledCircuitExecution
```

**Safety guardrails**:

| Scenario | Behavior |
|----------|----------|
| `cluster != "Cluster_1"` | Immediate `ValueError` — no compilation |
| `run_on_opx=False` (default) | Compile + diagram only; `run_result` is `None` |
| `run_on_opx=True`, cluster matches | Compile → open QM → execute → return result |
| Ambiguous / missing cluster | `RuntimeError` before any compilation |

### 28.8 Post-Run State Derivation

**Module**: `qubox_v2.programs.circuit_postprocess`,
`qubox_v2.programs.measurement`

```python
# StateRule defines how to derive boolean state from IQ data
@dataclass(frozen=True)
class StateRule:
    kind: str = "I_threshold"
    threshold: Any = 0.0
    sense: str = "greater"         # "greater" or "less"
    rotation_angle: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

# Apply a rule to IQ data
def derive_state(iq: Any, rule: StateRule) -> np.ndarray:
    """
    iq: dict with 'I'/'Q' keys, (I, Q) tuple, or complex ndarray
    Returns boolean ndarray.
    """
```

The compiler attaches a state-derivation processor to
`ProgramBuildResult.processors` for every `MeasurementRecord` that has a
`state_rule`.  After the QUA job completes, call each processor on the
output dict to populate `<key>.state` from `<key>.I` / `<key>.Q`.

### 28.9 Usage Examples

**Build and display a Ramsey circuit (no hardware):**

```python
from qubox_v2.programs.circuit_protocols import RamseyProtocol
from qubox_v2.programs.circuit_execution import run_compiled_circuit

circuit = RamseyProtocol(tau_clks=12, n_shots=64).build()

# Display the circuit diagram
print(circuit.to_diagram_text())
circuit.draw(include_gate_names=True)

# Compile (dry-run, no hardware)
execution = run_compiled_circuit(session, circuit, run_on_opx=False)
print(execution.diagram_text)
```

**Build an Echo circuit and inspect the resolution report:**

```python
from qubox_v2.programs.circuit_protocols import EchoProtocol
from qubox_v2.programs.circuit_compiler import CircuitRunnerV2

circuit = EchoProtocol(tau_clks=20, n_shots=100).build()
build = CircuitRunnerV2(session).compile(circuit)

print(build.metadata["resolution_report_text"])
print(build.metadata["instruction_trace"])
print(build.resolved_frequencies)
```

**Active Reset with post-run state derivation:**

```python
import numpy as np
from qubox_v2.programs.circuit_protocols import ActiveResetProtocol
from qubox_v2.programs.circuit_compiler import CircuitRunnerV2

circuit = ActiveResetProtocol(iterations=1, n_shots=100).build()
build = CircuitRunnerV2(session).compile(circuit)

# After QUA job completes, apply the state-derivation processor:
raw_output = job.result_handles  # ... fetch IQ data
processor = build.processors[0]
derived = processor({
    "active_reset_m0.I": np.array([...]),
    "active_reset_m0.Q": np.array([...]),
})
# derived["active_reset_m0.state"] is a boolean ndarray
```

**Use ParameterSource for calibration-aware gates:**

```python
from qubox_v2.programs.circuit_runner import (
    Gate, QuantumCircuit, ParameterSource, CalibrationReference,
    MeasurementSchema,
)

gate = Gate(
    name="qubit_rotation",
    target="qubit",
    params={
        "implementation_policy": "drag_gaussian",
        "amplitude": ParameterSource(
            calibration=CalibrationReference("pulse_calibration", "ge_ref_r180", "amplitude"),
            override=0.19,  # Override takes precedence
        ),
        "length": ParameterSource(
            calibration=CalibrationReference("pulse_calibration", "ge_ref_r180", "length"),
        ),
    },
)
circuit = QuantumCircuit(
    name="custom",
    gates=(gate,),
    metadata={"n_shots": 100},
    measurement_schema=MeasurementSchema(),
)
```

### 28.10 Imports Quick Reference

```python
# IR types
from qubox_v2.programs.circuit_runner import (
    Gate, QuantumCircuit, ParameterSource, CalibrationReference,
    GateCondition, ConditionalGate, CircuitBlock,
    MeasurementSchema, MeasurementRecord, StreamSpec,
)

# Protocol builders
from qubox_v2.programs.circuit_protocols import (
    RamseyProtocol, EchoProtocol, ActiveResetProtocol,
    make_ramsey_circuit, make_echo_circuit, make_active_reset_circuit,
)

# Compiler
from qubox_v2.programs.circuit_compiler import CircuitRunnerV2

# Execution
from qubox_v2.programs.circuit_execution import run_compiled_circuit

# Post-processing
from qubox_v2.programs.measurement import StateRule, derive_state

# Display (usually accessed via QuantumCircuit methods)
from qubox_v2.programs.circuit_display import circuit_to_diagram_text, draw_circuit
```

---

## Appendix A: Utility Functions

### `qubox_v2.experiments.experiment_base`

| Function | Signature | Return | Description |
|----------|-----------|--------|-------------|
| `create_if_frequencies` | `(el, start_fq, end_fq, df, lo_freq, base_if_freq) -> np.ndarray` | IF array | Compute IF sweep |
| `create_clks_array` | `(t_begin, t_end, dt, time_per_clk=4) -> np.ndarray` | Clock array | Time → clock cycles |
| `make_lo_segments` | `(rf_begin, rf_end) -> list[float]` | LO list | Multi-segment LO frequencies |
| `if_freqs_for_segment` | `(LO, rf_end, df) -> np.ndarray` | IF array | Per-segment IF frequencies |
| `merge_segment_outputs` | `(outputs, freqs) -> Output` | Merged output | Stitch multi-segment data |

### `qubox_v2.pulses.waveforms`

| Function | Signature | Return |
|----------|-----------|--------|
| `constant` | `(amplitude: float) -> float` | Constant value |
| `square` | `(amplitude, length) -> list[float]` | Square waveform |
| `gaussian` | `(amplitude, length, sigma) -> list[float]` | Gaussian waveform |
| `drag_gaussian` | `(amplitude, length, sigma, alpha, anharmonicity, detuning=0.0) -> tuple[list, list]` | `(I, Q)` |

### `qubox_v2.tools.waveforms`

| Function | Signature | Return | Description |
|----------|-----------|--------|-------------|
| `drag_gaussian_pulse_waveforms` | `(amplitude, length, sigma, alpha, anharmonicity, detuning=0.0, subtracted=True) -> (I, Q)` | `tuple[list, list]` | Gaussian DRAG waveform with Chen-style correction |
| `kaiser_pulse_waveforms` | `(amplitude, length, beta, detuning=0.0, subtracted=True, alpha=0.0, anharmonicity=0.0) -> (I, Q)` | `tuple[list, list]` | Spectrally selective Kaiser window pulse |
| `slepian_pulse_waveforms` | `(amplitude, length, NW, ...) -> (I, Q)` | `tuple[list, list]` | DPSS/Slepian window pulse |
| `drag_cosine_pulse_waveforms` | `(amplitude, length, alpha, anharmonicity, ...) -> (I, Q)` | `tuple[list, list]` | Cosine-enveloped DRAG |
| `CLEAR_waveform` | `(t_duration, t_kick, A_steady, ...) -> np.ndarray` | `np.ndarray` | 2-kick CLEAR measurement envelope |
| `build_CLEAR_waveform_from_physics` | `(t_duration, t_kick, A_steady, kappa_rad_s, chi_rad_s, dt_s=1e-9) -> np.ndarray` | `np.ndarray` | Physics-parameterized CLEAR waveform |
| `gaussian_amp_for_same_rotation` | `(ref_amp, ref_dur, target_dur, n_sigma=4.0) -> float` | `float` | Scale amplitude for different duration |

### `qubox_v2.tools.generators`

| Function | Signature | Return | Description |
|----------|-----------|--------|-------------|
| `register_qubit_rotation` | `(pom, *, name, axis, rlen, amp, waveform_type="drag", ...) -> None` | `None` | Register one rotation pulse |
| `register_rotations_from_ref_iq` | `(pom, ref_I, ref_Q, *, element, prefix, rotations, ...) -> dict` | `dict[str, (I, Q)]` | Create full rotation set from reference IQ |
| `ensure_displacement_ops` | `(pom, *, element, n_max, coherent_amp, ...) -> dict` | `dict[str, (I, Q)]` | Generate Fock-resolved displacement pulses |
| `validate_displacement_ops` | `(pom, element, disp_names) -> list[str]` | missing names | Check required displacement ops exist |

### `qubox_v2.experiments.result`

| Class | Description |
|-------|-------------|
| `FitResult` | Dataclass: `model_name`, `params`, `uncertainties`, `r_squared`, `residuals`, `metadata` |
| `AnalysisResult` | Dataclass: `data`, `fit`, `fits`, `metrics`, `source`, `metadata` |

### `qubox_v2.core.errors`

| Exception | Base | When |
|-----------|------|------|
| `QuboxError` | `RuntimeError` | Base for all qubox errors |
| `ConfigError` | `QuboxError` | Invalid or missing configuration |
| `ConnectionError` | `QuboxError` | OPX+ / Octave / instrument communication failure |
| `JobError` | `QuboxError` | QUA job submission, execution, or fetch failure |
| `DeviceError` | `QuboxError` | External-device driver error |
| `PulseError` | `QuboxError` | Invalid pulse definition |
| `CalibrationError` | `QuboxError` | Octave or element calibration failure |
| `ContextMismatchError` | `ConfigError` | Sample/cooldown/wiring context mismatch |

### `qubox_v2.core.schemas`

| Function | Signature | Return | Description |
|----------|-----------|--------|-------------|
| `validate_schema` | `(file_path, file_type, *, data=None) -> ValidationResult` | `ValidationResult` | Validate against schema |
| `register_migration` | `(file_type, target_version, func) -> None` | `None` | Register migration step |
| `migrate` | `(data, file_type, from_version, to_version) -> dict` | `dict` | Apply migration chain |
| `migrate_file` | `(file_path, file_type, target_version, *, backup=True) -> Path` | `Path` | Migrate on disk |
| `validate_config_dir` | `(config_dir) -> list[ValidationResult]` | `list` | Validate all config files |

---

## Appendix B: Known Inconsistencies

*The following inconsistencies were identified between documentation and
implementation at time of writing.  They are listed here for transparency.*

1. **`blob_k_g` default**: `ReadoutConfig.blob_k_g` is `2.0`;
   `CalibrateReadoutFull.run()` method signature has `blob_k_g: float = 3.0`.
   The `ReadoutConfig` value takes precedence when using the config path.

2. **`pulses.json` vs `pulse_specs.json`**: Both exist.  `pulses.json` is
   the deprecated format (POM persistence); `pulse_specs.json` is the
   declarative source of truth.  The transition is in progress.

3. **`cqed_params.json`**: Unversioned legacy file.  Read-only in v2 but
   preserved only as a legacy compatibility input; the v2 session path does not write it.

---

## Appendix C: Quick-Reference Cheat Sheet

### Imports

```python
# Session and core
from qubox_v2.experiments.session import SessionManager
from qubox_v2.experiments import ExperimentBase, ExperimentRunner
from qubox_v2.devices import SampleRegistry, ContextResolver

# Binding-driven API (v2.0.0)
from qubox_v2.core.bindings import (
    ChannelRef, OutputBinding, InputBinding, ReadoutBinding,
    ExperimentBindings, AliasMap, ConfigBuilder,
    bindings_from_hardware_config, build_alias_map, validate_binding,
)
from qubox_v2.programs.macros.measure import measure_with_binding

# Built-in experiments (import any you need)
from qubox_v2.experiments import (
    ResonatorSpectroscopy, QubitSpectroscopy, PowerRabi, TemporalRabi,
    T1Relaxation, T2Ramsey, T2Echo,
    IQBlob, ReadoutGEDiscrimination, AllXY, DRAGCalibration,
    RandomizedBenchmarking, PulseTrainCalibration,
    StorageSpectroscopy, StorageChiRamsey, FockResolvedT1,
    QubitStateTomography, StorageWignerTomography,
)

# Calibration
from qubox_v2.calibration import (
    CalibrationStore, CalibrationOrchestrator,
    CalibrationData, CoherenceParams, DiscriminationParams,
    PulseCalibration, FitRecord,
)

# Pulse tools
from qubox_v2.tools.generators import (
    register_rotations_from_ref_iq, ensure_displacement_ops,
)
from qubox_v2.tools.waveforms import (
    drag_gaussian_pulse_waveforms, kaiser_pulse_waveforms,
)

# Gate classes
from qubox_v2.gates.gate import Gate

# Circuit architecture (v2.4)
from qubox_v2.programs.circuit_runner import (
    Gate as IntentGate, QuantumCircuit, ParameterSource, CalibrationReference,
    MeasurementSchema, MeasurementRecord, StreamSpec,
)
from qubox_v2.programs.circuit_protocols import (
    RamseyProtocol, EchoProtocol, ActiveResetProtocol,
)
from qubox_v2.programs.circuit_compiler import CircuitRunnerV2
from qubox_v2.programs.circuit_execution import run_compiled_circuit
from qubox_v2.programs.measurement import StateRule, derive_state

# Result types
from qubox_v2.experiments.result import AnalysisResult, FitResult

# Utilities
from qubox_v2.experiments.experiment_base import create_if_frequencies, create_clks_array
from qubox_v2.core.preflight import preflight_check
from qubox_v2.core.artifacts import save_config_snapshot
```

### Common Workflow Patterns

```python
# Pattern 1: Simple run → analyze → plot
exp = SomeExperiment(session)
result = exp.run(...)
analysis = exp.analyze(result, update_calibration=True)
exp.plot(analysis)

# Pattern 2: Orchestrator-managed calibration
orch = CalibrationOrchestrator(session)
cycle = orch.run_analysis_patch_cycle(exp, run_kwargs={...}, apply=False)
orch.apply_patch(cycle["patch"], dry_run=False)

# Pattern 3: Custom experiment
class MyExp(ExperimentBase):
    def build_program(self, **kw): ...
    def run(self, **kw): ...
    def analyze(self, result, **kw): ...
    def plot(self, analysis, **kw): ...

# Pattern 4: Gate → Protocol → Circuit (v2.4)
circuit = RamseyProtocol(tau_clks=12, n_shots=64).build()
print(circuit.to_diagram_text())
execution = run_compiled_circuit(session, circuit, run_on_opx=False)
```

### ExperimentBase Accessor Quick Reference

| Accessor | Returns | Description |
|----------|---------|-------------|
| `self.attr` | `cQED_attributes` | Sample parameters (frequencies, element names, etc.) |
| `self.pulse_mgr` | `PulseOperationManager` | Pulse registration and lookup |
| `self.hw` | `HardwareController` | QM config, element frequency control |
| `self.measure_macro` | `measureMacro` | QUA readout code emitter |
| `self.calibration_store` | `CalibrationStore` | Typed calibration data |
| `self.device_manager` | `DeviceManager` | External instrument handles |
| `self.name` | `str` | Class name (for logging/artifacts) |

### ExperimentBase Helper Methods

| Method | Purpose |
|--------|---------|
| `set_standard_frequencies()` | Set element IFs to calibrated values |
| `get_readout_lo()` / `get_qubit_lo()` | Get LO frequencies |
| `burn_pulses()` | Push POM state to live QM config |
| `get_therm_clks(channel)` | Resolve thermalization wait time |
| `run_program(prog, n_total=...)` | Execute QUA program via runner |
| `save_output(output, tag)` | Persist data artifact |
| `get_confusion_matrix()` | Readout confusion matrix |
| `guarded_calibration_commit(...)` | Two-phase calibration persistence |

---

## Unit Conventions

| Quantity | Canonical Unit | Notes |
|---|---|---|
| Frequencies (LO, IF, RF, qubit, cavity) | Hz | All frequency fields in `ElementFrequencies`, `HardwareConfig` |
| Coherence times (T1, T2_ramsey, T2_echo) | seconds | `*_us` companion fields are microseconds |
| Pulse lengths | nanoseconds (ns) | `PulseCalibration.length`, QUA `play()` durations |
| Integration weight length | clock cycles | 1 clock = 4 ns |
| Thermalization waits | clock cycles | `qb_therm_clks`, `ro_therm_clks` |
| `create_clks_array` input | nanoseconds | Converted to clock cycles internally |
| Dispersive shift (chi), kerr, kappa | Hz | Stored in `ElementFrequencies` |

### Clock Cycle Conversion

The OPX+ clock period is 4 ns.  Functions like `create_clks_array()` accept
nanosecond inputs and return integer clock-cycle arrays.  Values not aligned
to the 4 ns grid are snapped with a `RuntimeWarning`.

### qualang_tools.units

Notebook code uses `u = unit()` from `qualang_tools.units` for dimensional
arithmetic:

    rf_begin = 8560 * u.MHz   # -> 8.56e9 Hz
    delay_end = 50 * u.us     # -> 50000 ns

---

*This document is auto-generated from source inspection and existing
architecture documents.  Cross-reference with the governing documents in
`qubox_v2/docs/` for policy-level requirements.*
