# Readout Pipeline Consistency Audit

**Date**: 2026-02-25
**Scope**: GE Discrimination → Butterfly → CalibrateReadoutFull pipeline
**Focus**: Legacy ↔ qubox_v2 mapping, state handoff, policy consistency

---

## 1. Pipeline Ordering

### Legacy (`cQED_Experiment`)

```
readout_weights_optimization()
  → mm.set_outputs(...)                              # immediate macro mutation
  → burn_pulses()                                    # push to QM config

readout_ge_discrimination()
  → mm._update_readout_discrimination(out)           # direct mutation
  → mm.set_pulse_op(...)                             # set weights
  → mm.set_drive_frequency(...)                      # set drive freq
  → auto_update_postsel=True → PostSelectionConfig   # auto blob config

burn_pulses()                                        # explicit between GE and Butterfly

readout_butterfly_measurement()
  → mm._update_readout_quality(out)                  # direct mutation
  → uses stored config from GE step
```

### qubox_v2

```
ReadoutWeightsOptimization.run()
  → registers weights in POM
  → optional: set_measure_macro=True → mm.set_pulse_op()

ReadoutGEDiscrimination.run()
  → _build_rotated_weights()                         # rot_cos/rot_sin/rot_m_sin
  → _apply_rotated_measure_macro()                   # mm.set_pulse_op(weights=...)
  → _apply_discrimination_measure_macro()            # mm._update_readout_discrimination(payload)
  →   + mm._ro_disc_params["qbx_readout_state"] = hash
  → optional: burn_rot_weights=True → burn_pulses()

ReadoutButterflyMeasurement.run()
  → checks mm._ro_disc_params["qbx_readout_state"]  # hash comparison
  → fallback chain: explicit → stored → blob → threshold
  → no macro mutation in run() itself

ReadoutButterflyMeasurement.analyze()
  → proposed_patch_ops with SetMeasureQuality        # via orchestrator
```

### CalibrateReadoutFull pipeline

```
Step 1: ReadoutWeightsOptimization (once)
Step 2: ReadoutGEDiscrimination (iterative, ge_update_measure_macro=True)
  → analyze() called BEFORE butterfly
Step 3: ReadoutButterflyMeasurement (iterative)
  → convergence check on fidelity tolerance
```

---

## 2. Policy Objects

### Readout Policy

| Field | Storage Key | GE Writes | Butterfly Reads | CalibStore Field |
|-------|-------------|-----------|-----------------|-----------------|
| threshold | `_ro_disc_params["threshold"]` | Yes (via `_update_readout_discrimination`) | Yes (fallback chain) | `DiscriminationParams.threshold` |
| angle | `_ro_disc_params["angle"]` | Yes | Yes (via hash signature) | `DiscriminationParams.angle` |
| fidelity | `_ro_disc_params["fidelity"]` | Yes | Yes (consistency check) | `DiscriminationParams.fidelity` |
| rot_mu_g/e | `_ro_disc_params["rot_mu_g/e"]` | Yes | Yes (blob fallback) | `DiscriminationParams.mu_g/e` |
| sigma_g/e | `_ro_disc_params["sigma_g/e"]` | Yes | Yes (blob fallback) | `DiscriminationParams.sigma_g/e` |
| rot_cos/sin weights | POM weight store | Yes (`_build_rotated_weights`) | Yes (via `_pick_weight_triplet`) | — |
| qbx_readout_state | `_ro_disc_params["qbx_readout_state"]` | Yes (hash dict) | Yes (hash comparison) | — (not in CalibStore) |
| PostSelectionConfig | `measureMacro._post_select_config` | Yes (auto from blob) | Yes (fallback chain) | — |

### Quality Policy (Butterfly → Downstream)

| Field | Storage Key | Butterfly Writes | CalibStore Field |
|-------|-------------|-----------------|-----------------|
| F, Q, V | `_ro_quality_params["F/Q/V"]` | Via `SetMeasureQuality` patch | `ReadoutQuality.F/Q/V` |
| t01, t10 | `_ro_quality_params["t01/t10"]` | **DEAD CODE** — not written | `ReadoutQuality.t01/t10` |
| eta_g, eta_e | `_ro_quality_params["eta_g/e"]` | **DEAD CODE** — not written | — |
| confusion_matrix | `_ro_quality_params["confusion_matrix"]` | Via patch | `ReadoutQuality.confusion_matrix` |

### State-Prep Policy

| Aspect | Legacy | qubox_v2 |
|--------|--------|----------|
| GE state prep | `x180` (r180 param) | `x180` (r180 param) |
| Butterfly prep | conditional reset + π | conditional reset + post-sel |
| Post-selection default | `blob_k_g=3.0` | `blob_k_g=2.0` (**mismatch**) |
| DRAG primitives | ref pulse from cqed_params | ref_r180 from CalibrationStore |

---

## 3. State Handoff: GE → Butterfly

### Where GE Updates/Saves/Applies

1. **`_build_rotated_weights()`** (readout.py:747–816) — creates rot_cos, rot_sin, rot_m_sin from discrimination angle
2. **`_apply_rotated_measure_macro()`** (readout.py:817–852) — sets measurement pulse_op with rotated weights
3. **`_apply_discrimination_measure_macro()`** (readout.py:866–924) — pushes threshold/angle/fidelity/centroids to mm, stamps `qbx_readout_state` hash
4. **`_persist_measure_macro_state()`** (readout.py:926–) — optional PersistMeasureConfig via orchestrator
5. **CalibrationStore** — via `guarded_calibration_commit()` or orchestrator patch

### Where Butterfly Retrieves/Uses

1. **Threshold sync** (readout.py:1624–1630) — if threshold is None, calls `sync_from_calibration()`
2. **Hash comparison** (readout.py:1647–1663) — reads `mm._ro_disc_params["qbx_readout_state"]`, compares with `_current_readout_state_signature()`
3. **Post-selection fallback** (readout.py:1665–1722):
   - Explicit `prep_policy` param → use directly
   - `use_stored_config` + hash match → `mm.get_post_select_config()`
   - Blob params from GE → `BLOBS` policy with `k_blob=2.0`
   - Threshold fallback → `THRESHOLD` policy
4. **Confusion matrix** — from CalibrationStore via `get_confusion_matrix()`

### Handoff Invariants

| Invariant | Status |
|-----------|--------|
| GE threshold persisted before Butterfly reads | ✓ (via mm._update_readout_discrimination) |
| GE rotated weights available in POM | ✓ (via _build_rotated_weights + burn_pulses) |
| GE state hash available for Butterfly check | ⚠ **Lost after sync_from_calibration** |
| PostSelectionConfig persisted and retrievable | ✓ (via mm._post_select_config) |
| Butterfly uses same threshold GE produced | ✓ (reads from mm._ro_disc_params) |
| Butterfly uses same weights GE produced | ✓ (reads from POM via _pick_weight_triplet) |

---

## 4. Identified Bugs and Mismatches

### BUG-R1: `qbx_readout_state` not in default dict (measure.py:148)

**Category**: Schema/key mismatch
**Severity**: Medium

The `_ro_disc_params` default dict does not include `qbx_readout_state`.
GE Discrimination writes it at readout.py:914. After `sync_from_calibration()`
runs (which overwrites from CalibrationStore — which doesn't store this field),
the hash is lost. On next Butterfly run, `ge_state` will be `None`, triggering
`"no_ge_state_signature"` and skipping the hash check entirely.

**Impact**: Butterfly cannot detect stale readout config after any calibration
commit that triggers sync.

### BUG-R2: `_update_readout_quality` dead code (measure.py:441–476)

**Category**: Metric definition mismatch
**Severity**: Low–Medium

Lines 441–476 are inside a triple-quoted string literal (dead code). The fields
`eta_g`, `eta_e`, `t01`, `t10`, and several other butterfly metrics are never
written to `_ro_quality_params` even though the default dict has slots for them
and the butterfly analyzer produces them.

**Impact**: `t01`/`t10` are written to CalibrationStore (via `set_readout_quality`)
but never propagated to measureMacro's runtime dict by `_update_readout_quality`.
The `sync_from_calibration` does read `t01`/`t10` from CalibStore (line 515),
so the values eventually reach runtime — but only after a sync cycle, not
immediately after a `SetMeasureQuality` patch op.

### BUG-R3: `sync_from_calibration` doesn't preserve `qbx_readout_state` (measure.py:479–523)

**Category**: Policy saved but not restored
**Severity**: Medium

`sync_from_calibration()` populates threshold, angle, fidelity, mu_g/e, sigma_g/e
from CalibrationStore but does NOT restore the `qbx_readout_state` hash.
Since `qbx_readout_state` is not stored in CalibrationStore (it's a runtime-only
hash), it's permanently lost after sync.

**Impact**: Same as BUG-R1 — Butterfly's hash comparison fails after any
orchestrator patch commit.

### BUG-R4: Orchestrator swallows sync errors silently (orchestrator.py:240–241)

**Category**: Policy not applied
**Severity**: Low

The `except Exception: pass` after `sync_from_calibration()` means any error
(e.g., missing element, invalid data) is silently discarded. The sync silently
fails and measureMacro may hold stale values.

### MISMATCH-R1: Legacy `blob_k_g=3.0` vs new `blob_k_g=2.0`

**Category**: State-prep mismatch
**Severity**: Low

Legacy `calibrate_readout_full()` uses `blob_k_g=3.0` (line ~2955 of
legacy_experiment.py). New `ReadoutButterflyMeasurement.run()` defaults to
`k_blob=2.0` (readout.py:1707). `ReadoutConfig.blob_k_g` also defaults to `2.0`.

**Impact**: Post-selection circles are tighter in qubox_v2. This may reject
more shots, affecting Butterfly statistics. This is likely intentional but
should be documented.

### MISMATCH-R2: Legacy has explicit `burn_pulses()` between GE and Butterfly

**Category**: Policy handoff gap
**Severity**: Low (already handled)

Legacy `calibrate_readout_full()` calls `burn_pulses()` explicitly between
GE discrimination and Butterfly. In qubox_v2's `CalibrateReadoutFull`, this
is handled by `burn_rot_weights=True` in GE's `run()` call (readout.py:2423).

**Impact**: None — functionally equivalent. Noted for reference.

---

## 5. Fix Summary

| ID | Fix | File | Lines |
|----|-----|------|-------|
| BUG-R1 | Add `"qbx_readout_state": None` to `_ro_disc_params` default dict | measure.py | 148–159 |
| BUG-R2 | Uncomment `t01`/`t10` update code in `_update_readout_quality` | measure.py | 441–476 |
| BUG-R3 | Preserve `qbx_readout_state` across `sync_from_calibration` | measure.py | 479–523 |
| BUG-R4 | Log sync errors instead of silently swallowing | orchestrator.py | 240–241 |
| GUARD-1 | Add qbx_readout_state preservation warning in sync | measure.py | 479 |
