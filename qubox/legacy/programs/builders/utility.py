
from qm.qua import *
from qualang_tools.loops import from_array
from ..macros.measure import measureMacro
import numpy as np

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
