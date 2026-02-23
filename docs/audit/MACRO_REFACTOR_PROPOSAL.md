# Macro System Refactor Proposal & Migration Plan

**Version**: 1.0.0
**Date**: 2026-02-22
**Status**: Audit Document — Deliverable 3 of Macro System Audit

---

## Table of Contents

1. [Goals and Constraints](#1-goals-and-constraints)
2. [Proposed cQED\_programs Modularization](#2-proposed-cqed_programs-modularization)
3. [Clean Macro Interface Contracts](#3-clean-macro-interface-contracts)
4. [Four-Phase Migration Plan](#4-four-phase-migration-plan)
5. [Risk Assessment](#5-risk-assessment)

---

## 1. Goals and Constraints

### 1.1 Goals

1. **Eliminate dual-truth stores** — single source of truth for discrimination
   and quality params, with `CalibrationStore` as canonical.
2. **Make macro dependencies explicit** — program factories should declare their
   readout configuration requirements via parameters, not implicit singleton reads.
3. **Modularize cQED\_programs** — break the 2914-line monolith into domain
   sub-modules with clean boundaries.
4. **Enforce analyze() purity** — no disk I/O or global state mutation from
   `analyze()` methods.

### 1.2 Constraints

- **Legacy parity**: All waveform generation, sign conventions, and calibration
  semantics must be preserved.  Experiments must produce identical QUA programs
  for identical inputs.
- **Notebook UX**: The user-facing `run() → analyze() → plot()` pattern must
  remain unchanged.  Existing notebooks should work without modification during
  the migration.
- **No big-bang rewrite**: Each phase must be independently deployable and
  reversible.
- **Patch-based calibration**: All calibration writes must flow through
  `CalibrationOrchestrator.apply_patch()` or `guarded_calibration_commit()`.

---

## 2. Proposed cQED\_programs Modularization

### 2.1 Target Module Structure

```
qubox_v2/programs/
    __init__.py
    macros/
        __init__.py
        measure.py          ← measureMacro (refactored)
        sequence.py          ← sequenceMacros (unchanged)
    builders/
        __init__.py
        spectroscopy.py      ← 8 functions migrated from cQED_programs
        time_domain.py       ← 10 functions
        readout.py           ← 6 functions
        calibration.py       ← 7 functions
        cavity.py            ← 11 functions (includes Fock-resolved)
        tomography.py        ← 3 functions
        utility.py           ← continuous_wave, SPA_flux_optimization
        simulation.py        ← sequential_simulation (isolates gate import)
    cQED_programs.py         ← Phase 1-2: re-export shim; Phase 4: removed
```

### 2.2 Migration of Individual Functions

Each existing re-export wrapper in `programs/` already defines the correct
grouping.  The migration moves **function bodies** from `cQED_programs.py`
into the corresponding `builders/` module.

| Current Function | Current Line | Target Module | Notes |
|------------------|-------------|---------------|-------|
| `readout_trace` | 10 | `builders/spectroscopy.py` | |
| `resonator_spectroscopy` | 40 | `builders/spectroscopy.py` | |
| `resonator_power_spectroscopy` | 75 | `builders/spectroscopy.py` | |
| `qubit_spectroscopy` | 111 | `builders/spectroscopy.py` | |
| `qubit_spectroscopy_ef` | 151 | `builders/spectroscopy.py` | |
| `resonator_spectroscopy_x180` | 620 | `builders/spectroscopy.py` | |
| `storage_spectroscopy` | 1752 | `builders/cavity.py` | Cavity spectroscopy |
| `num_splitting_spectroscopy` | 1781 | `builders/cavity.py` | Uses sequenceMacros |
| `temporal_rabi` | 194 | `builders/time_domain.py` | |
| `power_rabi` | 230 | `builders/time_domain.py` | |
| `time_rabi_chevron` | 267 | `builders/time_domain.py` | |
| `power_rabi_chevron` | 310 | `builders/time_domain.py` | |
| `ramsey_chevron` | 351 | `builders/time_domain.py` | |
| `T1_relaxation` | 397 | `builders/time_domain.py` | |
| `T2_ramsey` | 433 | `builders/time_domain.py` | Uses sequenceMacros |
| `T2_echo` | 468 | `builders/time_domain.py` | Uses sequenceMacros |
| `ac_stark_shift` | 733 | `builders/time_domain.py` | |
| `residual_photon_ramsey` | 776 | `builders/time_domain.py` | |
| `iq_blobs` | 699 | `builders/readout.py` | |
| `readout_ge_raw_trace` | 816 | `builders/readout.py` | |
| `readout_ge_integrated_trace` | 856 | `builders/readout.py` | **Side-effecting** — needs macro config migration |
| `readout_core_efficiency_calibration` | 967 | `builders/readout.py` | Complex; ~280 lines |
| `readout_butterfly_measurement` | 1094 | `builders/readout.py` | |
| `readout_leakage_benchmarking` | 1250 | `builders/readout.py` | |
| `all_xy` | 1299 | `builders/calibration.py` | |
| `randomized_benchmarking` | 1329 | `builders/calibration.py` | |
| `qubit_pulse_train_legacy` | 1420 | `builders/calibration.py` | |
| `qubit_pulse_train` | 1537 | `builders/calibration.py` | |
| `drag_calibration_YALE` | 1629 | `builders/calibration.py` | |
| `drag_calibration_GOOGLE` | 1680 | `builders/calibration.py` | |
| `sequential_qb_rotations` | 666 | `builders/calibration.py` | |
| `qubit_state_tomography` | 506 | `builders/tomography.py` | Uses sequenceMacros |
| `fock_resolved_state_tomography` | 2215 | `builders/tomography.py` | Uses sequenceMacros |
| `sel_r180_calibration0` | 1800 | `builders/cavity.py` | |
| `fock_resolved_spectroscopy` | 1903 | `builders/cavity.py` | Uses sequenceMacros |
| `fock_resolved_T1_relaxation` | 2104 | `builders/cavity.py` | |
| `fock_resolved_power_rabi` | 2155 | `builders/cavity.py` | |
| `fock_resolved_qb_ramsey` | 2187 | `builders/cavity.py` | |
| `storage_wigner_tomography` | 2411 | `builders/cavity.py` | |
| `phase_evolution_prog` | 2473 | `builders/cavity.py` | |
| `storage_chi_ramsey` | 2530 | `builders/cavity.py` | |
| `storage_ramsey` | 2572 | `builders/cavity.py` | |
| `qubit_reset_benchmark` | 2623 | `builders/readout.py` | Uses sequenceMacros |
| `active_qubit_reset_benchmark` | 2699 | `builders/readout.py` | Uses sequenceMacros |
| `continuous_wave` | 2844 | `builders/utility.py` | No macro dependency |
| `SPA_flux_optimization` | 2855 | `builders/utility.py` | |
| `sequential_simulation` | 2880 | `builders/simulation.py` | **Isolates** Gate/GateArray import |

### 2.3 Backward Compatibility Shim

During migration, `cQED_programs.py` is reduced to a re-export shim:

```python
# qubox_v2/programs/cQED_programs.py — backward compatibility shim
# All functions have been migrated to qubox_v2/programs/builders/
from .builders.spectroscopy import *    # noqa: F401,F403
from .builders.time_domain import *     # noqa: F401,F403
from .builders.readout import *         # noqa: F401,F403
from .builders.calibration import *     # noqa: F401,F403
from .builders.cavity import *          # noqa: F401,F403
from .builders.tomography import *      # noqa: F401,F403
from .builders.utility import *         # noqa: F401,F403
from .builders.simulation import *      # noqa: F401,F403
```

Existing `from ...programs import cQED_programs` imports continue to work
unchanged.

---

## 3. Clean Macro Interface Contracts

### 3.1 MeasurementSpec (New Abstraction)

Replace the implicit singleton contract with an explicit, immutable
configuration object.

```python
@dataclass(frozen=True)
class MeasurementSpec:
    """Resolved readout configuration for QUA program construction."""
    element: str
    operation: str
    weight_sets: list[list[str]]
    demod_fn: str                     # key from callable registry
    demod_args: tuple = ()
    demod_kwargs: dict = field(default_factory=dict)
    weight_len: int | None = None
    gain: float | None = None
    threshold: float = 0.0

    @classmethod
    def from_macro(cls) -> "MeasurementSpec":
        """Snapshot current measureMacro state into an immutable spec."""
        # ... reads _pulse_op, _active_op, _demod_weight_sets, etc.

    @classmethod
    def from_session(cls, session) -> "MeasurementSpec":
        """Build from SessionManager + CalibrationStore (canonical path)."""
        # ... reads calibration store, pulse manager

    def emit_measure(self, *, with_state=False, targets=None, state=None):
        """Emit QUA measure() statement from this spec (no singleton access)."""
        # ... same logic as measureMacro.measure() but reads from self
```

**Usage in refactored program builder:**

```python
# qubox_v2/programs/builders/spectroscopy.py (Phase 3)
def resonator_spectroscopy(
    ro_el: str,
    if_frequencies,
    depletion_len: int,
    n_avg: int = 1,
    *,
    mspec: MeasurementSpec | None = None,   # explicit readout config
):
    # Backward compat: fall back to singleton if no spec provided
    if mspec is None:
        mspec = MeasurementSpec.from_macro()

    with program() as prog:
        # ... uses mspec.element, mspec.emit_measure(), etc.
```

### 3.2 measureMacro Sync Protocol

Establish a one-way sync: `CalibrationStore → measureMacro`.

```python
# qubox_v2/programs/macros/measure.py — new public method
@classmethod
def sync_from_calibration(cls, cal_store: CalibrationStore, element: str) -> None:
    """
    Populate _ro_disc_params and _ro_quality_params from the canonical
    CalibrationStore.  Called by SessionManager.open() and after any
    calibration commit.

    Direction: CalibrationStore → measureMacro (never reverse).
    """
    disc = cal_store.get_discrimination(element)
    if disc is not None:
        cls._ro_disc_params["threshold"] = disc.threshold
        cls._ro_disc_params["angle"] = disc.angle
        cls._ro_disc_params["fidelity"] = getattr(disc, "fidelity", None)
        # ... map all fields

    quality = cal_store.get_readout_quality(element)
    if quality is not None:
        cls._ro_quality_params["F"] = quality.F
        cls._ro_quality_params["Q"] = quality.Q
        # ... map all fields
```

### 3.3 Experiment analyze() Purity Contract

```
RULE: analyze() methods MUST NOT:
  1. Call measureMacro._update_readout_discrimination()
  2. Call measureMacro._update_readout_quality()
  3. Call measureMacro.save_json()
  4. Call CalibrationStore.set_*() without going through
     guarded_calibration_commit() or CalibrationOrchestrator.

analyze() methods MUST:
  1. Return proposed calibration updates in AnalysisResult.metadata
  2. Let the caller (run() or notebook) decide whether to commit
```

### 3.4 Confusion Matrix Access Pattern

Replace direct `measureMacro._ro_quality_params.get("confusion_matrix")`
with a public accessor:

```python
# On ExperimentBase or a calibration helper module
def get_confusion_matrix(self, element: str | None = None) -> np.ndarray | None:
    """
    Read confusion matrix from CalibrationStore (preferred)
    or measureMacro (fallback).
    """
    el = element or self.attr.ro_el
    cal = self.calibration_store
    if cal is not None:
        rq = cal.get_readout_quality(el)
        if rq is not None and rq.confusion_matrix is not None:
            return np.asarray(rq.confusion_matrix)
    # Fallback to macro
    return self.measure_macro._ro_quality_params.get("confusion_matrix")
```

---

## 4. Four-Phase Migration Plan

### Phase 1: Structural Split (No Behavioral Change)

**Goal**: Move function bodies from `cQED_programs.py` into `builders/`
sub-modules.  No API changes.  No macro interface changes.

**Steps**:

1. Create `qubox_v2/programs/builders/` directory with `__init__.py`.
2. For each builder module (`spectroscopy.py`, `time_domain.py`, etc.):
   - Move function bodies from `cQED_programs.py`.
   - Preserve exact function signatures and docstrings.
   - Import `measureMacro` and `sequenceMacros` as before.
3. Replace `cQED_programs.py` with backward-compatibility re-export shim.
4. Update the existing `programs/spectroscopy.py` (etc.) wrappers to
   import from `builders/` instead of `cQED_programs`.
5. Move `sequential_simulation` to `builders/simulation.py`; move
   `Gate`/`GateArray`/`Measure` imports to that module only (resolves E3).

**Validation**:
- All existing `from ...programs import cQED_programs` imports work unchanged.
- All experiment `run()` methods produce identical QUA programs.
- `import qubox_v2.programs.cQED_programs; dir(...)` returns same symbols.

**Reversibility**: Revert by restoring original `cQED_programs.py`.

---

### Phase 2: Eliminate Direct Macro Mutation (analyze Purity)

**Goal**: Remove all direct `measureMacro._update_*()` calls from experiment
code.  Route all calibration updates through patches.

**Steps**:

1. **ReadoutGEDiscrimination.analyze()** (`readout.py:806`):
   - Remove `measureMacro._update_readout_discrimination(metrics)`.
   - Store proposed discrimination params in
     `AnalysisResult.metadata["proposed_discrimination"]`.
   - Add `SetMeasureDiscrimination` patch operation type to orchestrator.
   - Update `CalibrateReadoutFull` pipeline to apply the patch.

2. **ReadoutButterflyMeasurement.analyze()** (`readout.py:1794`):
   - Remove `measureMacro._update_readout_quality(payload)`.
   - Store proposed quality params in
     `AnalysisResult.metadata["proposed_readout_quality"]`.
   - Add `SetMeasureQuality` patch operation type to orchestrator.

3. **Remove measureMacro.save_json() from analyze paths** (`readout.py:817,2198`):
   - All `save_json()` calls move to `CalibrationOrchestrator.apply_patch()`
     via the existing `PersistMeasureConfig` operation.

4. **Confusion matrix access** (`gates.py:91,548,884`):
   - Replace `measureMacro._ro_quality_params.get("confusion_matrix")`
     with `self.get_confusion_matrix()` (new ExperimentBase helper per §3.4).

5. **Fix stale reference** (`sequence.py:380`):
   - Replace `getattr(measureMacro, "_threshold", 0.0)` with
     `measureMacro._ro_disc_params.get("threshold", 0.0)`.

**Validation**:
- `ReadoutGEDiscrimination.analyze()` returns identical `AnalysisResult` but
  without mutating measureMacro.
- `CalibrateReadoutFull.run()` produces identical end-state (discrimination
  and quality params committed via orchestrator).
- AllXY, DRAG, QubitPulseTrain confusion-matrix correction unchanged.

**Reversibility**: Each change is a single-file edit.  Revert individually.

---

### Phase 3: Establish CalibrationStore → measureMacro Sync

**Goal**: Resolve dual-truth stores.  `CalibrationStore` becomes canonical;
`measureMacro` is a derived cache.

**Steps**:

1. **Add `measureMacro.sync_from_calibration()`** (per §3.2):
   - Populates `_ro_disc_params` and `_ro_quality_params` from CalibrationStore.

2. **Call sync on SessionManager.open()**:
   ```python
   # session.py: after CalibrationStore and measureMacro are loaded
   if self.calibration and hasattr(measureMacro, 'sync_from_calibration'):
       measureMacro.sync_from_calibration(self.calibration, self.attributes.ro_el)
   ```

3. **Call sync after every calibration commit**:
   - In `CalibrationOrchestrator.apply_patch()`, after `calibration.save()`:
     ```python
     measureMacro.sync_from_calibration(self.session.calibration, element)
     ```

4. **Add measureMacro.save_json() to SessionManager.close()** (resolves C3):
   ```python
   # session.py close()
   try:
       from ..programs.macros.measure import measureMacro
       dst = self.experiment_path / "config" / "measureConfig.json"
       measureMacro.save_json(str(dst))
   except Exception as e:
       _logger.warning("Error saving measureConfig: %s", e)
   ```

5. **Deprecate direct `_update_readout_discrimination` / `_update_readout_quality`**:
   - Add `warnings.warn("Deprecated: use CalibrationOrchestrator", DeprecationWarning)`
     to both methods.

**Validation**:
- After session open, `measureMacro._ro_disc_params["threshold"]` matches
  `CalibrationStore.get_discrimination(element).threshold`.
- After calibration commit, `measureMacro` state reflects the committed values.
- `measureConfig.json` saved on close contains latest synced state.

**Reversibility**: Remove sync calls; behavior reverts to Phase 2 state.

---

### Phase 4: Introduce MeasurementSpec (Optional, Future)

**Goal**: Make program builders independent of the singleton by accepting
`MeasurementSpec` as an explicit parameter.

**Steps**:

1. **Create MeasurementSpec** (per §3.1) in `qubox_v2/programs/measurement_spec.py`.

2. **Add optional `mspec` parameter** to all builder functions:
   - Default `None` → fall back to `MeasurementSpec.from_macro()`.
   - Preserves backward compatibility.

3. **Update ExperimentBase.run\_program()** to auto-create spec:
   ```python
   def run_program(self, prog, *, mspec=None, **kw):
       if mspec is None:
           mspec = MeasurementSpec.from_session(self._ctx)
       # pass mspec through if program supports it
   ```

4. **Refactor `measureMacro.measure()`** to delegate to `MeasurementSpec.emit_measure()`.

5. **Remove `cQED_programs.py` re-export shim** — all consumers import from
   `builders/` directly or via the domain wrapper modules.

**Validation**:
- Programs built with explicit `MeasurementSpec` produce identical QUA IR to
  singleton-based programs.
- `measureMacro.measure()` still works for any code not yet migrated.

**Reversibility**: Remove `mspec` parameters; functions fall back to singleton.

---

## 5. Risk Assessment

| Phase | Risk | Mitigation |
|-------|------|------------|
| 1 | Import path breakage | Backward-compat shim ensures all existing imports work |
| 1 | Subtle function-body copy errors | Diff `cQED_programs.py` against `builders/*` to verify exact match |
| 2 | Readout calibration regression | Run `CalibrateReadoutFull` end-to-end; compare discrimination params, confusion matrix, butterfly metrics |
| 2 | Patch rule coverage gaps | Verify `DiscriminationRule` and `ReadoutQualityRule` in orchestrator produce equivalent patches |
| 3 | Sync timing issues | Test scenario: calibration commit → verify `measureMacro._ro_disc_params` matches within same cell |
| 3 | `measureConfig.json` load order | `sync_from_calibration()` must be called **after** both `load_json()` and `CalibrationStore` load; CalibrationStore wins |
| 4 | Dual-path maintenance burden | During transition, both singleton and MeasurementSpec paths must be supported and tested |
| All | Legacy notebook breakage | All phases preserve existing notebook cell patterns; only internal wiring changes |

---

*Cross-reference: MACRO_PROGRAM_ARCHITECTURE.md, MACRO_ENTANGLEMENT_REPORT.md,
API Reference §14-15, MODULARITY_RECOMMENDATIONS.md.*
