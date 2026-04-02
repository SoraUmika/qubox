
from qm.qua import *
from qualang_tools.loops import from_array
from ..macros.measure import emit_measurement
from ..macros.sequence import sequenceMacros
from ...gates.gate import Gate
from typing import List, Protocol, Any
import numpy as np

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ...core.bindings import ReadoutHandle

class MeasurementGate(Protocol):
    axis: str

    def play(self, targets: list[Any], state: Any = None, with_state: bool = False) -> None:
        ...


def sequential_simulation(gates: list[Gate], measurement_gates: List[MeasurementGate], st_therm_clks, num_shots, *, readout: "ReadoutHandle"):
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
                    emit_measurement(readout, targets=[I, Q])
                sequenceMacros.conditional_reset_ground(I, thr=(readout.threshold or 0.0), r180="x180", qb_el="qubit")
            wait(int(st_therm_clks))
            save(rep, n_st)
        with stream_processing():
            I_st.buffer(measurement_counts).save_all("I")
            Q_st.buffer(measurement_counts).save_all("Q")
            state_st.buffer(measurement_counts).save_all("states")
            n_st.save("iteration")
    return prog
