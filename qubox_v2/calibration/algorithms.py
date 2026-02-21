# qubox_v2/calibration/algorithms.py
"""Calibration analysis algorithms.

High-level routines that accept experimental data, perform fitting /
optimisation, and return typed calibration models ready for storage.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
from scipy.optimize import minimize, least_squares

from ..analysis.cQED_models import (
    chi_ramsey_model,
    num_splitting_model,
    number_split_frequency_model,
    qubit_pulse_train_model,
)
from ..analysis.fitting import generalized_fit
from .models import (
    FockSQRCalibration,
    MultiStateCalibration,
    PulseTrainResult,
)


# ---------------------------------------------------------------------------
# Pulse-train tomography
# ---------------------------------------------------------------------------
def fit_pulse_train(
    N_values: np.ndarray,
    I_data: np.ndarray,
    Q_data: np.ndarray,
    *,
    element: str = "",
    rotation_pulse: str = "x180",
    theta: float = np.pi,
    phi: float = 0.0,
    method: str = "least_squares",
) -> PulseTrainResult:
    """Fit pulse-train tomography data to extract amp_err, phase_err, delta.

    Parameters
    ----------
    N_values : array of int
        Number of pulse repetitions.
    I_data, Q_data : array of float
        Measured I and Q quadratures (one value per N).
    element : str
        Quantum element name (for labeling).
    rotation_pulse : str
        Name of the rotation pulse under test.
    theta : float
        Nominal rotation angle per pulse (radians). Default pi.
    phi : float
        Nominal drive phase (radians). Default 0 (X-axis).
    method : str
        ``"least_squares"`` (default) or ``"minimize"``.

    Returns
    -------
    PulseTrainResult
        Fitted parameters with amp_err, phase_err, delta, zeta.
    """
    N_arr = np.asarray(N_values, dtype=int)
    I_arr = np.asarray(I_data, dtype=float)
    Q_arr = np.asarray(Q_data, dtype=float)

    # Normalise to Bloch z-component (assumes I ~ <sigma_z>)
    # Combine I and Q into a measurement vector
    meas = np.column_stack([I_arr, Q_arr])  # shape (M, 2)

    def residuals(params):
        amp_err, phase_err, delta = params
        bloch_vecs = qubit_pulse_train_model(
            N_arr, theta, phi,
            amp_err=amp_err, phase_err=phase_err, delta=delta,
        )
        # bloch_vecs shape: (M, 3) -> we compare x,y components to I,Q
        # Convention: I ~ <sigma_x>, Q ~ <sigma_y> in the rotating frame
        pred = bloch_vecs[:, :2]  # (x, y) components
        return (meas - pred).ravel()

    x0 = np.array([0.0, 0.0, 0.0])

    if method == "least_squares":
        result = least_squares(residuals, x0, method="lm")
        amp_err, phase_err, delta = result.x
    else:
        def cost(params):
            r = residuals(params)
            return np.sum(r**2)
        result = minimize(cost, x0, method="Nelder-Mead")
        amp_err, phase_err, delta = result.x

    return PulseTrainResult(
        element=element,
        amp_err=float(amp_err),
        phase_err=float(phase_err),
        delta=float(delta),
        rotation_pulse=rotation_pulse,
        N_values=N_arr.tolist(),
        timestamp=datetime.now().isoformat(),
    )


def compute_corrected_knobs(
    pulse_train_result: PulseTrainResult,
    current_amplitude: float,
    current_phase: float = 0.0,
) -> dict[str, float]:
    """Compute corrected pulse amplitude and phase from pulse-train fit.

    Parameters
    ----------
    pulse_train_result : PulseTrainResult
        Result from ``fit_pulse_train``.
    current_amplitude : float
        Current pulse amplitude (absolute, not normalized).
    current_phase : float
        Current pulse phase offset (radians).

    Returns
    -------
    dict with keys:
        - ``corrected_amplitude`` : adjusted amplitude
        - ``corrected_phase`` : adjusted phase offset (radians)
        - ``amplitude_correction_factor`` : multiplicative factor
    """
    amp_err = pulse_train_result.amp_err
    phase_err = pulse_train_result.phase_err

    correction_factor = 1.0 / (1.0 + amp_err)
    corrected_amplitude = current_amplitude * correction_factor
    corrected_phase = current_phase - phase_err

    return {
        "corrected_amplitude": float(corrected_amplitude),
        "corrected_phase": float(corrected_phase),
        "amplitude_correction_factor": float(correction_factor),
    }


# ---------------------------------------------------------------------------
# Multi-state affine calibration
# ---------------------------------------------------------------------------
def fit_multi_alpha_affine(
    S_measured: dict[str, np.ndarray],
    S_ideal: dict[str, np.ndarray],
    *,
    element: str = "",
    alpha_values: list[float] | None = None,
) -> MultiStateCalibration:
    """Fit an affine map from measured IQ data to ideal state labels.

    Given calibration shots for N known states, fits the affine map::

        s_corrected = A @ s_measured + b

    that best maps the measured centroids to the ideal reference points.

    Parameters
    ----------
    S_measured : dict[str, ndarray]
        Keys are state labels (e.g. "g", "e", "0", "1", ...),
        values are complex arrays of single-shot IQ data.
    S_ideal : dict[str, ndarray]
        Same keys as ``S_measured``, values are the ideal (target)
        complex centroids or vectors.
    element : str
        Quantum element name.
    alpha_values : list[float], optional
        Coherent-state amplitudes used in the calibration.

    Returns
    -------
    MultiStateCalibration
    """
    state_labels = sorted(S_measured.keys())
    n_states = len(state_labels)

    # Build centroid matrices
    # measured centroids: shape (n_states, 2) [I, Q]
    meas_centroids = np.zeros((n_states, 2))
    ideal_centroids = np.zeros((n_states, 2))

    for i, label in enumerate(state_labels):
        s_m = np.asarray(S_measured[label])
        s_i = np.asarray(S_ideal[label])
        meas_centroids[i] = [np.mean(s_m.real), np.mean(s_m.imag)]
        ideal_centroids[i] = [np.mean(s_i.real), np.mean(s_i.imag)]

    # Solve: ideal = meas @ A^T + b  (least-squares)
    # Augment measured with ones column for affine offset
    meas_aug = np.column_stack([meas_centroids, np.ones(n_states)])

    # Solve for each output dimension
    # ideal[:, d] = meas_aug @ w_d -> w_d = (meas_aug^T meas_aug)^-1 meas_aug^T ideal[:, d]
    W, _, _, _ = np.linalg.lstsq(meas_aug, ideal_centroids, rcond=None)

    # W shape: (3, 2) -> A = W[:2, :].T, b = W[2, :]
    A = W[:2, :].T  # (2, 2)
    b = W[2, :]  # (2,)

    return MultiStateCalibration(
        element=element,
        alpha_values=list(alpha_values or []),
        affine_matrix=A.tolist(),
        offset_vector=b.tolist(),
        state_labels=state_labels,
        timestamp=datetime.now().isoformat(),
    )


def apply_affine_correction(
    S: np.ndarray,
    calibration: MultiStateCalibration,
) -> np.ndarray:
    """Apply a fitted affine correction to raw IQ data.

    Parameters
    ----------
    S : ndarray (complex)
        Raw IQ data as complex array.
    calibration : MultiStateCalibration
        The calibration containing affine_matrix and offset_vector.

    Returns
    -------
    ndarray (complex)
        Corrected IQ data.
    """
    A = np.asarray(calibration.affine_matrix)  # (2, 2)
    b = np.asarray(calibration.offset_vector)  # (2,)

    IQ = np.column_stack([S.real, S.imag])  # (N, 2)
    corrected = IQ @ A.T + b  # (N, 2)
    return corrected[:, 0] + 1j * corrected[:, 1]


# ---------------------------------------------------------------------------
# Number-splitting chi extraction
# ---------------------------------------------------------------------------
def fit_number_splitting(
    peak_frequencies: np.ndarray | list[float],
    fock_numbers: np.ndarray | list[int] | None = None,
) -> dict[str, float]:
    """Fit number-split peak positions to extract chi, chi2, chi3.

    Uses ``number_split_frequency_model``::

        f(n) = base_fq + chi * n + chi2 * n*(n-1) + chi3 * n*(n-1)*(n-2)

    Parameters
    ----------
    peak_frequencies : array of float
        Measured peak frequencies, one per Fock number.
    fock_numbers : array of int, optional
        Fock numbers corresponding to each peak. Defaults to 0, 1, 2, ...

    Returns
    -------
    dict with keys: ``base_fq``, ``chi``, ``chi2``, ``chi3``.
    """
    freqs = np.asarray(peak_frequencies, dtype=float)
    if fock_numbers is None:
        ns = np.arange(len(freqs), dtype=float)
    else:
        ns = np.asarray(fock_numbers, dtype=float)

    # Initial guesses
    base_fq_guess = freqs[0]
    chi_guess = float(np.mean(np.diff(freqs))) if len(freqs) > 1 else 0.0
    p0 = [base_fq_guess, chi_guess, 0.0, 0.0]

    popt, pcov = generalized_fit(
        ns, freqs, number_split_frequency_model, p0,
    )

    if popt is not None:
        return {
            "base_fq": float(popt[0]),
            "chi": float(popt[1]),
            "chi2": float(popt[2]),
            "chi3": float(popt[3]),
        }

    # Fallback: linear estimate
    return {
        "base_fq": float(freqs[0]),
        "chi": chi_guess,
        "chi2": 0.0,
        "chi3": 0.0,
    }


# ---------------------------------------------------------------------------
# Chi-Ramsey fitting
# ---------------------------------------------------------------------------
def fit_chi_ramsey(
    times: np.ndarray,
    signal: np.ndarray,
    *,
    chi_guess: float | None = None,
    nbar_guess: float = 1.0,
) -> dict[str, float]:
    """Fit chi-Ramsey collapse-and-revival data.

    Uses ``chi_ramsey_model(t, P0, A, T2_eff, nbar, chi, t0)``.

    Parameters
    ----------
    times : array of float
        Evolution times (seconds).
    signal : array of float
        Measured signal (excited-state probability).
    chi_guess : float, optional
        Initial guess for chi (Hz). If None, estimated from revival period.
    nbar_guess : float
        Initial guess for mean photon number.

    Returns
    -------
    dict with keys: ``P0``, ``A``, ``T2_eff``, ``nbar``, ``chi``, ``t0``.
    """
    times = np.asarray(times, dtype=float)
    signal = np.asarray(signal, dtype=float)

    P0_guess = float(signal.mean())
    A_guess = float((signal.max() - signal.min()) / 2)
    T2_guess = float(times[-1]) / 3

    if chi_guess is None:
        # Estimate chi from FFT of detrended signal
        detrended = signal - signal.mean()
        fft_vals = np.abs(np.fft.rfft(detrended))
        fft_freqs = np.fft.rfftfreq(len(detrended), d=float(times[1] - times[0]))
        if len(fft_vals) > 1:
            chi_guess = float(fft_freqs[1:][np.argmax(fft_vals[1:])])
        else:
            chi_guess = 1e6

    p0 = [P0_guess, A_guess, T2_guess, nbar_guess, chi_guess, 0.0]

    popt, pcov = generalized_fit(
        times, signal, chi_ramsey_model, p0,
    )

    param_names = ["P0", "A", "T2_eff", "nbar", "chi", "t0"]
    if popt is not None:
        return dict(zip(param_names, [float(v) for v in popt]))

    return dict(zip(param_names, p0))


# ---------------------------------------------------------------------------
# Fock-resolved SQR calibration
# ---------------------------------------------------------------------------
def fit_fock_sqr(
    gains: np.ndarray,
    signal: np.ndarray,
    fock_number: int,
    *,
    model_func: Any | None = None,
) -> FockSQRCalibration:
    """Fit a single Fock-resolved SQR power Rabi curve.

    Parameters
    ----------
    gains : array of float
        Sweep gains/amplitudes.
    signal : array of float
        Measured signal (magnitude or population).
    fock_number : int
        The Fock number this calibration applies to.
    model_func : callable, optional
        Custom model function. Defaults to a cosine model.

    Returns
    -------
    FockSQRCalibration
    """
    from ..analysis.cQED_models import power_rabi_model

    gains = np.asarray(gains, dtype=float)
    signal = np.asarray(signal, dtype=float)

    if model_func is None:
        model_func = power_rabi_model

    A_guess = float((signal.max() - signal.min()) / 2)
    pos_mask = gains > 0
    if np.any(pos_mask):
        g_pi_guess = float(gains[pos_mask][np.argmin(signal[pos_mask])])
    else:
        g_pi_guess = float(gains[np.argmin(signal)])
    offset_guess = float(signal.mean())
    p0 = [A_guess, g_pi_guess, offset_guess]

    popt, pcov = generalized_fit(gains, signal, model_func, p0)

    params = {}
    if popt is not None:
        params = {"A": float(popt[0]), "g_pi": float(popt[1]), "offset": float(popt[2])}

    return FockSQRCalibration(
        fock_number=fock_number,
        model_type=getattr(model_func, "__name__", "power_rabi_model"),
        params=params,
        timestamp=datetime.now().isoformat(),
    )


def optimize_fock_sqr_iterative(
    gains: np.ndarray,
    signals_per_fock: dict[int, np.ndarray],
    *,
    model_func: Any | None = None,
) -> list[FockSQRCalibration]:
    """Iteratively fit SQR calibrations for each Fock number.

    Parameters
    ----------
    gains : array of float
        Common gain sweep.
    signals_per_fock : dict[int, ndarray]
        Signal for each Fock number (key = n, value = signal array).
    model_func : callable, optional
        Custom model function for each Fock fit.

    Returns
    -------
    list[FockSQRCalibration]
        One calibration per Fock number, sorted by n.
    """
    results = []
    for n in sorted(signals_per_fock.keys()):
        cal = fit_fock_sqr(gains, signals_per_fock[n], n, model_func=model_func)
        results.append(cal)
    return results


def optimize_fock_sqr_spsa(
    cost_function,
    x0: np.ndarray,
    *,
    fock_number: int = 0,
    n_iter: int = 200,
    a: float = 0.1,
    c: float = 0.01,
    A: float = 10.0,
    alpha: float = 0.602,
    gamma: float = 0.101,
) -> FockSQRCalibration:
    """SPSA (Simultaneous Perturbation Stochastic Approximation) optimizer.

    Useful for noisy, experimental cost functions where gradient-based
    methods are unreliable.

    Parameters
    ----------
    cost_function : callable
        ``cost_function(params) -> float``. Evaluated on hardware.
    x0 : ndarray
        Initial parameter vector.
    fock_number : int
        Fock number for labeling.
    n_iter : int
        Number of SPSA iterations.
    a, c, A, alpha, gamma : float
        SPSA hyper-parameters.

    Returns
    -------
    FockSQRCalibration
        Best parameters found.
    """
    x = np.array(x0, dtype=float)
    p = len(x)

    best_cost = np.inf
    best_x = x.copy()

    for k in range(1, n_iter + 1):
        ak = a / (k + A) ** alpha
        ck = c / k ** gamma

        # Bernoulli perturbation
        delta = 2 * (np.random.randint(0, 2, size=p) - 0.5)

        # Evaluate cost at perturbed points
        y_plus = cost_function(x + ck * delta)
        y_minus = cost_function(x - ck * delta)

        # Gradient estimate
        g_hat = (y_plus - y_minus) / (2 * ck * delta)

        # Update
        x = x - ak * g_hat

        # Track best
        y_curr = min(y_plus, y_minus)
        if y_curr < best_cost:
            best_cost = y_curr
            best_x = x.copy()

    param_names = [f"p{i}" for i in range(len(best_x))]
    params = dict(zip(param_names, [float(v) for v in best_x]))

    return FockSQRCalibration(
        fock_number=fock_number,
        model_type="spsa_optimized",
        params=params,
        fidelity=float(-best_cost) if np.isfinite(best_cost) else None,
        timestamp=datetime.now().isoformat(),
    )
