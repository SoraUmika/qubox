# qubox Repository

This repository currently contains three relevant Python package surfaces:

- `qubox_v2`: the active execution-facing cQED framework for sessions, experiments, calibration orchestration, and QM / QUA interaction
- `qubox_tools`: the analysis-facing package for fitting, plotting, post-processing, and reusable optimization helpers
- `qubox`: a partial higher-level facade from the earlier refactor pass; it is not yet a full replacement for `qubox_v2`

## Current Recommendation

Use `qubox_v2` for experiment execution and `qubox_tools` for reusable analysis.

```python
from qubox_v2.experiments.session import SessionManager
from qubox_tools import generalized_fit
```

## Runtime Scope

`qubox_v2` remains the working lab stack for:

- session lifecycle
- experiment classes
- calibration storage and orchestration
- backend compilation and execution
- artifact generation

## Analysis Scope

`qubox_tools` is now the canonical home for:

- fitting models and routines
- plotting helpers
- post-processing transforms
- analysis algorithms
- optimization utilities used by calibration/analysis workflows

Legacy imports under `qubox_v2.analysis.*` and `qubox_v2.optimization.*` are preserved as compatibility wrappers.

## Quick Start

Execution:

```python
from qubox_v2.experiments.session import SessionManager

session = SessionManager(
    sample_id="sampleA",
    cooldown_id="cd_2026_03_13",
    registry_base="E:/qubox",
    qop_ip="10.157.36.68",
    cluster_name="Cluster_2",
).open()
```

Analysis:

```python
import numpy as np
import qubox_tools as qt

x = np.linspace(-1.0, 1.0, 101)
y = qt.fitting.models.gaussian_model(x, 0.15, 0.2, 0.8, 0.1)
popt, _ = qt.generalized_fit(
    x,
    y,
    qt.fitting.models.gaussian_model,
    p0=[0.0, 0.25, 1.0, 0.0],
)
```

## Documentation Map

- [API Reference](API_REFERENCE.md)
- [Refactor Verification](docs/qubox_refactor_verification.md)
- [Analysis Split](docs/qubox_tools_analysis_split.md)
- [qubox Facade Architecture](docs/qubox_architecture.md)
- [qubox Facade Migration Guide](docs/qubox_migration_guide.md)
- [Original Refactor Proposal](docs/qubox_experiment_framework_refactor_proposal.md)

## Python Policy

Preferred Python version: `3.12.13`.

Fallback version currently allowed for repository compatibility: `3.11.8`.

This refactor and verification pass was validated with:

- `E:\Program Files\Python311\python.exe`
- Python `3.11.8`
