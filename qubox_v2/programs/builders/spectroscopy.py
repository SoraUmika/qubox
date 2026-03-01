
from qm.qua import *
from qualang_tools.loops import from_array
from ..macros.measure import measureMacro
from ..macros.sequence import sequenceMacros
import numpy as np

def readout_trace(ro_therm_clks, n_avg, *, bindings: "ExperimentBindings | None" = None):
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

def resonator_spectroscopy(
    if_frequencies,
    depletion_clks=None,
    n_avg: int = 1,
    *,
    ro_el: str | None = None,
    bindings: "ExperimentBindings | None" = None,
):
    """
    Sweep readout IF frequencies to perform 1D resonator spectroscopy.
    For each IF, perform a measurement (I/Q) and optionally deplete residual photons.

    Parameters:
        ro_el          : QUA element for readout resonator
        ro_pulse       : Name of the readout pulse to use
        ro_gain        : Gain (amplitude) for the readout measurement
        if_frequencies : Python array/list of IFs to step through (integers)
        depletion_clks : Time (in clock cycles) to wait for photon depletion
        n_avg          : Number of averaging iterations (default=1)
    """
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        if ro_el is None:
            ro_el = _names.get("readout", "__ro")
    elif ro_el is None:
        raise ValueError("ro_el is required when bindings are not provided")

    if depletion_clks is None:
        raise TypeError("depletion_clks is required")

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
                wait(int(depletion_clks), ro_el)
                save(I, I_st)
                save(Q, Q_st)
            save(n, n_st)
        with stream_processing():
            n_st.save("iteration")
            I_st.buffer(len(if_frequencies)).average().save("I")
            Q_st.buffer(len(if_frequencies)).average().save("Q")
    return resonator_spec

def resonator_power_spectroscopy(
    if_frequencies,
    gains,
    depletion_clks=None,
    n_avg: int = 1,
    *,
    bindings: "ExperimentBindings | None" = None,
):
    """
    Perform a 2D sweep of readout IF and readout gain to map out resonator response versus power.

    Parameters:
        ro_el          : QUA element label for the readout resonator
        ro_pulse       : Name of the readout pulse to use
        if_frequencies : Python array/list of IFs to step through
        gains          : Python array/list of gain (amplitude) settings to step through
        depletion_clks : Time in clock cycles for photon depletion after measurement
        n_avg          : Number of averaging iterations (default=1)
    """
    if depletion_clks is None:
        raise TypeError("depletion_clks is required")

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
                    wait(int(depletion_clks), measureMacro.active_element())
                    save(I, I_st)
                    save(Q, Q_st)
            save(n, n_st)
        with stream_processing():
            n_st.save("iteration")
            I_st.buffer(len(gains)).buffer(len(if_frequencies)).average().save("I")
            Q_st.buffer(len(gains)).buffer(len(if_frequencies)).average().save("Q")
    return resonator_spec_2D

def qubit_spectroscopy(sat_pulse, if_frequencies, qb_gain, qb_len, qb_therm_clks:int=4, n_avg:int=1, *, qb_el: str | None = None, bindings: "ExperimentBindings | None" = None):
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
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        if qb_el is None:
            qb_el = _names.get("qubit", "__qb")
    elif qb_el is None:
        raise ValueError("qb_el is required when bindings are not provided")

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

def qubit_spectroscopy_ef(sat_pulse, if_frequencies, qb_ge_if, qb_gain, qb_len, r180, qb_therm_clks, n_avg:int=1, *, qb_el: str | None = None, bindings: "ExperimentBindings | None" = None):
    """
    Perform |e>-|f> spectroscopy by first preparing |e> via a pi_val-pulse (r180), then sweeping drive IF.

    Parameters:
        ro_el          : Readout resonator element
        qb_el          : Qubit element
        if_frequencies : Python array/list of IFs for the spectroscopy sweep
        qb_ge_if       : IF at which to apply the pi_val-pulse that drives |g>-|e>
        qb_gain        : Gain for the saturation pulse
        qb_len         : Duration of the saturation pulse
        r180           : Name of the pi_val-pulse used to prepare |e>
        qb_therm_clks  : Thermalization wait time after readout
        n_avg          : Number of averaging iterations (default=1)
    """
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        if qb_el is None:
            qb_el = _names.get("qubit", "__qb")
    elif qb_el is None:
        raise ValueError("qb_el is required when bindings are not provided")

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

def resonator_spectroscopy_x180(if_frequencies, r180, qb_therm_clks, n_avg, *, qb_el: str | None = None, bindings: "ExperimentBindings | None" = None):
    """
    Pulsed resonator spectroscopy sweeping the readout IF.
    For each IF, measure twice:
      (1) |g> : no qubit pulse
      (2) |e> : apply 'x180' to the qubit, then measure

    Streams:
      - "I" / "Q" are length 2*len(IFs) per average.
        First half -> ground (g), second half -> excited (e).
    """
    if bindings is not None:
        from ...core.bindings import ConfigBuilder
        _names = ConfigBuilder.ephemeral_names(bindings)
        if qb_el is None:
            qb_el = _names.get("qubit", "__qb")
    elif qb_el is None:
        raise ValueError("qb_el is required when bindings are not provided")

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
                align()
                measureMacro.measure(targets=[I, Q])
                wait(int(qb_therm_clks), measureMacro.active_element())
                save(I, I_st); save(Q, Q_st)

                # -------- Excited state measurement --------
                update_frequency(measureMacro.active_element(), ro_if)
                play(r180, qb_el)
                align()
                measureMacro.measure(targets=[I, Q])
                wait(int(qb_therm_clks), measureMacro.active_element())
                save(I, I_st); save(Q, Q_st)
            save(n, n_st)
        with stream_processing():
            I_st.buffer(2 * len(if_frequencies)).average().save("I")
            Q_st.buffer(2 * len(if_frequencies)).average().save("Q")
            n_st.save("iteration")

    return pulsed_ro_program
