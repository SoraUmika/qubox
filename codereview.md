# qubox_v2 Code Review — Comprehensive Audit Report

**Date:** 2026-02-25
**Codebase version:** v1.8.0 (commit `163b48e`)
**Scope:** Full qubox_v2 package — calibration, experiments, hardware, programs, analysis, session management
**Mode:** Read-only analysis; no code changes made

---

## Executive Summary

This audit surveyed ~30,000 lines across the qubox_v2 package: 60+ experiment classes,
the calibration orchestrator and store, the hardware/config engine, the pulse operation
manager, the measureMacro readout singleton, and the session lifecycle.  Documentation
in `API_REFERENCE.md` (v1.8.0) and `CHANGELOG.md` served as the baseline for expected
behavior.

**Top findings (highest risk first):**

1. **No timeout on QUA program execution** — a hung QM job blocks the Python process
   indefinitely with no interrupt mechanism.
2. **Silent exception swallowing in the post-patch sync path** — `orchestrator.py:233`
   and `session.py:close()` catch `Exception` and continue, meaning the calibration
   store can diverge from the measureMacro runtime state without any user-visible error.
3. **Readout calibration has incomplete transaction boundaries** — strict-mode weight
   refresh (readout.py:682-716) has two independent try/except blocks; if the first
   succeeds and the second fails, measureMacro labels and definitions are inconsistent.
4. **PulseOperationManager `burn_to_config` uses dict `.update()`** — silent key
   collision overwrites previously burned entries with no warning or merge validation.
5. **`measureMacro` is module-level mutable singleton** — class-level dicts shared
   across all call sites with no locking; thread-unsafe and difficult to test.
6. **Discrimination threshold stored in measureMacro but never compiled into QM
   config** — the threshold is a Python-only concept that diverges if the QUA program
   applies a different decision boundary.
7. **Storage spectroscopy writes `qubit_freq` path for a storage element** — semantic
   mismatch in calibration patch target.
8. **Referenced audit documents missing** — `READOUT_PIPELINE_AUDIT.md` and
   `AUDIT_REPORT.md` are cited in `CHANGELOG.md` but do not exist on disk.
9. **Config engine uses dict replacement for pulse overlay but deep-merge for element
   ops** — partial rebuild can silently drop previously merged waveforms.
10. **Aggressive raw-key persistence filter drops small arrays** — any array whose key
    matches `/raw|shot|buffer|acq/` is discarded regardless of size.

---

## System Overview

```
                     SessionManager
                    /       |       \
          ConfigEngine    CalibrationStore    HardwareController
              |                |                     |
     PulseOperationMgr    CalibOrchestrator      ProgramRunner
              |                |
         PulseFactory      PatchRules (12 kinds)
              |
         measureMacro (singleton)
```

**Key architectural contracts (from API_REFERENCE.md):**

- Calibration parameters NEVER auto-update from `analyze()`.
- `analyze()` is idempotent; mutations go through the CalibrationOrchestrator patch
  pipeline only.
- Experiments never generate waveforms; PulseFactory + POM own all pulse compilation.
- `ExperimentContext` (sample, cooldown, wiring_rev) provides identity; mismatches
  raise `ContextMismatchError`.
- Schema version: calibration.json v4.0.0, hardware.json v1, measureConfig.json v5.

**Lifecycle:** `SessionManager.open()` → merge pulses → open QM → load measureConfig
→ preflight → experiments → `close()` (save + disconnect).

---

## Top Risks (Ranked)

Risk is scored as **likelihood x severity** where each factor is High/Medium/Low.

---

### R1. No Timeout on QUA Program Execution

| | |
|---|---|
| **Likelihood** | Medium — QM hardware hangs are not rare during development |
| **Severity** | High — Python process blocks indefinitely; only Ctrl-C recovers |
| **Location** | `hardware/program_runner.py` — `run_program()` |

`run_program()` enters a `while handles.is_processing(): time.sleep(0.05)` loop
with no elapsed-time check and no `timeout_sec` parameter.  If the OPX/Octave
becomes unresponsive, the notebook cell hangs forever.

**Recommendation:** Add an optional `timeout_sec` parameter; track elapsed time in
the progress loop; call `job.halt()` and raise `TimeoutError` on expiry.

---

### R2. Silent Exception Swallowing in Post-Patch Sync

| | |
|---|---|
| **Likelihood** | Medium — sync failures occur when cal store schema changes |
| **Severity** | High — calibration store and measureMacro silently diverge |
| **Locations** | `calibration/orchestrator.py:231-234`, `experiments/session.py:close()` |

After every `apply_patch`, the orchestrator calls
`measureMacro.sync_from_calibration()` inside a bare `except Exception` that
logs a warning but continues.  Similarly, `session.close()` wraps every save and
disconnect in individual `except Exception: logger.warning(...)` blocks.

The practical consequence: a user commits a readout calibration patch, the sync
step fails (e.g., due to a schema change), and the measureMacro continues running
with stale discrimination parameters.  No error is raised; the only signal is a
log line that is easily missed in notebook output.

```python
# orchestrator.py:231-234
try:
    measureMacro.sync_from_calibration(self.session.calibration, ro_el)
except Exception as exc:
    _logger.warning("measureMacro sync_from_calibration failed: %s", exc)
```

**Recommendation:** At minimum, re-raise in a `CalibrationSyncWarning` so
downstream experiments see the flag.  In strict mode, this should be a hard error.

---

### R3. Readout Calibration Incomplete Transaction Boundaries

| | |
|---|---|
| **Likelihood** | Medium — any exception in weight construction triggers this |
| **Severity** | High — measureMacro labels reference non-existent or stale weights |
| **Location** | `experiments/calibration/readout.py:682-716` |

Strict-mode readout calibration has two independent try/except blocks:
1. Definition refresh (`_build_rotated_weights`) — line 684-698
2. Macro label update (`_apply_rotated_measure_macro`) — line 704-715

If step 1 succeeds but step 2 fails, the weight definitions are updated but the
measureMacro still points to old labels.  Conversely, if step 1 fails and step 2
succeeds, labels reference missing definitions.

Additional silent exceptions in readout.py at lines 652-654 (weight construction)
and 1757-1763 (hardware sync) compound the risk.

**Recommendation:** Wrap both steps in a single transaction or roll back step 1
on step-2 failure.  Replace `except Exception: pass` with explicit error propagation.

---

### R4. POM `burn_to_config` Key Collision

| | |
|---|---|
| **Likelihood** | Medium — happens when volatile and permanent stores share names |
| **Severity** | Medium — silently overwrites waveform/pulse definitions |
| **Location** | `pulses/manager.py` — `burn_to_config()` uses `dict.update()` |

When `burn_to_config(cfg, include_volatile=True)` merges persistent and volatile
stores into the QM config dict, it uses `dict.update()`.  If both stores define a
key (e.g., same waveform name), the volatile version silently overwrites the
persistent one with no warning.

Additionally, integration weight length changes for stemless defaults are not
tracked for recompilation — a stale weight array can persist in the QM config
after a pulse length change.

**Recommendation:** Add collision detection in `burn_to_config()` that warns or
raises when a persistent key is about to be overwritten by a volatile entry.

---

### R5. `measureMacro` Module-Level Mutable Singleton

| | |
|---|---|
| **Likelihood** | High — every experiment run touches this state |
| **Severity** | Medium — state corruption, untestable, thread-unsafe |
| **Location** | `programs/macros/measure.py` (1,906 lines) |

`measureMacro` uses class-level mutable dictionaries (`_ro_disc_params`,
`_ro_quality_params`, `_weight_registry`, etc.) shared across all call sites.
There is no locking, no copy-on-read, and no reset mechanism suitable for testing.

Specific sub-issues:
- **Discrimination threshold** is stored in Python state but never compiled into
  the QM config — it's a post-processing artifact that can diverge from the actual
  hardware decision boundary.
- **Weight name binding** is not validated against the compiled config; a typo in
  the weight label silently falls back to a default.
- **KDE serialization** is incomplete — `save_json()` can only serialize the
  covariance/mean parameters, not the fitted KDE object itself.

**Recommendation:** Refactor to instance-based pattern with explicit construction
from CalibrationStore state.  At minimum, add `threading.RLock` guards.

---

### R6. Inconsistent Config Merge Strategies

| | |
|---|---|
| **Likelihood** | Low — only triggers on partial pulse rebuilds |
| **Severity** | Medium — silent waveform loss |
| **Location** | `hardware/config_engine.py:161-174` — `build_qm_config()` |

Pulse overlay is applied via simple dict assignment (`cfg[k] = deepcopy(v)`) while
element ops overlay uses `deep_merge()`.  If a pulse overlay is incomplete (e.g.,
only contains newly added waveforms), previously existing waveforms in the hardware
base are silently dropped.

```python
# Line 166 — simple replacement (LOSSY)
cfg[k] = deepcopy(v)

# Line 170 — deep merge (CORRECT)
cfg = deep_merge(cfg, self.element_ops_overlay)
```

**Recommendation:** Change pulse overlay application to `deep_merge()` for
consistency, or document the replacement-only contract explicitly.

---

### R7. Storage Spectroscopy Writes to Wrong Frequency Path

| | |
|---|---|
| **Likelihood** | Medium — triggered every time StorageSpectroscopy runs with `update_calibration=True` |
| **Severity** | Medium — storage frequency written to `qubit_freq` field of storage element |
| **Location** | `experiments/cavity/storage.py:94` |

`StorageSpectroscopy.analyze()` emits a `SetCalibration` patch targeting
`frequencies.<st_el>.qubit_freq` for what is actually a storage resonator
frequency.  The semantic mismatch means the value ends up in the wrong field
of `ElementFrequencies`.

A dedicated `storage_freq` or `cavity_freq` field on `ElementFrequencies`
would be the correct target, or at minimum the calibration kind should be
`storage_freq` rather than reusing `qubit_freq`.

---

### R8. Referenced Audit Documents Missing from Disk

| | |
|---|---|
| **Likelihood** | Certain |
| **Severity** | Low — documentation gap only |
| **Locations** | `qubox_v2/docs/READOUT_PIPELINE_AUDIT.md`, `qubox_v2/docs/AUDIT_REPORT.md` |

`CHANGELOG.md` entries for v1.7.0 and v1.8.0 reference these files as "(new)"
deliverables, but neither exists on disk.  The audit content is instead inlined
in the CHANGELOG entries themselves.

**Recommendation:** Either create the files with the referenced content or update
the CHANGELOG references to indicate the content is inline.

---

### R9. No Double-Open Guard on Session / Hardware Controller

| | |
|---|---|
| **Likelihood** | Medium — common in notebook re-run scenarios |
| **Severity** | Low-Medium — stale element state, orphaned QM instances |
| **Locations** | `experiments/session.py:481`, `hardware/controller.py:77` |

Neither `SessionManager.open()` nor `HardwareController.open_qm()` checks
whether a QM instance is already open.  Re-running the open cell in a notebook
creates a new QM instance while the old one is closed via `close_other_machines`.
The Python-side element table is refreshed, but any experiment objects holding
stale references to the old session state may not see the update.

`HardwareController.close()` also does not clear `self.elements`, leaving stale
metadata until the next `open_qm()` call.

**Recommendation:** Add an `if self.qm is not None: raise` guard or an explicit
idempotent re-open path that warns the user.

---

### R10. Aggressive Persistence Filter for Raw-Keyed Arrays

| | |
|---|---|
| **Likelihood** | Medium — common output keys like `raw_counts`, `shot_data` |
| **Severity** | Low-Medium — silent data loss for small diagnostic arrays |
| **Location** | `core/persistence_policy.py:24-32, 155-158` |

`should_persist_array()` drops any array whose key matches the raw-key regex
(`/raw|shot|buffer|acq/`) regardless of size.  A 100-element `raw_counts` array
is dropped, while a 10,000-element `metadata_array` is kept.  The 8,192-element
threshold is only applied to non-matching keys.

**Recommendation:** Apply the size threshold first, then the pattern filter second
— or at minimum log when small arrays are dropped by pattern match.

---

### R11. Coherence Unit Heuristic Fragile Threshold

| | |
|---|---|
| **Likelihood** | Low — only triggers on legacy data without `*_us` companion |
| **Severity** | Medium — T1 value can be double-converted to wrong unit |
| **Location** | `calibration/store.py:178` |

When no `T1_us` companion is available, the store uses `T1_val > 1e-3` to guess
whether the value is in seconds or nanoseconds.  This was recently improved from
`> 1.0` (BUG-3 in CHANGELOG v1.8.0), but the heuristic remains fragile.  A T1
of 2 ms (0.002 s) would be correctly classified, but any value accidentally stored
in microseconds (e.g., 15.0 for 15 us) would be interpreted as nanoseconds and
divided by 1e9, yielding ~1.5e-8 s — a 1000x error.

**Recommendation:** Always require the `*_us` companion field; log an error
instead of guessing when it's absent.

---

### R12. `update_calibration=True` Silently Ignored in 5 Experiment Classes

| | |
|---|---|
| **Likelihood** | Medium — users pass the flag expecting behavior |
| **Severity** | Low — no data corruption, but misleading API |
| **Location** | `experiments/cavity/fock.py:82-85,223,395,563`, `experiments/cavity/storage.py` |

`FockResolvedSpectroscopy`, `FockResolvedT1`, `FockResolvedRamsey`,
`FockResolvedPowerRabi`, and `NumSplittingSpectroscopy` accept
`update_calibration=True` but only emit a `logger.warning()` directing users
to the CalibrationOrchestrator.

**Recommendation:** Raise `NotImplementedError` instead of logging a warning —
this makes the contract explicit and prevents silent pass-through.

---

### R13. Dead Code in ReadoutGEIntegratedTrace.plot()

| | |
|---|---|
| **Likelihood** | Certain — code is unreachable |
| **Severity** | Low — no functional impact |
| **Location** | `experiments/calibration/readout.py:1723-1727` |

```python
return fig        # Line 1723 — RETURNS HERE
plt.tight_layout()  # Line 1725 — UNREACHABLE
plt.show()
return fig
```

Copy-paste artifact.  No functional impact but clutters readability.

---

### R14. Experiment `_run_params` Fallback Masks Sequencing Errors

| | |
|---|---|
| **Likelihood** | Low — only if `analyze()` is called without prior `run()` |
| **Severity** | Low-Medium — produces results with wrong default pulse name |
| **Locations** | `experiments/time_domain/rabi.py:83`, `experiments/time_domain/coherence.py:207` |

Several `analyze()` methods fall back to a default pulse name (e.g.,
`"ge_ref_r180"`) when `self._run_params` is not populated.  This means calling
`analyze()` on a result loaded from disk (without a preceding `run()` in the same
session) silently assumes the default pulse was used, rather than raising an error
about missing run context.

---

### R15. Legacy Parameter Shadowing in Readout Experiments

| | |
|---|---|
| **Likelihood** | Low — requires passing both old and new param names |
| **Severity** | Low — confusing behavior, not data-corrupting |
| **Location** | `experiments/calibration/readout.py:425-446` |

`ReadoutGEDiscrimination.analyze()` accepts both `update_measure_macro` (new)
and `update_measureMacro` (legacy via kwargs).  If both are provided, the legacy
kwarg silently overrides the explicit parameter with no warning.

---

### R16. Schema Validation Logs But Does Not Raise

| | |
|---|---|
| **Likelihood** | Low — only if schema files are malformed |
| **Severity** | Low-Medium — session continues with invalid config |
| **Location** | `core/schemas.py` |

Schema validation errors are logged as warnings but the session proceeds with the
potentially invalid configuration.  In strict mode, these should raise.

---

### R17. Hash Length Inconsistency Across Systems

| | |
|---|---|
| **Likelihood** | Certain — by design |
| **Severity** | Low — cosmetic / identity confusion potential |
| **Locations** | `core/session_state.py` (12-char SHA-256), `core/experiment_context.py` (8-char wiring_rev) |

`SessionState.build_hash` uses 12-character SHA-256 truncation while
`ExperimentContext.wiring_rev` uses 8-character truncation.  Different collision
probabilities; not intercomparable without knowing which system generated the hash.

---

## Secondary Observations / Tech Debt

### Chevron Experiments: Stub Implementations
`TimeRabiChevron`, `PowerRabiChevron`, `RamseyChevron` in
`experiments/time_domain/chevron.py` have `analyze()` methods that extract data
but return only `{"shape": mag.shape}` — no fitting, no calibration, no metrics.

### Fidelity Normalization in Readout
`readout.py:2860` uses `if v > 1.0: v = v / 100` to detect percent-vs-fraction.
Legitimate rounding artifacts above 1.0 would trigger false normalization.

### Confusion Matrix Metric Semantics
`gates.py:95-109` reports `"assignment_fidelity_balanced_accuracy_percent"`
regardless of whether a confusion matrix was available for correction.

### `create_clks_array` Implicit Units
`experiment_base.py:71-97` accepts nanoseconds and outputs clock cycles with no
docstring or validation of input units.

### Orchestrator `quality.passed` Always True
`orchestrator.py:60` sets `quality["passed"] = True` unconditionally.  The
`CalibrationResult.passed` property reads this field but it is never set to
`False` by any code path.  Quality gating is entirely theoretical.

### `_set_calibration_path` Generic Fallback
`orchestrator.py:332-340` has a generic dict-update fallback for unrecognized
dotted paths that reloads the entire CalibrationData model.  This bypasses
typed setter methods and can introduce unvalidated fields.

### Fit History Unbounded Growth
`CalibrationStore.store_fit()` appends to an ever-growing list in
`fit_history[experiment]` with no pruning or rotation policy.

### Octave Output Mode Not Persisted
`config_engine.py:70-77` patches octave RF output modes at build-time only;
the override is ephemeral and must be re-applied on every `build_qm_config()`.

---

## Recommended Next Steps

1. **Add `timeout_sec` to `run_program()`** with elapsed-time tracking and
   `job.halt()` on expiry.  This is the single highest-impact change.

2. **Harden post-patch sync path**: either promote the sync exception to a
   user-visible warning/error, or add a `sync_ok` flag to the patch result dict
   so callers can check.

3. **Unify config merge strategy**: switch pulse overlay from dict replacement
   to `deep_merge()` in `build_qm_config()`.

4. **Add double-open guards** to `SessionManager.open()` and
   `HardwareController.open_qm()`.

5. **Replace `except Exception: pass`** patterns across readout.py and
   orchestrator.py with explicit error handling or at minimum structured logging
   that includes the traceback.

6. **Create missing audit documents** (`READOUT_PIPELINE_AUDIT.md`,
   `AUDIT_REPORT.md`) or update the CHANGELOG references.

7. **Introduce quality gating** in the orchestrator — set `quality["passed"]`
   based on fit R-squared, residual thresholds, or experiment-specific criteria
   instead of unconditionally `True`.

8. **Document unit conventions** in a canonical reference: which parameters are ns,
   which are clock cycles, which are seconds.  Add runtime assertions at module
   boundaries.

9. **Add collision detection** in `POM.burn_to_config()` when volatile entries
   shadow persistent ones.

10. **Evaluate `measureMacro` refactoring** from class-level singleton to
    instance-based pattern with explicit construction from CalibrationStore.

---

*Report generated by Claude (read-only audit). No code was modified.*
