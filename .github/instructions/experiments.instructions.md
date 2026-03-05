---
description: "Use when modifying experiment base classes, creating new experiment subclasses, or changing experiment lifecycle methods (run, analyze, configure). Enforces ExperimentRunner patterns and composition-over-inheritance."
applyTo: "qubox_v2/experiments/**"
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
