# Artifact Policy

**Version**: 1.0.0
**Date**: 2026-02-21
**Status**: Governing Document

---

## 1. Principle

Strict separation between **source of truth** (human-authored or calibration-committed) and **generated artifacts** (reproducible from sources). Generated artifacts must never be committed to version control or treated as authoritative.

---

## 2. Classification

### 2.1 Source of Truth (Persist, Version-Control)

| File | Location | Owner | Description |
|------|----------|-------|------------|
| `hardware.json` | `config/` | Manual / ConfigEngine | OPX+/Octave element config |
| `pulse_specs.json` | `config/` | PulseFactory | Declarative pulse recipes |
| `calibration.json` | `config/` | CalibrationStore | Committed calibration parameters |
| `cqed_params.json` | `config/` | Legacy | Physics parameters |
| `devices.json` | `config/` | Manual | External instrument config |
| `measureConfig.json` | `config/` | measureMacro | Readout macro state |
| `calibration_history.jsonl` | `config/` | CalibrationStore | Append-only commit log |

### 2.2 Generated Artifacts (Reproducible, Never Version-Control)

| Artifact | Location | Generator | Description |
|----------|----------|-----------|------------|
| `pulses.json` | `config/` | PulseOperationManager | Full waveform arrays (transitional, deprecated) |
| QM config dict | Memory only | ConfigEngine | Compiled hardware + pulses config |
| Waveform arrays | Memory only | PulseFactory | Compiled from pulse_specs + calibration |
| Config snapshots | `artifacts/` | `save_config_snapshot()` | Point-in-time session state |
| Run summaries | `artifacts/` | `save_run_summary()` | Per-experiment execution records |
| Calibration candidates | `artifacts/calibration_candidates/` | `guarded_calibration_commit()` | Rejected calibration proposals |
| Calibration run logs | `artifacts/calibration_runs/` | Experiment classes | Per-calibration raw data |

---

## 3. Directory Structure

```
<experiment_path>/                 # e.g., seq_1_device/
├── config/                        # SOURCE OF TRUTH
│   ├── hardware.json
│   ├── pulse_specs.json           # NEW (replaces pulses.json)
│   ├── pulses.json                # DEPRECATED (transitional)
│   ├── calibration.json
│   ├── calibration_history.jsonl  # NEW (append-only log)
│   ├── cqed_params.json
│   ├── devices.json
│   └── measureConfig.json
│
├── artifacts/                     # GENERATED (reproducible)
│   ├── config_snapshot_*.json
│   ├── run_summary_*.json
│   ├── calibration_candidates/
│   │   └── ref_r180_candidate_*.json
│   ├── calibration_runs/
│   │   └── power_rabi_x180_*.json
│   └── <build_hash>/             # NEW (per-session artifacts)
│       ├── session_state.json
│       ├── generated_config.json
│       └── reports/
│           └── legacy_parity_*.md
│
└── data/                          # RAW EXPERIMENT DATA
    └── <experiment_name>/
        └── <timestamp>/
            └── output.npz
```

---

## 4. Build-Hash Keyed Artifacts

### 4.1 Build Hash

`SessionState.build_hash` is a SHA-256 hash of the concatenated contents of all source-of-truth files:

```python
build_hash = sha256(
    hardware.json + pulse_specs.json + calibration.json
).hexdigest()[:12]
```

### 4.2 Artifact Manager

```python
class ArtifactManager:
    def __init__(self, experiment_path: Path, build_hash: str):
        self.root = experiment_path / "artifacts" / build_hash
        self.root.mkdir(parents=True, exist_ok=True)

    def save_session_state(self, state: SessionState) -> Path: ...
    def save_generated_config(self, config: dict) -> Path: ...
    def save_report(self, name: str, content: str) -> Path: ...
    def list_artifacts(self) -> list[Path]: ...
```

### 4.3 Artifact Lifecycle

1. Artifacts are created during session initialization and experiment execution.
2. Artifacts are never modified after creation.
3. Old artifact directories may be pruned periodically (they are reproducible).
4. The latest `session_state.json` can always be regenerated from source-of-truth files.

---

## 5. .gitignore Recommendations

```gitignore
# Generated artifacts (reproducible from source-of-truth)
**/artifacts/
**/data/

# Deprecated transitional file (regenerated from pulse_specs.json)
**/config/pulses.json

# Python bytecode
**/__pycache__/
*.pyc

# OS files
.DS_Store
Thumbs.db

# IDE
.vscode/
.idea/

# Temporary calibration files
**/calibration_db.scratch.json
**/calibration_db.tmp
```

---

## 6. What Must Not Be an Artifact

The following must never be placed in the `artifacts/` directory:

| Item | Reason | Correct Location |
|------|--------|-----------------|
| `calibration.json` | Source of truth | `config/` |
| `hardware.json` | Source of truth | `config/` |
| User notebook changes | Source code | Root / notebooks/ |
| Committed integration weights | Part of pulse_specs | `config/pulse_specs.json` |

---

## 7. Cleanup Policy

| Artifact Type | Retention | Cleanup Trigger |
|--------------|-----------|----------------|
| Config snapshots | Last 50 | Session startup |
| Run summaries | Last 100 | Session startup |
| Calibration candidates | Last 20 | Session startup |
| Build-hash directories | Last 10 | Manual / session startup |
| Calibration history | Permanent | Never |

Cleanup is advisory, not enforced. Users may keep all artifacts if disk space permits.
