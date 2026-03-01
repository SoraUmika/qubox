# Comprehensive Bug & Inconsistency Review + Controlled Fixes (qubox_v2)

## Executive summary

This review completed the required Phase 0 reading pass, then executed a static/structural audit focused on hard failures, silent correctness bugs, calibration-flow integrity, sweep/buffer consistency, and naming/schema consistency.

High-impact semantic bugs were found in readout-fidelity optimization paths where discriminator outputs were treated as tuples, despite returning a dict-like `Output`. This can silently degrade optimization metrics or trigger exception fallback behavior.

A targeted, minimal patch set was applied to eliminate those bugs without changing public method signatures.

## Scope and constraints applied

- Stability-first, minimal diffs.
- No public API/signature changes.
- No Python environment configuration.
- No broad refactors in this pass.

## Phase 0 completion (required reading)

Reviewed:
- `qubox_v2/docs/API_REFERENCE.md`
- `qubox_v2/docs/ARCHITECTURE.md`
- `README.md` (canonical architecture/API source for compat docs)
- `docs/CHANGELOG.md`
- `docs/design_circuit_runner.md`
- `docs/design_gate_tuning_framework.md`
- `docs/design_circuit_visualization.md`
- `notebooks/post_cavity_experiment_context.ipynb` (including setup/import context section)

## Findings and fixes

| ID | Severity | Category | Location | Status | Summary |
|---|---|---|---|---|---|
| F1 | High | Hard/Silent bug | `qubox_v2/experiments/spectroscopy/resonator.py` (`ReadoutFrequencyOptimization.run`) | Fixed | `two_state_discriminator(...)` result was tuple-unpacked, but function returns dict-like `Output`. Fidelity now read via `disc.get("fidelity", 0.0)`. |
| F2 | High | Hard/Silent bug | `qubox_v2/experiments/spa/flux_optimization.py` (`SPAPumpFrequencyOptimization.run`) | Fixed | GE discrimination used non-existent `I_g/Q_g/I_e/Q_e` outputs; corrected to use `S_g/S_e` and compute I/Q components before discriminator call. |
| F3 | Medium | Runtime safety | `qubox_v2/experiments/spectroscopy/resonator.py` (`ReadoutFrequencyOptimization.run`) | Fixed | Added explicit empty-sweep guard for `if_freqs` to prevent invalid run flow and late failures. |
| F4 | Medium | Type/contract consistency | `qubox_v2/experiments/spa/flux_optimization.py` | Fixed | `RunResult(mode="run", ...)` replaced with `ExecMode.HARDWARE` for enum-consistent mode typing. |
| F5 | Low | Code hygiene / drift indicator | `qubox_v2/experiments/tomography/qubit_tomo.py` | Fixed | Removed unused `measureMacro` import/local alias to reduce architectural ambiguity and dead code. |

## Files changed

- `qubox_v2/experiments/spectroscopy/resonator.py`
- `qubox_v2/experiments/spa/flux_optimization.py`
- `qubox_v2/experiments/tomography/qubit_tomo.py`

## Verification

- Language-service diagnostics were checked on all modified files.
- Result: no errors in edited files.

## Architectural drift report (current state)

### 1) Measurement abstraction drift (known/managed)

- Design direction emphasizes explicit measurement specs/snapshots.
- Codebase still has broad `measureMacro` coupling across experiments.
- This pass avoided behavioral refactors here to preserve stability.

### 2) Sweep construction edge behavior

- `create_if_frequencies(...)` can produce an empty array for edge cases (e.g., collapsed ranges).
- Guard was added at one high-risk callsite (`ReadoutFrequencyOptimization`) instead of changing global utility semantics.

### 3) Exec mode representation consistency

- Most runtime paths use enum-backed `ExecMode`; some residual string-based mode assignments existed.
- The observed SPA string modes were normalized in this pass.

## Controlled refactors recommended for future work (not applied here)

1. Introduce a small shared helper for discriminator extraction:
   - input: `(S_g, S_e)` or `(I_g, Q_g, I_e, Q_e)`
   - output: validated scalar fidelity
   - benefit: removes duplicated try/except extraction logic and schema drift.

2. Normalize all `RunResult.mode` writers to `ExecMode` enum values with one lint/static check.

3. Decide and document global `create_if_frequencies(...)` edge-case policy:
   - either guarantee >=1 point when `start==end`,
   - or uniformly require callsite guards.

4. Continue migration away from implicit macro state where feasible, using explicit readout snapshots/specs per design docs.

## Risk assessment after applied fixes

- Behavioral risk: low (changes are local and schema-aligned).
- API risk: low (no signature changes).
- Regression risk: low-to-medium in experiment-specific edge flows; broader hardware validation remains recommended in normal CI/lab workflow.
