"""Qubit state tomography."""
from __future__ import annotations

from typing import Any, Callable

from ..experiment_base import ExperimentBase
from ...analysis import post_process as pp
from ...hardware.program_runner import RunResult
from ...programs import cQED_programs
from ...programs.macros.measure import measureMacro


class QubitStateTomography(ExperimentBase):
    """Qubit 3-axis state tomography (sigma_x, sigma_y, sigma_z).

    Supports single or multiple state-preparation callables.
    When multiple preps are provided, the program runs full x/y/z
    tomography for each prep, producing arrays with an extra leading
    dimension.
    """

    def run(
        self,
        state_prep: Callable | list[Callable],
        n_avg: int,
        *,
        x90_pulse: str = "x90",
        yn90_pulse: str = "yn90",
        therm_clks: int | None = None,
    ) -> RunResult:
        attr = self.attr
        mm = measureMacro

        if callable(state_prep):
            preps = [state_prep]
        else:
            preps = list(state_prep)
        n_preps = len(preps)

        self.set_standard_frequencies()

        if therm_clks is None:
            therm_clks = attr.qb_therm_clks

        prog = cQED_programs.qubit_state_tomography(
            state_prep=state_prep,
            therm_clks=therm_clks,
            n_avg=n_avg,
            qb_el=attr.qb_el,
            x90=x90_pulse,
            yn90=yn90_pulse,
        )

        result = self.run_program(
            prog, n_total=n_avg,
            processors=[pp.ro_state_correct_proc],
            targets=[("state_x", "sx"), ("state_y", "sy"), ("state_z", "sz")],
            confusion=mm._ro_quality_params.get("confusion_matrix"),
            to_sigmaz=True,
        )

        if n_preps > 1:
            result.output["n_preps"] = n_preps

        return result
