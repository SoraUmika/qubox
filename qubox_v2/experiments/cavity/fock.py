"""Fock-manifold-resolved experiments."""
from __future__ import annotations

from typing import Any, Union

import numpy as np

from ..experiment_base import ExperimentBase, create_clks_array
from ...analysis import post_process as pp
from ...hardware.program_runner import RunResult
from ...programs import cQED_programs


class FockResolvedSpectroscopy(ExperimentBase):
    """Fock-resolved spectroscopy with post-selection.

    Probes qubit spectroscopy conditioned on photon number via
    selective pi-pulses and double post-selection.
    """

    def run(
        self,
        probe_fqs: list[float] | np.ndarray,
        *,
        state_prep: Any,
        sel_r180: str = "sel_x180",
        calibrate_ref_r180_S: bool = True,
        n_avg: int = 100,
    ) -> RunResult:
        attr = self.attr
        self.set_standard_frequencies()

        prog = cQED_programs.fock_resolved_spectroscopy(
            attr.qb_el, attr.st_el,
            np.asarray(probe_fqs),
            state_prep, sel_r180,
            calibrate_ref_r180_S,
            attr.qb_therm_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[pp.proc_default],
        )
        self.save_output(result.output, "fockResolvedSpectroscopy")
        return result


class FockResolvedT1(ExperimentBase):
    """T1 relaxation measurement in individual Fock manifolds."""

    def run(
        self,
        fock_fqs: list[float] | np.ndarray,
        fock_disps: list[str],
        delay_end: int,
        dt: int,
        delay_begin: int = 4,
        sel_r180: str = "sel_x180",
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        delay_clks = create_clks_array(delay_begin, delay_end, dt, time_per_clk=4)

        self.set_standard_frequencies()

        prog = cQED_programs.fock_resolved_T1_relaxation(
            attr.qb_el, attr.st_el,
            np.asarray(fock_fqs), fock_disps,
            delay_clks, sel_r180,
            attr.qb_therm_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("delays", delay_clks * 4),
            ],
        )
        self.save_output(result.output, "fockResolvedT1")
        return result


class FockResolvedRamsey(ExperimentBase):
    """Ramsey measurement in individual Fock manifolds.

    Per-Fock selective pi/2 with independent displacement
    per manifold; detuning sweep.
    """

    def run(
        self,
        fock_fqs: list[float] | np.ndarray,
        detunings: list[float] | np.ndarray,
        disps: list[str],
        delay_end: int,
        dt: int,
        delay_begin: int = 4,
        sel_r90: str = "sel_x90",
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        delay_clks = create_clks_array(delay_begin, delay_end, dt, time_per_clk=4)

        self.set_standard_frequencies()

        prog = cQED_programs.fock_resolved_qb_ramsey(
            attr.qb_el, attr.st_el,
            np.asarray(fock_fqs), np.asarray(detunings),
            disps, delay_clks, sel_r90,
            attr.qb_therm_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("delays", delay_clks * 4),
            ],
        )
        self.save_output(result.output, "fockResolvedRamsey")
        return result


class FockResolvedPowerRabi(ExperimentBase):
    """Power Rabi oscillations in Fock manifolds.

    Sweeps gain across Fock-number-resolved qubit transitions.
    """

    def run(
        self,
        fock_fqs: list[float] | np.ndarray,
        gains: list[float] | np.ndarray,
        sel_qb_pulse: str,
        disp_n_list: list[str],
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        self.set_standard_frequencies()

        prog = cQED_programs.fock_resolved_power_rabi(
            attr.qb_el, attr.st_el,
            np.asarray(fock_fqs), np.asarray(gains),
            sel_qb_pulse, disp_n_list,
            attr.qb_therm_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("gains", np.asarray(gains)),
            ],
        )
        self.save_output(result.output, "fockResolvedPowerRabi")
        return result
