# Design Principles

Core values guiding qubox's architecture and development.

## Priority Hierarchy

When two policies conflict, the higher-numbered priority wins:

| Priority | Principle | Meaning |
|----------|-----------|---------|
| 1 | **Physical correctness** | Compiled program behavior must match intent. A mismatch is never silently acceptable. |
| 2 | **Backward compatibility** | Do not rename or remove public APIs without explicit approval. |
| 3 | **Documentation consistency** | If behavior changes, docs change in the same task. |
| 4 | **Minimal change scope** | The smallest correct change wins. No unrelated cleanup. |
| 5 | **Reproducibility** | Changes must be explainable, inspectable, and re-runnable. |
| 6 | **Code clarity** | Prefer readable, structurally consistent code over clever abstraction. |

## Key Design Decisions

### 1. Channel Binding API

Physical ports are stable identity objects. Logical bindings map experiments to ports. This survives hardware rewiring without code changes.

```python
from qubox.core.bindings import ChannelRef, ReadoutBinding

transmon = ChannelRef(controller=1, port=1)
readout = ReadoutBinding(channel=transmon, frequency=7.2e9)
```

### 2. Transactional Calibration Patches

All calibration updates are gated by `FitResult.success`. A `Patch` is a list of `UpdateOp`s that either all succeed or are all rejected:

```python
patch = Patch(ops=[
    UpdateOp(field="qubit_freq", value=4.85e9),
    UpdateOp(field="pi_amp", value=0.312),
])
# Only committed if ALL ops pass validation
orchestrator.apply(patch, reason="rabi_calibration")
```

### 3. Semantic IR

The `Sequence` intermediate representation is hardware-agnostic. Experiments define operations in terms of physics, not QUA syntax:

```python
from qubox import Sequence, Operation

seq = Sequence([
    Operation("x180", element="transmon"),
    Operation("readout", element="resonator"),
])
```

This enables testing without hardware and future backend portability.

### 4. Two-Phase Calibration Commit

Every calibration result always persists an artifact (raw data + fit). The store update is conditional on fit quality. This means you never lose data even when a calibration fails.

### 5. Lazy Backend Resolution

A `Session` can exist without an active hardware connection. This allows offline analysis, configuration review, and test scenarios.

### 6. Registry-Based Discovery

`ExperimentLibrary`, `OperationLibrary`, and the pipeline registry use runtime registration. New experiments slot in without modifying central dispatchers.

## The QUA Validation Rule

!!! warning "Non-negotiable"
    **The compiled QUA program is the source of truth, not the written code.**

Every QUA-touching change must be validated:

1. **Compile** — must finish in < 1 minute
2. **Simulate** — on the hosted server (`10.157.36.68`, `Cluster_2`)
3. **Verify** — pulse ordering, timing, control flow, measurements

Mismatches between written intent and compiled behavior must be reported explicitly. They are never silently accepted.

## Target Users

The primary users are **experimental physicists**, not software engineers. This drives several choices:

- Experiment definitions should read like physics, not boilerplate
- Expose only what the user needs to configure
- Pulse sequences, timing, and control flow must be readable and simulatable
- Every experiment run must be re-runnable with the same result from the same config
