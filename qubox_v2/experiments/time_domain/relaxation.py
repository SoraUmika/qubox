"""T1 relaxation experiment."""
from __future__ import annotations

from ..experiment_base import ExperimentBase, create_clks_array
from ...analysis import post_process as pp
from ...hardware.program_runner import RunResult
from ...programs import cQED_programs


class T1Relaxation(ExperimentBase):
    """Qubit T1 energy relaxation time measurement.

    Applies a pi-pulse then waits a variable delay before readout.
    """

    def run(
        self,
        delay_end: int,
        dt: int,
        delay_begin: int = 4,
        r180: str = "x180",
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        delay_clks = create_clks_array(delay_begin, delay_end, dt, time_per_clk=4)

        self.set_standard_frequencies()

        prog = cQED_programs.T1_relaxation(
            attr.qb_el, r180, delay_clks, attr.qb_therm_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("delays", delay_clks * 4),
            ],
        )
        self.save_output(result.output, "T1Relaxation")
        return result
