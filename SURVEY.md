# Gate–Protocol–Circuit Architecture Survey

> **Historical document (2026-03-02).** This surveys the `qubox_v2_legacy`
> gate/circuit architecture which has since been narrowed and merged into
> `qubox`. See [API Reference](API_REFERENCE.md) for the current architecture.

**Date**: 2026-03-02  
**Scope**: `qubox_v2_legacy` full codebase  
**Purpose**: PHASE 0 mandatory survey before implementing the Gate → Protocol → Circuit → Backend (QUA) abstraction layer.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Architecture Overview](#2-current-architecture-overview)
3. [Where QUA Programs Are Constructed](#3-where-qua-programs-are-constructed)
4. [Where Pulse Definitions Are Resolved](#4-where-pulse-definitions-are-resolved)
5. [Where Calibration Values Are Injected](#5-where-calibration-values-are-injected)
6. [Where Measurement Streams Are Defined](#6-where-measurement-streams-are-defined)
7. [Existing Gate System](#7-existing-gate-system)
8. [Existing CircuitRunner](#8-existing-circuitrunner)
9. [Calibration Resolution Logic](#9-calibration-resolution-logic)
10. [Patch / Update Flow](#10-patch--update-flow)
11. [Artifact Persistence](#11-artifact-persistence)
12. [Duplicated Logic & Pain Points](#12-duplicated-logic--pain-points)
13. [Integration Constraints](#13-integration-constraints)
14. [Recommended Architecture Insertion Points](#14-recommended-architecture-insertion-points)

---

## 1. Executive Summary

`qubox_v2_legacy` is a layered experiment orchestration framework for circuit-QED systems on Quantum Machines OPX+ hardware. It enforces declarative pulses, immutable session state, and calibration-DB persistence. The framework currently has:

- **26 experiment classes** (all migrated to `_build_impl()` / `ProgramBuildResult`)
- **~50 QUA program builders** spread across 8 builder modules under `programs/builders/`
- **2 macro singletons** (`measureMacro`, `sequenceMacros`) that emit QUA sub-sequences
- **An existing Gate system** (`gates/`) focused on pure-model simulation + hardware waveform synthesis (no circuit-level orchestration)
- **An existing CircuitRunner** (`programs/circuit_runner.py`) that compiles a limited set of `QuantumCircuit` → QUA programs by dispatching to legacy builders

The current architecture has **no intermediate protocol layer** between physics intent and QUA emission. Experiments couple directly to program builder functions, passing raw parameters. There is no reusable, composable circuit abstraction for sequences like Ramsey, Echo, or Active Reset.

### Key Finding

The codebase is well-prepared for a Gate → Protocol → Circuit → Backend refactor because:
1. The gate model/hardware split already exists and is extensible
2. CircuitRunner exists as a partial prototype for circuit→QUA compilation
3. `ProgramBuildResult` provides the right output contract
4. CalibrationStore has typed getters for all needed parameters
5. All builder functions follow consistent patterns that can be abstracted

The main gaps:
- No physics-intent Gate layer (current Gate = model+hardware, not intent)
- No Protocol layer
- No composable Circuit type with measurement schema tracking
- CircuitRunner hardcodes 5 circuit names instead of being gate-driven
- No calibration-backed default resolution on Gate objects

---

## 2. Current Architecture Overview

### Layer Map

```
Layer 9  Notebook / User Interface
Layer 8  Verification + Legacy Parity Harness
Layer 7  Artifact Manager (build-hash keyed)
Layer 6  Experiment Definitions (ExperimentBase subclasses)
         └── _build_impl() → ProgramBuildResult → run_program()
Layer 5  Calibration Management (CalibrationStore, StateMachine, Patch)
Layer 4  ConfigCompiler (ConfigEngine)
Layer 3  PulseFactory + Operation Binding (POM, PulseFactory, PulseRegistry)
Layer 2  Pulse Specification (pulse_specs.json)
Layer 1  Hardware Abstraction (hardware.json, HardwareController, ProgramRunner)
```

### Key Actors

| Component | Module | Responsibility |
|-----------|--------|----------------|
| `SessionManager` | `experiments/session.py` | Service container; owns all infrastructure |
| `ExperimentBase` | `experiments/experiment_base.py` | Experiment lifecycle: build → run → analyze → plot |
| `ProgramBuildResult` | `experiments/result.py` | Immutable build snapshot (QUA program + metadata) |
| `CircuitRunner` | `programs/circuit_runner.py` | Circuit → QUA compiler (partial, 5 circuits) |
| `cQED_programs` (api) | `programs/api.py` | Re-exports all builder functions |
| `measureMacro` | `programs/macros/measure.py` | Singleton: emits QUA `measure()` with demod/discrimination |
| `sequenceMacros` | `programs/macros/sequence.py` | Singleton: emits reusable QUA sub-sequences |
| `CalibrationStore` | `calibration/store.py` | JSON-backed calibration persistence |
| `CalibrationOrchestrator` | `calibration/orchestrator.py` | Run → artifact → analyze → patch pipeline |
| `GateModel` / `GateHardware` | `gates/` | Simulation-first gate models + QUA hardware backends |
| `GateTuningStore` | `programs/gate_tuning.py` | Per-operation amplitude/phase correction records |

---

## 3. Where QUA Programs Are Constructed

All QUA programs are constructed via `with program() as prog:` blocks inside builder functions under `programs/builders/`.

### Builder Modules

| Module | # Programs | Focus |
|--------|-----------|-------|
| `builders/spectroscopy.py` | 7 | Resonator/qubit frequency sweeps |
| `builders/time_domain.py` | 10 | Rabi, T1, T2, Ramsey, Echo, AC-Stark |
| `builders/readout.py` | 7 | IQ blobs, butterfly, leakage, reset benchmarks |
| `builders/calibration.py` | 5 | AllXY, RB, DRAG, sequential rotations |
| `builders/cavity.py` | 11 | Storage spectroscopy, Wigner tomography, chi-Ramsey, SNAP, Fock-resolved |
| `builders/tomography.py` | 2 | Qubit and Fock-resolved state tomography |
| `builders/utility.py` | 2 | CW output, SPA flux optimization |
| `builders/simulation.py` | 1 | Plays `Gate` objects sequentially (polymorphic `gate.play()`) |

### QUA Program Construction Pattern (Universal)

```python
def some_experiment(param1, param2, ..., n_avg, qb_el="qubit", bindings=None):
    # 1. Bindings resolution (identical block in every function)
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        qb_el = qb_el or _names.get("qubit", "__qb")
    elif qb_el is None:
        raise ValueError(...)

    # 2. QUA program block
    with program() as prog:
        n = declare(int)
        I = declare(fixed)
        Q = declare(fixed)
        I_st = declare_stream()
        Q_st = declare_stream()
        n_st = declare_stream()
        
        with for_(n, 0, n < n_avg, n + 1):
            # 3. Thermalization wait
            wait(int(qb_therm_clks))
            
            # 4. Frequency updates (if sweeping)
            update_frequency(qb_el, f)
            
            # 5. Pulse operations
            play(op, qb_el)           # or play(op * amp(a), qb_el)
            wait(delay_clk)
            
            # 6. Measurement
            measureMacro.measure(targets=[I, Q])  # or with_state=True
            
            # 7. Stream saves
            save(I, I_st)
            save(Q, Q_st)
        
        save(n, n_st)
        
        # 8. Stream processing
        with stream_processing():
            I_st.buffer(N).average().save("I")
            Q_st.buffer(N).average().save("Q")
            n_st.save("iteration")
    
    return prog
```

### Special Builder: `builders/simulation.py`

The only builder that uses `Gate` objects directly:
```python
def sequential_simulation(gates, measurements, ...):
    with program() as prog:
        for gate in gates:
            gate.play()                    # polymorphic QUA emission
        for meas in measurements:
            meas.measure(targets=[I, Q])   # MeasurementGate
```

This is the closest existing pattern to what the new architecture should generalize.

---

## 4. Where Pulse Definitions Are Resolved

### Resolution Chain

```
Notebook (register_rotations_from_ref_iq, ensure_displacement_ops)
    → PulseOperationManager.create_control_pulse() / add_waveform()
    → burn_pulses() → ConfigEngine.build_qm_config()
    → QM config dict: elements[el]['operations'][op] → pulse_name
    → QUA play(op, element) resolves via QM runtime
```

### Key Resolution Points

1. **`PulseOperationManager` (POM)** — Dual-store (permanent + volatile) for waveforms, pulses, weights, and element↔operation mappings.
2. **`PulseFactory`** — Converts declarative specs (`pulse_specs.json`) into I/Q sample arrays.
3. **`PulseRegistry`** — Simplified registration API wrapping POM.
4. **`GateHardware.build(hw_ctx)`** — Computes I/Q waveforms from calibration data, registers as named operations via POM.
5. **`GateTuningStore`** — Stores per-operation amplitude_scale, detune_hz, phase_offset_rad corrections; applied by `CircuitRunner._apply_gate_tuning()`.

### Element-LO-IF Frequency Management

```
CalibrationStore.get_frequencies(element) → ElementFrequencies
    → HardwareController.set_element_fq(element, freq_hz)
    → QM runtime: LO + IF = RF
```

Experiments resolve frequencies via `ExperimentBase._resolve_readout_frequency()` / `_resolve_qubit_frequency()`, applying them through `ProgramBuildResult.resolved_frequencies` which the base class commits to hardware before execution.

---

## 5. Where Calibration Values Are Injected

### Injection Sites

| What | Where | Source |
|------|-------|--------|
| Readout threshold | `measureMacro._ro_disc_params["threshold"]` | `CalibrationStore.get_discrimination()` |
| Readout angle | `measureMacro._ro_disc_params["angle"]` | `CalibrationStore.get_discrimination()` |
| IQ demod weights | `measureMacro._demod_weight_sets` | `POM.get_pulseOp_by_element_op().int_weights_mapping` |
| Qubit frequency | `HardwareController.set_element_fq()` | `CalibrationStore.get_frequencies()` or `cQED_attributes` |
| Readout frequency | `HardwareController.set_element_fq()` | `CalibrationStore.get_frequencies()` |
| Pulse amplitudes | `play(op * amp(gain), el)` | Runtime sweep or `GateTuningStore.resolve()` |
| DRAG alpha | `play(x180 * amp(1,0,0,a), el)` | Sweep parameter or `CalibrationStore.get_pulse_calibration()` |
| Fock-resolved IFs | `update_frequency(qb_el, fock_if)` | `cQED_attributes.fock_fqs` → CalibrationStore |
| Thermalization time | `wait(int(qb_therm_clks))` | `cQED_attributes.qb_therm_clks` → CalibrationStore |
| Confusion matrix | `ExperimentBase.get_confusion_matrix()` | `CalibrationStore.get_readout_quality()` |
| Gate tuning corrections | `CircuitRunner._apply_gate_tuning()` | `GateTuningStore.resolve()` |

### Calibration → Gate Hardware Chain

```
CalibrationStore → cQED_attributes (context_snapshot)
    → HardwareContext.attributes
    → GateHardware.waveforms(hw_ctx)
    → POM.register_pulse_op()
    → QUA play(op, element)
```

---

## 6. Where Measurement Streams Are Defined

### Stream Declaration Pattern

Every builder declares streams at the program top:
```python
I = declare(fixed)
Q = declare(fixed)
I_st = declare_stream()
Q_st = declare_stream()
n_st = declare_stream()
# Optional:
state = declare(bool)
state_st = declare_stream()
```

### Stream Processing Patterns

| Pattern | Use Case | Example |
|---------|----------|---------|
| `.buffer(N).average().save("I")` | 1D averaged sweep | Spectroscopy, T1, T2 |
| `.buffer(N1).buffer(N2).average().save("I")` | 2D averaged sweep | Chevron, DRAG, Fock-resolved |
| `.save_all("I")` | Single-shot data | IQ blobs, butterfly |
| `.buffer(len(seqs)).average().save("I")` | RB sequence averaging | Randomized benchmarking |

### Measurement Emission

~95% of builders call:
```python
measureMacro.measure(targets=[I, Q])                    # Without state
measureMacro.measure(with_state=True, targets=[I, Q], state=state)  # With discrimination
```

The newer path (used by `temporal_rabi`, `power_rabi`):
```python
emit_measurement_spec(MeasureSpec(kind="iq", acquire="full"), targets=[I, Q], ...)
```

### MeasureSpec / MeasureGate (Measurement Abstraction)

```python
@dataclass(frozen=True)
class MeasureSpec:
    kind: str          # "iq", "discriminate", "butterfly", "adc"
    acquire: str       # "full", "sliced"
    policy: str        # "none", "BLOBS", "ZSCORE", ...
    policy_kwargs: dict
    calibration_snapshot: dict | None

@dataclass(frozen=True)
class MeasureGate:
    target: str        # QM readout element
    spec: MeasureSpec
```

---

## 7. Existing Gate System

### Architecture

The `gates/` package provides a **model/hardware split** for gate simulation and hardware execution:

```
gates/
├── gate.py          → Gate(model, hw) — combined object
├── model_base.py    → GateModel (ABC) — pure simulation
├── hardware_base.py → GateHardware (ABC) — QUA emission
├── contexts.py      → ModelContext, NoiseConfig, HardwareContext
├── sequence.py      → GateSequence — ordered composition
├── models/          → Concrete gate models
│   ├── qubit_rotation.py → QubitRotationModel
│   ├── displacement.py   → DisplacementModel
│   ├── snap.py           → SNAPModel
│   └── sqr.py            → SQRModel
├── hardware/        → Concrete hardware backends
│   ├── qubit_rotation.py → QubitRotationHardware
│   ├── displacement.py   → DisplacementHardware
│   ├── snap.py           → SNAPHardware
│   └── sqr.py            → SQRHardware
├── noise.py         → QubitT1T2Noise
├── fidelity.py      → entanglement_fidelity, avg_gate_fidelity
├── liouville.py     → Kraus/superop conversions
├── cache.py         → ModelCache
└── free_evolution.py → Dispersive dressing
```

### What These Gates Are

These are **simulation-first gate objects** for optimization and fidelity estimation:
- `GateModel.unitary()` computes ideal unitaries in qubit⊗cavity Hilbert space
- `GateModel.kraus()` adds T1/T2 noise via Kraus operators
- `GateModel.superop()` returns Liouville superoperators
- `GateHardware.build()` registers waveforms in POM
- `GateHardware.play()` emits `qua.play(op, target)` inside QUA program context
- `GateSequence.superop()` composes multiple gates' channel maps

### What These Gates Are NOT

- Not physics-intent gates (they carry waveform-level detail)
- Not composable circuit elements (no automatic calibration resolution)
- Not protocol building blocks (no concept of Ramsey = R90 → Idle → R90)
- No measurement capability (measurement is separate via `measureMacro`)
- No calibration-backed default parameters (require explicit construction)

### Gate Registration System

Both models and hardware use auto-registration via `__init_subclass__`:
- `_MODEL_REGISTRY[gate_type] → GateModel subclass`
- `_HARDWARE_REGISTRY[gate_type] → GateHardware subclass`

This enables type-dispatch deserialization: `model_from_dict(d)` and `hardware_from_dict(d, hw_ctx)`.

---

## 8. Existing CircuitRunner

### Location: `programs/circuit_runner.py`

A partial prototype that compiles `QuantumCircuit` → QUA by dispatching to legacy builder functions.

### Data Types

```python
@dataclass(frozen=True)
class Gate:
    name: str
    target: str | tuple[str, ...]
    params: dict[str, Any]
    duration_clks: int | None
    tags: tuple[str, ...]
    instance_name: str | None

@dataclass(frozen=True)
class QuantumCircuit:
    name: str
    gates: tuple[Gate, ...]
    metadata: dict[str, Any]

@dataclass(frozen=True)
class SweepAxis:
    key: str
    values: np.ndarray

@dataclass(frozen=True)
class SweepSpec:
    axes: tuple[SweepAxis, ...]
    averaging: int

@dataclass(frozen=True)
class CircuitBuildResult:
    name: str
    program: Any
    sweep: SweepSpec
    readout_snapshot: dict | None
    metadata: dict
```

**Note:** `Gate` in `circuit_runner.py` is a *different class* from `Gate` in `gates/gate.py`. The circuit runner's Gate is a lightweight intent descriptor; the simulation Gate carries a full model + hardware backend.

### Supported Circuits (Hardcoded)

| Circuit Name | Dispatch Method | Delegates To |
|--------------|----------------|--------------|
| `"power_rabi"` | `_compile_power_rabi()` | `cQED_programs.power_rabi()` |
| `"t1"` | `_compile_t1()` | `cQED_programs.T1_relaxation()` |
| `"readout_ge_discrimination"` | `_compile_ge()` | `cQED_programs.iq_blobs()` |
| `"readout_butterfly"` | `_compile_butterfly()` | `cQED_programs.readout_butterfly_measurement()` |
| `"xy_pair"` | `_compile_xy_pair()` | `cQED_programs.all_xy()` |

### Circuit Factory Functions

```python
make_power_rabi_circuit(...)      → (QuantumCircuit, SweepSpec)
make_t1_circuit(...)              → (QuantumCircuit, SweepSpec)
make_ge_discrimination_circuit(.) → (QuantumCircuit, SweepSpec)
make_butterfly_circuit(...)       → (QuantumCircuit, SweepSpec)
make_xy_pair_circuit(...)         → (QuantumCircuit, SweepSpec)
```

### Visualization

- `QuantumCircuit.draw_logical()` — Matplotlib circuit diagram
- `QuantumCircuit.draw_pulses(runner)` → `CircuitRunner.visualize_pulses()` — Simulated or timing-model pulse waveforms

### GateTuning Integration

`CircuitRunner._apply_gate_tuning()` queries `GateTuningStore` for per-operation corrections and applies `amplitude_scale` to gain sweeps.

### Limitations

1. Only 5 hardcoded circuit names — not extensible
2. Compilation dispatches to monolithic builder functions (no gate-by-gate lowering)
3. No calibration-backed parameter default resolution on gates
4. No circuit composition or protocol abstraction
5. `Gate` type in circuit_runner is disconnected from `Gate` in `gates/`
6. No measurement schema tracking on circuits
7. No resolution report generation

---

## 9. Calibration Resolution Logic

### CalibrationStore (`calibration/store.py`)

Single JSON-backed store with typed Pydantic models (schema v5.1.0).

**Key Access Patterns:**
```python
store.get_cqed_params(alias)        → CQEDParams (unified physics)
store.get_frequencies(element)       → ElementFrequencies (LO/IF/RF)
store.get_discrimination(element)    → DiscriminationParams (threshold, angle)
store.get_readout_quality(element)   → ReadoutQuality (F, Q, V, confusion)
store.get_pulse_calibration(el, op)  → PulseCalibration (amp, length, drag)
store.get_coherence(element)         → CoherenceParams (T1, T2)
store.get_fit(element, kind)         → FitRecord
```

**Alias Resolution:**
- `alias_index` maps human names → physical channel IDs
- `_dual_lookup()` tries alias then direct key
- Convention: `"qubit"`, `"readout"`, `"storage"` → physical element names

### Experiment Resolution Flow

```
ExperimentBase.resolve_param(name, override=, calibration_value=, default=)
    → Records source provenance in _resolved_param_trace
    → Returns: override > calibration > default > raise ValueError

ExperimentBase._resolve_qubit_frequency()
    → CalibrationStore.get_frequencies(qb_el).qubit_freq

ExperimentBase.get_therm_clks(channel)
    → CalibrationStore via _calibration_cqed_value(alias, field)
    → Fallback to attr object
```

### Gate-Level Calibration (Current)

Gate hardware implementations consume calibration indirectly:
```
HardwareContext.attributes (= cQED_attributes snapshot)
    → attrs.st_chi, attrs.b_alpha, attrs.dt_s, attrs.fock_fqs, ...
    → GateHardware.waveforms(hw_ctx) uses these for synthesis
```

There is **no direct CalibrationStore access from gate objects**. The `HardwareContext` acts as an intermediary, providing a "snapshot" of the current calibration state via `cQED_attributes`.

---

## 10. Patch / Update Flow

### Pipeline

```
Experiment.run()       → Artifact (raw data + meta)
    → CalibrationOrchestrator.persist_artifact()    → NPZ + JSON on disk
    → CalibrationOrchestrator.analyze(exp, artifact) → CalibrationResult
        → Quality gate: r² > 0.5, fit.success == True
    → CalibrationOrchestrator.build_patch(result)   → Patch (list of UpdateOps)
        → Dispatched to per-kind patch rules
    → CalibrationOrchestrator.apply_patch(patch, dry_run=True)
        → Preview: shows old/new values
    → CalibrationOrchestrator.apply_patch(patch, dry_run=False)
        → Snapshot store → Apply mutations → Save JSON → Sync measureMacro → Record tag
        → On failure: automatic rollback
```

### Update Operations

| Operation | Effect |
|-----------|--------|
| `SetCalibration` | Dotted-path write to CalibrationStore |
| `SetPulseParam` | Updates PulseCalibration field |
| `SetMeasureWeights` | Registers integration weights in POM |
| `PersistMeasureConfig` | Saves measureConfig.json |
| `SetMeasureDiscrimination` | Updates measureMacro discrimination params |
| `SetMeasureQuality` | Updates measureMacro quality params |
| `TriggerPulseRecompile` | Calls `session.burn_pulses()` |

### Patch Rules

| Rule | Trigger Kind | Patches |
|------|-------------|---------|
| `PiAmpRule` | `"pi_amp"` | Reference pulse amplitude + recompile |
| `T1Rule` | `"t1"` | CQEDParams.T1 |
| `T2RamseyRule` | `"t2_ramsey"` | CQEDParams.T2_ramsey + optional frequency |
| `T2EchoRule` | `"t2_echo"` | CQEDParams.T2_echo |
| `FrequencyRule` | configurable | CQEDParams.{qubit,storage,resonator}_freq |
| `DragAlphaRule` | `"drag_alpha"` | PulseCalibration.drag_coeff + recompile |
| `DiscriminationRule` | `"ReadoutGEDiscrimination"` | discrimination params |
| `ReadoutQualityRule` | `"ReadoutButterflyMeasurement"` | quality params |
| `PulseTrainRule` | `"pulse_train"` | Corrected amplitude + phase_offset + recompile |

---

## 11. Artifact Persistence

### ArtifactManager

- Storage: `<experiment_path>/artifacts/<build_hash>/`
- Persists: `session_state.json`, `generated_config.json`, arbitrary JSON/MD artifacts
- JSON writes use `sanitize_mapping_for_json()` to strip large arrays
- Keyed by SessionState `build_hash` (SHA-256 of hardware + calibration + pulse_specs)

### SessionState

Immutable frozen dataclass computed at `session.open()`:
- `build_hash`: SHA-256 first 12 hex chars over source-of-truth files
- Any calibration change → different hash → different artifact directory
- Includes: hardware.json, calibration.json, pulse_specs.json contents

### Persistence Rules

- Raw/shot-level arrays are dropped from JSON (tracked in `_persistence.dropped_fields`)
- Numeric arrays > 8192 elements are dropped
- Complex numbers → `{re, im}` dict
- All JSON writes go through `sanitize_mapping_for_json()`

---

## 12. Duplicated Logic & Pain Points

### 1. Universal QUA Boilerplate

Every builder function repeats:
```python
with program() as prog:
    n = declare(int); I = declare(fixed); Q = declare(fixed)
    I_st = declare_stream(); Q_st = declare_stream(); n_st = declare_stream()
    with for_(n, 0, n < n_avg, n + 1):
        wait(int(therm_clks))
        ... body ...
        measureMacro.measure(targets=[I, Q])
        save(I, I_st); save(Q, Q_st)
    save(n, n_st)
    with stream_processing():
        I_st.buffer(N).average().save("I")
        ...
```

**Impact**: ~50 copies of this boilerplate. Any change to stream naming, variable typing, or processing shape must be replicated everywhere.

### 2. Bindings Resolution Boilerplate

Every builder function accepting `bindings` has an identical 5-line block:
```python
if bindings is not None:
    from ...core.bindings import ConfigBuilder
    _names = ConfigBuilder.ephemeral_names(bindings)
    qb_el = qb_el or _names.get("qubit", "__qb")
elif qb_el is None:
    raise ValueError(...)
```

**Impact**: Duplicated across all ~50 builders.

### 3. measureMacro Singleton Coupling

~95% of builders depend on `measureMacro.measure()`, a mutable singleton. This makes testing difficult, introduces hidden state, and prevents parallel experiment construction.

### 4. Disconnected Gate Types

- `gates/gate.py` → `Gate(model: GateModel, hw: GateHardware)` — for optimization/simulation
- `programs/circuit_runner.py` → `Gate(name, target, params, ...)` — for circuit description
- `programs/measurement.py` → `MeasureGate(target, spec)` — for measurement abstraction
- `builders/simulation.py` — uses `Gate` from `gates/` directly with `gate.play()`

These three gate concepts are not unified.

### 5. Frequency Resolution Scattered

Frequency management happens in multiple places:
- `ExperimentBase.set_standard_frequencies()`
- `ExperimentBase._resolve_readout_frequency()` / `_resolve_qubit_frequency()`
- `FrequencyPlan.apply(hw)` (binding-driven)
- `update_frequency(element, if_freq)` inside QUA programs (for sweeps)
- `HardwareController.set_element_fq()`

### 6. No Measurement Schema on Circuits

Circuits don't track what readout streams they produce. The stream schema is implicit in each builder function and must be manually matched by the experiment's `process()` method.

---

## 13. Integration Constraints

### Must NOT Break

| System | Constraint |
|--------|-----------|
| `SessionState` | Build hash computation unchanged; immutable post-construction |
| `CalibrationStore` | API stable; alias resolution unchanged |
| `CalibrationOrchestrator` | Patch cycle pipeline preserved |
| `ExperimentBase` | `_build_impl()` / `build_program()` / `run()` / `analyze()` contract |
| `ProgramBuildResult` | Frozen structure is the program artifact contract |
| `measureMacro` | Must remain available for legacy experiments |
| `PulseOperationManager` | Waveform/pulse registration API stable |
| `artifact_manager` | Build-hash-keyed persistence unchanged |

### Must Coexist With

| Component | How |
|-----------|-----|
| All 26 existing experiment classes | New gate architecture is additive |
| Legacy `programs/builders/*` | New circuit compilation path is parallel |
| Existing `gates/` simulation system | Extend, don't replace |
| `GateTuningStore` | Integrate into new gate resolution |

### Protocol Contracts to Respect

1. **`Experiment` protocol** — `name`, `build_program()`, `simulate()`, `run()`, `process()`
2. **`PulseManager` protocol** — `add_waveform()`, `add_pulse()`, `burn_to_config()`
3. **`ProgramRunner` protocol** — `run_program()`, `simulate()`
4. **`HardwareController` protocol** — `set_element_fq()`, `set_element_lo()`, `get_element_lo()`, `get_element_if()`

### Frequency Management
- New architecture should use `FrequencyPlan` for atomic frequency setting
- Resolved frequencies must appear in `ProgramBuildResult.resolved_frequencies`

### Calibration Flow Direction
- Always: CalibrationStore → bindings/gates (never reverse from gate code)
- New gates should read calibration via typed getters, never write

---

## 14. Recommended Architecture Insertion Points

### New Module Layout

```
qubox_v2_legacy/gates/                     ← EXISTING (simulation/optimization)
qubox_v2_legacy/gates/intent/              ← NEW: Physics-intent gate types
    ├── __init__.py
    ├── base.py                     ← IntentGate ABC
    ├── qubit_rotation.py           ← QubitRotation gate
    ├── sqr.py                      ← SQR gate
    ├── displacement.py             ← Displacement gate
    ├── idle.py                     ← Idle gate
    ├── measure.py                  ← Measure gate
    ├── frame_update.py             ← FrameUpdate gate
    └── conditional.py              ← ConditionalGate wrapper

qubox_v2_legacy/gates/protocols/           ← NEW: Reusable protocol generators
    ├── __init__.py
    ├── base.py                     ← Protocol ABC
    ├── ramsey.py                   ← Ramsey protocol
    ├── echo.py                     ← Echo protocol
    └── active_reset.py             ← Active reset protocol

qubox_v2_legacy/gates/circuit/             ← NEW: Circuit composition
    ├── __init__.py
    ├── circuit.py                  ← Circuit type with measurement schema
    └── runner.py                   ← NEW CircuitRunner (gate-driven lowering)

qubox_v2_legacy/tests/gate_architecture/   ← NEW: Tests
    ├── __init__.py
    ├── test_gates.py
    ├── test_protocols.py
    ├── test_circuit.py
    └── test_runner.py
```

### Calibration Resolution Strategy

New intent gates should resolve parameters via:
1. **Explicit override** (user-provided)
2. **CalibrationStore getter** (typed, via `CalibrationResolver`)
3. **cQED_attributes fallback** (for backward compatibility)

This matches the existing `ExperimentBase.resolve_param()` pattern.

### QUA Lowering Strategy

The new `CircuitRunner` should:
1. Walk the circuit gate-by-gate
2. For each gate, resolve calibration defaults
3. Validate amplitude/timing constraints
4. Emit QUA primitives (reusing macro utilities where appropriate)
5. Track measurement streams in the circuit's schema

### Output Compatibility

New circuits must produce either:
- `CircuitBuildResult` (existing, from `circuit_runner.py`) for circuit-based flows
- `ProgramBuildResult` (from `experiments/result.py`) for experiment-based flows

Both paths ultimately produce a QUA program + metadata that flows through `ProgramRunner.run_program()`.

### Bridge to Existing Simulation Gates

The intent-level `QubitRotation` gate should be able to reference the existing `QubitRotationModel` for simulation fidelity estimation, and `QubitRotationHardware` for waveform synthesis. The lowering compiler can dispatch to these when available.

---

## Appendix A: File Inventory

### Programs Layer

| File | Lines | Role |
|------|-------|------|
| `programs/api.py` | ~100 | Re-export surface for all builders |
| `programs/circuit_runner.py` | 654 | Circuit → QUA compiler (5 circuits) |
| `programs/measurement.py` | ~200 | MeasureSpec, MeasureGate, emit_measurement_spec |
| `programs/gate_tuning.py` | ~300 | GateTuningStore, GateFamily, GateTuningRecord |
| `programs/macros/measure.py` | ~2137 | measureMacro singleton |
| `programs/macros/sequence.py` | ~697 | sequenceMacros (Ramsey, Echo, conditional reset) |
| `programs/builders/spectroscopy.py` | ~350 | 7 spectroscopy builders |
| `programs/builders/time_domain.py` | ~600 | 10 time-domain builders |
| `programs/builders/readout.py` | ~500 | 7 readout builders |
| `programs/builders/calibration.py` | ~400 | 5 calibration builders |
| `programs/builders/cavity.py` | ~800 | 11 cavity builders |
| `programs/builders/tomography.py` | ~300 | 2 tomography builders |
| `programs/builders/utility.py` | ~150 | 2 utility builders |
| `programs/builders/simulation.py` | ~100 | 1 gate-based simulation builder |

### Gates Layer

| File | Lines | Role |
|------|-------|------|
| `gates/gate.py` | ~35 | Gate(model, hw) combined object |
| `gates/model_base.py` | ~150 | GateModel ABC, registry |
| `gates/hardware_base.py` | ~80 | GateHardware ABC, registry |
| `gates/sequence.py` | ~35 | GateSequence composition |
| `gates/contexts.py` | ~80 | ModelContext, NoiseConfig, HardwareContext |
| `gates/models/*.py` | ~600 | 4 concrete models |
| `gates/hardware/*.py` | ~800 | 4 concrete hardware backends |
| `gates/noise.py` | ~150 | Noise models |
| `gates/fidelity.py` | ~80 | Fidelity metrics |
| `gates/liouville.py` | ~60 | Channel math |
| `gates/cache.py` | ~60 | ModelCache |
| `gates/free_evolution.py` | ~100 | Dispersive dressing |

### Calibration Layer

| File | Lines | Role |
|------|-------|------|
| `calibration/store.py` | ~500 | CalibrationStore persistence |
| `calibration/orchestrator.py` | ~400 | Patch pipeline |
| `calibration/patch_rules.py` | ~500 | Per-kind patch rules |
| `calibration/models.py` | ~400 | Pydantic calibration models |
| `calibration/contracts.py` | ~150 | Artifact, CalibrationResult, Patch |
| `calibration/transitions.py` | ~100 | Pulse naming conventions |
| `calibration/history.py` | ~80 | Snapshot utilities |

---

## Appendix B: Key Interfaces for New Architecture

### ExperimentBase (contract to match)
```python
class ExperimentBase:
    def build_program(**params) -> ProgramBuildResult   # Immutable build
    def simulate(sim_config, **params) -> SimulationResult
    def run(**params) -> RunResult
    def analyze(result, **params) -> AnalysisResult
    def plot(analysis, **kwargs) -> Figure
    def resolve_param(name, override, calibration_value, default) -> Any
```

### CalibrationStore (getters to use)
```python
class CalibrationStore:
    def get_cqed_params(alias) -> CQEDParams
    def get_frequencies(element) -> ElementFrequencies
    def get_discrimination(element) -> DiscriminationParams
    def get_readout_quality(element) -> ReadoutQuality
    def get_pulse_calibration(element, op) -> PulseCalibration
    def get_coherence(element) -> CoherenceParams
```

### ProgramBuildResult (output contract)
```python
@dataclass(frozen=True)
class ProgramBuildResult:
    program: Any                          # QUA program
    n_total: int
    processors: tuple[Callable, ...]
    experiment_name: str
    params: dict
    resolved_frequencies: dict[str, float]
    resolved_parameter_sources: dict
    bindings_snapshot: dict | None
```

---

*End of survey. No implementation has been written. This document establishes the baseline for PHASE 1 architecture design.*
