# Device / Cooldown / Calibration API Audit

**Date**: 2026-02-22
**Scope**: How the qubox_v2 codebase currently handles device identity,
cooldown scoping, calibration loading/saving, pulse persistence, and
hardware mapping.

---

## 1. What Is the Current Concept of a "Device"?

### 1.1 Implicit Definition

There is **no first-class `Device` model or identifier** in the runtime
code.  The "device" is represented by a **filesystem directory** passed to
`SessionManager.__init__()` as `experiment_path`:

```python
# qubox_v2/experiments/session.py:69-80
class SessionManager:
    def __init__(self, experiment_path: str | Path, ...) -> None:
        self.experiment_path = Path(experiment_path)
```

All configuration files live under `<experiment_path>/config/`.
The directory name (e.g. `seq_1_device`) is the only device identifier; it
is a human convention, not enforced by code.

### 1.2 What Constitutes a Device

In practice, the `seq_1_device/` directory contains:

| File | Role |
|------|------|
| `config/hardware.json` | OPX+/Octave physical wiring, controllers, elements |
| `config/devices.json` | External instruments (LOs, spectrum analyzer, octodac) |
| `config/cqed_params.json` | Physics parameters (frequencies, chi, anharmonicity) |
| `config/calibration.json` | Typed calibration store (v3.0.0) |
| `config/pulses.json` | Compiled pulse definitions |
| `config/measureConfig.json` | Readout macro state |
| `config/session_runtime.json` | Workflow runtime settings (optional) |

There is no `device_id`, `cooldown_id`, `wiring_revision`, or
`config_hash` field inside any of these files.
The directory *is* the device identity.

### 1.3 Code References

- `SessionManager.__init__()` (`session.py:69-80`): accepts `experiment_path`,
  creates directory if absent.
- `_resolve_path()` (`session.py:169-183`): searches `config/<file>` then
  `<experiment_path>/<file>`.
- `CalibrationStore.__init__()` (`store.py:59-62`): receives path directly;
  no device metadata.
- `ConfigEngine.load_hardware()` (`config_engine.py:122-138`): loads
  `hardware.json`; no device identity check.

---

## 2. What Is the Current Concept of a "Cooldown"?

### 2.1 Answer: None

There is **no explicit cooldown concept** anywhere in the codebase.

- No `cooldown_id` field in any config file or Pydantic model.
- `CalibrationData` (`models.py:122-146`) has `created` and
  `last_modified` timestamps but no cooldown or session identifier.
- `CoherenceParams` (`models.py:79-85`) has a `timestamp` field but no
  cooldown tag.
- `FitRecord` (`models.py:107-116`) has `experiment` and `timestamp` but
  no cooldown tag.

### 2.2 Implicit Cooldown Boundary

The only implicit cooldown boundary is:

1. The user physically warms up the dilution refrigerator.
2. The user cools down again.
3. The user replaces (or reuses) the `config/calibration.json` file.

**There is no code-level signal** that a cooldown boundary has occurred.
The `calibration.json` from the previous cooldown is silently reused unless
the user manually resets it.

### 2.3 `SessionState` Build Hash

`SessionState` (`core/session_state.py`) computes a SHA-256 hash over
source-of-truth files at session open:

```python
# Referenced in API_REFERENCE.md section 3.2
SessionState.from_config_dir(config_dir) -> SHA-256 build_hash
```

This hash changes if any config file changes, but it does **not** encode
a cooldown identifier.  Two sequential cooldowns with identical config files
produce the same hash, making it impossible to distinguish them.

---

## 3. Where Are Calibrations Loaded From at Session Start?

### 3.1 Loading Chain

When `SessionManager.__init__()` runs (session.py:69-146):

1. **`hardware.json`** loaded by `ConfigEngine.__init__()` (session.py:86-88
   → config_engine.py:94-119).
2. **`pulses.json`** loaded by `PulseOperationManager.from_json()`
   (session.py:115-119).
3. **`calibration.json`** loaded by `CalibrationStore.__init__()`
   (session.py:122-126 → store.py:59-62 → store.py:71-83).
4. **`devices.json`** loaded by `DeviceManager.__init__()`
   (session.py:129-132).
5. **`cqed_params.json`** loaded by `cQED_attributes.load()`
   (session.py:141 → `_load_attributes()` at session.py:190-196).
6. **`session_runtime.json`** loaded by `_load_runtime_settings()`
   (session.py:142 → session.py:201-239).

When `SessionManager.open()` runs (session.py:331-337):

7. **`measureConfig.json`** loaded by `_load_measure_config()`
   (session.py:335 → session.py:465-477 → `measureMacro.load_json()`).
8. Pulses merged into QM config via `config_engine.merge_pulses()`
   (session.py:333).
9. QM connection opened via `hardware.open_qm()` (session.py:334).
10. Runtime elements validated (session.py:336).

### 3.2 Calibration Store Loading Detail

```python
# store.py:71-83
def _load_or_create(self) -> CalibrationData:
    if self._path.exists():
        with open(self._path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return CalibrationData.model_validate(raw)
    data = CalibrationData(created=datetime.now().isoformat())
    self._path.parent.mkdir(parents=True, exist_ok=True)
    self._atomic_write(data)
    return data
```

- Path: `{experiment_path}/config/calibration.json`
- If the file exists, it is loaded and validated against the Pydantic model.
- If the file does not exist, an empty `CalibrationData` is created and
  written to disk immediately.

---

## 4. Where Are Calibrations Saved To? When?

### 4.1 Primary Save Path

`CalibrationStore.save()` (store.py:288-293):
- Writes to `{experiment_path}/config/calibration.json`
- Uses atomic write (temp file + `os.replace`) via `_atomic_write()`
  (store.py:326-346).
- Filters large arrays via `sanitize_mapping_for_json()`.

### 4.2 When Saves Occur

| Trigger | Code Path | When |
|---------|-----------|------|
| **Session close** | `SessionManager.close()` → `self.calibration.save()` (session.py:501) | Always on session teardown |
| **Auto-save** | `CalibrationStore._touch()` (store.py:348-352) | Every `set_*()` call if `auto_save=True` |
| **Orchestrator apply** | `CalibrationOrchestrator.apply_patch()` → `self.session.calibration.save()` (orchestrator.py:217) | After patch application |
| **Direct experiment** | Various `analyze()` methods call `calibration_store.set_*()` directly | Depends on `update_calibration=True` |
| **Snapshot** | `CalibrationStore.snapshot(tag)` (store.py:295-308) | Manual backup to timestamped file |

### 4.3 Calibration Artifact Saves

Calibration run artifacts (validation records) are saved separately:

```
artifacts/calibration_runs/{tag}_{timestamp}.json
```

Written by `ExperimentBase.guarded_calibration_commit()`
(experiment_base.py:390-488) regardless of whether the calibration update
passes validation.

Orchestrator artifacts are saved to:

```
artifacts/runtime/{name}_{timestamp}.npz + .meta.json
```

Written by `CalibrationOrchestrator.persist_artifact()`
(orchestrator.py:226-252).

---

## 5. How Does the Code Ensure Calibration Values Correspond to Current Hardware?

### 5.1 Answer: It Does Not

There is **no mechanism** that validates calibration values against the
current hardware mapping.  Specifically:

- No check that `calibration.json` element keys match `hardware.json`
  element names.
- No check that frequencies in `calibration.json` are compatible with
  LO/IF ranges in `hardware.json`.
- No check that `cqed_params.json` element names match `hardware.json`.
- No config hash or wiring revision stored in `calibration.json`.

### 5.2 Element Name Validation

The closest mechanism is `validate_runtime_elements()` (session.py:339-393),
which checks that `cqed_params.json` element names exist in the QM config:

```python
# session.py:346-351
qm_elements = set((self.hardware.elements or {}).keys())
requested = {
    "ro_el": getattr(attr, "ro_el", None),
    "qb_el": getattr(attr, "qb_el", None),
    "st_el": getattr(attr, "st_el", None),
}
```

This validates that logical element names (ro_el, qb_el, st_el) from
`cqed_params.json` exist as element keys in the compiled QM config.
It supports auto-mapping (e.g., "readout" → "resonator").

**But**: this does **not** validate that `calibration.json` entries
correspond to the same hardware wiring.

### 5.3 No Wiring Revision Tracking

There is no `wiring_revision` or `hardware_hash` field in any calibration
file.  If `hardware.json` is modified (e.g., LO frequencies changed,
ports reassigned), `calibration.json` continues to load without warning.

---

## 6. Schema Keys and Locations

### 6.1 Qubit Frequency

| Store | Key Path | Code Reference |
|-------|----------|----------------|
| `calibration.json` | `frequencies.<element>.qubit_freq` | `models.py:65` (`ElementFrequencies.qubit_freq`) |
| `cqed_params.json` | `qb_fq` | `cQED_attributes` class |
| Runtime | `hw.set_element_fq(qb_el, fq)` | `experiment_base.py:233` |

### 6.2 Storage Frequency

| Store | Key Path | Code Reference |
|-------|----------|----------------|
| `calibration.json` | `frequencies.<element>.qubit_freq` (reused for storage) | `models.py:65` |
| `cqed_params.json` | `st_fq` | `cQED_attributes` class |

### 6.3 Reference Pulse Amplitude (ref_r180)

| Store | Key Path | Code Reference |
|-------|----------|----------------|
| `calibration.json` | `pulse_calibrations.ref_r180.amplitude` | `models.py:96` (`PulseCalibration.amplitude`) |
| `cqed_params.json` | `r180_amp` | `cQED_attributes` class |
| Patch rule | `PiAmpRule.ref_pulse_name = "ref_r180"` | `patch_rules.py:24` |

### 6.4 DRAG Alpha

| Store | Key Path | Code Reference |
|-------|----------|----------------|
| `calibration.json` | `pulse_calibrations.<pulse>.drag_coeff` | `models.py:99` (`PulseCalibration.drag_coeff`) |
| Patch rule | `DragAlphaRule` propagates to ref_r180, x180, y180, x90, xn90, y90, yn90 | `patch_rules.py:160` |

### 6.5 Readout Weights / Rotation / Threshold

| Store | Key Path | Code Reference |
|-------|----------|----------------|
| `calibration.json` | `discrimination.<element>.threshold` | `models.py:33` |
| `calibration.json` | `discrimination.<element>.angle` | `models.py:34` |
| `measureConfig.json` | `current.ro_disc_params.threshold` | `measure.py` (~line 148) |
| `measureConfig.json` | `current.ro_disc_params.angle` | `measure.py` (~line 149) |
| `measureConfig.json` | `current.pulse_op.int_weights_mapping` | Weight references (cos, rot_cos, opt_cos, etc.) |
| `pulses.json` | `integration_weights.*` | Actual weight sample arrays |

### 6.6 Confusion Matrix / Readout Quality

| Store | Key Path | Code Reference |
|-------|----------|----------------|
| `calibration.json` | `readout_quality.<element>.F` | `models.py:48` (`ReadoutQuality.F`) |
| `calibration.json` | `readout_quality.<element>.Q` | `models.py:49` (`ReadoutQuality.Q`) |
| `calibration.json` | `readout_quality.<element>.V` | `models.py:50` (`ReadoutQuality.V`) |
| `calibration.json` | `discrimination.<element>.confusion_matrix` | `models.py:40` |
| `measureConfig.json` | `current.confusion_matrix` | `measure.py` (~line 170) |
| `measureConfig.json` | `current.transition_matrix` | `measure.py` (~line 172) |

---

## 7. How Pulses Are Persisted and Merged into Runtime QM Config

### 7.1 Pulse Persistence

Pulses are stored in `config/pulses.json` via `PulseOperationManager`:

```python
# session.py:288-294
def save_pulses(self, path=None) -> Path:
    dst = Path(path) if path else (self.experiment_path / "config" / "pulses.json")
    self.pulse_mgr.save_json(str(dst))
```

The POM has a **dual-store architecture** (permanent + volatile):
- **Permanent store**: persisted to `pulses.json`; contains waveforms,
  pulses, integration weights, and element-operation mappings.
- **Volatile store**: session-transient pulses cleared by
  `clear_temporary()`; never written to disk.

### 7.2 Merge into QM Config

The merge happens in `ConfigEngine.merge_pulses()` (config_engine.py:198-221):

```python
def merge_pulses(self, pom, *, include_volatile=True) -> None:
    cfg = deepcopy(self.hardware_base)
    pom.burn_to_config(cfg, include_volatile=include_volatile)
    self.pulse_overlay = {k: deepcopy(cfg.get(k, {})) for k in PULSE_KEYS}
    # Also captures element operations as deep-merge patch
```

Then `build_qm_config()` (config_engine.py:149-174) layers everything:

```
hardware_base → pulse_overlay → element_ops_overlay → runtime_overrides
```

### 7.3 Pulse Source-of-Truth

Currently, `pulses.json` is the operational pulse store.  The declarative
`pulse_specs.json` system exists (`PulseFactory`) but the transition is
in progress:

> `pulses.json` = deprecated format (POM persistence)
> `pulse_specs.json` = declarative source of truth (not yet primary)

Both paths coexist; `PulseFactory.register_all(pom)` can feed compiled
specs into the POM.

---

## 8. What Is Runtime-Only vs Persisted

| Data | Lifetime | Where |
|------|----------|-------|
| QM config dict | **Runtime only** | Rebuilt every `burn_pulses()` / `build_qm_config()` |
| Waveform sample arrays | **Runtime only** | Compiled from specs or loaded from POM; in memory |
| Volatile pulse store | **Runtime only** | `POM._vol` ResourceStore; cleared on save or `clear_temporary()` |
| Runtime overrides | **Runtime only** | `ConfigEngine.runtime_overrides`; never persisted |
| `measureMacro` state stack | **Runtime only** | `_state_stack` dict; lost on process exit |
| Live QM element frequencies | **Runtime only** | Set via `hw.set_element_fq()`; not auto-persisted |
| `hardware.json` | **Persisted** | Source-of-truth; manual edits only |
| `calibration.json` | **Persisted** | Written by `CalibrationStore.save()` |
| `pulses.json` | **Persisted** | Written by `POM.save_json()` |
| `measureConfig.json` | **Persisted** | Written by `measureMacro.save_json()` |
| `cqed_params.json` | **Persisted** | Written by `save_attributes()` |
| `session_runtime.json` | **Persisted** | Written by `save_runtime_settings()` |
| Calibration run artifacts | **Persisted** | `artifacts/calibration_runs/*.json` |
| Run output data | **Persisted** | `data/*.npz` + `*.meta.json` |

---

## 9. Summary of Key Findings

1. **No device identity model**: The device is a directory path, not
   a typed entity.  No `device_id` exists.

2. **No cooldown concept**: No code distinguishes between cooldowns.
   Calibrations from a previous cooldown are silently reused.

3. **No hardware-calibration coupling**: Changing `hardware.json` does
   not invalidate `calibration.json`.

4. **Multiple parallel truth sources**: `cqed_params.json` and
   `calibration.json` both store frequency data, with no enforced
   precedence hierarchy at read time.

5. **measureConfig.json drift risk**: Discrimination params exist in both
   `calibration.json` and `measureConfig.json` with no sync guarantee.

6. **Pulses dual-path**: Both `pulses.json` (legacy) and
   `pulse_specs.json` (declarative) coexist; the transition is incomplete.

---

## 10. Implementation Status (Phase 1+2)

**Date**: 2026-02-22

The following changes have been implemented to address findings 1-3 above:

| Component | File | Status |
|-----------|------|--------|
| `ExperimentContext` frozen dataclass | `core/experiment_context.py` | NEW |
| `ContextMismatchError` exception | `core/errors.py` | Added |
| `CalibrationContext` Pydantic model | `calibration/models.py` | Added |
| `context` field on `CalibrationData` | `calibration/models.py` | Added |
| v3->v4 calibration schema migration | `core/schemas.py` | Added |
| Context validation in `CalibrationStore` | `calibration/store.py` | Added |
| `DeviceRegistry` + `DeviceInfo` | `devices/device_registry.py` | NEW |
| `ContextResolver` | `devices/context_resolver.py` | NEW |
| `wiring_rev` property on `ConfigEngine` | `hardware/config_engine.py` | Added |
| Context fields on `SessionState` | `core/session_state.py` | Added |
| Context-mode constructor on `SessionManager` | `experiments/session.py` | Added |
| Context stamping in orchestrator artifacts | `calibration/orchestrator.py` | Added |
| Package `__init__` exports | `core/`, `calibration/`, `devices/` | Updated |
| Context-mode demo notebook | `notebooks/post_cavity_experiment_context.ipynb` | NEW |

**Backward compatibility**: `SessionManager("./seq_1_device")` continues to
work.  Legacy v3 calibration files auto-migrate in-memory to v4 (context=None).
Context validation is skipped when no context block is present.
