"""2-D chevron experiments (Rabi & Ramsey vs detuning)."""
from __future__ import annotations

import numpy as np

from ..experiment_base import ExperimentBase, create_clks_array
from ...analysis import post_process as pp
from ...hardware.program_runner import RunResult
from ...programs import cQED_programs


class TimeRabiChevron(ExperimentBase):
    """2-D sweep: Rabi oscillations vs detuning and pulse duration."""

    def run(
        self,
        if_span: float,
        df: float,
        max_pulse_duration: int,
        dt: int,
        pulse: str = "x180",
        pulse_gain: float = 1.0,
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        # Legacy parity: half-span each side, matching legacy np.arange(-if_span/2, if_span/2+0.1, df)
        dfs = np.arange(-if_span / 2, if_span / 2 + 0.1, df, dtype=int)
        pulse_clks = create_clks_array(4, max_pulse_duration, dt, time_per_clk=4)

        self.set_standard_frequencies()
        qb_if = int(self.hw.get_element_if(attr.qb_el))

        prog = cQED_programs.time_rabi_chevron(
            attr.ro_el, attr.qb_el, pulse, pulse_gain,
            qb_if, dfs, pulse_clks, attr.qb_therm_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("pulse_durations", pulse_clks * 4),
                pp.proc_attach("detunings", dfs),
            ],
        )
        self.save_output(result.output, "timeRabiChevron")
        return result


class PowerRabiChevron(ExperimentBase):
    """2-D sweep: Rabi oscillations vs detuning and amplitude."""

    def run(
        self,
        if_span: float,
        df: float,
        max_gain: float,
        dg: float,
        pulse: str = "x180",
        pulse_duration: int = 100,
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        # Legacy parity: half-span each side
        dfs = np.arange(-if_span / 2, if_span / 2 + 0.1, df, dtype=int)
        gains = np.arange(-max_gain, max_gain + 1e-12, dg, dtype=float)

        self.set_standard_frequencies()
        qb_if = int(self.hw.get_element_if(attr.qb_el))

        prog = cQED_programs.power_rabi_chevron(
            attr.ro_el, attr.qb_el, pulse, int(pulse_duration / 4),
            qb_if, dfs, gains, attr.qb_therm_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("gains", gains),
                pp.proc_attach("detunings", dfs),
            ],
        )
        self.save_output(result.output, "powerRabiChevron")
        return result


class RamseyChevron(ExperimentBase):
    """2-D sweep: Ramsey fringes vs detuning and delay."""

    def run(
        self,
        if_span: float,
        df: float,
        max_delay_duration: int,
        dt: int,
        r90: str = "x90",
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        # Legacy parity: half-span each side
        dfs = np.arange(-if_span / 2, if_span / 2 + 0.1, df, dtype=int)
        delay_clks = create_clks_array(4, max_delay_duration, dt, time_per_clk=4)

        self.set_standard_frequencies()
        qb_if = int(self.hw.get_element_if(attr.qb_el))

        prog = cQED_programs.ramsey_chevron(
            attr.ro_el, attr.qb_el, r90,
            qb_if, dfs, delay_clks, attr.qb_therm_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("delays", delay_clks * 4),
                pp.proc_attach("detunings", dfs),
            ],
        )
        self.save_output(result.output, "ramseyChevron")
        return result
