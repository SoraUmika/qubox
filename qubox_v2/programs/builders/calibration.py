
from contextlib import nullcontext
from qm.qua import *
from qualang_tools.loops import from_array
from ..macros.measure import measureMacro
from ..macros.sequence import sequenceMacros
import numpy as np

def sequential_qb_rotations(qb_el,  rotations:list[str], apply_avg, qb_therm_clks, n_shots):
    with program() as seq_rot_prog:
        n = declare(int)
        I = declare(fixed)
        Q = declare(fixed)
        state = declare(bool)

        I_st = declare_stream()
        Q_st = declare_stream()
        state_st = declare_stream()
        n_st = declare_stream()
        with for_(n, 0, n < n_shots, n + 1):
            for rotation in rotations:
                play(rotation, qb_el)
            align()
            measureMacro.measure(targets=[I,Q], state=state)
            wait(int(2*qb_therm_clks))
            save(I, I_st)
            save(Q, Q_st)
            save(state, state_st)
            save(n, n_st)
        with stream_processing():
            if apply_avg:
                I_st.average().save("I")
                Q_st.average().save("Q")
                state_st.boolean_to_int().average().save("state_flag")
            else:
                I_st.buffer(n_shots).save("I")
                Q_st.buffer(n_shots).save("Q")
                state_st.buffer(n_shots).save("state_flag")
            n_st.save("iteration")
    return seq_rot_prog

def all_xy(qb_el, allxy_rotation_sequences, qb_therm_clks, n_avg):
    with program() as all_xy:
        n = declare(int)
        state = declare(bool)
        I = declare(fixed)
        Q = declare(fixed)
        I_st = declare_stream()
        Q_st = declare_stream()
        state_st = declare_stream()
        n_st = declare_stream()
        with for_(n, 0, n < n_avg, n + 1):
            for (rot1, rot2) in allxy_rotation_sequences:
                #reset_if_phase(qb_el)
                play(rot1, qb_el)
                play(rot2, qb_el)
                align()
                measureMacro.measure(targets=[I,Q], with_state=True, state=state)
                wait(int(qb_therm_clks))
                save(I, I_st)
                save(Q, Q_st)
                save(state, state_st)
            save(n, n_st)
        with stream_processing():
            I_st.buffer(len(allxy_rotation_sequences)).average().save("I")
            Q_st.buffer(len(allxy_rotation_sequences)).average().save("Q")
            state_st.boolean_to_int().buffer(len(allxy_rotation_sequences)).average().save("Pe")
            n_st.save("iteration")
    return all_xy


def randomized_benchmarking(
    qb_el: str,
    sequences_ids: list[list[int]],
    qb_therm_clks: int,
    n_avg: int,
    *,
    primitives_by_id: dict[int, str],
    primitive_clks: int = 4,
    guard_clks: int = 18,
    interleave_op: str | None = None,
    interleave_clks: int | None = None,
    interleave_sentinel: int | None = None,   # <-- CHANGED: None => auto (max_id+1)
):
    if primitive_clks <= 0:
        raise ValueError("primitive_clks must be > 0")
    if guard_clks < 0:
        raise ValueError("guard_clks must be >= 0")
    if not primitives_by_id:
        raise ValueError("primitives_by_id cannot be empty.")

    # auto sentinel
    if interleave_sentinel is None:
        interleave_sentinel = int(max(primitives_by_id.keys())) + 1

    do_interleave = interleave_op is not None
    if do_interleave:
        if interleave_clks is None:
            raise ValueError("interleave_clks must be provided when interleave_op is not None.")
        if interleave_clks <= 0:
            raise ValueError("interleave_clks must be > 0")
    else:
        interleave_clks = 0  # not used

    with program() as rb_prog:
        n = declare(int)
        I = declare(fixed)
        Q = declare(fixed)
        state = declare(bool)
        op_id = declare(int)

        I_st = declare_stream()
        Q_st = declare_stream()
        state_st = declare_stream()
        n_st = declare_stream()

        with for_(n, 0, n < n_avg, n + 1):
            for seq_ids in sequences_ids:
                n_total = len(seq_ids)
                if do_interleave:
                    n_inter = int(sum(1 for x in seq_ids if int(x) == int(interleave_sentinel)))
                else:
                    n_inter = 0
                n_prim = int(n_total - n_inter)
                seq_duration = int(primitive_clks) * n_prim + int(interleave_clks) * n_inter

                align()
                wait(int(seq_duration) + int(guard_clks), measureMacro.active_element())

                seq_arr = np.asarray(seq_ids, dtype=int)
                if seq_arr.ndim != 1:
                    raise ValueError(f"Each seq_ids must be 1D list[int], got shape {seq_arr.shape}")

                with for_each_(op_id, seq_arr.tolist()):
                    with switch_(op_id, unsafe=True):
                        for pid in sorted(primitives_by_id.keys()):
                            with case_(int(pid)):
                                play(primitives_by_id[int(pid)], qb_el)

                        if do_interleave:
                            with case_(int(interleave_sentinel)):
                                play(str(interleave_op), qb_el)

                measureMacro.measure(targets=[I, Q], with_state=True, state=state)
                wait(int(2 * qb_therm_clks))

                save(I, I_st)
                save(Q, Q_st)
                save(state, state_st)

            save(n, n_st)

        with stream_processing():
            I_st.buffer(len(sequences_ids)).average().save("I")
            Q_st.buffer(len(sequences_ids)).average().save("Q")
            state_st.boolean_to_int().buffer(len(sequences_ids)).average().save("Pe")
            n_st.save("iteration")

    return rb_prog



def qubit_pulse_train_legacy(
    qb_el: str,
    reference_pulse: str,      # pi_val/2 pulse handle
    rotation_pulse: str,       # rotation pulse handle
    reference_clks: int,       # <-- needed to pre-advance readout timeline
    rotation_clks: int,
    N_values,                  # iterable of N; sequence applies N pulses
    qb_therm_clks: int,
    n_avg: int,
    *,
    latency_clks: int = 9,     # measured control-flow overhead
    use_strict_timing: bool = True,
):
    """
    Pulse-train experiment (gapless ref->rot->measure, compile-safe for large N):

      For each avg iteration and each N in N_values:
        wait(train_len, ro_el)             # pre-advance readout timeline to end of qubit train
        play(reference_pulse)
        play(rotation_pulse) N times (gapless)
        measure immediately (no align needed)
        wait thermalize

    Notes:
      - Avoids QUA switch_ for remainder.
      - Uses block size K = ceil(latency_clks / rotation_clks).
      - For N >= K: ref + first K rotations straight-line, then a QUA block loop,
        then Python-unrolled tail.
      - Measurement is scheduled gaplessly by advancing ro_el in advance (wait on ro_el).
    """
    N_values = list(map(int, N_values))
    n_N = len(N_values)
    if n_N == 0:
        raise ValueError("N_values is empty")

    reference_clks = int(reference_clks)
    rotation_clks  = int(rotation_clks)
    latency_clks   = int(latency_clks)

    if reference_clks < 0:
        raise ValueError("reference_clks must be >= 0")
    if rotation_clks <= 0:
        raise ValueError("rotation_clks must be a positive integer")
    if latency_clks <= 0:
        raise ValueError("latency_clks must be a positive integer")

    ro_el = measureMacro.active_element()

    # Block size so each runtime-loop iteration outputs >= latency_clks cycles
    K = max(1, (latency_clks + rotation_clks - 1) // rotation_clks)  # ceil(latency/rot)

    with program() as pulse_train_prog:
        n = declare(int)
        b = declare(int)   # block counter for runtime loops

        I = declare(fixed)
        Q = declare(fixed)

        I_st = declare_stream()
        Q_st = declare_stream()
        N_st = declare_stream()
        n_st = declare_stream()

        with for_(n, 0, n < int(n_avg), n + 1):
            align()
            for N in N_values:
                N = int(N)

                train_len = reference_clks + N * rotation_clks
                wait(train_len, ro_el)

                timing_ctx = strict_timing_() if use_strict_timing else nullcontext()
                with timing_ctx:
                    if N == 0:
                        play(reference_pulse, qb_el)

                    elif N < K:
                        play(reference_pulse, qb_el)
                        for _ in range(N):
                            play(rotation_pulse, qb_el)

                    else:
                        blocks, rem = divmod(N, K)

                        play(reference_pulse, qb_el)
                        for _ in range(K):
                            play(rotation_pulse, qb_el)

                        remaining_blocks = blocks - 1
                        if remaining_blocks > 0:
                            with for_(b, 0, b < remaining_blocks, b + 1):
                                for _ in range(K):
                                    play(rotation_pulse, qb_el)

                        for _ in range(rem):
                            play(rotation_pulse, qb_el)

                measureMacro.measure(targets=[I, Q])

                # Thermalization between points
                wait(int(qb_therm_clks), qb_el, ro_el)

                # Save one point
                save(I, I_st)
                save(Q, Q_st)
                save(N, N_st)

            save(n, n_st)

        with stream_processing():
            I_st.buffer(n_N).average().save("I")
            Q_st.buffer(n_N).average().save("Q")
            N_st.buffer(n_N).save("N_values")
            n_st.save("iteration")

    return pulse_train_prog

def qubit_pulse_train(
    qb_el: str,
    reference_pulse: str,      # pi_val/2 pulse handle
    rotation_pulse: str,       # rotation pulse handle
    N_values,                  # iterable of N; sequence applies N pulses
    qb_therm_clks: int,
    n_avg: int,
    run_reference: bool
):
    """
    Pulse-train experiment (gapless ref->rot->measure, compile-safe for large N):

      For each avg iteration and each N in N_values:
        wait(train_len, ro_el)             # pre-advance readout timeline to end of qubit train
        play(reference_pulse)
        play(rotation_pulse) N times (gapless)
        measure immediately (no align needed)
        wait thermalize

    Notes:
      - Avoids QUA switch_ for remainder.
      - Uses block size K = ceil(latency_clks / rotation_clks).
      - For N >= K: ref + first K rotations straight-line, then a QUA block loop,
        then Python-unrolled tail.
      - Measurement is scheduled gaplessly by advancing ro_el in advance (wait on ro_el).
    """
    n_N = len(N_values)
    with program() as pulse_train_prog:
        n = declare(int)

        I = declare(fixed)
        Q = declare(fixed)
        state = declare(bool)

        I_st = declare_stream()
        Q_st = declare_stream()
        state_st = declare_stream()
        n_st = declare_stream()

        if run_reference:
            I_ref = declare(fixed)
            Q_ref = declare(fixed)
            state_ref = declare(bool)
            I_ref_st = declare_stream()
            Q_ref_st = declare_stream()
            state_ref_st = declare_stream()
        with for_(n, 0, n < int(n_avg), n + 1):
            for N in N_values:
                if run_reference:
                    play(reference_pulse, qb_el)
                    for _ in range(N):
                        play(rotation_pulse*amp(0), qb_el)
                    align()
                    measureMacro.measure(targets=[I_ref, Q_ref], state=state_ref)

                    # Thermalization between points
                    wait(int(qb_therm_clks))

                    # Save one point
                    save(I_ref, I_ref_st)
                    save(Q_ref, Q_ref_st)
                    save(state_ref, state_ref_st)

                play(reference_pulse, qb_el)
                for _ in range(N):
                    play(rotation_pulse, qb_el)
                align()
                measureMacro.measure(targets=[I, Q], state=state)

                # Thermalization between points
                wait(int(qb_therm_clks))

                # Save one point
                save(I, I_st)
                save(Q, Q_st)
                save(state, state_st)

            save(n, n_st)

        with stream_processing():
            if run_reference:
                I_ref_st.buffer(n_N).average().save("I_ref")
                Q_ref_st.buffer(n_N).average().save("Q_ref")
                state_ref_st.boolean_to_int().buffer(n_N).average().save("state_ref")

            I_st.buffer(n_N).average().save("I")
            Q_st.buffer(n_N).average().save("Q")
            state_st.boolean_to_int().buffer(n_N).average().save("state")
            n_st.save("iteration")

    return pulse_train_prog

def drag_calibration_YALE(
    qb_el: str,
    amps,         # list/np.array of alpha pre-factors (dimensionless)
    x180, x90, y180, y90,    # your pulse handles
    qb_therm_clks: int,
    n_avg: int = 200,
):
    with program() as drag:
        n = declare(int)
        a = declare(fixed)
        I = declare(fixed)
        Q = declare(fixed)
        I1_st = declare_stream()
        Q1_st = declare_stream()
        I2_st = declare_stream()
        Q2_st = declare_stream()
        n_st = declare_stream()

        with for_(n, 0, n < n_avg, n + 1):
            with for_(*from_array(a, amps)):
                play(x180 * amp(1, 0, 0, a), qb_el)
                play(y90 * amp(a, 0, 0, 1), qb_el)
                align()

                measureMacro.measure(targets=[I, Q])

                wait(int(qb_therm_clks))
                save(I, I1_st)
                save(Q, Q1_st)
                align()

                play(y180 * amp(a, 0, 0, 1), qb_el)
                play(x90 * amp(1, 0, 0, a), qb_el)

                align()
                measureMacro.measure(targets=[I, Q])
                wait(int(qb_therm_clks))
                save(I, I2_st)
                save(Q, Q2_st)
            save(n, n_st)

        with stream_processing():
            I1_st.buffer(len(amps)).average().save("I1")
            Q1_st.buffer(len(amps)).average().save("Q1")
            I2_st.buffer(len(amps)).average().save("I2")
            Q2_st.buffer(len(amps)).average().save("Q2")

            n_st.save("iteration")
    return drag


def drag_calibration_GOOGLE(
    qb_el: str,
    amps,          # list / np.array of alpha pre-factors to scan
    iters,         # list / np.array of iteration counts, e.g. np.arange(0, 26, 1)
    x180,          # your calibrated pi pulse handle
    qb_therm_clks: int,
    n_avg: int = 200,
):
    """
    Google-style DRAG calibration:
    - For each alpha in `amps`
    - For each iteration count in `iters`
      - Apply many [x180(+alpha), x180(-alpha)] pairs in a row to amplify coherent error
      - Measure I/Q + state
    The correct alpha is the one that keeps the qubit closest to |g> even after many repetitions.
    """

    ro_el = measureMacro.active_element()

    with program() as drag:
        # QUA vars
        n = declare(int)        # averaging counter
        a = declare(fixed)      # DRAG prefactor we're sweeping
        it = declare(int)       # how many pulse pairs to apply this shot
        pulses = declare(int)   # loop counter inside the burst

        I = declare(fixed)
        Q = declare(fixed)
        state = declare(bool)

        # Streams
        I_st = declare_stream()
        Q_st = declare_stream()
        state_st = declare_stream()
        n_st = declare_stream()

        with for_(n, 0, n < n_avg, n + 1):
            # sweep over DRAG prefactor
            with for_(*from_array(a, amps)):
                # sweep over iteration count
                with for_(*from_array(it, iters)):

                    # error amplification loop:
                    # repeat [x180(+alpha); x180(-alpha)] 'it' times
                    with for_(pulses, 0, pulses <= it, pulses + 1):
                        # +alpha pulse
                        play(x180 * amp(1, 0, 0, a), qb_el)
                        # -alpha pulse (note sign flip on both main amp and DRAG amp)
                        play(x180 * amp(-1, 0, 0, -a), qb_el)

                    # measure after the burst
                    align(qb_el, ro_el)
                    measureMacro.measure(with_state=True, state=state, targets=[I, Q])

                    # passive reset
                    wait(int(qb_therm_clks), ro_el)

                    # save data
                    save(I, I_st)
                    save(Q, Q_st)
                    save(state, state_st)

            save(n, n_st)

        with stream_processing():
            I_st.buffer(len(iters)).buffer(len(amps)).average().save("I")
            Q_st.buffer(len(iters)).buffer(len(amps)).average().save("Q")
            state_st.boolean_to_int().buffer(len(iters)).buffer(len(amps)).average().save("state")
            n_st.save("iteration")

    return drag
