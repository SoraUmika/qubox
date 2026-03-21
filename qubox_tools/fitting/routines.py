import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit, differential_evolution
import inspect
def generalized_fit(
    xdata,
    ydata,
    model,
    p0,
    bounds=(-np.inf, np.inf),
    plotting=False,
    eq_str="",
    plot_options=None,
    param_format="{:.4g}",
    global_opt=False,
    retry_on_fail=True,
    max_retries=8,
    random_scale=0.5,
    verbose=False,
    **kwargs,
):
    """
    Generalized fitting function using SciPy's curve_fit, with optional retries
    using modified initial guesses if the fit fails, and optional global optimization.

    Parameters
    ----------
    xdata : array_like
        Independent variable data.
    ydata : array_like
        Dependent variable data.
    model : callable
        The model function to fit. It must have the signature f(x, *params).
    p0 : array_like
        Initial guess for the parameters.
    bounds : 2-tuple of array_like, optional
        Lower and upper bounds on parameters (default: (-inf, inf)).
    plotting : bool, optional
        If True, plot the raw data and the best-fit curve (default: False).
    eq_str : str, optional
        A string describing the equation for the model. If not provided, the function
        will attempt to use the model's `equation` attribute or a line from its docstring.
    plot_options : dict, optional
        A dictionary to override default plotting options. Available keys are:
            - 'xlabel': label for the x-axis (default: 'x')
            - 'ylabel': label for the y-axis (default: 'y')
            - 'title':  plot title (default: '')
            - 'legend_fontsize': font size for the legend (default: 12)
            - 'legend_loc': legend location (default: 'best') -- ignored if 'legend_outside' is True
            - 'legend_outside': bool indicating if the legend should be placed
                                outside the main plot area to the right (default: False)
            - 'figsize': figure size (default: (8, 5))
            - 'xlim': limits for the x-axis (default: None)
            - 'ylim': limits for the y-axis (default: None)
            - 's': marker size for scatter (default: 5)
            - 'save_path': path to save the figure (default: None)
    param_format : str, optional
        A format string for each fitted parameter (default: "{:.4g}").
    global_opt : bool, optional
        If True, use differential evolution to find the global minimum before
        polishing with curve_fit. Requires finite bounds for all parameters (default: False).
    retry_on_fail : bool, optional
        If True, try different initial guesses p0 when the fit fails (default: True).
    max_retries : int, optional
        Maximum number of attempts (including the first attempt) (default: 8).
    random_scale : float, optional
        Typical fractional size of random perturbations around the original p0
        when generating alternative starting points (default: 0.5).
    verbose : bool, optional
        If True, print information about retry attempts (default: False).
    **kwargs : dict, optional
        Additional keyword arguments to pass to curve_fit (e.g. maxfev).

    Returns
    -------
    popt : array or None
        Optimized parameters if the fit is successful; otherwise, None.
    pcov : 2D array or None
        The estimated covariance of popt if the fit is successful; otherwise, None.
    """

    # Normalize p0 and bounds to arrays
    p0 = np.asarray(p0, dtype=float)
    n_params = p0.size

    lb, ub = bounds
    if np.isscalar(lb):
        lb = np.full(n_params, lb, dtype=float)
    else:
        lb = np.asarray(lb, dtype=float)
    if np.isscalar(ub):
        ub = np.full(n_params, ub, dtype=float)
    else:
        ub = np.asarray(ub, dtype=float)

    if lb.shape != p0.shape or ub.shape != p0.shape:
        raise ValueError("Shapes of p0 and bounds must match.")

    if global_opt:
        if not (np.all(np.isfinite(lb)) and np.all(np.isfinite(ub))):
            raise ValueError("global_opt=True requires finite lower and upper bounds for all parameters.")

        if verbose:
            print("[generalized_fit] Running global optimization (differential_evolution)...")

        def _sse_cost(params):
            """Sum of squared errors cost function for DE."""
            try:
                y_pred = model(xdata, *params)
                if not np.all(np.isfinite(y_pred)):
                    return np.inf
                return np.sum((ydata - y_pred) ** 2)
            except Exception:
                return np.inf

        # Prepare bounds for differential_evolution: list of (min, max)
        de_bounds = list(zip(lb, ub))
        
        # Run differential evolution
        res_global = differential_evolution(_sse_cost, de_bounds, seed=None)

        if res_global.success:
            if verbose:
                print(f"[generalized_fit] Global search found candidate: {res_global.x}")
            # Update p0 to the globally found best parameters
            p0 = res_global.x
        else:
            if verbose:
                print(f"[generalized_fit] Global search warning: {res_global.message}")

    # Helper to clip and deduplicate candidate p0s
    tried_p0s = []

    def _register_candidate(candidate):
        candidate = np.asarray(candidate, dtype=float)
        candidate = np.clip(candidate, lb, ub)
        for t in tried_p0s:
            if np.allclose(candidate, t, rtol=1e-8, atol=1e-10):
                return None
        tried_p0s.append(candidate)
        return candidate

    # Build candidate list of p0s
    candidates = []

    # 1) Original p0
    cand = _register_candidate(p0)
    if cand is not None:
        candidates.append(cand)

    if retry_on_fail and max_retries > 1:
        # 2) Midpoint of finite bounds, where available
        finite_mask = np.isfinite(lb) & np.isfinite(ub)
        if np.any(finite_mask):
            mid = p0.copy()
            mid[finite_mask] = 0.5 * (lb[finite_mask] + ub[finite_mask])
            cand = _register_candidate(mid)
            if cand is not None:
                candidates.append(cand)

        # 3) Random perturbations around p0, clipped to bounds
        rng = np.random.default_rng()
        while len(candidates) < max_retries:
            jitter = rng.normal(loc=0.0, scale=random_scale, size=n_params)
            cand = p0 * (1.0 + jitter)

            # Handle p0 == 0 separately: sample inside bounds (if finite),
            # otherwise use small random values.
            zero_mask = (p0 == 0.0)
            if np.any(zero_mask):
                bounded = zero_mask & np.isfinite(lb) & np.isfinite(ub)
                if np.any(bounded):
                    cand[bounded] = rng.uniform(lb[bounded], ub[bounded])
                unbounded = zero_mask & ~bounded
                if np.any(unbounded):
                    cand[unbounded] = rng.normal(loc=0.0, scale=1.0, size=np.sum(unbounded))

            cand = _register_candidate(cand)
            if cand is not None:
                candidates.append(cand)
    else:
        # Only original p0 will be used
        candidates = [p0]

    popt, pcov = None, None
    last_error = None

    # Try each candidate p0 in turn
    for attempt_idx, p0_try in enumerate(candidates, start=1):
        try:
            if verbose:
                print(f"[generalized_fit] Attempt {attempt_idx}/{len(candidates)} with p0={p0_try}")
            popt, pcov = curve_fit(
                model,
                xdata,
                ydata,
                p0=p0_try,
                bounds=(lb, ub),
                **kwargs,
            )
            if verbose and attempt_idx > 1:
                print(f"[generalized_fit] Fit succeeded on attempt {attempt_idx}.")
            break
        except Exception as e:
            last_error = e
            if verbose:
                print(f"[generalized_fit] Attempt {attempt_idx} failed: {e!r}")
            popt, pcov = None, None

    if popt is None and verbose and last_error is not None:
        print("[generalized_fit] Fitting failed after all attempts. Last error:", last_error)

    # Determine the equation string to display.
    if not eq_str:
        if hasattr(model, "equation"):
            eq_str = model.equation
        elif model.__doc__:
            doc_lines = [line.strip() for line in model.__doc__.splitlines() if line.strip()]
            eq_candidates = [line for line in doc_lines if '=' in line]
            eq_str = eq_candidates[0] if eq_candidates else doc_lines[0]
        else:
            eq_str = "Model Equation"

    # If fitting succeeded, build the parameter string.
    if popt is not None:
        sig = inspect.signature(model)
        param_names = list(sig.parameters.keys())[1:]  # skip x
        if len(param_names) != len(popt):
            param_names = [f"p{i}" for i in range(len(popt))]
        param_str = "\n".join(
            f"{name} = {param_format.format(val)}"
            for name, val in zip(param_names, popt)
        )
        legend_text = f"{eq_str}\n{param_str}"
    else:
        failure_msg = "Fit failed."
        if last_error is not None:
            failure_msg += f" Last error: {last_error}"
        legend_text = f"{eq_str}\n{failure_msg}"

    # Default plotting options.
    default_plot_options = {
        'xlabel': 'x',
        'ylabel': 'y',
        'title': '',
        'legend_fontsize': 12,
        'legend_loc': 'best',
        'legend_outside': True,
        'figsize': (8, 5),
        'xlim': None,
        'ylim': None,
        's': 5,
        'save_path': None
    }
    if plot_options is not None:
        default_plot_options.update(plot_options)

    # Plot the raw data and, if available, the best-fit curve.
    if plotting:
        plt.figure(figsize=default_plot_options['figsize'])
        plt.scatter(xdata, ydata, label="Data", s=default_plot_options['s'])
        if popt is not None:
            x_fit = np.linspace(np.min(xdata), np.max(xdata), 1000)
            y_fit = model(x_fit, *popt)
            plt.plot(x_fit, y_fit, label=legend_text, lw=2)
        else:
            # Plot an empty line to show the legend if fit failed.
            plt.plot([], [], label=legend_text, lw=2)

        plt.xlabel(default_plot_options['xlabel'])
        plt.ylabel(default_plot_options['ylabel'])
        if default_plot_options['xlim'] is not None:
            plt.xlim(default_plot_options['xlim'])
        if default_plot_options['ylim'] is not None:
            plt.ylim(default_plot_options['ylim'])
        if default_plot_options['title']:
            plt.title(default_plot_options['title'])
        plt.grid()

        if default_plot_options['legend_outside']:
            plt.legend(
                bbox_to_anchor=(1.05, 1),
                loc='upper left',
                fontsize=default_plot_options['legend_fontsize'],
                borderaxespad=0.0
            )
        else:
            plt.legend(
                loc=default_plot_options['legend_loc'],
                fontsize=default_plot_options['legend_fontsize']
            )

        plt.tight_layout()

        if default_plot_options['save_path']:
            plt.savefig(default_plot_options['save_path'], bbox_inches='tight')

        plt.show()

    return popt, pcov


def fit_and_wrap(
    xdata,
    ydata,
    model,
    p0,
    *,
    model_name: str | None = None,
    bounds=(-np.inf, np.inf),
    plotting: bool = False,
    **kwargs,
):
    """Call ``generalized_fit`` and wrap the result in a ``FitResult``.

    Parameters
    ----------
    xdata, ydata, model, p0, bounds, plotting, **kwargs
        Forwarded to :func:`generalized_fit`.
    model_name : str, optional
        Human-readable name stored in ``FitResult.model_name``.
        Defaults to ``model.__name__``.

    Returns
    -------
    FitResult
        A typed result container with fitted parameters, uncertainties,
        R-squared, and residuals.  On fit failure the ``params`` dict is
        empty and ``metadata["failed"]`` is ``True``.
    """
    from qubox.legacy.experiments.result import FitResult

    popt, pcov = generalized_fit(
        xdata, ydata, model, p0, bounds=bounds, plotting=plotting, **kwargs,
    )

    name = model_name or getattr(model, "__name__", "model")

    if popt is None:
        return FitResult(
            model_name=name,
            params={},
            success=False,
            reason="All fit attempts failed (curve_fit did not converge)",
            metadata={"failed": True},
        )

    # Extract parameter names from model signature
    sig = inspect.signature(model)
    param_names = list(sig.parameters.keys())[1:]  # skip x
    if len(param_names) != len(popt):
        param_names = [f"p{i}" for i in range(len(popt))]

    params = dict(zip(param_names, popt.tolist()))

    # Uncertainties from covariance diagonal
    uncertainties = {}
    if pcov is not None:
        try:
            perr = np.sqrt(np.diag(pcov))
            uncertainties = dict(zip(param_names, perr.tolist()))
        except Exception:
            pass

    # R-squared
    r_squared = None
    try:
        y_pred = model(np.asarray(xdata), *popt)
        ss_res = np.sum((np.asarray(ydata) - y_pred) ** 2)
        ss_tot = np.sum((np.asarray(ydata) - np.mean(ydata)) ** 2)
        if ss_tot > 0:
            r_squared = 1.0 - ss_res / ss_tot
    except Exception:
        pass

    # Residuals
    residuals = None
    try:
        residuals = np.asarray(ydata) - model(np.asarray(xdata), *popt)
    except Exception:
        pass

    # Store the model equation string in metadata for use in plot legends
    eq_str = ""
    if hasattr(model, "equation"):
        eq_str = model.equation
    elif model.__doc__:
        doc_lines = [line.strip() for line in model.__doc__.splitlines() if line.strip()]
        eq_candidates = [line for line in doc_lines if '=' in line]
        eq_str = eq_candidates[0] if eq_candidates else ""

    return FitResult(
        model_name=name,
        params=params,
        success=True,
        reason=None,
        uncertainties=uncertainties,
        r_squared=r_squared,
        residuals=residuals,
        metadata={"equation": eq_str} if eq_str else {},
    )


def build_fit_legend(fit, *, param_format="{:.4g}"):
    """Build a legend string with the model equation and fitted parameter values.

    Mirrors the legend text that ``generalized_fit`` produces when
    ``plotting=True``, but works from a :class:`FitResult` object so it
    can be used in experiment ``plot()`` methods.

    Parameters
    ----------
    fit : FitResult
        Fit result (from ``fit_and_wrap``).
    param_format : str
        Format string for parameter values (default ``"{:.4g}"``).

    Returns
    -------
    str
        Multi-line string: equation on line 1, one ``name = value`` per
        subsequent line.  Returns empty string if *fit* has no params.
    """
    if not fit or not fit.params:
        return ""

    eq_str = fit.metadata.get("equation", "") if fit.metadata else ""
    param_str = "\n".join(
        f"{name} = {param_format.format(val)}"
        for name, val in fit.params.items()
    )
    if eq_str:
        return f"{eq_str}\n{param_str}"
    return param_str
