
from contextlib import nullcontext
from qm.qua import *
from qualang_tools.loops import from_array
from .macros.measure_macro import measureMacro
from .macros.sequence_macro import sequenceMacros
import numpy as np 
from .gates_legacy import Gate, GateArray, Measure

def readout_trace(ro_therm_clks, n_avg):
    """
    Acquire and average raw ADC traces for a given readout resonator element.
    Parameters:
        ro_el     : QUA element label for the readout resonator
        ro_pulse  : Name of the readout pulse (default "readout")
        ro_gain   : Amplitude scaling for the readout pulse
        ro_if     : Intermediate frequency (in Hz) to set on the resonator
        n_avg     : Number of averages (iterations) to perform
    """
    with program() as raw_trace_prog:
        n = declare(int)
        adc_st = declare_stream(adc_trace=True)
        n_st = declare_stream()

        with for_(n, 0, n < n_avg, n + 1):
            reset_if_phase(measureMacro.active_element())
            measureMacro.measure(adc_stream=adc_st)
            wait(int(ro_therm_clks))
            save(n, n_st)
            wait(25_000)

        with stream_processing():
            adc_st.input1().average().save("adc1")
            adc_st.input2().average().save("adc2")
            adc_st.input1().save("adc1_single_run")
            adc_st.input2().save("adc2_single_run")
            n_st.save("iteration")
    return raw_trace_prog

def resonator_spectroscopy(ro_el, if_frequencies, depletion_len, n_avg: int=1):
    """
    Sweep readout IF frequencies to perform 1D resonator spectroscopy.
    For each IF, perform a measurement (I/Q) and optionally deplete residual photons.

    Parameters:
        ro_el          : QUA element for readout resonator
        ro_pulse       : Name of the readout pulse to use
        ro_gain        : Gain (amplitude) for the readout measurement
        if_frequencies : Python array/list of IFs to step through (integers)
        depletion_len  : Time (in clock cycles) to wait for photon depletion
        n_avg          : Number of averaging iterations (default=1)
    """
    with program() as resonator_spec:
        n = declare(int)
        f = declare(int)
        I = declare(fixed)
        Q = declare(fixed)
        I_st = declare_stream()
        Q_st = declare_stream()
        n_st = declare_stream()
        with for_(n, 0, n < n_avg, n + 1):
            with for_(*from_array(f, if_frequencies)):
                update_frequency(ro_el, f)
                measureMacro.measure(targets=[I,Q])
                wait(int(depletion_len/4), ro_el)
                save(I, I_st)
                save(Q, Q_st)
            save(n, n_st)
        with stream_processing():
            n_st.save("iteration")
            I_st.buffer(len(if_frequencies)).average().save("I")
            Q_st.buffer(len(if_frequencies)).average().save("Q")
    return resonator_spec

def resonator_power_spectroscopy(if_frequencies, gains, depletion_len, n_avg:int=1):
    """
    Perform a 2D sweep of readout IF and readout gain to map out resonator response versus power.

    Parameters:
        ro_el          : QUA element label for the readout resonator
        ro_pulse       : Name of the readout pulse to use
        if_frequencies : Python array/list of IFs to step through
        gains          : Python array/list of gain (amplitude) settings to step through
        depletion_len  : Time in clock cycles for photon depletion after measurement
        n_avg          : Number of averaging iterations (default=1)
    """
    with program() as resonator_spec_2D:
        n = declare(int)
        if_req = declare(int)
        g = declare(fixed)
        I = declare(fixed)
        Q = declare(fixed)
        I_st = declare_stream()  
        Q_st = declare_stream()  
        n_st = declare_stream()  
        with for_(n, 0, n < n_avg, n + 1):  
            with for_(*from_array(if_req, if_frequencies)):  
                update_frequency(measureMacro.active_element(), if_req)
                with for_each_(g, gains): 
                    measureMacro.measure(targets=[I,Q], gain=g)
                    wait(int(depletion_len/4), measureMacro.active_element())
                    save(I, I_st)
                    save(Q, Q_st)
            save(n, n_st)
        with stream_processing():
            n_st.save("iteration")
            I_st.buffer(len(gains)).buffer(len(if_frequencies)).average().save("I")
            Q_st.buffer(len(gains)).buffer(len(if_frequencies)).average().save("Q")
    return resonator_spec_2D

def qubit_spectroscopy(sat_pulse, qb_el, if_frequencies, qb_gain, qb_len, qb_therm_clks:int=4, n_avg:int=1):
    """
    Perform spectroscopy on the qubit by sweeping drive IF and measuring readout response.

    Parameters:tiaow
        ro_el          : Readout resonator element label
        qb_el          : Qubit element label
        if_frequencies : Python array/list of IFs to sweep for the qubit drive
        qb_gain        : Gain for the qubit drive pulse
        qb_len         : Duration (in clock cycles) of the qubit drive pulse
        qb_therm_clks  : Number of clock cycles to wait for qubit thermalization (default=4)
        n_avg          : Number of averaging iterations (default=1)
    """
    with program() as qubit_spec:
        n = declare(int)
        if_freq = declare(int)
        I = declare(fixed)
        Q = declare(fixed)
        I_st = declare_stream()
        Q_st = declare_stream()
        n_st = declare_stream()
        with for_(n, 0, n < n_avg, n + 1):
            with for_(*from_array(if_freq, if_frequencies)):
                update_frequency(qb_el, if_freq)
                if qb_len:
                    play(sat_pulse * amp(qb_gain), qb_el, duration=qb_len)
                else:
                    play(sat_pulse * amp(qb_gain), qb_el)
                align(qb_el, measureMacro.active_element())
                measureMacro.measure(targets=[I,Q])
                wait(int(qb_therm_clks), measureMacro.active_element())
                save(I, I_st)
                save(Q, Q_st)
            save(n, n_st)
        with stream_processing():
            I_st.buffer(len(if_frequencies)).average().save("I")
            Q_st.buffer(len(if_frequencies)).average().save("Q")
            n_st.save("iteration")
        return qubit_spec
    
def qubit_spectroscopy_ef(sat_pulse, qb_el, if_frequencies, qb_ge_if, qb_gain, qb_len, r180 , qb_therm_clks, n_avg:int=1):
    """
    Perform |e>→|f> spectroscopy by first preparing |e> via a π-pulse (r180), then sweeping drive IF.

    Parameters:
        ro_el          : Readout resonator element
        qb_el          : Qubit element
        if_frequencies : Python array/list of IFs for the spectroscopy sweep
        qb_ge_if       : IF at which to apply the π-pulse that drives |g>→|e>
        qb_gain        : Gain for the saturation pulse
        qb_len         : Duration of the saturation pulse
        r180           : Name of the π-pulse used to prepare |e>
        qb_therm_clks  : Thermalization wait time after readout
        n_avg          : Number of averaging iterations (default=1)
    """
    with program() as qubit_spec:
        n = declare(int)
        if_freq = declare(int)
        I = declare(fixed)
        Q = declare(fixed)
        I_st = declare_stream()
        Q_st = declare_stream()
        n_st = declare_stream()
        with for_(n, 0, n < n_avg, n + 1):
            with for_(*from_array(if_freq, if_frequencies)):
                update_frequency(qb_el, qb_ge_if)
                play(r180, qb_el)   
                align()
                
                update_frequency(qb_el, if_freq)
                play(sat_pulse * amp(qb_gain), qb_el, duration=qb_len)
                align(measureMacro.active_element(), qb_el)
                measureMacro.measure(targets=[I,Q])
                wait(int(qb_therm_clks))
                save(I, I_st)
                save(Q, Q_st)
            save(n, n_st)
        with stream_processing():
            I_st.buffer(len(if_frequencies)).average().save("I")
            Q_st.buffer(len(if_frequencies)).average().save("Q")
            n_st.save("iteration")
        return qubit_spec
    
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
        r90             : Name of the π/2 pulse used to prepare/close Ramsey
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
    Measure T₁ (energy relaxation) by applying a π-pulse and then waiting variable times.

    Parameters:
        ro_el             : Readout resonator element
        qb_el             : Qubit element
        r180              : Name of the π-pulse that inverts |g>→|e>
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
    Measure T₂* (Ramsey dephasing) by applying two π/2 pulses separated by variable wait times.

    Parameters:
        ro_el             : Readout resonator element
        qb_el             : Qubit element
        r90               : Name of the π/2 pulse
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
    Measure T₂ (Hahn echo) by applying π/2 – wait – π – wait – π/2 sequence,
    with the wait time swept in half-intervals.

    Parameters:
        ro_el                : Readout resonator element
        qb_el                : Qubit element
        r180                 : Name of the π-pulse
        r90                  : Name of the π/2 pulse
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

def qubit_state_tomography(
    state_prep,
    therm_clks,
    n_avg,
    *,
    qb_el="qubit",
    x90="x90",
    yn90="yn90"
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
        +π/2 about X pulse name (used for measuring σ_y).
    yn90 : str, optional
        -π/2 about Y pulse name (used for measuring σ_x).

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

def resonator_spectroscopy_x180(qb_el, if_frequencies, r180, qb_therm_clks, n_avg):
    """
    Pulsed resonator spectroscopy sweeping the readout IF.
    For each IF, measure twice:
      (1) |g⟩ : no qubit pulse
      (2) |e⟩ : apply 'x180' to the qubit, then measure

    Streams:
      - "I" / "Q" are length 2*len(IFs) per average.
        First half -> ground (g), second half -> excited (e).
    """

    with program() as pulsed_ro_program:
        ro_if = declare(int)
        n     = declare(int)
        I     = declare(fixed)
        Q     = declare(fixed)

        I_st  = declare_stream()
        Q_st  = declare_stream()
        n_st  = declare_stream()

        with for_(n, 0, n < n_avg, n + 1):
            with for_(*from_array(ro_if, if_frequencies)):
                # -------- Ground state measurement --------
                update_frequency(measureMacro.active_element(), ro_if)
                play(r180, qb_el)   
                align()
                measureMacro.measure(targets=[I, Q])
                wait(int(qb_therm_clks), measureMacro.active_element())
                save(I, I_st); save(Q, Q_st)
            save(n, n_st)
        with stream_processing():
            I_st.buffer(len(if_frequencies)).average().save("I")
            Q_st.buffer(len(if_frequencies)).average().save("Q")
            n_st.save("iteration")

    return pulsed_ro_program
    
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

def iq_blobs(ro_el, qb_el,  r180, qb_therm_clks, n_runs):
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


def readout_ge_raw_trace(qb_el, r180, qb_therm_clks, ro_depl_clks, n_avg):
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
                                 target_save_rate_khz=2000.0):
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
    measureMacro.set_outputs(weights)
    measureMacro.set_demodulator(demod.sliced, div_clks)
    measureMacro.set_output_ports(["out1", "out2", "out1", "out2"])
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

        if len(weights) != 4:
            raise ValueError("weights mismatch, must be length four for this experiment!")

        # ===== Dynamic safety wait calculation =====
        # Each iteration saves: 8 * num_div variables (4 IQ pairs × 2 states × num_div)
        saves_per_iteration = 8 * num_div
        
        # Time spent in measurements and processing (in ns):
        # - 2 measurements (g and e states)
        # - 2 depletion waits
        # - 2 save loops (negligible compared to waits)
        # Assume each measurement takes ~1 µs (typical readout length)
        measurement_time_ns = 2 * 1000  # 2 measurements × 1 µs
        depletion_time_ns = 2 * ro_depl_clks * 4  # 2 depletion waits × clks × 4ns/clk
        fixed_time_ns = measurement_time_ns + depletion_time_ns
        
        # Target time per iteration based on save rate:
        # target_save_rate_khz saves/ms → saves_per_iteration should take:
        target_time_per_iter_ns = (saves_per_iteration / target_save_rate_khz) * 1e6  # kHz to ns
        
        # Safety wait needed (subtract fixed time):
        safety_wait_ns = max(0, target_time_per_iter_ns - fixed_time_ns)
        safety_wait_clks = int(safety_wait_ns / 4)  # convert to clock cycles
        
        # Ensure minimum wait of 1000 clks (4 µs) for stability
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


def readout_leakage_benchmarking(ro_el, qb_el, r180, control_bits, qb_therm_clks, num_sequences, n_avg):
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
                        play(r180, qb_el)                          # π-pulse
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
    reference_pulse: str,      # π/2 pulse handle
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
    reference_pulse: str,      # π/2 pulse handle
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
    amps,         # list/np.array of α pre-factors (dimensionless)
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
    amps,          # list / np.array of α pre-factors to scan
    iters,         # list / np.array of iteration counts, e.g. np.arange(0, 26, 1)
    x180,          # your calibrated pi pulse handle
    qb_therm_clks: int,
    n_avg: int = 200,
):
    """
    Google-style DRAG calibration:
    - For each alpha in `amps`
    - For each iteration count in `iters`
      - Apply many [x180(+α), x180(-α)] pairs in a row to amplify coherent error
      - Measure I/Q + state
    The correct α is the one that keeps the qubit closest to |g> even after many repetitions.
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
                    # repeat [x180(+α); x180(-α)] 'it' times
                    with for_(pulses, 0, pulses <= it, pulses + 1):
                        # +α pulse
                        play(x180 * amp(1, 0, 0, a), qb_el)
                        # -α pulse (note sign flip on both main amp and DRAG amp)
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

def storage_spectroscopy(qb_el, st_el, disp, sel_r180, if_frequencies, st_therm_clks, n_avg):
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

def num_splitting_spectroscopy(state_prep, qb_el, st_el, sel_r180, if_frequencies, st_therm_clks, n_avg):
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
):
    """
    SIGNAL+NULL (per n and per f):
      state_prep -> M0 -> sel_r180@f -> M1_sel -> null@f -> M1_null -> therm

    Optional CAL (once per outer n iteration, before f sweep):
      prep |g> -> M0 -> sel_r180@qb_if -> M1 -> relax
      prep |e> -> M0 -> sel_r180@qb_if -> M1 -> relax
    CAL streams buffered as (n_avg, 2) (shots x prep).
    """
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
    n_avg
):
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


def fock_resolved_power_rabi(qb_el, st_el, gains, disp_n_list, fock_ifs, sel_qb_pulse, st_therm_clks, n_avg):
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

def fock_resolved_qb_ramsey(qb_el, st_el, fock_ifs, detunings, disps, sel_r90, delay_clks, st_therm_clk, n_avg):
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

def fock_resolved_state_tomography(qb_el, state_prep, qb_if, fock_ifs, sel_r180, rxp90, 
                                   rym90, st_therm_clks, tag_off_idle_clks, n_avg):
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


def storage_wigner_tomography(
        prep_gates: list[Gate],             # Python list of Gate instances to prepare ρ
        st_el, qb_el, ro_el,
        base_disp,
        x_vals, p_vals, base_alpha,
        x90_pulse,              # fast π/2 on the qubit
        parity_wait_clks,       # ≃ π/χ, in clock ticks
        st_therm_clks,          # storage cooldown
        n_avg                   # number of repeats
):
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
                         st_therm_clks, n_avg):

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
    x90_pulse,            # π/2 pulse on the qubit
    delay_ticks,          # list/ndarray of waiting‐time values (in clock ticks)
    st_therm_clks,        # cooldown for storage (in clock ticks)
    n_avg                 # number of averages
):
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
    sel_r180,            # π/2 pulse on the qubit
    delay_ticks,          # list/ndarray of waiting‐time values (in clock ticks)
    st_therm_clks,        # cooldown for storage (in clock ticks)
    n_avg                 # number of averages
):
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

                # prepare one‐photon (or coherent) state in storage
                play(disp_pulse, st_el)
                wait(tau)
                align(st_el)
                play(disp_pulse*amp(0, 1, 1, 0), st_el)
                align(st_el)
                play(sel_r180, qb_el)
                align()
                I, Q = measureMacro.measure(targets=[I,Q])

                # re‐thermalize storage
                wait(int(st_therm_clks), st_el)

                save(I, I_st)
                save(Q, Q_st)

            # progress counter
            save(rep, n_st)

        # stream processing: buffer over τ, then average over reps
        with stream_processing():
            I_st.buffer(len(delay_ticks)).average().save("I")
            Q_st.buffer(len(delay_ticks)).average().save("Q")
            n_st.save("iteration")

    return prog

def qubit_reset_benchmark(qb_el: str, random_bits, r180: str,
                          qb_therm_clks: int, num_shots: int):
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

                # Optional: prepare |e> for the "1" target by a leading π
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


def active_qubit_reset_benchmark(qb_el: str, post_sel_policy, post_sel_kwargs, r180: str, qb_therm_clks, MAX_PREP_TRIALS, n_shots):
    MAX_PREP_TRIALS = int(MAX_PREP_TRIALS)

    # Threshold used for the *correction* (the post-select policy can be different)
    thr=measureMacro._ro_disc_params["threshold"]
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

def continuous_wave(target_el, pulse, gain, truncate_clks, delay_clks=4):
    with program() as prog:
        delay_flag = declare(bool, value=False)
        if delay_clks > 0:
            assign(delay_flag, True)
        with infinite_loop_():
            play(pulse*amp(gain), target_el, truncate=truncate_clks)
            #with if_(delay_flag):
            #    wait(delay_clks, target_el)
    return prog

def SPA_flux_optimization(sel_IFs, depl_clks, n_avg):
    sel_IFs = np.array(sel_IFs, dtype=int)
    with program() as resonator_spec:
        n = declare(int)
        f = declare(int)
        I = declare(fixed)
        Q = declare(fixed)
        I_st = declare_stream()
        Q_st = declare_stream()
        n_st = declare_stream()
        with for_(n, 0, n < n_avg, n + 1):
            with for_each_(f, sel_IFs):
                update_frequency(measureMacro.active_element(), f)
                measureMacro.measure(targets=[I,Q])
                wait(int(depl_clks), measureMacro.active_element())
                save(I, I_st)
                save(Q, Q_st)
            save(n, n_st)
        with stream_processing():
            n_st.save("iteration")
            I_st.buffer(len(sel_IFs)).average().save("I")
            Q_st.buffer(len(sel_IFs)).average().save("Q")
    return resonator_spec

from typing import List, Union
def sequential_simulation(gates: list[Gate], measurement_gates: List[Measure], st_therm_clks, num_shots):
    measurement_counts = sum(1 for mg in measurement_gates if mg.axis != "none")
    with program() as prog:
        I   = declare(fixed)
        Q   = declare(fixed)
        state = declare(bool)
        rep = declare(int)

        I_st = declare_stream()
        Q_st = declare_stream()
        state_st = declare_stream()
        n_st = declare_stream()

        with for_(rep, 0, rep < num_shots, rep + 1):
            for gate, measurement_gate in zip(gates, measurement_gates):
                gate.play()
                align()
                if measurement_gate.axis != "none":
                    measurement_gate.play(targets=[I, Q], state=state, with_state=True)
                    save(state, state_st)
                    save(I, I_st)
                    save(Q, Q_st)
                else:
                    measureMacro.measure(targets=[I, Q])
                sequenceMacros.conditional_reset_ground(I, thr=measureMacro._ro_disc_params["threshold"], r180="x180", qb_el="qubit")
            wait(int(st_therm_clks))    
            save(rep, n_st)
        with stream_processing():
            I_st.buffer(measurement_counts).save_all("I")
            Q_st.buffer(measurement_counts).save_all("Q")
            state_st.buffer(measurement_counts).save_all("states")
            n_st.save("iteration")
    return prog

