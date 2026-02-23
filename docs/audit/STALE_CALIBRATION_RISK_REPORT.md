# Stale Calibration Risk Report

**Date**: 2026-02-22
**Scope**: All ways the current system could reuse stale calibrations
across cooldowns or devices.

---

## Risk Summary

| # | Risk | Severity | Likelihood | Existing Signal |
|---|------|----------|------------|-----------------|
| R1 | Implicit reuse of `calibration.json` with no cooldown scoping | **Critical** | **Certain** (default behavior) | None |
| R2 | Hardware mapping changes not invalidating calibrations | **High** | Likely (common during setup) | None |
| R3 | `measureConfig.json` drift from `calibration.json` | **Medium** | Likely (happens routinely) | None |
| R4 | Silent overwrites during session close | **Medium** | Likely | None |
| R5 | `cqed_params.json` / `calibration.json` frequency divergence | **Medium** | Likely | None |
| R6 | No config-hash or wiring-revision compatibility check | **High** | Certain (no check exists) | None |
| R7 | Cross-device calibration file copy | **Critical** | Possible (user error) | None |
| R8 | Build-hash collision across cooldowns | **Low** | Possible | None |
| R9 | Partial write on crash during close | **Medium** | Unlikely (but possible) | None |
| R10 | Fit history accumulation without cooldown boundary | **Low** | Certain | None |

---

## R1: Implicit Reuse of `calibration.json` With No Cooldown Scoping

### Code Path

```
SessionManager.__init__() (session.py:122-126)
  → CalibrationStore.__init__(cal_path) (store.py:59-62)
    → _load_or_create() (store.py:71-83)
      → json.load(self._path) — loads whatever is on disk
      → CalibrationData.model_validate(raw) — no freshness check
```

### Failure Mode

When a user starts a new cooldown session, `calibration.json` from the
previous cooldown is loaded verbatim.  Calibration values (T1, T2,
discrimination threshold, pulse amplitudes) are almost certainly stale
because:

- T1/T2 drift between cooldowns (thermal cycling, TLS reconfiguration).
- Readout angle/threshold shift due to resonator frequency drift.
- Qubit frequency shifts due to oxide aging or magnetic flux changes.

The system provides **zero warning** that calibrations may be stale.

### Likelihood

**Certain**.  This is the default behavior.  Every session start after a
cooldown reuses the previous calibration file.

### Existing Logs/Signals

None.  `CalibrationStore._load_or_create()` logs "Loading calibration
from ..." (store.py:73) but does not check `last_modified` age or
compare against any cooldown boundary.

### Impact

- Experiments run with wrong readout discrimination, producing incorrect
  state populations (e.g., T1 measurement biased by stale threshold).
- Gate calibrations (pi-pulse amplitude) applied to a different qubit
  frequency, causing systematic rotation errors.
- User may not notice until well into the session, wasting hours of
  fridge time.

---

## R2: Hardware Mapping Changes Not Invalidating Calibrations

### Code Path

```
ConfigEngine.load_hardware() (config_engine.py:122-138)
  — loads hardware.json (controllers, octaves, elements, port mappings)
  — no comparison against calibration.json element keys

CalibrationStore._load_or_create() (store.py:71-83)
  — loads calibration.json independently
  — no check that element names or wiring match hardware.json
```

### Failure Mode

If `hardware.json` is modified (elements renamed, LO frequencies changed,
ports reassigned, new elements added), `calibration.json` continues to
load without validation.  Possible scenarios:

1. **Element rename**: `hardware.json` changes "resonator" to "readout";
   `calibration.json` still has `discrimination.resonator.*` — lookups
   return `None` silently.

2. **LO frequency change**: `hardware.json` changes resonator LO from
   8.8 GHz to 8.5 GHz; `calibration.json` still has
   `frequencies.resonator.lo_freq = 8.8e9` — IF frequency computation
   produces wrong drive frequency.

3. **Port reassignment**: Qubit DAC channel moved; calibrated pulse
   amplitudes now drive the wrong element.

### Likelihood

**Likely** during initial device setup and hardware debugging.  Less
likely during steady-state operation.

### Existing Logs/Signals

`validate_runtime_elements()` (session.py:339-393) checks that
`cqed_params.json` element names exist in the QM config, but does **not**
validate `calibration.json` keys.  It also does not check frequency
compatibility.

---

## R3: `measureConfig.json` Drift From `calibration.json`

### Code Path

**Write to `calibration.json`:**
```
CalibrationOrchestrator.apply_patch() (orchestrator.py:159-162)
  → _set_calibration_path("discrimination.resonator.threshold", value)
  → session.calibration.set_discrimination(...)
  → session.calibration.save()
```

**Write to `measureConfig.json`:**
```
CalibrationOrchestrator.apply_patch() (orchestrator.py:206-210)
  → "PersistMeasureConfig" op
  → measureMacro.save_json(path)
```

These are **separate operations**.  If only one is triggered (e.g.,
the orchestrator patch includes `SetCalibration` but not
`PersistMeasureConfig`), the two files diverge.

### Failure Mode

`measureConfig.json` is loaded at session start by
`measureMacro.load_json()` (session.py:465-477).  If its discrimination
params differ from `calibration.json`, experiments using `measureMacro`
(which is the standard readout path) will use the `measureConfig.json`
values, while experiments reading `calibration_store.get_discrimination()`
will get the `calibration.json` values.

**Current state proves this happens**: `calibration.json` has
`threshold = -2.07e-05`, while `measureConfig.json` has
`threshold = -2.42e-05`.

### Likelihood

**Likely**.  Multiple independent write paths exist.  Direct experiment
`analyze()` methods (documented in LEAKS.md) write to `calibration.json`
and/or `measureMacro` independently.

### Existing Logs/Signals

None.  No comparison between the two stores is ever performed.

---

## R4: Silent Overwrites During Session Close

### Code Path

```
SessionManager.close() (session.py:482-502):
  1. hardware.close()
  2. devices disconnect
  3. save_pulses()       → pulses.json
  4. save_runtime_settings() → session_runtime.json
  5. calibration.save()  → calibration.json
```

### Failure Mode

`close()` unconditionally writes `pulses.json` and `calibration.json`.
If the user previously ran a calibration that produced incorrect results
(e.g., a bad T1 fit with `update_calibration=True`), and the experiment's
`analyze()` method directly mutated the calibration store (which several
do, per LEAKS.md), the bad values are silently persisted on close.

There is no "dirty flag" check or "confirm before save" prompt.

### Likelihood

**Likely**.  The `close()` method is called automatically by the context
manager `__exit__()` (session.py:507-509), including on exceptions.

### Existing Logs/Signals

`_logger.info("Calibration saved to %s", self._path)` (store.py:293)
is logged but does not indicate whether the data changed since load.

---

## R5: `cqed_params.json` / `calibration.json` Frequency Divergence

### Code Path

**Calibration frequency update:**
```
CalibrationOrchestrator._set_calibration_path()
  → "frequencies.qubit.qubit_freq" = new_value
  → CalibrationStore.set_frequencies(...)
```

**cqed_params frequency:**
```
SessionManager._load_attributes() → cQED_attributes.load()
  → reads qb_fq from cqed_params.json
```

**Usage in experiments:**
```
ExperimentBase.set_standard_frequencies() (experiment_base.py:226-233):
  self.hw.set_element_fq(self.attr.qb_el, qb_fq or self.attr.qb_fq)
  # ^^^ uses cqed_params.qb_fq, NOT calibration.json qubit_freq
```

### Failure Mode

When a frequency calibration (e.g., `QubitSpectroscopy`) updates
`calibration.json:frequencies.qubit.qubit_freq`, the value in
`cqed_params.json:qb_fq` is **not automatically updated**.
`set_standard_frequencies()` reads from `self.attr.qb_fq`
(cqed_params), so subsequent experiments may use the old frequency
unless the attribute is manually updated.

Some experiments do update `cqed_params` (e.g., by calling
`self.attr.qb_fq = new_freq` + `save_attributes()`), but this is
experiment-specific logic, not a system guarantee.

### Likelihood

**Likely**.  The orchestrator patch system writes to `calibration.json`
via `FrequencyRule` (patch_rules.py:124-143) but does not synchronize
`cqed_params.json`.

### Existing Logs/Signals

None.

---

## R6: No Config-Hash or Wiring-Revision Compatibility Check

### Code Path

`CalibrationData` model (models.py:122-146) has no fields for:
- `device_id`
- `cooldown_id`
- `hardware_hash`
- `wiring_revision`
- `config_hash`

`CalibrationStore.__init__()` (store.py:59-62) receives only a file path.
No compatibility metadata is checked.

### Failure Mode

A `calibration.json` file can be freely moved between device directories,
or a device directory can have its `hardware.json` replaced while keeping
the same `calibration.json`.  The system will load without error.

### Likelihood

**Certain** — no check exists.

### Existing Logs/Signals

None.

---

## R7: Cross-Device Calibration File Copy

### Code Path

Since device identity is just a directory path, there is nothing stopping
a user from:

```bash
cp seq_1_device/config/calibration.json seq_2_device/config/calibration.json
```

The copied file will load without any validation that the element names,
frequencies, or wiring match the target device.

### Failure Mode

Calibration values from device A (e.g., qubit at 6.15 GHz, r180_amp=0.08)
are applied to device B (e.g., qubit at 5.8 GHz, r180_amp=0.12).
All experiments run with fundamentally wrong parameters.

### Likelihood

**Possible**.  This is a user error, but the system provides no guardrails.

### Existing Logs/Signals

None.

---

## R8: Build-Hash Collision Across Cooldowns

### Code Path

`SessionState.from_config_dir()` computes SHA-256 over source-of-truth
files.  If two sequential cooldowns use identical config files (common
when the user simply restarts without modifying configs), the build hash
is identical.

### Failure Mode

Artifacts from different cooldowns are stored under the same build-hash
directory.  Session state snapshots and generated configs are overwritten.
This is not immediately harmful (the configs are indeed identical), but
it makes post-hoc forensics impossible: you cannot tell which cooldown
produced which artifact.

### Likelihood

**Possible**.  Common for successive cooldowns where the user does not
modify config files.

### Existing Logs/Signals

None.  The build hash is logged but contains no cooldown metadata.

---

## R9: Partial Write on Crash During Close

### Code Path

```
SessionManager.close() (session.py:482-502):
  3. save_pulses()       → pulses.json     ← may succeed
  4. save_runtime_settings() → ...          ← may succeed
  5. calibration.save()  → calibration.json ← may fail if process killed
```

Individual saves are atomic (temp file + `os.replace`), but the sequence
is not transactional.

### Failure Mode

If the process is killed between step 3 and step 5, `pulses.json` has
been updated but `calibration.json` has not.  The next session loads
mismatched pulse definitions and calibration values.

### Likelihood

**Unlikely** in normal operation.  Possible during:
- Jupyter kernel restarts
- OOM kills
- Network disconnections during QM teardown
- Power outages

### Existing Logs/Signals

Each save is wrapped in try/except (session.py:493-500) with warning
logs, but there is no cross-file consistency verification on next load.

---

## R10: Fit History Accumulation Without Cooldown Boundary

### Code Path

```
CalibrationStore.store_fit(record) (store.py:182-187):
  self._data.fit_history.setdefault(record.experiment, []).append(record)
```

### Failure Mode

Fit records from different cooldowns accumulate in the same list.
`get_latest_fit()` returns the most recent record, which may be from the
current cooldown — but `get_fit_history()` returns all records across all
cooldowns, with no way to filter by cooldown.

This is a minor issue: the fit history is primarily for debugging, not
for driving experiment logic.

### Likelihood

**Certain**.  Every fit is appended; no pruning or cooldown-scoping
exists.

### Existing Logs/Signals

Records have `timestamp` fields but no `cooldown_id`.

---

## Recommendations Summary

| Risk | Recommended Mitigation |
|------|----------------------|
| R1 | Add `cooldown_id` to `CalibrationData`; warn on load if ID does not match session |
| R2 | Store hardware config hash in `calibration.json`; validate on load |
| R3 | Unify discrimination params into single source (calibration store); derive measureConfig |
| R4 | Add dirty-flag tracking; optionally confirm before save on close |
| R5 | Deprecate `cqed_params.json` frequency fields; use `calibration.json` as sole source |
| R6 | Add `device_id` + `wiring_revision` + `config_hash` to calibration schema |
| R7 | Validate device_id on CalibrationStore load; refuse mismatched files |
| R8 | Include cooldown_id in build-hash salt |
| R9 | Write atomic "save manifest" with checksums; verify on next load |
| R10 | Add cooldown_id to FitRecord; support filtered queries |
