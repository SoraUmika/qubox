"""Qubit state tomography."""
from __future__ import annotations

from typing import Any, Callable

import numpy as np
import matplotlib.pyplot as plt

from ..experiment_base import ExperimentBase
from ..result import AnalysisResult, ProgramBuildResult
from ...analysis import post_process as pp
from ...analysis.cQED_plottings import plot_bloch_states
from ...hardware.program_runner import RunResult
from ...programs import api as cQED_programs
from ...programs.macros.measure import measureMacro
from ...programs.measurement import try_build_readout_snapshot_from_macro


class QubitStateTomography(ExperimentBase):
    """Qubit 3-axis state tomography (sigma_x, sigma_y, sigma_z).

    Supports single or multiple state-preparation callables.
    When multiple preps are provided, the program runs full x/y/z
    tomography for each prep, producing arrays with an extra leading
    dimension.
    """

    def _build_impl(
        self,
        state_prep: Callable | list[Callable],
        n_avg: int,
        *,
        x90_pulse: str = "x90",
        yn90_pulse: str = "yn90",
        therm_clks: int | None = None,
    ) -> ProgramBuildResult:
        attr = self.attr
        mm = measureMacro

        if callable(state_prep):
            preps = [state_prep]
        else:
            preps = list(state_prep)
        n_preps = len(preps)

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

        run_kwargs = {
            "targets": [("state_x", "sx"), ("state_y", "sy"), ("state_z", "sz")],
            "confusion": self.get_confusion_matrix(),
            "to_sigmaz": True,
            "n_preps": n_preps,
        }
        return ProgramBuildResult(
            program=prog,
            n_total=n_avg,
            processors=(pp.ro_state_correct_proc,),
            experiment_name="QubitStateTomography",
            params={
                "state_prep_count": n_preps,
                "n_avg": n_avg,
                "x90_pulse": x90_pulse,
                "yn90_pulse": yn90_pulse,
                "therm_clks": therm_clks,
            },
            resolved_frequencies={
                attr.ro_el: self._resolve_readout_frequency(),
                attr.qb_el: self._resolve_qubit_frequency(),
            },
            bindings_snapshot=self._serialize_bindings(),
            builder_function="cQED_programs.qubit_state_tomography",
            measure_macro_state=try_build_readout_snapshot_from_macro(),
            run_program_kwargs=run_kwargs,
        )

    def run(
        self,
        state_prep: Callable | list[Callable],
        n_avg: int,
        *,
        x90_pulse: str = "x90",
        yn90_pulse: str = "yn90",
        therm_clks: int | None = None,
    ) -> RunResult:
        build = self.build_program(
            state_prep=state_prep,
            n_avg=n_avg,
            x90_pulse=x90_pulse,
            yn90_pulse=yn90_pulse,
            therm_clks=therm_clks,
        )
        run_kwargs = dict(build.run_program_kwargs or {})
        n_preps = int(run_kwargs.pop("n_preps", 1))
        result = self.run_program(
            build.program,
            n_total=build.n_total,
            processors=list(build.processors),
            **run_kwargs,
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
        # Prefer full arrays from analysis.data; fall back to scalar means
        sx = analysis.data.get("sx") if analysis.data.get("sx") is not None else analysis.metrics.get("sx")
        sy = analysis.data.get("sy") if analysis.data.get("sy") is not None else analysis.metrics.get("sy")
        sz = analysis.data.get("sz") if analysis.data.get("sz") is not None else analysis.metrics.get("sz")
        if sx is None or sy is None or sz is None:
            return None

        # Convert arrays to scalar means for single-point Bloch vector
        sx_val = float(np.mean(sx))
        sy_val = float(np.mean(sy))
        sz_val = float(np.mean(sz))

        states = [np.array([sx_val, sy_val, sz_val])]
        labels = kwargs.get("labels", None)
        fig, _ = plot_bloch_states(states, labels=labels)
        purity = analysis.metrics.get("purity", 0)
        plt.suptitle(f"Qubit State Tomography  |  Purity = {purity:.3f}")
        plt.show()
        return fig
