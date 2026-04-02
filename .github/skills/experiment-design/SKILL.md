---
name: experiment-design
description: >
  Use this skill when designing new cQED experiments, creating new experiment classes, defining
  pulse sequences, or extending the experiment library. Trigger on: "new experiment",
  "pulse sequence", "protocol", "Rabi", "Ramsey", "T1", "T2", "spectroscopy", "readout",
  "calibration", "chevron", "Fock", "tomography", "SNAP", "SPA", or any request to add a
  new measurement type to qubox.
---

# Experiment Design Skill

## When to Use

- Creating a new experiment class (spectroscopy, time-domain, readout calibration, etc.)
- Defining a new pulse sequence or protocol
- Extending `ExperimentLibrary` with a new template
- Adding support for a new cQED measurement type
- Adapting an existing experiment to new hardware parameters

## How to Use

### Step 1 — Read References

Before writing any code:

- `standard_experiments.md` — reference protocols; understand the established baseline
- `API_REFERENCE.md` — public experiment API (Session, ExperimentLibrary, template API)
- `qubox/legacy/experiments/` — existing experiment classes to follow as patterns
- `qubox/experiments/templates/` — modern template-based experiment definitions
- `qubox/experiments/workflows/` — higher-level workflow compositions
- A relevant existing experiment (e.g., `qubox/legacy/experiments/time_domain/` for T1/T2)

### Step 2 — Understand the Pipeline

Every experiment in qubox follows this pipeline:

```
ExperimentDefinition (qubox.experiments.templates)
    │
    ▼
QUA program builder (qubox.legacy.programs.*)
    │
    ▼
Compiled QUA program
    │
    ▼
Execution on OPX+ via QM API
    │
    ▼
Raw results → Analysis (qubox_tools)
    │
    ▼
ExperimentResult / CalibrationResult
```

Understand where your new experiment fits in this pipeline before writing code.

### Step 3 — Follow Existing Patterns

#### For a new experiment class (legacy-style):

1. Find the most similar existing experiment in `qubox/legacy/experiments/`.
2. Inherit from the same base class (e.g., `ExperimentRunner`).
3. Implement: `build_plan()`, `run()`, `analyze()`.
4. Follow the same `__init__` signature convention (session as first arg).
5. Register it in `qubox/legacy/experiments/__init__.py`.

#### For a new template (modern-style):

1. Add a method to the appropriate section of `qubox/experiments/templates/library.py`.
2. Follow the `session.exp.<category>.<name>()` naming convention.
3. Add a `LegacyExperimentAdapter` entry in `qubox/backends/qm/runtime.py` `_load_adapters()`.

### Step 4 — Define the Pulse Sequence

- Define the sequence in terms of QUA primitives: `play()`, `wait()`, `measure()`, `align()`.
- Document the sequence structure: state prep → experiment body → measurement.
- Identify sweep parameters (frequency, amplitude, duration, phase).
- Identify measurement type (IQ raw, state discrimination, averaged).

### Step 5 — Validate

Use the **qua-validation** skill (`.github/skills/qua-validation/SKILL.md`) to:

1. Compile the QUA program
2. Simulate on the hosted server
3. Verify pulse sequence matches intent
4. Check standard experiments still pass

### Step 6 — Document

- Add the new experiment to `API_REFERENCE.md`.
- Add a changelog entry to `docs/CHANGELOG.md`.
- Add or update a notebook example if this is a user-facing experiment.
- If the experiment has known hardware limitations: document in `limitations/qua_related_limitations.md`.

## Reference Files

| File | Purpose |
| --- | --- |
| `standard_experiments.md` | Baseline protocols to use as design reference |
| `API_REFERENCE.md` | Public experiment API |
| `qubox/legacy/experiments/` | Existing experiment classes (follow these patterns) |
| `qubox/experiments/templates/library.py` | Modern template definitions |
| `qubox/backends/qm/runtime.py` | Adapter registration (`_load_adapters`) |
| `qubox/legacy/programs/` | QUA program builders |

## Rules

- Follow the existing class hierarchy. Do not create a parallel hierarchy.
- Preserve backward compatibility. Do not change existing experiment interfaces.
- Validate through the simulator before declaring done. See qua-validation skill.
- Do not add unrelated infrastructure changes in the same task as a new experiment.
- Document every new experiment in `API_REFERENCE.md`.
- A new experiment without a passing simulator check is incomplete work.

## Experiment Categories (existing)

| Category | Location |
| --- | --- |
| Spectroscopy | `qubox/legacy/experiments/spectroscopy/` |
| Time-domain (Rabi, T1, T2) | `qubox/legacy/experiments/time_domain/` |
| Readout calibration | `qubox/legacy/experiments/calibration/readout/` |
| Gate calibration | `qubox/legacy/experiments/calibration/gates/` |
| Cavity / Fock / storage | `qubox/legacy/experiments/cavity/` |
| Tomography | `qubox/legacy/experiments/tomography/` |
| SPA | `qubox/legacy/experiments/spa/` |
