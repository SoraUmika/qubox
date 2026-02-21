# qubox_v2/pulses/waveforms.py
"""Waveform factory functions for creating QM-compatible waveform samples.

This module provides pure functions for generating waveform envelopes.
All functions return plain Python lists (or scalars) ready for the QM config.

For DRAG and kaiser waveforms, this wraps qualang_tools but normalizes output.
"""
from __future__ import annotations

from typing import Union

import numpy as np

from ..core.types import MAX_AMPLITUDE, WaveformSamples


def constant(amplitude: float) -> float:
    """Create a constant waveform (scalar).

    Parameters
    ----------
    amplitude : float
        Constant amplitude in volts. Must satisfy |amplitude| <= MAX_AMPLITUDE.

    Raises
    ------
    ValueError
        If amplitude exceeds MAX_AMPLITUDE.
    """
    if abs(amplitude) > MAX_AMPLITUDE:
        raise ValueError(
            f"Amplitude {amplitude} exceeds MAX_AMPLITUDE ({MAX_AMPLITUDE})."
        )
    return float(amplitude)


def square(amplitude: float, length: int) -> list[float]:
    """Create a square (flat-top) waveform.

    Parameters
    ----------
    amplitude : float
        Amplitude in volts.
    length : int
        Number of samples (must be >= 4 and divisible by 4).
    """
    if abs(amplitude) > MAX_AMPLITUDE:
        raise ValueError(
            f"Amplitude {amplitude} exceeds MAX_AMPLITUDE ({MAX_AMPLITUDE})."
        )
    return [float(amplitude)] * length


def gaussian(amplitude: float, length: int, sigma: float) -> list[float]:
    """Create a Gaussian envelope waveform.

    Parameters
    ----------
    amplitude : float
        Peak amplitude in volts.
    length : int
        Number of samples.
    sigma : float
        Standard deviation in samples.
    """
    t = np.arange(length) - (length - 1) / 2.0
    gauss = amplitude * np.exp(-0.5 * (t / sigma) ** 2)
    samples = gauss.tolist()
    _check_amplitude(samples, "gaussian")
    return samples


def drag_gaussian(
    amplitude: float,
    length: int,
    sigma: float,
    alpha: float,
    anharmonicity: float,
    detuning: float = 0.0,
) -> tuple[list[float], list[float]]:
    """Create DRAG-compensated Gaussian I/Q waveforms.

    Parameters
    ----------
    amplitude : float
        Peak amplitude.
    length : int
        Number of samples.
    sigma : float
        Gaussian standard deviation in samples.
    alpha : float
        DRAG coefficient.
    anharmonicity : float
        Qubit anharmonicity in Hz.
    detuning : float
        Detuning from qubit frequency in Hz.

    Returns
    -------
    I_wf, Q_wf : tuple[list[float], list[float]]
        In-phase and quadrature waveform samples.
    """
    try:
        from qualang_tools.config.waveform_tools import drag_gaussian_pulse_waveforms
        I_wf, Q_wf = drag_gaussian_pulse_waveforms(
            amplitude, length, sigma, alpha, anharmonicity, detuning
        )
        I_wf = [float(x) for x in I_wf]
        Q_wf = [float(x) for x in Q_wf]
    except ImportError:
        # Fallback: compute DRAG manually
        t = np.arange(length) - (length - 1) / 2.0
        gauss = amplitude * np.exp(-0.5 * (t / sigma) ** 2)
        dgauss = -t / sigma**2 * gauss
        I_wf = gauss.tolist()
        Q_wf = (alpha * dgauss / anharmonicity).tolist()

    _check_amplitude(I_wf, "DRAG I")
    _check_amplitude(Q_wf, "DRAG Q")
    return I_wf, Q_wf


def kaiser(
    amplitude: float,
    length: int,
    beta: float,
    detuning: float = 0.0,
    alpha: float = 0.0,
    anharmonicity: float = 0.0,
) -> tuple[list[float], list[float]]:
    """Create Kaiser window IQ waveforms (spectrally selective).

    Parameters
    ----------
    amplitude : float
        Peak amplitude.
    length : int
        Number of samples.
    beta : float
        Kaiser window shape parameter.
    detuning : float
        Frequency detuning in Hz.
    alpha : float
        DRAG coefficient (0 to disable).
    anharmonicity : float
        Qubit anharmonicity in Hz (required if alpha != 0).

    Returns
    -------
    I_wf, Q_wf : tuple[list[float], list[float]]
    """
    win = np.kaiser(length, beta)
    win = win / win.max() * amplitude
    t = np.arange(length) - (length - 1) / 2.0

    if detuning != 0.0:
        phase = 2 * np.pi * detuning * t * 1e-9  # t in ns
        I_wf = (win * np.cos(phase)).tolist()
        Q_wf = (win * np.sin(phase)).tolist()
    else:
        I_wf = win.tolist()
        Q_wf = [0.0] * length

    if alpha != 0.0 and anharmonicity != 0.0:
        dwin = np.gradient(win)
        Q_drag = alpha * dwin / anharmonicity
        Q_wf = [q + d for q, d in zip(Q_wf, Q_drag.tolist())]

    _check_amplitude(I_wf, "kaiser I")
    _check_amplitude(Q_wf, "kaiser Q")
    return I_wf, Q_wf


def cosine(amplitude: float, length: int) -> list[float]:
    """Create a cosine-shaped envelope (half period)."""
    t = np.linspace(0, np.pi, length)
    samples = (amplitude * (1 - np.cos(t)) / 2).tolist()
    _check_amplitude(samples, "cosine")
    return samples


def zeros(length: int) -> list[float]:
    """Create a zero waveform of given length."""
    return [0.0] * length


def normalize_samples(
    samples: WaveformSamples, *, label: str = "waveform"
) -> Union[float, list[float]]:
    """Normalize waveform samples for QM config serialization.

    Converts numpy arrays to lists, numpy scalars to floats, etc.
    """
    if isinstance(samples, np.ndarray):
        if samples.ndim != 1:
            raise ValueError(f"{label}: numpy array must be 1D, got shape {samples.shape}.")
        return [float(x) for x in samples.tolist()]

    if hasattr(samples, "item") and not isinstance(samples, (list, tuple, dict, str, bytes)):
        try:
            return float(samples.item())
        except Exception:
            pass

    if isinstance(samples, (list, tuple)):
        return [float(x) for x in samples]

    return samples


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------
def _check_amplitude(samples: list[float], label: str) -> None:
    peak = max(abs(s) for s in samples) if samples else 0.0
    if peak > MAX_AMPLITUDE:
        raise ValueError(
            f"{label} waveform peak amplitude {peak:.4f} exceeds "
            f"MAX_AMPLITUDE ({MAX_AMPLITUDE})."
        )
