# Calibration Policy

**Version**: 1.0.0
**Date**: 2026-02-21
**Status**: Governing Document

---

## 1. Core Principle

**Calibration parameters must NEVER auto-update.** Every calibration change follows the mandatory lifecycle:

```
Acquire → Analyze → Plot → User Confirm → Commit
```

No shortcut. No silent writes. No `update_calibration=True` that bypasses review.

---

## 2. Calibration State Machine

### 2.1 States

```python
class CalibrationState(str, Enum):
    IDLE           = "idle"            # No calibration in progress
    CONFIGURED     = "configured"      # Parameters set, ready to acquire
    ACQUIRING      = "acquiring"       # Hardware acquisition running
    ACQUIRED       = "acquired"        # Raw data available
    ANALYZING      = "analyzing"       # Fit/analysis in progress
    ANALYZED       = "analyzed"        # Analysis complete, patch proposed
    PLOTTED        = "plotted"         # Results visualized for user
    PENDING_APPROVAL = "pending_approval"  # Waiting for user decision
    COMMITTING     = "committing"      # Applying approved patch
    COMMITTED      = "committed"       # Patch applied and persisted
    FAILED         = "failed"          # Error during any phase
    ABORTED        = "aborted"         # User cancelled
    ROLLED_BACK    = "rolled_back"     # Reverted to previous state
```

### 2.2 Allowed Transitions

```
IDLE → CONFIGURED           # User sets experiment parameters
CONFIGURED → ACQUIRING      # run() begins hardware execution
ACQUIRING → ACQUIRED        # run() completes, RunResult available
ACQUIRING → FAILED          # Hardware error
ACQUIRED → ANALYZING        # analyze() begins
ANALYZING → ANALYZED        # analyze() completes, CalibrationPatch produced
ANALYZING → FAILED          # Analysis error (bad fit, etc.)
ANALYZED → PLOTTED          # plot() called, user can see results
PLOTTED → PENDING_APPROVAL  # User presented with commit decision
PENDING_APPROVAL → COMMITTING  # User approves
PENDING_APPROVAL → ABORTED    # User rejects
COMMITTING → COMMITTED     # Patch applied to CalibrationStore
COMMITTING → FAILED         # Write error
COMMITTED → ROLLED_BACK    # User triggers rollback

# Any state → ABORTED (user can abort at any time)
# Any state → FAILED (unrecoverable error)
```

### 2.3 Enforcement Rules

1. `calibration.json` may only be written when the state machine is in `COMMITTING`.
2. Transition to `COMMITTING` requires passing through `PENDING_APPROVAL`.
3. No state may be skipped. `ACQUIRED` cannot jump to `COMMITTED`.
4. The state machine logs every transition with timestamp to the session log.
5. Failed transitions raise `CalibrationStateError` with the attempted and current states.

---

## 3. CalibrationPatch

A `CalibrationPatch` is an explicit, inspectable diff object produced by `analyze()`.

### 3.1 Structure

```python
@dataclass(frozen=True)
class CalibrationPatch:
    experiment: str              # "power_rabi", "resonator_spectroscopy", etc.
    timestamp: str               # ISO 8601
    changes: list[PatchEntry]    # Ordered list of changes
    validation: PatchValidation  # Quality gates that were checked
    metadata: dict[str, Any]     # Fit params, R², run metadata

@dataclass(frozen=True)
class PatchEntry:
    path: str          # Dotted key path: "frequencies.resonator.if_freq"
    old_value: Any     # Previous value (None if new)
    new_value: Any     # Proposed value
    dtype: str         # Expected type: "float", "int", "str", "list[float]"

@dataclass(frozen=True)
class PatchValidation:
    passed: bool
    checks: dict[str, bool]     # {"min_r2": True, "bounds_check": True, ...}
    reasons: list[str]          # Human-readable failure reasons
```

### 3.2 Rules

1. A patch must explicitly list every key it modifies. No implicit side effects.
2. `old_value` must match the current value in `CalibrationStore`. If it doesn't, the patch is stale and must be rejected.
3. `new_value` must be JSON-serializable. Complex numbers, numpy arrays, and other non-serializable types must be converted.
4. The `validation` field must be populated before the patch reaches `PENDING_APPROVAL`.
5. Patches that fail validation may still be committed if the user explicitly overrides (with logged justification).

---

## 4. Validation Gates

### 4.1 Standard Gates

| Gate | Applies To | Description |
|------|-----------|-------------|
| `min_r2` | Fit-based calibrations | Minimum R² for the fit (default: 0.80) |
| `bounds_check` | All | New value within physically reasonable bounds |
| `monotonic_check` | Rabi, spectroscopy | Data shows expected trend near extremum |
| `relative_residual` | Fit-based | RMS residual / data range < threshold |
| `stale_check` | All | Patch `old_value` matches current store value |
| `type_check` | All | `new_value` type matches `dtype` declaration |

### 4.2 Experiment-Specific Gates

| Experiment | Additional Gates |
|-----------|-----------------|
| `PowerRabi` | `g_pi` within [0.01, 2.0], left/right monotonicity near minimum |
| `ResonatorSpectroscopy` | `f0` within ±50 MHz of LO, `kappa` > 0 |
| `T1Relaxation` | `T1` > 100 ns, `T1` < 1 ms |
| `T2Ramsey` | `T2_star` > 100 ns, `T2_star` < T1 × 3 |
| `DRAGCalibration` | `optimal_alpha` within [-5.0, 5.0] |
| `ReadoutGEDiscrimination` | `fidelity` > 0.50 |

### 4.3 Gate Override

Users may override failed gates with explicit acknowledgment:

```python
patch.override_validation(
    gate="min_r2",
    reason="Known low-Q sample, R²=0.72 is acceptable",
    user="jl82323"
)
```

Overrides are recorded in the patch metadata and in calibration history.

---

## 5. Calibration History

### 5.1 Append-Only Log

Every committed patch is appended to `calibration_history.jsonl`:

```json
{"timestamp": "2026-02-21T23:02:28", "experiment": "power_rabi", "changes": [...], "validation": {...}, "build_hash": "a3f7c2d"}
```

This file is append-only. It must never be truncated or edited.

### 5.2 Snapshot Strategy

Before applying a patch, `CalibrationStore` creates a timestamped snapshot:

```
config/calibration_2026-02-21T230228.json
```

Snapshots enable point-in-time recovery. The `diff_snapshots()` utility in `calibration/history.py` compares any two snapshots.

### 5.3 Rollback

Rollback restores the snapshot taken immediately before the rolled-back commit:

```python
store.rollback(to_snapshot="calibration_2026-02-21T230228.json")
```

Rollback itself is recorded as a history entry with `"action": "rollback"`.

---

## 6. Parameter Storage Structure

### 6.1 calibration.json Layout

```json
{
  "version": "3.0.0",
  "created": "2026-02-21T13:27:47",
  "last_modified": "2026-02-21T23:02:28",

  "discrimination": {
    "<element>": {
      "threshold": float,
      "angle": float,
      "mu_g": [float, float],
      "mu_e": [float, float],
      "sigma_g": float,
      "sigma_e": float,
      "fidelity": float
    }
  },

  "readout_quality": {
    "<element>": {
      "F": float, "Q": float, "V": float,
      "t01": float, "t10": float,
      "confusion_matrix": [[float]]
    }
  },

  "frequencies": {
    "<element>": {
      "lo_freq": float,
      "if_freq": float,
      "qubit_freq": float | null,
      "anharmonicity": float | null,
      "fock_freqs": [float] | null,
      "chi": float | null,
      "kappa": float | null,
      "kerr": float | null
    }
  },

  "coherence": {
    "<element>": {
      "T1": float | null,
      "T2_ramsey": float | null,
      "T2_echo": float | null
    }
  },

  "pulse_calibrations": {
    "<pulse_name>": {
      "pulse_name": str,
      "element": str,
      "amplitude": float | null,
      "length": int | null,
      "sigma": float | null,
      "drag_coeff": float | null
    }
  },

  "fit_history": {},
  "pulse_train_results": {},
  "fock_sqr_calibrations": {},
  "multi_state_calibration": {}
}
```

### 6.2 Source of Truth Hierarchy

For parameters that appear in multiple files:

```
calibration.json            ← AUTHORITATIVE for calibrated values
    overrides
cqed_params.json            ← LEGACY reference for physics parameters
    provides defaults for
hardware.json               ← AUTHORITATIVE for LO frequencies, element wiring
```

If `calibration.json` has `frequencies.resonator.lo_freq`, that value takes precedence over anything in `cqed_params.json`.

---

## 7. Experiment Integration

### 7.1 Current Pattern (Preserved)

```python
# In notebook:
exp = PowerRabi(session)
result = exp.run(max_gain=1.2, n_avg=5000)
analysis = exp.analyze(result, update_calibration=True)
exp.plot(analysis)
```

When `update_calibration=True`, `analyze()` calls `guarded_calibration_commit()` internally. This existing pattern continues to work.

### 7.2 Target Pattern (State Machine Opt-In)

```python
# In notebook:
exp = PowerRabi(session)
result = exp.run(max_gain=1.2, n_avg=5000)
analysis = exp.analyze(result)
exp.plot(analysis)

# Explicit patch inspection and approval
patch = exp.propose_calibration_patch(analysis)
print(patch.summary())  # Show what would change
patch.approve()          # User explicitly approves
session.calibration.apply_patch(patch)
```

The state machine is **opt-in** during the transition period. Existing `update_calibration=True` continues to work through `guarded_calibration_commit()`, which internally creates and auto-approves a patch.

---

## 8. What Must Never Happen

1. An experiment's `__init__()` writing to `calibration.json`.
2. `analyze()` writing to `calibration.json` without passing through validation gates.
3. A silent calibration update with no log entry.
4. Calibration data from one element contaminating another element's section.
5. A patch applied against stale data (old_value mismatch).
6. Calibration history being truncated, edited, or rewritten.

---

## 9. Known Gaps / Risks (2026-02-22 Audit)

The following gaps were identified during the device/cooldown/calibration audit.
They represent deviations from the policy above that exist in the current codebase.

### 9.1 No Cooldown Scoping

`calibration.json` has no `cooldown_id` or `device_id` field.  Calibrations
from a previous cooldown are silently loaded on session start without any
freshness check.  This violates the spirit of the "never auto-update" principle
because the user is implicitly reusing stale data without explicit confirmation.

**Reference**: `docs/audit/STALE_CALIBRATION_RISK_REPORT.md` Risk R1.

### 9.2 No Hardware-Calibration Coupling

Changing `hardware.json` (LO frequency, port assignments) does not invalidate
`calibration.json`.  There is no `wiring_revision` or `config_hash` embedded
in the calibration file to detect wiring drift.

**Reference**: `docs/audit/STALE_CALIBRATION_RISK_REPORT.md` Risk R2.

### 9.3 Direct Calibration Mutation in analyze()

Several experiment `analyze()` methods call `calibration_store.set_*()` directly,
bypassing the state machine and `CalibrationOrchestrator`.  This is documented
in `docs/audit/LEAKS.md` Section A (24 instances).  Notably:

- `ResonatorSpectroscopy.analyze()` → `set_frequencies()`
- `ReadoutGEDiscrimination.analyze()` → `set_discrimination()` + mutates `measureMacro`
- `CalibrateReadoutFull.run()` → calls `calibration_store.save()`, `measureMacro.save_json()`

These direct mutations circumvent the validation gates required by this policy.

### 9.4 Dual-Truth for Discrimination Params

Discrimination parameters (threshold, angle, fidelity, confusion matrix) exist in
both `calibration.json` and `measureConfig.json` with no enforced sync mechanism.
A calibration update to one store does not automatically propagate to the other.

**Reference**: `docs/audit/PATHS_AND_OWNERSHIP.md` Observation 1.

### 9.5 Resolution Plan

See `docs/audit/MODULARITY_RECOMMENDATIONS.md` for the phased plan:
- Phase 1: Add context metadata to calibration files, validate on load.
- Phase 2: Cooldown-scoped directory layout.
- Phase 3: Multi-device selection UX.
