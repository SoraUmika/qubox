---
name: experiment-design
description: >
  Use this skill when designing new cQED experiments, creating new experiment classes, defining
  pulse sequences, or extending the experiment library. Trigger on: "new experiment",
  "pulse sequence", "protocol", "Rabi", "Ramsey", "T1", "T2", "spectroscopy", "readout",
  "calibration", "chevron", "Fock", "tomography", "SNAP", "SPA", or any request to add a
  new measurement type to qubox.
---

# Experiment Design

## Pipeline

```
ExperimentDefinition → QUA program builder → Compiled QUA → OPX+ execution → Raw results → Analysis → ExperimentResult
```

## Before Writing Code

Read: `standard_experiments.md`, `API_REFERENCE.md`, and the most similar existing experiment in `qubox/legacy/experiments/`.

## Implementation Paths

**Legacy-style** (class in `qubox/legacy/experiments/`):
1. Inherit from same base as nearest experiment (e.g., `ExperimentRunner`)
2. Implement `build_plan()`, `run()`, `analyze()` — session as first `__init__` arg
3. Register in `qubox/legacy/experiments/__init__.py`

**Modern template** (in `qubox/experiments/templates/library.py`):
1. Add method → `session.exp.<category>.<name>()` naming
2. Add `LegacyExperimentAdapter` in `qubox/backends/qm/runtime.py` `_load_adapters()`

## Pulse Sequence Design

- QUA primitives: `play()`, `wait()`, `measure()`, `align()`
- Structure: state prep → experiment body → measurement
- Identify: sweep params (freq, amp, duration, phase) + measurement type (IQ raw, state disc, averaged)

## Validation

Use **qua-validation** skill: compile → simulate on hosted server → verify sequence matches intent → standard experiments still pass. A new experiment without simulator check is incomplete.

## Documentation

Update: `API_REFERENCE.md`, `docs/CHANGELOG.md`, notebook if user-facing, `limitations/` if applicable.

## Existing Categories

| Category | Location |
|----------|----------|
| Spectroscopy | `qubox/legacy/experiments/spectroscopy/` |
| Time-domain (Rabi, T1, T2) | `qubox/legacy/experiments/time_domain/` |
| Readout calibration | `qubox/legacy/experiments/calibration/readout/` |
| Gate calibration | `qubox/legacy/experiments/calibration/gates/` |
| Cavity / Fock / storage | `qubox/legacy/experiments/cavity/` |
| Tomography | `qubox/legacy/experiments/tomography/` |
| SPA | `qubox/legacy/experiments/spa/` |

## Rules

- Follow existing hierarchy — no parallel hierarchies
- Preserve backward compatibility
- No unrelated infrastructure changes in same task
