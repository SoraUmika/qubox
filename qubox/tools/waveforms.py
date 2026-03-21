"""Pulse waveform generators for the qubox toolkit.

All functions here are pure-Python / NumPy / SciPy with no dependency on
``qubox_v2_legacy``.  They are the canonical waveform-generation utilities
used by notebooks, experiments, and calibration routines.

Migrated from ``qubox_v2_legacy.tools.waveforms``.
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Sequence

import numpy as np
from scipy.signal.windows import blackman, dpss, gaussian


# ---------------------------------------------------------------------------
# DRAG / Gaussian pulses
# ---------------------------------------------------------------------------

def drag_gaussian_pulse_waveforms(
    amplitude,
    length,
    sigma,
    alpha,
    anharmonicity,
    detuning=0.0,
    subtracted=True,
    sampling_rate=1e9,
    **kwargs,
):
    """Create Gaussian-based DRAG waveforms compensating leakage and AC Stark shift.

    Chen et al. PRL 116, 020501 (2016).

    Parameters
    ----------
    amplitude : float
        Amplitude in volts.
    length : int
        Pulse length in ns.
    sigma : float
        Gaussian standard deviation in ns.
    alpha : float
        DRAG coefficient.
    anharmonicity : float
        f_21 − f_10 in Hz.
    detuning : float
        AC-Stark-shift correction frequency in Hz (default 0).
    subtracted : bool
        If True, subtract the final sample so the pulse starts and ends at 0.
    sampling_rate : float
        Samples per second (default 1 GHz).

    Returns
    -------
    (I_wf, Q_wf) : tuple[list[float], list[float]]
    """
    delta = kwargs.get("delta", None)
    if delta is not None:
        warnings.warn(
            "'delta' has been replaced by 'anharmonicity' and will be removed in a future release.",
            DeprecationWarning,
            stacklevel=2,
        )
        if alpha != 0 and delta == 0:
            raise Exception("Cannot create a DRAG pulse with `anharmonicity=0`")
        t = np.arange(length, step=1e9 / sampling_rate)
        center = (length - 1e9 / sampling_rate) / 2
        gauss_wave = amplitude * np.exp(-((t - center) ** 2) / (2 * sigma**2))
        gauss_der_wave = (
            amplitude * (-2 * 1e9 * (t - center) / (2 * sigma**2))
            * np.exp(-((t - center) ** 2) / (2 * sigma**2))
        )
        if subtracted:
            gauss_wave = gauss_wave - gauss_wave[-1]
        z = gauss_wave + 1j * 0
        if alpha != 0:
            z += 1j * gauss_der_wave * (alpha / (delta - 2 * np.pi * detuning))
            z *= np.exp(1j * 2 * np.pi * detuning * t * 1e-9)
    else:
        if alpha != 0 and anharmonicity == 0:
            raise Exception("Cannot create a DRAG pulse with `anharmonicity=0`")
        t = np.arange(length, step=1e9 / sampling_rate)
        center = (length - 1e9 / sampling_rate) / 2
        gauss_wave = amplitude * np.exp(-((t - center) ** 2) / (2 * sigma**2))
        gauss_der_wave = (
            amplitude * (-2 * 1e9 * (t - center) / (2 * sigma**2))
            * np.exp(-((t - center) ** 2) / (2 * sigma**2))
        )
        if subtracted:
            gauss_wave = gauss_wave - gauss_wave[-1]
        z = gauss_wave + 1j * 0
        if alpha != 0:
            z += 1j * gauss_der_wave * (alpha / (2 * np.pi * anharmonicity - 2 * np.pi * detuning))
            z *= np.exp(1j * 2 * np.pi * detuning * t * 1e-9)
    return z.real.tolist(), z.imag.tolist()


def drag_cosine_pulse_waveforms(
    amplitude,
    length,
    alpha,
    anharmonicity,
    detuning=0.0,
    sampling_rate=1e9,
    **kwargs,
):
    """Create cosine-based DRAG waveforms.

    Chen et al. PRL 116, 020501 (2016).
    """
    delta = kwargs.get("delta", None)
    if delta is not None:
        warnings.warn(
            "'delta' has been replaced by 'anharmonicity' and will be removed in a future release.",
            DeprecationWarning,
            stacklevel=2,
        )
        if alpha != 0 and anharmonicity == 0:
            raise Exception("Cannot create a DRAG pulse with `anharmonicity=0`")
        t = np.arange(length, step=1e9 / sampling_rate)
        end_point = length - 1e9 / sampling_rate
        cos_wave = 0.5 * amplitude * (1 - np.cos(t * 2 * np.pi / end_point))
        sin_wave = (
            0.5 * amplitude * (2 * np.pi / end_point * 1e9) * np.sin(t * 2 * np.pi / end_point)
        )
        z = cos_wave + 1j * 0
        if alpha != 0:
            z += 1j * sin_wave * (alpha / (delta - 2 * np.pi * detuning))
            z *= np.exp(1j * 2 * np.pi * detuning * t * 1e-9)
    else:
        if alpha != 0 and anharmonicity == 0:
            raise Exception("Cannot create a DRAG pulse with `anharmonicity=0`")
        t = np.arange(length, step=1e9 / sampling_rate)
        end_point = length - 1e9 / sampling_rate
        cos_wave = 0.5 * amplitude * (1 - np.cos(t * 2 * np.pi / end_point))
        sin_wave = (
            0.5 * amplitude * (2 * np.pi / end_point * 1e9) * np.sin(t * 2 * np.pi / end_point)
        )
        z = cos_wave + 1j * 0
        if alpha != 0:
            z += 1j * sin_wave * (alpha / (2 * np.pi * anharmonicity - 2 * np.pi * detuning))
            z *= np.exp(1j * 2 * np.pi * detuning * t * 1e-9)
    return z.real.tolist(), z.imag.tolist()


# ---------------------------------------------------------------------------
# Windowed pulses (Kaiser, Slepian/DPSS)
# ---------------------------------------------------------------------------

def kaiser_pulse_waveforms(
    amplitude,
    length,
    beta,
    detuning=0.0,
    subtracted=True,
    sampling_rate=1e9,
    alpha=0.0,
    anharmonicity=0.0,
    **kwargs,
):
    """Create a Kaiser-window pulse (optionally with DRAG quadrature term).

    Useful for spectrally selective pulses with low sidelobes.

    Parameters
    ----------
    amplitude : float
        Peak envelope amplitude in volts.
    length : int
        Pulse length in ns (== number of samples at 1 GHz).
    beta : float
        Kaiser window beta.  Larger → lower sidelobes, wider main lobe.
    detuning : float
        Carrier detuning in Hz for complex modulation.
    subtracted : bool
        If True, subtract last sample so edges tend to zero.
    sampling_rate : float
        Samples per second (default 1 GHz).
    alpha : float
        DRAG coefficient (0 → no quadrature term).
    anharmonicity : float
        f_21 − f_10 in Hz (required when alpha != 0).
    """
    delta = kwargs.get("delta", None)
    if delta is not None:
        warnings.warn(
            "'delta' has been replaced by 'anharmonicity' and will be removed in a future release.",
            DeprecationWarning,
            stacklevel=2,
        )
        anharmonicity = float(delta)

    if alpha != 0.0 and anharmonicity == 0.0:
        raise Exception("Cannot create a DRAG-like pulse with `anharmonicity=0` when alpha != 0.")

    t = np.arange(length, step=1e9 / sampling_rate)
    N = t.size
    if N < 2:
        raise ValueError("length must be >= 2 samples")

    env = amplitude * np.kaiser(N, beta)
    if subtracted:
        env = env - env[-1]

    z = env.astype(np.complex128)

    if alpha != 0.0:
        dt_s = (1e9 / sampling_rate) * 1e-9
        denv_dt = np.gradient(env, dt_s)
        denom = 2 * np.pi * (anharmonicity - detuning)
        z = z + 1j * denv_dt * (alpha / denom)

    if detuning != 0.0:
        z = z * np.exp(1j * 2 * np.pi * detuning * t * 1e-9)

    return z.real.tolist(), z.imag.tolist()


def slepian_pulse_waveforms(
    amplitude,
    length,
    NW,
    detuning=0.0,
    subtracted=True,
    sampling_rate=1e9,
    alpha=0.0,
    anharmonicity=0.0,
    **kwargs,
):
    """Create a Slepian (DPSS) window pulse (optionally with DRAG correction).

    Maximises energy concentration in the main lobe.

    Parameters
    ----------
    NW : float
        Time-bandwidth product (standard DPSS parameter).
    """
    delta = kwargs.get("delta", None)
    if delta is not None:
        warnings.warn(
            "'delta' has been replaced by 'anharmonicity' and will be removed in a future release.",
            DeprecationWarning,
            stacklevel=2,
        )
        anharmonicity = float(delta)

    if alpha != 0.0 and anharmonicity == 0.0:
        raise Exception("Cannot create a DRAG-like pulse with `anharmonicity=0` when alpha != 0.")

    t = np.arange(length, step=1e9 / sampling_rate)
    N = t.size
    if N < 2:
        raise ValueError("length must be >= 2 samples")

    w = dpss(N, NW, Kmax=1, sym=True)
    if w.ndim == 2:
        w = w[0]
    w = w / np.max(np.abs(w)) * amplitude
    env = w

    if subtracted:
        env = env - env[-1]

    z = env.astype(np.complex128)

    if alpha != 0.0:
        dt_s = (1e9 / sampling_rate) * 1e-9
        denv_dt = np.gradient(env, dt_s)
        denom = 2 * np.pi * (anharmonicity - detuning)
        z = z + 1j * denv_dt * (alpha / denom)

    if detuning != 0.0:
        z = z * np.exp(1j * 2 * np.pi * detuning * t * 1e-9)

    return z.real.tolist(), z.imag.tolist()


# ---------------------------------------------------------------------------
# Flat-top waveforms
# ---------------------------------------------------------------------------

def flattop_gaussian_waveform(amplitude, flat_length, rise_fall_length, return_part="all", sampling_rate=1e9):
    """Flat-top Gaussian waveform."""
    assert sampling_rate % 1e9 == 0, "sampling_rate must be an integer multiple of 1e9."
    gauss_wave = amplitude * gaussian(
        int(np.round(2 * rise_fall_length * sampling_rate / 1e9)),
        rise_fall_length / 5 * sampling_rate / 1e9,
    )
    rise_part = gauss_wave[: int(rise_fall_length * sampling_rate / 1e9)].tolist()
    if return_part == "all":
        return rise_part + [amplitude] * int(flat_length * sampling_rate / 1e9) + rise_part[::-1]
    elif return_part == "rise":
        return rise_part
    elif return_part == "fall":
        return rise_part[::-1]
    raise Exception("'return_part' must be 'all', 'rise', or 'fall'")


def flattop_cosine_waveform(amplitude, flat_length, rise_fall_length, return_part="all", sampling_rate=1e9):
    """Flat-top cosine waveform."""
    assert sampling_rate % 1e9 == 0, "sampling_rate must be an integer multiple of 1e9."
    rise_part = (
        amplitude * 0.5 * (1 - np.cos(np.linspace(0, np.pi, int(rise_fall_length * sampling_rate / 1e9))))
    ).tolist()
    if return_part == "all":
        return rise_part + [amplitude] * int(flat_length * sampling_rate / 1e9) + rise_part[::-1]
    elif return_part == "rise":
        return rise_part
    elif return_part == "fall":
        return rise_part[::-1]
    raise Exception("'return_part' must be 'all', 'rise', or 'fall'")


def flattop_tanh_waveform(amplitude, flat_length, rise_fall_length, return_part="all", sampling_rate=1e9):
    """Flat-top tanh waveform."""
    assert sampling_rate % 1e9 == 0, "sampling_rate must be an integer multiple of 1e9."
    rise_part = (
        amplitude * 0.5 * (1 + np.tanh(np.linspace(-4, 4, int(rise_fall_length * sampling_rate / 1e9))))
    ).tolist()
    if return_part == "all":
        return rise_part + [amplitude] * int(flat_length * sampling_rate / 1e9) + rise_part[::-1]
    elif return_part == "rise":
        return rise_part
    elif return_part == "fall":
        return rise_part[::-1]
    raise Exception("'return_part' must be 'all', 'rise', or 'fall'")


def flattop_blackman_waveform(amplitude, flat_length, rise_fall_length, return_part="all", sampling_rate=1e9):
    """Flat-top Blackman waveform."""
    assert sampling_rate % 1e9 == 0, "sampling_rate must be an integer multiple of 1e9."
    backman_wave = amplitude * blackman(2 * int(rise_fall_length * sampling_rate / 1e9))
    rise_part = backman_wave[: int(rise_fall_length * sampling_rate / 1e9)].tolist()
    if return_part == "all":
        return rise_part + [amplitude] * int(flat_length * sampling_rate / 1e9) + rise_part[::-1]
    elif return_part == "rise":
        return rise_part
    elif return_part == "fall":
        return rise_part[::-1]
    raise Exception("'return_part' must be 'all', 'rise', or 'fall'")


def blackman_integral_waveform(pulse_length, v_start, v_end, sampling_rate=1e9):
    """Adiabatic Blackman-integral ramp from v_start to v_end."""
    assert sampling_rate % 1e9 == 0, "sampling_rate must be an integer multiple of 1e9."
    time = np.linspace(0, pulse_length - 1, int(pulse_length * sampling_rate / 1e9))
    wave = v_start + (
        time / (pulse_length - 1)
        - (25 / (42 * np.pi)) * np.sin(2 * np.pi * time / (pulse_length - 1))
        + (1 / (21 * np.pi)) * np.sin(4 * np.pi * time / (pulse_length - 1))
    ) * (v_end - v_start)
    return wave.tolist()


# ---------------------------------------------------------------------------
# CLEAR readout waveforms
# ---------------------------------------------------------------------------

def CLEAR_waveform(
    t_duration: int,
    t_kick: int | Sequence[int],
    A_steady: float,
    A_rise_hi: float,
    A_rise_lo: float,
    A_fall_lo: float,
    A_fall_hi: float,
) -> np.ndarray:
    """Build a 2-kick CLEAR-like readout envelope.

    Layout: [A_rise_hi, A_rise_lo] → steady(A_steady) → [A_fall_lo, A_fall_hi]
    """
    if isinstance(t_kick, Sequence) and not isinstance(t_kick, (str, bytes)):
        if len(t_kick) != 4:
            raise ValueError(f"t_kick sequence must have length 4, got {len(t_kick)}")
        t_rise_hi, t_rise_lo, t_fall_lo, t_fall_hi = map(int, t_kick)
    else:
        t_rise_hi = t_rise_lo = t_fall_lo = t_fall_hi = int(t_kick)

    edge_total = t_rise_hi + t_rise_lo + t_fall_lo + t_fall_hi
    if t_duration < edge_total:
        raise ValueError(f"t_duration={t_duration} too short for kick segments totalling {edge_total}")

    n_steady = t_duration - edge_total
    env = np.empty(t_duration, dtype=float)
    idx = 0
    env[idx:idx + t_rise_hi] = A_rise_hi;  idx += t_rise_hi
    env[idx:idx + t_rise_lo] = A_rise_lo;  idx += t_rise_lo
    env[idx:idx + n_steady]   = A_steady;   idx += n_steady
    env[idx:idx + t_fall_lo] = A_fall_lo;  idx += t_fall_lo
    env[idx:idx + t_fall_hi] = A_fall_hi
    return env


def design_clear_kicks_from_rates(
    kappa_rad_s: float,
    chi_rad_s: float,
    A_steady: float,
    segment_dt_s: float,
) -> tuple[float, float, float, float]:
    """Analytically design CLEAR kick amplitudes from cavity parameters."""
    lam_g = kappa_rad_s / 2 - 1j * chi_rad_s
    lam_e = kappa_rad_s / 2 + 1j * chi_rad_s
    s_g = np.exp(-lam_g * segment_dt_s)
    s_e = np.exp(-lam_e * segment_dt_s)
    g_g = -1j / lam_g * (1 - s_g)
    g_e = -1j / lam_e * (1 - s_e)
    alpha_ss_g = -1j * A_steady / lam_g
    alpha_ss_e = -1j * A_steady / lam_e
    M = np.array([[s_g * g_g, g_g], [s_e * g_e, g_e]], dtype=complex)
    A1, A2 = np.linalg.solve(M, np.array([alpha_ss_g, alpha_ss_e], dtype=complex))
    rhs_down = -np.array([s_g**2 * alpha_ss_g, s_e**2 * alpha_ss_e], dtype=complex)
    A4, A5 = np.linalg.solve(M, rhs_down)

    def realify(z):
        return float(np.real_if_close(z, tol=1e-9))

    return realify(A1), realify(A2), realify(A4), realify(A5)


def build_CLEAR_waveform_from_physics(
    t_duration: int,
    t_kick: int | Sequence[int],
    A_steady: float,
    kappa_rad_s: float,
    chi_rad_s: float,
    dt_s: float = 1e-9,
) -> np.ndarray:
    """Wrapper: build CLEAR envelope from kappa, chi, and kick timing."""
    if isinstance(t_kick, Sequence) and not isinstance(t_kick, (str, bytes)):
        if len(t_kick) != 4:
            raise ValueError(f"t_kick sequence must have length 4, got {len(t_kick)}")
        if len({int(t) for t in t_kick}) != 1:
            raise ValueError("Analytic CLEAR design requires equal kick segment lengths.")
        seg_len = int(t_kick[0])
    else:
        seg_len = int(t_kick)

    A_rise_hi, A_rise_lo, A_fall_lo, A_fall_hi = design_clear_kicks_from_rates(
        kappa_rad_s=kappa_rad_s,
        chi_rad_s=chi_rad_s,
        A_steady=A_steady,
        segment_dt_s=seg_len * dt_s,
    )
    return CLEAR_waveform(
        t_duration=t_duration,
        t_kick=seg_len,
        A_steady=A_steady,
        A_rise_hi=A_rise_hi,
        A_rise_lo=A_rise_lo,
        A_fall_lo=A_fall_lo,
        A_fall_hi=A_fall_hi,
    )


# ---------------------------------------------------------------------------
# Amplitude scaling utility
# ---------------------------------------------------------------------------

def gaussian_amp_for_same_rotation(
    ref_amp: float,
    ref_dur: float,
    target_dur: float,
    *,
    n_sigma: float = 4.0,
) -> float:
    """Scale Gaussian amplitude to produce the same rotation angle at a new duration."""
    if ref_dur <= 0 or target_dur <= 0:
        raise ValueError("ref_dur and target_dur must be > 0.")
    if n_sigma <= 0:
        raise ValueError("n_sigma must be > 0.")
    sigma_ref = ref_dur / (2.0 * n_sigma)
    sigma_tgt = target_dur / (2.0 * n_sigma)
    trunc = math.erf(n_sigma / math.sqrt(2.0))
    area_ref = sigma_ref * math.sqrt(2.0 * math.pi) * trunc
    area_tgt = sigma_tgt * math.sqrt(2.0 * math.pi) * trunc
    return ref_amp * (area_ref / area_tgt)
