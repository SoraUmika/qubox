# QuBox — Workspace Instructions

## Project Overview

QuBox is a cQED (circuit quantum electrodynamics) experiment orchestration framework for OPX+ / Octave hardware. Python 3.10+, Pydantic v2 models, 120-char line length (ruff).

## Architecture

- **core/** — Session state, experiment context (frozen dataclass), config, persistence, schemas
- **calibration/** — Orchestrator pipeline: run → persist → analyze → build_patch → apply_patch
- **experiments/** — `ExperimentRunner` base + 30+ physics-specific subclasses
- **hardware/** — ConfigEngine + HardwareController for OPX+ / Octave
- **pulses/** — PulseOperationManager, registry, factory, waveforms
- **analysis/** — Fitting, metrics, cQED models & plotting, post-processing
- **compile/** — Ansatz optimization, GPU accelerators (JAX/CUDA)
- **gates/** — Gate system architecture
- **simulation/** — QuTiP quantum simulation

See [qubox_v2_legacy/docs/ARCHITECTURE.md](qubox_v2_legacy/docs/ARCHITECTURE.md) for full details.

## Code Style

- Ruff linter, 120-char lines, Python 3.10+ type hints
- Pydantic v2 for all data models; frozen dataclasses for identity objects
- `from __future__ import annotations` in every module
- Imports: stdlib → third-party → local (relative within package)

## Conventions

- **ExperimentContext** is immutable; never assign to its fields after construction
- **FitResult.success contract**: a failed fit must propagate `quality["passed"] = False`; never silently use stale parameters
- **CalibrationOrchestrator** owns the run → analyze → patch → apply lifecycle; do not bypass it
- Prefer composition over deep inheritance for experiment classes
- All patch application must be transactional with rollback support

## Build and Test

```bash
pip install -e ".[dev]"      # editable install with dev deps
pytest                        # run full test suite
pytest tests/gate_architecture/ -v   # gate architecture tests with golden snapshots
ruff check qubox/             # lint
```

## Documentation

- Update `docs/CHANGELOG.md` (append-only) for every user-facing change
- Keep `API_REFERENCE.md` and `ARCHITECTURE.md` in sync with code changes
