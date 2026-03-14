
from qm.qua import *
from qualang_tools.loops import from_array
from ..macros.measure import measureMacro
from ..macros.sequence import sequenceMacros
import numpy as np


def qubit_state_tomography(
    state_prep,
    therm_clks,
    n_avg,
    *,
    qb_el: str | None = None,
    x90="x90",
    yn90="yn90",
    bindings: "ExperimentBindings | None" = None,
):
    """
    Return a QUA program that runs qubit state tomography for one or more
    state preparations under a single program call.

    Parameters
    ----------
    state_prep : callable **or** list/tuple of callables
        Each callable prepares the qubit (and anything coupled to it) before
        each tomography shot.  When a single callable is passed, the program
        behaves identically to the original single-prep version.
        When a sequence of callables is passed, the program loops over all
        of them inside each averaging iteration.
    therm_clks : int
        Wait time (clock cycles) after each axis measurement.
    n_avg : int
        Number of averaging iterations.
    qb_el : str, optional
        Qubit element name.
    x90 : str, optional
        +pi_val/2 about X pulse name (used for measuring \u03c3_y).
    yn90 : str, optional
        -pi_val/2 about Y pulse name (used for measuring \u03c3_x).

    Returns
    -------
    prog : QUA program
        Ready to run.

    Stream outputs
    --------------
    When *one* state_prep callable is provided (backward-compatible):
        state_x, state_y, state_z : scalar (averaged over n_avg)
        I_axes_avg, Q_axes_avg    : shape (3,) averaged over n_avg

    When *P* state_prep callables are provided:
        state_x, state_y, state_z : shape (P,) averaged over n_avg
        I_axes_avg, Q_axes_avg    : shape (P, 3) averaged over n_avg
    """
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        qb_el = qb_el or _names.get("qubit", "__qb")
    elif qb_el is None:
        raise ValueError("qb_el is required when bindings are not provided")

    # Normalise to a list
    if callable(state_prep):
        preps = [state_prep]
    else:
        preps = list(state_prep)
    n_preps = len(preps)
    if n_preps == 0:
        raise ValueError("state_prep must be a callable or a non-empty sequence of callables")

    with program() as prog:
        # loop / temp vars
        n = declare(int)
        state_x = declare(bool)
        state_y = declare(bool)
        state_z = declare(bool)

        # streams
        state_x_st = declare_stream()
        state_y_st = declare_stream()
        state_z_st = declare_stream()
        n_st     = declare_stream()

        I = declare(fixed)
        Q = declare(fixed)
        I_st = declare_stream()
        Q_st = declare_stream()

        with for_(n, 0, n < n_avg, n + 1):
            for prep_fn in preps:
                sequenceMacros.qubit_state_tomography(state_x, state_prep=prep_fn, state_st=state_x_st,
                                                      therm_clks=therm_clks, targets=[I, Q], axis="x", qb_el=qb_el, x90=x90, yn90=yn90)
                save(I, I_st)
                save(Q, Q_st)
                sequenceMacros.qubit_state_tomography(state_y, state_prep=prep_fn, state_st=state_y_st,
                                                      therm_clks=therm_clks, targets=[I, Q], axis="y", qb_el=qb_el, x90=x90, yn90=yn90)
                save(I, I_st)
                save(Q, Q_st)
                sequenceMacros.qubit_state_tomography(state_z, state_prep=prep_fn, state_st=state_z_st,
                                                      therm_clks=therm_clks, targets=[I, Q], axis="z", qb_el=qb_el, x90=x90, yn90=yn90)
                save(I, I_st)
                save(Q, Q_st)

            save(n, n_st)

        # -------- stream processing --------
        with stream_processing():
            n_st.save("iteration")

            if n_preps == 1:
                # Backward-compatible: scalars, no prep dimension
                state_x_st.boolean_to_int().average().save("state_x")
                state_y_st.boolean_to_int().average().save("state_y")
                state_z_st.boolean_to_int().average().save("state_z")

                I_st.buffer(3).average().save("I_axes_avg")
                Q_st.buffer(3).average().save("Q_axes_avg")
            else:
                # Multi-prep: shape (n_preps,) / (n_preps, 3)
                state_x_st.boolean_to_int().buffer(n_preps).average().save("state_x")
                state_y_st.boolean_to_int().buffer(n_preps).average().save("state_y")
                state_z_st.boolean_to_int().buffer(n_preps).average().save("state_z")

                I_st.buffer(3).buffer(n_preps).average().save("I_axes_avg")
                Q_st.buffer(3).buffer(n_preps).average().save("Q_axes_avg")

    return prog


def fock_resolved_state_tomography(qb_el, state_prep, qb_if, fock_ifs, sel_r180, rxp90,
                                   rym90, st_therm_clks, tag_off_idle_clks, n_avg, *, bindings: "ExperimentBindings | None" = None):
    """
    Performs Fock-resolved state tomography using sequenceMacros.
    Separates x, y, z measurements into different streams.

    Parameters
    ----------
    state_prep : callable **or** list/tuple of callables
        Each callable prepares the cavity+qubit state before tomography.
        When a single callable is passed the program is backward-compatible.
        When a sequence of P callables is passed, the program Python-unrolls
        over all of them inside each (n_avg, fock_if) iteration.

    Stream outputs
    --------------
    Single prep (backward-compatible):
        state_{x,y,z}_{on,off} : shape (N_fock,)

    P preps:
        state_{x,y,z}_{on,off} : shape (N_fock, P)
    """
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        qb_el = qb_el or _names.get("qubit", "__qb")
    elif qb_el is None:
        raise ValueError("qb_el is required when bindings are not provided")
    # Normalise to a list
    if callable(state_prep):
        preps = [state_prep]
    else:
        preps = list(state_prep)
    n_preps = len(preps)
    if n_preps == 0:
        raise ValueError("state_prep must be a callable or a non-empty sequence of callables")

    fock_ifs = np.array(fock_ifs, dtype=int)

    with program() as prog:
        n = declare(int)
        f = declare(int) # Fock specific IF

        I = declare(fixed)
        Q = declare(fixed)

        # Declarations for each axis (On/Off)
        state_x_on = declare(bool)
        state_y_on = declare(bool)
        state_z_on = declare(bool)
        state_x_off = declare(bool)
        state_y_off = declare(bool)
        state_z_off = declare(bool)

        state_x_on_st = declare_stream()
        state_y_on_st = declare_stream()
        state_z_on_st = declare_stream()
        state_x_off_st = declare_stream()
        state_y_off_st = declare_stream()
        state_z_off_st = declare_stream()

        n_st = declare_stream()

        with for_(n, 0, n < n_avg, n + 1):
            with for_each_(f, fock_ifs):

                for prep_fn in preps:
                    # Wrapper to ensure prep at correct IF (closure captures prep_fn)
                    def prep_wrapper(fn=prep_fn):
                        update_frequency(qb_el, qb_if)
                        fn()

                    # --- X Axis ---
                    # 1. Tag Off (Global only)
                    sequenceMacros.qubit_state_tomography(
                        state=state_x_off,
                        state_prep=prep_wrapper,
                        state_st=state_x_off_st,
                        targets=[I, Q],
                        axis="x",
                        qb_el=qb_el,
                        x90=rxp90,
                        yn90=rym90,
                        therm_clks=st_therm_clks,
                        selective_pulse=sel_r180,
                        selective_freq=f,       # <<< was None; must match ON
                        wait_after=True,        # OFF = dummy
                        wait_after_clks=tag_off_idle_clks,
                    )

                    sequenceMacros.qubit_state_tomography(
                        state=state_x_on,
                        state_prep=prep_wrapper,
                        state_st=state_x_on_st,
                        targets=[I, Q],
                        axis="x",
                        qb_el=qb_el,
                        x90=rxp90,
                        yn90=rym90,
                        therm_clks=st_therm_clks,
                        selective_pulse=sel_r180,
                        selective_freq=f,
                        wait_after=False,       # ON = real tag (default)
                    )

                    # --- Y Axis ---
                    # 1. Tag Off
                    sequenceMacros.qubit_state_tomography(
                        state=state_y_off,
                        state_prep=prep_wrapper,
                        state_st=state_y_off_st,
                        targets=[I, Q],
                        axis="y",
                        qb_el=qb_el,
                        x90=rxp90,
                        yn90=rym90,
                        therm_clks=st_therm_clks,
                        selective_pulse=sel_r180,
                        selective_freq=f,
                        wait_after=True,
                        wait_after_clks=tag_off_idle_clks,
                    )

                    # 2. Tag On
                    sequenceMacros.qubit_state_tomography(
                        state=state_y_on,
                        state_prep=prep_wrapper,
                        state_st=state_y_on_st,
                        targets=[I, Q],
                        axis="y",
                        qb_el=qb_el,
                        x90=rxp90,
                        yn90=rym90,
                        therm_clks=st_therm_clks,
                        selective_pulse=sel_r180,
                        selective_freq=f,
                        wait_after=False,
                    )

                    # --- Z Axis ---
                    # 1. Tag Off
                    sequenceMacros.qubit_state_tomography(
                        state=state_z_off,
                        state_prep=prep_wrapper,
                        state_st=state_z_off_st,
                        targets=[I, Q],
                        axis="z",
                        qb_el=qb_el,
                        x90=rxp90,
                        yn90=rym90,
                        therm_clks=st_therm_clks,
                        selective_pulse=sel_r180,
                        selective_freq=f,
                        wait_after=True,
                        wait_after_clks=tag_off_idle_clks,
                    )

                    # 2. Tag On
                    sequenceMacros.qubit_state_tomography(
                        state=state_z_on,
                        state_prep=prep_wrapper,
                        state_st=state_z_on_st,
                        targets=[I, Q],
                        axis="z",
                        qb_el=qb_el,
                        x90=rxp90,
                        yn90=rym90,
                        therm_clks=st_therm_clks,
                        selective_pulse=sel_r180,
                        selective_freq=f,
                        wait_after=False,
                    )

            save(n, n_st)

        with stream_processing():
            if n_preps == 1:
                # Backward-compatible: shape (N_fock,)
                state_x_off_st.boolean_to_int().buffer(len(fock_ifs)).average().save("state_x_off")
                state_x_on_st.boolean_to_int().buffer(len(fock_ifs)).average().save("state_x_on")

                state_y_off_st.boolean_to_int().buffer(len(fock_ifs)).average().save("state_y_off")
                state_y_on_st.boolean_to_int().buffer(len(fock_ifs)).average().save("state_y_on")

                state_z_off_st.boolean_to_int().buffer(len(fock_ifs)).average().save("state_z_off")
                state_z_on_st.boolean_to_int().buffer(len(fock_ifs)).average().save("state_z_on")
            else:
                # Multi-prep: shape (N_fock, n_preps)
                state_x_off_st.boolean_to_int().buffer(n_preps).buffer(len(fock_ifs)).average().save("state_x_off")
                state_x_on_st.boolean_to_int().buffer(n_preps).buffer(len(fock_ifs)).average().save("state_x_on")

                state_y_off_st.boolean_to_int().buffer(n_preps).buffer(len(fock_ifs)).average().save("state_y_off")
                state_y_on_st.boolean_to_int().buffer(n_preps).buffer(len(fock_ifs)).average().save("state_y_on")

                state_z_off_st.boolean_to_int().buffer(n_preps).buffer(len(fock_ifs)).average().save("state_z_off")
                state_z_on_st.boolean_to_int().buffer(n_preps).buffer(len(fock_ifs)).average().save("state_z_on")

            n_st.save("iteration")

    return prog
