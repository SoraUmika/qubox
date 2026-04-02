# measureMacro Refactoring Plan

**Date:** 2026-07-17  
**Status:** Proposed  
**Author:** Architecture audit / Agent  
**Scope:** Replace the `measureMacro` class-level singleton with instance-based readout configuration

---

## 1. Problem Statement

`measureMacro` is a 1,863-line class in `qubox/programs/macros/measure.py` that uses **class-level attributes as global mutable state**. It is imported by **44 call sites across 22 files** and is the single most coupled component in the codebase.

### Why This Is the P0 Problem

| Problem | Impact |
|---------|--------|
| **Global mutable state** | All class attributes are shared process-wide. Any mutation anywhere is visible everywhere. No isolation between experiments, tests, or concurrent workflows. |
| **Blocks multi-qubit** | Each qubit needs its own discrimination params (`threshold`, `angle`, `rot_mu_g/e`, `sigma_g/e`). The singleton can only represent one readout channel at a time. |
| **Hidden coupling** | Builders implicitly depend on `measureMacro` being pre-configured. No function signature declares what readout config it needs — it silently reads from the global. |
| **Fragile state management** | `push_settings()` / `restore_settings()` is a manual stack. Forgetting a restore corrupts all subsequent experiments. The `using_defaults()` context manager helps but doesn't cover all paths. |
| **Snapshot brittleness** | `ProgramBuildResult` captures a snapshot via `try_build_readout_snapshot_from_macro()` — a point-in-time copy of global state that may already be stale by the time it's read. |
| **Test pollution** | `tools/test_all_simulations.py` directly mutates `measureMacro._ro_disc_params["threshold"] = 0.0` to avoid crashes. Tests cannot run in isolation. |
| **Mixed responsibilities** | The class is simultaneously: (1) a QUA code emitter, (2) a configuration holder, (3) a calibration state store, (4) a JSON persistence layer, (5) an analysis utility library. |

### What Already Exists

The codebase already has **four replacement types** designed but not yet adopted:

| Type | Location | Purpose | Status |
|------|----------|---------|--------|
| `ReadoutBinding` | `core/bindings.py` | Mutable per-channel readout config with `discrimination` and `quality` dicts | **Exists, populated by SessionManager, not used by builders** |
| `ReadoutCal` | `core/bindings.py` | Frozen calibration snapshot (threshold, confusion matrix, weights) | **Exists, not adopted** |
| `ReadoutHandle` | `core/bindings.py` | Frozen binding + calibration + element + operation — everything needed to measure | **Exists, not adopted** |
| `measure_with_binding()` | `programs/macros/measure.py:1897` | QUA emitter using `ReadoutBinding` | **Exists, not called anywhere** |
| `emit_measurement()` | `programs/macros/measure.py:2032` | QUA emitter using `ReadoutHandle` | **Exists, not called anywhere** |
| `emit_measurement_spec()` | `programs/measurement.py:99` | Dispatcher that already routes to `emit_measurement()` when `readout=` is provided | **Exists, `readout=` path unused** |

**The replacement infrastructure is 80% built. The problem is adoption.**

---

## 2. Architecture of the Solution

### 2.1 Target State

```
┌──────────────────────────────────────────────────────────┐
│ SessionManager.open()                                     │
│   ├─ builds ExperimentBindings (one ReadoutBinding per    │
│   │   readout channel, populated from CalibrationStore)   │
│   └─ creates ReadoutHandle (frozen) for program building  │
│                                                           │
│ ExperimentBase._build_impl(...)                           │
│   ├─ receives ReadoutHandle via self.readout_handle       │
│   └─ passes it to builder functions                       │
│                                                           │
│ Builder functions (readout.py, time_domain.py, etc.)      │
│   ├─ accept readout: ReadoutHandle as explicit parameter  │
│   ├─ call emit_measurement(readout, ...) for QUA emission │
│   └─ use readout.element / readout.cal.threshold directly │
│                                                           │
│ CalibrationOrchestrator.apply_patch()                     │
│   ├─ updates CalibrationStore (canonical)                 │
│   ├─ rebuilds ReadoutBinding from CalibrationStore        │
│   └─ (compat) syncs measureMacro too during transition    │
│                                                           │
│ measureMacro (compat shim during transition)              │
│   ├─ delegates to a per-process ReadoutBinding instance   │
│   └─ deprecated after all call sites migrate              │
└──────────────────────────────────────────────────────────┘
```

### 2.2 Key Invariants

1. **Readout config flows explicitly**: `CalibrationStore → ReadoutBinding → ReadoutHandle → builder function → QUA emission`. No implicit global reads.
2. **measureMacro becomes a thin compat shim**: During transition, `measureMacro.measure()` delegates to `measure_with_binding()` using a module-level `ReadoutBinding` instance. This keeps all existing notebooks working while builders are migrated one by one.
3. **Multi-qubit ready**: Each readout channel gets its own `ReadoutBinding`. The `ExperimentBindings.extras` dict already supports arbitrary named bindings.
4. **No big bang**: Each builder file is migrated independently. The test suite (`test_all_simulations.py`) validates after each step.

---

## 3. What measureMacro Actually Does (API Surface Decomposition)

The 1,863-line class combines **six distinct responsibilities**. The refactoring separates them:

### Category 1: QUA Code Emission (→ `emit_measurement()`)
- `measure()` — emits QUA `measure()` statement + optional `assign(state, I > threshold)`
- `active_element()` — resolves readout element name from bound PulseOp
- `active_op()` — resolves QUA operation handle

**Migration target**: Already implemented as `emit_measurement(readout: ReadoutHandle, ...)`.  
**Action needed**: Make builders call `emit_measurement()` instead of `measureMacro.measure()`.

### Category 2: Configuration Binding (→ `ReadoutBinding` / `ReadoutHandle`)
- `set_pulse_op()`, `set_active_op()`, `set_demodulator()`, `set_outputs()`, `set_gain()`, `set_drive_frequency()`, etc.
- `_demod_weight_sets`, `_demod_fn`, `_demod_args`, `_gain`, `_pulse_op`, `_active_op`

**Migration target**: `ReadoutBinding` already has `pulse_op`, `active_op`, `demod_weight_sets`, `gain`, `drive_frequency`. `ReadoutHandle` wraps it as frozen.  
**Action needed**: Populate `ReadoutBinding` where `set_pulse_op()` is called today. Build `ReadoutHandle` from it at program-build time.

### Category 3: Calibration DSP State (→ `ReadoutBinding.discrimination` / `.quality`)
- `_ro_disc_params`, `_ro_quality_params`
- `_update_readout_discrimination()`, `_update_readout_quality()`
- `sync_from_calibration()`, `export_readout_calibration()`, `get_readout_calibration()`

**Migration target**: `ReadoutBinding.discrimination` and `.quality` dicts already mirror the exact same keys.  `ReadoutBinding.sync_from_calibration()` exists.  
**Action needed**: CalibrationOrchestrator updates `ReadoutBinding` instead of `measureMacro._ro_disc_params`.

### Category 4: Persistence (→ stays on measureMacro as compat, eventually on Session)
- `save_json()`, `load_json()`, `to_json_dict()`
- `_snapshot()`, `_restore_from_snapshot()`, `_snapshot_to_json()`, `_snapshot_from_json()`

**Migration target**: `ReadoutBinding` serialization should replace measureConfig.json.  
**Action needed**: Phase 3 — after builders are migrated. SessionManager already knows how to serialize ReadoutBinding.

### Category 5: State Stack (→ eliminate)
- `push_settings()`, `restore_settings()`, `using_defaults()`, `_state_stack`

**Migration target**: With explicit parameter passing, there's no global state to save/restore. Each program build receives its own `ReadoutHandle`.  
**Action needed**: Once all builders accept `ReadoutHandle`, the stack becomes dead code.

### Category 6: Analysis Utilities (→ extract to `qubox_tools`)
- `compute_Pe_from_S()`, `compute_posterior_weights()`, `compute_posterior_state_weight()`, `check_iq_blob_rotation_consistency_2d()`

These are pure Python functions that happen to read `_ro_disc_params` for convenience. They have no QUA dependency.

**Migration target**: Move to `qubox_tools.algorithms.readout_analysis` (or similar). Accept `disc_params: dict` as explicit argument.  
**Action needed**: Phase 4 — after core migration. Low risk, can be done at any time.

---

## 4. Phased Migration Plan

### Phase 0: Infrastructure Prep (Low Risk, 1-2 days)
*Goal: Complete the replacement APIs and create the compat bridge.*

**Step 0.1 — Complete `ReadoutBinding` with missing demod fields**
`ReadoutBinding` currently lacks `demod_fn` and `per_output` overrides that `measureMacro` has. Add:
```python
@dataclass
class ReadoutBinding:
    # ... existing fields ...
    demod_fn: str = "dual_demod.full"  # Key name, not callable
    demod_fn_args: tuple = ()
    demod_fn_kwargs: dict[str, Any] = field(default_factory=dict)
    weight_length: int | None = None  # (already on InputBinding, may need duplication or reference)
```
These fields are needed by `measure_with_binding()` and `emit_measurement()` for full parity.

**Step 0.2 — Add `ReadoutHandle.from_session()` factory**
Create a factory that builds `ReadoutHandle` from `SessionManager` state (the exact operation that `_load_measure_config` + `set_pulse_op` does today):
```python
@classmethod
def from_session(cls, session: SessionManager) -> ReadoutHandle:
    """Build ReadoutHandle from current session state."""
    ro_binding = session.bindings.readout
    cal = ReadoutCal.from_readout_binding(ro_binding)
    ro_el = session.context_snapshot().ro_el
    return cls(binding=ro_binding, cal=cal, element=ro_el, operation="readout")
```

**Step 0.3 — Create compat bridge in measureMacro**
Add a module-level `_compat_binding: ReadoutBinding | None` that `measureMacro` writes to whenever its state changes. This ensures `ReadoutBinding` is always in sync during the transition:
```python
# At module level in measure.py
_compat_binding: ReadoutBinding | None = None

class measureMacro:
    @classmethod
    def _sync_to_binding(cls):
        """Push current singleton state into the module-level ReadoutBinding."""
        global _compat_binding
        if _compat_binding is None:
            _compat_binding = ReadoutBinding(...)  # construct from current state
        else:
            # update _compat_binding fields from class state
            ...
    
    # Add _sync_to_binding() call at the end of:
    # - set_pulse_op()
    # - _update_readout_discrimination()
    # - _update_readout_quality()
    # - _restore_from_snapshot()
    # - sync_from_calibration()
```

**Step 0.4 — Add `readout_handle` property to ExperimentBase**
```python
@property
def readout_handle(self) -> ReadoutHandle | None:
    """ReadoutHandle for the current session, or None if not available."""
    bindings = getattr(self._ctx, "bindings", None)
    if bindings is not None:
        return ReadoutHandle.from_readout_binding(bindings.readout)
    return None
```

**Validation**: Run `tools/test_all_simulations.py`. All 23 experiments must still PASS. No builder changes yet.

---

### Phase 1: Migrate `emit_measurement_spec` Dispatch (Low Risk, 0.5 days)
*Goal: All builder functions that go through `emit_measurement_spec()` can use the ReadoutHandle path.*

Currently `emit_measurement_spec(spec, ...)` already dispatches to `emit_measurement(readout, ...)` when `readout=` is provided. But nobody passes `readout=`.

**Step 1.1 — Thread `readout=` through builder functions that use `emit_measurement_spec`**

Affected builders (use `emit_measurement_spec` today):
- `programs/builders/time_domain.py` — `temporal_rabi()`, `t1_decay()`, `ramsey()`, `echo()`
- (Add to each):
```python
def temporal_rabi(..., readout: ReadoutHandle | None = None):
    ...
    emit_measurement_spec(measure_spec, targets=[I, Q], readout=readout)
```

When `readout` is None, the existing `measureMacro` path fires. When provided, the new `emit_measurement()` path fires. **100% backward compatible**.

**Step 1.2 — Thread `readout=` through ExperimentBase subclasses that call builders**

In `_build_impl()`:
```python
# Before:
prog = temporal_rabi(pulse, clks, gain, therm, n_avg, qb_el=qb_el)
# After:
prog = temporal_rabi(pulse, clks, gain, therm, n_avg, qb_el=qb_el, readout=self.readout_handle)
```

When `readout_handle` is None (no bindings available), same behavior as today.

**Validation**: Run `test_all_simulations.py`. Then manually test a single experiment with `readout_handle` populated.

---

### Phase 2: Migrate `readout.py` Builders (Medium Risk, 2-3 days)
*Goal: The heaviest consumer (40+ refs) accepts `ReadoutHandle`.*

This is the core of the migration. `programs/builders/readout.py` has the densest `measureMacro` usage.

**Strategy**: Add `readout: ReadoutHandle | None = None` parameter to each function. When provided, use `readout.element` instead of `measureMacro.active_element()` and `emit_measurement(readout, ...)` instead of `measureMacro.measure(...)`. When None, fall back to existing singleton behavior.

**Migration order** (simplest to most complex):

| Priority | Function | measureMacro refs | Notes |
|----------|----------|-------------------|-------|
| 1 | `build_iq_blob_readout()` | 2 (measure + active_element) | Simplest: single measure call |
| 2 | `build_adc_readout()` | 4 (measure×2 + active_element×2) | Similar pattern |
| 3 | `build_sliced_readout_ge()` | 6+ | Uses set_outputs + set_demodulator |
| 4 | `build_single_shot_readout()` | 2 | Simple measure call |
| 5 | `build_active_reset_readout()` | 4 | measure + state + threshold |
| 6 | `build_active_reset_ge_readout()` | 8 | measure×3 + threshold + active_element |
| 7 | `build_two_shot_readout()` | 6 | measure×2 + active_element×2 |
| 8 | `build_spa_readout_opt()` | 12+ | Most complex: multi-measurement + threshold |
| 9 | `build_qubit_reset_benchmark()` | 8+ | measure×3 + active_element×3 |

**Per-function migration pattern**:
```python
# BEFORE
def build_iq_blob_readout(qb_op, n_shots, *, qb_el="qubit", bindings=None):
    ...
    measureMacro.measure(targets=[I, Q])
    ...

# AFTER
def build_iq_blob_readout(qb_op, n_shots, *, qb_el="qubit", bindings=None, readout=None):
    ...
    if readout is not None:
        emit_measurement(readout, targets=[I, Q])
    else:
        measureMacro.measure(targets=[I, Q])
    ...
```

**For `active_element()` replacement**:
```python
# BEFORE
align(qb_el, measureMacro.active_element())
wait(int(therm_clks), measureMacro.active_element())

# AFTER  
ro_el = readout.element if readout is not None else measureMacro.active_element()
align(qb_el, ro_el)
wait(int(therm_clks), ro_el)
```

**For threshold access**:
```python
# BEFORE
thr = measureMacro._ro_disc_params.get("threshold") or 0.0

# AFTER
thr = (readout.cal.threshold if readout is not None else measureMacro._ro_disc_params.get("threshold")) or 0.0
```

**Validation after each function**: Run the specific simulation test that exercises that builder. After all functions: full `test_all_simulations.py`.

---

### Phase 2B: Migrate Other Builders (Medium Risk, 1-2 days)

Same pattern applied to:
- `programs/builders/spectroscopy.py`
- `programs/builders/calibration.py`
- `programs/builders/cavity.py`
- `programs/builders/simulation.py`
- `programs/builders/utility.py`
- `programs/builders/tomography.py`
- `programs/macros/sequence.py` (sequenceMacros)

Each of these has 1-5 `measureMacro` references. Same dual-path pattern.

---

### Phase 3: Migrate Infrastructure (Medium Risk, 1-2 days)
*Goal: SessionManager and CalibrationOrchestrator work primarily through ReadoutBinding.*

**Step 3.1 — Session._load_measure_config() populates ReadoutBinding**

Instead of loading measureConfig.json directly into `measureMacro`, load it into the session's `ReadoutBinding`. Then sync to `measureMacro` for backward compat:

```python
def _load_measure_config(self):
    # Load into ReadoutBinding (primary)
    path = self._resolve_path("measureConfig.json", required=False)
    if path is not None:
        self._populate_readout_binding_from_json(path)
    
    # Sync CalibrationStore → ReadoutBinding
    self.bindings.readout.sync_from_calibration(self.calibration)
    
    # Compat: sync ReadoutBinding → measureMacro
    self._sync_binding_to_measure_macro()
```

**Step 3.2 — CalibrationOrchestrator.apply_patch() updates ReadoutBinding first**

The orchestrator already syncs both `measureMacro` and `ReadoutBinding` (lines 187-204 of orchestrator.py). Flip the priority: `ReadoutBinding` becomes primary, `measureMacro` sync becomes the compat path.

**Step 3.3 — override_readout_operation() updates ReadoutBinding**

Same pattern: update `ReadoutBinding` first, then sync to `measureMacro`.

**Validation**: Full notebook execution flow (00 → 16) must work unchanged.

---

### Phase 4: Extract Analysis Utilities (Low Risk, 0.5 days)
*Goal: Pure-Python analysis functions no longer live on the singleton.*

Move to `qubox_tools/algorithms/readout_analysis.py`:
- `compute_Pe_from_S(S, rot_mu_g, rot_mu_e)` — add explicit params
- `compute_posterior_weights(S, disc_params, ...)` — accept dict
- `compute_posterior_state_weight(S, disc_params, ...)` — accept dict
- `check_iq_blob_rotation_consistency_2d(S_g, S_e, disc_params, ...)` — accept dict

Leave thin wrappers on `measureMacro` that delegate to the extracted functions with `cls._ro_disc_params`.

**Validation**: Any notebook or experiment that calls these analysis functions must produce identical results.

---

### Phase 5: Deprecate and Slim measureMacro (Low Risk, 1 day)
*Goal: measureMacro becomes a thin compat shim.*

After Phases 1-4, `measureMacro` usage falls into two buckets:
1. **Builders that haven't been updated** (if any): still use the dual-path pattern
2. **Notebooks and tools** that import `measureMacro` directly (e.g., `measureMacro._ro_disc_params["threshold"] = 0.0`)

**Step 5.1 — Deprecation warnings**
Add `warnings.warn("measureMacro.X is deprecated, use ReadoutHandle", DeprecationWarning, stacklevel=2)` to:
- `measure()`
- `set_pulse_op()`
- `active_element()`
- Direct `_ro_disc_params` access (via `__getattr__` or property if refactored to instance)

**Step 5.2 — Remove dead code**
Once all builders pass `readout=`, remove:
- `push_settings()` / `restore_settings()` / `_state_stack` (no longer needed)
- `_snapshot()` / `_restore_from_snapshot()` (replaced by `ReadoutBinding` serialization)
- All per-output demod machinery (`_per_fn`, `_per_args`, `_per_kwargs`)
- `_callable_registry()` and JSON compat layers for v1-v4

**Step 5.3 — Slim the file**
Target: `measure.py` drops from 1,863 lines to ~200 (compat shim + `emit_measurement()`).

---

## 5. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Breaking existing experiments during transition | **High** | Dual-path pattern (`readout=None` falls back to singleton). Run `test_all_simulations.py` after every function migration. |
| Stale measureMacro state when ReadoutBinding is primary | **Medium** | Phase 0.3 compat bridge keeps them in sync bidirectionally during transition. |
| Notebooks break because they directly access `_ro_disc_params` | **Medium** | Thin compat wrappers preserve the attribute access pattern. Deprecation warnings give visibility. |
| `sequenceMacros` tight coupling to `measureMacro.active_element()` | **Low** | Same dual-path pattern: add `readout=` parameter, fall back to singleton. |
| Multi-qubit experiments need multiple ReadoutHandles | **Low** | `ExperimentBindings.extras` already supports this. The new API is multi-qubit-ready by design. |
| JSON persistence format change | **Low** | Phase 3 only. Backward-compatible loading of measureConfig.json is preserved. |

---

## 6. Validation Strategy

### Per-Function Validation (Phases 1-2)
After each builder function is migrated:
1. Run the corresponding experiment category from `test_all_simulations.py`
2. Compare compiled QUA program structure (pulse ordering, measure calls, align placement)
3. Both code paths must produce identical programs

### Full Suite Validation (After Each Phase)
1. `python tools/test_all_simulations.py` — all 23 categories PASS
2. Compile and simulate one experiment per category with `ReadoutHandle` provided
3. Verify `measureConfig.json` round-trip (save → load → build → compare)

### Notebook Validation (Phase 3)
1. Run notebooks 00 → 16 sequentially
2. Verify no `DeprecationWarning` in the critical path (only if using new API)
3. Verify calibration patches still propagate to both ReadoutBinding and measureMacro

---

## 7. Migration Effort Summary

| Phase | Description | Risk | Effort | Prerequisite |
|-------|-------------|------|--------|--------------|
| **0** | Infrastructure prep (compat bridge, factories) | Low | 1-2 days | None |
| **1** | `emit_measurement_spec` callers | Low | 0.5 days | Phase 0 |
| **2** | `readout.py` builders (40+ refs) | Medium | 2-3 days | Phase 0 |
| **2B** | Other builders (6 files) | Medium | 1-2 days | Phase 0 |
| **3** | Session + Orchestrator infrastructure | Medium | 1-2 days | Phases 1-2 |
| **4** | Extract analysis utilities | Low | 0.5 days | None (independent) |
| **5** | Deprecate + slim measureMacro | Low | 1 day | Phases 1-4 |

**Total estimated effort: 7-11 working days**

---

## 8. File Change Map

Files that will be modified, by phase:

### Phase 0
- `qubox/core/bindings.py` — add fields to ReadoutBinding, add `ReadoutHandle.from_session()`
- `qubox/programs/macros/measure.py` — add compat bridge (`_sync_to_binding`)
- `qubox/experiments/experiment_base.py` — add `readout_handle` property

### Phase 1
- `qubox/programs/builders/time_domain.py` — add `readout=` parameter
- `qubox/programs/measurement.py` — no change (already dispatches)
- Relevant experiment subclasses — pass `readout_handle` to builders

### Phase 2
- `qubox/programs/builders/readout.py` — add `readout=` to all 9 functions
- `qubox/experiments/calibration/readout.py` — pass `readout_handle` to builders

### Phase 2B
- `qubox/programs/builders/spectroscopy.py`
- `qubox/programs/builders/calibration.py`
- `qubox/programs/builders/cavity.py`
- `qubox/programs/builders/simulation.py`
- `qubox/programs/builders/utility.py`
- `qubox/programs/builders/tomography.py`
- `qubox/programs/macros/sequence.py`

### Phase 3
- `qubox/experiments/session.py` — ReadoutBinding as primary in `_load_measure_config()`
- `qubox/calibration/orchestrator.py` — ReadoutBinding as primary in `apply_patch()`

### Phase 4
- `qubox_tools/algorithms/` — new `readout_analysis.py`
- `qubox/programs/macros/measure.py` — thin delegation wrappers

### Phase 5
- `qubox/programs/macros/measure.py` — remove dead code, add deprecation warnings
- `qubox/notebook/__init__.py` — export `ReadoutHandle` alongside deprecated `measureMacro`
- `tools/test_all_simulations.py` — use `ReadoutHandle` instead of singleton mutation

---

## 9. Decision Points for User

Before execution, confirm:

1. **Start with Phase 0?** — This is zero-risk prep work. Ready to proceed?
2. **Migration order within Phase 2** — Start with simplest builders (`build_iq_blob_readout`) or most impactful (`build_active_reset_readout`)?
3. **Analysis utility extraction (Phase 4)** — Should `compute_Pe_from_S` etc. move to `qubox_tools` now (parallel with Phase 1), or wait until after builders are done?
4. **Persistence format** — Keep `measureConfig.json` as the canonical format, or migrate to a `ReadoutBinding`-native format in Phase 3?
5. **Deprecation timeline** — When should `measureMacro.measure()` start emitting `DeprecationWarning`? (Phase 5, or earlier?)
