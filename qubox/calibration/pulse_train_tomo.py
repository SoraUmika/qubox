"""Pulse-train tomography — QUA experiment execution.

QUA-dependent functions (``make_state_prep``, ``run_pulse_train_tomography``)
live here.  Pure analysis functions have moved to
``qubox_tools.fitting.pulse_train`` and are re-exported below for
backward compatibility.
"""
from __future__ import annotations

import numpy as np
from qm.qua import play, align, declare, for_
from IPython.display import clear_output

# Canonical analysis functions — re-export for backward compat
from qubox_tools.fitting.pulse_train import (  # noqa: F401
    apply_relaxation,
    apply_rz,
    apply_theta_phi_correction,
    default_r0_dict,
    extract_bloch_from_tomo,
    fit_params_to_qubitrotation_knobs,
    fit_pulse_train_model,
    model_base,
    model_with_zeta,
    model_with_zeta_and_relax,
    plot_meas_vs_fit,
    pretty_knob_report,
    safe_normalize,
    wrap_pm_pi,
)


# ---------------------------------------------------------------------------
# QUA state-prep wrapper
# ---------------------------------------------------------------------------
def make_state_prep(prep_fn, arb_rot, N: int):
    """Factory for experiment.qubit_state_tomography callback.

    Parameters
    ----------
    prep_fn : callable or None
        Plays primitive QUA pulses for the initial state.
    arb_rot : object
        Gate-under-test with a ``.play()`` method.
    N : int
        Number of gate repetitions.

    Uses QUA ``for_()`` loop so compiled program size is O(1) regardless of N.
    """
    N = int(N)

    def state_prep():
        if prep_fn is not None:
            prep_fn()
            align()
        if N > 0:
            n_var = declare(int)
            with for_(n_var, 0, n_var < N, n_var + 1):
                arb_rot.play()
            align()

    return state_prep


# ---------------------------------------------------------------------------
# QUA experiment runner
# ---------------------------------------------------------------------------
def run_pulse_train_tomography(
    *,
    experiment,
    arb_rot,
    prep_defs: dict,
    N_values,
    n_avg: int,
    verbose: bool = True,
    sanity_check: bool = True,
):
    """Bundled pulse-train tomography: one program call per N value.

    Each call bundles all K initial-state preps.
    Total calls = len(N_values) + 1 sanity.

    Parameters
    ----------
    experiment : object
        Must have ``.qubit_state_tomography(preps, n_avg)`` method.
    arb_rot : object
        Gate-under-test with ``.play()``.
    prep_defs : dict[str, callable | None]
        Maps state labels to QUA prep callables.
    N_values : array-like of int
        Number of pulse repetitions to sweep.
    n_avg : int
        Averaging count.
    verbose : bool
        Print progress.
    sanity_check : bool
        Run prep-only sanity check first.

    Returns
    -------
    meas : dict[str, ndarray]
        Shape ``(len(N_values), 3)`` per key.
    prep_check : dict[str, ndarray] | None
        Sanity-check Bloch vectors (only if ``sanity_check=True``).
    """
    N_values = np.asarray(N_values, int)
    keys = list(prep_defs.keys())
    K = len(keys)

    # ------------------------------------------------------------------
    # 1) Sanity check: bundle all K prep-only callables into one call
    # ------------------------------------------------------------------
    prep_check = None
    if sanity_check:
        sanity_preps = []
        for key in keys:
            pfn = prep_defs[key]

            def _make_sanity(fn=pfn):
                def _prep_only():
                    if fn is not None:
                        fn()
                    align()
                return _prep_only

            sanity_preps.append(_make_sanity())

        if verbose:
            print(f"[sanity] Running {K} prep-only tomos in 1 call …")
        rr = experiment.qubit_state_tomography(sanity_preps, int(n_avg))
        bloch_all = extract_bloch_from_tomo(rr)

        prep_check = {}
        for i, key in enumerate(keys):
            prep_check[key] = bloch_all[i]
            print("Prep sanity check (tomography after prep only, N=0):")
        for k, v in prep_check.items():
            print(f"  {k:>2}: (sx,sy,sz)=({v[0]:+.3f},{v[1]:+.3f},{v[2]:+.3f})")

    # ------------------------------------------------------------------
    # 2) Main sweep: one call per N, bundling all K preps
    # ------------------------------------------------------------------
    meas = {key: np.zeros((len(N_values), 3), float) for key in keys}

    for ni, N in enumerate(N_values):
        clear_output(wait=True)

        preps_for_N = []
        for key in keys:
            preps_for_N.append(make_state_prep(prep_defs[key], arb_rot, int(N)))

        if verbose:
            print(f"[RUN N={int(N):>3} ({ni+1}/{len(N_values)})] {K} preps (n_avg={n_avg})")

        rr = experiment.qubit_state_tomography(preps_for_N, int(n_avg))
        bloch_all = extract_bloch_from_tomo(rr)

        for ki, key in enumerate(keys):
            meas[key][ni] = bloch_all[ki]

    if verbose:
        print("RUN complete.")
    return meas, prep_check
