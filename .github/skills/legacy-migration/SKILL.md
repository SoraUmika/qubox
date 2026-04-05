---
name: legacy-migration
description: "Migrate experiments from the legacy codebase to qubox. Use when: migrating a legacy experiment, porting experiment code from the JJL_Experiments reference codebase, translating legacy QUA programs to qubox framework, comparing legacy vs qubox experiment behavior, or any request like 'migrate experiment', 'port from legacy', 'legacy to qubox', or referencing post_cavity_experiment_legacy.ipynb."
argument-hint: "Name of the experiment to migrate (e.g., 'Rabi', 'T1', 'readout calibration')"
---

# Legacy Migration

## Reference

| Item | Location |
|------|----------|
| Legacy codebase | `C:\Users\jl82323\Box\...\JJL_Experiments` (read-only) |
| Reference notebook | `post_cavity_experiment_legacy.ipynb` |
| Target | `qubox/experiments/` (modern) or `qubox/legacy/experiments/` (legacy-style) |

**Legacy behavior is the ground truth.** Discrepancies must be reported, never silently accepted.

## Procedure

1. **Study legacy** — Read experiment definition + `post_cavity_experiment_legacy.ipynb`. Document: pulse sequence, parameters, sweep vars, measurement type, analysis pipeline.
2. **Map to qubox** — Find closest existing qubox experiment as pattern. Implement with `ExperimentRunner` base: `build_plan()`, `run()`, `analyze()`. Preserve parameter names.
3. **Validate equivalence** — Compile + simulate both versions (use qua-validation skill). Compare pulse ordering, timing, measurements, control flow. `n_avg=1` for quick checks.
4. **Create notebook** — New numbered notebook under `notebooks/` (§9.1 convention).
5. **Document** — Update `API_REFERENCE.md`, `docs/CHANGELOG.md`. Legacy defects → `limitations/`.

## Rules

- Do not modify the legacy codebase (read-only)
- One experiment per migration task
- Preserve parameter names for user familiarity
- Legacy defects: document in `limitations/`, implement corrected version with explanation
