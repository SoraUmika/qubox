"""Qubit state tomography."""
from __future__ import annotations

from typing import Any, Callable

import numpy as np
import matplotlib.pyplot as plt

from ..experiment_base import ExperimentBase
from ..result import AnalysisResult
from ...analysis import post_process as pp
from ...analysis.cQED_plottings import plot_bloch_states
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

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        sx = result.output.extract("sx")
        sy = result.output.extract("sy")
        sz = result.output.extract("sz")
        metrics: dict[str, Any] = {}

        if sx is not None and sy is not None and sz is not None:
            sx_val = float(np.mean(sx))
            sy_val = float(np.mean(sy))
            sz_val = float(np.mean(sz))
            metrics["sx"] = sx_val
            metrics["sy"] = sy_val
            metrics["sz"] = sz_val
            metrics["purity"] = float(sx_val**2 + sy_val**2 + sz_val**2)

        return AnalysisResult.from_run(result, metrics=metrics)

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        sx = analysis.metrics.get("sx")
        sy = analysis.metrics.get("sy")
        sz = analysis.metrics.get("sz")
        if sx is None or sy is None or sz is None:
            return None

        states = [np.array([sx, sy, sz])]
        labels = kwargs.get("labels", None)
        fig, _ = plot_bloch_states(states, labels=labels)
        purity = analysis.metrics.get("purity", 0)
        plt.suptitle(f"Qubit State Tomography  |  Purity = {purity:.3f}")
        plt.show()
        return fig
