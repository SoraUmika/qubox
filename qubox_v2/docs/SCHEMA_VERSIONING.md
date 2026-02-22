# Schema Versioning

**Version**: 1.0.0
**Date**: 2026-02-21
**Status**: Governing Document

---

## 1. Principle

Every persisted JSON file must include a schema version field. The system must refuse to load files with unsupported versions and must never silently overwrite or upgrade.

---

## 2. Versioned Files

| File | Version Field | Current Version | Model |
|------|--------------|----------------|-------|
| `hardware.json` | `version` | 1 | `HardwareConfig` |
| `pulse_specs.json` | `schema_version` | 1 | `PulseSpecFile` |
| `pulses.json` (deprecated) | `_schema_version` | 2 | `PulseOperationManager` |
| `calibration.json` | `version` | `"3.0.0"` | `CalibrationData` |
| `measureConfig.json` | `_version` | 5 | `measureMacro` |
| `devices.json` | `schema_version` | 1 | `DeviceConfig` |
| `cqed_params.json` | (unversioned) | — | Legacy compat |

### 2.1 Note on `cqed_params.json`

This file is legacy and unversioned. It is loaded read-only. No schema enforcement is applied. Over time, its contents should migrate into `calibration.json` under the `frequencies` and `coherence` sections.

---

## 3. Version Field Convention

New files use `schema_version` (integer):

```json
{
  "schema_version": 1,
  ...
}
```

Existing files retain their current field names for backward compatibility:
- `hardware.json` → `version` (integer)
- `calibration.json` → `version` (string, e.g. `"3.0.0"`)
- `measureConfig.json` → `_version` (integer)

---

## 4. Loading Behavior

```
Load file
    │
    ├── Has version field?
    │   ├── YES → Parse version
    │   │         ├── Supported? → Load normally
    │   │         └── Unsupported? → raise UnsupportedSchemaError
    │   │
    │   └── NO → Assign default version 1
    │             └── Log warning: "File {path} has no schema version, assuming v1"
    │
    └── File missing? → raise FileNotFoundError (never create implicitly)
```

### 4.1 UnsupportedSchemaError

```python
class UnsupportedSchemaError(Exception):
    def __init__(self, file_path: str, found_version: int, supported_versions: list[int]):
        self.file_path = file_path
        self.found_version = found_version
        self.supported_versions = supported_versions
        super().__init__(
            f"Schema version {found_version} in {file_path} is not supported. "
            f"Supported versions: {supported_versions}. "
            f"Run the migration tool to upgrade."
        )
```

---

## 5. Migration

### 5.1 Rules

1. Migration must never overwrite the original file. It creates a new file.
2. The original file is renamed with a `.bak.<timestamp>` suffix.
3. Migration is a separate, explicit step — never triggered automatically during load.
4. Each migration function handles exactly one version step: `vN → vN+1`.
5. Multi-step migration chains: `v1 → v2` then `v2 → v3`.

### 5.2 Migration Tool

```bash
python -m qubox_v2.migration.schema_migrator \
    --file config/calibration.json \
    --target-version 4
```

Output:
```
Reading config/calibration.json (version 3.0.0)
Migrating 3 → 4...
  - Added field: calibration.post_selection (default: {})
  - Renamed field: calibration.fit_history → calibration.fit_records
Written config/calibration.json
Backup saved: config/calibration.json.bak.20260221T231500
```

### 5.3 Migration Registry

```python
# In core/schemas.py
MIGRATIONS: dict[str, dict[int, Callable]] = {
    "hardware": {
        # version 1 → 2
        2: migrate_hardware_v1_to_v2,
    },
    "pulse_specs": {
        # No migrations yet (v1 is current)
    },
    "calibration": {
        # version 3 → 4 (when needed)
    },
}
```

---

## 6. Schema Validators

### 6.1 Validator Interface

```python
def validate_schema(file_path: Path, file_type: str) -> ValidationResult:
    """
    Validate a JSON file against its expected schema.

    Parameters
    ----------
    file_path : Path
        Path to the JSON file.
    file_type : str
        One of: "hardware", "pulse_specs", "calibration", "measure_config", "devices"

    Returns
    -------
    ValidationResult
        .valid: bool
        .version: int
        .errors: list[str]
        .warnings: list[str]
    """
```

### 6.2 Session Startup Validation

```
SessionManager.open()
    │
    ├── validate_schema("hardware.json", "hardware")
    │   └── Fail → raise with actionable message
    │
    ├── validate_schema("calibration.json", "calibration")
    │   └── Fail → raise with actionable message
    │
    ├── validate_schema("pulse_specs.json" or "pulses.json", "pulse_specs" or "pulses")
    │   └── Fail → raise with actionable message
    │
    └── All pass → construct SessionState → continue initialization
```

---

## 7. Adding a New Schema Version

When you need to change a persisted file format:

1. **Increment the version number** in the model.
2. **Write a migration function** `migrate_vN_to_vN+1(data: dict) -> dict`.
3. **Register the migration** in `MIGRATIONS`.
4. **Add the new version** to the schema validator's supported list.
5. **Update this document** with the new version and what changed.
6. **Add a test** in `verification/schema_checks.py` that loads a v(N) file, migrates, and validates as v(N+1).
7. **Never remove support** for loading the previous version (at minimum, migration must work).

---

## 8. Version History

### hardware.json

| Version | Date | Changes |
|---------|------|---------|
| 1 | 2026-02-19 | Initial schema: controllers, octaves, elements, __qubox |

### pulse_specs.json

| Version | Date | Changes |
|---------|------|---------|
| 1 | 2026-02-21 | Initial schema: declarative pulse specifications |

### calibration.json

| Version | Date | Changes |
|---------|------|---------|
| 3.0.0 | 2026-02-21 | Current: discrimination, readout_quality, frequencies, coherence, pulse_calibrations, fit_history, pulse_train_results, fock_sqr_calibrations, multi_state_calibration |

### measureConfig.json

| Version | Date | Changes |
|---------|------|---------|
| 5 | 2026-02-21 | Current: pulse_op, weights, demod config, discrimination params, quality params, post-selection |
