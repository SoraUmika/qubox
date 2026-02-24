# qubox_v2/analysis/pulse_train_models.py
"""Pure analysis functions for pulse-train tomography.

This module contains the mathematical models, fitting algorithms,
parameter conversion utilities, and plotting for pulse-train
tomography.  It has NO dependencies on QUA or experiment execution.

The experiment execution functions (``run_pulse_train_tomography``,
``make_state_prep``) remain in ``qubox_v2.calibration.pulse_train_tomo``.
"""
from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import least_squares, differential_evolution

from . import cQED_models


# ---------------------------------------------------------------------------
# Small math helpers
# ---------------------------------------------------------------------------
def wrap_pm_pi(x: float) -> float:
    return float((x + np.pi) % (2 * np.pi) - np.pi)


def safe_normalize(v, eps: float = 1e-12):
    v = np.asarray(v, float)
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, eps)


def apply_theta_phi_correction(theta_cmd: float, phi_cmd: float, *, amp_err_hat: float, phase_err_hat: float):
    """Inverse of model's theta->theta(1+amp_err), phi->phi+phase_err."""
    theta_corr = theta_cmd / (1.0 + float(amp_err_hat))
    phi_corr = wrap_pm_pi(phi_cmd - float(phase_err_hat))
    return float(theta_corr), float(phi_corr)


# ---------------------------------------------------------------------------
# Tomography I/O helpers
# ---------------------------------------------------------------------------
def extract_bloch_from_tomo(runres):
    """Extract Bloch vector(s) from tomography RunResult.

    Returns
    -------
    np.ndarray
        Shape ``(3,)`` when a single prep was used, or ``(P, 3)`` for P preps.
    """
    raw_sx, raw_sy, raw_sz, sx, sy, sz = runres.output.extract(
        "raw_sx", "raw_sy", "raw_sz", "sx", "sy", "sz"
    )

    sx = np.asarray(sx, float).ravel()
    sy = np.asarray(sy, float).ravel()
    sz = np.asarray(sz, float).ravel()

    if sx.size == 1:
        return np.array([float(sx), float(sy), float(sz)], float)
    return np.column_stack([sx, sy, sz])  # (P, 3)


# ---------------------------------------------------------------------------
# Bloch-vector prediction models
# ---------------------------------------------------------------------------
def model_base(N_values, theta, phi, *, r0, delta, amp_err, phase_err):
    return np.asarray(
        cQED_models.qubit_pulse_train_model(
            N_values, theta, phi,
            r0=r0, delta=delta, amp_err=amp_err, phase_err=phase_err
        ), float
    )


def apply_rz(vec, angle):
    c = np.cos(angle); s = np.sin(angle)
    x, y, z = float(vec[0]), float(vec[1]), float(vec[2])
    return np.array([c*x - s*y, s*x + c*y, z], float)


def model_with_zeta(N_values, theta, phi, *, r0, delta, amp_err, phase_err, zeta=0.0):
    base = model_base(N_values, theta, phi, r0=r0, delta=delta, amp_err=amp_err, phase_err=phase_err)
    if abs(zeta) < 1e-15:
        return base
    N = np.asarray(N_values, int)
    out = np.empty_like(base)
    for i, n in enumerate(N):
        out[i] = apply_rz(base[i], zeta * n)
    return out


# ---------------------------------------------------------------------------
# Optional: Relaxation model (T1/T2)
# ---------------------------------------------------------------------------
def apply_relaxation(bloch, t, *, T1, T2, z_eq=+1.0):
    """Apply simple Bloch relaxation for elapsed time t (seconds).

    x,y -> x exp(-t/T2)
    z   -> z_eq + (z - z_eq) exp(-t/T1)
    """
    bloch = np.asarray(bloch, float)
    t = np.asarray(t, float)
    T1 = float(T1); T2 = float(T2)
    if T1 <= 0 or T2 <= 0:
        raise ValueError("T1 and T2 must be > 0")
    e1 = np.exp(-t / T1)
    e2 = np.exp(-t / T2)
    out = np.array(bloch, float, copy=True)
    out[..., 0] *= e2
    out[..., 1] *= e2
    out[..., 2] = float(z_eq) + (out[..., 2] - float(z_eq)) * e1
    return out


def model_with_zeta_and_relax(
    N_values, theta, phi, *,
    r0, delta, amp_err, phase_err,
    zeta=0.0,
    fit_relax: bool = False,
    t_step: float | None = None,
    T1: float | None = None,
    T2: float | None = None,
    z_eq: float = +1.0,
):
    pred = model_with_zeta(
        N_values, theta, phi,
        r0=r0, delta=delta, amp_err=amp_err, phase_err=phase_err, zeta=zeta
    )
    if not fit_relax:
        return pred
    if t_step is None:
        raise ValueError("fit_relax=True requires t_step (seconds per repetition).")
    if T1 is None or T2 is None:
        raise ValueError("fit_relax=True requires T1 and T2.")
    N = np.asarray(N_values, int)
    t = N * float(t_step)
    return apply_relaxation(pred, t, T1=float(T1), T2=float(T2), z_eq=float(z_eq))


# ---------------------------------------------------------------------------
# Fit helper: default initial states
# ---------------------------------------------------------------------------
def default_r0_dict():
    return {
        "g":  np.array([ 0.0,  0.0,  1.0]),
        "e":  np.array([ 0.0,  0.0, -1.0]),
        "+x": np.array([ 1.0,  0.0,  0.0]),
        "+y": np.array([ 0.0,  1.0,  0.0]),
        "-x": np.array([-1.0,  0.0,  0.0]),
        "-y": np.array([ 0.0, -1.0,  0.0]),
    }


# ---------------------------------------------------------------------------
# Knob conversion
# ---------------------------------------------------------------------------
def fit_params_to_qubitrotation_knobs(
    *,
    amp_err_hat: float,
    phase_err_hat: float,
    delta_hat: float,
    dt_s: float,
    n_samp: int,
    d_omega_sign: float = +1.0,
):
    """Convert (delta_hat, amp_err_hat, phase_err_hat) into QubitRotation knob corrections."""
    T = float(n_samp) * float(dt_s)
    if T <= 0:
        raise ValueError(f"Bad pulse duration T={T}. Check dt_s and n_samp.")
    lam0 = np.pi / (2.0 * T)
    d_alpha = -float(phase_err_hat)
    d_lambda = lam0 * (1.0 / (1.0 + float(amp_err_hat)) - 1.0)
    d_omega = float(d_omega_sign) * float(delta_hat) / T
    return dict(T=T, lam0=lam0, d_lambda=d_lambda, d_alpha=d_alpha, d_omega=d_omega)


def pretty_knob_report(knobs: dict, *, delta_hat: float, amp_err_hat: float, phase_err_hat: float, zeta_hat: float | None):
    T = knobs["T"]
    lam0 = knobs["lam0"]
    d_lambda = knobs["d_lambda"]
    d_alpha = knobs["d_alpha"]
    d_omega = knobs["d_omega"]

    print("\n=== Convert fit params -> QubitRotation knobs (inverse corrections) ===")
    print(f"Pulse duration T = {T:.6e} s ({T*1e9:.2f} ns)")
    print(f"lam0 = pi/(2T) = {lam0:.6e} (units: 1/s)")

    print("\nFit (from pulse-train model):")
    print(f"  delta_hat     = {delta_hat:+.6f} rad/pulse  (= \u0394*T)")
    print(f"  amp_err_hat   = {amp_err_hat:+.4%}  (theta -> theta*(1+amp_err))")
    print(f"  phase_err_hat = {phase_err_hat:+.6f} rad  (phi -> phi+phase_err)")
    if zeta_hat is not None:
        print(f"  zeta_hat      = {zeta_hat:+.6f} rad/step  (extra Rz per repetition)")

    print("\nSuggested QubitRotation knob corrections (for THIS rotation):")
    print(f"  d_alpha  = {d_alpha:+.6f} rad")
    print(f"  d_lambda = {d_lambda:+.6e}")
    print(f"  -> implied scale = {1.0 + d_lambda/lam0:+.6f}  (target 1/(1+amp_err) = {1.0/(1.0+amp_err_hat):+.6f})")
    print(f"  d_omega  = {d_omega:+.6e} rad/s  (|delta|/T = {abs(delta_hat)/T:.6e} rad/s)")
    print("\nNOTE: If applying d_omega makes your fitted delta_hat worse on the next run, flip its sign.")
    if zeta_hat is not None:
        print("NOTE: zeta_hat is a per-repetition Z rotation; correcting it is usually a per-step phase update, not d_omega.")


# ---------------------------------------------------------------------------
# Main fitter: DE + LS global optimisation
# ---------------------------------------------------------------------------
def fit_pulse_train_model(
    *,
    meas: dict,
    N_values,
    theta: float,
    phi: float,
    r0_dict: dict | None = None,
    fit_zeta: bool = True,
    fit_relax: bool = False,
    t_step: float | None = None,
    z_eq: float = +1.0,
    residual_mode: str = "dir",
    raw_weight: float = 1.0,
    bounds: dict | None = None,
    de_kwargs: dict | None = None,
    ls_kwargs: dict | None = None,
    fit_idx=None,
    verbose: bool = True,
    multi_seed: bool = False,
    seeds=None,
    seed_select: str = "ls",
    seed_print_best: bool = True,
):
    """Fits coherent params (delta, amp_err, phase_err[, zeta]) and optionally (T1, T2)."""
    N_values = np.asarray(N_values, int)
    theta = float(theta); phi = float(phi)

    if r0_dict is None:
        r0_dict = default_r0_dict()

    if fit_idx is None:
        fit_idx = np.arange(len(N_values), dtype=int)
    fit_idx = np.asarray(fit_idx, int)
    N_fit = N_values[fit_idx]

    if residual_mode not in ("dir", "raw", "both"):
        raise ValueError("residual_mode must be 'dir', 'raw', or 'both'")
    if fit_relax and t_step is None:
        raise ValueError("fit_relax=True requires t_step (seconds per repetition).")

    if bounds is None:
        bounds = {
            "delta":     (-1, 1),
            "amp_err":   (-0.05, +0.05),
            "phase_err": (-0.3, +0.3),
            "zeta":      (-1.0, +1.0),
            "T1":        (0.2e-6, 100e-6),
            "T2":        (0.2e-6, 100e-6),
        }

    param_names = ["delta", "amp_err", "phase_err"]
    if fit_zeta:
        param_names.append("zeta")
    if fit_relax:
        param_names += ["T1", "T2"]

    de_bounds = [bounds[n] for n in param_names]
    lb = np.array([b[0] for b in de_bounds], float)
    ub = np.array([b[1] for b in de_bounds], float)

    def unpack(p):
        p = np.asarray(p, float).ravel()
        out = {}
        for i, name in enumerate(param_names):
            out[name] = float(p[i])
        if "phase_err" in out:
            out["phase_err"] = wrap_pm_pi(out["phase_err"])
        if "zeta" not in out:
            out["zeta"] = 0.0
        if "T1" not in out:
            out["T1"] = None
        if "T2" not in out:
            out["T2"] = None
        return out

    def predict_for_key(pp, key):
        return model_with_zeta_and_relax(
            N_fit, theta, phi,
            r0=r0_dict[key],
            delta=pp["delta"],
            amp_err=pp["amp_err"],
            phase_err=pp["phase_err"],
            zeta=pp["zeta"],
            fit_relax=fit_relax,
            t_step=t_step,
            T1=pp["T1"] if fit_relax else None,
            T2=pp["T2"] if fit_relax else None,
            z_eq=z_eq,
        )

    def residuals_vec(p):
        pp = unpack(p)
        res_all = []
        for key, Y_meas in meas.items():
            Y = np.asarray(Y_meas, float)[fit_idx]
            pred = predict_for_key(pp, key)
            if residual_mode == "dir":
                res = (safe_normalize(pred) - safe_normalize(Y)).ravel()
            elif residual_mode == "raw":
                res = (pred - Y).ravel()
            else:
                res_dir = (safe_normalize(pred) - safe_normalize(Y)).ravel()
                res_raw = (pred - Y).ravel()
                res = np.concatenate([res_dir, float(raw_weight) * res_raw])
            res_all.append(res)
        return np.concatenate(res_all)

    def sse_objective(p):
        r = residuals_vec(p)
        return float(np.sum(r * r))

    def fmt_params_raw(p):
        pp = unpack(p)
        s = f"delta={pp['delta']:+.4f}, amp_err={pp['amp_err']:+.3%}, phase_err={pp['phase_err']:+.4f}"
        if fit_zeta:
            s += f", zeta={pp['zeta']:+.4f}"
        if fit_relax:
            s += f", T1={pp['T1']*1e6:+.3f}us, T2={pp['T2']*1e6:+.3f}us"
        return s

    def run_one_seed(seed_value: int):
        _best = {"sse": np.inf, "p": None}

        def de_callback(xk, convergence):
            sse = float(sse_objective(xk))
            if sse < _best["sse"] - 1e-10:
                _best["sse"] = sse
                _best["p"] = np.array(xk, float)
                if verbose:
                    print(f"[DE NEW BEST | seed={seed_value}] SSE={sse:.6e}  |  {fmt_params_raw(_best['p'])}")
            return False

        if verbose:
            print(f"\n--- Running DE (seed={seed_value}) ---")

        _de_kwargs = dict(
            strategy="best1bin",
            maxiter=120,
            popsize=20,
            tol=1e-6,
            mutation=(0.5, 1.5),
            recombination=0.7,
            polish=False,
            updating="immediate",
            workers=1,
            seed=int(seed_value),
            callback=de_callback,
        )
        if de_kwargs:
            _de_kwargs.update(de_kwargs)
        _de_kwargs["seed"] = int(seed_value)
        _de_kwargs["callback"] = de_callback

        de_local = differential_evolution(sse_objective, bounds=de_bounds, **_de_kwargs)
        p_de = de_local.x

        if verbose:
            print(f"[DE done | seed={seed_value}] best SSE = {de_local.fun:.6e}")
            print(f"[DE done | seed={seed_value}] best params: {fmt_params_raw(p_de)}")

        if verbose:
            print(f"[LS polish | seed={seed_value}] ...")

        _ls_kwargs = dict(method="trf")
        if ls_kwargs:
            _ls_kwargs.update(ls_kwargs)

        ls_local = least_squares(residuals_vec, p_de, bounds=(lb, ub), **_ls_kwargs)
        p_hat_local = unpack(ls_local.x)
        return p_hat_local, de_local, ls_local

    if verbose:
        print(f"[fit] using {len(fit_idx)}/{len(N_values)} N points")
        print(f"[rotation params] theta = {theta:.6f} rad ({theta/np.pi:.4f} \u03c0), phi = {phi:.6f} rad ({phi/np.pi:.4f} \u03c0)")
        print("N_fit =", N_fit)
        print(f"[mode] residual_mode={residual_mode}  fit_zeta={fit_zeta}  fit_relax={fit_relax}")
        if fit_relax:
            print(f"[relax] t_step={float(t_step):.3e} s/rep, z_eq={float(z_eq):+.3f}")

    seed_diag = None
    if multi_seed:
        if seeds is None:
            seeds = list(range(1, 9))
        else:
            seeds = list(seeds)

        if verbose:
            print(f"\n[multi_seed] running {len(seeds)} seeds: {seeds}")

        best = None
        seed_rows = []
        for s in seeds:
            p_hat_s, de_s, ls_s = run_one_seed(int(s))
            row = dict(
                seed=int(s),
                DE_SSE=float(de_s.fun),
                LS_cost=float(ls_s.cost),
                delta=float(p_hat_s["delta"]),
                amp_err=float(p_hat_s["amp_err"]),
                phase_err=float(p_hat_s["phase_err"]),
                zeta=float(p_hat_s.get("zeta", 0.0)),
                T1=float(p_hat_s["T1"]) if fit_relax else None,
                T2=float(p_hat_s["T2"]) if fit_relax else None,
                ls_success=bool(ls_s.success),
                ls_nfev=int(ls_s.nfev),
            )
            seed_rows.append(row)

            score = row["LS_cost"] if seed_select.lower() == "ls" else row["DE_SSE"]
            if best is None or score < best["score"] - 1e-12:
                best = dict(score=score, p_hat=p_hat_s, de=de_s, ls=ls_s, seed=int(s))
                if seed_print_best:
                    extra = ""
                    if fit_relax:
                        extra = f" T1={row['T1']*1e6:.3f}us T2={row['T2']*1e6:.3f}us"
                    print(
                        f"[SEED NEW BEST] seed={best['seed']:2d}  score({seed_select})={best['score']:.6e}  "
                        f"delta={row['delta']:+.5f}  amp_err={row['amp_err']:+.3%}  "
                        f"phase_err={row['phase_err']:+.5f}  zeta={row['zeta']:+.5f}{extra}"
                    )

        p_hat = best["p_hat"]
        de = best["de"]
        ls = best["ls"]
        seed_diag = dict(
            seeds=seeds,
            rows=seed_rows,
            chosen_seed=int(best["seed"]),
            seed_select=seed_select.lower(),
        )
        if verbose:
            print(f"\n[multi_seed] chosen seed = {seed_diag['chosen_seed']} (by {seed_select})")
    else:
        seed_value = 1
        if de_kwargs and "seed" in de_kwargs:
            seed_value = int(de_kwargs["seed"])
        p_hat, de, ls = run_one_seed(seed_value)

    pred_fit = {}
    for key in meas.keys():
        pred_fit[key] = model_with_zeta_and_relax(
            N_values, theta, phi,
            r0=r0_dict[key],
            delta=p_hat["delta"],
            amp_err=p_hat["amp_err"],
            phase_err=p_hat["phase_err"],
            zeta=p_hat["zeta"] if fit_zeta else 0.0,
            fit_relax=fit_relax,
            t_step=t_step,
            T1=p_hat["T1"] if fit_relax else None,
            T2=p_hat["T2"] if fit_relax else None,
            z_eq=z_eq,
        )

    fit_meta = dict(
        fit_idx=fit_idx,
        N_fit=N_fit,
        r0_dict=r0_dict,
        fit_zeta=fit_zeta,
        fit_relax=fit_relax,
        t_step=t_step,
        residual_mode=residual_mode,
        raw_weight=float(raw_weight),
        z_eq=float(z_eq),
    )
    if seed_diag is not None:
        fit_meta["seed_diag"] = seed_diag

    return p_hat, de, ls, pred_fit, fit_meta


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------
def plot_meas_vs_fit(
    *,
    meas: dict,
    pred_fit: dict,
    N_values,
    theta: float,
    phi: float,
    p_hat: dict,
    fit_meta: dict,
    title_prefix: str = "",
    residual_mode: str = "dir",
):
    N_values = np.asarray(N_values, int)
    prep_order = list(meas.keys())
    r0_dict = fit_meta.get("r0_dict", default_r0_dict())

    cycle = plt.rcParams["axes.prop_cycle"].by_key().get("color", ["C0", "C1", "C2"])
    cX, cY, cZ = cycle[0], cycle[1], cycle[2]

    fig, axes = plt.subplots(
        len(prep_order), 2,
        figsize=(16, 4.8 * len(prep_order)),
        sharex="col",
    )
    if len(prep_order) == 1:
        axes = np.asarray([axes], object)

    for row, key in enumerate(prep_order):
        ax_main = axes[row, 0]
        ax_res  = axes[row, 1]

        Y_meas = np.asarray(meas[key], float)
        Y_fit  = np.asarray(pred_fit[key], float)

        Ym = safe_normalize(Y_meas)
        Yf = safe_normalize(Y_fit)

        ax_main.scatter(N_values, Ym[:, 0], s=30, marker="o", color=cX, label="X dir (norm data)")
        ax_main.scatter(N_values, Ym[:, 1], s=30, marker="s", color=cY, label="Y dir (norm data)")
        ax_main.scatter(N_values, Ym[:, 2], s=30, marker="^", color=cZ, label="Z dir (norm data)")
        ax_main.plot(N_values, Yf[:, 0], "-", lw=2.0, color=cX, label="X dir fit")
        ax_main.plot(N_values, Yf[:, 1], "-", lw=2.0, color=cY, label="Y dir fit")
        ax_main.plot(N_values, Yf[:, 2], "-", lw=2.0, color=cZ, label="Z dir fit")

        ax_main.scatter(N_values, Y_meas[:, 0], s=22, marker="o", color=cX, alpha=0.30, label="X raw (no fit)")
        ax_main.scatter(N_values, Y_meas[:, 1], s=22, marker="s", color=cY, alpha=0.30, label="Y raw (no fit)")
        ax_main.scatter(N_values, Y_meas[:, 2], s=22, marker="^", color=cZ, alpha=0.30, label="Z raw (no fit)")

        ax_main.set_title(f"prep {key}: direction+fit with raw overlay")
        ax_main.set_ylabel("Bloch component")
        ax_main.grid(True, alpha=0.3)
        ax_main.axhline(0, color="k", ls="--", lw=0.8, alpha=0.4)
        if row == 0:
            ax_main.legend(fontsize=9, ncol=3)

        Y_ideal = model_with_zeta(
            N_values, theta, phi,
            r0=r0_dict[key],
            delta=0.0, amp_err=0.0, phase_err=0.0, zeta=0.0,
        )

        res_raw = Y_meas - Y_ideal
        res_dir = safe_normalize(Y_meas) - safe_normalize(Y_ideal)

        if residual_mode in ("raw", "both"):
            ax_res.scatter(N_values, res_raw[:, 0], s=18, marker="o", color=cX, alpha=0.55, label="X raw resid (meas-ideal)")
            ax_res.scatter(N_values, res_raw[:, 1], s=18, marker="s", color=cY, alpha=0.55, label="Y raw resid (meas-ideal)")
            ax_res.scatter(N_values, res_raw[:, 2], s=18, marker="^", color=cZ, alpha=0.55, label="Z raw resid (meas-ideal)")

        if residual_mode in ("dir", "both"):
            ax_res.plot(N_values, res_dir[:, 0], "-", lw=1.8, color=cX, label="X dir resid (norm)")
            ax_res.plot(N_values, res_dir[:, 1], "-", lw=1.8, color=cY, label="Y dir resid (norm)")
            ax_res.plot(N_values, res_dir[:, 2], "-", lw=1.8, color=cZ, label="Z dir resid (norm)")

        ax_res.axhline(0, color="k", ls="--", lw=0.8, alpha=0.6)
        ax_res.grid(True, alpha=0.3)
        ax_res.set_title(f"prep {key}: residuals vs ideal (no errors)")
        ax_res.set_ylabel("residual")
        if row == 0:
            ax_res.legend(fontsize=9, ncol=2)

    axes[-1, 0].set_xlabel("N")
    axes[-1, 1].set_xlabel("N")

    fit_idx = fit_meta["fit_idx"]
    fit_zeta = fit_meta["fit_zeta"]
    title = (
        f"{title_prefix}theta={theta:.4f} rad ({theta/np.pi:.3f}\u03c0), phi={phi:.4f} rad ({phi/np.pi:.3f}\u03c0)  |  "
        f"amp_err={p_hat['amp_err']:+.3%}, phase_err={p_hat['phase_err']:+.3f} rad, delta={p_hat['delta']:+.3f} rad"
        + (f", zeta={p_hat['zeta']:+.3f} rad/step" if fit_zeta else "")
        + f"  |  fit points: {len(fit_idx)}/{len(N_values)}"
    )
    fig.suptitle(title, fontsize=13, y=0.995)
    plt.tight_layout(rect=[0, 0, 1, 0.97])
    plt.show()
