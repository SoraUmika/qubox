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
17. [Compatibility Layer (qubox.compat)](#17-compatibility-layer-quboxcompat)
18. [qubox_tools — Analysis Toolkit](#18-qubox_tools--analysis-toolkit)
19. [Legacy Internals (qubox_v2_legacy)](#19-legacy-internals-qubox_v2_legacy)
20. [Examples and Minimal Usage Patterns](#20-examples-and-minimal-usage-patterns)
21. [Known Gaps and Inconsistencies](#21-known-gaps-and-inconsistencies)

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
- **Python**: 3.12.13 (preferred), 3.11.8 (fallback)

---

## 2. Package Architecture

### 2.1 Package Structure

```
qubox/
├── __init__.py          # Top-level public API exports
├── session/
│   ├── __init__.py
│   └── session.py       # Session class — the main entry point
├── sequence/
│   ├── __init__.py
│   ├── models.py        # Operation, Condition, Sequence
│   ├── sweeps.py        # SweepAxis, SweepPlan, SweepFactory
│   └── acquisition.py   # AcquisitionSpec, AcquisitionFactory
├── operations/
│   ├── __init__.py
│   └── library.py       # OperationLibrary — semantic gate/pulse operations
├── circuit/
│   ├── __init__.py
│   └── models.py        # QuantumCircuit, QuantumGate
├── data/
│   ├── __init__.py
│   └── models.py        # ExecutionRequest, ExperimentResult
├── calibration/
│   ├── __init__.py
│   └── models.py        # CalibrationSnapshot, CalibrationProposal
├── analysis/
│   ├── __init__.py
│   └── pipelines.py     # run_named_pipeline()
├── experiments/
│   ├── __init__.py
│   ├── templates/
│   │   └── library.py   # ExperimentLibrary (qubit, resonator, reset)
│   ├── workflows/
│   │   └── library.py   # WorkflowLibrary (readout)
│   └── custom/
│       └── __init__.py
├── backends/
│   ├── __init__.py
│   └── qm/
│       ├── __init__.py
│       ├── runtime.py   # QMRuntime — executes templates & custom sequences
│       └── lowering.py  # Lowers Sequence / QuantumCircuit → legacy IR
├── compat/
│   ├── __init__.py
│   └── notebook.py      # Lazy re-exports of qubox_v2_legacy classes
└── examples/
    ├── __init__.py
    └── quickstart.py    # Minimal demo script
```

### 2.2 Subpackage Summary

| Subpackage | Purpose |
|------------|---------|
| `qubox.session` | `Session` — runtime entry point; owns sweep/acquire factories, operation and experiment libraries |
| `qubox.sequence` | Intermediate representation: `Operation`, `Condition`, `Sequence`, sweep and acquisition models |
| `qubox.operations` | `OperationLibrary` — calibration-aware semantic operations (gates, waits, measurements, resets) |
| `qubox.circuit` | `QuantumCircuit` and `QuantumGate` — gate-sequence view over the shared Sequence IR |
| `qubox.data` | `ExecutionRequest` and `ExperimentResult` — run specification and result container |
| `qubox.calibration` | `CalibrationSnapshot` and `CalibrationProposal` — calibration inspection and patch proposing |
| `qubox.analysis` | `run_named_pipeline()` — lightweight named analysis pipelines for custom experiments |
| `qubox.experiments` | `ExperimentLibrary` and `WorkflowLibrary` — template-based experiment runners |
| `qubox.backends.qm` | `QMRuntime` — QM-specific execution: lowers sequences to QUA programs via legacy adapter |
| `qubox.compat` | Compatibility shims for notebooks still importing legacy classes |
| `qubox.examples` | Runnable example scripts demonstrating the API |

### 2.3 Layering

```
┌─────────────────────────────────────────────────────┐
│  User Notebook / Script                             │
│    import qubox                                     │
├─────────────────────────────────────────────────────┤
│  qubox   (public API: Session, Sequence, etc.)      │
├─────────────────────────────────────────────────────┤
│  qubox.backends.qm   (QMRuntime, lowering)          │
├─────────────────────────────────────────────────────┤
│  qubox_v2_legacy   (internal: SessionManager,       │
│    CalibrationStore, PulseFactory, ProgramRunner,   │
│    experiment classes, QUA compilation)              │
├─────────────────────────────────────────────────────┤
│  Quantum Machines QUA / OPX+ / Octave               │
└─────────────────────────────────────────────────────┘
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
    connect=True,               # open QM connection immediately
)
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
    connect: bool = True,
    **kwargs,
) -> Session
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `sample_id` | `str` | Identifier for the sample (maps to a directory under `samples/`) |
| `cooldown_id` | `str` | Identifier for the cooldown cycle |
| `registry_base` | `str \| Path \| None` | Root directory of the registry (defaults to cwd) |
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

For advanced use cases that require direct access to the `qubox_v2_legacy`
runtime (calibration store, pulse manager, hardware controller, etc.):

```python
legacy = session.legacy_session

# Examples:
calibration_store = legacy.calibration
pulse_mgr = legacy.pulse_mgr
ctx = legacy.context_snapshot()
```

Any attribute access on `session` that is not defined on `Session` itself
is transparently forwarded to `session.legacy_session` via `__getattr__`.

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
session.exp          # → ExperimentLibrary
session.exp.qubit    # → QubitExperimentLibrary
session.exp.resonator# → ResonatorExperimentLibrary
session.exp.reset    # → ResetExperimentLibrary
```

### 11.2 Template Experiments

All template experiments return an `ExperimentResult`.

#### Resonator Spectroscopy

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

#### Qubit Spectroscopy

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

#### Power Rabi

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

#### Ramsey

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

#### Active Reset Benchmark

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
from qubox.compat.notebook import CalibrationOrchestrator, Patch

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

The `qubox.analysis.run_named_pipeline()` function provides lightweight
analysis for custom experiments.

```python
from qubox.analysis import run_named_pipeline
```

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
2. **Compiles** the lowered circuit into a QUA program via `CircuitRunner.compile_v2()`.
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

## 17. Compatibility Layer (qubox.compat)

### 17.1 Purpose

`qubox.compat.notebook` provides lazy re-exports of legacy classes from
`qubox_v2_legacy` (previously `qubox_v2`) so that existing notebooks and
scripts can import from `qubox` without modification.

### 17.2 Usage

```python
from qubox.compat.notebook import (
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

    # Calibration
    CalibrationOrchestrator,
    CalibrationStore,
    Patch,

    # Session / Core
    SampleRegistry,
    SessionState,
    ExperimentContext,
    ArtifactManager,

    # Results
    RunResult,
    AnalysisResult,
    ProgramBuildResult,

    # Tools
    register_rotations_from_ref_iq,
    ensure_displacement_ops,
    kaiser_pulse_waveforms,
    drag_gaussian_pulse_waveforms,
    save_config_snapshot,
    save_run_summary,

    # Hardware / Programs
    measureMacro,
    QuboxSimulationConfig,
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

> **Migration note:** These re-exports exist for backward compatibility.
> New code should prefer the `qubox` API (`Session`, `session.exp.*`,
> `session.ops.*`, etc.) for all supported workflows.

---

## 18. qubox_tools — Analysis Toolkit

### 18.1 Import

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
| `qubox_tools.compat` | Compatibility helpers for legacy imports |

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

## 19. Legacy Internals (qubox_v2_legacy)

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
| `CircuitRunner` | `qubox_v2_legacy.programs.circuit_runner` | IR-based QUA compilation |
| `SampleRegistry` | `qubox_v2_legacy.devices` | Filesystem sample/cooldown management |
| `ExperimentContext` | `qubox_v2_legacy.core.experiment_context` | Immutable experiment identity |
| `ArtifactManager` | `qubox_v2_legacy.core.artifact_manager` | Build-hash-keyed artifact storage |
| 30+ experiment classes | `qubox_v2_legacy.experiments` | Physics-specific experiment implementations |

> **Users should not import directly from `qubox_v2_legacy`** in new code.
> Use `qubox` for the public API, and `qubox.compat.notebook` for legacy
> compatibility when needed.

### 19.1 Key Internal Concepts

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

### 19.2 Calibration JSON Structure (v5.0.0)

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

### 19.3 Sample / Cooldown Filesystem Layout

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

## 20. Examples and Minimal Usage Patterns

### 20.1 Quick Start — Template Experiment

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

### 20.2 Custom Sequence Experiment

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

### 20.3 Custom Circuit Experiment

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

### 20.4 Notebook Pattern with Legacy Compatibility

This is the pattern used in the tutorial notebook. It mixes the new `qubox`
session API with legacy experiment classes imported through `qubox.compat`:

```python
from qubox import Session
from qubox.compat.notebook import (
    ResonatorSpectroscopy,
    QubitSpectroscopy,
    PowerRabi,
    SampleRegistry,
    Patch,
    save_config_snapshot,
)

# Open session (new API)
session = Session.open(
    sample_id="post_cavity_sample_A",
    cooldown_id="cd_2025_02_22",
    registry_base="E:/qubox",
    qop_ip="10.157.36.68",
    cluster_name="Cluster_2",
    connect=True,
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

### 20.5 Analysis with qubox_tools

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

## 21. Known Gaps and Inconsistencies

### 21.1 README.md Alignment

> **Status:** Resolved. The `README.md` now correctly documents `qubox` as
> the canonical user-facing package with `from qubox import Session` examples.

### 21.2 Limited Template Adapter Coverage

Only five experiment templates are currently registered in `QMRuntime`:
- `qubit.spectroscopy`
- `resonator.spectroscopy`
- `qubit.power_rabi`
- `qubit.ramsey`
- `reset.active`

The 25+ other experiments (T1, AllXY, DRAG, Fock-resolved, tomography, etc.)
are accessible only through:
- Legacy compatibility imports (`qubox.compat.notebook`), or
- Custom sequence/circuit composition (`session.exp.custom()`).

### 21.3 qubox_v2_legacy Naming

The legacy package was renamed from `qubox_v2` to `qubox_v2_legacy` as part
of the migration. All internal references (compat layer, tests, tools) now
correctly use `qubox_v2_legacy` as the import target.

> **Status:** Resolved. The compat layer (`qubox.compat.notebook`) and all
> internal code reference `qubox_v2_legacy` consistently.

### 21.4 Sweep Axis Center Resolution

When a `SweepAxis` has a `center` token (e.g. `"q0.ge"`), the center offset
is resolved and added to the sweep values at execution time inside
`QMRuntime`, not at construction time. This means `axis.values` contains
*relative* values until the request is run.

### 21.5 Custom Experiment Sweep Integration

Sweep axes provided to `session.exp.custom()` are stored in circuit metadata
as `"sweep_axes"` but are not yet used to drive actual QUA loop sweeps.
The current implementation passes sweep metadata through and uses the
averaging count from `SweepPlan.averaging`, but the sweep variable is not
looped over in the generated QUA program. Multi-point sweeps in custom
experiments require further backend work.

### 21.6 Analysis Pipeline Simplicity

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
| `from qubox_v2.experiments import PowerRabi` | `session.exp.qubit.power_rabi(...)` or `from qubox.compat.notebook import PowerRabi` |
| `from qubox_v2.calibration import CalibrationOrchestrator` | `from qubox.compat.notebook import CalibrationOrchestrator` |
| `from qubox_v2.devices import SampleRegistry` | `from qubox.compat.notebook import SampleRegistry` |
| Direct experiment `run()` calls | Template experiments via `session.exp.*` or legacy via `qubox.compat.notebook` |

### Workflow Changes

| Old Pattern | New Pattern |
|-------------|-------------|
| `experiment = PowerRabi(session)` / `experiment.run(...)` | `session.exp.qubit.power_rabi(...)` returns `ExperimentResult` |
| `orch.run_analysis_patch_cycle(...)` | `result = session.exp.qubit.*(...); proposal = result.proposal(); proposal.apply(session)` |
| Manual `PulseOperationManager` interaction | `session.ops.*` for semantic operations |
| `session.pulse_mgr`, `session.hw` | `session.legacy_session.pulse_mgr`, `session.legacy_session.hw` |
| `session.context_snapshot()` | `session.legacy_session.context_snapshot()` or `session.context_snapshot()` (forwarded) |

### What Stays the Same

- The underlying hardware interaction (OPX+ / Octave) is unchanged.
- Calibration JSON schema (v5.0.0) is unchanged.
- `qubox_tools` for analysis is unchanged.
- Sample/cooldown filesystem layout is unchanged.
- All 30+ legacy experiment classes are still available via `qubox.compat.notebook`.

---

*End of API Reference.*
