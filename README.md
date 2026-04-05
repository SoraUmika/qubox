# qubox

A Python framework for circuit-QED (cQED) experiment design, execution, and
analysis targeting Quantum Machines hardware (OPX+ + Octave, QUA API v1.2.6).

## Packages

| Package | Role |
|---------|------|
| `qubox` | Runtime framework — sessions, experiments, calibration, QUA compilation, hardware control |
| `qubox_tools` | Analysis toolkit — fitting, plotting, algorithms, optimization |
| `qubox_lab_mcp` | Lab MCP server for agent and tool integration |

## Quick Start

```python
# Runtime
from qubox import Session

session = Session.open(
    sample_id="sampleA",
    cooldown_id="cd_2026_03_13",
    registry_base="E:/qubox",
    qop_ip="10.157.36.68",
    cluster_name="Cluster_2",
)

# Notebook-facing imports
from qubox.notebook import QubitSpectroscopy, PowerRabi, open_shared_session

# Analysis
import qubox_tools as qt
popt, _ = qt.generalized_fit(x, y, qt.fitting.models.gaussian_model, p0=[...])
```

`qop_ip` must be provided explicitly or persisted in `hardware.json`; the
runtime no longer falls back to `localhost` during session bootstrap.

## Import Surfaces

| Surface | Audience | Contents |
|---------|----------|----------|
| `qubox` | All users | `Session`, `Sequence`, `QuantumCircuit`, sweep/acquisition specs, top-level data models |
| `qubox.notebook` | Notebook users | Experiment classes, session helpers, workflow primitives, waveform generators (~65 symbols) |
| `qubox.notebook.advanced` | Infrastructure | Calibration store internals, device registry, artifacts, verification (~45 symbols) |
| `qubox_tools` | Analysis | Fitting, plotting, post-processing, optimization |

## Repository Layout

```text
qubox/              Main package (public API + implementation)
qubox_tools/        Analysis, fitting, plotting, optimization
qubox_lab_mcp/      Lab MCP server
tools/              Developer & agent utilities (validation, logging, demos)
notebooks/          28 sequential experiment notebooks
tests/              Pytest test suite
docs/               Architecture docs, changelog, design reviews
samples/            Sample & cooldown data directories
limitations/        Known QUA/hardware limitations
past_prompt/        Agent prompt logs (append-only)
```

## Documentation Map

### Canonical (current, maintained)

| Document | Role |
|----------|------|
| [API Reference](API_REFERENCE.md) | Public API, package architecture, session/experiment/workflow surfaces |
| [Architecture — Package Map](site_docs/architecture/package-map.md) | Every module and its role |
| [Architecture — Execution Flow](site_docs/architecture/execution-flow.md) | Experiment → hardware → analysis pipeline |
| [Architecture — Design Principles](site_docs/architecture/design-principles.md) | Priority hierarchy, key design decisions |
| [AGENTS.md](AGENTS.md) | Agent policy — QUA validation, docs sync, change protocol |
| [Changelog](docs/CHANGELOG.md) | Append-only change log |
| [Standard Experiments](standard_experiments.md) | Trust gates for QUA compilation validation |

### Supporting (current analysis or planning)

| Document | Role |
|----------|------|
| [Refactor Status](site_docs/architecture/refactor-status.md) | Architecture refactor progress tracking |
| [Codebase Refactor Plan](docs/codebase_refactor_plan.md) | Active refactor priorities and roadmap |
| [Architecture Audit](docs/architecture_audit.md) | Full structural overview (2026-04-02) |
| [measureMacro Refactoring Plan](docs/measureMacro_refactoring_plan.md) | Measurement singleton replacement plan |

### Historical (preserved for reference, may describe removed packages)

| Document | Scope |
|----------|-------|
| [Architecture Overview](docs/qubox_architecture.md) | Early facade-era architecture sketch (2026-03-13) |
| [Migration Guide](docs/qubox_migration_guide.md) | Original qubox_v2_legacy → qubox migration paths |
| [Refactor Verification](docs/qubox_refactor_verification.md) | Assessment of the partial v2 → v3 migration |
| [Analysis Split](docs/qubox_tools_analysis_split.md) | Original qubox_v2_legacy.analysis → qubox_tools extraction |
| [Refactor Proposal](docs/qubox_experiment_framework_refactor_proposal.md) | Original experiment framework redesign proposal |
| [Architecture Review](docs/architecture_review.md) | Early qubox_v2_legacy structural survey (2026-03-02) |
| [Gate Architecture Review](docs/gate_architecture_review.md) | Circuit/gate subsystem review (2025-01) |

## Python Policy

Required Python version: **3.12.10**, using either the workspace `.venv` or a
global 3.12.10 interpreter.
