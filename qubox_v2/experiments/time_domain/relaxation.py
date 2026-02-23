"""T1 relaxation experiment."""
from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib.pyplot as plt

from ..experiment_base import ExperimentBase, create_clks_array
from ..result import AnalysisResult, FitResult
from ...analysis import post_process as pp
from ...analysis.fitting import fit_and_wrap
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
        ydata = np.real(S)

        p0_time_unit = str(kw.pop("p0_time_unit", "us")).lower()

        A_guess = float(ydata[0] - ydata[-1])
        # Robust T1 guess: find where signal crosses halfway between first and last value
        midpoint = (ydata[0] + ydata[-1]) / 2.0
        half_idx = int(np.argmin(np.abs(ydata - midpoint)))
        if half_idx > 0 and half_idx < len(delays) - 1:
            T1_guess = float(delays[half_idx]) / np.log(2)
        else:
            T1_guess = float(delays[-1]) / 3
        offset_guess = float(ydata[-1])
        auto_p0 = [A_guess, T1_guess, offset_guess]

        if p0 is not None:
            p0_fit = list(p0)
            if len(p0_fit) >= 2:
                if p0_time_unit == "us":
                    p0_fit[1] = float(p0_fit[1]) * 1e3
                elif p0_time_unit != "ns":
                    raise ValueError("p0_time_unit must be 'us' or 'ns'")
        else:
            p0_fit = auto_p0

        fit = fit_and_wrap(delays, ydata, T1_relaxation_model,
                           p0_fit,
                           model_name="T1_relaxation", **kw)

        metrics: dict[str, Any] = {"T1_guess_ns": T1_guess, "fit_converged": bool(fit.params)}
        if fit.params:
            metrics["T1"] = fit.params["T1"]
            metrics["T1_us"] = fit.params["T1"] / 1e3

        metadata: dict[str, Any] = {
            "calibration_kind": "t1",
            "units": {"T1": "ns", "T1_us": "us"},
        }
        if update_calibration and fit.params:
            metadata.setdefault("proposed_patch_ops", []).extend([
                {
                    "op": "SetCalibration",
                    "payload": {
                        "path": f"coherence.{self.attr.qb_el}.T1",
                        "value": float(fit.params["T1"]),
                    },
                },
                {
                    "op": "SetCalibration",
                    "payload": {
                        "path": f"coherence.{self.attr.qb_el}.T1_us",
                        "value": float(fit.params["T1"] / 1e3),
                    },
                },
            ])

            if bool(kw.get("derive_qb_therm_clks", False)):
                clk_ns = float(kw.get("clock_period_ns", 4.0))
                qb_therm_clks = int(np.floor((2.0 * float(fit.params["T1"])) / clk_ns))
                metrics["qb_therm_clks"] = qb_therm_clks
                metadata.setdefault("proposed_patch_ops", []).append(
                    {
                        "op": "SetCalibration",
                        "payload": {
                            "path": f"coherence.{self.attr.qb_el}.qb_therm_clks",
                            "value": qb_therm_clks,
                        },
                    }
                )

        analysis = AnalysisResult.from_run(result, fit=fit, metrics=metrics, metadata=metadata)

        return analysis

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        delays = analysis.data.get("delays")
        S = analysis.data.get("S")
        if delays is None or S is None:
            return None

        ydata = np.real(S)
        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 5))
        else:
            fig = ax.figure

        ax.scatter(delays / 1e3, ydata, s=5, label="Data")
        if analysis.fit and analysis.fit.params:
            p = analysis.fit.params
            x_fit = np.linspace(delays.min(), delays.max(), 500)
            y_fit = T1_relaxation_model(x_fit, p["A"], p["T1"], p["offset"])
            eq_str = analysis.fit.metadata.get("equation", "") if analysis.fit.metadata else ""
            legend = (
                f"{eq_str}\nA = {p['A']:.4g}\nT1 = {p['T1'] / 1e3:.4g} us\noffset = {p['offset']:.4g}"
                if eq_str else
                f"A = {p['A']:.4g}\nT1 = {p['T1'] / 1e3:.4g} us\noffset = {p['offset']:.4g}"
            )
            ax.plot(x_fit / 1e3, y_fit, "r-", lw=2,
                    label=legend)

        ax.set_xlabel("Delay (us)")
        ax.set_ylabel("Re(S)")
        ax.set_title("T1 Relaxation")
        ax.legend(
            bbox_to_anchor=(1.05, 1), loc='upper left',
            fontsize=10, borderaxespad=0.0,
        )
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig
