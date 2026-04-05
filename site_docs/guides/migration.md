# Migration Guide

Migrating from the legacy `qubox_v2_legacy` codebase to qubox v3.

## Overview

qubox v3 replaced the legacy `qubox_v2_legacy` package with a restructured, modular
architecture. Both `qubox_v2_legacy` and `qubox.legacy` have been fully removed.
All code now lives under `qubox`, `qubox_tools`, or `qubox_lab_mcp`.

## Import Changes

### Package Rename

```python
# OLD — do not use (both packages have been removed)
# from qubox_v2_legacy.experiments import QubitSpectroscopy
# from qubox.legacy.experiments import QubitSpectroscopy

# CURRENT — use the canonical qubox surface
from qubox.experiments import QubitSpectroscopy
```

### Analysis Package Merge

The `qubox.analysis` package has been merged into `qubox_tools`:

| Old Import | New Import |
|-----------|-----------|
| `from qubox.analysis.fitting import generalized_fit` | `from qubox_tools.fitting.routines import generalized_fit` |
| `from qubox.analysis.output import Output` | `from qubox_tools.data.containers import Output` |
| `from qubox.analysis.cQED_models import *` | `from qubox_tools.fitting.cqed import *` |
| `from qubox.analysis.cQED_plottings import *` | `from qubox_tools.plotting.cqed import *` |
| `from qubox.analysis.analysis_tools import *` | `from qubox_tools.algorithms.transforms import *` |
| `from qubox.analysis.algorithms import *` | `from qubox_tools.algorithms.core import *` |
| `from qubox.analysis.post_process import *` | `from qubox_tools.algorithms.post_process import *` |
| `from qubox.analysis.post_selection import *` | `from qubox_tools.algorithms.post_selection import *` |
| `from qubox.analysis.metrics import *` | `from qubox_tools.algorithms.metrics import *` |
| `from qubox.analysis.calibration_algorithms import *` | `from qubox_tools.fitting.calibration import *` |

### PulseOp

```python
# OLD
from qubox.analysis.pulseOp import PulseOp

# NEW
from qubox.core.pulse_op import PulseOp
```

## DeviceMetadata (replaces cQED_attributes)

The `cQED_attributes` dictionary has been replaced by `DeviceMetadata`:

```python
# OLD
attrs = session.cQED_attributes
qubit_freq = attrs['qubit_freq']

# NEW
meta = session.metadata
qubit_freq = meta.qubit_freq_hz
```

!!! warning
    `session.<attr>` forwarding (e.g., `session.qubit_freq`) still works but emits
    a deprecation warning. Migrate to `session.metadata.<attr>`.

## Notebook Surface

### Two-Tier Imports

```python
# Tier 1: Day-to-day experiment work (~65 symbols)
from qubox.notebook import (
    PowerRabi, QubitSpectroscopy, CalibrationOrchestrator, ...
)

# Tier 2: Infrastructure and store internals (~45 symbols)
from qubox.notebook.advanced import (
    CalibrationStore, CQEDParams, FitRecord, ...
)
```

## Workflow Extraction

Workflow utilities moved from notebook to standalone package:

```python
# OLD — notebook-only
from qubox.notebook.workflow import save_checkpoint

# NEW — works anywhere
from qubox.workflow import save_stage_checkpoint
```

## Experiment Migration Strategy

1. **Read the legacy experiment** — Understand pulse sequence, parameters, and expected output
2. **Implement in qubox** — Follow `ExperimentBase` lifecycle pattern
3. **Validate equivalence** — Compile + simulate, compare output vs. legacy
4. **Create a notebook** — Add a numbered notebook demonstrating the experiment
5. **Update docs** — `CHANGELOG.md`, `API_REFERENCE.md`

## Breaking Changes in v3

| Change | Action Required |
|--------|----------------|
| `qubox_v2_legacy` removed | Import from `qubox.*` directly |
| `qubox.legacy` removed | Import from `qubox.*` directly |
| `qubox.analysis` → `qubox_tools` | Update imports |
| `cQED_attributes` → `DeviceMetadata` | Use `session.metadata` |
| `PulseOp` location changed | Import from `qubox.core.pulse_op` |
| Notebook surface split | Use `qubox.notebook` or `qubox.notebook.advanced` |
