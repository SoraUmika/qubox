# qubox_v2/verification/legacy_parity.py
"""Legacy parity harness — compare qubox_v2 waveform generation against legacy.

This module provides automated regression checks ensuring that PulseFactory
(declarative path) produces waveforms bit-identical to the legacy
PulseOperationManager path for identical parameters.

See docs/VERIFICATION_STRATEGY.md for the full specification.

Usage
-----
>>> from qubox_v2.verification.legacy_parity import run_parity_check
>>> report = run_parity_check(config_dir="seq_1_device/config")
>>> print(report.summary())
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Comparison metrics
# ---------------------------------------------------------------------------

@dataclass
class WaveformComparison:
    """Comparison metrics between two waveforms."""
    spec_name: str
    l2_norm: float = 0.0
    normalized_dot_product: float = 1.0
    peak_amplitude_diff: float = 0.0
    area_diff: float = 0.0
    length_match: bool = True
    passed: bool = True
    details: str = ""

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (
            f"  {status} {self.spec_name}: "
            f"L2={self.l2_norm:.2e}, "
            f"dot={self.normalized_dot_product:.6f}, "
            f"peak_diff={self.peak_amplitude_diff:.2e}, "
            f"area_diff={self.area_diff:.2e}"
        )


@dataclass
class ParityReport:
    """Full parity check report."""
    passed: bool = True
    comparisons: list[WaveformComparison] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    legacy_pulse_count: int = 0
    v2_pulse_count: int = 0

    def summary(self) -> str:
        status = "PASSED" if self.passed else "FAILED"
        lines = [
            f"Legacy Parity Check: {status}",
            f"  Legacy pulses: {self.legacy_pulse_count}",
            f"  V2 pulses:     {self.v2_pulse_count}",
            f"  Compared:      {len(self.comparisons)}",
            f"  Skipped:       {len(self.skipped)}",
            f"  Errors:        {len(self.errors)}",
            "",
        ]

        failures = [c for c in self.comparisons if not c.passed]
        passes = [c for c in self.comparisons if c.passed]

        if failures:
            lines.append(f"FAILURES ({len(failures)}):")
            for c in failures:
                lines.append(str(c))
                if c.details:
                    lines.append(f"    Detail: {c.details}")
            lines.append("")

        if passes:
            lines.append(f"Passes ({len(passes)}):")
            for c in passes:
                lines.append(str(c))

        if self.skipped:
            lines.append("")
            lines.append(f"Skipped ({len(self.skipped)}):")
            for s in self.skipped:
                lines.append(f"  - {s}")

        if self.errors:
            lines.append("")
            lines.append(f"Errors ({len(self.errors)}):")
            for e in self.errors:
                lines.append(f"  - {e}")

        return "\n".join(lines)

    def to_markdown(self) -> str:
        """Generate a Markdown report suitable for artifact storage."""
        status = "PASSED" if self.passed else "FAILED"
        lines = [
            f"# Legacy Parity Report: {status}",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Legacy pulses | {self.legacy_pulse_count} |",
            f"| V2 pulses | {self.v2_pulse_count} |",
            f"| Compared | {len(self.comparisons)} |",
            f"| Passed | {len([c for c in self.comparisons if c.passed])} |",
            f"| Failed | {len([c for c in self.comparisons if not c.passed])} |",
            f"| Skipped | {len(self.skipped)} |",
            "",
        ]

        if self.comparisons:
            lines.extend([
                "## Comparison Details",
                "",
                "| Spec | Status | L2 Norm | Dot Product | Peak Diff | Area Diff |",
                "|------|--------|---------|-------------|-----------|-----------|",
            ])
            for c in self.comparisons:
                s = "PASS" if c.passed else "FAIL"
                lines.append(
                    f"| {c.spec_name} | {s} | {c.l2_norm:.2e} | "
                    f"{c.normalized_dot_product:.6f} | "
                    f"{c.peak_amplitude_diff:.2e} | {c.area_diff:.2e} |"
                )

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pass thresholds
# ---------------------------------------------------------------------------

L2_THRESHOLD = 1e-10
DOT_PRODUCT_THRESHOLD = 0.999999
PEAK_DIFF_THRESHOLD = 1e-10
AREA_DIFF_THRESHOLD = 1e-10


# ---------------------------------------------------------------------------
# Core comparison
# ---------------------------------------------------------------------------

def compare_waveforms(
    name: str,
    I_legacy: np.ndarray,
    Q_legacy: np.ndarray,
    I_v2: np.ndarray,
    Q_v2: np.ndarray,
) -> WaveformComparison:
    """Compare two complex waveforms and return metrics.

    Parameters
    ----------
    name : str
        Identifier for this comparison.
    I_legacy, Q_legacy : ndarray
        Legacy I/Q waveform arrays.
    I_v2, Q_v2 : ndarray
        V2 I/Q waveform arrays.

    Returns
    -------
    WaveformComparison
    """
    I_leg = np.asarray(I_legacy, dtype=np.float64)
    Q_leg = np.asarray(Q_legacy, dtype=np.float64)
    I_new = np.asarray(I_v2, dtype=np.float64)
    Q_new = np.asarray(Q_v2, dtype=np.float64)

    # Length check
    length_match = (len(I_leg) == len(I_new)) and (len(Q_leg) == len(Q_new))
    if not length_match:
        return WaveformComparison(
            spec_name=name,
            length_match=False,
            passed=False,
            details=f"Length mismatch: legacy={len(I_leg)}, v2={len(I_new)}",
        )

    w_leg = I_leg + 1j * Q_leg
    w_new = I_new + 1j * Q_new

    diff = w_new - w_leg

    # L2 norm
    l2 = float(np.sqrt(np.sum(np.abs(diff) ** 2)))

    # Normalized dot product
    norm_leg = np.sqrt(np.sum(np.abs(w_leg) ** 2))
    norm_new = np.sqrt(np.sum(np.abs(w_new) ** 2))
    if norm_leg > 0 and norm_new > 0:
        dot = float(np.abs(np.sum(w_new * np.conj(w_leg))) / (norm_leg * norm_new))
    else:
        dot = 1.0 if (norm_leg == 0 and norm_new == 0) else 0.0

    # Peak amplitude difference
    peak_diff = float(np.max(np.abs(diff)))

    # Area difference
    area_leg = float(np.sum(np.abs(w_leg)))
    area_new = float(np.sum(np.abs(w_new)))
    area_diff = abs(area_new - area_leg)

    # Pass/fail
    passed = (
        l2 < L2_THRESHOLD
        and dot > DOT_PRODUCT_THRESHOLD
        and peak_diff < PEAK_DIFF_THRESHOLD
        and area_diff < AREA_DIFF_THRESHOLD
    )

    details = ""
    if not passed:
        failures = []
        if l2 >= L2_THRESHOLD:
            failures.append(f"L2={l2:.2e} >= {L2_THRESHOLD}")
        if dot <= DOT_PRODUCT_THRESHOLD:
            failures.append(f"dot={dot:.6f} <= {DOT_PRODUCT_THRESHOLD}")
        if peak_diff >= PEAK_DIFF_THRESHOLD:
            failures.append(f"peak={peak_diff:.2e} >= {PEAK_DIFF_THRESHOLD}")
        if area_diff >= AREA_DIFF_THRESHOLD:
            failures.append(f"area={area_diff:.2e} >= {AREA_DIFF_THRESHOLD}")
        details = "; ".join(failures)

    return WaveformComparison(
        spec_name=name,
        l2_norm=l2,
        normalized_dot_product=dot,
        peak_amplitude_diff=peak_diff,
        area_diff=area_diff,
        length_match=True,
        passed=passed,
        details=details,
    )


# ---------------------------------------------------------------------------
# Legacy waveform extraction
# ---------------------------------------------------------------------------

def extract_legacy_waveforms(pulses_json_path: str | Path) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Extract I/Q waveform arrays from a legacy pulses.json file.

    Parameters
    ----------
    pulses_json_path : str | Path
        Path to the legacy ``pulses.json``.

    Returns
    -------
    dict[str, tuple[ndarray, ndarray]]
        Mapping from pulse name to (I_wf, Q_wf) arrays.
    """
    path = Path(pulses_json_path)
    data = json.loads(path.read_bytes())

    waveforms: dict[str, tuple[np.ndarray, np.ndarray]] = {}

    # pulses.json has a "waveforms" section and a "pulses" section.
    # Waveforms are referenced by name from pulse definitions.
    wf_defs = data.get("waveforms", {})
    pulse_defs = data.get("pulses", {})

    for pulse_name, pulse_data in pulse_defs.items():
        wf_dict = pulse_data.get("waveforms", {})
        I_ref = wf_dict.get("I")
        Q_ref = wf_dict.get("Q")

        I_wf = _resolve_waveform(I_ref, wf_defs)
        Q_wf = _resolve_waveform(Q_ref, wf_defs)

        if I_wf is not None and Q_wf is not None:
            waveforms[pulse_name] = (I_wf, Q_wf)

    return waveforms


def _resolve_waveform(ref: str | None, wf_defs: dict) -> np.ndarray | None:
    """Resolve a waveform reference name to an array."""
    if ref is None:
        return None

    wf_data = wf_defs.get(ref)
    if wf_data is None:
        return None

    wf_type = wf_data.get("type", "arbitrary")

    if wf_type == "constant":
        sample = float(wf_data.get("sample", 0.0))
        # Constant waveforms don't have explicit length in the waveform def.
        # They're expanded to match the pulse length. Return a 1-sample marker.
        return np.array([sample])

    if wf_type == "arbitrary":
        samples = wf_data.get("samples", [])
        return np.array(samples, dtype=np.float64)

    return None


# ---------------------------------------------------------------------------
# Full parity check
# ---------------------------------------------------------------------------

def run_parity_check(
    config_dir: str | Path,
    *,
    pulse_specs_data: dict | None = None,
) -> ParityReport:
    """Run full parity check between legacy pulses.json and PulseFactory output.

    Parameters
    ----------
    config_dir : str | Path
        Path to the config directory containing both ``pulses.json`` and
        ``pulse_specs.json``.
    pulse_specs_data : dict, optional
        Pre-loaded pulse_specs data. If None, reads from disk.

    Returns
    -------
    ParityReport
    """
    config_dir = Path(config_dir)
    report = ParityReport()

    # Load legacy waveforms
    pulses_path = config_dir / "pulses.json"
    if not pulses_path.exists():
        report.errors.append(f"Legacy pulses.json not found: {pulses_path}")
        report.passed = False
        return report

    try:
        legacy_wfs = extract_legacy_waveforms(pulses_path)
        report.legacy_pulse_count = len(legacy_wfs)
    except Exception as exc:
        report.errors.append(f"Failed to extract legacy waveforms: {exc}")
        report.passed = False
        return report

    # Load pulse specs
    if pulse_specs_data is None:
        ps_path = config_dir / "pulse_specs.json"
        if not ps_path.exists():
            report.errors.append(f"pulse_specs.json not found: {ps_path}")
            report.passed = False
            return report
        pulse_specs_data = json.loads(ps_path.read_bytes())

    # Compile via PulseFactory
    try:
        from ..pulses.factory import PulseFactory
        factory = PulseFactory(pulse_specs_data)
        compiled = factory.compile_all()
        report.v2_pulse_count = len(compiled)
    except Exception as exc:
        report.errors.append(f"PulseFactory compile_all failed: {exc}")
        report.passed = False
        return report

    # Compare matching pulses
    for spec_name, (I_v2, Q_v2, meta) in compiled.items():
        # Try to match against legacy pulse name
        element = meta.get("element", "")
        op = meta.get("op", "")
        legacy_key = _find_legacy_match(spec_name, element, op, legacy_wfs)

        if legacy_key is None:
            report.skipped.append(f"{spec_name} (no matching legacy pulse)")
            continue

        I_leg, Q_leg = legacy_wfs[legacy_key]

        # Constant waveforms in legacy are single-sample markers
        if len(I_leg) == 1 and len(I_v2) > 1:
            # Expand constant to match v2 length
            I_leg = np.full(len(I_v2), I_leg[0])
            Q_leg = np.full(len(Q_v2), Q_leg[0])

        comparison = compare_waveforms(
            spec_name,
            I_leg, Q_leg,
            np.array(I_v2), np.array(Q_v2),
        )
        report.comparisons.append(comparison)

        if not comparison.passed:
            report.passed = False

    return report


def _find_legacy_match(
    spec_name: str,
    element: str,
    op: str,
    legacy_wfs: dict,
) -> str | None:
    """Find the best matching legacy pulse name for a v2 spec.

    Tries several naming conventions used in legacy pulses.json.
    """
    # Direct name match
    if spec_name in legacy_wfs:
        return spec_name

    # element_op pattern (e.g. "qubit_x180")
    candidate = f"{element}_{op}"
    if candidate in legacy_wfs:
        return candidate

    # op_element pattern
    candidate = f"{op}_{element}"
    if candidate in legacy_wfs:
        return candidate

    # Just op name
    if op in legacy_wfs:
        return op

    # Fuzzy: check if spec_name is a substring of any legacy key
    for key in legacy_wfs:
        if spec_name in key or key in spec_name:
            return key

    return None


# ---------------------------------------------------------------------------
# Golden reference generation
# ---------------------------------------------------------------------------

def generate_golden_references(
    config_dir: str | Path,
    output_path: str | Path,
) -> Path:
    """Generate golden reference waveforms from current PulseFactory output.

    Stores as a .npz file for future regression checks.

    Parameters
    ----------
    config_dir : str | Path
        Path to config directory with pulse_specs.json.
    output_path : str | Path
        Where to save the .npz file.

    Returns
    -------
    Path
        Path to the generated golden reference file.
    """
    config_dir = Path(config_dir)
    output_path = Path(output_path)

    ps_path = config_dir / "pulse_specs.json"
    data = json.loads(ps_path.read_bytes())

    from ..pulses.factory import PulseFactory
    factory = PulseFactory(data)
    compiled = factory.compile_all()

    arrays = {}
    for name, (I_wf, Q_wf, meta) in compiled.items():
        safe_name = name.replace(".", "_").replace("/", "_")
        arrays[f"{safe_name}_I"] = np.array(I_wf, dtype=np.float64)
        arrays[f"{safe_name}_Q"] = np.array(Q_wf, dtype=np.float64)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(str(output_path), **arrays)
    _logger.info("Golden references saved: %s (%d pulses)", output_path, len(compiled))
    return output_path


def check_against_golden(
    config_dir: str | Path,
    golden_path: str | Path,
) -> ParityReport:
    """Compare current PulseFactory output against golden references.

    Parameters
    ----------
    config_dir : str | Path
        Path to config directory.
    golden_path : str | Path
        Path to golden reference .npz file.

    Returns
    -------
    ParityReport
    """
    config_dir = Path(config_dir)
    golden_path = Path(golden_path)

    report = ParityReport()

    golden = np.load(str(golden_path))
    ps_path = config_dir / "pulse_specs.json"
    data = json.loads(ps_path.read_bytes())

    from ..pulses.factory import PulseFactory
    factory = PulseFactory(data)
    compiled = factory.compile_all()
    report.v2_pulse_count = len(compiled)

    # Count golden pulse pairs
    golden_names = set()
    for key in golden.files:
        if key.endswith("_I"):
            golden_names.add(key[:-2])
    report.legacy_pulse_count = len(golden_names)

    for name, (I_v2, Q_v2, meta) in compiled.items():
        safe_name = name.replace(".", "_").replace("/", "_")
        I_key = f"{safe_name}_I"
        Q_key = f"{safe_name}_Q"

        if I_key not in golden.files or Q_key not in golden.files:
            report.skipped.append(f"{name} (not in golden reference)")
            continue

        I_golden = golden[I_key]
        Q_golden = golden[Q_key]

        comparison = compare_waveforms(
            name,
            I_golden, Q_golden,
            np.array(I_v2), np.array(Q_v2),
        )
        report.comparisons.append(comparison)

        if not comparison.passed:
            report.passed = False

    return report
