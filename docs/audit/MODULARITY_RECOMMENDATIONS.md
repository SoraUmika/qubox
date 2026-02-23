# Modularity Recommendations

**Date**: 2026-02-22
**Status**: Proposal (no code changes)
**Goal**: Make the system modular across different physical samples/devices
(e.g., switching cQED transmon samples where calibrations are not
transferable), while staying consistent with how the code currently works.

---

## 1. Defining "Experiment Context"

### 1.1 What It Should Mean

An **experiment context** is a unique combination of:

| Field | Type | Meaning | Example |
|-------|------|---------|---------|
| `device_id` | `str` | Unique identifier for a physical sample + wiring configuration | `"seq_1"`, `"transmon_B_v2"` |
| `cooldown_id` | `str` | Identifier for a specific cool-down cycle of the device | `"cd_2026_02_22"`, `"cd_003"` |
| `wiring_rev` | `str` | Hash or tag of the hardware wiring configuration | `"a3f8b2"` (SHA-256 prefix of hardware.json) |
| `config_hash` | `str` | Hash of the combined source-of-truth files at session start | `"f805bd32b3dc"` (from SessionState) |

### 1.2 Why All Four Fields

- **`device_id`**: A physical sample has specific qubit/cavity/coupling
  parameters.  Calibrations from device A are meaningless on device B.
- **`cooldown_id`**: Same device, different cooldown, means different T1/T2,
  different readout discrimination, different qubit frequency drift.
  Calibrations should not bleed across cooldowns.
- **`wiring_rev`**: Changing the LO frequency, swapping a cable, or
  reassigning ports invalidates calibrations even within a cooldown.
- **`config_hash`**: Captures the full snapshot for reproducibility and
  artifact linking.

### 1.3 Where These Fields Would Live

Add a `context` block to `CalibrationData` (models.py):

```python
class CalibrationContext(BaseModel):
    device_id: str
    cooldown_id: str
    wiring_rev: str
    config_hash: str | None = None
    created: str | None = None
```

Add a `context` block to the top level of `calibration.json`:

```json
{
  "version": "4.0.0",
  "context": {
    "device_id": "seq_1",
    "cooldown_id": "cd_2026_02_22",
    "wiring_rev": "a3f8b2",
    "config_hash": "f805bd32b3dc"
  },
  ...
}
```

---

## 2. Modular Layering Strategy

### 2.1 Layer Diagram

```
┌─────────────────────────────────────────────────────┐
│        Session Runtime Layer                         │
│  Active bindings, temporary overrides, live QM state │
│  (ConfigEngine.runtime_overrides, measureMacro stack)│
│  Lifetime: single session / notebook kernel          │
├─────────────────────────────────────────────────────┤
│        Calibration Set Layer                         │
│  Numbers that drift per cooldown                     │
│  (calibration.json, measureConfig.json)             │
│  Lifetime: one cooldown of one device               │
├─────────────────────────────────────────────────────┤
│        Device Model Layer                            │
│  Logical elements, expected operations, physics      │
│  (cqed_params.json, pulse_specs.json, pulses.json)  │
│  Lifetime: one device (across cooldowns)             │
├─────────────────────────────────────────────────────┤
│        Hardware Mapping Layer                        │
│  Physical ports, wiring, LO sources                  │
│  (hardware.json, devices.json, octave_links)        │
│  Lifetime: physical setup (may span devices)         │
└─────────────────────────────────────────────────────┘
```

### 2.2 Layer Ownership

| Layer | Owns | Changes When | Invalidates |
|-------|------|--------------|-------------|
| Hardware Mapping | Port assignments, LO sources, controller topology | Cable swap, add/remove instrument | All calibration sets using this wiring |
| Device Model | Element names, anharmonicity, chi, expected ops | Sample replacement, new device | All calibration sets for this device |
| Calibration Set | T1, T2, threshold, angle, pulse amplitudes, DRAG | New cooldown, frequency drift, aging | Active session runtime (must reload) |
| Session Runtime | Live QM config, volatile pulses, measureMacro stack | Every session open/close | Nothing persistent |

### 2.3 Key Principle

**Lower layers are stable; upper layers drift.**  A hardware mapping
change should cascade upward, invalidating calibration sets.  A calibration
set change should not affect the device model or hardware mapping.

---

## 3. Proposed Directory Layout

### 3.1 Per-Device, Per-Cooldown Structure

```
experiments/
├── devices/
│   ├── seq_1/                              # device_id = "seq_1"
│   │   ├── device.json                     # device metadata (device_id, description, sample info)
│   │   ├── config/
│   │   │   ├── hardware.json               # hardware mapping (shared across cooldowns)
│   │   │   ├── devices.json                # external instruments
│   │   │   ├── cqed_params.json            # device-level physics (anharmonicity, chi)
│   │   │   └── pulse_specs.json            # declarative pulse recipes (device-level)
│   │   │
│   │   ├── cooldowns/
│   │   │   ├── cd_2026_02_22/              # cooldown_id = "cd_2026_02_22"
│   │   │   │   ├── config/
│   │   │   │   │   ├── calibration.json    # calibration set (cooldown-scoped)
│   │   │   │   │   ├── pulses.json         # compiled pulses (cooldown-scoped)
│   │   │   │   │   ├── measureConfig.json  # readout macro state (cooldown-scoped)
│   │   │   │   │   └── session_runtime.json
│   │   │   │   ├── data/                   # run outputs
│   │   │   │   └── artifacts/              # generated artifacts
│   │   │   │
│   │   │   └── cd_2026_02_15/              # previous cooldown
│   │   │       ├── config/
│   │   │       │   └── calibration.json    # preserved calibrations
│   │   │       ├── data/
│   │   │       └── artifacts/
│   │   │
│   │   └── calibration_db.json             # mixer calibration (device-level, survives warmup)
│   │
│   └── transmon_B/                         # another device
│       ├── device.json
│       ├── config/
│       │   └── hardware.json
│       └── cooldowns/
│           └── ...
│
└── active_context.json                     # pointer to current device + cooldown
```

### 3.2 `device.json` Schema

```json
{
  "device_id": "seq_1",
  "description": "Transmon + storage cavity, sample batch 2025-Q4",
  "sample_info": {
    "qubit_type": "transmon",
    "cavity_type": "3D_aluminum",
    "fabrication_date": "2025-10-15"
  },
  "element_map": {
    "qubit": "qubit",
    "readout": "resonator",
    "storage": "storage"
  },
  "created": "2025-11-01T10:00:00"
}
```

### 3.3 `active_context.json` Schema

```json
{
  "device_id": "seq_1",
  "cooldown_id": "cd_2026_02_22",
  "resolved_path": "devices/seq_1/cooldowns/cd_2026_02_22",
  "wiring_rev": "a3f8b2",
  "activated_at": "2026-02-22T13:30:00"
}
```

---

## 4. Compatibility Check / Calibration Validity Mechanism

### 4.1 What Should Be Compared

When `CalibrationStore` loads a `calibration.json`:

| Check | Compare | Source |
|-------|---------|--------|
| Device match | `calibration.context.device_id` vs `device.json:device_id` | Loaded from device directory |
| Cooldown match | `calibration.context.cooldown_id` vs current cooldown ID | From session start or `active_context.json` |
| Wiring match | `calibration.context.wiring_rev` vs SHA-256(hardware.json) | Computed at session start |
| Staleness | `calibration.last_modified` vs current timestamp | Wall clock |

### 4.2 What Should Happen on Mismatch

| Mismatch Type | Default Action | Override |
|---------------|----------------|----------|
| **Device mismatch** | **Refuse to load** — raise `ConfigError` | `force_load=True` with explicit warning |
| **Cooldown mismatch** | **Warn loudly** — log at ERROR level, require explicit acknowledgement | `--accept-stale-cooldown` flag or notebook cell confirmation |
| **Wiring mismatch** | **Refuse to load** — wiring change invalidates calibrations | `force_load=True` with explicit warning |
| **Stale (>24h)** | **Warn** — log at WARNING level; suggest recalibration | Configurable staleness threshold |

### 4.3 Implementation Sketch (Not Implemented)

```python
# In CalibrationStore.__init__ (future):
def _validate_context(self, expected_device_id, expected_cooldown_id, hardware_hash):
    ctx = self._data.context
    if ctx is None:
        logger.warning("No context in calibration.json — legacy file")
        return

    if ctx.device_id != expected_device_id:
        raise ConfigError(
            f"Calibration device_id='{ctx.device_id}' does not match "
            f"expected device_id='{expected_device_id}'"
        )

    if ctx.wiring_rev != hardware_hash:
        raise ConfigError(
            f"Calibration wiring_rev='{ctx.wiring_rev}' does not match "
            f"current hardware hash='{hardware_hash}'"
        )

    if ctx.cooldown_id != expected_cooldown_id:
        logger.error(
            "Calibration cooldown_id='%s' does not match current cooldown '%s'. "
            "These calibrations may be stale.",
            ctx.cooldown_id, expected_cooldown_id,
        )
```

---

## 5. Phased Implementation Plan

### Phase 0: Docs + Audit (This Task)

**Status**: In progress.

**Deliverables**:
- `docs/audit/DEVICE_COOLDOWN_CALIBRATION_API.md` — current state audit
- `docs/audit/PATHS_AND_OWNERSHIP.md` — file inventory
- `docs/audit/STALE_CALIBRATION_RISK_REPORT.md` — risk assessment
- `docs/audit/MODULARITY_RECOMMENDATIONS.md` — this document
- Updated `qubox_v2/docs/API_REFERENCE.md`
- Updated `qubox_v2/docs/CALIBRATION_POLICY.md`

**No code changes.**

---

### Phase 1: Introduce Explicit Context Metadata + Safe Loading

**Goal**: Add context metadata to calibration files and validate on load.
Minimal code changes; backward-compatible.

**Modules likely to change**:

| Module | Change |
|--------|--------|
| `calibration/models.py` | Add `CalibrationContext` model; add `context` field to `CalibrationData` |
| `calibration/store.py` | Add `_validate_context()` called from `_load_or_create()`; accept `device_id`, `cooldown_id`, `hardware_hash` in constructor |
| `experiments/session.py` | Pass context fields to `CalibrationStore.__init__()`; compute `wiring_rev` from hardware.json hash |
| `core/session_state.py` | Add `device_id` and `cooldown_id` to `SessionState` |

**Backward compatibility**: If `calibration.json` has no `context` block
(legacy files), emit a deprecation warning and skip validation.

**Migration**: Add a schema migration from v3.0.0 to v4.0.0 that inserts
an empty `context` block.

**Estimated scope**: ~100 lines of new code; ~30 lines of modified code.

---

### Phase 2: Calibration Registry + Cooldown Scoping

**Goal**: Implement the per-cooldown directory layout.  Enable cooldown
isolation.

**Modules likely to change**:

| Module | Change |
|--------|--------|
| `experiments/session.py` | Resolve `experiment_path` from `device_id` + `cooldown_id`; create cooldown directory on first use |
| `calibration/store.py` | Support cooldown-scoped file paths; add `new_cooldown()` method that creates fresh calibration with copied device-level defaults |
| `core/artifact_manager.py` | Scope artifacts under cooldown directory |
| New: `devices/device_registry.py` | `DeviceRegistry` class managing `devices/` directory, `device.json` files, cooldown listing |
| New: `devices/context_resolver.py` | Resolve `active_context.json` → device path + cooldown path |

**Key design decisions**:
- On new cooldown: copy device-level `cqed_params.json` but create fresh `calibration.json`?
  Or copy last cooldown's calibration as starting point?
  **Recommendation**: Fresh calibration (empty), force user to re-calibrate.
  Optionally allow explicit `--seed-from-cooldown=cd_prev` to copy.

**Estimated scope**: ~300 lines of new code; ~100 lines of modified code.

---

### Phase 3: Multi-Device Selection UX (CLI/Notebook)

**Goal**: Provide user-facing tooling for device/cooldown management.

**New capabilities**:

| Feature | Implementation |
|---------|---------------|
| List devices | `qubox devices list` → scans `experiments/devices/` |
| List cooldowns | `qubox cooldowns list --device seq_1` |
| Activate context | `qubox activate --device seq_1 --cooldown cd_2026_02_22` |
| New cooldown | `qubox cooldown new --device seq_1 --id cd_2026_02_22` |
| New device | `qubox device new --id transmon_B --hardware path/to/hardware.json` |
| Notebook helpers | `from qubox_v2 import activate_device; session = activate_device("seq_1", "cd_2026_02_22")` |

**Modules likely to change**:

| Module | Change |
|--------|--------|
| New: `cli/device_commands.py` | CLI commands for device/cooldown management |
| New: `cli/cooldown_commands.py` | CLI commands for cooldown lifecycle |
| `experiments/session.py` | `SessionManager.from_device(device_id, cooldown_id)` classmethod |
| Notebooks | Updated setup cells using `activate_device()` instead of raw path |

**Estimated scope**: ~500 lines of new code.

---

## 6. Concrete Modules Likely to Change Later

This table lists every module that will need modification across all
phases, for planning purposes only.  **No changes are made in this task.**

| Module | Phase | Nature of Change |
|--------|-------|------------------|
| `qubox_v2/calibration/models.py` | 1 | Add `CalibrationContext` model |
| `qubox_v2/calibration/store.py` | 1, 2 | Context validation; cooldown directory support |
| `qubox_v2/experiments/session.py` | 1, 2, 3 | Context wiring; device/cooldown resolution |
| `qubox_v2/core/session_state.py` | 1 | Add device/cooldown metadata |
| `qubox_v2/core/schemas.py` | 1 | v3→v4 calibration schema migration |
| `qubox_v2/core/artifact_manager.py` | 2 | Cooldown-scoped artifact paths |
| `qubox_v2/calibration/orchestrator.py` | 2 | Context-aware patch application |
| `qubox_v2/calibration/patch_rules.py` | — | No changes expected (rules are context-agnostic) |
| `qubox_v2/experiments/experiment_base.py` | — | No changes expected (experiments are context-agnostic) |
| `qubox_v2/hardware/config_engine.py` | 1 | Compute wiring_rev hash |
| `qubox_v2/programs/macros/measure.py` | 2 | Cooldown-scoped measureConfig path |
| New: `qubox_v2/devices/device_registry.py` | 2 | Device directory management |
| New: `qubox_v2/devices/context_resolver.py` | 2 | Active context resolution |
| New: `qubox_v2/cli/device_commands.py` | 3 | CLI device management |
| New: `qubox_v2/cli/cooldown_commands.py` | 3 | CLI cooldown management |
| Notebooks | 3 | Updated setup cells |

---

## 7. Evidence and Workflow References

### 7.1 Current Notebook Workflow

The primary workflow notebook (`notebooks/post_cavity_experiment.ipynb`)
currently initializes with:

```python
session = SessionManager("./seq_1_device", qop_ip="10.157.36.68", ...)
session.open()
```

After Phase 3, this would become:

```python
from qubox_v2 import activate_device
session = activate_device("seq_1", "cd_2026_02_22", qop_ip="10.157.36.68")
session.open()
```

### 7.2 Current Risks Addressed

| Risk (from STALE_CALIBRATION_RISK_REPORT.md) | Phase Addressed |
|----------------------------------------------|-----------------|
| R1: Implicit reuse across cooldowns | Phase 1 (warn) → Phase 2 (prevent) |
| R2: Hardware changes not invalidating | Phase 1 (wiring_rev check) |
| R3: measureConfig/calibration drift | Phase 2 (unified store) |
| R6: No config-hash compatibility check | Phase 1 (context validation) |
| R7: Cross-device file copy | Phase 1 (device_id check) |
| R8: Build-hash collision | Phase 1 (cooldown_id in salt) |

### 7.3 Backward Compatibility Guarantee

- Phase 1 is fully backward-compatible: legacy `calibration.json` files
  without a `context` block are accepted with a deprecation warning.
- Phase 2 introduces new directory layout but can fallback to flat
  `experiment_path` for existing setups.
- Phase 3 is additive: `SessionManager("./path")` continues to work;
  `activate_device()` is a convenience wrapper.

---

## 8. Non-Goals

This document does **not** propose:

- Automatic calibration scheduling or recalibration triggers.
- Multi-qubit device support (beyond element-level scoping).
- Cloud-based calibration storage or remote sync.
- Changes to the QUA program layer or experiment physics.
- Changes to the gate system or simulation layer.
