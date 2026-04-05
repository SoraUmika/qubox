# Notebook Surface

Two-tier import surface designed for Jupyter notebook workflows.

## Tier 1: Essentials (`qubox.notebook`)

~65 symbols covering day-to-day experiment work:

```python
from qubox.notebook import (
    # Session management
    open_shared_session, require_shared_session,

    # Experiments (all domains)
    PowerRabi, TimeRabi, T1, T2Ramsey, T2Echo,
    QubitSpectroscopy, ResonatorSpectroscopy,
    IQBlobCalibration, AllXY, DragCalibration,

    # Calibration workflow
    CalibrationOrchestrator,
    preview_or_apply_patch_ops,

    # Workflow utilities
    save_stage_checkpoint, load_stage_checkpoint,
    fit_quality_gate,

    # Waveform generators
    drag_gaussian, kaiser_pulse, slepian_pulse,
)
```

### Categories in Essentials

| Category | Examples |
|----------|---------|
| Session | `open_shared_session`, `require_shared_session`, `close_shared_session` |
| Spectroscopy | `QubitSpectroscopy`, `ResonatorSpectroscopy`, `EFSpectroscopy` |
| Time domain | `PowerRabi`, `TimeRabi`, `T1`, `T2Ramsey`, `T2Echo`, `Chevron` |
| Calibration experiments | `IQBlobCalibration`, `AllXY`, `DragCalibration`, `RB` |
| Cavity | `StorageSpectroscopy`, `ChiRamsey`, `FockResolvedSpectroscopy` |
| Tomography | `StateTomography`, `WignerTomography` |
| SPA | `SPAFluxSweep`, `SPAPumpOptimization` |
| Calibration workflow | `CalibrationOrchestrator`, `preview_or_apply_patch_ops` |
| Workflow | `save_stage_checkpoint`, `fit_quality_gate`, `ensure_primitive_rotations` |
| Waveforms | `drag_gaussian`, `kaiser_pulse`, `slepian_pulse` |

## Tier 2: Advanced (`qubox.notebook.advanced`)

~45 infrastructure symbols for power users:

```python
from qubox.notebook.advanced import (
    # CalibrationStore internals
    CalibrationStore, CQEDParams, PulseCalibration,
    ReadoutCalibration, MixerCalibration,
    CalibrationMetadata, FitRecord,

    # Device registry
    SampleRegistry, CooldownRegistry,

    # Verification
    SchemaValidator, WaveformRegression,

    # Data artifacts
    ExperimentArtifact, AnalysisArtifact,

    # Configuration
    HardwareConfig, ControllerConfig, OctaveConfig,
)
```

### Categories in Advanced

| Category | Examples |
|----------|---------|
| Store models | `CalibrationStore`, `CQEDParams`, `PulseCalibration`, `FitRecord` |
| Data artifacts | `ExperimentArtifact`, `AnalysisArtifact` |
| Device registry | `SampleRegistry`, `CooldownRegistry` |
| Schemas | `SchemaValidator`, `WaveformRegression` |
| Configuration | `HardwareConfig`, `ControllerConfig`, `OctaveConfig` |

## Session Management

```python
from qubox.notebook import open_shared_session, require_shared_session

# Open a shared session (call once, typically in notebook 00)
session = open_shared_session(
    sample_id="sampleA",
    cooldown_id="cd_2026_03",
    registry_base="./samples",
    qop_ip="10.157.36.68",
    cluster_name="Cluster_2",
)

# In subsequent notebooks, require the shared session
session = require_shared_session()
```

!!! info "Shared Session"
    `open_shared_session` stores the session in module-level state so that subsequent
    notebooks can retrieve it with `require_shared_session()` without re-establishing
    the hardware connection.

## Notebook Workflow Runtime

`qubox.notebook.workflow` re-exports portable primitives from `qubox.workflow`
and adds shared-session notebook helpers:

```python
from qubox.notebook.workflow import (
    # Re-exported from qubox.workflow
    save_stage_checkpoint,
    load_stage_checkpoint,
    fit_quality_gate,
    preview_or_apply_patch_ops,
    ensure_primitive_rotations,

    # Notebook-specific helpers
    open_notebook_stage,            # Open a numbered-notebook stage
    build_notebook_workflow_config,  # Build notebook workflow config
    NotebookWorkflowConfig,         # Frozen config dataclass
    NotebookStageContext,            # Context from open_notebook_stage
)
```

!!! note
    For non-notebook usage, import directly from `qubox.workflow`.
