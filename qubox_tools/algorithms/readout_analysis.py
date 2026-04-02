"""Pure-Python readout analysis utilities.

Extracted from ``measureMacro`` (Phase 4 of measureMacro refactoring).
These functions accept explicit discrimination parameters instead of
reading from the mutable ``measureMacro`` singleton.
"""

from __future__ import annotations

import numpy as np


# --------------------------------------------------------------------------- #
#  P(e) projection
# --------------------------------------------------------------------------- #


def compute_Pe_from_S(
    S,
    rot_mu_g: complex = 0.0 + 0.0j,
    rot_mu_e: complex = 1.0 + 0.0j,
):
    """Project IQ signal onto g/e axis and return P(e).

    Parameters
    ----------
    S : array-like
        Complex IQ signal data.
    rot_mu_g : complex
        Rotated mean for ground state.
    rot_mu_e : complex
        Rotated mean for excited state.

    Returns
    -------
    float | ndarray
        Excited-state probability (projection ratio).
    """
    S = np.asarray(S)

    d = rot_mu_e - rot_mu_g
    denom = float(np.abs(d) ** 2)

    if denom == 0.0:
        out = np.full(S.shape, np.nan, dtype=float)
        return float(out) if out.shape == () else out

    pe = np.real((S - rot_mu_g) * np.conj(d)) / denom

    return float(pe) if pe.shape == () else pe


# --------------------------------------------------------------------------- #
#  Bayesian posterior weights
# --------------------------------------------------------------------------- #


def compute_posterior_weights(
    S,
    disc_params: dict,
    *,
    model_type: str = "1d",
    pi_e: float = 0.5,
    require_finite: bool = True,
):
    """Compute posterior weights (w_g, w_e) using a Gaussian model.

    Parameters
    ----------
    S : array-like
        Complex IQ signal data.
    disc_params : dict
        Discrimination parameters with keys ``rot_mu_g``, ``rot_mu_e``,
        ``sigma_g``, ``sigma_e``.
    model_type : str
        ``"1d"`` or ``"2d"`` Gaussian model (default ``"1d"``).
    pi_e : float
        Prior probability of excited state (default 0.5).
    require_finite : bool
        If True, non-finite values produce NaN weights.

    Returns
    -------
    w_g, w_e : ndarray
        Posterior probabilities P(g|S) and P(e|S).
    """
    pi_e = float(pi_e)
    if not (0.0 < pi_e < 1.0):
        raise ValueError(f"pi_e must be in (0,1), got {pi_e}")
    pi_g = 1.0 - pi_e

    rot_mu_g = disc_params.get("rot_mu_g")
    rot_mu_e = disc_params.get("rot_mu_e")
    sigma_g = disc_params.get("sigma_g")
    sigma_e = disc_params.get("sigma_e")

    if rot_mu_g is None or rot_mu_e is None:
        raise ValueError(
            "rot_mu_g and rot_mu_e must be set in disc_params. "
            "Run readout discrimination calibration first."
        )
    if sigma_g is None or sigma_e is None:
        raise ValueError(
            "sigma_g and sigma_e must be set in disc_params. "
            "Run readout discrimination calibration first."
        )

    Ig = float(np.real(rot_mu_g))
    Ie = float(np.real(rot_mu_e))
    Qg = float(np.imag(rot_mu_g))
    Qe = float(np.imag(rot_mu_e))
    sigma_g = float(sigma_g)
    sigma_e = float(sigma_e)

    if not (np.isfinite(sigma_g) and sigma_g > 0):
        raise ValueError(f"Invalid sigma_g: {sigma_g}")
    if not (np.isfinite(sigma_e) and sigma_e > 0):
        raise ValueError(f"Invalid sigma_e: {sigma_e}")

    S = np.asarray(S)
    if S.ndim == 0:
        S = S.reshape(1)
    if not np.iscomplexobj(S):
        S = S.astype(np.complex128, copy=False)

    I = np.real(S)
    Q = np.imag(S)

    model_type = str(model_type).lower()
    if model_type not in ("1d", "2d"):
        raise ValueError(f"model_type must be '1d' or '2d', got {model_type!r}")

    if require_finite:
        finite = np.isfinite(I) if model_type == "1d" else (np.isfinite(I) & np.isfinite(Q))
    else:
        finite = np.ones(I.shape, dtype=bool)

    def _stable_sigmoid(x):
        x = np.clip(x, -60.0, 60.0)
        return 1.0 / (1.0 + np.exp(-x))

    if model_type == "2d":
        dg2 = (I - Ig) ** 2 + (Q - Qg) ** 2
        de2 = (I - Ie) ** 2 + (Q - Qe) ** 2
        sg2 = sigma_g ** 2
        se2 = sigma_e ** 2

        llr = (
            -de2 / (2.0 * se2) + dg2 / (2.0 * sg2)
            - np.log(se2 / sg2)
            + np.log(pi_e / pi_g)
        )
    else:
        zg2 = ((I - Ig) / sigma_g) ** 2
        ze2 = ((I - Ie) / sigma_e) ** 2
        llr = (
            -0.5 * ze2 + 0.5 * zg2
            - np.log(sigma_e / sigma_g)
            + np.log(pi_e / pi_g)
        )

    w_e = _stable_sigmoid(llr)
    w_e = np.where(finite, w_e, np.nan)
    w_g = 1.0 - w_e
    return w_g, w_e


def compute_posterior_state_weight(
    S,
    disc_params: dict,
    *,
    target_state: str = "g",
    model_type: str = "1d",
    pi_e: float = 0.5,
    require_finite: bool = True,
):
    """Convenience wrapper: compute posterior weight for a single target state.

    Parameters
    ----------
    S : array-like
        Complex IQ signal data.
    disc_params : dict
        Discrimination parameters (same as :func:`compute_posterior_weights`).
    target_state : str
        ``"g"`` for ground or ``"e"`` for excited.
    model_type, pi_e, require_finite
        Forwarded to :func:`compute_posterior_weights`.

    Returns
    -------
    ndarray
        Posterior probability P(target_state|S).
    """
    target_state = str(target_state).lower()
    if target_state not in ("g", "e"):
        raise ValueError(f"target_state must be 'g' or 'e', got {target_state!r}")

    w_g, w_e = compute_posterior_weights(
        S, disc_params, model_type=model_type, pi_e=pi_e, require_finite=require_finite
    )
    return w_e if target_state == "e" else w_g


# --------------------------------------------------------------------------- #
#  2D IQ blob rotation consistency check
# --------------------------------------------------------------------------- #


def check_iq_blob_rotation_consistency_2d(
    S_g,
    S_e,
    disc_params: dict,
    *,
    posterior_classification_threshold: float = 0.5,
    llr_clip: float = 60.0,
    angle_tolerance_rad: float = 0.15,
    sigma_mismatch_tolerance_ratio: float = 0.5,
    include_1d_threshold_baseline: bool = True,
    verbose: bool = True,
) -> dict:
    """Offline GE IQ-blob consistency check using a 2D isotropic posterior model.

    Parameters
    ----------
    S_g, S_e : array-like complex
        IQ blob samples for prepared |g> and |e> respectively.
    disc_params : dict
        Discrimination parameters with keys ``rot_mu_g``, ``rot_mu_e``,
        ``sigma_g``, ``sigma_e``, optionally ``angle`` and ``threshold``.
    posterior_classification_threshold : float
        Hard posterior decision threshold (default 0.5).
    llr_clip : float
        LLR clipping range for numerical stability.
    angle_tolerance_rad : float
        Tolerance for "angle collapsed to zero" check.
    sigma_mismatch_tolerance_ratio : float
        Relative tolerance for stored vs effective 2D sigma comparison.
    include_1d_threshold_baseline : bool
        If True, compute optional 1D threshold baseline on raw I.
    verbose : bool
        If True, print a summary block.

    Returns
    -------
    dict
        Summary dictionary with angle check, 2D posterior metrics, confusion
        matrix, optional 1D baseline, and diagnostic warnings.
    """
    p_thr = float(posterior_classification_threshold)
    if not np.isfinite(p_thr) or p_thr < 0.0 or p_thr > 1.0:
        raise ValueError("posterior_classification_threshold must be finite in [0,1]")

    llr_clip = float(llr_clip)
    if not np.isfinite(llr_clip) or llr_clip <= 0:
        raise ValueError("llr_clip must be finite and > 0")

    S_g = np.asarray(S_g)
    S_e = np.asarray(S_e)
    if S_g.ndim == 0:
        S_g = S_g.reshape(1)
    if S_e.ndim == 0:
        S_e = S_e.reshape(1)
    if not np.iscomplexobj(S_g):
        S_g = S_g.astype(np.complex128, copy=False)
    if not np.iscomplexobj(S_e):
        S_e = S_e.astype(np.complex128, copy=False)

    finite_g = np.isfinite(np.real(S_g)) & np.isfinite(np.imag(S_g))
    finite_e = np.isfinite(np.real(S_e)) & np.isfinite(np.imag(S_e))
    S_g = S_g[finite_g]
    S_e = S_e[finite_e]
    if S_g.size == 0 or S_e.size == 0:
        raise ValueError("S_g and S_e must contain at least one finite complex sample")

    mu_g = disc_params.get("rot_mu_g")
    mu_e = disc_params.get("rot_mu_e")
    sigma_g = disc_params.get("sigma_g")
    sigma_e = disc_params.get("sigma_e")
    theta_ge = disc_params.get("angle")
    thr_ge = disc_params.get("threshold")

    if mu_g is None or mu_e is None:
        raise ValueError("Missing rot_mu_g/rot_mu_e in disc_params; run GE discrimination first")
    if sigma_g is None or sigma_e is None:
        raise ValueError("Missing sigma_g/sigma_e in disc_params; run GE discrimination first")

    sigma_g = float(sigma_g)
    sigma_e = float(sigma_e)
    if not (np.isfinite(sigma_g) and sigma_g > 0):
        raise ValueError(f"Invalid sigma_g: {sigma_g}")
    if not (np.isfinite(sigma_e) and sigma_e > 0):
        raise ValueError(f"Invalid sigma_e: {sigma_e}")

    Ig = float(np.real(mu_g))
    Qg = float(np.imag(mu_g))
    Ie = float(np.real(mu_e))
    Qe = float(np.imag(mu_e))

    def _stable_sigmoid(x):
        x = np.clip(x, -llr_clip, llr_clip)
        return 1.0 / (1.0 + np.exp(-x))

    def _posterior_e_2d(S):
        I = np.real(S)
        Q = np.imag(S)
        dg2 = (I - Ig) ** 2 + (Q - Qg) ** 2
        de2 = (I - Ie) ** 2 + (Q - Qe) ** 2
        sg2 = sigma_g ** 2
        se2 = sigma_e ** 2
        llr = (-de2 / (2.0 * se2)) + (dg2 / (2.0 * sg2)) - np.log(se2 / sg2)
        return _stable_sigmoid(llr), llr

    pe_g, llr_g = _posterior_e_2d(S_g)
    pe_e, llr_e = _posterior_e_2d(S_e)

    pred_e_on_g = pe_g >= p_thr
    pred_e_on_e = pe_e >= p_thr

    p_gg = float(np.mean(~pred_e_on_g))
    p_eg = float(np.mean(pred_e_on_g))
    p_ge = float(np.mean(~pred_e_on_e))
    p_ee = float(np.mean(pred_e_on_e))

    f_bal = 0.5 * (p_gg + p_ee)
    f_bal_pct = 100.0 * f_bal
    confusion = np.array([[p_gg, p_eg], [p_ge, p_ee]], dtype=float)

    from qubox_tools.algorithms.transforms import two_state_discriminator

    disc_blob = two_state_discriminator(S_g, S_e, b_plot=False, save_S_rot=False)
    theta_blob = float(disc_blob["angle"])

    theta_abs = abs(np.arctan2(np.sin(theta_blob), np.cos(theta_blob)))
    theta_mod_pi = min(theta_abs, abs(np.pi - theta_abs))
    angle_ok = bool(theta_mod_pi <= float(angle_tolerance_rad))

    dg2_mu = (np.real(S_g) - Ig) ** 2 + (np.imag(S_g) - Qg) ** 2
    de2_mu = (np.real(S_e) - Ie) ** 2 + (np.imag(S_e) - Qe) ** 2
    sigma_g_eff_2d = float(np.sqrt(max(np.mean(dg2_mu) / 2.0, 0.0)))
    sigma_e_eff_2d = float(np.sqrt(max(np.mean(de2_mu) / 2.0, 0.0)))

    tol = float(sigma_mismatch_tolerance_ratio)
    sigma_warning = None
    if np.isfinite(tol) and tol >= 0:
        rg = abs(sigma_g_eff_2d / sigma_g - 1.0)
        re = abs(sigma_e_eff_2d / sigma_e - 1.0)
        if rg > tol or re > tol:
            sigma_warning = (
                "Stored sigma_g/sigma_e look inconsistent with isotropic 2D cloud spreads. "
                "They may be 1D projected widths; treat 2D posterior as debug-only."
            )

    baseline_1d = None
    if include_1d_threshold_baseline and thr_ge is not None and np.isfinite(float(thr_ge)):
        thr = float(thr_ge)
        p_gg_1d = float(np.mean(np.real(S_g) < thr))
        p_ee_1d = float(np.mean(np.real(S_e) >= thr))
        baseline_1d = {
            "threshold": thr,
            "P(g_hat|g)": p_gg_1d,
            "P(e_hat|e)": p_ee_1d,
            "F_bal": 0.5 * (p_gg_1d + p_ee_1d),
            "F_bal_pct": 100.0 * 0.5 * (p_gg_1d + p_ee_1d),
        }

    likely_failure_modes = []
    if not angle_ok:
        likely_failure_modes = [
            "rotation sign/convention mismatch",
            "stale integration-weight mapping at compile time",
            "rotated weights not burned/applied before iq_blobs run",
            "wrong weight triplet bound for measurement operation",
        ]

    summary = {
        "ge_params": {
            "rot_mu_g": complex(mu_g),
            "rot_mu_e": complex(mu_e),
            "sigma_g": sigma_g,
            "sigma_e": sigma_e,
            "theta_ge": None if theta_ge is None else float(theta_ge),
            "threshold_ge": None if thr_ge is None else float(thr_ge),
        },
        "blob_discriminator": {
            "theta_blob": theta_blob,
            "theta_blob_mod_pi_abs": float(theta_mod_pi),
            "angle_tolerance_rad": float(angle_tolerance_rad),
            "angle_invariant_holds": angle_ok,
        },
        "posterior_2d": {
            "equal_priors": True,
            "posterior_classification_threshold": p_thr,
            "llr_clip": llr_clip,
            "P(g_hat|g)": p_gg,
            "P(e_hat|g)": p_eg,
            "P(g_hat|e)": p_ge,
            "P(e_hat|e)": p_ee,
            "F_bal": float(f_bal),
            "F_bal_pct": float(f_bal_pct),
            "confusion_matrix": confusion,
            "mean_llr_g": float(np.nanmean(llr_g)),
            "mean_llr_e": float(np.nanmean(llr_e)),
        },
        "sigma_interpretation": {
            "sigma_g_stored": sigma_g,
            "sigma_e_stored": sigma_e,
            "sigma_g_eff_2d": sigma_g_eff_2d,
            "sigma_e_eff_2d": sigma_e_eff_2d,
            "warning": sigma_warning,
        },
        "baseline_1d": baseline_1d,
        "likely_failure_modes": likely_failure_modes,
    }

    if verbose:
        print("=" * 72)
        print("GE -> IQ BLOBS CONSISTENCY CHECK (2D POSTERIOR, PYTHON-ONLY)")
        print("=" * 72)
        gp = summary["ge_params"]
        bp = summary["blob_discriminator"]
        p2 = summary["posterior_2d"]
        print("GE params:")
        print(f"  mu_g={gp['rot_mu_g']}, mu_e={gp['rot_mu_e']}")
        print(f"  sigma_g={gp['sigma_g']:.6g}, sigma_e={gp['sigma_e']:.6g}")
        print(f"  theta_GE={gp['theta_ge']}, thr_GE={gp['threshold_ge']}")
        print("Blob angle check:")
        print(f"  theta_blob={bp['theta_blob']:.6g} rad")
        print(f"  |theta_blob|_mod_pi={bp['theta_blob_mod_pi_abs']:.6g} rad")
        print(f"  invariant(|theta_blob|~0)={bp['angle_invariant_holds']}")
        print("2D posterior metrics (equal priors):")
        print(f"  F_bal={p2['F_bal']:.6f} ({p2['F_bal_pct']:.3f}%)")
        print("  confusion [[P(\u011d|g), P(\xea|g)], [P(\u011d|e), P(\xea|e)]] =")
        print(np.array2string(p2["confusion_matrix"], precision=6, suppress_small=False))
        if summary["baseline_1d"] is not None:
            b1 = summary["baseline_1d"]
            print("1D threshold baseline on blobs:")
            print(f"  thr={b1['threshold']:.6g}, F_bal={b1['F_bal']:.6f} ({b1['F_bal_pct']:.3f}%)")
        if sigma_warning:
            print("WARNING:")
            print(f"  {sigma_warning}")
        if likely_failure_modes:
            print("Likely failure modes:")
            for item in likely_failure_modes:
                print(f"  - {item}")
        print("=" * 72)

    return summary
