# Workflow Safety Refactoring — v2.1.0

**Date:** 2026-03-02
**Spec:** P0.1–P2.1 (based on architecture review findings H1–H5)

---

## Summary

This document describes a set of coordinated changes to the `qubox_v2`
experiment workflow that eliminate silent-failure paths, make state
mutations explicit and reversible, remove heuristic unit conversions,
establish a single source of truth for calibration data, and provide a
session-scoped measurement configuration object.

Every change is backward-compatible: existing code that does not use the
new features will continue to work unchanged, with the exception of the
`apply_patch()` default changing from `dry_run=False` → `dry_run=True`
(P0.2), which was deemed critical for safety.

---

## P0.1 — Fit-Outcome Contract (no silent failures)

### Problem
When `curve_fit` fails, `fit_and_wrap()` returns a `FitResult` with
`params == {}` and `metadata["failed"] = True`.  Nothing in the contract
*forces* downstream code to check the metadata dict, so fit failures
silently propagate into `build_patch()` → `apply_patch()` and can wipe
calibrated parameters with stale/empty values.

### Changes

| File | Change |
|------|--------|
| `experiments/result.py` | Added `success: bool = True` and `reason: str \| None = None` to `FitResult`. |
| `analysis/fitting.py` | `fit_and_wrap()` now returns `FitResult(success=False, reason=...)` on failure and explicit `success=True, reason=None` on success. |
| `calibration/orchestrator.py` | `analyze()` checks `fit.success`; if `False`, immediately returns a `CalibrationResult` with `quality["passed"] = False` — preventing `build_patch` from ever running. |
| `analysis/calibration_algorithms.py` | `fit_number_splitting()` and `fit_chi_ramsey()` now emit `RuntimeWarning` on fit failure and include `_fit_success` in their return dicts. |

### Migration
- Old code creating `FitResult` without `success=` will still work
  (defaults to `True`).
- Code that checked `metadata["failed"]` should migrate to `success`.

---

## P0.2 — Transactional Patch Apply + Preview

### Problem
`apply_patch()` defaulted to `dry_run=False`, meaning every call mutated
the CalibrationStore immediately.  If an operation failed mid-way,
earlier mutations were already committed — leaving the store in an
inconsistent state.

### Changes

| File | Change |
|------|--------|
| `calibration/orchestrator.py` | `apply_patch(dry_run=True)` — default flipped to `True`. Non-dry-run path: takes an in-memory snapshot before mutations, rolls back on exception.  Raises `RuntimeError("Transactional patch apply failed and was rolled back: ...")`. Preview now annotates `old_value`/`new_value` for `SetCalibration` ops. Mutation logic factored into `_apply_updates(patch)`. |
| `calibration/store.py` | Added `create_in_memory_snapshot() → dict` and `restore_in_memory_snapshot(snapshot)` for rollback support. |

### Migration
- Code calling `orch.apply_patch(patch)` without arguments now gets a
  dry-run preview.  Add `dry_run=False` to actually apply.

---

## P0.3 — Remove Heuristic Unit Conversions

### Problem
`T1Rule` contained `if t1_raw > 1e-3: t1_s = t1_raw * 1e-9` — a magic
heuristic that silently decided whether a number was in seconds or
nanoseconds.  This produced wrong results for long T1 values and violated
explicit-is-better-than-implicit.

### Changes

| File | Change |
|------|--------|
| `calibration/patch_rules.py` | **T1Rule**: Removed the heuristic.  Now prefers `T1_s` (seconds, direct), then `T1_ns` (nanoseconds, converted), then bare `T1` (stored as-is with `DeprecationWarning` if > 1 ms). |
| `calibration/patch_rules.py` | **T2RamseyRule**: Prefers `T2_star_s` → `T2_star` (with deprecation warning, assumed ns) → `T2_star_ns`. |
| `calibration/patch_rules.py` | **T2EchoRule**: Prefers `T2_echo_s` → `T2_echo` (with deprecation warning, assumed ns) → `T2_echo_ns`. |

### Migration
- Experiment `analyze()` methods should return `T1_s`, `T2_star_s`,
  `T2_echo_s` keys.  The bare keys still work but emit deprecation
  warnings and will be removed in v3.0.

---

## P1.1 — CalibrationStore as Single Source of Truth

### Problem
`cQED_attributes` carries a stale copy of frequencies, coherence times,
and pulse parameters.  Drift between `cQED_attributes` and
`CalibrationStore` is never detected.

### Changes

| File | Change |
|------|--------|
| `analysis/cQED_attributes.py` | Added `_CQED_FIELD_MAP` and `_PULSE_FIELD_MAP` class-level dicts mapping attribute fields to CalibrationStore paths. |
| `analysis/cQED_attributes.py` | Added `verify_consistency(store, *, rtol=1e-6, raise_on_mismatch=False) → list[str]` — compares all mapped fields, returns human-readable mismatch list. |
| `analysis/cQED_attributes.py` | Added `@classmethod from_calibration_store(store, *, ro_el, qb_el, st_el)` — builds a snapshot entirely from the store. |

### Migration
- Call `attr.verify_consistency(store)` after loading to detect drift.
- Prefer `cQED_attributes.from_calibration_store(...)` over manual
  construction.

---

## P1.2 — Session-Scoped Measurement Config

### Problem
Measurement discrimination/quality parameters are scattered across
`measureMacro` class-variables, `CalibrationStore` records, and
`cQED_attributes` fields.  Mutation of the `measureMacro` singleton is a
hidden side effect.

### Changes

| File | Change |
|------|--------|
| `core/measurement_config.py` (NEW) | Frozen `@dataclass MeasurementConfig` with all discrimination and quality parameters.  Factory methods: `from_calibration_store()`, `from_measure_macro_snapshot()`.  Reverse-direction: `apply_to_measure_macro()` (with `DeprecationWarning`).  `to_dict()` for serialisation. |

### Migration
- Build `MeasurementConfig` from the store at session start, then pass
  it to experiments rather than relying on the `measureMacro` singleton.

---

## P2.1 — MultiProgramExperiment Base Class

### Problem
Experiments that need multiple QUA programs (e.g., Wigner tomography
sweeping Fock levels) have no shared base class.  Each re-implements
the build-N → run-N → analyze-per-program → merge pattern.

### Changes

| File | Change |
|------|--------|
| `experiments/multi_program.py` (NEW) | `MultiProgramExperiment(ExperimentBase)` abstract base.  Subclasses override `build_programs(**kw) → list[ProgramBuildResult]`.  Provides `run_all(**kw) → MultiProgramResult` that orchestrates build → run → analyze → merge. |
| `experiments/multi_program.py` | `@dataclass MultiProgramResult` with `individual_results`, `merged`, `builds`, `metadata`. |

### Migration
- Subclass `MultiProgramExperiment` and implement `build_programs()`.
  Optionally override `analyze_single()` and `merge_results()`.

---

## Test Coverage

All changes are covered by `tests/test_workflow_safety_refactor.py`
(32 tests, 8 test classes):

| Class | Tests | Covers |
|-------|-------|--------|
| `TestFitResultContract` | 4 | P0.1 fields |
| `TestFitAndWrapContract` | 2 | P0.1 fit_and_wrap |
| `TestCalibrationAlgorithmsWarnings` | 2 | P0.1 warnings |
| `TestTransactionalPatch` | 4 | P0.2 dry_run + rollback |
| `TestT1RuleHeuristicRemoval` | 4 | P0.3 T1 |
| `TestT2ExplicitUnits` | 5 | P0.3 T2 |
| `TestVerifyConsistency` | 4 | P1.1 |
| `TestMeasurementConfig` | 4 | P1.2 |
| `TestMultiProgramExperiment` | 3 | P2.1 |
