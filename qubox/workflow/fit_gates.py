"""Fit quality gate helpers.

Reusable fit-quality checks for experiment analysis results.
No notebook dependency.
"""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np


def fit_quality_gate(analysis: Any, *, r_squared_min: float = 0.5) -> tuple[bool, str]:
    """Check whether a fit result meets quality thresholds.

    Parameters
    ----------
    analysis:
        An analysis result object with an optional ``.fit`` attribute carrying
        ``params``, ``success``, and ``r_squared``.
    r_squared_min:
        Minimum acceptable R² value.

    Returns
    -------
    (passed, reason) tuple.
    """
    fit = getattr(analysis, "fit", None)
    if fit is None or not getattr(fit, "params", None):
        return False, "fit produced no parameters"
    if getattr(fit, "success", True) is False:
        return False, "fit reported failure"
    r_squared = getattr(fit, "r_squared", np.nan)
    if np.isfinite(r_squared) and r_squared < r_squared_min:
        return False, f"fit r_squared below threshold: {r_squared:.3f} < {r_squared_min:.3f}"
    return True, "fit quality passed"


def fit_center_inside_window(
    fitted_value_hz: float,
    frequencies_hz: Iterable[float],
    *,
    margin_points: int = 2,
) -> tuple[bool, str]:
    """Check whether a fitted center frequency lies inside the scan window.

    Parameters
    ----------
    fitted_value_hz:
        The fitted center frequency in Hz.
    frequencies_hz:
        The frequency sweep points used.
    margin_points:
        Number of edge points considered as guard band.

    Returns
    -------
    (passed, reason) tuple.
    """
    frequencies = np.asarray(list(frequencies_hz), dtype=float)
    if frequencies.size == 0 or not np.isfinite(fitted_value_hz):
        return False, "fit produced no finite center frequency"
    left_guard = frequencies[min(margin_points, frequencies.size - 1)]
    right_guard = frequencies[max(0, frequencies.size - 1 - margin_points)]
    if fitted_value_hz <= left_guard:
        return False, f"fit center is pinned near the low-frequency edge ({fitted_value_hz / 1e6:.3f} MHz)"
    if fitted_value_hz >= right_guard:
        return False, f"fit center is pinned near the high-frequency edge ({fitted_value_hz / 1e6:.3f} MHz)"
    return True, "fit center lies safely inside the scan window"


__all__ = ["fit_center_inside_window", "fit_quality_gate"]
