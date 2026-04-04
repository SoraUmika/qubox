"""Waveform generation determinism and regression tests.

Tests that PulseFactory produces deterministic, correct waveforms for all
supported pulse shapes. This module can be run standalone or imported into
a pytest suite.

See docs/VERIFICATION_STRATEGY.md for the full specification.

Usage
-----
>>> from qubox.verification.waveform_regression import run_all_checks
>>> results = run_all_checks()
>>> assert all(r.passed for r in results)
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Test result
# ---------------------------------------------------------------------------

@dataclass
class ShapeTestResult:
    """Result of a single shape test."""
    shape: str
    test_name: str
    passed: bool = True
    error: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        msg = f"  {status} [{self.shape}] {self.test_name}"
        if self.error:
            msg += f" — {self.error}"
        return msg


# ---------------------------------------------------------------------------
# Individual shape tests
# ---------------------------------------------------------------------------

def test_constant_shape() -> list[ShapeTestResult]:
    """Test constant pulse generation."""
    from ..pulses.factory import _handle_constant

    results = []

    # Basic constant
    I, Q = _handle_constant({"amplitude_I": 0.2, "amplitude_Q": 0.1, "length": 100})
    r = ShapeTestResult(shape="constant", test_name="basic_constant")
    if len(I) != 100 or len(Q) != 100:
        r.passed = False
        r.error = f"Expected length 100, got I={len(I)}, Q={len(Q)}"
    elif not all(abs(v - 0.2) < 1e-15 for v in I):
        r.passed = False
        r.error = "I samples not all 0.2"
    elif not all(abs(v - 0.1) < 1e-15 for v in Q):
        r.passed = False
        r.error = "Q samples not all 0.1"
    results.append(r)

    # Zero-amplitude constant
    I, Q = _handle_constant({"amplitude_I": 0.0, "amplitude_Q": 0.0, "length": 16})
    r = ShapeTestResult(shape="constant", test_name="zero_amplitude_constant")
    if not all(v == 0.0 for v in I + Q):
        r.passed = False
        r.error = "Non-zero samples in zero-amplitude constant"
    results.append(r)

    return results


def test_zero_shape() -> list[ShapeTestResult]:
    """Test zero pulse generation."""
    from ..pulses.factory import _handle_zero

    results = []

    I, Q = _handle_zero({"length": 32})
    r = ShapeTestResult(shape="zero", test_name="basic_zero")
    if len(I) != 32 or len(Q) != 32:
        r.passed = False
        r.error = f"Expected length 32, got I={len(I)}, Q={len(Q)}"
    elif not all(v == 0.0 for v in I + Q):
        r.passed = False
        r.error = "Non-zero samples in zero pulse"
    results.append(r)

    # Default length
    I, Q = _handle_zero({})
    r = ShapeTestResult(shape="zero", test_name="default_length_zero")
    if len(I) != 16:
        r.passed = False
        r.error = f"Default length should be 16, got {len(I)}"
    results.append(r)

    return results


def test_drag_gaussian_shape() -> list[ShapeTestResult]:
    """Test DRAG Gaussian pulse generation."""
    from ..pulses.factory import _handle_drag_gaussian

    results = []

    # Basic DRAG Gaussian (no DRAG correction)
    params = {
        "amplitude": 0.1,
        "length": 16,
        "sigma": 2.6667,
        "drag_coeff": 0.0,
        "anharmonicity": 255750000.0,
        "detuning": 0.0,
        "subtracted": True,
    }
    I, Q = _handle_drag_gaussian(params)

    r = ShapeTestResult(shape="drag_gaussian", test_name="no_drag_correction")
    if len(I) != 16:
        r.passed = False
        r.error = f"Expected length 16, got {len(I)}"
    elif any(v != 0.0 for v in Q):
        r.passed = False
        r.error = "Q should be all-zero when drag_coeff=0"
    results.append(r)

    # Symmetry check: subtracted Gaussian first and last should be ~0
    r = ShapeTestResult(shape="drag_gaussian", test_name="subtracted_endpoints")
    if abs(I[0]) > 1e-10 or abs(I[-1]) > 1e-10:
        r.passed = False
        r.error = f"Subtracted Gaussian endpoints not zero: I[0]={I[0]:.2e}, I[-1]={I[-1]:.2e}"
    results.append(r)

    # With DRAG correction
    params_drag = {**params, "drag_coeff": 0.5}
    I_d, Q_d = _handle_drag_gaussian(params_drag)

    r = ShapeTestResult(shape="drag_gaussian", test_name="with_drag_correction")
    if all(v == 0.0 for v in Q_d):
        r.passed = False
        r.error = "Q should be non-zero when drag_coeff != 0"
    results.append(r)

    # Determinism: two calls with same params produce identical output
    I2, Q2 = _handle_drag_gaussian(params_drag)
    r = ShapeTestResult(shape="drag_gaussian", test_name="determinism")
    if I_d != I2 or Q_d != Q2:
        r.passed = False
        r.error = "Two calls with same params produced different output"
    results.append(r)

    return results


def test_drag_cosine_shape() -> list[ShapeTestResult]:
    """Test DRAG cosine pulse generation."""
    from ..pulses.factory import _handle_drag_cosine

    results = []

    params = {
        "amplitude": 0.1,
        "length": 20,
        "alpha": 0.0,
        "anharmonicity": 255750000.0,
        "detuning": 0.0,
    }
    I, Q = _handle_drag_cosine(params)

    r = ShapeTestResult(shape="drag_cosine", test_name="basic_cosine")
    if len(I) != 20:
        r.passed = False
        r.error = f"Expected length 20, got {len(I)}"
    results.append(r)

    # Cosine envelope should be zero at endpoints
    r = ShapeTestResult(shape="drag_cosine", test_name="cosine_endpoints")
    if abs(I[0]) > 1e-10 or abs(I[-1]) > 1e-10:
        r.passed = False
        r.error = f"Cosine endpoints not zero: I[0]={I[0]:.2e}, I[-1]={I[-1]:.2e}"
    results.append(r)

    return results


def test_kaiser_shape() -> list[ShapeTestResult]:
    """Test Kaiser window pulse generation."""
    from ..pulses.factory import _handle_kaiser

    results = []

    params = {
        "amplitude": 0.1,
        "length": 200,
        "beta": 4.0,
        "detuning": 0.0,
        "alpha": 0.0,
        "anharmonicity": 0.0,
    }
    I, Q = _handle_kaiser(params)

    r = ShapeTestResult(shape="kaiser", test_name="basic_kaiser")
    if len(I) != 200:
        r.passed = False
        r.error = f"Expected length 200, got {len(I)}"
    results.append(r)

    # Kaiser peak should be near amplitude
    r = ShapeTestResult(shape="kaiser", test_name="kaiser_peak")
    peak = max(abs(v) for v in I)
    if abs(peak - 0.1) > 0.02:
        r.passed = False
        r.error = f"Peak amplitude {peak:.4f} not near expected 0.1"
    results.append(r)

    return results


def test_slepian_shape() -> list[ShapeTestResult]:
    """Test Slepian window pulse generation."""
    from ..pulses.factory import _handle_slepian

    results = []

    params = {
        "amplitude": 0.1,
        "length": 200,
        "NW": 4.0,
        "detuning": 0.0,
        "alpha": 0.0,
        "anharmonicity": 0.0,
    }
    I, Q = _handle_slepian(params)

    r = ShapeTestResult(shape="slepian", test_name="basic_slepian")
    if len(I) != 200:
        r.passed = False
        r.error = f"Expected length 200, got {len(I)}"
    results.append(r)

    return results


def test_flattop_shapes() -> list[ShapeTestResult]:
    """Test all flat-top pulse shapes."""
    from ..pulses.factory import (
        _handle_flattop_gaussian,
        _handle_flattop_cosine,
        _handle_flattop_tanh,
        _handle_flattop_blackman,
    )

    results = []
    params = {
        "amplitude": 0.2,
        "flat_length": 200,
        "rise_fall_length": 20,
    }

    for name, handler in [
        ("flattop_gaussian", _handle_flattop_gaussian),
        ("flattop_cosine", _handle_flattop_cosine),
        ("flattop_tanh", _handle_flattop_tanh),
        ("flattop_blackman", _handle_flattop_blackman),
    ]:
        I, Q = handler(params)
        expected_len = 200 + 2 * 20  # flat + rise + fall

        r = ShapeTestResult(shape=name, test_name="basic_flattop")
        # Length check (may vary by shape; check it's roughly right)
        if abs(len(I) - expected_len) > 4:
            r.passed = False
            r.error = f"Expected ~{expected_len}, got {len(I)}"
        results.append(r)

        # Q should be all zeros for flat-top (I-only envelope)
        r = ShapeTestResult(shape=name, test_name="q_channel_zero")
        if any(v != 0.0 for v in Q):
            r.passed = False
            r.error = "Q channel should be all-zero for flattop shapes"
        results.append(r)

        # Flat region should be near amplitude
        r = ShapeTestResult(shape=name, test_name="flat_region_amplitude")
        mid_start = len(I) // 2 - 10
        mid_end = len(I) // 2 + 10
        flat_region = I[mid_start:mid_end]
        if flat_region and abs(max(flat_region) - 0.2) > 0.01:
            r.passed = False
            r.error = f"Flat region amplitude {max(flat_region):.4f} not near 0.2"
        results.append(r)

    return results


def test_constraints() -> list[ShapeTestResult]:
    """Test post-generation constraint application."""
    from ..pulses.factory import _apply_constraints

    results = []

    # Clipping
    I_big = [0.5, 0.6, 0.7, 0.5]
    Q_zero = [0.0, 0.0, 0.0, 0.0]
    I_clip, Q_clip = _apply_constraints(I_big, Q_zero, {"max_amplitude": 0.45, "clip": True})

    r = ShapeTestResult(shape="constraints", test_name="clipping")
    peak = max(abs(v) for v in I_clip)
    if peak > 0.45 + 1e-10:
        r.passed = False
        r.error = f"Clipping failed: peak={peak:.4f} > 0.45"
    results.append(r)

    # Padding
    I_odd = [0.1, 0.2, 0.3, 0.4, 0.5]
    Q_odd = [0.0] * 5
    I_pad, Q_pad = _apply_constraints(I_odd, Q_odd, {"pad_to_multiple_of": 4})

    r = ShapeTestResult(shape="constraints", test_name="padding")
    if len(I_pad) % 4 != 0:
        r.passed = False
        r.error = f"Padding failed: length={len(I_pad)} not multiple of 4"
    results.append(r)

    # No constraints (pass-through)
    I_orig = [0.1, 0.2]
    Q_orig = [0.3, 0.4]
    I_out, Q_out = _apply_constraints(I_orig, Q_orig, None)

    r = ShapeTestResult(shape="constraints", test_name="no_constraints_passthrough")
    if I_out != I_orig or Q_out != Q_orig:
        r.passed = False
        r.error = "No-constraints should pass through unchanged"
    results.append(r)

    return results


def test_rotation_derived() -> list[ShapeTestResult]:
    """Test rotation_derived pulse compilation."""
    from ..pulses.factory import PulseFactory

    results = []

    # Create a minimal specs data with a reference and derived pulse
    specs_data = {
        "schema_version": 1,
        "specs": {
            "ref_r180": {
                "shape": "drag_gaussian",
                "element": "qubit",
                "op": "ref_r180",
                "params": {
                    "amplitude": 0.11165,
                    "length": 16,
                    "sigma": 2.6667,
                    "drag_coeff": 0.0,
                    "anharmonicity": 255750000.0,
                    "detuning": 0.0,
                    "subtracted": True,
                },
            },
            "x180": {
                "shape": "rotation_derived",
                "element": "qubit",
                "op": "x180",
                "params": {
                    "reference_spec": "ref_r180",
                    "theta": math.pi,
                    "phi": 0.0,
                },
            },
            "x90": {
                "shape": "rotation_derived",
                "element": "qubit",
                "op": "x90",
                "params": {
                    "reference_spec": "ref_r180",
                    "theta": math.pi / 2,
                    "phi": 0.0,
                },
            },
            "y180": {
                "shape": "rotation_derived",
                "element": "qubit",
                "op": "y180",
                "params": {
                    "reference_spec": "ref_r180",
                    "theta": math.pi,
                    "phi": math.pi / 2,
                },
            },
        },
        "integration_weights": {},
        "element_operations": {},
    }

    factory = PulseFactory(specs_data)

    # x180 should match ref_r180 (theta=pi, phi=0, so amp_scale≈1)
    try:
        I_ref, Q_ref, _ = factory.compile_one("ref_r180")
        I_x180, Q_x180, _ = factory.compile_one("x180")

        r = ShapeTestResult(shape="rotation_derived", test_name="x180_matches_ref")
        # x180 with theta=pi should be very close to ref
        diff = np.max(np.abs(np.array(I_x180) - np.array(I_ref)))
        if diff > 1e-8:
            r.passed = False
            r.error = f"x180 I differs from ref by {diff:.2e}"
        results.append(r)

    except Exception as exc:
        r = ShapeTestResult(shape="rotation_derived", test_name="x180_matches_ref",
                            passed=False, error=str(exc))
        results.append(r)

    # x90 should have half the amplitude of x180
    try:
        I_x90, Q_x90, _ = factory.compile_one("x90")

        r = ShapeTestResult(shape="rotation_derived", test_name="x90_half_amplitude")
        ratio = np.max(np.abs(np.array(I_x90))) / np.max(np.abs(np.array(I_x180)))
        if abs(ratio - 0.5) > 0.05:
            r.passed = False
            r.error = f"x90/x180 peak ratio = {ratio:.4f}, expected ~0.5"
        results.append(r)

    except Exception as exc:
        r = ShapeTestResult(shape="rotation_derived", test_name="x90_half_amplitude",
                            passed=False, error=str(exc))
        results.append(r)

    # y180 should have Q component (rotated by pi/2)
    try:
        I_y180, Q_y180, _ = factory.compile_one("y180")

        r = ShapeTestResult(shape="rotation_derived", test_name="y180_has_q_component")
        q_peak = np.max(np.abs(np.array(Q_y180)))
        if q_peak < 1e-6:
            r.passed = False
            r.error = f"y180 Q peak = {q_peak:.2e}, expected nonzero"
        results.append(r)

    except Exception as exc:
        r = ShapeTestResult(shape="rotation_derived", test_name="y180_has_q_component",
                            passed=False, error=str(exc))
        results.append(r)

    return results


# ---------------------------------------------------------------------------
# Run all checks
# ---------------------------------------------------------------------------

def run_all_checks() -> list[ShapeTestResult]:
    """Run all waveform regression checks.

    Returns
    -------
    list[ShapeTestResult]
        All test results.
    """
    all_results: list[ShapeTestResult] = []

    test_funcs = [
        test_constant_shape,
        test_zero_shape,
        test_drag_gaussian_shape,
        test_drag_cosine_shape,
        test_kaiser_shape,
        test_slepian_shape,
        test_flattop_shapes,
        test_constraints,
        test_rotation_derived,
    ]

    for func in test_funcs:
        try:
            results = func()
            all_results.extend(results)
        except Exception as exc:
            all_results.append(ShapeTestResult(
                shape=func.__name__,
                test_name="execution",
                passed=False,
                error=f"Test function raised: {exc}",
            ))

    passed = sum(1 for r in all_results if r.passed)
    failed = sum(1 for r in all_results if not r.passed)
    _logger.info(
        "Waveform regression: %d passed, %d failed (%d total)",
        passed, failed, len(all_results),
    )

    return all_results


def print_report(results: list[ShapeTestResult]) -> None:
    """Print a human-readable report of all test results."""
    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]

    print(f"\nWaveform Regression Report")
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
