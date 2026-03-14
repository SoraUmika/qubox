# Prompt Log

- Timestamp: 2026-03-13T04:36:24.200922-05:00
- Repository: `E:\qubox`
- Task: Major refactor from `qubox_v2` toward a canonical `qubox` package

## Original Request

Perform a major architectural refactor of the repository so that:

- `qubox` becomes the canonical package identity
- `Session` becomes the main runtime entry point
- standard experiment templates are exposed through a clearer user-facing API
- custom `Sequence` and `QuantumCircuit` authoring are supported
- sweeps and acquisition remain first-class concepts
- calibration snapshots and explicit update proposals are part of the public model
- notebooks, docs, packaging metadata, and tests are updated accordingly
- `qubox_v2` may remain temporarily as a compatibility layer, but not as the
  main public path

## Result

Implemented a first major migration slice toward the requested architecture.

### New canonical package

Added a new `qubox/` package with:

- `Session`
- `Sequence`, `Operation`, `Condition`
- `QuantumCircuit`, `QuantumGate`
- `SweepAxis`, `SweepPlan`, `AcquisitionSpec`
- `OperationLibrary`
- `ExecutionRequest`, `ExperimentResult`
- `CalibrationSnapshot`, `CalibrationProposal`
- `QMRuntime`

### Public experiment path

Added a new template-driven API through `session.exp`:

- `session.exp.qubit.spectroscopy(...)`
- `session.exp.qubit.power_rabi(...)`
- `session.exp.qubit.ramsey(...)`
- `session.exp.resonator.spectroscopy(...)`
- `session.exp.reset.active(...)`
- `session.exp.custom(...)`

### Canonical backend adapter

Added `qubox.backends.qm`:

- lowers `Sequence` / `QuantumCircuit` into the existing `compile_v2` path
- routes standard experiment requests through one explicit runtime adapter
- keeps legacy builders and experiment classes behind the adapter boundary

### Calibration model

Added:

- frozen `CalibrationSnapshot.from_session(...)`
- explicit `ExperimentResult.proposal()` -> `CalibrationProposal`
- proposal `apply(..., dry_run=...)` flow through the legacy orchestrator

### Documentation and packaging

Added:

- `README.md`
- `docs/qubox_architecture.md`
- `docs/qubox_migration_guide.md`
- updated `qubox_v2/pyproject.toml`
- updated `docs/CHANGELOG.md`
- updated notebook startup paths to use `from qubox import Session`

### Tests and validation

Added:

- `tests/test_qubox_public_api.py`

Validation performed:

- `pytest tests\test_qubox_public_api.py -q` -> passed
- JSON parse validation for:
  - `notebooks/post_cavity_experiment_context.ipynb`
  - `notebooks/post_cavity_experiment_quantum_circuit.ipynb`
- import sanity check for `from qubox import Session`

### Remaining migration boundary

This is a real refactor, but not the final backend rewrite.

Current state:

- `qubox` is now the canonical public package for new code
- `qubox_v2` still contains the mature backend internals and compatibility path
- not every historical experiment has a first-class `session.exp.*` wrapper yet
- workflow migration is only partially public; `readout.full` is still a
  compatibility-style report wrapper
- deep notebook internals still use some `qubox_v2` imports where the
  corresponding public `qubox` surface has not yet been lifted
