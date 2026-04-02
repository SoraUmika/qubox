# Quick Start

## Installation

qubox is installed as an editable package from the repository:

```bash
pip install -e .
```

**Requirements:**

- Python 3.12.10 (required; 3.11.8 fallback on ECE-SHANKAR-07 only)
- Quantum Machines QUA SDK (`qm-qua >= 1.1`)
- Pydantic v2

## Minimal Session

```python
from qubox import Session

session = Session.open(
    sample_id="post_cavity_sample_A",
    cooldown_id="cd_2026_03_31",
    registry_base="./samples",
    qop_ip="10.157.36.68",
    cluster_name="Cluster_2",
)
```

The `Session` object is the primary entry point. It manages:

- Hardware connections (OPX+ & Octave)
- Calibration store (JSON-backed, versioned)
- Experiment templates (`session.exp.*`)
- Operation library (`session.ops.*`)

## Running an Experiment

### Via Template Library (recommended)

```python
# Resonator spectroscopy
result = session.exp.resonator.spectroscopy(
    f_min=7.0e9, f_max=7.5e9, df=0.1e6, n_avg=2000
)

# Power Rabi
result = session.exp.qubit.power_rabi(
    a_min=0.0, a_max=1.0, da=0.01, n_avg=1000
)
```

### Via Direct Class Import

```python
from qubox.notebook import PowerRabi, CalibrationOrchestrator

exp = PowerRabi(session._compat)
result = exp.run(a_min=0.0, a_max=1.0, da=0.01, n_avg=1000)
analysis = exp.analyze(result)
```

## Analysis

```python
import qubox_tools as qt

# Generalized fitting
popt, pcov = qt.generalized_fit(
    x_data, y_data,
    qt.fitting.models.lorentzian_model,
    p0=[center_guess, width_guess, amp_guess, offset_guess],
)

# Post-processing
from qubox_tools.algorithms import post_process as pp
demodulated = pp.demod_accumulated(raw_I, raw_Q, ...)
```

## Notebook Workflow

Notebooks follow a sequential numbering convention starting from `00_hardware_defintion.ipynb`:

```python
from qubox.notebook import (
    open_shared_session,
    require_shared_session,
    open_notebook_stage,
    ResonatorSpectroscopy,
    CalibrationOrchestrator,
)

# Open shared session (notebook 00)
session = open_shared_session(bootstrap_path="./bootstrap.json")

# Use in subsequent notebooks
session = require_shared_session()
```

## Project Structure

```
qubox/              Main package — public API
qubox_tools/        Analysis, fitting, plotting
qubox_lab_mcp/      Lab MCP server
notebooks/          28 sequential experiment notebooks
tools/              Developer utilities
tests/              Test suite
docs/               Documentation
samples/            Sample configurations
```

## Next Steps

- [:material-book-open-variant: API Reference](api/index.md) — Full API documentation
- [:material-cog: Architecture](architecture/index.md) — How it all fits together
- [:material-school: Notebook Workflow](guides/notebooks.md) — Step-by-step experiment guide
- [:material-swap-horizontal: Migration Guide](guides/migration.md) — Moving from legacy code
