
from contextlib import nullcontext
from qm.qua import *
from qualang_tools.loops import from_array
from ..macros.measure import measureMacro
from ..macros.sequence import sequenceMacros
import numpy as np

def sequential_qb_rotations(qb_el, rotations:list[str], apply_avg, qb_therm_clks, n_shots, *, bindings: "ExperimentBindings | None" = None):
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        qb_el = qb_el or _names.get("qubit", "__qb")
    elif qb_el is None:
        raise ValueError("qb_el is required when bindings are not provided")
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

def all_xy(qb_el, allxy_rotation_sequences, qb_therm_clks, n_avg, *, bindings: "ExperimentBindings | None" = None):
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        qb_el = qb_el or _names.get("qubit", "__qb")
    elif qb_el is None:
        raise ValueError("qb_el is required when bindings are not provided")
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
    bindings: "ExperimentBindings | None" = None,
):
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        qb_el = qb_el or _names.get("qubit", "__qb")
    elif qb_el is None:
        raise ValueError("qb_el is required when bindings are not provided")
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


def drag_calibration_YALE(
    qb_el: str,
    amps,         # list/np.array of alpha pre-factors (dimensionless)
    x180, x90, y180, y90,    # your pulse handles
    qb_therm_clks: int,
    n_avg: int = 200,
    *,
    bindings: "ExperimentBindings | None" = None,
):
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        qb_el = qb_el or _names.get("qubit", "__qb")
    elif qb_el is None:
        raise ValueError("qb_el is required when bindings are not provided")
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
    *,
    bindings: "ExperimentBindings | None" = None,
):
    """
    Google-style DRAG calibration:
    - For each alpha in `amps`
    - For each iteration count in `iters`
      - Apply many [x180(+alpha), x180(-alpha)] pairs in a row to amplify coherent error
      - Measure I/Q + state
    The correct alpha is the one that keeps the qubit closest to |g> even after many repetitions.
    """
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        qb_el = qb_el or _names.get("qubit", "__qb")
    elif qb_el is None:
        raise ValueError("qb_el is required when bindings are not provided")

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
