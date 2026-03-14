import numpy as np
import matplotlib.pyplot as plt
from math import factorial
from ..fitting.routines import generalized_fit
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 (needed for 3D proj)
from matplotlib.widgets import CheckButtons
def plot_bloch_states(
    states,
    labels=None,
    colors=None,
    title="Bloch sphere",
    sphere_alpha=0.4,
    arrow_scale=1.0,
):
    """
    Plot one or more Bloch vectors on a Bloch sphere, with interactive
    checkboxes to toggle visibility of each state.

    Parameters
    ----------
    states : array_like
        Either shape (3,) for a single state [sx, sy, sz],
        or shape (N, 3) for N states.
    labels : list of str, optional
        Base labels for each state. Must have length N if provided.
    colors : list of color specs, optional
        Colors for each state (e.g. 'r', 'C0', '#ff00ff').
        If None, uses Matplotlib's default color cycle.
    title : str, optional
        Title for the plot.
    sphere_alpha : float, optional
        Transparency for the Bloch sphere wireframe.
    arrow_scale : float, optional
        Scale factor for arrow lengths (1.0 = exact Bloch vector length).

    Returns
    -------
    fig, ax_sphere
        The figure and the 3D axis for the Bloch sphere.
    """
    states = np.asarray(states, dtype=float)
    if states.ndim == 1:
        states = states[None, :]  # shape (1, 3)

    n_states = states.shape[0]

    # Base labels (used for arrows)
    if labels is None:
        base_labels = [f"state {i}" for i in range(n_states)]
    else:
        if len(labels) != n_states:
            raise ValueError("labels must have same length as number of states")
        base_labels = list(labels)

    # Build checkbox labels with state values (fixed 2 decimal places)
    vec_strs = [f"({sx:.2f}, {sy:.2f}, {sz:.2f})" for sx, sy, sz in states]
    check_labels = [f"{lbl} {vec}" for lbl, vec in zip(base_labels, vec_strs)]

    if colors is None:
        # use default color cycle
        prop_cycle = plt.rcParams["axes.prop_cycle"]
        color_cycle = list(prop_cycle.by_key().get("color", []))
        colors = [color_cycle[i % len(color_cycle)] for i in range(n_states)]
    elif len(colors) != n_states:
        raise ValueError("colors must have same length as number of states")

    # --- Figure with two subplots: left Bloch sphere, right checkboxes ---
    fig = plt.figure(figsize=(8, 6))
    ax_sphere = fig.add_subplot(121, projection="3d")
    ax_check = fig.add_subplot(122)
    ax_check.axis("off")

    # --- Draw Bloch sphere on ax_sphere ---
    u = np.linspace(0, 2 * np.pi, 60)
    v = np.linspace(0, np.pi, 30)
    x = np.outer(np.cos(u), np.sin(v))
    y = np.outer(np.sin(u), np.sin(v))   # <-- this
    z = np.outer(np.ones_like(u), np.cos(v))


    ax_sphere.plot_wireframe(
        x, y, z, rcount=15, ccount=15, linewidth=0.5, alpha=sphere_alpha
    )

    # Axes lines
    ax_sphere.plot([-1, 1], [0, 0], [0, 0], "k-", linewidth=1)
    ax_sphere.plot([0, 0], [-1, 1], [0, 0], "k-", linewidth=1)
    ax_sphere.plot([0, 0], [0, 0], [-1, 1], "k-", linewidth=1)

    # Basis labels (|g> at -z, |e> at +z)
    ax_sphere.text(0, 0, 1.1, r"$|e\rangle$", ha="center", va="center")
    ax_sphere.text(0, 0, -1.2, r"$|g\rangle$", ha="center", va="center")
    ax_sphere.text(1.1, 0, 0, r"$+X$", ha="center", va="center")
    ax_sphere.text(-1.2, 0, 0, r"$-X$", ha="center", va="center")
    ax_sphere.text(0, 1.1, 0, r"$+Y$", ha="center", va="center")
    ax_sphere.text(0, -1.2, 0, r"$-Y$", ha="center", va="center")

    # --- Plot each state as an arrow (store artists for toggling) ---
    arrows = []
    texts = []
    for (sx, sy, sz), base_label, color in zip(states, base_labels, colors):
        sx_p, sy_p, sz_p = arrow_scale * np.array([sx, sy, sz])

        q = ax_sphere.quiver(
            0, 0, 0,
            sx_p, sy_p, sz_p,
            arrow_length_ratio=0.1,
            linewidth=2,
            color=color,
        )
        # Arrow text: only base label, no state values
        txt = ax_sphere.text(
            1.05 * sx_p,
            1.05 * sy_p,
            1.05 * sz_p,
            base_label,
            ha="center",
            va="center",
            color=color,
        )
        arrows.append(q)
        texts.append(txt)

    # Cosmetics on sphere
    ax_sphere.set_box_aspect([1, 1, 1])
    ax_sphere.set_xlim([-1.1, 1.1])
    ax_sphere.set_ylim([-1.1, 1.1])
    ax_sphere.set_zlim([-1.1, 1.1])
    ax_sphere.set_xlabel(r"$\langle \sigma_x \rangle$")
    ax_sphere.set_ylabel(r"$\langle \sigma_y \rangle$")
    ax_sphere.set_zlabel(r"$\langle \sigma_z \rangle$")
    ax_sphere.set_title(title)

    # --- Checkboxes for toggling states ---
    visibility = [True] * n_states

    check = CheckButtons(
        ax_check,
        labels=check_labels,
        actives=visibility,
    )

    # color the checkbox labels to match arrows
    for txt_lbl, color in zip(check.labels, colors):
        txt_lbl.set_color(color)

    # map checkbox label â†’ index
    label_to_idx = {lbl: i for i, lbl in enumerate(check_labels)}

    def toggle_state(label):
        idx = label_to_idx[label]
        vis = not arrows[idx].visible
        arrows[idx].set_visible(vis)
        texts[idx].set_visible(vis)
        fig.canvas.draw_idle()

    check.on_clicked(toggle_state)

    plt.tight_layout()
    plt.show()

    return fig, ax_sphere


def display_fock_populations(
    fock_states,
    fock_pops,
    fit_alpha=False,
    label_size=14,
    title_size=16,
    tick_size=12,
    legend_size=12,
    label="label",
    plotting=True,
    baseline: float | None = None,
    normalize: bool = False,
    max_alpha=20,
    title: str | None = None,
):
    """
    Display Fock populations and (optionally) fit them to a coherent-state
    Poisson distribution with scale and offset:

        p_n â‰ˆ offset + scale * exp(-Î») Î»^n / n!,   Î» = |alpha|^2

    Parameters
    ----------
    fock_states : array-like
        List/array of n values (0,1,2,...).
    fock_pops : array-like
        Measured populations or amplitudes for each n. Can be signed.
        If `baseline` is not None, we first subtract it:
            pops_used = fock_pops - baseline
        All fitting uses `pops_used`.
    fit_alpha : bool, optional
        If True, fit to the Poisson model and extract |alpha|.
    label_size, title_size, tick_size, legend_size : int, optional
        Font sizes for plot.
    label : str, optional
        Extra label appended to the plot title.
    plotting : bool, optional
        If True, make a bar plot and overlay the fit.
    baseline : float or None, optional
        If not None, subtract this constant from all fock_pops before
        plotting and fitting. Useful for removing a known DC offset.
    normalize : bool, optional
        If True, also compute a normalized set of populations,

            p_n^(norm) = pops_used / sum(pops_used),

        and plot these on a secondary y-axis. Normalization is only used
        for plotting; the fit still uses the unnormalized pops_used.
    title : str or None, optional
        If provided, use this as the plot title. If None, construct the title
        from `label` and fit results (default behavior).

    Returns
    -------
    fit_params : dict or None
        Dictionary containing fit parameters if fit_alpha is True and the fit succeeds:
        - 'alpha': Extracted |alpha|
        - 'lambda': Î» = |alpha|Â²
        - 'scale': Amplitude scaling factor
        - 'offset': Baseline offset
        Returns None if fit_alpha is False or the fit fails.
    """

    n = np.asarray(fock_states, dtype=float)
    pops_raw = np.asarray(fock_pops, dtype=float)

    # Apply baseline correction if requested
    if baseline is not None:
        pops = pops_raw - baseline
    else:
        pops = pops_raw

    # Basic sanity: ensure integer n for factorial
    n_int = n.astype(int)

    # Optional normalized pops (for secondary axis only)
    pops_norm = None
    if normalize:
        total = np.sum(pops)
        # Only normalize if the sum is reasonably nonzero
        if np.abs(total) > 1e-15:
            pops_norm = pops / total
        else:
            pops_norm = None  # skip normalized axis if invalid

    fit_params = None
    fit_curve = None

    # --- Fit to Poisson model (using baseline-corrected, but not normalized pops) ---
    if fit_alpha:
        def poisson_with_offset_model(n_arr, lam, scale, offset):
            n_arr = np.asarray(n_arr, dtype=float)
            n_int_local = n_arr.astype(int)
            facs = np.array([factorial(k) for k in n_int_local], dtype=float)
            pois = np.exp(-lam) * (lam**n_arr) / facs
            return offset + scale * pois

        y = pops

        # Initial guess for Î» from weighted mean of n
        if np.allclose(y, 0):
            lam0 = 0.5
        else:
            w = np.abs(y)
            w_sum = np.sum(w)
            if w_sum == 0:
                lam0 = 0.5
            else:
                w /= w_sum
                lam0 = float(np.sum(n_int * w))

        scale0 = float(np.max(y) - np.min(y)) if np.any(y != 0) else 1.0
        offset0 = float(np.mean(y))

        # Determine data range for setting finite bounds for global_opt
        y_min, y_max = np.min(y), np.max(y)
        y_span = (y_max - y_min) if (y_max != y_min) else 1.0

        # Bounds for lambda = |alpha|^2. Max |alpha|=20 => lambda=400.
        lam_bounds = (1e-9, max_alpha**2)
        # Bounds for scale and offset based on data magnitude
        scale_bounds = (-50.0 * abs(y_span), 50.0 * abs(y_span))
        offset_bounds = (y_min - 10.0 * abs(y_span), y_max + 10.0 * abs(y_span))

        lower_bounds = np.array([lam_bounds[0], scale_bounds[0], offset_bounds[0]], dtype=float)
        upper_bounds = np.array([lam_bounds[1], scale_bounds[1], offset_bounds[1]], dtype=float)

        p0 = np.array([max(lam0, 1e-3), scale0, offset0], dtype=float)

        pois_fit_res = generalized_fit(
            n_int,
            y,
            poisson_with_offset_model,
            p0,
            bounds=(lower_bounds, upper_bounds),
            global_opt=True,
            plotting=False,
            eq_str="offset + scale * exp(-Î») Î»^n / n!",
        )

        lam_fit, scale_fit, offset_fit = pois_fit_res[0]
        lam_fit = max(lam_fit, 0.0)
        alpha_fit = float(np.sqrt(lam_fit))

        fit_params = {
            'alpha': alpha_fit,
            'lambda': float(lam_fit),
            'scale': float(scale_fit),
            'offset': float(offset_fit)
        }

        fit_curve = poisson_with_offset_model(n_int, lam_fit, scale_fit, offset_fit)

    # --- Plotting ---
    if plotting:
        fig, ax1 = plt.subplots(figsize=(8, 5))

        # Primary axis: baseline-corrected raw pops
        bars = ax1.bar(n_int, pops, alpha=0.7, label="measured")
        ax1.set_xlabel(r"Fock state $|n\rangle$", fontsize=label_size)
        ax1.set_ylabel("Population / amplitude", fontsize=label_size)

        # Overlay Poisson fit (still on primary axis)
        if fit_alpha and (fit_curve is not None):
            alpha_fit = fit_params['alpha']
            scale_fit = fit_params['scale']
            offset_fit = fit_params['offset']
            line_fit, = ax1.plot(
                n_int,
                fit_curve,
                "o-",
                linewidth=2,
                label=(rf"Poisson fit: $|\alpha| \approx {alpha_fit:.2f}$" + "\n" +
                       rf"scale = {scale_fit:.3f}, offset = {offset_fit:.3f}"),
            )
        else:
            line_fit = None

        # Secondary axis: normalized pops, if requested and valid
        ax2 = None
        line_norm = None
        if normalize and (pops_norm is not None):
            ax2 = ax1.twinx()
            line_norm, = ax2.plot(
                n_int,
                pops_norm,
                "s--",
                linewidth=2,
                label="normalized (Î£=1)",
            )
            ax2.set_ylabel("Normalized population", fontsize=12)

        # Title
        if title is None:
            # Default title construction
            plot_title = f"Fock Populations {label}"
            if fit_alpha and (fit_params is not None):
                alpha_fit = fit_params['alpha']
                plot_title += rf"  (|alpha| â‰ˆ {alpha_fit:.2f})"
        else:
            # User-provided title
            plot_title = title
        ax1.set_title(plot_title, fontsize=title_size)

        # X-axis ticks and general cosmetics
        ax1.set_xticks(n_int)
        ax1.set_xticklabels([rf"$|{i}\rangle$" for i in n_int])
        ax1.tick_params(axis="both", which="major", labelsize=tick_size)
        if ax2 is not None:
            ax2.tick_params(axis="both", which="major", labelsize=tick_size)

        ax1.grid(axis="y", linestyle='--', alpha=0.7)

        # Combined legend from both axes
        handles1, labels1 = ax1.get_legend_handles_labels()
        handles = handles1
        labels_ = labels1
        if ax2 is not None:
            handles2, labels2 = ax2.get_legend_handles_labels()
            handles = handles1 + handles2
            labels_ = labels1 + labels2

        if handles:
            ax1.legend(handles, labels_, fontsize=legend_size, loc="best")

        fig.tight_layout()
        plt.show()

    return fit_params


from matplotlib.colors import TwoSlopeNorm

def plot_wigner(W: np.ndarray,
                x_vals: np.ndarray,
                p_vals: np.ndarray) -> None:
    """
    Plot a Wigner function W(alpha) on the (Re alpha, Im alpha) plane.

    Parameters
    ----------
    W : 2D array, shape (len(p_vals), len(x_vals))
        Wigner values on the grid.
    x_vals : 1D array of length W.shape[1]
        Points along the real axis.
    p_vals : 1D array of length W.shape[0]
        Points along the imaginary axis.
    """
    if x_vals is None or p_vals is None:
        raise ValueError("x_vals and p_vals must be provided for plotting.")
    if W.shape != (len(p_vals), len(x_vals)):
        raise ValueError(f"W.shape={W.shape} "
                         f"does not match (len(p_vals),len(x_vals))="
                         f"({len(p_vals)},{len(x_vals)})")

    fig, ax = plt.subplots(figsize=(5, 4.5))
    norm = TwoSlopeNorm(vcenter=0.0)  # diverging cmap centered on 0
    im = ax.imshow(
        W,
        origin="lower",
        extent=[x_vals[0], x_vals[-1], p_vals[0], p_vals[-1]],
        cmap="RdBu_r",
        norm=norm,
        interpolation="nearest"
    )

    ax.set_xlabel(r"$\mathrm{Re}\,\alpha$")
    ax.set_ylabel(r"$\mathrm{Im}\,\alpha$")
    ax.set_title(r"Wigner function  $W(\alpha)$")

    cbar = fig.colorbar(im, ax=ax, fraction=0.045)
    cbar.set_label(r"$W$  (arb. units)")

    plt.tight_layout()
    plt.show()
    
def plot_IQ(datasets, labels=None, ax=None, **scatter_kwargs):
    """
    Scatter-plot one or more complex IQ datasets on the I-Q plane.

    Parameters
    ----------
    datasets : array_like of complex or list/tuple thereof
        Your IQ shots as complex numbers (I + 1jÂ·Q). You can pass a single
        array or a list of arrays: [S_g, S_e, ...].
    labels : list of str, optional
        Labels for each dataset. If provided, len(labels) must match len(datasets).
    ax : matplotlib.axes.Axes, optional
        If given, plot into this Axes; otherwise a new figure/axes is created.
    scatter_kwargs : keyword arguments passed to plt.scatter.
        You can pass scalars (same styling for all) or lists/tuples
        of the same length as `datasets` to style each separately.
        E.g. color=['blue','red'], alpha=[0.3,0.3].
    """
    # Wrap single array into list
    if not isinstance(datasets, (list, tuple)):
        datasets = [datasets]

    n = len(datasets)
    # Handle labels
    if labels is None:
        labels = [None]*n
    elif len(labels) != n:
        raise ValueError(f"labels length ({len(labels)}) != number of datasets ({n})")

    # Create axes if needed
    if ax is None:
        fig, ax = plt.subplots()

    # Plot each dataset
    for idx, (S, lbl) in enumerate(zip(datasets, labels)):
        I = np.real(S)
        Q = np.imag(S)
        # build perâ€dataset kwargs: if value is list/tuple, take element[idx]
        this_kwargs = {}
        for key, val in scatter_kwargs.items():
            if isinstance(val, (list, tuple)):
                if len(val) != n:
                    raise ValueError(f"scatter_kwargs['{key}'] length must be {n}")
                this_kwargs[key] = val[idx]
            else:
                this_kwargs[key] = val

        ax.scatter(I, Q, label=lbl, **this_kwargs)

    # Styling
    ax.set_xlabel("I (real)")
    ax.set_ylabel("Q (imag)")
    ax.set_aspect("equal", adjustable="datalim")
    ax.axhline(0, color="gray", lw=0.5)
    ax.axvline(0, color="gray", lw=0.5)

    # Legend if any labels were provided
    if any(labels):
        ax.legend()

    return ax
