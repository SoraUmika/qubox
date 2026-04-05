"""Calibration analysis algorithms — backward-compatibility re-exports.

Canonical implementations have moved to
``qubox_tools.fitting.calibration``.  This module re-exports
everything so existing ``from qubox.calibration.algorithms import …``
statements continue to work.
"""
from __future__ import annotations

from qubox_tools.fitting.calibration import (  # noqa: F401
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
