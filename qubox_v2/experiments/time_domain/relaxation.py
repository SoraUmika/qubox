"""T1 relaxation experiment."""
from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib.pyplot as plt

from ..experiment_base import ExperimentBase, create_clks_array
from ..result import AnalysisResult, FitResult, ProgramBuildResult
from ...analysis import post_process as pp
from ...analysis.fitting import fit_and_wrap
from ...analysis.cQED_models import T1_relaxation_model
from ...analysis.analysis_tools import project_complex_to_line_real
from ...hardware.program_runner import RunResult
from ...programs.circuit_runner import CircuitRunner, make_t1_circuit
from ...programs import api as cQED_programs


def _resolve_qb_therm_clks(exp: ExperimentBase, value: int | None, owner: str) -> int:
    return int(exp.resolve_override_or_attr(
        value=value,
        attr_name="qb_therm_clks",
        owner=owner,
        cast=int,
    ))


class T1Relaxation(ExperimentBase):
    """Qubit T1 energy relaxation time measurement.

    Applies a pi-pulse then waits a variable delay before readout.
    """

    def _build_impl(
        self,
        delay_end: int,
        dt: int,
        delay_begin: int = 4,
        r180: str = "x180",
        n_avg: int = 1000,
        *,
        use_circuit_runner: bool = True,
    ) -> ProgramBuildResult:
        attr = self.attr
        delay_clks = create_clks_array(delay_begin, delay_end, dt, time_per_clk=4)
        qb_therm_clks = _resolve_qb_therm_clks(self, None, "T1Relaxation")

        ro_fq = self._resolve_readout_frequency()
        qb_fq = self._resolve_qubit_frequency()

        builder_function = "cQED_programs.T1_relaxation"
        if use_circuit_runner:
            try:
                circuit, sweep = make_t1_circuit(
                    qb_el=attr.qb_el,
                    qb_therm_clks=int(qb_therm_clks),
                    n_avg=n_avg,
                    waits_clks=delay_clks,
                    r180=r180,
                )
                compiled = CircuitRunner(self._ctx).compile(circuit, sweep=sweep)
                prog = compiled.program
                builder_function = "CircuitRunner.t1"
            except Exception:
                prog = cQED_programs.T1_relaxation(
                    r180, delay_clks, qb_therm_clks, n_avg,
                    qb_el=attr.qb_el,
                    bindings=self._bindings_or_none,
                )
        else:
            prog = cQED_programs.T1_relaxation(
                r180, delay_clks, qb_therm_clks, n_avg,
                qb_el=attr.qb_el,
                bindings=self._bindings_or_none,
            )

        return ProgramBuildResult(
            program=prog,
            n_total=n_avg,
            processors=(
                pp.proc_default,
                pp.proc_attach("delays", delay_clks * 4),
            ),
            experiment_name="T1Relaxation",
            params={
                "delay_end": delay_end, "dt": dt,
                "delay_begin": delay_begin, "r180": r180,
                "n_avg": n_avg,
            },
            resolved_frequencies={attr.ro_el: ro_fq, attr.qb_el: qb_fq},
            bindings_snapshot=self._serialize_bindings(),
            builder_function=builder_function,
            sweep_axes={"delays": delay_clks * 4},
        )

    def run(
        self,
        delay_end: int,
        dt: int,
        delay_begin: int = 4,
        r180: str = "x180",
        n_avg: int = 1000,
        *,
        use_circuit_runner: bool = True,
    ) -> RunResult:
        build = self.build_program(
            delay_end=delay_end, dt=dt, delay_begin=delay_begin,
            r180=r180, n_avg=n_avg,
            use_circuit_runner=use_circuit_runner,
        )
        result = self.run_program(
            build.program, n_total=build.n_total,
            processors=list(build.processors),
        )
        self.save_output(result.output, "T1Relaxation")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, p0=None, **kw) -> AnalysisResult:
        delays = result.output.extract("delays")
        S = result.output.extract("S")
        ydata, proj_center, proj_direction = project_complex_to_line_real(S)

        derive_qb_therm_clks = bool(kw.pop("derive_qb_therm_clks", False))
        clock_period_ns = float(kw.pop("clock_period_ns", 4.0))
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
            t1_ns = float(fit.params["T1"])
            metrics["T1_ns"] = t1_ns
            metrics["T1_s"] = t1_ns * 1e-9
            metrics["T1_us"] = t1_ns / 1e3

        metadata: dict[str, Any] = {
            "calibration_kind": "t1",
            "units": {"T1_ns": "ns", "T1_s": "s", "T1_us": "us"},
        }
        if update_calibration and fit.params:
            t1_ns = float(fit.params["T1"])
            t1_s = t1_ns * 1e-9
            metadata.setdefault("proposed_patch_ops", []).extend([
                {
                    "op": "SetCalibration",
                    "payload": {
                        "path": "cqed_params.transmon.T1",
                        "value": t1_s,
                    },
                },
                {
                    "op": "SetCalibration",
                    "payload": {
                        "path": "cqed_params.transmon.T1_us",
                        "value": t1_ns / 1e3,
                    },
                },
            ])

            if derive_qb_therm_clks:
                clk_ns = clock_period_ns
                qb_therm_clks = int(np.floor((6.0 * t1_ns) / clk_ns))
                metrics["qb_therm_clks"] = qb_therm_clks
                metadata.setdefault("proposed_patch_ops", []).append(
                    {
                        "op": "SetCalibration",
                        "payload": {
                            "path": "cqed_params.transmon.qb_therm_clks",
                            "value": qb_therm_clks,
                        },
                    }
                )

        metadata["signal_projection"] = {
            "center_real": float(np.real(proj_center)),
            "center_imag": float(np.imag(proj_center)),
            "direction_real": float(np.real(proj_direction)),
            "direction_imag": float(np.imag(proj_direction)),
        }

        analysis = AnalysisResult.from_run(result, fit=fit, metrics=metrics, metadata=metadata)

        return analysis

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        delays = analysis.data.get("delays")
        S = analysis.data.get("S")
        if delays is None or S is None:
            return None

        ydata, _, _ = project_complex_to_line_real(S)
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
        ax.set_ylabel("Projected Signal (a.u.)")
        ax.set_title("T1 Relaxation")
        ax.legend(
            bbox_to_anchor=(1.05, 1), loc='upper left',
            fontsize=10, borderaxespad=0.0,
        )
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig
