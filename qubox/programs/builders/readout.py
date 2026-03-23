
from contextlib import nullcontext
from qm.qua import *
from qualang_tools.loops import from_array
from ..macros.measure import measureMacro
from ..macros.sequence import sequenceMacros
import numpy as np


def iq_blobs(ro_el, qb_el, r180, qb_therm_clks, n_runs, *, bindings: "ExperimentBindings | None" = None):
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        ro_el = ro_el or _names.get("readout", "__ro")
        qb_el = qb_el or _names.get("qubit", "__qb")
    else:
        if ro_el is None:
            raise ValueError("ro_el is required when bindings are not provided")
        if qb_el is None:
            raise ValueError("qb_el is required when bindings are not provided")
    with program() as IQ_blobs_program:
        n = declare(int)
        I = declare(fixed)
        Q = declare(fixed)
        Ig_st = declare_stream()
        Qg_st = declare_stream()
        Ie_st = declare_stream()
        Qe_st = declare_stream()
        n_st = declare_stream()
        with for_(n, 0, n < n_runs, n + 1):
            measureMacro.measure(targets=[I,Q])
            wait(int(qb_therm_clks), ro_el)
            save(I, Ig_st)
            save(Q, Qg_st)

            align()
            play(r180, qb_el)
            align(qb_el, ro_el)

            measureMacro.measure(targets=[I,Q])
            wait(int(qb_therm_clks), ro_el)
            save(I, Ie_st)
            save(Q, Qe_st)
            save(n, n_st)

        with stream_processing():
            Ig_st.save_all("Ig")
            Qg_st.save_all("Qg")
            Ie_st.save_all("Ie")
            Qe_st.save_all("Qe")
            n_st.save("iteration")
    return IQ_blobs_program


def readout_ge_raw_trace(qb_el, r180, qb_therm_clks, ro_depl_clks, n_avg, *, bindings: "ExperimentBindings | None" = None):
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        qb_el = qb_el or _names.get("qubit", "__qb")
    elif qb_el is None:
        raise ValueError("qb_el is required when bindings are not provided")
    with program() as readout_ge_raw_trace:
        n        = declare(int)
        k        = declare(int)
        adc_st_g = declare_stream(adc_trace=True)
        adc_st_e = declare_stream(adc_trace=True)
        iter_st  = declare_stream()

        assign(k, 0)

        # Ground loop
        with for_(n, 0, n < n_avg, n + 1):
            align()
            reset_if_phase(measureMacro.active_element())
            measureMacro.measure(adc_stream=adc_st_g)
            wait(int(ro_depl_clks))
            save(k, iter_st)
            assign(k, k + 1)
            wait(50000)
        # Excited loop
        with for_(n, 0, n < n_avg, n + 1):
            align()
            play(r180, qb_el)
            align()
            reset_if_phase(measureMacro.active_element())
            measureMacro.measure(adc_stream=adc_st_e)
            wait(int(qb_therm_clks))
            save(k, iter_st)
            assign(k, k + 1)
            wait(50000)

        with stream_processing():
            adc_st_g.input1().average().save("adc1_g")
            adc_st_g.input2().average().save("adc2_g")
            adc_st_e.input1().average().save("adc1_e")
            adc_st_e.input2().average().save("adc2_e")
            iter_st.save("iteration")

    return readout_ge_raw_trace

def readout_ge_integrated_trace(qb_el, weights, num_div, div_clks, r180, ro_depl_clks, n_avg,
                                 target_save_rate_khz=2000.0, *, bindings: "ExperimentBindings | None" = None):
    """
    Modified to dynamically calculate safety wait time to maintain target save rate.

    Parameters:
        qb_el : qubit element
        weights : list of 4 integration weights
        num_div : number of divisions for sliced demodulation
        div_clks : duration of each division slice
        r180 : pi pulse name
        ro_depl_clks : resonator depletion time
        n_avg : number of averages
        target_save_rate_khz : target save rate in kHz (default=2.0, meaning 2000 saves/sec)
    """
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        qb_el = qb_el or _names.get("qubit", "__qb")
    elif qb_el is None:
        raise ValueError("qb_el is required when bindings are not provided")
    if not isinstance(weights, (list, tuple)):
        raise TypeError(
            "weights must be a list/tuple of four integration-weight labels for "
            "[II, IQ, QI, QQ]."
        )
    if len(weights) != 4:
        raise ValueError(
            "readout_ge_integrated_trace requires 4 weights for [II, IQ, QI, QQ], "
            f"got {len(weights)}: {weights!r}."
        )

    measureMacro.set_outputs(list(weights))
    measureMacro.set_demodulator(demod.sliced, div_clks)
    output_ports = ["out1" if (i % 2 == 0) else "out2" for i in range(len(weights))]
    measureMacro.set_output_ports(output_ports)
    with program() as readout_ge_integrated_trace:
        n   = declare(int)
        ind = declare(int)

        II = declare(fixed, size=num_div)
        IQ = declare(fixed, size=num_div)
        QI = declare(fixed, size=num_div)
        QQ = declare(fixed, size=num_div)

        n_st  = declare_stream()
        II_st = declare_stream(); IQ_st = declare_stream()
        QI_st = declare_stream(); QQ_st = declare_stream()

        # ===== Dynamic safety wait calculation =====
        # Each iteration saves: 8 * num_div variables (4 IQ pairs x 2 states x num_div)
        saves_per_iteration = 8 * num_div

        # Time spent in measurements and processing (in ns):
        # - 2 measurements (g and e states)
        # - 2 depletion waits
        # - 2 save loops (negligible compared to waits)
        # Assume each measurement takes ~1 us (typical readout length)
        measurement_time_ns = 2 * 1000  # 2 measurements x 1 us
        depletion_time_ns = 2 * ro_depl_clks * 4  # 2 depletion waits x clks x 4ns/clk
        fixed_time_ns = measurement_time_ns + depletion_time_ns

        # Target time per iteration based on save rate:
        # target_save_rate_khz saves/ms -> saves_per_iteration should take:
        target_time_per_iter_ns = (saves_per_iteration / target_save_rate_khz) * 1e6  # kHz to ns

        # Safety wait needed (subtract fixed time):
        safety_wait_ns = max(0, target_time_per_iter_ns - fixed_time_ns)
        safety_wait_clks = int(safety_wait_ns / 4)  # convert to clock cycles

        # Ensure minimum wait of 1000 clks (4 us) for stability
        safety_wait_clks = max(1000, safety_wait_clks)

        # ===== End calculation =====


        with for_(n, 0, n < n_avg, n + 1):
            # Ground state trace
            measureMacro.measure(targets=[II, IQ, QI, QQ])
            wait(int(ro_depl_clks), measureMacro.active_element())

            with for_(ind, 0, ind < num_div, ind + 1):
                save(II[ind], II_st)
                save(IQ[ind], IQ_st)
                save(QI[ind], QI_st)
                save(QQ[ind], QQ_st)

            # Additional wait between g and e measurements
            wait(int(max(ro_depl_clks, 200)), measureMacro.active_element())

            # Excited state trace
            play(r180, qb_el)
            align(qb_el, measureMacro.active_element())
            measureMacro.measure(targets=[II, IQ, QI, QQ])

            wait(int(ro_depl_clks), measureMacro.active_element())

            with for_(ind, 0, ind < num_div, ind + 1):
                save(II[ind], II_st)
                save(IQ[ind], IQ_st)
                save(QI[ind], QI_st)
                save(QQ[ind], QQ_st)

            # Dynamically calculated safety wait to maintain target save rate
            wait(safety_wait_clks, measureMacro.active_element())

            save(n, n_st)

        with stream_processing():
            n_st.save("iteration")
            II_st.buffer(2 * num_div).average().save("II")
            IQ_st.buffer(2 * num_div).average().save("IQ")
            QI_st.buffer(2 * num_div).average().save("QI")
            QQ_st.buffer(2 * num_div).average().save("QQ")

    return readout_ge_integrated_trace

def readout_core_efficiency_calibration(
    qb_el: str,
    r180: str,
    post_sel_policy: str,
    post_sel_kwargs: dict,
    n_shots: int,
    *,
    qb_therm_clks: int,
    save_m0_state: bool = True,
    bindings: "ExperimentBindings | None" = None,
):
    """
    Single-shot (no retry) calibration of BLOBS/THRESHOLD/etc *core* efficiencies.

    For each shot:
      Branch 0 (intended |g>):
        - M0 measure once -> (I0,Q0)
        - Evaluate g-core membership AND e-core membership on same point
      Branch 1 (intended |e>):
        - prepare |e> via r180
        - M0 measure once -> (I0,Q0)
        - Evaluate g-core membership AND e-core membership on same point

    Outputs (arrays are shape [n_shots, 2] where [:,0]=g-branch, [:,1]=e-branch):
      - I0, Q0
      - acc_gcore, acc_ecore   (int 0/1 per shot)
      - acc_gcore_rate, acc_ecore_rate  (shape [2], averaged over shots)
      - (optional) m0_state (int 0/1) from measureMacro.measure(with_state=True)
    """
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        qb_el = qb_el or _names.get("qubit", "__qb")
    elif qb_el is None:
        raise ValueError("qb_el is required when bindings are not provided")
    with program() as prog:
        I0, Q0 = declare(fixed), declare(fixed)
        m0 = declare(bool)

        # Core-membership flags computed from the same IQ point
        acc_g = declare(bool)
        acc_e = declare(bool)

        n = declare(int)

        # Streams
        I0_st, Q0_st = declare_stream(), declare_stream()
        accg_st, acce_st = declare_stream(), declare_stream()
        m0_st = declare_stream()

        with for_(n, 0, n < int(n_shots), n + 1):

            # =========================================================
            # Branch A: intended |g>
            # =========================================================
            if save_m0_state:
                measureMacro.measure(with_state=True, targets=[I0, Q0], state=m0)  # M0
            else:
                measureMacro.measure(with_state=False, targets=[I0, Q0])           # M0

            # Evaluate BOTH memberships on this same (I0,Q0)
            sequenceMacros.post_select(
                accept=acc_g,
                I=I0, Q=Q0,
                target_state="g",
                policy=post_sel_policy,
                **post_sel_kwargs,
            )
            sequenceMacros.post_select(
                accept=acc_e,
                I=I0, Q=Q0,
                target_state="e",
                policy=post_sel_policy,
                **post_sel_kwargs,
            )

            save(I0, I0_st); save(Q0, Q0_st)
            save(acc_g, accg_st); save(acc_e, acce_st)
            if save_m0_state:
                save(m0, m0_st)

            wait(int(qb_therm_clks))
            # =========================================================
            # Branch B: intended |e>
            # =========================================================

            play(r180, qb_el)
            align()

            if save_m0_state:
                measureMacro.measure(with_state=True, targets=[I0, Q0], state=m0)  # M0
            else:
                measureMacro.measure(with_state=False, targets=[I0, Q0])           # M0

            sequenceMacros.post_select(
                accept=acc_g,
                I=I0, Q=Q0,
                target_state="g",
                policy=post_sel_policy,
                **post_sel_kwargs,
            )
            sequenceMacros.post_select(
                accept=acc_e,
                I=I0, Q=Q0,
                target_state="e",
                policy=post_sel_policy,
                **post_sel_kwargs,
            )

            save(I0, I0_st); save(Q0, Q0_st)
            save(acc_g, accg_st); save(acc_e, acce_st)
            if save_m0_state:
                save(m0, m0_st)

            wait(int(qb_therm_clks))

        with stream_processing():
            # IQ per shot per branch -> shape (n_shots, 2)
            I0_st.buffer(2).buffer(n_shots).save("I0")
            Q0_st.buffer(2).buffer(n_shots).save("Q0")

            # Core memberships per shot per branch -> shape (n_shots, 2)
            accg_st.boolean_to_int().buffer(2).buffer(n_shots).save("acc_gcore")
            acce_st.boolean_to_int().buffer(2).buffer(n_shots).save("acc_ecore")

            # Averages -> shape (2,)
            accg_st.boolean_to_int().buffer(2).average().save("acc_gcore_rate")
            acce_st.boolean_to_int().buffer(2).average().save("acc_ecore_rate")

            if save_m0_state:
                m0_st.boolean_to_int().buffer(2).buffer(n_shots).save("m0_state")

    return prog

def readout_butterfly_measurement(
    qb_el,
    r180,
    post_sel_policy,
    post_sel_kwargs,
    M0_MAX_TRIALS,
    n_shots,
    wait_between_shots=10000,
    *,
    bindings: "ExperimentBindings | None" = None,
):
    """
    Butterfly readout with *post-selection* on M0, but with a gapless M0->M1->M2 triplet.

    For each shot, for each branch (target |g> then target |e>):
      - repeat:
          M0, M1, M2 (back-to-back)
          post-select using M0 via sequenceMacros.post_select(... -> sets `accept`)
          if rejected: apply conditional pi (using I0 vs threshold) and retry
        until accept or MAX_TRIALS reached
      - save the last triplet (accepted if accept==True, otherwise last failed attempt)
    """
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        qb_el = qb_el or _names.get("qubit", "__qb")
    elif qb_el is None:
        raise ValueError("qb_el is required when bindings are not provided")

    MAX_PREP_TRIALS = int(M0_MAX_TRIALS)

    # Threshold used for the *correction* (the post-select policy can be different)
    ro_disc_params = getattr(measureMacro, "_ro_disc_params", None) or {}
    thr = ro_disc_params.get("threshold", 0)

    with program() as ro_butterfly_meas:
        # --- Per-measurement I/Q ---
        I0, Q0 = declare(fixed), declare(fixed)
        I1, Q1 = declare(fixed), declare(fixed)
        I2, Q2 = declare(fixed), declare(fixed)

        # --- Optional "state" returned by measureMacro.measure(with_state=True, ...) ---
        m0 = declare(bool)
        m1 = declare(bool)
        m2 = declare(bool)

        # --- Loop control ---
        n = declare(int)
        tries = declare(int)
        accept = declare(bool)

        # --- Streams ---
        state_st = declare_stream()
        I0_st, Q0_st = declare_stream(), declare_stream()
        I1_st, Q1_st = declare_stream(), declare_stream()
        I2_st, Q2_st = declare_stream(), declare_stream()
        acc_st = declare_stream()
        tries_st = declare_stream()
        iter_st = declare_stream()

        with for_(n, 0, n < n_shots, n + 1):

            # =========================================================
            # Branch A: target_state = "g"
            # =========================================================
            assign(tries, 0)
            assign(accept, False)

            with while_((~accept) & (tries < MAX_PREP_TRIALS)):

                # ---- GAPLESS triple measurement ----
                measureMacro.measure(with_state=True, targets=[I0, Q0], state=m0)  # M0
                measureMacro.measure(with_state=True, targets=[I1, Q1], state=m1)  # M1
                measureMacro.measure(with_state=True, targets=[I2, Q2], state=m2)  # M2

                # ---- Post-select based on M0 (I0,Q0) ----
                sequenceMacros.post_select(
                    accept=accept,
                    I=I0,
                    Q=Q0,
                    target_state="g",
                    policy=post_sel_policy,
                    **post_sel_kwargs,
                )

                # ---- Corrective action if rejected (do it here) ----
                with if_(~accept):
                    # If we want |g> but M0 looks "excited" under scalar threshold, flip.
                    sequenceMacros.conditional_reset_ground(I0, thr, r180, qb_el)
                assign(tries, tries + 1)

            # Save once for this branch (accepted triplet if accept==True else last attempt)
            save(m0, state_st); save(m1, state_st); save(m2, state_st)
            save(I0, I0_st);    save(Q0, Q0_st)
            save(I1, I1_st);    save(Q1, Q1_st)
            save(I2, I2_st);    save(Q2, Q2_st)
            save(accept, acc_st)
            save(tries, tries_st)

            # =========================================================
            # Branch B: target_state = "e"
            # =========================================================
            assign(tries, 0)
            assign(accept, False)

            play(r180, qb_el)  # Prepare |e> before starting M0-M1-M2 attempts
            align()
            with while_((~accept) & (tries < MAX_PREP_TRIALS)):

                # ---- GAPLESS triple measurement ----
                measureMacro.measure(with_state=True, targets=[I0, Q0], state=m0)  # M0
                measureMacro.measure(with_state=True, targets=[I1, Q1], state=m1)  # M1
                measureMacro.measure(with_state=True, targets=[I2, Q2], state=m2)  # M2

                # ---- Post-select based on M0 (I0,Q0) ----
                sequenceMacros.post_select(
                    accept=accept,
                    I=I0,
                    Q=Q0,
                    target_state="e",
                    policy=post_sel_policy,
                    **post_sel_kwargs,
                )

                # ---- Corrective action if rejected ----
                with if_(~accept):
                    sequenceMacros.conditional_reset_excited(I0, thr, r180, qb_el)
                assign(tries, tries + 1)

            # Save once for this branch
            save(m0, state_st); save(m1, state_st); save(m2, state_st)
            save(I0, I0_st);    save(Q0, Q0_st)
            save(I1, I1_st);    save(Q1, Q1_st)
            save(I2, I2_st);    save(Q2, Q2_st)
            save(accept, acc_st)
            save(tries, tries_st)

            # Optional per-shot marker
            save(n, iter_st)

            wait(wait_between_shots)

        with stream_processing():
            # states: (n_shots, 2 branches, 3 measurements)
            # Convert boolean to int to avoid numpy bool8 dtype descriptor issues
            state_st.boolean_to_int().buffer(3).buffer(2).buffer(n_shots).save("states")

            # IQ: (n_shots, 2 branches)
            I0_st.buffer(2).buffer(n_shots).save("I0")
            Q0_st.buffer(2).buffer(n_shots).save("Q0")
            I1_st.buffer(2).buffer(n_shots).save("I1")
            Q1_st.buffer(2).buffer(n_shots).save("Q1")
            I2_st.buffer(2).buffer(n_shots).save("I2")
            Q2_st.buffer(2).buffer(n_shots).save("Q2")

            # accept/tries: (n_shots, 2 branches)
            acc_st.boolean_to_int().buffer(2).average().save("acceptance_rate")
            tries_st.buffer(2).average().save("average_tries")

            iter_st.save("iteration")

    return ro_butterfly_meas


def readout_leakage_benchmarking(ro_el, qb_el, r180, control_bits, qb_therm_clks, num_sequences, n_avg, *, bindings: "ExperimentBindings | None" = None):
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        ro_el = ro_el or _names.get("readout", "__ro")
        qb_el = qb_el or _names.get("qubit", "__qb")
    else:
        if ro_el is None:
            raise ValueError("ro_el is required when bindings are not provided")
        if qb_el is None:
            raise ValueError("qb_el is required when bindings are not provided")
    bit_rows, num_bits = control_bits.shape
    num_bits += 1
    with program() as ro_leakage_bm:
        sequence_num = declare(int)
        n = declare(int)
        i_mem = declare(int)

        I     = declare(fixed)
        Q     = declare(fixed)
        state = declare(bool)

        I_st = declare_stream()
        Q_st = declare_stream()
        state_st = declare_stream()
        sequence_num_st = declare_stream()

        for sequence_idx, bit_row in enumerate(control_bits):
            assign(sequence_num, sequence_idx)
            with for_(n, 0, n < n_avg, n + 1):
                measureMacro.measure(with_state=True,
                                                targets=[I,Q], state=state)
                align(ro_el, qb_el)

                save(I, I_st)
                save(Q, Q_st)
                save(state, state_st)
                with for_each_(i_mem, bit_row):
                    with if_(i_mem == 1):
                        play(r180, qb_el)                          # pi_val-pulse
                    with else_():
                        play(r180*amp(0), qb_el)                   # identity
                    align(qb_el, ro_el)

                    measureMacro.measure(with_state=True, targets=[I,Q], state=state)
                    save(I, I_st)
                    save(Q, Q_st)
                    save(state, state_st)

                wait(int(qb_therm_clks), qb_el, ro_el)
            save(sequence_num, sequence_num_st)

        with stream_processing():
            I_st.buffer(num_bits).buffer(n_avg).buffer(bit_rows).save("I")
            Q_st.buffer(num_bits).buffer(n_avg).buffer(bit_rows).save("Q")
            state_st.buffer(num_bits).buffer(n_avg).buffer(bit_rows).save("state_flag")
            sequence_num_st.save("iteration")
    return ro_leakage_bm


def qubit_reset_benchmark(qb_el: str, random_bits, r180: str,
                          qb_therm_clks: int, num_shots: int, *, bindings: "ExperimentBindings | None" = None):
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        qb_el = qb_el or _names.get("qubit", "__qb")
    elif qb_el is None:
        raise ValueError("qb_el is required when bindings are not provided")
    bit_size = len(random_bits)

    ro_disc_params = getattr(measureMacro, "_ro_disc_params", None) or {}
    thr = ro_disc_params.get("threshold", 0)
    with program() as prog:
        # streams
        I1_st  = declare_stream()
        Q1_st  = declare_stream()
        I2_st  = declare_stream()
        Q2_st  = declare_stream()
        s1_st  = declare_stream()
        s2_st  = declare_stream()
        trg_st = declare_stream()
        n_st   = declare_stream()

        # loop vars
        rep = declare(int)
        bit = declare(bool)

        # measured vars
        I1, Q1 = declare(fixed), declare(fixed)
        I2, Q2 = declare(fixed), declare(fixed)
        state1 = declare(bool)
        state2 = declare(bool)

        with for_(rep, 0, rep < num_shots, rep + 1):
            with for_each_(bit, random_bits):

                # Optional: prepare |e> for the "1" target by a leading pi_val
                with if_(bit):
                    play(r180, qb_el)

                # M1: measure current state (herald)
                measureMacro.measure(with_state=True, targets=[I1, Q1], state=state1)
                save(I1, I1_st)
                save(Q1, Q1_st)
                save(state1, s1_st)

                # Conditional reset toward |g> (ground is the reset target)
                sequenceMacros.conditional_reset_ground(
                    I1,
                    thr=measureMacro.thr,
                    r180=r180,
                    qb_el=qb_el,
                )

                # (Optional) allow depletion/thermalization before M2
                if qb_therm_clks > 0:
                    wait(int(qb_therm_clks), qb_el)

                # M2: verify after reset
                measureMacro.measure(with_state=True, targets=[I2, Q2], state=state2)
                save(I2, I2_st)
                save(Q2, Q2_st)
                save(state2, s2_st)

                # Record the intended target bit for this iteration
                save(bit, trg_st)

            save(rep, n_st)

        with stream_processing():
            trg_st.buffer(bit_size).buffer(num_shots).save("target")
            s1_st.buffer(bit_size).buffer(num_shots).save("state_M1")
            s2_st.buffer(bit_size).buffer(num_shots).save("state_M2")
            I1_st.buffer(bit_size).buffer(num_shots).save("I_M1")
            Q1_st.buffer(bit_size).buffer(num_shots).save("Q_M1")
            I2_st.buffer(bit_size).buffer(num_shots).save("I_M2")
            Q2_st.buffer(bit_size).buffer(num_shots).save("Q_M2")
            n_st.save("iteration")

    return prog


def active_qubit_reset_benchmark(qb_el: str, post_sel_policy, post_sel_kwargs, r180: str, qb_therm_clks, MAX_PREP_TRIALS, n_shots, *, bindings: "ExperimentBindings | None" = None):
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        qb_el = qb_el or _names.get("qubit", "__qb")
    elif qb_el is None:
        raise ValueError("qb_el is required when bindings are not provided")
    MAX_PREP_TRIALS = int(MAX_PREP_TRIALS)

    # Threshold used for the *correction* (the post-select policy can be different)
    thr = measureMacro._ro_disc_params.get("threshold") or 0.0
    with program() as active_reset_benchmark:
        # --- Per-measurement I/Q ---
        I0, Q0 = declare(fixed), declare(fixed)
        I1, Q1 = declare(fixed), declare(fixed)
        I2, Q2 = declare(fixed), declare(fixed)

        I0_st, Q0_st = declare_stream(), declare_stream()
        I1_st, Q1_st = declare_stream(), declare_stream()
        I2_st, Q2_st = declare_stream(), declare_stream()

        # --- Optional "state" returned by measureMacro.measure(with_state=True, ...) ---
        m0 = declare(bool)
        m1 = declare(bool)
        m2 = declare(bool)

        # --- Loop control ---
        n = declare(int)
        tries = declare(int)
        accept = declare(bool)

        # --- Streams ---
        m0_st = declare_stream()
        m1_st = declare_stream()
        m2_st = declare_stream()

        acc_st = declare_stream()
        tries_st = declare_stream()
        iter_st = declare_stream()

        with for_(n, 0, n < n_shots, n + 1):

            # =========================================================
            # Branch A: target_state = "g"
            # =========================================================
            assign(tries, 0)
            assign(accept, False)

            with while_((~accept) & (tries < MAX_PREP_TRIALS)):
                # ---- State prep measurement ----
                measureMacro.measure(with_state=True, targets=[I0, Q0], state=m0)  # M0

                # --- Reset protocol ---
                measureMacro.measure(with_state=True, targets=[I1, Q1], state=m1)  # M1
                sequenceMacros.conditional_reset_ground(I1, thr, r180, qb_el)

                # --- Final measurement to verify ---
                measureMacro.measure(with_state=True, targets=[I2, Q2], state=m2)  # M2

                # ---- Post-select based on M0 (I0,Q0) to ensure we prepared |g> ----
                sequenceMacros.post_select(
                    accept=accept,
                    I=I0,
                    Q=Q0,
                    target_state="g",
                    policy=post_sel_policy,
                    **post_sel_kwargs,
                )

                # ---- Corrective action if rejected (do it here) ----
                with if_(~accept):
                    # If we want |g> but M0 looks "excited" under scalar threshold, flip.
                    sequenceMacros.conditional_reset_ground(I0, thr, r180, qb_el)
                assign(tries, tries + 1)

            # Save once for this branch (accepted triplet if accept==True else last attempt)
            save(m0, m0_st); save(m1, m1_st); save(m2, m2_st)
            save(I0, I0_st); save(Q0, Q0_st)
            save(I1, I1_st); save(Q1, Q1_st)
            save(I2, I2_st); save(Q2, Q2_st)
            save(accept, acc_st)
            save(tries, tries_st)

            # =========================================================
            # Branch B: target_state = "e"
            # =========================================================
            assign(tries, 0)
            assign(accept, False)

            play(r180, qb_el)  # Prepare |e> before starting M0-M1-M2 attempts
            align()
            with while_((~accept) & (tries < MAX_PREP_TRIALS)):

                # ---- State prep measurement ----
                measureMacro.measure(with_state=True, targets=[I0, Q0], state=m0)  # M0

                # --- Reset protocol ---
                measureMacro.measure(with_state=True, targets=[I1, Q1], state=m1)  # M1
                sequenceMacros.conditional_reset_ground(I1, thr, r180, qb_el)

                # --- Final measurement to verify ---
                measureMacro.measure(with_state=True, targets=[I2, Q2], state=m2)  # M2

                # ---- Post-select based on M0 (I0,Q0) to ensure we prepared |e> ----
                sequenceMacros.post_select(
                    accept=accept,
                    I=I0,
                    Q=Q0,
                    target_state="e",
                    policy=post_sel_policy,
                    **post_sel_kwargs,
                )

                # ---- Corrective action if rejected ----
                with if_(~accept):
                    sequenceMacros.conditional_reset_excited(I0, thr, r180, qb_el)
                assign(tries, tries + 1)

            # Save once for this branch
            save(m0, m0_st); save(m1, m1_st); save(m2, m2_st)
            save(I0, I0_st); save(Q0, Q0_st)
            save(I1, I1_st); save(Q1, Q1_st)
            save(I2, I2_st); save(Q2, Q2_st)
            save(accept, acc_st)
            save(tries, tries_st)

            # Optional per-shot marker
            save(n, iter_st)

            wait(qb_therm_clks)

        with stream_processing():
            # states: (n_shots, 2 branches, 3 measurements)
            m0_st.buffer(2).buffer(n_shots).save("m0")
            m1_st.buffer(2).buffer(n_shots).save("m1")
            m2_st.buffer(2).buffer(n_shots).save("m2")

            I0_st.buffer(2).buffer(n_shots).save("I0")
            Q0_st.buffer(2).buffer(n_shots).save("Q0")
            I1_st.buffer(2).buffer(n_shots).save("I1")
            Q1_st.buffer(2).buffer(n_shots).save("Q1")
            I2_st.buffer(2).buffer(n_shots).save("I2")
            Q2_st.buffer(2).buffer(n_shots).save("Q2")


            acc_st.buffer(2).buffer(n_shots).save("accept")
            tries_st.buffer(2).buffer(n_shots).save("tries")

            iter_st.save("iteration")
    return active_reset_benchmark
