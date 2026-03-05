# Contract Checklist — qubox_v2 Invariants

Use this checklist when reviewing any code change. Each item is a hard invariant that must hold across the codebase.

## P0 — Critical Contracts

- [ ] **FitResult.success propagation**: If `FitResult.success is False`, then `CalibrationResult.quality["passed"]` MUST be `False`. No silent fallthrough to stale parameters.
- [ ] **ExperimentContext immutability**: `ExperimentContext` is `@dataclass(frozen=True)`. No code path may assign to its fields after construction. Use `dataclasses.replace()` to derive new contexts.
- [ ] **Patch transactionality**: `CalibrationOrchestrator.apply_patch()` must capture pre-patch state and support rollback on failure. No partial state mutations left on exception.
- [ ] **Persistence boundary**: All `Output` objects pass through `split_output_for_persistence()` before serialization. Raw numpy arrays never written to JSON.

## P1 — Structural Contracts

- [ ] **Import ordering**: `from __future__ import annotations` as first import in every module. Then stdlib → third-party → local (relative).
- [ ] **No circular imports**: Adding new cross-module imports must not create cycles. Core modules remain leaf dependencies.
- [ ] **Pydantic v2 only**: All data models use Pydantic v2 (`BaseModel`, `model_validator`, not v1-style `validator`).
- [ ] **Type hints**: All public function signatures have type annotations. Use `str | None` syntax (PEP 604), not `Optional[str]`.

## P2 — Behavioral Contracts

- [ ] **CalibrationOrchestrator lifecycle**: The sequence `run_experiment → persist_artifact → analyze → build_patch → apply_patch` must not be bypassed. No direct state mutation outside this pipeline.
- [ ] **r_squared threshold**: `quality["passed"] = False` if `r_squared < 0.5` in calibration analysis.
- [ ] **Session identity**: `SessionState` changes trigger `config_hash` recomputation in `ExperimentContext`.
- [ ] **Pulse burn**: Pulse operations must go through `PulseOperationManager` → `ConfigEngine` → hardware. No direct QUA pulse calls.

## P3 — Style Contracts

- [ ] **Line length**: 120 characters max (ruff enforced).
- [ ] **Docstrings**: NumPy-style for public classes and functions.
- [ ] **Module docstring**: Every module has a top-level docstring with module path and description.
