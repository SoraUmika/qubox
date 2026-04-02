---
description: "Use when modifying experiment base classes, creating new experiment subclasses, or changing experiment lifecycle methods (run, analyze, configure). Enforces ExperimentRunner patterns and composition-over-inheritance."
applyTo: "qubox/legacy/experiments/**"
---

# Experiments Module Instructions

## Patterns

1. New experiments inherit `ExperimentRunner` (lightweight base), not the legacy monolith
2. `run()` returns `RunResult`; never mutates session state directly
3. `analyze()` returns `Output` with proper `FitResult` and `metadata["calibration_kind"]`
4. Use `ConfigBuilder` for QUA config construction — no manual config dicts
5. Register pulses through `PulseOperationManager`, not direct QUA pulse calls

## Composition Over Inheritance

- Prefer mixing in capabilities via composition (device manager, pulse manager) over deep class hierarchies
- Each experiment subclass should override only physics-specific methods
- Infrastructure plumbing lives in `ExperimentRunner`

## Procedure

1. Read the existing experiment class hierarchy in `qubox/legacy/experiments/` before adding or modifying.
2. Check that `run()` returns `RunResult` and does NOT mutate session state.
3. Check that `analyze()` sets `metadata["calibration_kind"]` and propagates `FitResult.success`.
4. Use the **experiment-design** skill for creating new experiment types from scratch.
5. Use the **qua-validation** skill to compile and simulate after any pulse-sequence change.
6. Run `pytest tests/ -k experiment -v` to verify no regressions.
