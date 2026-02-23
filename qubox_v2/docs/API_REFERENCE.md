# qubox\_v2 — API Reference & Architecture Guide

**Version**: 1.3.0
**Date**: 2026-02-22
**Status**: Governing Document
**Changelog**:
- v1.3.0 — Added sections 20-22: Macro System Architecture (measureMacro,
  sequenceMacros, cQED_programs), Experiment ↔ Macro Interaction Rules,
  Macro State Ownership & Persistence Boundaries.
- v1.2.0 — Added sections 16-19: ExperimentContext & DeviceRegistry,
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
16. [ExperimentContext & DeviceRegistry](#16-experimentcontext--deviceregistry)
17. [CalibrationContext & ContextResolver](#17-calibrationcontext--contextresolver)
18. [Context-Mode SessionManager](#18-context-mode-sessionmanager)
19. [Migration Guide: Legacy → Context Mode](#19-migration-guide-legacy--context-mode)
20. [Macro System Architecture](#20-macro-system-architecture)
21. [Experiment ↔ Macro Interaction Rules](#21-experiment--macro-interaction-rules)
22. [Macro State Ownership & Persistence Boundaries](#22-macro-state-ownership--persistence-boundaries)

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

```python
session = SessionManager(experiment_path="seq_1_device/")
session.open()
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

### Step 4 — Program Build

```python
result = rabi.run(gains=np.linspace(0, 1.5, 100), n_avg=5000)
```

Internally, `run()`:

1. Calls `set_standard_frequencies()` to align element IF/LO to calibrated
   values.
2. Builds a QUA program via `build_program()`.
3. `PulseOperationManager` resolves `(element, op)` → pulse name → waveform
   samples.
4. Calibration parameters are injected where needed (e.g., readout threshold,
   discrimination angle).

### Step 5 — Execution

```python
# Already called inside run():
# runner.run_program(qua_prog, n_total=n_avg)
```

- `ProgramRunner` submits the job to QM via `qm.execute()`.
- Optional progress reporting via `tqdm` handle or custom callback.
- SPA pump is managed via context manager (on before execute, off after).
- Execution metadata (duration, job ID, mode) captured in `RunResult`.

### Step 6 — Analysis Layer

```python
analysis = rabi.analyze(result, update_calibration=True)
rabi.plot(analysis)
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
| `override_readout_operation` | `(*, element, operation, weights, drive_frequency, demod, threshold, weight_len, apply_to_attributes, persist_measure_config) -> dict[str, Any]` | `dict` | Modifies live readout op, optionally persists |

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

### 4.2 Calibration State Machine

**Module**: `qubox_v2.calibration.state_machine`

```python
class CalibrationState(str, Enum):
    IDLE             = "idle"
    CONFIGURED       = "configured"
    ACQUIRING        = "acquiring"
    ACQUIRED         = "acquired"
    ANALYZING        = "analyzing"
    ANALYZED         = "analyzed"
    PLOTTED          = "plotted"
    PENDING_APPROVAL = "pending_approval"
    COMMITTING       = "committing"
    COMMITTED        = "committed"
    FAILED           = "failed"
    ABORTED          = "aborted"
    ROLLED_BACK      = "rolled_back"
```

**Transition rules:**

- Only transitions listed in `ALLOWED_TRANSITIONS` are legal.
- `FAILED` and `ABORTED` are reachable from any state.
- `calibration.json` may only be written when state is `COMMITTING`.
- Transition to `COMMITTING` requires passing through `PENDING_APPROVAL`.
- No state may be skipped.
- Every transition is logged with a timestamp.

```python
class CalibrationStateMachine:
    def __init__(self, experiment: str) -> None

    def transition(self, target: CalibrationState) -> None
    def can_transition(self, target: CalibrationState) -> bool
    def is_committable(self) -> bool
    def abort(self, reason: str = "") -> None
    def fail(self, error: str) -> None
    def summary(self) -> dict[str, Any]
```

**Failure mode**: `CalibrationStateError` raised on illegal transition.

### 4.3 CalibrationPatch

**Module**: `qubox_v2.calibration.state_machine`  
**Purpose**: Explicit diff object for calibration updates.

```python
@dataclass
class CalibrationPatch:
    experiment: str
    timestamp: str                          # Auto ISO-8601
    changes: list[PatchEntry] = field(...)
    validation: PatchValidation = field(...)
    metadata: dict[str, Any] = field(...)
```

```python
@dataclass(frozen=True)
class PatchEntry:
    path: str       # Dotted key path, e.g. "readout.ge_angle"
    old_value: Any
    new_value: Any
    dtype: str = ""
```

```python
@dataclass(frozen=True)
class PatchValidation:
    passed: bool
    checks: dict[str, bool] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
```

| Method | Signature | Return |
|--------|-----------|--------|
| `add_change` | `(path, old_value, new_value, dtype="") -> None` | `None` |
| `override_validation` | `(gate, reason, user="") -> None` | `None` |
| `is_approved` | `() -> bool` | `bool` |
| `summary` | `() -> str` | `str` |
| `to_dict` | `() -> dict[str, Any]` | `dict` |

### 4.4 Calibration Data Models

**Module**: `qubox_v2.calibration.models`  
All models are Pydantic v2 `BaseModel` subclasses.

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `DiscriminationParams` | Single-shot readout discrimination | `threshold`, `angle`, `mu_g`, `mu_e`, `sigma_g`, `sigma_e`, `fidelity?`, `confusion_matrix?` |
| `ReadoutQuality` | Butterfly measurement metrics | `F?`, `Q?`, `V?`, `t01?`, `t10?`, `confusion_matrix?` |
| `ElementFrequencies` | Calibrated frequencies (Hz) | `lo_freq`, `if_freq`, `qubit_freq?`, `anharmonicity?`, `fock_freqs?`, `chi?`, `kappa?`, `kerr?` |
| `CoherenceParams` | Coherence times | `T1?`, `T2_ramsey?`, `T2_echo?` |
| `PulseCalibration` | Calibrated pulse params | `pulse_name`, `element`, `amplitude?`, `length?`, `sigma?`, `drag_coeff?` |
| `FitRecord` | Generic fit result | `experiment`, `model_name`, `params`, `uncertainties?`, `reduced_chi2?` |
| `PulseTrainResult` | Pulse-train tomography | `amp_err`, `phase_err`, `delta`, `zeta` |
| `FockSQRCalibration` | Per-Fock SQR gate | `fock_number`, `model_type`, `params`, `fidelity?` |
| `MultiStateCalibration` | Multi-alpha affine calibration | `alpha_values`, `affine_matrix`, `offset_vector` |
| `CalibrationData` | **Root container** (schema v3.0.0) | All of the above, plus `version`, `created`, `last_modified` |

### 4.5 Calibration Flow Examples

```
PowerRabi.analyze(update_calibration=True)
    → updates PulseCalibration("x180").amplitude   (g_pi)

DRAGCalibration.analyze(update_calibration=True)
    → updates PulseCalibration("x180").drag_coeff   (beta)

ReadoutGEDiscrimination.analyze(update_calibration=True)
    → updates DiscriminationParams.{threshold, angle, fidelity}
    → optionally registers rotated integration weights in POM

CalibrateReadoutFull.run(config=cfg)
    → Step 1: ReadoutWeightsOptimization (optional)
    → Step 2: ReadoutGEDiscrimination
    → Step 3: ReadoutButterflyMeasurement
    → returns combined result with all metrics
```

### 4.6 When `calibration.json` is Written

1. **Only** during the `COMMITTING` state of `CalibrationStateMachine`.
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
| `calibration.json` | **Disk** (source of truth) | Only via `CalibrationStore` in `COMMITTING` state |
| `cqed_params.json` | **Disk** (legacy compat) | Written by `save_attributes()`; read-only in v2 path |
| `measureConfig.json` | **Disk** | Written by measureMacro lifecycle |
| `devices.json` | **Disk** | Manual edits; written by `DeviceManager.save()` |
| `pulses.json` | **Disk** (deprecated) | Transitional compatibility; will be removed |
| `calibration_history.jsonl` | **Disk** | Append-only; never truncated |
| Session artifacts | **Disk** (`artifacts/<build_hash>/`) | Immutable after creation |

### 7.2 `calibration.json` Structure

```json
{
  "version": "3.0.0",
  "discrimination": {
    "<element>": { "threshold": ..., "angle": ..., "mu_g": [...], ... }
  },
  "readout_quality": {
    "<element>": { "F": ..., "Q": ..., "V": ..., ... }
  },
  "frequencies": {
    "<element>": { "lo_freq": ..., "if_freq": ..., "qubit_freq": ..., ... }
  },
  "coherence": {
    "<element>": { "T1": ..., "T2_ramsey": ..., ... }
  },
  "pulse_calibrations": {
    "<name>": { "pulse_name": "x180", "element": "qubit", "amplitude": ..., ... }
  },
  "fit_history": [ ... ],
  "pulse_train_results": { ... },
  "fock_sqr_calibrations": { ... },
  "multi_state_calibration": { ... },
  "created": "...",
  "last_modified": "..."
}
```

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
| `calibration.json` | `version` | `"3.0.0"` |
| `measureConfig.json` | `_version` | 5 |
| `devices.json` | `schema_version` | 1 |
| `pulses.json` (deprecated) | `_schema_version` | 2 |

**Migration machinery:**

```python
# Register a migration step
register_migration("calibration", target_version=4, func=migrate_3_to_4)

# Apply migration chain
migrate(data, "calibration", from_version=3, to_version=4) -> dict

# Validate any config file
validate_schema(file_path, file_type) -> ValidationResult

# Validate all config files in a directory
validate_config_dir(config_dir) -> list[ValidationResult]
```

### 7.5 What Must Never Auto-Overwrite

1. `calibration.json` — only written during `COMMITTING` state.
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
| `QubitPulseTrain` | Pulse-train amplitude calibration |
| `QubitPulseTrainLegacy` | Legacy pulse-train method |
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
| `SPAFluxOptimization2` | SPA flux optimization variant |
| `SPAPumpFrequencyOptimization` | SPA pump frequency optimization |

### 9.2 Experiment Contract Summary

Every experiment must satisfy:

1. **`run()`**: Returns `RunResult`.  No calibration writes.  No hidden
   pulse registration.  Must call `set_standard_frequencies()`.
2. **`analyze()`**: Idempotent.  No hardware ops.  Populate
   `AnalysisResult.{metrics, fit, metadata}`.
3. **`plot()`**: Accept `AnalysisResult` + optional `ax`.  Create own
   figure if `ax=None`.  Return `Figure`.

### 9.3 `ReadoutConfig` (Full Pipeline Configuration)

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
- **Side effect**: Also calls `save_attributes()` → writes `cqed_params.json`.

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
| `PersistMeasureConfig` | Save measureMacro to JSON | Lines 206-210 |
| `TriggerPulseRecompile` | Call `session.burn_pulses()` | Lines 212-214 |

After all ops (non-dry-run): `session.calibration.save()` and
`session.save_pulses()` (lines 217-218).

### 13.4 Patch Rules

**Module**: `qubox_v2/calibration/patch_rules.py`

| Rule | Result Kind | What It Patches |
|------|-------------|-----------------|
| `PiAmpRule` | `pi_amp` | Reference pulse amplitude + primitive family (x180, y180, x90, etc.) |
| `T1Rule` | `t1` | `coherence.<element>.T1` |
| `T2RamseyRule` | `t2_ramsey` | `coherence.<element>.T2_ramsey` + optional frequency correction |
| `T2EchoRule` | `t2_echo` | `coherence.<element>.T2_echo` |
| `FrequencyRule` | `qubit_freq` / `storage_freq` | `frequencies.<element>.qubit_freq` + optional kappa |
| `DragAlphaRule` | `drag_alpha` | `pulse_calibrations.<pulse>.drag_coeff` for all primitives |
| `DiscriminationRule` | `ReadoutGEDiscrimination` | `discrimination.<element>.*` |
| `ReadoutQualityRule` | `ReadoutButterflyMeasurement` | `readout_quality.<element>.*` |
| `WeightRegistrationRule` | Any (with metadata) | Promotes proposed ops from analysis metadata |

Default rule mapping: `default_patch_rules(session)` (patch_rules.py:246-274).

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
- `CalibrateReadoutFull` pipeline (direct calls in readout.py).

**When loaded**:
- `SessionManager.open()` → `_load_measure_config()` (session.py:335,
  465-477).

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

### 14.4 Known Gap: Dual-Truth Problem

Discrimination params exist in both:

- `calibration.json` → `discrimination.<element>.*`
  (canonical typed store)
- `measureConfig.json` → `current.ro_disc_params.*`
  (runtime macro state)

These can diverge.  See `STALE_CALIBRATION_RISK_REPORT.md` Risk R3.

---

## 15. Known Gaps and Risks

### 15.1 No Device Identity — **RESOLVED in v1.2.0**

~~There is no `device_id`, `cooldown_id`, or `wiring_revision` in any
config file.~~  Now addressed by `ExperimentContext` (Section 16) and
`CalibrationContext` (Section 17).  Device identity is embedded in
calibration files as of schema v4.0.0.

### 15.2 No Cooldown Scoping — **RESOLVED in v1.2.0**

~~Calibrations from previous cooldowns are silently reused.~~
Now addressed by `DeviceRegistry` cooldown directories (Section 16.2)
and `ContextMismatchError` enforcement (Section 17.2).  Each cooldown
gets its own `config/` subtree.

### 15.3 No Hardware-Calibration Coupling — **RESOLVED in v1.2.0**

~~Changes to `hardware.json` do not invalidate `calibration.json`.~~
Now addressed by `wiring_rev` (SHA-256 of hardware.json) embedded in
`ExperimentContext` and validated on `CalibrationStore` load
(Section 17.2).

### 15.4 Dual-Truth Stores

Discrimination params and frequencies exist in multiple files without
enforced sync.
See `docs/audit/PATHS_AND_OWNERSHIP.md` Observations 1 and 2.
See `docs/audit/MACRO_ENTANGLEMENT_REPORT.md` entries D1, D2, D3.
**Status**: Partially mitigated — context block adds provenance tracking,
but `measureConfig.json` and `calibration.json` can still diverge.
Sync mechanism planned in `docs/audit/MACRO_REFACTOR_PROPOSAL.md` Phase 3.

### 15.5 Direct Calibration Mutation in analyze()

Several experiment `analyze()` methods directly mutate the calibration
store, bypassing the state machine and orchestrator.
See `docs/audit/LEAKS.md` Section A.
See `docs/audit/MACRO_ENTANGLEMENT_REPORT.md` entries A1, A2, C1.
**Status**: Open — no structural change yet.  Migration plan in
`docs/audit/MACRO_REFACTOR_PROPOSAL.md` Phase 2.

### 15.6 Non-Transactional Session Close

`SessionManager.close()` writes multiple files sequentially without
transactional guarantees.
See `docs/audit/STALE_CALIBRATION_RISK_REPORT.md` Risk R9.
**Status**: Open.

### 15.7 Modularity Roadmap — **IMPLEMENTED in v1.2.0**

~~Concrete proposals for device/cooldown scoping are documented in
`docs/audit/MODULARITY_RECOMMENDATIONS.md`.~~
All modularity recommendations have been implemented.  See Sections 16-19.

---

## 16. ExperimentContext & DeviceRegistry

### 16.1 ExperimentContext

**Module**: `qubox_v2/core/experiment_context.py`
**Type**: `@dataclass(frozen=True)`

An immutable identity token that pins a session to a specific device,
cooldown, and hardware wiring.  Created once during `SessionManager` init
and never mutated.

```python
@dataclass(frozen=True)
class ExperimentContext:
    device_id:      str
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
| `matches_device` | `(other: ExperimentContext) -> bool` | `bool` | Same `device_id` |
| `matches_cooldown` | `(other: ExperimentContext) -> bool` | `bool` | Same `device_id` *and* `cooldown_id` |
| `matches_wiring` | `(other: ExperimentContext) -> bool` | `bool` | Same `wiring_rev` |
| `compute_wiring_rev` | `(hw_path: Path) -> str` | `str` | Static: SHA-256[:8] of file (staticmethod) |

#### Typical Flow

```text
DeviceRegistry ─resolve_config_paths()─▶ file system paths
                                           │
ContextResolver ─resolve()─────────────────▶ ExperimentContext
                                           │
SessionManager.__init__() ◀────────────────┘
  │
  ├─▶ CalibrationStore(path, context=ctx)  ← validates on load
  └─▶ session.context                      ← exposed property
```

### 16.2 DeviceRegistry

**Module**: `qubox_v2/devices/device_registry.py`
**Type**: `class DeviceRegistry`

Manages the filesystem tree for multi-device, multi-cooldown experiments.

```python
class DeviceRegistry:
    def __init__(self, base_path: Path) -> None
```

**Directory layout created by registry operations:**

```text
{base_path}/devices/
  {device_id}/
    device.json            ← DeviceInfo metadata
    config/                ← device-level: hardware.json, cqed_params.json,
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
| `create_device` | `(device_id, *, description, config_source, sample_info)` | `Path` | Create device dir + copy config |
| `create_cooldown` | `(device_id, cooldown_id, *, seed_from)` | `Path` | Create cooldown dir, seed calibration |
| `list_devices` | `()` | `list[str]` | All device IDs |
| `list_cooldowns` | `(device_id)` | `list[str]` | All cooldown IDs for a device |
| `device_exists` | `(device_id) -> bool` | `bool` | Check device dir exists |
| `cooldown_exists` | `(device_id, cooldown_id) -> bool` | `bool` | Check cooldown dir exists |
| `device_path` | `(device_id) -> Path` | `Path` | Absolute path to device dir |
| `cooldown_path` | `(device_id, cooldown_id) -> Path` | `Path` | Absolute path to cooldown dir |
| `load_device_info` | `(device_id) -> DeviceInfo` | `DeviceInfo` | Read `device.json` |
| `resolve_config_paths` | `(device_id, cooldown_id) -> dict` | `dict` | Merged device-level + cooldown-level paths |

### 16.3 DeviceInfo

**Module**: `qubox_v2/devices/device_registry.py`
**Type**: `@dataclass`

```python
@dataclass
class DeviceInfo:
    device_id:   str
    description: str   = ""
    created:     str   = ""          # ISO-8601
    sample_info: dict  = field(default_factory=dict)
```

---

## 17. CalibrationContext & ContextResolver

### 17.1 CalibrationContext

**Module**: `qubox_v2/calibration/models.py`
**Type**: `class CalibrationContext(BaseModel)` (Pydantic v2)

Embedded context block inside `calibration.json`, stamped on every save
to record which device, cooldown, and wiring revision produced the data.

```python
class CalibrationContext(BaseModel):
    device_id:      str
    cooldown_id:    str
    wiring_rev:     str
    schema_version: str  = "4.0.0"
    config_hash:    str  = ""
    created:        str  = ""   # ISO-8601
```

The `CalibrationData` model (root of `calibration.json`) now includes:

```python
class CalibrationData(BaseModel):
    version: str = "4.0.0"
    context: CalibrationContext | None = None   # NEW in v4.0.0
    # ... existing fields ...
```

#### Schema Migration v3 → v4

On load, `CalibrationStore._load_or_create()` detects `version < "4.0.0"`
and calls `_migrate_calibration_3_to_4()` (registered in `core/schemas.py`),
which:

1. Sets `version = "4.0.0"`.
2. Adds an empty `context: null` block.
3. The migration is in-memory only; the file is updated on next
   `calibration.save()`.

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
3. Compare `context.device_id` with `data.context.device_id`.
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
    def __init__(self, registry: DeviceRegistry) -> None

    def resolve(
        self,
        device_id: str,
        cooldown_id: str,
    ) -> ExperimentContext
```

Resolves a `(device_id, cooldown_id)` pair into a full
`ExperimentContext` by:

1. Looking up `hardware.json` in the device config directory.
2. Computing `wiring_rev` via `ExperimentContext.compute_wiring_rev()`.
3. Computing `config_hash` from the merged set of device-level +
   cooldown-level config files.
4. Setting `schema_version = "4.0.0"`.

### 17.4 ContextMismatchError

**Module**: `qubox_v2/core/errors.py`

```python
class ContextMismatchError(ConfigError):
    """Calibration data was produced by a different device or wiring revision."""
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
        device_id: str | None = None,
        cooldown_id: str | None = None,
        registry_base: Path | None = None,
        strict_context: bool = True,
    ) -> None
```

**New keyword-only parameters** (v1.2.0):

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `device_id` | `str \| None` | `None` | Device identifier in the registry |
| `cooldown_id` | `str \| None` | `None` | Cooldown identifier |
| `registry_base` | `Path \| None` | `None` | Root path containing `devices/` tree |
| `strict_context` | `bool` | `True` | Pass to `CalibrationStore` for mismatch enforcement |

### 18.2 Mode Selection

| Condition | Mode | `experiment_path` | `context` |
|-----------|------|--------------------|-----------|
| `device_id` + `cooldown_id` provided | **Context** | Auto-resolved to cooldown dir | `ExperimentContext(...)` |
| Only `experiment_path` provided | **Legacy** | As provided | `None` |

In context mode, the session:

1. Creates a `DeviceRegistry(registry_base)`.
2. Resolves `config_paths = registry.resolve_config_paths(device_id, cooldown_id)`.
3. Sets `experiment_path` to the cooldown root directory.
4. Builds `ExperimentContext` via `ContextResolver(registry).resolve(...)`.
5. Passes `context` and `strict_context` to `CalibrationStore`.
6. Populates `SessionState` with `device_id`, `cooldown_id`, `wiring_rev`.

### 18.3 New Properties and Methods

| Member | Type | Description |
|--------|------|-------------|
| `session.context` | `ExperimentContext \| None` | Active context (None in legacy mode) |
| `SessionManager.from_device(cls, ...)` | classmethod | Convenience for context-mode construction |

### 18.4 SessionState Updates

**Module**: `qubox_v2/core/session_state.py`

New fields added to `SessionState`:

| Field | Type | Default | Source |
|-------|------|---------|--------|
| `device_id` | `str \| None` | `None` | `ExperimentContext.device_id` |
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
work unchanged.  Context mode is opt-in — activate it by passing `device_id`
and `cooldown_id`.

### 19.2 Step-by-Step Migration

1. **Import `DeviceRegistry`**:

```python
from qubox_v2.devices import DeviceRegistry
```

2. **Create a device from existing config** (one-time setup):

```python
registry = DeviceRegistry(Path("E:/qubox"))
registry.create_device(
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
    device_id="my_device",
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
# Start a new cooldown for the same device
registry.create_cooldown("my_device", "cd_2025_04_01")

session = SessionManager(
    device_id="my_device",
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
| Session constructor | `SessionManager("./seq_1_device")` | `SessionManager(device_id=..., cooldown_id=...)` |
| Calibration path | `{experiment_path}/config/calibration.json` | `devices/{id}/cooldowns/{cd}/config/calibration.json` |
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
| `cQED_programs` | `programs/cQED_programs.py` | Function library (2914 lines, 46 functions) | QUA program factories for all experiment types |

### 20.2 measureMacro

**Type**: Module-level singleton (non-instantiable; all methods are `@classmethod`).

**State model**: All state is stored as mutable class variables.  Key state groups:

| Group | Variables | Persistence |
|-------|-----------|-------------|
| Pulse binding | `_pulse_op`, `_active_op` | `measureConfig.json` |
| Demodulation | `_demod_weight_sets`, `_demod_fn`, `_demod_args`, `_demod_kwargs`, `_demod_weight_len` | `measureConfig.json` |
| Gain/frequency | `_gain`, `_drive_frequency` | `measureConfig.json` |
| Discrimination | `_ro_disc_params` (threshold, angle, fidelity, mu_g/e, sigma_g/e) | `measureConfig.json` + `calibration.json` (dual-truth) |
| Quality | `_ro_quality_params` (F, Q, V, confusion_matrix, transition_matrix, affine_n) | `measureConfig.json` + `calibration.json` (dual-truth) |
| Post-selection | `_post_select_config` | `measureConfig.json` |
| State stack | `_state_stack`, `_state_index`, `_state_counter` | Not persisted |

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

### 20.4 cQED\_programs

**Type**: Monolithic module of 46 QUA program factory functions.

**Import structure:**
```python
from .macros.measure import measureMacro
from .macros.sequence import sequenceMacros
from ..experiments.gates_legacy import Gate, GateArray, Measure
```

**Program families:**

| Family | Count | Functions |
|--------|-------|-----------|
| Spectroscopy | 8 | `readout_trace`, `resonator_spectroscopy`, `resonator_power_spectroscopy`, `qubit_spectroscopy`, `qubit_spectroscopy_ef`, `resonator_spectroscopy_x180`, `storage_spectroscopy`, `num_splitting_spectroscopy` |
| Time-domain | 10 | `temporal_rabi`, `power_rabi`, `time_rabi_chevron`, `power_rabi_chevron`, `ramsey_chevron`, `T1_relaxation`, `T2_ramsey`, `T2_echo`, `ac_stark_shift`, `residual_photon_ramsey` |
| Readout | 6 | `iq_blobs`, `readout_ge_raw_trace`, `readout_ge_integrated_trace`, `readout_core_efficiency_calibration`, `readout_butterfly_measurement`, `readout_leakage_benchmarking` |
| Calibration | 7 | `all_xy`, `randomized_benchmarking`, `sequential_qb_rotations`, `qubit_pulse_train`, `qubit_pulse_train_legacy`, `drag_calibration_YALE`, `drag_calibration_GOOGLE` |
| Cavity | 11 | `storage_spectroscopy`, `num_splitting_spectroscopy`, `sel_r180_calibration0`, `fock_resolved_spectroscopy`, `fock_resolved_T1_relaxation`, `fock_resolved_power_rabi`, `fock_resolved_qb_ramsey`, `storage_wigner_tomography`, `phase_evolution_prog`, `storage_chi_ramsey`, `storage_ramsey` |
| Tomography | 3 | `qubit_state_tomography`, `fock_resolved_state_tomography`, `sequential_simulation` |
| Reset | 2 | `qubit_reset_benchmark`, `active_qubit_reset_benchmark` |
| Utility | 2 | `continuous_wave`, `SPA_flux_optimization` |

All functions except `continuous_wave` depend on `measureMacro` for readout
code generation.

**Re-export wrappers** exist in `programs/spectroscopy.py`,
`programs/time_domain.py`, `programs/readout.py`, `programs/calibration.py`,
`programs/cavity.py`, and `programs/tomography.py`.  These are pure
re-exports — no code has been migrated.

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
| Read confusion matrix | `self.get_confusion_matrix()` (pending) or `self.measure_macro._ro_quality_params["confusion_matrix"]` | Inside `analyze()` |
| Read calibration values | `self.measure_macro.get_readout_calibration()` | Inside `analyze()` |

**Prohibited interactions:**

| Action | Why Prohibited | Current Violations |
|--------|----------------|--------------------|
| Calling `_update_readout_discrimination()` | Bypasses calibration state machine | `readout.py:807` |
| Calling `_update_readout_quality()` | Bypasses calibration state machine | `readout.py:1794` |
| Calling `save_json()` from `analyze()` | Violates analyze idempotency | `readout.py:817,2198` |
| Mutating `_ro_disc_params` directly | Untracked state change | `session.py:550` |
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
# In ExperimentBase.analyze() — CORRECT pattern (current)
confusion = kw.get("confusion", None)
if confusion is None:
    confusion = self.measure_macro._ro_quality_params.get("confusion_matrix")

# RECOMMENDED replacement (future):
confusion = kw.get("confusion", None)
if confusion is None:
    confusion = self.get_confusion_matrix()
```

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
| `SessionManager.close()` | (Not currently saved — gap) | Session teardown |

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

| Pair | Status | Resolution Path |
|------|--------|-----------------|
| `calibration.json` ↔ `measureConfig.json` (discrimination) | **Open** — both written independently | Planned: `CalibrationStore → measureMacro` sync (see `docs/audit/MACRO_REFACTOR_PROPOSAL.md` Phase 3) |
| `calibration.json` ↔ `measureConfig.json` (quality) | **Open** | Same |
| `calibration.json` ↔ `cqed_params.json` (frequencies) | **Partially resolved** | `cqed_params.json` is read-only in v2; `calibration.json` is canonical |

### 22.4 Macro System Audit Documents

The following audit documents provide detailed analysis of the macro system:

| Document | Path | Content |
|----------|------|---------|
| Architecture Summary | `docs/audit/MACRO_PROGRAM_ARCHITECTURE.md` | Data model, public methods, program families, data flow |
| Entanglement Report | `docs/audit/MACRO_ENTANGLEMENT_REPORT.md` | Specific coupling points with file paths and line numbers |
| Refactor Proposal | `docs/audit/MACRO_REFACTOR_PROPOSAL.md` | Modularization plan, clean interfaces, 4-phase migration |

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
   still written by `save_attributes()` for backward compatibility.

---

*This document is auto-generated from source inspection and existing
architecture documents.  Cross-reference with the governing documents in
`qubox_v2/docs/` for policy-level requirements.*
