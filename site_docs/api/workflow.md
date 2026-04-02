# Workflow

Portable workflow primitives that work in any Python context — no notebook dependency.

## Overview

`qubox.workflow` provides standalone workflow utilities extracted from the notebook layer.
These can be used in scripts, CI/CD pipelines, or notebooks.

## Stage Checkpoints

Save and restore experiment session state at named stages:

```python
from qubox.workflow import save_stage_checkpoint, load_stage_checkpoint, WorkflowConfig

config = WorkflowConfig(
    checkpoint_dir="./checkpoints",
    auto_save=True,
)

# Save checkpoint
save_stage_checkpoint(
    session=session,
    stage_name="post_spectroscopy",
    config=config,
)

# Load checkpoint
checkpoint = load_stage_checkpoint("post_spectroscopy", config=config)
```

### WorkflowConfig

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `checkpoint_dir` | `str \| Path` | `"./checkpoints"` | Directory for checkpoint files |
| `auto_save` | `bool` | `True` | Auto-save after stage completion |

### StageCheckpoint

| Field | Type | Description |
|-------|------|-------------|
| `stage_name` | `str` | Name of the completed stage |
| `timestamp` | `datetime` | When the checkpoint was created |
| `calibration_snapshot` | `dict` | CalibrationStore state at this point |
| `metadata` | `dict` | Additional context |

## Fit Quality Gates

Validate fit results before proceeding:

```python
from qubox.workflow import fit_quality_gate, fit_center_inside_window

# Check overall fit quality
passed = fit_quality_gate(
    fit_result,
    min_r_squared=0.95,
    max_relative_error=0.1,
)

# Check that fitted center is within the sweep window
in_window = fit_center_inside_window(
    fit_result,
    window_min=4.5e9,
    window_max=5.5e9,
    param_name="center_freq",
)
```

## Calibration Helpers

Preview or apply calibration patches:

```python
from qubox.workflow import preview_or_apply_patch_ops

# Preview mode — show changes without applying
preview_or_apply_patch_ops(
    store=session.store,
    ops=patch.ops,
    apply=False,
)

# Apply mode — commit changes
preview_or_apply_patch_ops(
    store=session.store,
    ops=patch.ops,
    apply=True,
    reason="spectroscopy_update",
)
```

## Pulse Seeding

Ensure required pulse calibrations exist in the store:

```python
from qubox.workflow import ensure_primitive_rotations

# Seed default pulse calibrations if missing
ensure_primitive_rotations(
    store=session.store,
    pulses=["x180", "x90", "y180", "y90"],
)
```
