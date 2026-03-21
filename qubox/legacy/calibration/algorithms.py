# qubox_v2/calibration/algorithms.py
"""Calibration analysis algorithms — backward-compatibility re-exports.

Canonical implementations have moved to
``qubox_v2.analysis.calibration_algorithms``.  This module re-exports
everything so existing ``from qubox_v2.calibration.algorithms import …``
statements continue to work.
"""
from __future__ import annotations

from ..analysis.calibration_algorithms import (  # noqa: F401
    apply_affine_correction,
    compute_corrected_knobs,
    fit_chi_ramsey,
    fit_fock_sqr,
    fit_multi_alpha_affine,
    fit_number_splitting,
    fit_pulse_train,
    optimize_fock_sqr_iterative,
    optimize_fock_sqr_spsa,
)

__all__ = [
    "apply_affine_correction",
    "compute_corrected_knobs",
    "fit_chi_ramsey",
    "fit_fock_sqr",
    "fit_multi_alpha_affine",
    "fit_number_splitting",
    "fit_pulse_train",
    "optimize_fock_sqr_iterative",
    "optimize_fock_sqr_spsa",
]
