# API Reference

Complete reference for the qubox public API.

## Top-Level Exports

```python
import qubox

qubox.__version__  # "3.0.0"
```

| Symbol | Type | Description |
|--------|------|-------------|
| `Session` | class | Primary entry point — session lifecycle, hardware, calibration |
| `Sequence` | class | Hardware-agnostic operation sequence |
| `Operation` | class | Single operation in a sequence |
| `Condition` | class | Conditional branching in sequences |
| `SweepAxis` | class | Sweep dimension definition |
| `SweepPlan` | class | Multi-axis sweep plan |
| `AcquisitionSpec` | class | Measurement acquisition specification |
| `QuantumCircuit` | class | Gate-level circuit abstraction |
| `QuantumGate` | class | Individual quantum gate |
| `ExecutionRequest` | class | Frozen execution specification |
| `ExperimentResult` | class | Mutable result container |
| `CalibrationSnapshot` | class | Point-in-time calibration state |
| `CalibrationProposal` | class | Proposed calibration changes |
| `DeviceMetadata` | class | Frozen device parameter access (replaces `cQED_attributes`) |

## Import Patterns

=== "Session-based (recommended)"

    ```python
    from qubox import Session

    session = Session.open(...)
    result = session.exp.qubit.spectroscopy(...)
    ```

=== "Notebook imports"

    ```python
    from qubox.notebook import (
        PowerRabi, CalibrationOrchestrator,
        open_shared_session, require_shared_session,
    )
    ```

=== "Infrastructure"

    ```python
    from qubox.notebook.advanced import (
        CalibrationStore, FitRecord, SampleRegistry,
    )
    ```

=== "Portable workflow"

    ```python
    from qubox.workflow import (
        save_stage_checkpoint, fit_quality_gate,
        preview_or_apply_patch_ops,
    )
    ```

## Sections

| Page | Content |
|------|---------|
| [Session](session.md) | Session lifecycle, template experiments, operations |
| [Sequence IR](sequence.md) | Operations, conditions, sweeps, acquisitions |
| [Experiments](experiments/index.md) | All 40+ experiment classes |
| [Calibration](calibration/index.md) | Store, orchestrator, patch rules, models |
| [Workflow](workflow.md) | Stage checkpoints, fit gates, helpers |
| [Notebook Surface](notebook.md) | Two-tier notebook import surface |
| [Hardware](hardware.md) | Config engine, controllers, program runner |
| [Gates & Circuits](gates.md) | Gate models, hardware implementations, synthesis |
