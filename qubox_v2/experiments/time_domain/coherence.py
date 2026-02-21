"""T2 coherence experiments (Ramsey & Echo) and residual photon Ramsey."""
from __future__ import annotations

from typing import Any

import numpy as np

from ..experiment_base import ExperimentBase, create_clks_array
from ..config_builder import ConfigSettings
from ...analysis import post_process as pp
from ...hardware.program_runner import RunResult
from ...programs import cQED_programs
from ...programs.macros.measure import measureMacro


class T2Ramsey(ExperimentBase):
    """T2* measurement via Ramsey interferometry.

    Two pi/2 pulses separated by a variable delay, with a controlled
    detuning to create oscillating fringes.
    """

    def run(
        self,
        qb_detune: int,
        delay_end: int,
        dt: int,
        delay_begin: int = 4,
        r90: str = "x90",
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr

        if qb_detune > ConfigSettings.MAX_IF_BANDWIDTH:
            raise ValueError("qb_detune exceeds maximum IF bandwidth")

        delay_clks = create_clks_array(delay_begin, delay_end, dt, time_per_clk=4)

        self.hw.set_element_fq(attr.qb_el, attr.qb_fq + qb_detune)
        self.hw.set_element_fq(attr.ro_el, measureMacro._drive_frequency)

        prog = cQED_programs.T2_ramsey(
            attr.qb_el, r90, delay_clks, attr.qb_therm_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("delays", delay_clks * 4),
                pp.proc_attach("qb_detune", qb_detune),
            ],
        )
        self.save_output(result.output, "T2Ramsey")
        return result


class T2Echo(ExperimentBase):
    """T2 measurement via Hahn spin-echo.

    pi/2 - tau - pi - tau - pi/2 - measure.
    """

    def run(
        self,
        delay_end: int,
        dt: int,
        delay_begin: int = 8,
        r180: str = "x180",
        r90: str = "x90",
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        half_wait_clks = create_clks_array(delay_begin, delay_end, dt, time_per_clk=8)

        self.set_standard_frequencies()

        prog = cQED_programs.T2_echo(
            attr.qb_el, r180, r90, half_wait_clks, attr.qb_therm_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("delays", half_wait_clks * 8),
            ],
            axis=0,
        )
        self.save_output(result.output, "T2Echo")
        return result


class ResidualPhotonRamsey(ExperimentBase):
    """Cavity residual-photon characterization via Ramsey.

    Measures effective dephasing from residual cavity photons by
    performing a Ramsey measurement with a test readout pulse
    interspersed.
    """

    def run(
        self,
        t_R_begin: int,
        t_R_end: int,
        dt: int,
        test_ro_op: str,
        qb_detuning: int = 0,
        t_relax: int = 40,
        t_buffer: int = 400,
        r90: str = "x90",
        r180: str = "x180",
        prep_e: bool = False,
        test_ro_amp: float = 1.0,
        measure_ro_op: str = "readout_long",
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        delay_clks = create_clks_array(t_R_begin, t_R_end, dt, time_per_clk=4)

        self.set_standard_frequencies(qb_fq=attr.qb_fq + qb_detuning)

        prog = cQED_programs.residual_photon_ramsey(
            attr.qb_el, attr.ro_el,
            r90, r180, delay_clks,
            test_ro_op, test_ro_amp,
            int(t_relax / 4), int(t_buffer / 4),
            prep_e, measure_ro_op,
            attr.qb_therm_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("delays", delay_clks * 4),
            ],
        )
        self.save_output(result.output, "residualPhotonRamsey")
        return result
