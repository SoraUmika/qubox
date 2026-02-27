
from __future__ import annotations
from contextlib import nullcontext
from typing import TYPE_CHECKING
from qm.qua import *
from qualang_tools.loops import from_array
from ..macros.measure import measureMacro
from ..macros.sequence import sequenceMacros
import numpy as np

if TYPE_CHECKING:
    from ...experiments.gates_legacy import Gate


def storage_spectroscopy(qb_el, st_el, disp, sel_r180, if_frequencies, st_therm_clks, n_avg, *, bindings: "ExperimentBindings | None" = None):
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        qb_el = qb_el or _names.get("qubit", "__qb")
        st_el = st_el or _names.get("storage", "__st")
    else:
        if qb_el is None:
            raise ValueError("qb_el is required when bindings are not provided")
        if st_el is None:
            raise ValueError("st_el is required when bindings are not provided")
    with program() as storage_spec:
        n = declare(int)
        f = declare(int)
        I = declare(fixed)
        Q = declare(fixed)
        I_st = declare_stream()
        Q_st = declare_stream()
        n_st = declare_stream()

        with for_(n, 0, n < n_avg, n + 1):
            with for_(*from_array(f, if_frequencies)):
                update_frequency(st_el, f)
                play(disp, st_el)
                align()
                play(sel_r180, qb_el)
                align()
                measureMacro.measure(targets=[I,Q])
                wait(int(st_therm_clks), st_el)
                save(I, I_st)
                save(Q, Q_st)
            save(n, n_st)

        with stream_processing():
            I_st.buffer(len(if_frequencies)).average().save("I")
            Q_st.buffer(len(if_frequencies)).average().save("Q")
            n_st.save("iteration")
    return storage_spec

def num_splitting_spectroscopy(state_prep, qb_el, st_el, sel_r180, if_frequencies, st_therm_clks, n_avg, *, bindings: "ExperimentBindings | None" = None):
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        qb_el = qb_el or _names.get("qubit", "__qb")
        st_el = st_el or _names.get("storage", "__st")
    else:
        if qb_el is None:
            raise ValueError("qb_el is required when bindings are not provided")
        if st_el is None:
            raise ValueError("st_el is required when bindings are not provided")
    with program() as num_splitting_spectroscopy_program:
        n = declare(int)
        f = declare(int)
        I = declare(fixed)
        Q = declare(fixed)
        I_st = declare_stream()
        Q_st = declare_stream()
        n_st = declare_stream()
        with for_(n, 0, n < n_avg, n + 1):
            sequenceMacros.num_splitting_spectroscopy(if_frequencies, state_prep, I, Q, I_st, Q_st,
                                                    st_therm_clks, st_el=st_el, qb_el=qb_el, sel_r180=sel_r180)
            save(n, n_st)
        with stream_processing():
            I_st.buffer(len(if_frequencies)).average().save("I")
            Q_st.buffer(len(if_frequencies)).average().save("Q")
            n_st.save("iteration")
    return num_splitting_spectroscopy_program

def sel_r180_calibration0(
    qb_el,
    *,
    qb_if: int,
    sel_r180: str,
    qb_therm_clks: int,
    n_avg: int = 2000,
    fock_ifs=None,             # optional sweep list; if None -> [qb_if]
    x180_pulse: str = "x180",  # unconditional qubit pi to prep |e>
    bindings: "ExperimentBindings | None" = None,
):
    """
    Calibrate sel_r180 flip probabilities with no M0.

    For each IF f:
      (A) thermalize -> sel_r180 @ f -> M1  -> thermalize
      (B) thermalize -> x180 -> sel_r180 @ f -> M1 -> thermalize

    Saved streams (per iteration, per f):
      - I_g/Q_g : after sel starting from thermal g  (estimates g->e)
      - I_e/Q_e : after sel starting from e          (estimates e->g via 1-Pe)
      - f_if, iteration
    """
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        qb_el = qb_el or _names.get("qubit", "__qb")
    elif qb_el is None:
        raise ValueError("qb_el is required when bindings are not provided")
    if fock_ifs is None:
        fock_ifs = [int(qb_if)]
    fock_ifs = np.array(fock_ifs, dtype=int).tolist()

    with program() as prog:
        n = declare(int)
        f = declare(int)

        # One measurement per block
        I_g = declare(fixed); Q_g = declare(fixed)
        I_e = declare(fixed); Q_e = declare(fixed)
        st_g = declare(bool)
        st_e = declare(bool)

        # Streams
        I_g_st = declare_stream(); Q_g_st = declare_stream()
        I_e_st = declare_stream(); Q_e_st = declare_stream()
        st_g_st = declare_stream(); st_e_st = declare_stream()
        f_st = declare_stream()
        n_st = declare_stream()

        with for_(n, 0, n < n_avg, n + 1):
            with for_each_(f, fock_ifs):

                # -------------------------
                # (A) start in thermal g
                # -------------------------
                wait(int(qb_therm_clks))

                update_frequency(qb_el, f)
                align()
                play(sel_r180, qb_el)
                align()

                measureMacro.measure(targets=[I_g, Q_g], state=st_g)

                wait(int(qb_therm_clks))

                save(I_g, I_g_st); save(Q_g, Q_g_st)
                save(st_g, st_g_st)

                # -------------------------
                # (B) start in e (via x180)
                # -------------------------
                update_frequency(qb_el, qb_if)
                align()
                play(x180_pulse, qb_el)
                align()

                update_frequency(qb_el, f)
                align()
                play(sel_r180, qb_el)
                align()

                measureMacro.measure(targets=[I_e, Q_e], state=st_e)

                wait(int(qb_therm_clks))

                save(I_e, I_e_st); save(Q_e, Q_e_st)
                save(st_e, st_e_st)

                # tag which IF this was
                save(f, f_st)

            save(n, n_st)

        with stream_processing():
            I_g_st.buffer(len(fock_ifs)).save_all("I_g")
            Q_g_st.buffer(len(fock_ifs)).save_all("Q_g")
            st_g_st.boolean_to_int().buffer(len(fock_ifs)).save_all("state_g")

            I_e_st.buffer(len(fock_ifs)).save_all("I_e")
            Q_e_st.buffer(len(fock_ifs)).save_all("Q_e")
            st_e_st.boolean_to_int().buffer(len(fock_ifs)).save_all("state_e")

            f_st.buffer(len(fock_ifs)).save_all("f_if")
            n_st.save("iteration")

    return prog


def fock_resolved_spectroscopy(
    qb_el,
    state_prep,
    qb_if,
    fock_ifs,
    sel_r180,
    st_therm_clks,
    n_avg,
    *,
    sel_r180_transfer_calibration: bool = False,
    qb_therm_clks: int | None = None,
    r180: str = "x180",
    bindings: "ExperimentBindings | None" = None,
):
    """
    SIGNAL+NULL (per n and per f):
      state_prep -> M0 -> sel_r180@f -> M1_sel -> null@f -> M1_null -> therm

    Optional CAL (once per outer n iteration, before f sweep):
      prep |g> -> M0 -> sel_r180@qb_if -> M1 -> relax
      prep |e> -> M0 -> sel_r180@qb_if -> M1 -> relax
    CAL streams buffered as (n_avg, 2) (shots x prep).
    """
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        qb_el = qb_el or _names.get("qubit", "__qb")
    elif qb_el is None:
        raise ValueError("qb_el is required when bindings are not provided")
    fock_ifs = np.array(fock_ifs, dtype=int)
    L = int(len(fock_ifs))
    if qb_therm_clks is None:
        qb_therm_clks = int(st_therm_clks)

    with program() as prog:
        n = declare(int)
        f = declare(int)

        # ---------------------------
        # Shared M0 variables (used for both SEL and NULL)
        # ---------------------------
        I0 = declare(fixed); Q0 = declare(fixed)
        state0 = declare(bool)

        # ---------------------------
        # M1 variables: SEL arm
        # ---------------------------
        I1_sel = declare(fixed); Q1_sel = declare(fixed)
        state1_sel = declare(bool)

        # ---------------------------
        # M1 variables: NULL arm
        # ---------------------------
        I1_null = declare(fixed); Q1_null = declare(fixed)
        state1_null = declare(bool)

        # ---------------------------
        # Streams: M0
        # ---------------------------
        I0_st = declare_stream(); Q0_st = declare_stream()
        state0_st = declare_stream()

        # Streams: M1 SEL
        I1_sel_st = declare_stream(); Q1_sel_st = declare_stream()
        state1_sel_st = declare_stream()

        # Streams: M1 NULL
        I1_null_st = declare_stream(); Q1_null_st = declare_stream()
        state1_null_st = declare_stream()

        # ---------------------------
        # Optional CAL variables/streams
        # ---------------------------
        if sel_r180_transfer_calibration:
            I0_cal = declare(fixed); Q0_cal = declare(fixed)
            I1_cal = declare(fixed); Q1_cal = declare(fixed)
            state0_cal = declare(bool)
            state1_cal = declare(bool)

            I0_cal_st = declare_stream(); Q0_cal_st = declare_stream()
            I1_cal_st = declare_stream(); Q1_cal_st = declare_stream()
            state0_cal_st = declare_stream(); state1_cal_st = declare_stream()

        n_st = declare_stream()

        with for_(n, 0, n < n_avg, n + 1):

            # ============================================================
            # CAL (once per n): g/e prep at qb_if (kept as-is)
            # ============================================================
            if sel_r180_transfer_calibration:
                # ---- CAL block 1: start from |g> ----
                wait(int(qb_therm_clks))
                update_frequency(qb_el, qb_if)
                align()

                measureMacro.measure(targets=[I0_cal, Q0_cal], state=state0_cal)

                update_frequency(qb_el, qb_if)
                align()
                play(sel_r180, qb_el)
                align()

                measureMacro.measure(targets=[I1_cal, Q1_cal], state=state1_cal)

                wait(int(qb_therm_clks))

                save(I0_cal, I0_cal_st); save(Q0_cal, Q0_cal_st)
                save(I1_cal, I1_cal_st); save(Q1_cal, Q1_cal_st)
                save(state0_cal, state0_cal_st)
                save(state1_cal, state1_cal_st)

                # ---- CAL block 2: start from |e> ----
                wait(int(qb_therm_clks))
                update_frequency(qb_el, qb_if)
                align()

                play(r180, qb_el)
                align()

                measureMacro.measure(targets=[I0_cal, Q0_cal], state=state0_cal)

                update_frequency(qb_el, qb_if)
                align()
                play(sel_r180, qb_el)
                align()

                measureMacro.measure(targets=[I1_cal, Q1_cal], state=state1_cal)

                wait(int(qb_therm_clks))

                save(I0_cal, I0_cal_st); save(Q0_cal, Q0_cal_st)
                save(I1_cal, I1_cal_st); save(Q1_cal, Q1_cal_st)
                save(state0_cal, state0_cal_st)
                save(state1_cal, state1_cal_st)

            # ============================================================
            # SIGNAL+NULL sweep over fock_ifs
            # ============================================================
            with for_each_(f, fock_ifs):
                update_frequency(qb_el, qb_if)
                state_prep()

                # ---- M0 (shared) ----
                measureMacro.measure(targets=[I0, Q0], state=state0)

                # ---- SEL arm ----
                update_frequency(qb_el, f)
                align()
                play(sel_r180, qb_el)
                align()

                measureMacro.measure(targets=[I1_sel, Q1_sel], state=state1_sel)

                # ---- NULL arm (timing-matched, zero amp) ----
                # Keep same IF f to preserve mixer/IF path
                align()
                play(sel_r180 * amp(0.0), qb_el)
                align()

                measureMacro.measure(targets=[I1_null, Q1_null], state=state1_null)

                # thermalize
                wait(int(st_therm_clks))

                # save
                save(I0, I0_st); save(Q0, Q0_st)
                save(state0, state0_st)

                save(I1_sel, I1_sel_st); save(Q1_sel, Q1_sel_st)
                save(state1_sel, state1_sel_st)

                save(I1_null, I1_null_st); save(Q1_null, Q1_null_st)
                save(state1_null, state1_null_st)

            save(n, n_st)
            wait(int(st_therm_clks))

        with stream_processing():
            # Per n: L entries for each stream
            I0_st.buffer(L).save_all("I0")
            Q0_st.buffer(L).save_all("Q0")
            state0_st.boolean_to_int().buffer(L).save_all("states0")

            I1_sel_st.buffer(L).save_all("I_sel")
            Q1_sel_st.buffer(L).save_all("Q_sel")
            state1_sel_st.boolean_to_int().buffer(L).save_all("states1_sel")

            I1_null_st.buffer(L).save_all("I_null")
            Q1_null_st.buffer(L).save_all("Q_null")
            state1_null_st.boolean_to_int().buffer(L).save_all("states1_null")

            # CAL: per n we save 2 entries (prep)
            if sel_r180_transfer_calibration:
                I0_cal_st.buffer(2).save_all("I0_cal")
                Q0_cal_st.buffer(2).save_all("Q0_cal")
                I1_cal_st.buffer(2).save_all("I_cal")
                Q1_cal_st.buffer(2).save_all("Q_cal")
                state0_cal_st.boolean_to_int().buffer(2).save_all("states0_cal")
                state1_cal_st.boolean_to_int().buffer(2).save_all("states1_cal")

            n_st.save("iteration")

    return prog




def fock_resolved_T1_relaxation(
    qb_el, st_el,
    fock_disps, fock_ifs,
    sel_r180,
    delay_clks, st_therm_clks,
    n_avg,
    *,
    bindings: "ExperimentBindings | None" = None,
):
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        qb_el = qb_el or _names.get("qubit", "__qb")
        st_el = st_el or _names.get("storage", "__st")
    else:
        if qb_el is None:
            raise ValueError("qb_el is required when bindings are not provided")
        if st_el is None:
            raise ValueError("st_el is required when bindings are not provided")
    fock_ifs = np.array(fock_ifs, dtype=int)

    with program() as prog:
        n = declare(int)
        I = declare(fixed)
        Q = declare(fixed)
        delay_clk = declare(int)

        I_st = declare_stream()
        Q_st = declare_stream()
        n_st = declare_stream()

        with for_(n, 0, n < n_avg, n + 1):
            for disp_pulse, f_if in zip(fock_disps, fock_ifs):
                update_frequency(qb_el, int(f_if))

                # sweep delay; each point must re-prepare the cavity state
                with for_(*from_array(delay_clk, delay_clks)):
                    # (optional) ensure starting from baseline each shot
                    # wait(int(st_therm_clks))  # if needed before prep

                    play(disp_pulse, st_el)      # prepare |n> (or coherent approx)
                    wait(delay_clk)              # evolution time
                    align()

                    play(sel_r180, qb_el)        # fock-resolved mapping pulse
                    align()

                    measureMacro.measure(targets=[I, Q])
                    wait(int(st_therm_clks))     # let system relax/reset

                    save(I, I_st)
                    save(Q, Q_st)

            save(n, n_st)

        with stream_processing():
            I_st.buffer(len(delay_clks)).buffer(len(fock_ifs)).average().save("I")
            Q_st.buffer(len(delay_clks)).buffer(len(fock_ifs)).average().save("Q")
            n_st.save("iteration")

    return prog


def fock_resolved_power_rabi(qb_el, st_el, gains, disp_n_list, fock_ifs, sel_qb_pulse, st_therm_clks, n_avg, *, bindings: "ExperimentBindings | None" = None):
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        qb_el = qb_el or _names.get("qubit", "__qb")
        st_el = st_el or _names.get("storage", "__st")
    else:
        if qb_el is None:
            raise ValueError("qb_el is required when bindings are not provided")
        if st_el is None:
            raise ValueError("st_el is required when bindings are not provided")
    fock_ifs = np.array(fock_ifs, dtype=int)
    with program() as prog:
        n = declare(int)
        I = declare(fixed)
        Q = declare(fixed)
        g = declare(fixed)
        f = declare(int)
        I_st = declare_stream()
        Q_st = declare_stream()
        n_st = declare_stream()
        with for_(n, 0, n < n_avg, n + 1):
            for (f, disp_pulse) in zip(fock_ifs, disp_n_list):
                with for_(*from_array(g, gains)):
                    play(disp_pulse, st_el)

                    update_frequency(qb_el, f)
                    align()
                    play(sel_qb_pulse*amp(g), qb_el)
                    align()

                    measureMacro.measure(targets=[I, Q])
                    wait(int(st_therm_clks))
                    save(I, I_st)
                    save(Q, Q_st)
            save(n, n_st)
        with stream_processing():
            I_st.buffer(len(gains)).buffer(len(fock_ifs)).average().save("I")
            Q_st.buffer(len(gains)).buffer(len(fock_ifs)).average().save("Q")
            n_st.save("iteration")
    return prog

def fock_resolved_qb_ramsey(qb_el, st_el, fock_ifs, detunings, disps, sel_r90, delay_clks, st_therm_clk, n_avg, *, bindings: "ExperimentBindings | None" = None):
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        qb_el = qb_el or _names.get("qubit", "__qb")
        st_el = st_el or _names.get("storage", "__st")
    else:
        if qb_el is None:
            raise ValueError("qb_el is required when bindings are not provided")
        if st_el is None:
            raise ValueError("st_el is required when bindings are not provided")
    with program() as fock_resolved_qb_ramsey:
        delay_clk = declare(int)
        n = declare(int)
        I = declare(fixed)
        Q = declare(fixed)
        I_st = declare_stream()
        Q_st = declare_stream()
        n_st = declare_stream()
        with for_(n, 0, n < n_avg, n + 1):
            for fock_if, detune, disp in zip(fock_ifs, detunings, disps):
                update_frequency(qb_el, fock_if+detune)
                with for_(*from_array(delay_clk, delay_clks)):
                    play(disp, st_el)
                    align()
                    sequenceMacros.qubit_ramsey(delay_clk, qb_el=qb_el, r90_1=sel_r90, r90_2=sel_r90)
                    align()
                    measureMacro.measure(targets=[I,Q])
                    wait(int(st_therm_clk))
                    save(I, I_st)
                    save(Q, Q_st)
            save(n, n_st)
        with stream_processing():
            I_st.buffer(len(delay_clks)).buffer(len(fock_ifs)).average().save("I")
            Q_st.buffer(len(delay_clks)).buffer(len(fock_ifs)).average().save("Q")
            n_st.save("iteration")
    return fock_resolved_qb_ramsey

def storage_wigner_tomography(
        prep_gates: list[Gate],             # Python list of Gate instances to prepare Ï
        st_el, qb_el, ro_el,
        base_disp,
        x_vals, p_vals, base_alpha,
        x90_pulse,              # fast pi_val/2 on the qubit
        parity_wait_clks,       # â‰ƒ pi_val/chi_val, in clock ticks
        st_therm_clks,          # storage cooldown
        n_avg,                  # number of repeats
        *,
        bindings: "ExperimentBindings | None" = None,
):
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        st_el = st_el or _names.get("storage", "__st")
        qb_el = qb_el or _names.get("qubit", "__qb")
        ro_el = ro_el or _names.get("readout", "__ro")
    else:
        if st_el is None:
            raise ValueError("st_el is required when bindings are not provided")
        if qb_el is None:
            raise ValueError("qb_el is required when bindings are not provided")
        if ro_el is None:
            raise ValueError("ro_el is required when bindings are not provided")
    m00_list, m01_list, m10_list, m11_list = [], [], [], []
    for p in p_vals:
        for x in x_vals:
            ratio  = -(x + 1j*p) / base_alpha
            norm   = abs(ratio)
            c, s   = ratio.real / norm, ratio.imag / norm   if norm else (0.0, 0.0)
            m00_list.append(norm*c)
            m01_list.append(-norm*s)
            m10_list.append(norm*s)
            m11_list.append(norm*c)

    m_matrix = (m00_list, m01_list, m10_list, m11_list)

    with program() as prog:
        rep = declare(int)
        I, Q = declare(fixed), declare(fixed)
        m00 = declare(fixed)
        m01 = declare(fixed)
        m10 = declare(fixed)
        m11 = declare(fixed)
        I_st = declare_stream()
        Q_st = declare_stream()
        n_st = declare_stream()

        with for_(rep, 0, rep < n_avg, rep + 1):
            with for_each_((m00, m01, m10, m11), m_matrix):
                for gate in prep_gates:
                    gate.play()
                align(st_el, qb_el)

                play(base_disp * amp(m00, m01, m10, m11), st_el)

                play(x90_pulse, qb_el)
                wait(int(parity_wait_clks), qb_el)
                play(x90_pulse, qb_el)
                align(qb_el, ro_el)

                I, Q = measureMacro.measure(targets=[I,Q])
                wait(int(st_therm_clks), st_el)

                save(I, I_st)
                save(Q, Q_st)

            save(rep, n_st)

        with stream_processing():
            I_st.buffer(len(x_vals)).buffer(len(p_vals)).average().save("I")
            Q_st.buffer(len(x_vals)).buffer(len(p_vals)).average().save("Q")
            n_st.save("iteration")

    return prog

def phase_evolution_prog(ro_el, qb_el, st_el,
                         disp_alpha_pulse, disp_eps_pulse,
                         sel_r180_pulse,
                         fock0_if,
                         fock_probe_ifs,
                         delay_clks,
                         snap_list,
                         st_therm_clks, n_avg,
                         *, bindings: "ExperimentBindings | None" = None):
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        ro_el = ro_el or _names.get("readout", "__ro")
        qb_el = qb_el or _names.get("qubit", "__qb")
        st_el = st_el or _names.get("storage", "__st")
    else:
        if ro_el is None:
            raise ValueError("ro_el is required when bindings are not provided")
        if qb_el is None:
            raise ValueError("qb_el is required when bindings are not provided")
        if st_el is None:
            raise ValueError("st_el is required when bindings are not provided")

    fock_probe_ifs = np.array(fock_probe_ifs, dtype=int)
    fock_dim = len(fock_probe_ifs)
    delay_dim = len(delay_clks)
    theta_dim = len(snap_list)
    with program() as prog:
        rep   = declare(int)
        d_idx = declare(int)
        I, Q  = declare(fixed), declare(fixed)
        I_st, Q_st, n_st = declare_stream(), declare_stream(), declare_stream()

        fock_n_if = declare(int)
        with for_(rep, 0, rep < n_avg, rep + 1):
            with for_(*from_array(d_idx, delay_clks)):
                for snap in snap_list:
                    with for_each_(fock_n_if, fock_probe_ifs):
                        reset_frame(st_el)
                        reset_frame(qb_el)
                        update_frequency(qb_el, fock0_if)

                        play(disp_alpha_pulse, st_el)
                        align(qb_el, st_el)

                        with if_(d_idx>0):
                            wait(d_idx, st_el, qb_el)

                        play(snap, qb_el)
                        align(qb_el, st_el)

                        play(disp_eps_pulse, st_el)

                        align()

                        update_frequency(qb_el, fock_n_if)
                        play(sel_r180_pulse, qb_el)
                        align(qb_el, ro_el)
                        I, Q = measureMacro.measure(targets=[I,Q])
                        wait(int(st_therm_clks), st_el)

                        save(I, I_st)
                        save(Q, Q_st)
            save(rep, n_st)
        with stream_processing():
            I_st.buffer(fock_dim).buffer(theta_dim).buffer(delay_dim).average().save("I")
            Q_st.buffer(fock_dim).buffer(theta_dim).buffer(delay_dim).average().save("Q")
            n_st.save("iteration")

    return prog

def storage_chi_ramsey(
    ro_el, qb_el, st_el,
    disp_pulse,           # displacement pulse to put n photons in the cavity
    x90_pulse,            # pi_val/2 pulse on the qubit
    delay_ticks,          # list/ndarray of waiting\u2010time values (in clock ticks)
    st_therm_clks,        # cooldown for storage (in clock ticks)
    n_avg,                # number of averages
    *, bindings: "ExperimentBindings | None" = None,
):
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        ro_el = ro_el or _names.get("readout", "__ro")
        qb_el = qb_el or _names.get("qubit", "__qb")
        st_el = st_el or _names.get("storage", "__st")
    else:
        if ro_el is None:
            raise ValueError("ro_el is required when bindings are not provided")
        if qb_el is None:
            raise ValueError("qb_el is required when bindings are not provided")
        if st_el is None:
            raise ValueError("st_el is required when bindings are not provided")
    with program() as prog:
        rep = declare(int)
        tau   = declare(int)
        I   = declare(fixed)
        Q   = declare(fixed)

        I_st = declare_stream()
        Q_st = declare_stream()
        n_st = declare_stream()

        with for_(rep, 0, rep < n_avg, rep + 1):

            # sweep Ramsey waiting time
            with for_(*from_array(tau, delay_ticks)):
                play(disp_pulse, st_el)
                align(st_el, qb_el)
                play(x90_pulse, qb_el)
                wait(tau, qb_el)
                play(x90_pulse, qb_el)
                align(qb_el, ro_el)

                I, Q = measureMacro.measure(targets=[I,Q])
                wait(int(st_therm_clks), st_el)

                save(I, I_st)
                save(Q, Q_st)
            save(rep, n_st)
        with stream_processing():
            I_st.buffer(len(delay_ticks)).average().save("I")
            Q_st.buffer(len(delay_ticks)).average().save("Q")
            n_st.save("iteration")

    return prog

def storage_ramsey(
    ro_el, qb_el, st_el,
    disp_pulse,           # displacement pulse to put n photons in the cavity
    sel_r180,            # pi_val/2 pulse on the qubit
    delay_ticks,          # list/ndarray of waiting\u2010time values (in clock ticks)
    st_therm_clks,        # cooldown for storage (in clock ticks)
    n_avg,                # number of averages
    *, bindings: "ExperimentBindings | None" = None,
):
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        ro_el = ro_el or _names.get("readout", "__ro")
        qb_el = qb_el or _names.get("qubit", "__qb")
        st_el = st_el or _names.get("storage", "__st")
    else:
        if ro_el is None:
            raise ValueError("ro_el is required when bindings are not provided")
        if qb_el is None:
            raise ValueError("qb_el is required when bindings are not provided")
        if st_el is None:
            raise ValueError("st_el is required when bindings are not provided")
    with program() as prog:
        rep = declare(int)
        tau   = declare(int)
        I   = declare(fixed)
        Q   = declare(fixed)

        I_st = declare_stream()
        Q_st = declare_stream()
        n_st = declare_stream()

        # average loop
        with for_(rep, 0, rep < n_avg, rep + 1):

            # sweep Ramsey waiting time
            with for_(*from_array(tau, delay_ticks)):

                # prepare one\u2010photon (or coherent) state in storage
                play(disp_pulse, st_el)
                wait(tau)
                align(st_el)
                play(disp_pulse*amp(0, 1, 1, 0), st_el)
                align(st_el)
                play(sel_r180, qb_el)
                align()
                I, Q = measureMacro.measure(targets=[I,Q])

                # re\u2010thermalize storage
                wait(int(st_therm_clks), st_el)

                save(I, I_st)
                save(Q, Q_st)

            # progress counter
            save(rep, n_st)

        # stream processing: buffer over \u03c4, then average over reps
        with stream_processing():
            I_st.buffer(len(delay_ticks)).average().save("I")
            Q_st.buffer(len(delay_ticks)).average().save("Q")
            n_st.save("iteration")

    return prog
