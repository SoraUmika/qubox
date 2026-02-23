
from qm.qua import *
from qualang_tools.loops import from_array
from ..macros.measure import measureMacro
from ..macros.sequence import sequenceMacros
import numpy as np


def temporal_rabi(qb_el, pulse, pulse_clks, pulse_gain, qb_therm_clks, n_avg):
    """
    Perform Rabi oscillations in the time domain by varying the pulse duration (in clock cycles).

    Parameters:
        ro_el             : Readout resonator element
        qb_el             : Qubit element
        qb_gain           : Gain for the qubit drive pulse
        qb_therm_clks     : Thermalization wait after each measurement
        pulse_clks        : Array/list of pulse durations (in clock cycles) to use
        pulse             : Name of the qubit drive pulse (default "gaussian_X")
        n_avg             : Number of averaging iterations (default=1)
    """
    with program() as rabi_prog:
        pulse_clk = declare(int)
        n = declare(int)
        I = declare(fixed)
        Q = declare(fixed)
        I_st = declare_stream()
        Q_st = declare_stream()
        n_st = declare_stream()
        with for_(n, 0, n < n_avg, n + 1):
            with for_(*from_array(pulse_clk, pulse_clks)):
                play(pulse*amp(pulse_gain), qb_el, duration=pulse_clk)
                align(qb_el, measureMacro.active_element())
                measureMacro.measure(targets=[I,Q])
                wait(int(qb_therm_clks))
                save(I, I_st)
                save(Q, Q_st)
            save(n, n_st)
        with stream_processing():
            I_st.buffer(len(pulse_clks)).average().save("I")
            Q_st.buffer(len(pulse_clks)).average().save("Q")
            n_st.save("iteration")
    return rabi_prog

def power_rabi(qb_el, qb_clock_len:int, gains, qb_therm_clks, pulse, truncate_clks, n_avg:int=1000):
    """
    Perform Rabi oscillations in the amplitude domain by sweeping pulse amplitude (gain).

    Parameters:
        ro_el          : Readout resonator element
        qb_el          : Qubit element
        qb_clock_len   : Fixed pulse duration (in clock cycles) for Rabi drive
        gains          : Python array/list of gain (amplitude) values to test
        qb_therm_clks  : Wait time (in clock cycles) for thermalization
        pulse          : Name of the qubit drive pulse (default "gaussian_X")
        truncate       : Whether to truncate the pulse (default False)
        n_avg          : Number of averaging iterations (default=1000)
    """
    with program() as power_rabi_prog:
        g = declare(fixed)
        n = declare(int)
        I = declare(fixed)
        Q = declare(fixed)
        I_st = declare_stream()
        Q_st = declare_stream()
        n_st = declare_stream()
        with for_(n, 0, n < n_avg, n + 1):
            with for_(*from_array(g, gains)):
                play(pulse*amp(g), qb_el, duration=qb_clock_len, truncate=truncate_clks)
                align(qb_el, measureMacro.active_element())
                measureMacro.measure(targets=[I, Q])
                wait(int(qb_therm_clks))
                save(I, I_st)
                save(Q, Q_st)
            save(n, n_st)
        with stream_processing():
            I_st.buffer(len(gains)).average().save("I")
            Q_st.buffer(len(gains)).average().save("Q")
            n_st.save("iteration")
    return power_rabi_prog

def time_rabi_chevron(ro_el, qb_el, pulse, pulse_gain, qb_if, dfs, duration_clks, qb_therm_clks, n_avg:int=1):
    """
    Generate a Rabi chevron (time vs. frequency) by sweeping both pulse duration and detuning.

    Parameters:
        ro_el           : Readout resonator element
        qb_el           : Qubit element
        pulse           : Name of the qubit drive pulse
        pulse_gain      : Gain amplitude for the qubit pulse
        qb_if           : Base IF for the qubit drive
        dfs             : Python array/list of frequency detunings relative to qb_if
        duration_clks   : Python array/list of pulse durations (clock cycles)
        qb_therm_clks   : Thermalization wait time after readout
        n_avg           : Number of averaging iterations (default=1)
    """
    with program() as time_rabi_chevron_program:
        n = declare(int)
        f = declare(int)
        t = declare(int)
        I = declare(fixed)
        Q = declare(fixed)
        I_st = declare_stream()
        Q_st = declare_stream()
        n_st = declare_stream()

        with for_(n, 0, n < n_avg, n + 1):
            with for_(*from_array(t, duration_clks)):
                with for_(*from_array(f, dfs)):
                    update_frequency(qb_el, f + qb_if)
                    play(pulse * amp(pulse_gain), qb_el, duration=t)
                    align(qb_el, measureMacro.active_element())
                    measureMacro.measure(targets=[I,Q])
                    wait(int(qb_therm_clks), measureMacro.active_element())
                    save(I, I_st)
                    save(Q, Q_st)
            save(n, n_st)

        with stream_processing():
            I_st.buffer(len(dfs)).buffer(len(duration_clks)).average().save("I")
            Q_st.buffer(len(dfs)).buffer(len(duration_clks)).average().save("Q")
            n_st.save("iteration")
    return time_rabi_chevron_program

def power_rabi_chevron(ro_el, qb_el, pulse, pulse_duration, qb_if, dfs, amplitudes, qb_therm_clks, n_avg:int=1):
    """
    Generate a Rabi chevron (power vs. frequency) by sweeping both pulse amplitude and detuning.

    Parameters:
        ro_el           : Readout resonator element
        qb_el           : Qubit element
        pulse           : Name of the qubit drive pulse
        pulse_duration  : Fixed duration (in clock cycles) for each pulse
        qb_if           : Base IF for the qubit drive
        dfs             : Python array/list of detunings relative to qb_if
        amplitudes      : Python array/list of gain amplitudes to sweep
        qb_therm_clks   : Thermalization wait after readout
        n_avg           : Number of averaging iterations (default=1)
    """
    with program() as rabi_chevron_prog:
        n = declare(int)
        df = declare(int)
        a = declare(fixed)
        I = declare(fixed)
        Q = declare(fixed)
        I_st = declare_stream()
        Q_st = declare_stream()
        n_st = declare_stream()
        with for_(n, 0, n < n_avg, n + 1):
            with for_(*from_array(a, amplitudes)):
                with for_(*from_array(df, dfs)):
                    update_frequency(qb_el, df + qb_if)
                    play(pulse * amp(a), qb_el, duration=pulse_duration)
                    align(qb_el, measureMacro.active_element())
                    measureMacro.measure(targets=[I,Q])
                    wait(int(qb_therm_clks), measureMacro.active_element())
                    save(I, I_st)
                    save(Q, Q_st)
            save(n, n_st)
        with stream_processing():
            I_st.buffer(len(dfs)).buffer(len(amplitudes)).average().save("I")
            Q_st.buffer(len(dfs)).buffer(len(amplitudes)).average().save("Q")
            n_st.save("iteration")
    return rabi_chevron_prog

def ramsey_chevron(ro_el, qb_el, r90, qb_if, dfs, delay_clks, qb_therm_clks, n_avg:int=1):
    """
    Perform Ramsey chevron: sweep both delay time and detuning to map out Ramsey fringes.

    Parameters:
        ro_el           : Readout resonator element
        qb_el           : Qubit element
        r90             : Name of the pi_val/2 pulse used to prepare/close Ramsey
        qb_if           : Base IF for qubit drive
        dfs             : Python array/list of detunings relative to qb_if
        delay_clks      : Python array/list of free-evolution delays (in clock cycles)
        qb_therm_clks   : Thermalization wait after readout
        n_avg           : Number of averaging iterations (default=1)
    """
    with program() as ramsey_chevron_prog:
        n = declare(int)
        df = declare(int)
        delay = declare(int)
        I = declare(fixed)
        Q = declare(fixed)
        I_st = declare_stream()
        Q_st = declare_stream()
        n_st = declare_stream()
        with for_(n, 0, n < n_avg, n + 1):
            with for_(*from_array(delay, delay_clks)):
                with for_(*from_array(df, dfs)):
                    update_frequency(qb_el, df + qb_if)
                    with if_(delay >= 4):
                        play(r90, qb_el)
                        wait(delay, qb_el)
                        play(r90, qb_el)
                    with else_():
                        play(r90, qb_el)
                        play(r90, qb_el)
                    align(qb_el, measureMacro.active_element())
                    I, Q = measureMacro.measure(targets=[I,Q])
                    wait(int(qb_therm_clks), measureMacro.active_element())
                    save(I, I_st)
                    save(Q, Q_st)
            save(n, n_st)
        with stream_processing():
            I_st.buffer(len(dfs)).buffer(len(delay_clks)).average().save("I")
            Q_st.buffer(len(dfs)).buffer(len(delay_clks)).average().save("Q")
            n_st.save("iteration")
    return ramsey_chevron_prog

def T1_relaxation(qb_el, r180, wait_cycles_list, qb_therm_clks, n_avg):
    """
    Measure T1 (energy relaxation) by applying a pi_val-pulse and then waiting variable times.

    Parameters:
        ro_el             : Readout resonator element
        qb_el             : Qubit element
        r180              : Name of the pi_val-pulse that inverts |g>->|e>
        wait_cycles_list  : Python array/list of wait times (in clock cycles) before readout
        qb_therm_clks     : Thermalization wait after readout
        n_avg             : Number of averaging iterations
    """
    with program() as T1_prog:
        cycles_to_wait = declare(int)
        n = declare(int)
        I = declare(fixed)
        Q = declare(fixed)
        I_st = declare_stream()
        Q_st = declare_stream()
        n_st = declare_stream()
        with for_(n, 0, n < n_avg, n + 1):
            with for_(*from_array(cycles_to_wait, wait_cycles_list)):
                play(r180, qb_el)
                align(qb_el, measureMacro.active_element())
                wait(cycles_to_wait)
                measureMacro.measure(targets=[I,Q])
                wait(int(qb_therm_clks))
                save(I, I_st)
                save(Q, Q_st)
            save(n, n_st)
        with stream_processing():
            I_st.buffer(len(wait_cycles_list)).average().save("I")
            Q_st.buffer(len(wait_cycles_list)).average().save("Q")
            n_st.save("iteration")
    return T1_prog

def T2_ramsey(qb_el, r90, wait_cycles_list, qb_therm_clks, n_avg):
    """
    Measure T2* (Ramsey dephasing) by applying two pi_val/2 pulses separated by variable wait times.

    Parameters:
        ro_el             : Readout resonator element
        qb_el             : Qubit element
        r90               : Name of the pi_val/2 pulse
        wait_cycles_list  : Python array/list of free-evolution delays (clock cycles)
        qb_therm_clks     : Thermalization wait after readout
        n_avg             : Number of averaging iterations
    """
    with program() as T2_ramsey_prog:
        delay_clk = declare(int)
        n = declare(int)
        I = declare(fixed)
        Q = declare(fixed)
        I_st = declare_stream()
        Q_st = declare_stream()
        n_st = declare_stream()
        with for_(n, 0, n < n_avg, n + 1):
            with for_(*from_array(delay_clk, wait_cycles_list)):
                sequenceMacros.qubit_ramsey(delay_clk, qb_el=qb_el, r90_1=r90, r90_2=r90)
                align(qb_el, measureMacro.active_element())
                measureMacro.measure(targets=[I,Q])
                wait(int(qb_therm_clks))
                save(I, I_st)
                save(Q, Q_st)
            save(n, n_st)
        with stream_processing():
            I_st.buffer(len(wait_cycles_list)).average().save("I")
            Q_st.buffer(len(wait_cycles_list)).average().save("Q")
            n_st.save("iteration")
    return T2_ramsey_prog

def T2_echo(qb_el, r180, r90,
            half_wait_cycles_list, qb_therm_clks, n_avg):
    """
    Measure T2 (Hahn echo) by applying pi_val/2 -- wait -- pi_val -- wait -- pi_val/2 sequence,
    with the wait time swept in half-intervals.

    Parameters:
        ro_el                : Readout resonator element
        qb_el                : Qubit element
        r180                 : Name of the pi_val-pulse
        r90                  : Name of the pi_val/2 pulse
        half_wait_cycles_list: Python array/list of half-wait times
        qb_therm_clks        : Thermalization wait after measurement
        n_avg                : Number of averaging iterations
    """
    with program() as T2_echo_prog:
        delay_clk = declare(int)
        n = declare(int)
        I = declare(fixed)
        Q = declare(fixed)
        I_st = declare_stream()
        Q_st = declare_stream()
        n_st = declare_stream()
        with for_(n, 0, n < n_avg, n + 1):
            with for_(*from_array(delay_clk, half_wait_cycles_list)):
                sequenceMacros.qubit_echo(delay_clk, delay_clk, qb_el, r90, r180)
                align(qb_el, measureMacro.active_element())
                measureMacro.measure(targets=[I,Q])
                wait(int(qb_therm_clks))
                save(I, I_st)
                save(Q, Q_st)
            save(n, n_st)
        with stream_processing():
            I_st.buffer(len(half_wait_cycles_list)).average().save("I")
            Q_st.buffer(len(half_wait_cycles_list)).average().save("Q")
            n_st.save("iteration")
    return T2_echo_prog

def ac_stark_shift(
    qb_el: str,
    iter_min: int,
    d: int,
    iters,              # array/list of iteration counts
    r180: str,          # name of the registered temp pi pulse
    qb_therm_clks: int,
    n_avg: int
):
    with program() as ac_stark_prog:
        n      = declare(int)
        it     = declare(int)
        pulses = declare(int)
        I      = declare(fixed)
        Q      = declare(fixed)
        state  = declare(bool)

        I_st      = declare_stream()
        Q_st      = declare_stream()
        state_st  = declare_stream()

        with for_(n, 0, n < n_avg, n + 1):
            with for_(*from_array(it, iters)):
                with for_(pulses, iter_min, pulses <= it, pulses + d):
                    play(r180 * amp(1),  qb_el)
                    play(r180 * amp(-1), qb_el)

                align(qb_el, measureMacro.active_element())
                measureMacro.measure(targets=[I, Q], with_state=True, state=state)
                wait(int(qb_therm_clks), measureMacro.active_element())

                save(I, I_st)
                save(Q, Q_st)
                save(state, state_st)

        with stream_processing():
            I_st.buffer(len(iters)).average().save("I")
            Q_st.buffer(len(iters)).average().save("Q")
            state_st.boolean_to_int().buffer(len(iters)).average().save("state")

    return ac_stark_prog


def residual_photon_ramsey(qb_el, test_ro_op, t_R_clks, t_relax_clk, t_buffer_clk, prep_e, test_ro_amp,
                            r90, r180, qb_therm_clks, n_avg):
    """
    Measure residual photons via a Ramsey experiment after a variable relaxation time. Based on
    PHYS. REV. APPLIED 5, 011001 (2016)
    """
    with program() as residual_photon_ramsey_prog:
        t_R_clk = declare(int)
        n = declare(int)
        I = declare(fixed)
        Q = declare(fixed)
        I_st = declare_stream()
        Q_st = declare_stream()

        n_st = declare_stream()
        with for_(n, 0, n < n_avg, n + 1):
            with for_(*from_array(t_R_clk, t_R_clks)):
                if prep_e:
                    play(r180 , qb_el)
                align()
                play(test_ro_op * amp(test_ro_amp), measureMacro.active_element())
                align()
                wait(t_relax_clk)
                sequenceMacros.qubit_ramsey(t_R_clk, qb_el, r90, r90)
                align()
                wait(t_buffer_clk)
                measureMacro.measure(targets=[I,Q])
                wait(int(qb_therm_clks))
                save(I, I_st)
                save(Q, Q_st)

            save(n, n_st)
        with stream_processing():
            I_st.buffer(len(t_R_clks)).average().save("I")
            Q_st.buffer(len(t_R_clks)).average().save("Q")

            n_st.save("iteration")
    return residual_photon_ramsey_prog
