"""T1 relaxation experiment."""
from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib.pyplot as plt

from ..experiment_base import ExperimentBase, create_clks_array
from ..result import AnalysisResult, FitResult
from ...analysis import post_process as pp
from ...analysis.fitting import fit_and_wrap, build_fit_legend
from ...analysis.cQED_models import T1_relaxation_model
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

    def analyze(self, result: RunResult, *, update_calibration: bool = False, p0=None, **kw) -> AnalysisResult:
        delays = result.output.extract("delays")
        S = result.output.extract("S")
        mag = np.abs(S)

        A_guess = float(mag[0] - mag[-1])
        T1_guess = float(delays[-1]) / 3
        offset_guess = float(mag[-1])
        auto_p0 = [A_guess, T1_guess, offset_guess]

        fit = fit_and_wrap(delays, mag, T1_relaxation_model,
                           p0 if p0 is not None else auto_p0,
                           model_name="T1_relaxation", **kw)

        metrics: dict[str, Any] = {}
        if fit.params:
            metrics["T1"] = fit.params["T1"]

        analysis = AnalysisResult.from_run(result, fit=fit, metrics=metrics)

        if update_calibration and self.calibration_store and fit.params:
            min_r2 = float(kw.get("min_r2", 0.80))
            self.guarded_calibration_commit(
                analysis=analysis,
                run_result=result,
                calibration_tag="t1_relaxation",
                min_r2=min_r2,
                required_metrics={"T1": (1.0, None)},
                apply_update=lambda: self.calibration_store.set_coherence(
                    self.attr.qb_el, T1=fit.params["T1"],
                ),
            )

        return analysis

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        delays = analysis.data.get("delays")
        S = analysis.data.get("S")
        if delays is None or S is None:
            return None

        mag = np.abs(S)
        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 5))
        else:
            fig = ax.figure

        ax.scatter(delays / 1e3, mag, s=5, label="Data")
        if analysis.fit and analysis.fit.params:
            p = analysis.fit.params
            x_fit = np.linspace(delays.min(), delays.max(), 500)
            y_fit = T1_relaxation_model(x_fit, p["A"], p["T1"], p["offset"])
            ax.plot(x_fit / 1e3, y_fit, "r-", lw=2,
                    label=build_fit_legend(analysis.fit))

        ax.set_xlabel("Delay (us)")
        ax.set_ylabel("Magnitude")
        ax.set_title("T1 Relaxation")
        ax.legend(
            bbox_to_anchor=(1.05, 1), loc='upper left',
            fontsize=10, borderaxespad=0.0,
        )
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig
