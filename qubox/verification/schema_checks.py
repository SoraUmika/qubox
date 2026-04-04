"""Schema validation tests for all config files.

Verifies that:
- All config files parse and pass schema validation
- Version fields are present and supported
- Required top-level keys exist
- File-type specific invariants hold

See docs/SCHEMA_VERSIONING.md for the specification.

Usage
-----
>>> from qubox.verification.schema_checks import run_schema_checks
>>> results = run_schema_checks("seq_1_device/config")
>>> assert all(r.valid for r in results)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Test result
# ---------------------------------------------------------------------------

@dataclass
class SchemaCheckResult:
    """Result of a single schema check."""
    file_name: str
    file_type: str
    valid: bool = True
    version: Any = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        status = "PASS" if self.valid else "FAIL"
        msg = f"  {status} {self.file_name} (type={self.file_type}, v={self.version})"
        if self.errors:
            msg += f" — {'; '.join(self.errors)}"
        return msg


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_hardware(config_dir: Path) -> SchemaCheckResult:
    """Check hardware.json schema."""
    from ..core.schemas import validate_schema

    path = config_dir / "hardware.json"
    result = SchemaCheckResult(file_name="hardware.json", file_type="hardware")

    if not path.exists():
        result.valid = False
        result.errors.append("File not found")
        return result

    vr = validate_schema(path, "hardware")
    result.valid = vr.valid
    result.version = vr.version
    result.errors = vr.errors
    result.warnings = vr.warnings

    # Additional hardware-specific checks
    if vr.valid:
        data = json.loads(path.read_bytes())

        # Check __qubox marker
        if "__qubox" not in data:
            result.warnings.append("Missing __qubox metadata section")

        # Check element count
        elements = data.get("elements", {})
        if len(elements) == 0:
            result.errors.append("No elements defined")
            result.valid = False

    return result


def check_calibration(config_dir: Path) -> SchemaCheckResult:
    """Check calibration.json schema."""
    from ..core.schemas import validate_schema

    path = config_dir / "calibration.json"
    result = SchemaCheckResult(file_name="calibration.json", file_type="calibration")

    if not path.exists():
        result.valid = False
        result.errors.append("File not found")
        return result

    vr = validate_schema(path, "calibration")
    result.valid = vr.valid
    result.version = vr.version
    result.errors = vr.errors
    result.warnings = vr.warnings

    return result


def check_pulse_specs(config_dir: Path) -> SchemaCheckResult:
    """Check pulse_specs.json (or pulses.json fallback) schema."""
    from ..core.schemas import validate_schema

    ps_path = config_dir / "pulse_specs.json"
    if ps_path.exists():
        file_type = "pulse_specs"
        path = ps_path
    else:
        path = config_dir / "pulses.json"
        file_type = "pulses"

    result = SchemaCheckResult(file_name=path.name, file_type=file_type)

    if not path.exists():
        result.valid = False
        result.errors.append("Neither pulse_specs.json nor pulses.json found")
        return result

    vr = validate_schema(path, file_type)
    result.valid = vr.valid
    result.version = vr.version
    result.errors = vr.errors
    result.warnings = vr.warnings

    # Spec-specific checks
    if vr.valid and file_type == "pulse_specs":
        data = json.loads(path.read_bytes())
        _check_pulse_spec_invariants(data, result)

    return result


def _check_pulse_spec_invariants(data: dict, result: SchemaCheckResult) -> None:
    """Check pulse_specs.json invariants from PULSE_SPEC_SCHEMA.md."""
    specs = data.get("specs", {})
    el_ops = data.get("element_operations", {})
    weights = data.get("integration_weights", {})

    from ..pulses.spec_models import VALID_SHAPES

    elements_seen: set[str] = set()
    element_ops: dict[str, set[str]] = {}

    for name, spec in specs.items():
        shape = spec.get("shape", "")
        element = spec.get("element", "")
        op = spec.get("op", "")

        # Shape validation
        if shape not in VALID_SHAPES:
            result.errors.append(f"Spec '{name}': unknown shape '{shape}'")

        # Track elements and ops
        if element:
            elements_seen.add(element)
            element_ops.setdefault(element, set()).add(op)

        # rotation_derived must have reference_spec
        if shape == "rotation_derived":
            ref = spec.get("params", {}).get("reference_spec")
            if not ref:
                result.errors.append(f"Spec '{name}': rotation_derived missing reference_spec")
            elif ref not in specs:
                result.errors.append(f"Spec '{name}': reference_spec '{ref}' not found")

    # Every element should have const and zero
    for el in elements_seen:
        ops = element_ops.get(el, set())
        if "const" not in ops:
            result.warnings.append(f"Element '{el}' missing 'const' operation")
        if "zero" not in ops:
            result.warnings.append(f"Element '{el}' missing 'zero' operation")

    # Integration weight segment lengths must be divisible by 4
    for w_name, w_def in weights.items():
        if w_def.get("type") == "segmented":
            for seg_key in ("cosine_segments", "sine_segments"):
                for seg in w_def.get(seg_key, []):
                    if isinstance(seg, (list, tuple)) and len(seg) >= 2:
                        length = int(seg[1])
                        if length % 4 != 0:
                            result.errors.append(
                                f"Weight '{w_name}' {seg_key} segment length "
                                f"{length} not divisible by 4"
                            )


def check_measure_config(config_dir: Path) -> SchemaCheckResult:
    """Check measureConfig.json schema."""
    from ..core.schemas import validate_schema

    path = config_dir / "measureConfig.json"
    result = SchemaCheckResult(file_name="measureConfig.json", file_type="measure_config")

    if not path.exists():
        result.warnings.append("File not found (optional)")
        return result

    vr = validate_schema(path, "measure_config")
    result.valid = vr.valid
    result.version = vr.version
    result.errors = vr.errors
    result.warnings = vr.warnings

    return result


def check_devices(config_dir: Path) -> SchemaCheckResult:
    """Check devices.json schema."""
    from ..core.schemas import validate_schema

    path = config_dir / "devices.json"
    result = SchemaCheckResult(file_name="devices.json", file_type="devices")

    if not path.exists():
        result.warnings.append("File not found (optional)")
        return result

    vr = validate_schema(path, "devices")
    result.valid = vr.valid
    result.version = vr.version
    result.errors = vr.errors
    result.warnings = vr.warnings

    return result


# ---------------------------------------------------------------------------
# Pydantic model validation
# ---------------------------------------------------------------------------

def check_spec_models() -> SchemaCheckResult:
    """Validate that all Pydantic spec models instantiate correctly with defaults."""
    from ..pulses.spec_models import (
        PulseConstraints,
        ConstantParams,
        ZeroParams,
        DragGaussianParams,
        DragCosineParams,
        KaiserParams,
        SlepianParams,
        FlattopParams,
        CLEARParams,
        RotationDerivedParams,
        ArbitraryBlobParams,
        PulseSpecEntry,
        PulseSpecFile,
    )

    result = SchemaCheckResult(
        file_name="spec_models.py",
        file_type="pydantic_models",
    )

    # Test each model with minimal valid data
    try:
        PulseConstraints()
        ZeroParams()
        ConstantParams(length=16)
        DragGaussianParams(amplitude=0.1, length=16, sigma=2.0)
        DragCosineParams(amplitude=0.1, length=20)
        KaiserParams(amplitude=0.1, length=200, beta=4.0)
        SlepianParams(amplitude=0.1, length=200, NW=4.0)
        FlattopParams(amplitude=0.2, flat_length=200, rise_fall_length=20)
        CLEARParams(
            t_duration=400, t_kick=20,
            A_steady=0.2, A_rise_hi=0.4, A_rise_lo=0.1,
            A_fall_lo=-0.1, A_fall_hi=-0.4,
        )
        RotationDerivedParams(reference_spec="ref_r180")
        ArbitraryBlobParams()
        PulseSpecEntry(shape="constant", element="test", op="const")
        PulseSpecFile()

        result.valid = True
    except Exception as exc:
        result.valid = False
        result.errors.append(f"Model instantiation failed: {exc}")

    # Test shape validator rejects unknown shapes
    try:
        PulseSpecEntry(shape="nonexistent_shape", element="test", op="test")
        result.errors.append("Shape validator did not reject unknown shape")
        result.valid = False
    except Exception:
        pass  # Expected

    # Test length validator rejects < 4
    try:
        ConstantParams(length=2)
        result.errors.append("Length validator did not reject length < 4")
        result.valid = False
    except Exception:
        pass  # Expected

    return result


# ---------------------------------------------------------------------------
# Run all checks
# ---------------------------------------------------------------------------

def run_schema_checks(
    config_dir: str | Path | None = None,
) -> list[SchemaCheckResult]:
    """Run all schema validation checks.

    Parameters
    ----------
    config_dir : str | Path | None
        Path to config directory. If None, only model checks run.

    Returns
    -------
    list[SchemaCheckResult]
    """
    results: list[SchemaCheckResult] = []

    # Pydantic model checks (always run)
    results.append(check_spec_models())

    # File-based checks (only if config_dir provided)
    if config_dir is not None:
        config_dir = Path(config_dir)
        results.append(check_hardware(config_dir))
        results.append(check_calibration(config_dir))
        results.append(check_pulse_specs(config_dir))
        results.append(check_measure_config(config_dir))
        results.append(check_devices(config_dir))

    passed = sum(1 for r in results if r.valid)
    failed = sum(1 for r in results if not r.valid)
    _logger.info("Schema checks: %d passed, %d failed", passed, failed)

    return results


def print_report(results: list[SchemaCheckResult]) -> None:
    """Print a human-readable schema check report."""
    passed = [r for r in results if r.valid]
    failed = [r for r in results if not r.valid]

    print(f"\nSchema Validation Report")
    print(f"{'=' * 50}")
    print(f"Total: {len(results)}  Passed: {len(passed)}  Failed: {len(failed)}")
    print()

    if failed:
        print("FAILURES:")
        for r in failed:
            print(r)
        print()

    print("ALL RESULTS:")
    for r in results:
        print(r)
        if r.warnings:
            for w in r.warnings:
                print(f"    WARN: {w}")
