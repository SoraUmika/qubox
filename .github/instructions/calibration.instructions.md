---
description: "Use when modifying calibration orchestrator, patch rules, calibration store, calibration history, or calibration transitions. Enforces FitResult.success contract, patch transactionality, and calibration lifecycle invariants."
applyTo: "qubox/legacy/calibration/**"
---

# Calibration Module Instructions

## Critical Contracts

1. **FitResult.success propagation**: If `FitResult.success is False`, then `CalibrationResult.quality["passed"]` MUST be `False`. Never silently use stale parameters.
2. **Patch transactionality**: `apply_patch()` must capture pre-patch state and support rollback on exception. No partial state mutations.
3. **Orchestrator lifecycle**: The sequence `run_experiment → persist → analyze → build_patch → apply_patch` must not be bypassed.
4. **r_squared threshold**: `quality["passed"] = False` when `r_squared < 0.5`.

## Patterns

- `CalibrationOrchestrator` is the single entry point for all calibration state changes
- `Patch` objects are immutable descriptions of intended state changes
- `CalibrationResult` carries `quality` dict that gates downstream application
- All `Output` objects pass through `split_output_for_persistence()` before serialization

## Procedure

1. Read the existing `CalibrationOrchestrator` flow before modifying any step.
2. Verify the FitResult contract on every code path through `analyze()`.
3. Confirm `apply_patch()` captures a snapshot before mutation and rolls back on exception.
4. Run `pytest tests/ -k calibration -v` after changes to verify contract compliance.
5. Use the **calibration-experiment-audit** skill for full lifecycle tracing if the change is non-trivial.
