"""Fock-resolved state tomography."""
from __future__ import annotations

from typing import Any, Callable

import numpy as np

from ..experiment_base import ExperimentBase
from ...analysis import post_process as pp
from ...hardware.program_runner import RunResult
from ...programs import cQED_programs


class FockResolvedStateTomography(ExperimentBase):
    """State tomography in individual Fock manifolds.

    Supports single or multiple state-preparation callables.
    Measures sigma_x, sigma_y, sigma_z conditioned on Fock number.
    """

    def run(
        self,
        fock_fqs: list[float] | np.ndarray,
        state_prep: Callable | list[Callable],
        *,
        tag_off_idle_duration: int | None = None,
        sel_r180: str = "sel_x180",
        rxp90: str = "x90",
        rym90: str = "yn90",
        qb_if: float | None = None,
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        self.set_standard_frequencies()

        prog = cQED_programs.fock_resolved_state_tomography(
            attr.qb_el, attr.st_el,
            np.asarray(fock_fqs),
            state_prep,
            tag_off_idle_duration=tag_off_idle_duration,
            sel_r180=sel_r180,
            rxp90=rxp90, rym90=rym90,
            qb_if=qb_if,
            therm_clks=attr.qb_therm_clks,
            n_avg=n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[pp.proc_default],
        )
        self.save_output(result.output, "fockResolvedTomography")
        return result
