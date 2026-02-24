# qubox_v2 Codebase Review Report

**Date**: 2026-02-23
**Scope**: Full review of `qubox_v2/` (169 Python files, 29 modules) + notebook usage
**Status**: READ-ONLY audit -- no changes made

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Critical Bugs (Will Crash at Runtime)](#2-critical-bugs)
3. [High-Severity Issues (Logic Bugs / Silent Failures)](#3-high-severity-issues)
4. [Medium-Severity Issues (Inconsistencies / Design Flaws)](#4-medium-severity-issues)
5. [Low-Severity Issues (Dead Code / Style / Cleanup)](#5-low-severity-issues)
6. [Notebook Issues](#6-notebook-issues)
7. [Cross-Module Architectural Concerns](#7-cross-module-architectural-concerns)
8. [Housekeeping](#8-housekeeping)
9. [Summary Statistics](#9-summary-statistics)

---

## 1. Executive Summary

The `qubox_v2` codebase is a well-structured, layered experiment orchestration
framework with strong architectural documentation. The recent v1.4.0-v1.6.0
refactors (macro system, calibration schema, builder split) have significantly
improved the architecture. However, this review identified **~90 distinct issues**
across the following categories:

- **5 critical crash bugs** that will fail at runtime
- **~15 high-severity logic bugs** (silent failures, wrong results, contract violations)
- **~25 medium-severity issues** (inconsistencies, design flaws, API drift)
- **~45 low-severity issues** (dead code, unused imports, style)

The most concerning patterns are:
1. **Waveform physics inconsistency** between `tools/waveforms.py` and `pulses/waveforms.py`
2. **Experiment contract violations** -- several `analyze()` methods mutate state
3. **Missing numpy import** in the simulation solver (complete crash)
4. **measureMacro singleton** with several latent bugs around `None` thresholds and reset behavior

---

## 2. Critical Bugs

These will crash at runtime when the affected code path is reached.

### C1. Missing `numpy` import in `simulation/solver.py`

- **File**: `qubox_v2/simulation/solver.py`
- **Lines**: 26, 43, 46, 68
- **Impact**: Any call to `_compile_hamiltonian()` raises `NameError: name 'np' is not defined`
- **Details**: Line 2 only imports `qutip as qt`. Lines 26+ reference `np.asarray`, `np.ndarray` without ever importing numpy.

### C2. `float(None)` crash in `simulation/drive_builder.py`

- **File**: `qubox_v2/simulation/drive_builder.py:89`
- **Impact**: `validate_no_overlap_strict()` crashes with `TypeError` when `t_start` is missing from envelope params
- **Details**: `float(ep.get("t_start", None))` crashes before the `None` guard on line 90 can execute.

### C3. `__all__` exports commented-out `skopt_bo` function

- **File**: `qubox_v2/optimization/__init__.py:15`
- **Impact**: `from qubox_v2.optimization import skopt_bo` raises `ImportError`
- **Details**: `skopt_bo` is listed in `__all__` but the function body in `stochastic_opt.py` (lines 261-306) is inside a triple-quoted string literal, never actually defined.

### C4. Unconditional `from IPython.display import clear_output`

- **File**: `qubox_v2/calibration/pulse_train_tomo.py:13`
- **Impact**: Importing this module outside IPython/Jupyter raises `ImportError`
- **Details**: Top-level import with no guard. Also used unconditionally at line 148 inside the main sweep loop.

### C5. Unconditional `import cma` / `from skopt import gp_minimize`

- **Files**: `qubox_v2/optimization/stochastic_opt.py:7`, `qubox_v2/optimization/optimization.py:2`
- **Impact**: Importing these modules without `pycma` or `scikit-optimize` installed crashes immediately
- **Details**: These are optional dependencies that should be lazily imported.

---

## 3. High-Severity Issues

### H1. Kaiser DRAG correction physics differs between two files

- **Files**: `qubox_v2/tools/waveforms.py:73-167` vs `qubox_v2/pulses/waveforms.py:124-172`
- **Impact**: The two `kaiser` waveform generators produce **different waveforms** for the same inputs
- **Details**: `tools/waveforms.py` divides the DRAG derivative by `2*pi*(anharmonicity - detuning)` (correct physics). `pulses/waveforms.py` divides by bare `anharmonicity` without the `2*pi` factor and without `dt` scaling on `np.gradient()`. Any experiment using the wrong path will get incorrectly scaled DRAG quadratures.

### H2. DRAG gaussian fallback uses wrong denominator

- **File**: `qubox_v2/pulses/waveforms.py:105-117`
- **Impact**: When `qualang_tools` is not importable, the fallback DRAG computation divides by bare `anharmonicity` instead of `2*pi*anharmonicity`
- **Details**: The local `tools/waveforms.py:66` correctly uses the `2*pi` factor. The `pulses/waveforms.py` fallback does not.

### H3. `measureMacro.measure()` returns `None` when `with_state=False`

- **File**: `qubox_v2/programs/macros/measure.py:1603-1665`
- **Impact**: Callers unpacking `I, Q = measureMacro.measure(...)` get `TypeError` on the non-state path
- **Details**: The function only returns target vars when `with_state=True`. Otherwise it falls off the end returning `None`.

### H4. `measureMacro` threshold can be `None` in QUA assign

- **File**: `qubox_v2/programs/macros/measure.py:1662`
- **Impact**: `assign(state, target_vars[0] > None)` fails at QUA compilation
- **Details**: After `_apply_defaults()` or `reset()`, threshold is `None`. No guard before the QUA assign.

### H5. `prepare_state()` uses uninitialized `I` on first iteration

- **File**: `qubox_v2/programs/macros/sequence.py:295-303`
- **Impact**: First conditional reset flip is based on `I=0.0` (default QUA fixed), not an actual measurement
- **Details**: The loop does conditional_reset THEN measure. On the first iteration, `I` has never been measured.

### H6. `prepare_state()` raises `KeyError` if threshold not passed

- **File**: `qubox_v2/programs/macros/sequence.py:206`
- **Impact**: Crashes with `KeyError: 'threshold'` if caller omits it from kwargs
- **Details**: `p["threshold"]` with no default. Should fall back to `measureMacro._ro_disc_params`.

### H7. Mixer calibration scratch DB never consumed by QM reopen

- **File**: `qubox_v2/calibration/mixer_calibration.py:405-409`
- **Impact**: IQ correction trials in `save_to_db=False` mode have no effect
- **Details**: `_write_scratch_db()` writes trial values, but `open_qm()` reads from the canonical path which was not updated.

### H8. Three reset experiment classes missing `analyze()` and `plot()`

- **File**: `qubox_v2/experiments/calibration/reset.py`
- **Classes**: `QubitResetBenchmark`, `ActiveQubitResetBenchmark`, `ReadoutLeakageBenchmarking`
- **Impact**: Calling `analyze()` or `plot()` raises `NotImplementedError`
- **Details**: `ExperimentBase` requires these methods. The classes only implement `run()`.

### H9. `analyze()` idempotency violations -- global state mutation

- **File**: `qubox_v2/experiments/calibration/readout.py`
- **Impact**: `ReadoutGEDiscrimination.analyze()` registers weights into POM and updates measureMacro -- non-idempotent
- **Details**: Calling `analyze()` twice registers weights twice. The API contract explicitly states analyze must be idempotent.

### H10. `PulseTrainCalibration.analyze()` mutates `RunResult.output`

- **File**: `qubox_v2/experiments/calibration/gates.py:970-971`
- **Impact**: Writes `pred_fit_{key}` into the input `result.output` dict
- **Details**: This modifies the caller's input argument, violating idempotency.

### H11. SPSA optimizer tracks wrong best point

- **File**: `qubox_v2/analysis/calibration_algorithms.py:380-385`
- **Impact**: `best_x` records the post-gradient-update position, not the position where `best_cost` was measured
- **Details**: `y_curr` is measured at `x +/- ck*delta`, but `best_x` is saved after `x = x - ak * g_hat`.

### H12. `smooth_opt.py` `tol` placed inside `options` dict instead of as keyword arg

- **File**: `qubox_v2/optimization/smooth_opt.py:47-48`
- **Impact**: `tol` is silently ignored by most scipy solvers (L-BFGS-B, BFGS) when inside `options`
- **Details**: Should be `scipy.optimize.minimize(..., tol=tol, options=options)`.

### H13. Mutable default `drives={}` in `simulation/cQED.py`

- **File**: `qubox_v2/simulation/cQED.py:36`
- **Impact**: All instances that don't pass explicit `drives` share the same dict
- **Details**: Classic Python mutable default argument anti-pattern.

### H14. Mutable default `bounds=[(-10,10),(-10,10)]` in stochastic optimizers

- **File**: `qubox_v2/optimization/stochastic_opt.py:35-36, 73-74`
- **Impact**: If caller mutates the returned bounds, subsequent calls get corrupted defaults

---

## 4. Medium-Severity Issues

### Calibration Module

| ID | File | Line(s) | Description |
|----|------|---------|-------------|
| M1 | `calibration/orchestrator.py` | 286 | Identical if/else branches: `dict(out) if isinstance(...) else dict(out)` |
| M2 | `calibration/orchestrator.py` | 148-222 | Unrecognized patch ops silently dropped (no warning/error) |
| M3 | `calibration/store.py` | 450 | No `os.replace` retry logic on Windows (unlike `mixer_calibration.py`) |
| M4 | `calibration/pulse_train_tomo.py` | 138 | "Prep sanity check" banner prints K times (inside loop) |
| M5 | `calibration/mixer_calibration.py` | 37 | Uses `logging.getLogger` instead of project-standard `get_logger` |
| M6 | `calibration/history.py` | all | Entire module is dead code -- never imported by any file |

### Analysis Module

| ID | File | Line(s) | Description |
|----|------|---------|-------------|
| M7 | `analysis/analysis_tools.py` | 96-97 | `round_to_multiple("nearest")`: tie breaks DOWN, comment says UP |
| M8 | `analysis/analysis_tools.py` | 627-645 | `right_lines` always empty; entire if-branch is unreachable dead code |
| M9 | `analysis/calibration_algorithms.py` | 35-105 | `fit_pulse_train` overlaps with `pulse_train_models.fit_pulse_train_model` -- two fitting paths for same physics |
| M10 | `analysis/cQED_models.py` | 804-817 | `kerr_ramsey_model_` is near-duplicate of `kerr_ramsey_model` |
| M11 | `analysis/cQED_plottings.py` | 255-260 | Local `poisson_with_offset_model` duplicates `cQED_models` version |
| M12 | `analysis/__init__.py` | 1-38 | `post_selection` module not exported |

### Experiments Module

| ID | File | Line(s) | Description |
|----|------|---------|-------------|
| M13 | `experiments/session.py` | 625 | `calibration.save()` in `close()` NOT wrapped in try/except (unlike all other saves) |
| M14 | `experiments/config_builder.py` | 174, 180 | Typo: `"minius_sine_weights"` should be `"minus_sine_weights"` |
| M15 | `experiments/__init__.py` | -- | Missing exports: `SessionManager`, `RunResult`, `AnalysisResult`, `FitResult`, `ReadoutConfig` |

### Programs / Macros Module

| ID | File | Line(s) | Description |
|----|------|---------|-------------|
| M16 | `programs/macros/measure.py` | 141-148 | Mutable class-level containers shared across subclasses |
| M17 | `programs/macros/measure.py` | 1288 | `_apply_defaults()` resets `norm_params` to `None` instead of `{}` |
| M18 | `programs/macros/sequence.py` | 71-79 | `wait_after` parameter name inverts ON/OFF semantics |
| M19 | `programs/macros/sequence.py` | 361 | `prepare_state()` returns nothing; auto-declared QUA vars are lost |

### Hardware Module

| ID | File | Line(s) | Description |
|----|------|---------|-------------|
| M20 | `hardware/config_engine.py` | 101 | `self._lock = threading.RLock()` declared but never acquired -- ConfigEngine is thread-unsafe despite having a lock |
| M21 | `hardware/controller.py` | 260-264 | `get_element_lo()` skips `_check_el()` validation for list inputs |
| M22 | `hardware/qua_program_manager.py` | 128-138 | `load_hardware()` rebuilds HardwareController without passing `default_output_mode` |
| M23 | `devices/device_manager.py` | 370-388 | `get()` has race condition: releases lock before creating handle |

### Other Modules

| ID | File | Line(s) | Description |
|----|------|---------|-------------|
| M24 | `compat/__init__.py` | 111-131 | Uses deprecated PEP 302 `find_module()`/`load_module()` -- removed in Python 3.12 |
| M25 | `simulation/cQED.py` | 172 | `assert` used for input validation (stripped with `python -O`) |
| M26 | `simulation/hamiltonian_builder.py:10` vs `cQED.py:22` | -- | Duplicate `Term` dataclass definition in two files |
| M27 | `gui/program_gui.py` | 249 | `sys.exit(app.exec_())` kills entire process including Jupyter kernels |
| M28 | `gui/program_gui.py` | 165 | Assumes callable returns object with `.output` attribute |
| M29 | `migration/pulses_converter.py` | 221 | `'scale' in dir()` is an anti-pattern for checking local variable existence |

---

## 5. Low-Severity Issues

### Unused Imports

| File | Line(s) | Import |
|------|---------|--------|
| `calibration/models.py` | 10 | `Optional` (uses `X \| None` syntax instead) |
| `calibration/models.py` | 13 | `field_serializer`, `field_validator` |
| `analysis/cQED_models.py` | 3 | `matplotlib.pyplot as plt` (never used) |
| `experiments/time_domain/rabi.py` | 16 | `measureMacro` (uses `self.measure_macro` property instead) |
| `experiments/cavity/fock.py` | 5 | `Union` |
| `experiments/cavity/storage.py` | 4 | `Union` |
| `experiments/config_builder.py` | 26 | `yaml` (PyYAML dependency, never used) |
| `hardware/controller.py` | 15 | `deepcopy` |
| `hardware/controller.py` | 17 | `List` from typing |
| `hardware/queue_manager.py` | 13, 15 | `Dict, List, Optional, Union`, `numpy` |
| `simulation/cQED.py` | 5 | `matplotlib.pyplot as plt` (re-imported locally in method) |
| `simulation/cQED.py` | 8 | `scipy.sparse as sp` |
| `simulation/drive_builder.py` | 586-588 | Duplicate imports at bottom of file |
| `tools/generators.py` | 114-115 | Duplicate `numpy` and `typing` imports |
| `analysis/algorithms.py` | 159 | Duplicate `import numpy as np` |
| `analysis/algorithms.py` | 237 | Separate `from typing import List` |
| `analysis/algorithms.py` | 717 | `from math import exp, pi` when `math` already imported |
| `optimization/stochastic_opt.py` | 56, 93 | Hardcoded `seed=42` not exposed as parameter |
| `verification/waveform_regression.py` | 19 | `import math` (unused) |

### Dead Code

| File | Line(s) | Description |
|------|---------|-------------|
| `calibration/models.py` | 19-22 | `_ndarray_to_list()` function never called |
| `calibration/history.py` | all | Entire module never imported |
| `analysis/cQED_models.py` | 1215-1217 | `if __name__ == '__main__': pass` |
| `analysis/analysis_tools.py` | 408 | Commented-out `out.update(sigmas_mog_output)` |
| `analysis/algorithms.py` | 932-937 | Stale TODO comment about moving helper functions |
| `experiments/config_builder.py` | 256-258 | Duplicate `to_json()` definition (first overridden by second) |
| `experiments/cavity/fock.py` | 96-99 | `fock_freqs` list populated but never used |
| `programs/macros/measure.py` | 441-476 | Dangling triple-quoted string literal (dead commented-out code) |
| `optimization/optimization.py` | 61-97 | `test_bayesian_optimize_simple()` test function in production code |

### Encoding Issues

| File | Line(s) | Description |
|------|---------|-------------|
| `analysis/analysis_tools.py` | 73 | Corrupted Unicode en-dash (`"1\u00e2\u20ac\u2019D"` should be `"1-D"`) |
| `analysis/analysis_tools.py` | 689 | Corrupted Unicode em-dash in `"Freedman\u00e2\u20ac\u201cDiaconis"` |

### Deprecation Warnings

| File | Line(s) | Description |
|------|---------|-------------|
| `analysis/algorithms.py` | 285 | `np.trapz` deprecated in NumPy 2.0+ (use `np.trapezoid`) |
| `compat/__init__.py` | 111-131 | PEP 302 `find_module`/`load_module` deprecated since Python 3.4 |

### Missing `__all__` Definitions

| File | Description |
|------|-------------|
| `programs/builders/*.py` (all 8) | No `__all__`; wildcard re-export may leak internal names |
| `programs/cQED_programs.py` | No `__all__` on the shim |
| `tools/generators.py` | No `__all__`; star-import from `waveforms` pollutes namespace |

### Minor Naming / Style

| File | Line(s) | Description |
|------|---------|-------------|
| `analysis/cQED_models.py` | 381-430 | `T2_ramsey_model` docstring parameter order mismatches signature |
| `analysis/cQED_models.py` | 445 | Missing space: `def T2_echo_model(t, A, T2_echo, n,offset)` |
| `analysis/cQED_plottings.py` | 177 | `max_alpha` parameter undocumented in docstring |
| `calibration/patch_rules.py` | 15 | `_clone_payload` silently converts tuples to lists |

---

## 6. Notebook Issues

### `post_cavity_experiment_context.ipynb`

#### Medium Severity

| ID | Cell(s) | Description |
|----|---------|-------------|
| N1 | 33 | `analyze(update_calibration=True)` after orchestrator cycle with `apply=False` -- bypasses the orchestrator patch workflow |
| N2 | 49, 64 | Direct access to private `measureMacro._ro_quality_params` -- should use accessor methods |
| N3 | 108 | Direct `session.hw.qm.execute()` -- bypasses `ProgramRunner` (SPA pump, progress, metadata skipped) |
| N4 | 19,26,28,33,35,38,43,71,78 | Heavy reliance on private `orch._run_result_from_artifact()` (not public API) |
| N5 | 74 | Hardcoded displacement amplitude `0.019580` and selective pulse amp `0.0013420737712946228*1.2` |

#### Low Severity

| ID | Cell(s) | Description |
|----|---------|-------------|
| N6 | 1, 62 | Redundant `ReadoutConfig` import |
| N7 | 62 | Duplicate readout experiment imports |
| N8 | 62 | Uses alias `n_samples` / `measure_op` instead of canonical `n_samples_disc` / `ro_op` |
| N9 | 62 | `M0_MAX_TRIALS=1000` is 62x the default of 16 with no justification |
| N10 | 69, 92, 97, 99 | Four experiment cells entirely commented out (dead placeholder code) |
| N11 | 61 | Markdown says "state machine pipeline" -- state machine is deleted |
| N12 | 19,26,28,... | Redundant double-analyze after every orchestrator cycle |
| N13 | 23, 76, 82 | Direct `update_calibration=True` outside orchestrator workflow |

### `post_cavity_experiment.ipynb` (Sibling Notebook)

**BROKEN**: Contains imports from deleted `qubox_v2.calibration.state_machine` (content lines 1317-1333, 3069). This notebook will crash on import.

---

## 7. Cross-Module Architectural Concerns

### 7.1. Dual Waveform Libraries

`tools/waveforms.py` and `pulses/waveforms.py` both generate the same waveform types (Kaiser, DRAG Gaussian) with **different physics**. This is the highest-risk inconsistency in the codebase:

- `tools/waveforms.py` uses `2*pi*(anharmonicity - detuning)` for DRAG correction (correct)
- `pulses/waveforms.py` uses bare `anharmonicity` (missing 2*pi, missing detuning)

Any experiment that uses the `pulses/` path gets different waveforms than one using the `tools/` path.

**Recommendation**: Consolidate to a single canonical waveform library. `tools/waveforms.py` should be the source of truth; `pulses/waveforms.py` should import from it.

### 7.2. `ExperimentRunner` vs `SessionManager` Overlap

`experiments/base.py` defines `ExperimentRunner` which creates and owns hardware, config engine, pulse manager, etc. This overlaps almost entirely with `SessionManager` from `experiments/session.py`. No code currently subclasses `ExperimentRunner`.

**Recommendation**: Evaluate whether `ExperimentRunner` can be removed in favor of `SessionManager`.

### 7.3. Three Lorentzian Functions

- `analysis/models.py:lorentzian_model` (generic)
- `analysis/cQED_models.py:resonator_spec_model` (same formula, different param names)
- `analysis/cQED_models.py:qubit_spec_model` (same formula, HWHM parameterization)

**Recommendation**: Consolidate into one parameterized Lorentzian with domain-specific aliases.

### 7.4. Two Pulse-Train Fitting Paths

- `analysis/calibration_algorithms.py:fit_pulse_train` (simple least-squares)
- `analysis/pulse_train_models.py:fit_pulse_train_model` (sophisticated DE+LS, multi-seed)

Both fit the same Bloch-vector model with no cross-referencing.

**Recommendation**: Deprecate the simpler version or make it call the advanced one with simplified defaults.

### 7.5. API Reference Stale References

The API Reference (`docs/API_REFERENCE.md`) still mentions `StateMachine` in multiple locations (lines 89, 125, 404, 1994) despite `calibration/state_machine.py` being deleted.

### 7.6. Inconsistent Logger Initialization

Some modules use `get_logger(__name__)` from `core.logging` while others use `logging.getLogger(__name__)`. This could result in different formatting or output destinations.

Affected: `hardware/program_runner.py`, `calibration/mixer_calibration.py` vs the rest.

---

## 8. Housekeeping

### 8.1. Temporary Directories

19 `tmpclaude-XXXX-cwd` directories scattered throughout the source tree (5 at root, 11 in experiments/, 3 nested). These are leftover working directories from Claude Code sessions and should be deleted.

### 8.2. Orphaned `__pycache__` Entries

- `calibration/__pycache__/patch.cpython-311.pyc` (source `patch.py` deleted)
- `calibration/__pycache__/state_machine.cpython-311.pyc` (source `state_machine.py` deleted)

### 8.3. Broken Sibling Notebook

`notebooks/post_cavity_experiment.ipynb` imports from deleted `qubox_v2.calibration.state_machine` and will fail at runtime.

---

## 9. Summary Statistics

| Category | Count |
|----------|-------|
| **Critical crash bugs** | 5 |
| **High severity (logic bugs / silent failures)** | 14 |
| **Medium severity (inconsistencies / design flaws)** | 29 |
| **Low severity (dead code / style / cleanup)** | ~45 |
| **Notebook issues** | ~20 |
| **Total** | **~113** |

### Recommended Fix Priority

1. **Immediate** (session-blocking):
   - C1: Add `import numpy as np` to `simulation/solver.py`
   - C2: Fix `float(None)` in `simulation/drive_builder.py`
   - C3: Remove `skopt_bo` from `optimization/__init__.py` `__all__` or uncomment the function
   - C4-C5: Guard optional imports (`IPython`, `cma`, `skopt`)
   - H1-H2: Consolidate waveform libraries to fix DRAG physics inconsistency

2. **High priority** (wrong results / contract violations):
   - H3-H6: Fix `measureMacro` and `sequenceMacros` bugs (None threshold, uninitialized I, missing returns)
   - H8: Implement `analyze()`/`plot()` on reset experiment classes
   - H9-H10: Fix idempotency violations in readout and pulse-train analysis
   - H11: Fix SPSA best-point tracking

3. **Medium priority** (robustness / consistency):
   - M7: Fix `round_to_multiple` tie-breaking logic
   - M13: Wrap `calibration.save()` in try/except during `close()`
   - M20: Either use the lock in ConfigEngine or remove it
   - Fix broken `post_cavity_experiment.ipynb` notebook

4. **Low priority** (cleanup):
   - Remove 19 `tmpclaude-*` directories
   - Clean up ~20 unused imports
   - Remove dead code (history.py, dead functions, dangling string literals)
   - Add `__all__` to builder modules
   - Fix Unicode encoding artifacts

---

*This report is a snapshot audit. No code changes were made.*
