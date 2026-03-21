"""qubox.schemas — JSON config file schema validation and migration.

Migrated from ``qubox_v2_legacy.core.schemas``.
The ``_validate_pulse_specs`` type-specific check has been made standalone
(no longer imports from qubox_v2_legacy.pulses.spec_models).

Usage::

    from qubox.schemas import validate_config_dir, validate_schema

    results = validate_config_dir("./config")
    for r in results:
        if not r.valid:
            print(r.summary())
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class UnsupportedSchemaError(Exception):
    """Raised when a file contains an unsupported schema version."""

    def __init__(self, file_path: str, found_version: Any, supported_versions: list):
        self.file_path = file_path
        self.found_version = found_version
        self.supported_versions = supported_versions
        super().__init__(
            f"Schema version {found_version!r} in '{file_path}' is not supported. "
            f"Supported: {supported_versions}. Run the migration tool to upgrade."
        )


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    """Result of a single schema validation check."""

    valid: bool
    version: Any = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        status = "PASS" if self.valid else "FAIL"
        lines = [f"Validation: {status} (version={self.version})"]
        for e in self.errors:
            lines.append(f"  ERROR: {e}")
        for w in self.warnings:
            lines.append(f"  WARN:  {w}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Schema definitions
# ---------------------------------------------------------------------------

# Maps file_type → (version_field, supported_versions, required_top_keys)
_SCHEMA_DEFS: dict[str, tuple[str, list[Any], list[str]]] = {
    "hardware": (
        "version",
        [1],
        ["controllers", "elements"],
    ),
    "pulse_specs": (
        "schema_version",
        [1],
        ["specs"],
    ),
    "pulses": (
        "_schema_version",
        [1, 2],
        ["pulses"],
    ),
    "calibration": (
        "version",
        ["5.0.0", "5.1.0"],
        [],
    ),
    "measure_config": (
        "_version",
        [4, 5],
        [],
    ),
    "devices": (
        "schema_version",
        [1],
        ["devices"],
    ),
}

# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def validate_schema(
    file_path: str | Path,
    file_type: str,
    *,
    data: dict | None = None,
) -> ValidationResult:
    """Validate a JSON file against its expected schema.

    Parameters
    ----------
    file_path : str | Path
        Path to the JSON file.
    file_type : str
        One of: ``"hardware"``, ``"pulse_specs"``, ``"pulses"``,
        ``"calibration"``, ``"measure_config"``, ``"devices"``.
    data : dict, optional
        Pre-loaded JSON data; file is read from disk if omitted.

    Returns
    -------
    ValidationResult
    """
    file_path = Path(file_path)

    if file_type not in _SCHEMA_DEFS:
        return ValidationResult(
            valid=False,
            errors=[f"Unknown file_type '{file_type}'. "
                    f"Known types: {sorted(_SCHEMA_DEFS.keys())}"],
        )

    version_field, supported, required_keys = _SCHEMA_DEFS[file_type]
    errors: list[str] = []
    warnings: list[str] = []

    if data is None:
        if not file_path.exists():
            return ValidationResult(valid=False, errors=[f"File not found: {file_path}"])
        try:
            data = json.loads(file_path.read_bytes())
        except json.JSONDecodeError as exc:
            return ValidationResult(valid=False, errors=[f"JSON parse error in {file_path}: {exc}"])

    version = data.get(version_field)
    if version is None:
        warnings.append(f"File '{file_path.name}' has no '{version_field}' field, assuming v1")
        version = 1

    if version not in supported:
        errors.append(f"Unsupported {version_field}={version!r}. Supported: {supported}")

    for key in required_keys:
        if key not in data:
            errors.append(f"Missing required top-level key '{key}'")

    if file_type == "hardware":
        _validate_hardware(data, errors, warnings)
    elif file_type == "calibration":
        _validate_calibration(data, errors, warnings)

    return ValidationResult(valid=len(errors) == 0, version=version, errors=errors, warnings=warnings)


def _validate_hardware(data: dict, errors: list[str], warnings: list[str]) -> None:
    elements = data.get("elements", {})
    if not elements:
        errors.append("hardware.json has no elements defined")
        return
    for el_name, el_data in elements.items():
        if not isinstance(el_data, dict):
            errors.append(f"Element '{el_name}' is not a dict")
            continue
        ops = el_data.get("operations", {})
        if "const" not in ops:
            warnings.append(f"Element '{el_name}' missing 'const' operation")
        if "zero" not in ops:
            warnings.append(f"Element '{el_name}' missing 'zero' operation")


def _validate_calibration(data: dict, errors: list[str], warnings: list[str]) -> None:
    version = data.get("version")
    if version is not None and not isinstance(version, str):
        warnings.append(
            f"calibration.json version should be a string (e.g. '5.1.0'), "
            f"got {type(version).__name__}"
        )
    context = data.get("context")
    if context is not None:
        if not isinstance(context, dict):
            errors.append("calibration 'context' must be a dict")
        else:
            for key in ("sample_id", "cooldown_id", "wiring_rev"):
                val = context.get(key)
                if val is not None and not isinstance(val, str):
                    errors.append(f"context.{key} must be a string, got {type(val).__name__}")


# ---------------------------------------------------------------------------
# Migration registry
# ---------------------------------------------------------------------------

MigrationFunc = Callable[[dict], dict]

MIGRATIONS: dict[str, dict[int, MigrationFunc]] = {
    "hardware": {},
    "pulse_specs": {},
    "calibration": {},
    "measure_config": {},
    "devices": {},
}


def register_migration(file_type: str, target_version: int, func: MigrationFunc) -> None:
    """Register a migration function for one version step.

    Parameters
    ----------
    file_type : str
        Config file type (e.g. ``"hardware"``).
    target_version : int
        Version the data will be at *after* the migration.
    func : callable
        ``func(data: dict) -> dict``
    """
    if file_type not in MIGRATIONS:
        MIGRATIONS[file_type] = {}
    MIGRATIONS[file_type][target_version] = func
    _logger.debug("Registered migration: %s v%d", file_type, target_version)


def migrate(
    data: dict,
    file_type: str,
    from_version: int,
    to_version: int,
) -> dict:
    """Apply a chain of registered migrations from *from_version* to *to_version*.

    Raises :class:`UnsupportedSchemaError` if a required migration step is missing.
    """
    if from_version >= to_version:
        return data
    available = MIGRATIONS.get(file_type, {})
    current = from_version
    while current < to_version:
        next_version = current + 1
        if next_version not in available:
            raise UnsupportedSchemaError(
                file_path=f"<{file_type}>",
                found_version=current,
                supported_versions=[to_version],
            )
        _logger.info("Migrating %s: v%d → v%d", file_type, current, next_version)
        data = available[next_version](data)
        current = next_version
    return data


def migrate_file(
    file_path: str | Path,
    file_type: str,
    target_version: int,
    *,
    backup: bool = True,
) -> Path:
    """Migrate a JSON config file to *target_version* in place.

    Creates a ``.bak.<timestamp>`` backup unless ``backup=False``.
    """
    from datetime import datetime

    file_path = Path(file_path)
    data = json.loads(file_path.read_bytes())

    version_field = _SCHEMA_DEFS.get(file_type, ("schema_version", [], []))[0]
    current_version = data.get(version_field, 1)
    if isinstance(current_version, str):
        try:
            current_version = int(current_version.split(".")[0])
        except (ValueError, AttributeError):
            current_version = 1

    if current_version >= target_version:
        _logger.info("File %s already at version %s, no migration needed", file_path, current_version)
        return file_path

    if backup:
        ts = datetime.now().strftime("%Y%m%dT%H%M%S")
        bak_path = file_path.with_suffix(f".bak.{ts}")
        bak_path.write_bytes(file_path.read_bytes())
        _logger.info("Backup saved: %s", bak_path)

    migrated = migrate(data, file_type, current_version, target_version)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(migrated, f, indent=2, ensure_ascii=False)
        f.write("\n")
    _logger.info("Migrated %s to version %d", file_path, target_version)
    return file_path


# ---------------------------------------------------------------------------
# Batch validation
# ---------------------------------------------------------------------------

def validate_config_dir(config_dir: str | Path) -> list[ValidationResult]:
    """Validate all recognised config files in *config_dir*.

    Returns a list of :class:`ValidationResult` objects, one per file found.
    Intended to be called during session startup to surface schema issues early.
    """
    config_dir = Path(config_dir)
    results = []

    file_map = {
        "hardware.json": "hardware",
        "pulse_specs.json": "pulse_specs",
        "pulses.json": "pulses",
        "calibration.json": "calibration",
        "measureConfig.json": "measure_config",
        "devices.json": "devices",
    }

    for filename, file_type in file_map.items():
        path = config_dir / filename
        if not path.exists():
            continue
        result = validate_schema(path, file_type)
        if not result.valid:
            _logger.error("Schema validation failed for %s: %s", filename, "; ".join(result.errors))
        elif result.warnings:
            _logger.warning("Schema warnings for %s: %s", filename, "; ".join(result.warnings))
        results.append(result)

    return results
