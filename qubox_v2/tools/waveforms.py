import numpy as np
from collections.abc import Sequence

from scipy.signal.windows import gaussian, blackman, dpss


def drag_gaussian_pulse_waveforms(
    amplitude, length, sigma, alpha, anharmonicity, detuning=0.0, subtracted=True, sampling_rate=1e9, **kwargs
):
    """
    Creates Gaussian based DRAG waveforms that compensate for the leakage and for the AC stark shift.

    These DRAG waveforms has been implemented following the next Refs.:
    Chen et al. PRL, 116, 020501 (2016)
    https://journals.aps.org/prl/abstract/10.1103/PhysRevLett.116.020501
    and Chen's thesis
    https://web.physics.ucsb.edu/~martinisgroup/theses/Chen2018.pdf

    :param float amplitude: The amplitude in volts.
    :param int length: The pulse length in ns.
    :param float sigma: The gaussian standard deviation.
    :param float alpha: The DRAG coefficient.
    :param float anharmonicity: f_21 - f_10 - The differences in energy between the 2-1 and the 1-0 energy levels, in Hz.
    :param float detuning: The frequency shift to correct for AC stark shift, in Hz.
    :param bool subtracted: If true, returns a subtracted Gaussian, such that the first and last points will be at 0
        volts. This reduces high-frequency components due to the initial and final points offset. Default is true.
    :param float sampling_rate: The sampling rate used to describe the waveform, in samples/s. Default is 1G samples/s.
    :return: Returns a tuple of two lists. The first list is the 'I' waveform (real part) and the second is the
        'Q' waveform (imaginary part)
    """
    delta = kwargs.get("delta", None)
    if delta is not None:
        print("'delta' has been replaced by 'anharmonicity' and will be deprecated in the future. ")
        if alpha != 0 and delta == 0:
            raise Exception("Cannot create a DRAG pulse with `anharmonicity=0`")
        t = np.arange(length, step=1e9 / sampling_rate)  # An array of size pulse length in ns
        center = (length - 1e9 / sampling_rate) / 2
        gauss_wave = amplitude * np.exp(-((t - center) ** 2) / (2 * sigma**2))  # The gaussian function
        gauss_der_wave = (
            amplitude * (-2 * 1e9 * (t - center) / (2 * sigma**2)) * np.exp(-((t - center) ** 2) / (2 * sigma**2))
        )  # The derivative of gaussian
        if subtracted:
            gauss_wave = gauss_wave - gauss_wave[-1]  # subtracted gaussian
        z = gauss_wave + 1j * 0
        if alpha != 0:
            # The complex DRAG envelope:
            z += 1j * gauss_der_wave * (alpha / (delta - 2 * np.pi * detuning))
            # The complex detuned DRAG envelope:
            z *= np.exp(1j * 2 * np.pi * detuning * t * 1e-9)
        I_wf = z.real.tolist()  # The `I` component is the real part of the waveform
        Q_wf = z.imag.tolist()  # The `Q` component is the imaginary part of the waveform
    else:
        if alpha != 0 and anharmonicity == 0:
            raise Exception("Cannot create a DRAG pulse with `anharmonicity=0`")
        t = np.arange(length, step=1e9 / sampling_rate)  # An array of size pulse length in ns
        center = (length - 1e9 / sampling_rate) / 2
        gauss_wave = amplitude * np.exp(-((t - center) ** 2) / (2 * sigma**2))  # The gaussian function
        gauss_der_wave = (
            amplitude * (-2 * 1e9 * (t - center) / (2 * sigma**2)) * np.exp(-((t - center) ** 2) / (2 * sigma**2))
        )  # The derivative of gaussian
        if subtracted:
            gauss_wave = gauss_wave - gauss_wave[-1]  # subtracted gaussian
        z = gauss_wave + 1j * 0
        if alpha != 0:
            # The complex DRAG envelope:
            z += 1j * gauss_der_wave * (alpha / (2 * np.pi * anharmonicity - 2 * np.pi * detuning))
            # The complex detuned DRAG envelope:
            z *= np.exp(1j * 2 * np.pi * detuning * t * 1e-9)
        I_wf = z.real.tolist()  # The `I` component is the real part of the waveform
        Q_wf = z.imag.tolist()  # The `Q` component is the imaginary part of the waveform
    return I_wf, Q_wf

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
    """
    Creates a Kaiser-window pulse waveform (optionally with a DRAG-like quadrature term).

    This is useful for *spectrally selective* pulses (low sidelobes -> reduced crosstalk).
    The baseband envelope is a Kaiser window of length `length` samples, scaled by `amplitude`.

    Optional features:
      - subtracted: subtract final sample so first/last go closer to 0 (reduces HF leakage)
      - detuning: apply a complex carrier exp(i 2pi_val detuning t) in Hz (same convention as your DRAG function)
      - alpha + anharmonicity: add an "i * derivative" quadrature term, DRAG-style.
        Note: for a pure selectivity window you can leave alpha=0.

    Parameters
    ----------
    amplitude : float
        Peak scaling of the envelope (volts).
    length : int
        Pulse length in ns (matches your existing function). With sampling_rate=1e9, this is #samples.
    beta : float
        Kaiser window beta. Larger beta -> lower sidelobes (less crosstalk) but wider mainlobe (longer pulses needed).
    detuning : float
        Detuning in Hz for complex modulation (baseband envelope multiplied by exp(i 2pi_val detuning t)).
    subtracted : bool
        If True, subtract the last sample so the waveform ends near 0 (reduces spectral splatter).
    sampling_rate : float
        Samples per second (default 1e9).
    alpha : float
        DRAG coefficient. If 0, no quadrature component is added.
    anharmonicity : float
        f_21 - f_10 in Hz. Required if alpha != 0.
    kwargs :
        Accepted for API compatibility. If `delta` is provided it is treated as `anharmonicity`.

    Returns
    -------
    (I_wf, Q_wf) : (list[float], list[float])
        I and Q waveforms.
    """
    # Backward-compat: allow delta keyword like your gaussian_drag function
    delta = kwargs.get("delta", None)
    if delta is not None:
        print("'delta' has been replaced by 'anharmonicity' and will be deprecated in the future.")
        anharmonicity = float(delta)

    if alpha != 0.0 and anharmonicity == 0.0:
        raise Exception("Cannot create a DRAG-like pulse with `anharmonicity=0` when alpha != 0.")

    # Time axis in ns, same convention as your Gaussian DRAG function
    t = np.arange(length, step=1e9 / sampling_rate)  # ns
    N = t.size
    if N < 2:
        raise ValueError("length must be >= 2 samples")

    # Kaiser window in [0..N-1], symmetric
    env = amplitude * np.kaiser(N, beta)

    if subtracted:
        env = env - env[-1]

    # Complex envelope
    z = env.astype(np.complex128)

    # Optional DRAG-like quadrature: i * derivative of the envelope
    if alpha != 0.0:
        # derivative w.r.t. time in ns -> convert to per-second properly
        # dt_ns is time step in ns; dt_s is time step in seconds
        dt_ns = (1e9 / sampling_rate)
        dt_s = dt_ns * 1e-9

        # Numerical derivative (same length); np.gradient is stable and simple
        denv_dt = np.gradient(env, dt_s)  # d(env)/dt in units of V/s

        # DRAG scaling: mirror your gaussian_drag convention
        # Use (2pi_val*anharmonicity - 2pi_val*detuning) in rad/s
        denom = 2 * np.pi * (anharmonicity - detuning)
        z = z + 1j * denv_dt * (alpha / denom)

    # Optional detuning (complex modulation)
    if detuning != 0.0:
        z = z * np.exp(1j * 2 * np.pi * detuning * t * 1e-9)

    I_wf = z.real.tolist()
    Q_wf = z.imag.tolist()
    return I_wf, Q_wf

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
    """
    Creates a Slepian (DPSS) window pulse waveform (with optional DRAG-like correction).

    Based on the Discrete Prolate Spheroidal Sequences (Slepian sequences), which maximize
    energy concentration in the main lobe for a given bandwidth.

    Parameters
    ----------
    amplitude : float
        Peak scaling of the envelope (volts).
    length : int
        Pulse length in ns. With sampling_rate=1e9, this is #samples.
    NW : float
        Time-bandwidth product (standard DPSS parameter).
        Passed to scipy.signal.windows.dpss(M, NW).
        Common values are 3, 4, etc.
    detuning : float
        Detuning in Hz for complex modulation (baseband envelope multiplied by exp(i 2pi_val detuning t)).
    subtracted : bool
        If True, subtract the last sample so the waveform ends near 0.
    sampling_rate : float
        Samples per second (default 1e9).
    alpha : float
        DRAG coefficient. If 0, no quadrature component is added.
    anharmonicity : float
        f_21 - f_10 in Hz. Required if alpha != 0.
    kwargs :
        Accepted for API compatibility. If `delta` is provided it is treated as `anharmonicity`.

    Returns
    -------
    (I_wf, Q_wf) : (list[float], list[float])
        I and Q waveforms.
    """
    # Backward-compat: allow delta keyword like your gaussian_drag function
    delta = kwargs.get("delta", None)
    if delta is not None:
        print("'delta' has been replaced by 'anharmonicity' and will be deprecated in the future.")
        anharmonicity = float(delta)

    if alpha != 0.0 and anharmonicity == 0.0:
        raise Exception("Cannot create a DRAG-like pulse with `anharmonicity=0` when alpha != 0.")

    # Time axis in ns
    t = np.arange(length, step=1e9 / sampling_rate)  # ns
    N = t.size
    if N < 2:
        raise ValueError("length must be >= 2 samples")

    # DPSS window (0th order)
    # scipy.signal.windows.dpss(M, NW, Kmax, sym, ...)
    w = dpss(N, NW, Kmax=1, sym=True)
    if w.ndim == 2:
        w = w[0]

    # Scale amplitude
    w = w / np.max(np.abs(w)) * amplitude
    env = w

    if subtracted:
        env = env - env[-1]

    # Complex envelope
    z = env.astype(np.complex128)

    # Optional DRAG-like quadrature
    if alpha != 0.0:
        dt_ns = (1e9 / sampling_rate)
        dt_s = dt_ns * 1e-9
        denv_dt = np.gradient(env, dt_s)  # V/s
        denom = 2 * np.pi * (anharmonicity - detuning)
        z = z + 1j * denv_dt * (alpha / denom)

    # Optional detuning (complex modulation)
    if detuning != 0.0:
        z = z * np.exp(1j * 2 * np.pi * detuning * t * 1e-9)

    I_wf = z.real.tolist()
    Q_wf = z.imag.tolist()
    return I_wf, Q_wf

def drag_cosine_pulse_waveforms(amplitude, length, alpha, anharmonicity, detuning=0.0, sampling_rate=1e9, **kwargs):
    """
    Creates Cosine based DRAG waveforms that compensate for the leakage and for the AC stark shift.

    These DRAG waveforms has been implemented following the next Refs.:
    Chen et al. PRL, 116, 020501 (2016)
    https://journals.aps.org/prl/abstract/10.1103/PhysRevLett.116.020501
    and Chen's thesis
    https://web.physics.ucsb.edu/~martinisgroup/theses/Chen2018.pdf

    :param float amplitude: The amplitude in volts.
    :param int length: The pulse length in ns.
    :param float alpha: The DRAG coefficient.
    :param float anharmonicity: f_21 - f_10 - The differences in energy between the 2-1 and the 1-0 energy levels, in Hz.
    :param float detuning: The frequency shift to correct for AC stark shift, in Hz.
    :param float sampling_rate: The sampling rate used to describe the waveform, in samples/s. Default is 1G samples/s.
    :return: Returns a tuple of two lists. The first list is the 'I' waveform (real part) and the second is the
        'Q' waveform (imaginary part)
    """
    delta = kwargs.get("delta", None)
    if delta is not None:
        print("'delta' has been replaced by 'anharmonicity' and will be deprecated in the future.")
        if alpha != 0 and anharmonicity == 0:
            raise Exception("Cannot create a DRAG pulse with `anharmonicity=0`")
        t = np.arange(length, step=1e9 / sampling_rate)  # An array of size pulse length in ns
        end_point = length - 1e9 / sampling_rate
        cos_wave = 0.5 * amplitude * (1 - np.cos(t * 2 * np.pi / end_point))  # The cosine function
        sin_wave = (
            0.5 * amplitude * (2 * np.pi / end_point * 1e9) * np.sin(t * 2 * np.pi / end_point)
        )  # The derivative of cosine function
        z = cos_wave + 1j * 0
        if alpha != 0:
            # The complex DRAG envelope:
            z += 1j * sin_wave * (alpha / (delta - 2 * np.pi * detuning))
            # The complex detuned DRAG envelope:
            z *= np.exp(1j * 2 * np.pi * detuning * t * 1e-9)
        I_wf = z.real.tolist()  # The `I` component is the real part of the waveform
        Q_wf = z.imag.tolist()  # The `Q` component is the imaginary part of the waveform
    else:
        if alpha != 0 and anharmonicity == 0:
            raise Exception("Cannot create a DRAG pulse with `anharmonicity=0`")
        t = np.arange(length, step=1e9 / sampling_rate)  # An array of size pulse length in ns
        end_point = length - 1e9 / sampling_rate
        cos_wave = 0.5 * amplitude * (1 - np.cos(t * 2 * np.pi / end_point))  # The cosine function
        sin_wave = (
            0.5 * amplitude * (2 * np.pi / end_point * 1e9) * np.sin(t * 2 * np.pi / end_point)
        )  # The derivative of cosine function
        z = cos_wave + 1j * 0
        if alpha != 0:
            # The complex DRAG envelope:
            z += 1j * sin_wave * (alpha / (2 * np.pi * anharmonicity - 2 * np.pi * detuning))
            # The complex detuned DRAG envelope:
            z *= np.exp(1j * 2 * np.pi * detuning * t * 1e-9)
        I_wf = z.real.tolist()  # The `I` component is the real part of the waveform
        Q_wf = z.imag.tolist()  # The `Q` component is the imaginary part of the waveform
    return I_wf, Q_wf


def flattop_gaussian_waveform(amplitude, flat_length, rise_fall_length, return_part="all", sampling_rate=1e9):
    """
    Returns a flat top Gaussian waveform. This is a square pulse with a rise and fall of a Gaussian with the given
    sigma. It is possible to only get the rising or falling parts, which allows scanning the flat part length from QUA.
    The length of the pulse will be the `flat_length + 2 * rise_fall_length`.

    :param float amplitude: The amplitude in volts.
    :param int flat_length: The flat part length in ns.
    :param int rise_fall_length: The rise and fall times in ns. The Gaussian sigma is given by the
        `rise_fall_length / 5`.
    :param str return_part: When set to 'all', returns the complete waveform. Default is 'all'. When set to 'rise',
    returns only the rising part. When set to 'fall', returns only the falling part. This is useful for separating
    the three parts which allows scanning the duration of the flat part is to scanned from QUA
    :param float sampling_rate: The sampling rate used to describe the waveform, in samples/s. Must be an integer multiple of 1e9 samples per seconds. Default is 1G samples/s.
    :return: Returns the waveform as a list of values with 1ns spacing
    """

    assert sampling_rate % 1e9 == 0, "The sampling rate must be an integer multiple of 1e9 samples per second."

    gauss_wave = amplitude * gaussian(
        int(np.round(2 * rise_fall_length * sampling_rate / 1e9)), rise_fall_length / 5 * sampling_rate / 1e9
    )
    rise_part = gauss_wave[: int(rise_fall_length * sampling_rate / 1e9)]
    rise_part = rise_part.tolist()
    if return_part == "all":
        return rise_part + [amplitude] * int(flat_length * sampling_rate / 1e9) + rise_part[::-1]
    elif return_part == "rise":
        return rise_part
    elif return_part == "fall":
        return rise_part[::-1]
    else:
        raise Exception("'return_part' must be either 'all', 'rise' or 'fall'")


def flattop_cosine_waveform(amplitude, flat_length, rise_fall_length, return_part="all", sampling_rate=1e9):
    """
    Returns a flat top cosine waveform. This is a square pulse with a rise and fall with cosine shape with the given
    sigma. It is possible to only get the rising or falling parts, which allows scanning the flat part length from QUA.
    The length of the pulse will be the `flat_length + 2 * rise_fall_length`.

    :param float amplitude: The amplitude in volts.
    :param int flat_length: The flat part length in ns.
    :param int rise_fall_length: The rise and fall times in ns, taken as the time for a cosine to go from 0 to 1
    (pi phase-shift) and conversely.
    :param str return_part: When set to 'all', returns the complete waveform. Default is 'all'. When set to 'rise',
    returns only the rising part. When set to 'fall', returns only the falling part. This is useful for separating
    the three parts which allows scanning the duration of the flat part is to scanned from QUA
    :param float sampling_rate: The sampling rate used to describe the waveform, in samples/s. Must be an integer multiple of 1e9 samples per seconds. Default is 1G samples/s.
    :return: Returns the waveform as a list of values with 1ns spacing
    """
    assert sampling_rate % 1e9 == 0, "The sampling rate must be an integer multiple of 1e9 samples per second."
    rise_part = amplitude * 0.5 * (1 - np.cos(np.linspace(0, np.pi, int(rise_fall_length * sampling_rate / 1e9))))
    rise_part = rise_part.tolist()
    if return_part == "all":
        return rise_part + [amplitude] * int(flat_length * sampling_rate / 1e9) + rise_part[::-1]
    elif return_part == "rise":
        return rise_part
    elif return_part == "fall":
        return rise_part[::-1]
    else:
        raise Exception("'return_part' must be either 'all', 'rise' or 'fall'")


def flattop_tanh_waveform(amplitude, flat_length, rise_fall_length, return_part="all", sampling_rate=1e9):
    """
    Returns a flat top tanh waveform. This is a square pulse with a rise and fall with tanh shape with the given
    sigma. It is possible to only get the rising or falling parts, which allows scanning the flat part length from QUA.
    The length of the pulse will be the `flat_length + 2 * rise_fall_length`.

    :param float amplitude: The amplitude in volts.
    :param int flat_length: The flat part length in ns.
    :param int rise_fall_length: The rise and fall times in ns, taken as a number of points of a tanh between -4
        and 4.
    :param str return_part: When set to 'all', returns the complete waveform. Default is 'all'. When set to 'rise',
    returns only the rising part. When set to 'fall', returns only the falling part. This is useful for separating
    the three parts which allows scanning the duration of the flat part is to scanned from QUA
    :param float sampling_rate: The sampling rate used to describe the waveform, in samples/s. Must be an integer multiple of 1e9 samples per seconds. Default is 1G samples/s.
    :return: Returns the waveform as a list of values with 1ns spacing
    """
    assert sampling_rate % 1e9 == 0, "The sampling rate must be an integer multiple of 1e9 samples per second."
    rise_part = amplitude * 0.5 * (1 + np.tanh(np.linspace(-4, 4, int(rise_fall_length * sampling_rate / 1e9))))
    rise_part = rise_part.tolist()
    if return_part == "all":
        return rise_part + [amplitude] * int(flat_length * sampling_rate / 1e9) + rise_part[::-1]
    elif return_part == "rise":
        return rise_part
    elif return_part == "fall":
        return rise_part[::-1]
    else:
        raise Exception("'return_part' must be either 'all', 'rise' or 'fall'")


def flattop_blackman_waveform(amplitude, flat_length, rise_fall_length, return_part="all", sampling_rate=1e9):
    """
    Returns a flat top Blackman waveform. This is a square pulse with a rise and fall with Blackman shape with the given
    length. It is possible to only get the rising or falling parts, which allows scanning the flat part length from QUA.
    The length of the pulse will be the `flat_length + 2 * rise_fall_length`.

    :param float amplitude: The amplitude in volts.
    :param int flat_length: The flat part length in ns.
    :param int rise_fall_length: The rise and fall times in ns, taken as the time to go from 0 to 'amplitude'.
    :param str return_part: When set to 'all', returns the complete waveform. Default is 'all'. When set to 'rise',
    returns only the rising part. When set to 'fall', returns only the falling part. This is useful for separating
    the three parts which allows scanning the duration of the  flat part is to scanned from QUA
    :param float sampling_rate: The sampling rate used to describe the waveform, in samples/s. Must be an integer multiple of 1e9 samples per seconds. Default is 1G samples/s.
    :return: Returns the waveform as a list
    """
    assert sampling_rate % 1e9 == 0, "The sampling rate must be an integer multiple of 1e9 samples per second."
    backman_wave = amplitude * blackman(2 * int(rise_fall_length * sampling_rate / 1e9))
    rise_part = backman_wave[: int(rise_fall_length * sampling_rate / 1e9)]
    rise_part = rise_part.tolist()
    if return_part == "all":
        return rise_part + [amplitude] * int(flat_length * sampling_rate / 1e9) + rise_part[::-1]
    elif return_part == "rise":
        return rise_part
    elif return_part == "fall":
        return rise_part[::-1]
    else:
        raise Exception("'return_part' must be either 'all', 'rise' or 'fall'")


def blackman_integral_waveform(pulse_length, v_start, v_end, sampling_rate=1e9):
    """
    Returns a Blackman integral waveform. This is the integral of a Blackman waveform, adiabatically going from
    'v_start' to 'v_end' in 'pulse_length' ns.

    :param int pulse_length: The pulse length in ns.
    :param float v_start: The starting amplitude in volts.
    :param float v_end: The ending amplitude in volts.
    :param float sampling_rate: The sampling rate used to describe the waveform, in samples/s. Must be an integer multiple of 1e9 samples per seconds. Default is 1G samples/s.
    :return: Returns the waveform as a list
    """
    assert sampling_rate % 1e9 == 0, "The sampling rate must be an integer multiple of 1e9 samples per second."
    time = np.linspace(0, pulse_length - 1, int(pulse_length * sampling_rate / 1e9))
    black_wave = v_start + (
        time / (pulse_length - 1)
        - (25 / (42 * np.pi)) * np.sin(2 * np.pi * time / (pulse_length - 1))
        + (1 / (21 * np.pi)) * np.sin(4 * np.pi * time / (pulse_length - 1))
    ) * (v_end - v_start)
    return black_wave.tolist()

def CLEAR_waveform(
    t_duration: int,
    t_kick: int | Sequence[int],
    A_steady: float,
    A_rise_hi: float,
    A_rise_lo: float,
    A_fall_lo: float,
    A_fall_hi: float,
) -> np.ndarray:
    """
    Build a 2-kick CLEAR-like envelope.

    Layout:
        [A_rise_hi, A_rise_lo]  ->  steady at A_steady  ->  [A_fall_lo, A_fall_hi]

    Parameters
    ----------
    t_duration : int
        Total pulse length (in samples / clks / ns â€“ be consistent).
    t_kick : int or sequence of 4 ints
        If int: length of each kick segment (all 4 segments the same).
        If sequence: (t_rise_hi, t_rise_lo, t_fall_lo, t_fall_hi) for each segment.
    A_steady : float
        Steady-state measurement amplitude (square level).
    A_rise_hi : float
        Amplitude of the first rise segment.
    A_rise_lo : float
        Amplitude of the second rise segment.
    A_fall_lo : float
        Amplitude of the first fall segment.
    A_fall_hi : float
        Amplitude of the second fall segment.

    Returns
    -------
    env : np.ndarray
        1D array of length t_duration with the CLEAR envelope.
    """
    # Normalize t_kick into per-segment lengths
    if isinstance(t_kick, Sequence) and not isinstance(t_kick, (str, bytes)):
        if len(t_kick) != 4:
            raise ValueError(
                f"t_kick sequence must have length 4 (rise_hi, rise_lo, fall_lo, fall_hi), "
                f"got length {len(t_kick)}"
            )
        t_rise_hi, t_rise_lo, t_fall_lo, t_fall_hi = map(int, t_kick)
    else:
        # Single value â†’ use same length for all four segments
        t_rise_hi = t_rise_lo = t_fall_lo = t_fall_hi = int(t_kick)

    edge_total = t_rise_hi + t_rise_lo + t_fall_lo + t_fall_hi

    if t_duration < edge_total:
        raise ValueError(
            f"t_duration={t_duration} is too short for kick segments totaling "
            f"{edge_total} samples"
        )

    n_steady = t_duration - edge_total
    env = np.empty(t_duration, dtype=float)
    idx = 0

    # Rise_hi
    env[idx:idx + t_rise_hi] = A_rise_hi
    idx += t_rise_hi

    # Rise_lo
    env[idx:idx + t_rise_lo] = A_rise_lo
    idx += t_rise_lo

    # Steady
    env[idx:idx + n_steady] = A_steady
    idx += n_steady

    # Fall_lo
    env[idx:idx + t_fall_lo] = A_fall_lo
    idx += t_fall_lo

    # Fall_hi
    env[idx:idx + t_fall_hi] = A_fall_hi
    idx += t_fall_hi

    return env

def design_clear_kicks_from_rates(
    kappa_rad_s: float,
    chi_rad_s: float,
    A_steady: float,
    segment_dt_s: float,
):
    """
    Analytic CLEAR design in terms of *voltage* amplitudes.

    Parameters
    ----------
    kappa_rad_s : float
        Resonator linewidth kappa in rad/s.
    chi_rad_s : float
        Dispersive shift chi_val in rad/s (positive, we use Â±chi_val for g/e).
    A_steady : float
        Steady-state measurement amplitude in volts (your usual readout level).
    segment_dt_s : float
        Duration of a single kick segment in seconds (Ï„).

    Returns
    -------
    A_rise_hi, A_rise_lo, A_fall_lo, A_fall_hi : tuple[float, float, float, float]
        Real-valued amplitudes (volts) for the 4 kick segments.
    """
    # Qubit-state-dependent cavity poles
    lam_g = kappa_rad_s / 2 - 1j * chi_rad_s
    lam_e = kappa_rad_s / 2 + 1j * chi_rad_s

    # Evolution over one segment of length Ï„
    s_g = np.exp(-lam_g * segment_dt_s)
    s_e = np.exp(-lam_e * segment_dt_s)

    # Linear response for constant drive during one segment
    # alpha_out = s_j alpha_in + g_j * A, where A is in volts
    g_g = -1j / lam_g * (1 - s_g)
    g_e = -1j / lam_e * (1 - s_e)

    # Steady-state cavity amplitudes for the plateau drive A_steady
    alpha_ss_g = -1j * A_steady / lam_g
    alpha_ss_e = -1j * A_steady / lam_e

    # --- Ring-up system: 2 segments (A1, A2) ---
    # For each state j âˆˆ {g, e}:
    #   alpha_j^(2) = s_j g_j A1 + g_j A2 = alpha_ss_j
    M = np.array(
        [
            [s_g * g_g, g_g],
            [s_e * g_e, g_e],
        ],
        dtype=complex,
    )
    rhs_up = np.array([alpha_ss_g, alpha_ss_e], dtype=complex)
    A1, A2 = np.linalg.solve(M, rhs_up)

    # --- Ring-down system: 2 segments (A4, A5) ---
    # Start both states at steady state (alpha_ss_j), end at alpha_j^(5) = 0
    # alpha_j^(5) = s_j^2 alpha_ss_j + s_j g_j A4 + g_j A5 = 0
    rhs_down = -np.array(
        [s_g**2 * alpha_ss_g, s_e**2 * alpha_ss_e],
        dtype=complex,
    )
    A4, A5 = np.linalg.solve(M, rhs_down)

    # Solutions will be real to numerical precision; strip tiny imaginary parts
    def realify(z):
        return float(np.real_if_close(z, tol=1e-9))

    return (
        realify(A1),
        realify(A2),
        realify(A4),
        realify(A5),
    )


def build_CLEAR_waveform_from_physics(
    t_duration: int,
    t_kick: int | Sequence[int],
    A_steady: float,
    kappa_rad_s: float,
    chi_rad_s: float,
    dt_s: float = 1e-9,
):
    """
    Wrapper around CLEAR_waveform using kappa, chi_val, and dt to choose kick amplitudes.

    Assumes all four kick segments have the same duration if you pass an int
    for t_kick (recommended for the analytic design).

    Parameters
    ----------
    t_duration : int
        Total pulse length in samples.
    t_kick : int or sequence of 4 ints
        Kick segment lengths, same convention as CLEAR_waveform.
        For analytic design, pass an int for equal-length segments.
    A_steady : float
        Plateau amplitude in volts (your usual readout amplitude).
    kappa_rad_s : float
        Resonator linewidth kappa in rad/s.
    chi_rad_s : float
        Dispersive shift chi_val in rad/s.
    dt_s : float
        Time per sample in seconds (e.g. 1e-9 for 1 ns).

    Returns
    -------
    env : np.ndarray
        CLEAR envelope in volts, ready to be used as your readout envelope.
    """
    # Normalize t_kick to single segment length for the analytic design
    if isinstance(t_kick, Sequence) and not isinstance(t_kick, (str, bytes)):
        if len(t_kick) != 4:
            raise ValueError(
                f"t_kick sequence must have length 4 (rise_hi, rise_lo, "
                f"fall_lo, fall_hi), got {len(t_kick)}"
            )
        # For now, require equal kick segment lengths if user passes a sequence
        if len({int(t) for t in t_kick}) != 1:
            raise ValueError(
                "Analytic CLEAR design currently assumes all four kick "
                "segments have the same duration."
            )
        seg_len = int(t_kick[0])
    else:
        seg_len = int(t_kick)

    segment_dt_s = seg_len * dt_s

    A_rise_hi, A_rise_lo, A_fall_lo, A_fall_hi = design_clear_kicks_from_rates(
        kappa_rad_s=kappa_rad_s,
        chi_rad_s=chi_rad_s,
        A_steady=A_steady,
        segment_dt_s=segment_dt_s,
    )

    # Now just call your existing generator
    env = CLEAR_waveform(
        t_duration=t_duration,
        t_kick=seg_len,
        A_steady=A_steady,
        A_rise_hi=A_rise_hi,
        A_rise_lo=A_rise_lo,
        A_fall_lo=A_fall_lo,
        A_fall_hi=A_fall_hi,
    )
    return env

import math
def gaussian_amp_for_same_rotation(
    ref_amp: float,
    ref_dur: float,
    target_dur: float,
    *,
    n_sigma: float = 4.0,
) -> float:
    """
    Scale the amplitude of a truncated Gaussian pulse so it produces the same
    qubit rotation angle as a reference Gaussian pulse, but with a new duration.

    Assumptions (standard in RWA for weak/moderate drives):
      - Rotation angle Î¸ âˆ âˆ« Î©(t) dt  (pulse "area")
      - Î©(t) is proportional to your Gaussian envelope amplitude
      - Both pulses are Gaussians centered in the middle of the window and
        truncated to [0, dur]
      - The Gaussian width scales with duration via: sigma = dur / (2*n_sigma)
        so that the edges are at Â±n_sigma from the center.

    Under these assumptions, the required scaling is simply:
        amp_target = ref_amp * (ref_dur / target_dur)

    The code below derives this from the analytic integral of a truncated Gaussian.
    """
    if ref_dur <= 0 or target_dur <= 0:
        raise ValueError("ref_dur and target_dur must be > 0.")
    if n_sigma <= 0:
        raise ValueError("n_sigma must be > 0.")

    # sigma = dur / (2*n_sigma)  (center at dur/2, edges at Â±n_sigma*sigma)
    sigma_ref = ref_dur / (2.0 * n_sigma)
    sigma_tgt = target_dur / (2.0 * n_sigma)

    # Truncation factor from integrating a centered Gaussian over [0, dur]:
    # area = amp * sigma * sqrt(2pi_val) * erf( (dur/2) / (sqrt(2)*sigma) )
    # Here (dur/2)/(sqrt(2)*sigma) = n_sigma/sqrt(2), same for both pulses,
    # so erf(...) cancels; leaving amp âˆ 1/sigma âˆ 1/dur.
    # Still, we compute it explicitly for clarity.
    trunc = math.erf(n_sigma / math.sqrt(2.0))

    area_ref_per_amp = sigma_ref * math.sqrt(2.0 * math.pi) * trunc
    area_tgt_per_amp = sigma_tgt * math.sqrt(2.0 * math.pi) * trunc

    return ref_amp * (area_ref_per_amp / area_tgt_per_amp)


