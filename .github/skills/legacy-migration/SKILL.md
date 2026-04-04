---
name: legacy-migration
description: "Migrate experiments from the legacy codebase to qubox. Use when: migrating a legacy experiment, porting experiment code from the JJL_Experiments reference codebase, translating legacy QUA programs to qubox framework, comparing legacy vs qubox experiment behavior, or any request like 'migrate experiment', 'port from legacy', 'legacy to qubox', or referencing post_cavity_experiment_legacy.ipynb."
argument-hint: "Name of the experiment to migrate (e.g., 'Rabi', 'T1', 'readout calibration')"
---

# Legacy Migration Skill

## When to Use

- Migrating a specific experiment from the legacy codebase to qubox
- Porting pulse sequences or QUA programs from legacy to modern qubox patterns
- Comparing legacy vs qubox experiment behavior for validation
- Any task referencing `AGENTS.md §14` (Legacy Reference Codebase)

## Legacy Reference

| Item | Location |
|------|----------|
| Legacy codebase | `C:\Users\jl82323\Box\...\JJL_Experiments` (read-only) |
| Reference notebook | `post_cavity_experiment_legacy.ipynb` |
| Target package | `qubox/legacy/experiments/` (legacy-style) or `qubox/experiments/` (modern) |

**The legacy codebase is the behavioral ground truth.** Experiments there have been validated
on real hardware. The migrated version must match the legacy behavior.

## Procedure

### Step 1 — Study the Legacy Implementation

1. Read the experiment definition in the legacy codebase
2. Read `post_cavity_experiment_legacy.ipynb` for execution context
3. Document:
   - Pulse sequence structure (state prep → experiment body → measurement)
   - Parameters and their defaults
   - Sweep variables and ranges
   - Measurement protocol (IQ raw, state discrimination, averaged)
   - Analysis pipeline (fitting function, extracted parameters)

### Step 2 — Map to qubox Framework

Determine the migration target:

| Legacy Pattern | qubox Target |
|---------------|-------------|
| Standalone QUA program | `qubox/legacy/programs/` builder function |
| Experiment class | `qubox/legacy/experiments/` subclass |
| Template experiment | `qubox/experiments/templates/library.py` method |

Follow the closest existing qubox experiment as a pattern.

### Step 3 — Implement

1. Create the experiment class inheriting from the appropriate base (`ExperimentRunner`)
2. Implement `build_plan()`, `run()`, `analyze()`
3. Preserve parameter names and semantics from legacy (smooth user transition)
4. Register in appropriate `__init__.py`
5. Add to `qubox.notebook` import surface if user-facing

### Step 4 — Validate Behavioral Equivalence

Use the **qua-validation** skill for this step:

1. **Compile** both legacy and migrated versions
2. **Simulate** both on the hosted server (10.157.36.68 / Cluster_2)
3. **Compare**:
   - [ ] Same pulse ordering
   - [ ] Same timing structure
   - [ ] Same measurement placement
   - [ ] Same control flow (loops, sweeps)
   - [ ] Same parameter encoding in QUA variables
4. If behavior differs: **report the discrepancy** — never silently accept it

Validation shortcuts: `n_avg=1`, shorten idle waits, minimum simulation duration.

### Step 5 — Create Notebook

Add a new numbered notebook under `notebooks/` (follow §9.1 sequential numbering):

1. Import from `qubox.notebook`
2. Demonstrate the migrated experiment with example parameters
3. Show expected output format
4. Reference the legacy experiment for comparison

### Step 6 — Document

- Update `API_REFERENCE.md` with the new experiment entry
- Add a `docs/CHANGELOG.md` entry: `- [added] Migrated <experiment> from legacy`
- If the legacy experiment has a known defect, document it in `limitations/` and explain
  the corrected behavior in qubox

### Step 7 — Report

```markdown
## Migration Report: [ExperimentName]

### Legacy Source
- File: [path in legacy codebase]
- Notebook: post_cavity_experiment_legacy.ipynb

### qubox Target
- File: [path in qubox]
- Notebook: [new notebook path]

### Behavioral Equivalence
- [ ] Pulse ordering matches
- [ ] Timing matches
- [ ] Measurements match
- [ ] Control flow matches
- [ ] Parameters preserved

### Discrepancies
[List any differences with justification]

### Known Defects Corrected
[List any legacy bugs fixed, with explanation]
```

## Rules

- **Legacy behavior is the reference.** Discrepancies must be reported and justified.
- **Do not modify the legacy codebase.** It is read-only reference material.
- **One experiment per migration task.** Keep scope small and verifiable.
- **Preserve parameter names** where possible for user familiarity.
- Legacy defects go to `limitations/` with corrected implementation in qubox.
