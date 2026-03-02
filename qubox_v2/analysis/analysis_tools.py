import numpy as np
import math
import matplotlib.pyplot as plt
from qualang_tools.units import unit
from typing import Sequence, Mapping
from math import factorial
def compute_probabilities(values: Sequence[bool] | np.ndarray) -> Mapping[str, float]:
    """
    Compute P(True) and P(False) for a list/array-like of booleans (or 0/1).
    Works with Python lists, NumPy arrays, and pandas Series.
    """
    arr = np.asarray(values)

    # Empty input handling
    if arr.size == 0:
        return {"P(True)": 0.0, "P(False)": 0.0}

    # Coerce to boolean if needed (accepts 0/1 numerics too)
    if arr.dtype != bool:
        try:
            arr = arr.astype(bool)
        except Exception as e:
            raise TypeError("values must be booleans or 0/1-like") from e

    total = arr.size
    count_true = int(arr.sum())       # True counts as 1
    p_true = count_true / total
    return {"P(True)": p_true, "P(False)": 1.0 - p_true}


def project_complex_to_line_real(S: np.ndarray):
    """Project complex IQ samples onto their dominant real axis.

    Parameters
    ----------
    S : array-like of complex
        Complex demodulated samples.

    Returns
    -------
    tuple
        ``(S_proj, center, direction)`` where:
        - ``S_proj`` is a float array with the same shape as ``S``
        - ``center`` is the complex center used for projection
        - ``direction`` is a unit complex number defining the projection axis
    """
    arr = np.asarray(S)
    if arr.size == 0:
        return np.asarray(arr, dtype=float), 0.0 + 0.0j, 1.0 + 0.0j

    vec = arr.reshape(-1).astype(np.complex128, copy=False)
    finite = np.isfinite(vec.real) & np.isfinite(vec.imag)
    if not np.any(finite):
        return np.full(arr.shape, np.nan, dtype=float), 0.0 + 0.0j, 1.0 + 0.0j

    valid = vec[finite]
    center = np.mean(valid)
    centered = valid - center

    if centered.size < 2:
        direction = 1.0 + 0.0j
    else:
        xy = np.column_stack([centered.real, centered.imag])
        cov = np.cov(xy, rowvar=False)
        try:
            vals, vecs = np.linalg.eigh(cov)
            principal = vecs[:, int(np.argmax(vals))]
            direction = complex(float(principal[0]), float(principal[1]))
        except Exception:
            direction = 1.0 + 0.0j

    nrm = abs(direction)
    if not np.isfinite(nrm) or nrm == 0:
        direction = 1.0 + 0.0j
    else:
        direction /= nrm

    proj_flat = np.full(vec.shape, np.nan, dtype=float)
    proj_flat[finite] = np.real((vec[finite] - center) * np.conj(direction))
    return proj_flat.reshape(arr.shape), center, direction

def complex_encoder(obj):
    """Encode complex numbers and numpy arrays as JSON-safe dicts."""
    # 1) Python / NumPy complex scalars
    if isinstance(obj, (complex, np.complex64, np.complex128)):
        return {"__complex__": True, "real": obj.real, "imag": obj.imag}

    # 2) NumPy arrays
    if isinstance(obj, np.ndarray):
        return {
            "__ndarray__": True,
            "dtype": str(obj.dtype),
            "shape": obj.shape,
            "data": obj.tolist(),   # will recurse and use default=complex_encoder on elements
        }

    # 3) Other NumPy scalar types (int64, float64, etc.)
    if isinstance(obj, np.generic):
        return obj.item()

    # Let json know we don't handle this type
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

def complex_decoder(d):
    """Decode dicts back into complex numbers and numpy arrays if marked."""
    # 1) Complex
    if "__complex__" in d:
        return complex(d["real"], d["imag"])

    # 2) NumPy arrays
    if "__ndarray__" in d:
        arr = np.array(d["data"], dtype=d["dtype"])
        return arr.reshape(d["shape"])

    # 3) Anything else: leave as normal dict
    return d

def demod2volts(S, duration, axis=0):
    u = unit()
    S = np.asarray(S)
    duration = np.asarray(duration)
    if duration.ndim == 0:
        return u.demod2volts(S, duration)
    if duration.ndim != 1 or duration.shape[0] != S.shape[axis]:
        raise ValueError(f"duration must be scalar or 1â€‘D of length S.shape[{axis}]")
    bshape = [1] * S.ndim
    bshape[axis] = duration.shape[0]
    duration = duration.reshape(bshape)
    return u.demod2volts(S, duration)

def round_to_multiple(n: int, mult: int = 4, direction: str = "up") -> int:
    """
    Round integer n to a multiple of `mult`.
    direction: "up" | "down" | "nearest"
    """
    if mult <= 0:
        raise ValueError("mult must be a positive integer")
    r = n % mult
    if r == 0:
        return int(n)
    if direction == "up":
        return int(n + (mult - r))
    elif direction == "down":
        return int(n - r)
    elif direction == "nearest":
        up = n + (mult - r)
        down = n - r
        # tie -> round up
        return int(up if (n - down) > (up - n) else down)
    else:
        raise ValueError("direction must be 'up', 'down', or 'nearest'")


def interp_logpdf(x, grid_x, logpdf_grid):
    """Vectorized 1D interpolation for log-densities."""
    return np.interp(x, grid_x, logpdf_grid, left=logpdf_grid[0], right=logpdf_grid[-1])


def bilinear_interp_logpdf(I, Q, grid_I, grid_Q, logpdf_grid):
    """
    Bilinear interpolation on a regular grid.
    logpdf_grid shape: (len(grid_Q), len(grid_I)) i.e. (nQ, nI)
    """
    I = np.asarray(I, dtype=np.float64)
    Q = np.asarray(Q, dtype=np.float64)

    nI = grid_I.size
    nQ = grid_Q.size

    # find cell indices
    i = np.searchsorted(grid_I, I) - 1
    q = np.searchsorted(grid_Q, Q) - 1

    i = np.clip(i, 0, nI - 2)
    q = np.clip(q, 0, nQ - 2)

    I0 = grid_I[i]
    I1 = grid_I[i + 1]
    Q0 = grid_Q[q]
    Q1 = grid_Q[q + 1]

    # weights in [0,1]
    tx = (I - I0) / (I1 - I0 + 1e-30)
    ty = (Q - Q0) / (Q1 - Q0 + 1e-30)

    f00 = logpdf_grid[q, i]
    f10 = logpdf_grid[q, i + 1]
    f01 = logpdf_grid[q + 1, i]
    f11 = logpdf_grid[q + 1, i + 1]

    return (1 - tx) * (1 - ty) * f00 + tx * (1 - ty) * f10 + (1 - tx) * ty * f01 + tx * ty * f11


def compile_1d_kde_to_grid(
    model,
    *,
    n_grid: int = 4096,
    pad_sigma: float = 6.0,
    eps: float = 1e-300,
):
    """
    Convert an A_1d KDE model (with gaussian_kde objects) into a fast grid lookup.

    Produces:
      model["method"] = "kde_grid"
      model["grid_x"] = x grid
      model["logpdf_g_grid"], model["logpdf_e_grid"] = log density arrays on grid
    """
    if model.get("type") != "A_1d" or model.get("method") != "kde":
        raise ValueError("compile_1d_kde_to_grid expects model type A_1d with method='kde'.")

    kde_g = model["kde_g"]
    kde_e = model["kde_e"]

    # Use training data range; gaussian_kde stores dataset in `.dataset`
    # dataset shape is (1, N) for 1D KDE
    xg = np.asarray(kde_g.dataset).ravel()
    xe = np.asarray(kde_e.dataset).ravel()
    x_all = np.concatenate([xg, xe])

    # Choose grid range with padding
    mu = np.mean(x_all)
    sig = np.std(x_all) + 1e-12
    lo = np.min(x_all) - pad_sigma * sig
    hi = np.max(x_all) + pad_sigma * sig

    grid_x = np.linspace(lo, hi, int(n_grid), dtype=np.float64)

    pg = np.maximum(kde_g(grid_x), eps)
    pe = np.maximum(kde_e(grid_x), eps)

    model2 = dict(model)  # shallow copy
    model2["method"] = "kde_grid"
    model2["grid_x"] = grid_x
    model2["logpdf_g_grid"] = np.log(pg)
    model2["logpdf_e_grid"] = np.log(pe)

    # Drop heavy KDE objects to save memory / enable serialization
    model2.pop("kde_g", None)
    model2.pop("kde_e", None)

    return model2


def compile_2d_kde_to_grid(
    model,
    *,
    nI: int = 256,
    nQ: int = 256,
    pad_sigma: float = 6.0,
    eps: float = 1e-300,
):
    """
    Convert a B_2d_kde model (gaussian_kde) into a grid lookup:
      - grid_I, grid_Q
      - logpdf_g_grid (nQ x nI), logpdf_e_grid (nQ x nI)
    """
    if model.get("type") != "B_2d_kde":
        raise ValueError("compile_2d_kde_to_grid expects model type B_2d_kde.")

    kde_g = model["kde_g"]
    kde_e = model["kde_e"]

    # training data (2, N)
    Xg = np.asarray(kde_g.dataset)
    Xe = np.asarray(kde_e.dataset)
    I_all = np.concatenate([Xg[0], Xe[0]])
    Q_all = np.concatenate([Xg[1], Xe[1]])

    muI, sigI = np.mean(I_all), np.std(I_all) + 1e-12
    muQ, sigQ = np.mean(Q_all), np.std(Q_all) + 1e-12

    I_lo, I_hi = np.min(I_all) - pad_sigma * sigI, np.max(I_all) + pad_sigma * sigI
    Q_lo, Q_hi = np.min(Q_all) - pad_sigma * sigQ, np.max(Q_all) + pad_sigma * sigQ

    grid_I = np.linspace(I_lo, I_hi, int(nI), dtype=np.float64)
    grid_Q = np.linspace(Q_lo, Q_hi, int(nQ), dtype=np.float64)

    # Evaluate KDE on grid points (vectorized)
    II, QQ = np.meshgrid(grid_I, grid_Q, indexing="xy")  # both (nQ, nI)
    pts = np.vstack([II.ravel(), QQ.ravel()])  # (2, nI*nQ)

    pg = np.maximum(kde_g(pts), eps).reshape(nQ, nI)
    pe = np.maximum(kde_e(pts), eps).reshape(nQ, nI)

    model2 = dict(model)
    model2["type"] = "B_2d_grid"
    model2["grid_I"] = grid_I
    model2["grid_Q"] = grid_Q
    model2["logpdf_g_grid"] = np.log(pg)
    model2["logpdf_e_grid"] = np.log(pe)

    # Drop heavy KDE objects
    model2.pop("kde_g", None)
    model2.pop("kde_e", None)
    return model2

def bools_to_sigma_z(bools: np.ndarray) -> np.ndarray:
    """Convert boolean array (True=|e>, False=|g>) to sigma_z values (+1/-1)."""
    bools = np.asarray(bools, dtype=bool)
    return 2.0 * bools.astype(float) - 1.0

def sigma_z_to_bools(sigma_z: np.ndarray) -> np.ndarray:
    """Convert sigma_z array (+1/-1) to boolean array (True=|e>, False=|g>)."""
    sigma_z = np.asarray(sigma_z, dtype=float)
    return sigma_z > 0.0

def sigma_z_to_probs(sigma_z: np.ndarray) -> np.ndarray:
    """Convert sigma_z array (+1/-1) to excited-state probabilities [0,1]."""
    sigma_z = np.asarray(sigma_z, dtype=float)
    return 0.5 * (sigma_z + 1.0)

def I_to_probs(I_data: np.ndarray, threshold: float):
    return (I_data > threshold) * 1

def alpha_for_max_fock_population(n: int, phase: float = 0.0) -> complex:
    """
    Return coherent-state displacement alpha that maximizes the population P_n
    of Fock level |n> in |alpha>.

    For a coherent state, P_n = exp(-|alpha|^2) * |alpha|^(2n) / n!,
    which is maximized at |alpha|^2 = n  => |alpha| = sqrt(n).

    Parameters
    ----------
    n : int
        Target Fock level (n >= 0).
    phase : float
        Phase of alpha in radians. Does not change populations; included for convenience.

    Returns
    -------
    alpha : complex
        The displacement amplitude alpha.
    """
    if not isinstance(n, int) or n < 0:
        raise ValueError("n must be an integer >= 0.")
    r = np.sqrt(n)
    return r * np.exp(1j * phase)


def max_fock_population_value(n: int) -> float:
    """
    The maximum achievable P_n within coherent states (at |alpha|^2 = n).
    Useful to know how 'peaky' you can get.
    """
    if not isinstance(n, int) or n < 0:
        raise ValueError("n must be an integer >= 0.")
    # P_n,max = e^{-n} n^n / n!
    return float(np.exp(-n) * (n**n) / factorial(n)) if n > 0 else 1.0

def fit_ge_affine_normalizer(mu_g, mu_e, *, eps: float = 1e-12) -> tuple[complex, complex]:
    """
    Fit an affine complex map z -> a*z + b such that the |g> and |e> 
    blob centers are sent to -1 and +1 on the real axis.

    Works on already-rotated blobs or raw blobs; the complex factor
    handles any small residual phase.
    """
    zg = mu_g
    ze = mu_e
    den = ze - zg
    if not np.isfinite(den) or abs(den) < eps:
        raise ValueError("Blob centers are degenerate or non-finite (ze â‰ˆ zg); cannot normalize.")
    a = 2.0 / den                      # complex scale (includes tiny rotation)
    b = -(ze + zg) * a / 2.0           # complex shift so midpoint -> 0
    return complex(a), complex(b)

def apply_norm_IQ(Z: np.ndarray, factor: complex, offset: complex) -> np.ndarray:
    """Apply z' = factor*z + offset to a complex array."""
    return factor * Z + offset

def IQ_to_S(I,Q):
    """Convert I,Q arrays to complex S = I + 1j*Q."""
    return I.astype(np.complex128) + 1j * Q.astype(np.complex128)

def rotate_IQ_blob(I, Q, angle: float) -> tuple[np.ndarray, np.ndarray]:
    """Rotate IQ blob by angle (radians)."""
    C = np.cos(angle)
    S = np.sin(angle)
    I_rot = I * C - Q * S
    Q_rot = I * S + Q * C
    return I_rot, Q_rot

def rotate_S(S: np.ndarray, angle: float) -> np.ndarray:
    """Rotate complex IQ blob S by angle (radians)."""
    I_rot, Q_rot = rotate_IQ_blob(S.real, S.imag, angle)
    return I_rot + 1j * Q_rot



from .algorithms import optimal_threshold_empirical, estimate_intrinsic_sigmas_mog
from .metrics import gaussianity_score
from .output import Output


def two_state_discriminator(
    *args,
    b_plot: bool = False,
    plots=("hist", "raw_blob", "rot_blob", "Fidelities", "info"),
    fig_title: str | None = None,
    save_S_rot: bool = True
) -> Output:
    """
    Find rotation angle (excited on +I), optimal 1D threshold on rotated I, and metrics.

    Usage:
      two_state_discriminator(Ig, Qg, Ie, Qe, ...)
      two_state_discriminator(Sg, Se, ...)
    where:
      Sg = Ig + 1j * Qg
      Se = Ie + 1j * Qe
    """

    # --- Parse positional arguments -----------------------------------------
    if len(args) == 4:
        # Old style: (Ig, Qg, Ie, Qe)
        Ig, Qg, Ie, Qe = map(np.asarray, args)
        Sg = Ig + 1j * Qg
        Se = Ie + 1j * Qe

    elif len(args) == 2:
        # New style: (Sg, Se)
        Sg, Se = map(np.asarray, args)
        Ig, Qg = Sg.real, Sg.imag
        Ie, Qe = Se.real, Se.imag

    else:
        raise TypeError(
            "two_state_discriminator expects either "
            "(Ig, Qg, Ie, Qe, ...) or (Sg, Se, ...)."
        )

    def _latex_sci(x: float, sigfigs: int = 4) -> str:
        if x == 0 or not np.isfinite(x):
            return "0"
        exp = int(np.floor(np.log10(abs(x))))
        mant = x / (10 ** exp)
        mant_str = f"{mant:.{sigfigs-1}g}"
        if exp == 0:
            return mant_str
        return rf"{mant_str}\times 10^{{{exp}}}"

    def _plain(x: float) -> str:
        if not np.isfinite(x):
            return "nan"
        return f"{x:.4f}"

    out = Output()

    Ig = np.asarray(Ig, float).ravel()
    Qg = np.asarray(Qg, float).ravel()
    Ie = np.asarray(Ie, float).ravel()
    Qe = np.asarray(Qe, float).ravel()

    # ---------------------------------------------------------------------- #
    # 1) Use MoG-based estimator to get axis, sigmas, rotated centers
    # ---------------------------------------------------------------------- #
    sigmas_mog_output = estimate_intrinsic_sigmas_mog(Sg, Se)
    #out.update(sigmas_mog_output)

    axis = sigmas_mog_output["axis"]               # complex unit vector
    mu_g = float(sigmas_mog_output["mu_g"])        # along rotated I axis
    mu_e = float(sigmas_mog_output["mu_e"])
    sigma_g = float(sigmas_mog_output["sigma_g"])
    sigma_e = float(sigmas_mog_output["sigma_e"])

    mu_g_I_unrot = float(sigmas_mog_output["mu_g_I_unrot"])
    mu_g_Q_unrot = float(sigmas_mog_output["mu_g_Q_unrot"])
    mu_e_I_unrot = float(sigmas_mog_output["mu_e_I_unrot"])
    mu_e_Q_unrot = float(sigmas_mog_output["mu_e_Q_unrot"])

    mu_g_I_rot = float(sigmas_mog_output["mu_g_I_rot"])
    mu_g_Q_rot = float(sigmas_mog_output["mu_g_Q_rot"])
    mu_e_I_rot = float(sigmas_mog_output["mu_e_I_rot"])
    mu_e_Q_rot = float(sigmas_mog_output["mu_e_Q_rot"])

    # Angle, just for reporting (rotation that aligns axis with +I)
    angle = float(-np.angle(axis))

    # ---------------------------------------------------------------------- #
    # 2) Rotate blobs using the same axis as estimate_intrinsic_sigmas_mog
    # ---------------------------------------------------------------------- #
    Sg_rot = Sg * np.conj(axis)
    Se_rot = Se * np.conj(axis)

    if save_S_rot:
        out["Sg_rot"] = Sg_rot
        out["Se_rot"] = Se_rot
    Ig_rot, Qg_rot = Sg_rot.real, Sg_rot.imag
    Ie_rot, Qe_rot = Se_rot.real, Se_rot.imag

    # Store sigmas (already in out, but also explicit if you like)
    out["sigma_g"] = sigma_g
    out["sigma_e"] = sigma_e

    # ---------------------------------------------------------------------- #
    # 3) Optimal empirical threshold on rotated I
    # ---------------------------------------------------------------------- #
    threshold, err_rate = optimal_threshold_empirical(Ig_rot, Ie_rot)

    gg = np.sum(Ig_rot < threshold) / len(Ig_rot)
    ge = 1.0 - gg
    ee = np.sum(Ie_rot > threshold) / len(Ie_rot)
    eg = 1.0 - ee
    fidelity = 100.0 * (gg + ee) / 2.0

    # Core outputs
    out["angle"] = float(angle)
    out["threshold"] = float(threshold)
    out["fidelity"] = float(fidelity)
    out["gg"] = float(gg)
    out["ge"] = float(ge)
    out["eg"] = float(eg)
    out["ee"] = float(ee)

    # Rotated centers as complex numbers in rotated frame
    out["rot_mu_g"] = complex(mu_g_I_rot, mu_g_Q_rot)
    out["rot_mu_e"] = complex(mu_e_I_rot, mu_e_Q_rot)
    
    out["unrot_mu_g"] = complex(mu_g_I_unrot, mu_g_Q_unrot)
    out["unrot_mu_e"] = complex(mu_e_I_unrot, mu_e_Q_unrot)
    
    # Affine normalizer on rotated I means
    a, b = fit_ge_affine_normalizer(mu_g_I_rot, mu_e_I_rot)
    norm_params = {"factor": a, "offset": b}
    out["norm_params"] = norm_params

    # ---------------------------------------------------------------------- #
    # 4) Plotting
    # ---------------------------------------------------------------------- #
    if b_plot:
        if isinstance(plots, str):
            plots = (plots,)

        plot_order = ("raw_blob", "rot_blob", "hist", "Fidelities", "info")
        plot_set = [p for p in plot_order if p in plots]

        if plot_set:
            n = len(plot_set)
            ncols = min(3, n)
            nrows = math.ceil(n / ncols)

            fig, axes = plt.subplots(
                nrows,
                ncols,
                squeeze=False,
                figsize=(4 * ncols, 4 * nrows),
            )
            ax_list = axes.ravel()

            for ax, kind in zip(ax_list, plot_set):
                if kind == "raw_blob":
                    ax.plot(Ig, Qg, ".", alpha=0.1, markersize=2, label=r"$|g\rangle$")
                    ax.plot(Ie, Qe, ".", alpha=0.1, markersize=2, label=r"$|e\rangle$")

                    # mark raw centers
                    ax.plot(
                        mu_g_I_unrot,
                        mu_g_Q_unrot,
                        "x",
                        markersize=8,
                        mew=2,
                        label=r"$\mu_g$",
                        zorder=5,
                    )
                    ax.plot(
                        mu_e_I_unrot,
                        mu_e_Q_unrot,
                        "x",
                        markersize=8,
                        mew=2,
                        label=r"$\mu_e$",
                        zorder=5,
                    )

                    ax.axis("equal")
                    ax.set_xlabel(r"$I$")
                    ax.set_ylabel(r"$Q$")
                    ax.set_title(r"Original IQ")
                    ax.legend(loc="best")
                    ax.ticklabel_format(style="sci", axis="both", scilimits=(0, 0))

                elif kind == "rot_blob":
                    ax.plot(
                        Ig_rot,
                        Qg_rot,
                        ".",
                        alpha=0.1,
                        markersize=2,
                        label=r"$|g\rangle$",
                    )
                    ax.plot(
                        Ie_rot,
                        Qe_rot,
                        ".",
                        alpha=0.1,
                        markersize=2,
                        label=r"$|e\rangle$",
                    )

                    # mark rotated centers
                    ax.plot(
                        mu_g_I_rot,
                        mu_g_Q_rot,
                        "x",
                        markersize=8,
                        mew=2,
                        label=r"$\mu_g^\mathrm{(rot)}$",
                        zorder=5,
                    )
                    ax.plot(
                        mu_e_I_rot,
                        mu_e_Q_rot,
                        "x",
                        markersize=8,
                        mew=2,
                        label=r"$\mu_e^\mathrm{(rot)}$",
                        zorder=5,
                    )

                    ax.axis("equal")
                    ax.set_xlabel(r"$I_\mathrm{rot}$")
                    ax.set_ylabel(r"$Q_\mathrm{rot}$")
                    ax.set_title(r"Rotated IQ")
                    ax.legend(loc="best")
                    ax.ticklabel_format(style="sci", axis="both", scilimits=(0, 0))

                elif kind == "hist":
                    ax.hist(Ig_rot, bins=100, alpha=0.75, label=r"$|g\rangle$")
                    ax.hist(Ie_rot, bins=100, alpha=0.75, label=r"$|e\rangle$")
                    ax.axvline(x=threshold, ls="--", alpha=0.6, label=r"$I_\mathrm{thr}$")
                    ax.axvline(x=mu_g, ls="-.", alpha=0.8, label=r"$\mu_g$")
                    ax.axvline(x=mu_e, ls="-.", alpha=0.8, label=r"$\mu_e$")
                    ax.set_xlabel(r"$I_\mathrm{rot}$")
                    ax.set_title(r"$I_\mathrm{rot}$ Histogram")
                    ax.legend(loc="best")
                    ax.ticklabel_format(style="sci", axis="x", scilimits=(0, 0))

                elif kind == "Fidelities":
                    im = ax.imshow(
                        np.array([[gg, ge], [eg, ee]]),
                        vmin=0,
                        vmax=1,
                    )
                    ax.set_xticks([0, 1])
                    ax.set_yticks([0, 1])
                    ax.set_xticklabels([r"$|g\rangle$", r"$|e\rangle$"])
                    ax.set_yticklabels([r"$|g\rangle$", r"$|e\rangle$"])
                    ax.set_ylabel(r"Prepared")
                    ax.set_xlabel(r"Measured")
                    ax.set_title(r"Fidelity Matrix")

                    ax.text(0, 0, rf"${_plain(gg)}$", ha="center", va="center")
                    ax.text(1, 0, rf"${_plain(ge)}$", ha="center", va="center")
                    ax.text(0, 1, rf"${_plain(eg)}$", ha="center", va="center")
                    ax.text(1, 1, rf"${_plain(ee)}$", ha="center", va="center")

                    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

                elif kind == "info":
                    ax.axis("off")

                    left_lines = [
                        rf"$\theta = {_plain(angle)}\ \mathrm{{rad}}$",
                        rf"$\theta^\circ = {_plain(180/np.pi*angle)}^\circ$",
                        rf"$I_\mathrm{{thr}} = {_latex_sci(threshold)}$",
                        rf"$\mathcal{{F}} = {_plain(fidelity)}\ \%$",
                        rf"$P(g|g) = {_plain(gg)}$",
                        rf"$P(e|g) = {_plain(ge)}$",
                        rf"$P(g|e) = {_plain(eg)}$",
                        rf"$P(e|e) = {_plain(ee)}$",
                        rf"$\mu_g = {_latex_sci(mu_g)}$",
                        rf"$\sigma_g = {_latex_sci(sigma_g)}$",
                        rf"$\mu_e = {_latex_sci(mu_e)}$",
                        rf"$\sigma_e = {_latex_sci(sigma_e)}$",
                    ]

                    right_lines = []

                    if right_lines:
                        ax.text(
                            0.01,
                            0.99,
                            "\n".join(left_lines),
                            va="top",
                            ha="left",
                            fontsize=9,
                        )
                        ax.text(
                            0.52,
                            0.99,
                            "\n".join(right_lines),
                            va="top",
                            ha="left",
                            fontsize=9,
                        )
                    else:
                        ax.text(
                            0.01,
                            0.99,
                            "\n".join(left_lines),
                            va="top",
                            ha="left",
                            fontsize=9,
                        )

                    ax.set_title(r"Discriminator Summary")

            # delete unused axes
            for j in range(len(plot_set), len(ax_list)):
                fig.delaxes(ax_list[j])

            if fig_title is not None:
                fig.suptitle(fig_title)
                fig.tight_layout(rect=[0, 0.03, 1, 0.95])
            else:
                fig.tight_layout()

    return out

# -----------------------------
# Shared helpers
# -----------------------------
def _as_complex_1d(x):
    a = np.asarray(x)
    if a.ndim == 0:
        a = a.reshape(1)
    if not np.iscomplexobj(a):
        a = a.astype(np.complex128, copy=False)
    return a.ravel()

def _isfinite_complex(z):
    return np.isfinite(z.real) & np.isfinite(z.imag)

def _stable_sigmoid(llr, clip=60.0):
    llr = np.clip(llr, -clip, clip)
    return 1.0 / (1.0 + np.exp(-llr))

def _fd_bins(x, min_bins=32, max_bins=512):
    """Freedmanâ€“Diaconis bin rule with sane clamps."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if x.size < 2:
        return min_bins
    q25, q75 = np.percentile(x, [25, 75])
    iqr = q75 - q25
    if iqr <= 0:
        return min_bins
    bw = 2.0 * iqr * (x.size ** (-1.0 / 3.0))
    if bw <= 0:
        return min_bins
    nb = int(np.ceil((x.max() - x.min()) / bw))
    return int(np.clip(nb, min_bins, max_bins))


# ============================================================
# Option A: 1D "optimal axis" + empirical density (KDE or hist)
# ============================================================
def build_posterior_model_1d(
    Sg_cal,
    Se_cal,
    *,
    method="kde",              # "kde" or "hist"
    kde_bw="scott",            # for KDE
    bins="fd",                 # for hist: "fd" or int
    smooth_sigma_bins=0.0,     # hist smoothing in bin units (0 disables)
    require_finite=True,
    eps=1e-300,
):
    """
    Build a reusable posterior model from calibration clouds (prep-g and prep-e).

    Returns a dict 'model' containing:
      - type: "1d"
      - mu_g, mu_e: complex means
      - u: unit complex axis along (mu_e - mu_g)
      - origin: complex (we use mu_g as origin for projection)
      - density params:
          * if method="kde": stores scipy gaussian_kde objects for g/e
          * if method="hist": stores centers + logpdf arrays for g/e

    Later, call posterior_weights_from_model(S, model, pi_e=...).
    """
    Sg = _as_complex_1d(Sg_cal)
    Se = _as_complex_1d(Se_cal)
    if require_finite:
        Sg = Sg[_isfinite_complex(Sg)]
        Se = Se[_isfinite_complex(Se)]
    if Sg.size < 10 or Se.size < 10:
        raise ValueError("Need at least ~10 finite calibration points in each class (g and e).")

    mu_g = np.mean(Sg)
    mu_e = np.mean(Se)
    d = mu_e - mu_g
    if not np.isfinite(d.real) or not np.isfinite(d.imag) or np.abs(d) < 1e-15:
        raise ValueError("Calibration means too close / non-finite; cannot define a stable 1D axis.")
    u = d / np.abs(d)   # unit complex axis
    origin = mu_g

    def project(z):
        z = np.asarray(z)
        # allow any shape complex array
        return np.real((z - origin) * np.conj(u))

    xg = project(Sg)
    xe = project(Se)

    method = str(method).lower()
    model = {
        "type": "A_1d",
        "method": method,
        "mu_g": complex(mu_g),
        "mu_e": complex(mu_e),
        "u": complex(u),
        "origin": complex(origin),
        "require_finite": bool(require_finite),
        "eps": float(eps),
    }

    if method == "kde":
        try:
            from scipy.stats import gaussian_kde
        except Exception as ex:
            raise ImportError("scipy is required for method='kde'. Install scipy or use method='hist'.") from ex

        kde_g = gaussian_kde(xg, bw_method=kde_bw)
        kde_e = gaussian_kde(xe, bw_method=kde_bw)

        model.update({
            "kde_bw": kde_bw,
            "kde_g": kde_g,
            "kde_e": kde_e,
        })
        return model

    if method == "hist":
        x_all = np.concatenate([xg, xe], axis=0)
        nb = _fd_bins(x_all) if (isinstance(bins, str) and bins.lower() == "fd") else int(bins)

        lo = np.nanmin(x_all)
        hi = np.nanmax(x_all)
        if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
            raise ValueError("Invalid projected calibration range for histogram density.")
        edges = np.linspace(lo, hi, nb + 1)
        centers = 0.5 * (edges[:-1] + edges[1:])

        hg, _ = np.histogram(xg, bins=edges, density=True)
        he, _ = np.histogram(xe, bins=edges, density=True)

        if smooth_sigma_bins and smooth_sigma_bins > 0:
            try:
                from scipy.ndimage import gaussian_filter1d
                hg = gaussian_filter1d(hg, float(smooth_sigma_bins), mode="nearest")
                he = gaussian_filter1d(he, float(smooth_sigma_bins), mode="nearest")
            except Exception:
                # small fallback smoother
                sig = float(smooth_sigma_bins)
                rad = int(np.ceil(4 * sig))
                kx = np.arange(-rad, rad + 1)
                ker = np.exp(-0.5 * (kx / sig) ** 2)
                ker /= np.sum(ker)
                hg = np.convolve(hg, ker, mode="same")
                he = np.convolve(he, ker, mode="same")

        hg = np.maximum(hg, eps)
        he = np.maximum(he, eps)

        model.update({
            "bins": nb,
            "centers": centers,
            "logpdf_g": np.log(hg),
            "logpdf_e": np.log(he),
            "smooth_sigma_bins": float(smooth_sigma_bins),
            "x_lo": float(lo),
            "x_hi": float(hi),
        })
        return model

    raise ValueError("method must be 'kde' or 'hist'.")


# ============================================================
# Option B: full 2D KDE in IQ
# ============================================================
def build_posterior_model_2d(
    Sg_cal,
    Se_cal,
    *,
    kde_bw="scott",
    require_finite=True,
    eps=1e-300,
):
    """
    Build a reusable 2D KDE posterior model from calibration clouds.

    Returns a dict 'model' containing:
      - type: "B_2d_kde"
      - mu_g, mu_e (for reference)
      - kde_g, kde_e: scipy gaussian_kde objects over (I,Q)
    """
    try:
        from scipy.stats import gaussian_kde
    except Exception as ex:
        raise ImportError("scipy is required for 2D KDE.") from ex

    Sg = _as_complex_1d(Sg_cal)
    Se = _as_complex_1d(Se_cal)

    Ig, Qg = Sg.real, Sg.imag
    Ie, Qe = Se.real, Se.imag

    if require_finite:
        mg = np.isfinite(Ig) & np.isfinite(Qg)
        me = np.isfinite(Ie) & np.isfinite(Qe)
        Ig, Qg = Ig[mg], Qg[mg]
        Ie, Qe = Ie[me], Qe[me]

    if Ig.size < 50 or Ie.size < 50:
        raise ValueError("2D KDE usually needs >= ~50 finite calibration points per class (more is better).")

    data_g = np.vstack([Ig, Qg])  # (2, Ng)
    data_e = np.vstack([Ie, Qe])  # (2, Ne)

    kde_g = gaussian_kde(data_g, bw_method=kde_bw)
    kde_e = gaussian_kde(data_e, bw_method=kde_bw)

    model = {
        "type": "B_2d_kde",
        "kde_bw": kde_bw,
        "kde_g": kde_g,
        "kde_e": kde_e,
        "mu_g": complex(np.mean(Ig) + 1j * np.mean(Qg)),
        "mu_e": complex(np.mean(Ie) + 1j * np.mean(Qe)),
        "require_finite": bool(require_finite),
        "eps": float(eps),
    }
    return model


# ============================================================
# Apply either model later to compute posterior weights
# ============================================================
def posterior_weights_from_model(S, model, *, pi_e=0.5, clip_llr=60.0):
    """
    Compute (w_g, w_e) for any complex array S using a model built above.
    """
    pi_e = float(pi_e)
    if not (0.0 < pi_e < 1.0):
        raise ValueError(f"pi_e must be in (0,1), got {pi_e}")
    pi_g = 1.0 - pi_e
    require_finite = bool(model.get("require_finite", True))
    eps = float(model.get("eps", 1e-300))

    S = np.asarray(S)
    if S.ndim == 0:
        S = S.reshape(1)
    if not np.iscomplexobj(S):
        S = S.astype(np.complex128, copy=False)

    if model["type"] == "A_1d":
        u = complex(model["u"])
        origin = complex(model["origin"])

        x = np.real((S - origin) * np.conj(u))
        finite = np.isfinite(x) if require_finite else np.ones_like(x, dtype=bool)

        if model["method"] == "kde":
            kde_g = model["kde_g"]
            kde_e = model["kde_e"]
            # gaussian_kde expects 1D array inputs; preserve shape afterward
            x_flat = x.ravel()
            pg = np.maximum(kde_g(x_flat), eps).reshape(x.shape)
            pe = np.maximum(kde_e(x_flat), eps).reshape(x.shape)
            llr = (np.log(pe) - np.log(pg)) + np.log(pi_e / pi_g)

        elif model["method"] == "hist":
            centers = model["centers"]
            logpg = np.interp(x, centers, model["logpdf_g"], left=model["logpdf_g"][0], right=model["logpdf_g"][-1])
            logpe = np.interp(x, centers, model["logpdf_e"], left=model["logpdf_e"][0], right=model["logpdf_e"][-1])
            llr = (logpe - logpg) + np.log(pi_e / pi_g)

        else:
            raise ValueError(f"Unknown A_1d method: {model['method']}")

        w_e = _stable_sigmoid(llr, clip=clip_llr)
        w_e = np.where(finite, w_e, np.nan)
        w_g = 1.0 - w_e
        return w_g, w_e

    if model["type"] == "B_2d_kde":
        kde_g = model["kde_g"]
        kde_e = model["kde_e"]

        I = S.real
        Q = S.imag
        finite = (np.isfinite(I) & np.isfinite(Q)) if require_finite else np.ones_like(I, dtype=bool)

        pts = np.vstack([I.ravel(), Q.ravel()])
        pg = np.maximum(kde_g(pts), eps).reshape(I.shape)
        pe = np.maximum(kde_e(pts), eps).reshape(I.shape)

        llr = (np.log(pe) - np.log(pg)) + np.log(pi_e / pi_g)
        w_e = _stable_sigmoid(llr, clip=clip_llr)
        w_e = np.where(finite, w_e, np.nan)
        w_g = 1.0 - w_e
        return w_g, w_e

    raise ValueError(f"Unknown model type: {model.get('type')}")

