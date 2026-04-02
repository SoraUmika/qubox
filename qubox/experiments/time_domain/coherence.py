"""T2 coherence experiments (Ramsey & Echo) and residual photon Ramsey."""
from __future__ import annotations

from typing import Any
import warnings

import numpy as np
import matplotlib.pyplot as plt

from ..experiment_base import ExperimentBase, create_clks_array
from ..config_builder import ConfigSettings
from ..result import AnalysisResult, FitResult, ProgramBuildResult
from qubox_tools.algorithms import post_process as pp
from qubox_tools.fitting.routines import fit_and_wrap, build_fit_legend
from qubox_tools.fitting.cqed import T2_ramsey_model, T2_echo_model
from qubox_tools.algorithms.transforms import project_complex_to_line_real
from ...hardware.program_runner import RunResult
from ...programs import api as cQED_programs
from ...programs.macros.measure import measureMacro


def _resolve_qb_therm_clks(exp: ExperimentBase, value: int | None, owner: str) -> int:
    return int(exp.resolve_override_or_attr(
        value=value,
        attr_name="qb_therm_clks",
        owner=owner,
        cast=int,
    ))


class T2Ramsey(ExperimentBase):
    """T2* measurement via Ramsey interferometry.

    Two pi/2 pulses separated by a variable delay, with a controlled
    detuning to create oscillating fringes.
    """

    def _build_impl(
        self,
        qb_detune: int,
        delay_end: int,
        dt: int,
        delay_begin: int = 4,
        r90: str = "x90",
        n_avg: int = 1000,
        qb_therm_clks: int | None = None,
        *,
        qb_detune_MHz: float | None = None,
    ) -> ProgramBuildResult:
        attr = self.attr

        if qb_detune_MHz is not None:
            qb_detune = int(float(qb_detune_MHz) * 1e6)

        if qb_detune > ConfigSettings.MAX_IF_BANDWIDTH:
            raise ValueError("qb_detune exceeds maximum IF bandwidth")

        delay_clks = create_clks_array(delay_begin, delay_end, dt, time_per_clk=4)
        qb_therm_clks = _resolve_qb_therm_clks(self, qb_therm_clks, "T2Ramsey")

        ro_fq = self._resolve_readout_frequency()
        qb_fq = self._resolve_qubit_frequency(detune=qb_detune)

        prog = cQED_programs.T2_ramsey(
            r90, delay_clks, qb_therm_clks, n_avg,
            qb_el=attr.qb_el,
            bindings=self._bindings_or_none,
            readout=self.readout_handle,
        )

        return ProgramBuildResult(
            program=prog,
            n_total=n_avg,
            processors=(
                pp.proc_default,
                pp.proc_attach("delays", delay_clks * 4),
                pp.proc_attach("qb_detune", qb_detune),
            ),
            experiment_name="T2Ramsey",
            params={
                "qb_detune": qb_detune, "delay_end": delay_end, "dt": dt,
                "delay_begin": delay_begin, "r90": r90, "n_avg": n_avg,
                "qb_therm_clks": qb_therm_clks,
            },
            resolved_frequencies={attr.ro_el: ro_fq, attr.qb_el: qb_fq},
            bindings_snapshot=self._serialize_bindings(),
            builder_function="cQED_programs.T2_ramsey",
            sweep_axes={"delays": delay_clks * 4},
        )

    def run(
        self,
        qb_detune: int,
        delay_end: int,
        dt: int,
        delay_begin: int = 4,
        r90: str = "x90",
        n_avg: int = 1000,
        qb_therm_clks: int | None = None,
        *,
        qb_detune_MHz: float | None = None,
    ) -> RunResult:
        build = self.build_program(
            qb_detune=qb_detune, delay_end=delay_end, dt=dt,
            delay_begin=delay_begin, r90=r90, n_avg=n_avg,
            qb_therm_clks=qb_therm_clks,
            qb_detune_MHz=qb_detune_MHz,
        )
        result = self.run_program(
            build.program, n_total=build.n_total,
            processors=list(build.processors),
        )
        self.save_output(result.output, "T2Ramsey")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, p0=None, **kw) -> AnalysisResult:
        delays = result.output.extract("delays")
        S = result.output.extract("S")
        ydata, proj_center, proj_direction = project_complex_to_line_real(S)
        qb_detune = result.output.extract("qb_detune")

        apply_frequency_correction = bool(kw.pop("apply_frequency_correction", False))
        freq_correction_sign = float(kw.pop("freq_correction_sign", -1.0))
        p0_time_unit = str(kw.pop("p0_time_unit", "us")).lower()
        p0_freq_unit = str(kw.pop("p0_freq_unit", "MHz")).lower()

        # qb_detune is in Hz; model expects 1/ns (GHz) when delays are in ns
        f_det_guess = float(qb_detune) / 1e9 if qb_detune is not None else 0.0
        A_guess = float((ydata.max() - ydata.min()) / 2)
        T2_guess = float(delays[-1]) / 3
        offset_guess = float(ydata.mean())
        auto_p0 = [A_guess, T2_guess, 1.0, f_det_guess, 0.0, offset_guess]

        if p0 is not None:
            p0_fit = list(p0)
            if len(p0_fit) >= 2:
                if p0_time_unit == "us":
                    p0_fit[1] = float(p0_fit[1]) * 1e3
                elif p0_time_unit != "ns":
                    raise ValueError("p0_time_unit must be 'us' or 'ns'")
            if len(p0_fit) >= 4:
                if p0_freq_unit == "mhz":
                    p0_fit[3] = float(p0_fit[3]) / 1e3
                elif p0_freq_unit != "1/ns":
                    raise ValueError("p0_freq_unit must be 'MHz' or '1/ns'")
        else:
            p0_fit = auto_p0

        fit = fit_and_wrap(delays, ydata, T2_ramsey_model,
                           p0_fit,
                           model_name="T2_ramsey", **kw)

        metrics: dict[str, Any] = {}
        if fit.params:
            metrics["T2_star"] = fit.params["T2"]
            metrics["f_det"] = fit.params["f_det"]
            metrics["T2_star_us"] = fit.params["T2"] / 1e3
            metrics["f_det_MHz"] = fit.params["f_det"] * 1e3

        metadata: dict[str, Any] = {
            "calibration_kind": "t2_ramsey",
            "units": {"T2_star": "ns", "T2_star_us": "us", "f_det": "1/ns", "f_det_MHz": "MHz"},
        }
        if update_calibration and fit.params:
            metadata.setdefault("proposed_patch_ops", []).extend([
                {
                    "op": "SetCalibration",
                    "payload": {
                        "path": "cqed_params.transmon.T2_ramsey",
                        "value": float(fit.params["T2"]),
                    },
                },
                {
                    "op": "SetCalibration",
                    "payload": {
                        "path": "cqed_params.transmon.T2_star_us",
                        "value": float(fit.params["T2"] / 1e3),
                    },
                },
            ])

            if apply_frequency_correction:
                sign = freq_correction_sign
                correction_hz = sign * float(fit.params["f_det"]) * 1e9
                # Include the input detuning: the qubit was driven at qb_fq + qb_detune
                qb_detune_hz = float(qb_detune or 0)
                current_qb = self.get_qubit_frequency() + qb_detune_hz
                corrected_qb = current_qb + correction_hz
                metrics["qb_detune_Hz"] = qb_detune_hz
                metrics["qb_freq_correction_Hz"] = correction_hz
                metrics["qb_freq_corrected_Hz"] = corrected_qb
                metadata.setdefault("proposed_patch_ops", []).append(
                    {
                        "op": "SetCalibration",
                        "payload": {
                            "path": "cqed_params.transmon.qubit_freq",
                            "value": corrected_qb,
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
        analysis.data["projected_S"] = ydata

        return analysis

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        delays = analysis.data.get("delays")
        ydata = analysis.data.get("projected_S")
        if delays is None or ydata is None:
            return None
        ydata = np.asarray(ydata, dtype=float)
        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 5))
        else:
            fig = ax.figure

        ax.scatter(delays / 1e3, ydata, s=5, label="Data")
        if analysis.fit and analysis.fit.params:
            p = analysis.fit.params
            x_fit = np.linspace(delays.min(), delays.max(), 500)
            y_fit = T2_ramsey_model(x_fit, p["A"], p["T2"], p["n"], p["f_det"], p["phi"], p["offset"])
            eq_str = analysis.fit.metadata.get("equation", "") if analysis.fit.metadata else ""
            legend = (
                f"{eq_str}\nA = {p['A']:.4g}\nT2* = {p['T2'] / 1e3:.4g} us\n"
                f"n = {p['n']:.4g}\nf_det = {p['f_det'] * 1e3:.4g} MHz\n"
                f"phi = {p['phi']:.4g}\noffset = {p['offset']:.4g}"
                if eq_str else
                f"A = {p['A']:.4g}\nT2* = {p['T2'] / 1e3:.4g} us\n"
                f"n = {p['n']:.4g}\nf_det = {p['f_det'] * 1e3:.4g} MHz\n"
                f"phi = {p['phi']:.4g}\noffset = {p['offset']:.4g}"
            )
            ax.plot(x_fit / 1e3, y_fit, "r-", lw=2,
                    label=legend)

        ax.set_xlabel("Delay (us)")
        ax.set_ylabel("Projected Signal (a.u.)")
        ax.set_title("T2 Ramsey")
        ax.legend(
            bbox_to_anchor=(1.05, 1), loc='upper left',
            fontsize=10, borderaxespad=0.0,
        )
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig


class T2Echo(ExperimentBase):
    """T2 measurement via Hahn spin-echo.

    pi/2 - tau - pi - tau - pi/2 - measure.
    """

    def _build_impl(
        self,
        delay_end: int,
        dt: int,
        delay_begin: int = 8,
        r180: str = "x180",
        r90: str = "x90",
        n_avg: int = 1000,
        qb_therm_clks: int | None = None,
    ) -> ProgramBuildResult:
        attr = self.attr
        half_wait_clks = create_clks_array(delay_begin, delay_end, dt, time_per_clk=8)
        qb_therm_clks = _resolve_qb_therm_clks(self, qb_therm_clks, "T2Echo")

        ro_fq = self._resolve_readout_frequency()
        qb_fq = self._resolve_qubit_frequency()

        prog = cQED_programs.T2_echo(
            r180, r90, half_wait_clks, qb_therm_clks, n_avg,
            qb_el=attr.qb_el,
            bindings=self._bindings_or_none,
            readout=self.readout_handle,
        )

        return ProgramBuildResult(
            program=prog,
            n_total=n_avg,
            processors=(
                pp.proc_default,
                pp.proc_attach("delays", half_wait_clks * 8),
            ),
            experiment_name="T2Echo",
            params={
                "delay_end": delay_end, "dt": dt,
                "delay_begin": delay_begin, "r180": r180,
                "r90": r90, "n_avg": n_avg,
                "qb_therm_clks": qb_therm_clks,
            },
            resolved_frequencies={attr.ro_el: ro_fq, attr.qb_el: qb_fq},
            bindings_snapshot=self._serialize_bindings(),
            builder_function="cQED_programs.T2_echo",
            sweep_axes={"delays": half_wait_clks * 8},
            run_program_kwargs={"axis": 0},
        )

    def run(
        self,
        delay_end: int,
        dt: int,
        delay_begin: int = 8,
        r180: str = "x180",
        r90: str = "x90",
        n_avg: int = 1000,
        qb_therm_clks: int | None = None,
    ) -> RunResult:
        build = self.build_program(
            delay_end=delay_end, dt=dt, delay_begin=delay_begin,
            r180=r180, r90=r90, n_avg=n_avg,
            qb_therm_clks=qb_therm_clks,
        )
        result = self.run_program(
            build.program, n_total=build.n_total,
            processors=list(build.processors),
            **build.run_program_kwargs,
        )
        self.save_output(result.output, "T2Echo")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, p0=None, **kw) -> AnalysisResult:
        delays = result.output.extract("delays")
        S = result.output.extract("S")
        ydata, proj_center, proj_direction = project_complex_to_line_real(S)

        p0_time_unit = str(kw.pop("p0_time_unit", "us")).lower()

        A_guess = float((ydata.max() - ydata.min()) / 2)
        T2_echo_guess = float(delays[-1]) / 3
        offset_guess = float(ydata.mean())
        auto_p0 = [A_guess, T2_echo_guess, 1.0, offset_guess]

        if p0 is not None:
            p0_fit = list(p0)
            if len(p0_fit) >= 2:
                if p0_time_unit == "us":
                    p0_fit[1] = float(p0_fit[1]) * 1e3
                elif p0_time_unit != "ns":
                    raise ValueError("p0_time_unit must be 'us' or 'ns'")
        else:
            p0_fit = auto_p0

        fit = fit_and_wrap(delays, ydata, T2_echo_model,
                           p0_fit,
                           model_name="T2_echo", **kw)

        metrics: dict[str, Any] = {}
        if fit.params:
            metrics["T2_echo"] = fit.params["T2_echo"]
            metrics["T2_echo_us"] = fit.params["T2_echo"] / 1e3

        metadata: dict[str, Any] = {
            "calibration_kind": "t2_echo",
            "units": {"T2_echo": "ns", "T2_echo_us": "us"},
        }
        if update_calibration and fit.params:
            metadata.setdefault("proposed_patch_ops", []).extend([
                {
                    "op": "SetCalibration",
                    "payload": {
                        "path": "cqed_params.transmon.T2_echo",
                        "value": float(fit.params["T2_echo"]),
                    },
                },
                {
                    "op": "SetCalibration",
                    "payload": {
                        "path": "cqed_params.transmon.T2_echo_us",
                        "value": float(fit.params["T2_echo"] / 1e3),
                    },
                },
            ])

        metadata["signal_projection"] = {
            "center_real": float(np.real(proj_center)),
            "center_imag": float(np.imag(proj_center)),
            "direction_real": float(np.real(proj_direction)),
            "direction_imag": float(np.imag(proj_direction)),
        }

        analysis = AnalysisResult.from_run(result, fit=fit, metrics=metrics, metadata=metadata)
        analysis.data["projected_S"] = ydata

        return analysis

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        delays = analysis.data.get("delays")
        ydata = analysis.data.get("projected_S")
        if delays is None or ydata is None:
            return None
        ydata = np.asarray(ydata, dtype=float)
        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 5))
        else:
            fig = ax.figure

        ax.scatter(delays / 1e3, ydata, s=5, label="Data")
        if analysis.fit and analysis.fit.params:
            p = analysis.fit.params
            x_fit = np.linspace(delays.min(), delays.max(), 500)
            y_fit = T2_echo_model(x_fit, p["A"], p["T2_echo"], p["n"], p["offset"])
            eq_str = analysis.fit.metadata.get("equation", "") if analysis.fit.metadata else ""
            legend = (
                f"{eq_str}\nA = {p['A']:.4g}\nT2_echo = {p['T2_echo'] / 1e3:.4g} us\n"
                f"n = {p['n']:.4g}\noffset = {p['offset']:.4g}"
                if eq_str else
                f"A = {p['A']:.4g}\nT2_echo = {p['T2_echo'] / 1e3:.4g} us\n"
                f"n = {p['n']:.4g}\noffset = {p['offset']:.4g}"
            )
            ax.plot(x_fit / 1e3, y_fit, "r-", lw=2,
                    label=legend)

        ax.set_xlabel("Delay (us)")
        ax.set_ylabel("Projected Signal (a.u.)")
        ax.set_title("T2 Echo")
        ax.legend(
            bbox_to_anchor=(1.05, 1), loc='upper left',
            fontsize=10, borderaxespad=0.0,
        )
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig


class ResidualPhotonRamsey(ExperimentBase):
    """Cavity residual-photon characterization via Ramsey.

    Measures effective dephasing from residual cavity photons by
    performing a Ramsey measurement with a test readout pulse
    interspersed.
    """

    def _build_impl(
        self,
        t_R_begin: int,
        t_R_end: int,
        dt: int,
        test_ro_op: str,
        qb_detuning: int = 0,
        t_relax_ns: int = 40,
        t_buffer_ns: int = 400,
        r90: str = "x90",
        r180: str = "x180",
        prep_e: bool = False,
        test_ro_amp: float = 1.0,
        measure_ro_op: str = "readout_long",
        n_avg: int = 1000,
        qb_therm_clks: int | None = None,
        **kw,
    ) -> ProgramBuildResult:
        attr = self.attr
        if "t_relax" in kw:
            t_relax_ns = int(kw.pop("t_relax"))
        if "t_buffer" in kw:
            t_buffer_ns = int(kw.pop("t_buffer"))
        if kw:
            unknown = ", ".join(sorted(kw.keys()))
            raise TypeError(f"Unexpected keyword argument(s): {unknown}")

        if (t_relax_ns % 4) != 0:
            warnings.warn(
                f"t_relax_ns={t_relax_ns} is not on 4 ns clock grid; rounding to nearest clock.",
                RuntimeWarning,
                stacklevel=2,
            )
        if (t_buffer_ns % 4) != 0:
            warnings.warn(
                f"t_buffer_ns={t_buffer_ns} is not on 4 ns clock grid; rounding to nearest clock.",
                RuntimeWarning,
                stacklevel=2,
            )

        t_relax_clks = int(round(t_relax_ns / 4.0))
        t_buffer_clks = int(round(t_buffer_ns / 4.0))
        delay_clks = create_clks_array(t_R_begin, t_R_end, dt, time_per_clk=4)
        qb_therm = self.resolve_override_or_attr(
            value=qb_therm_clks,
            attr_name="qb_therm_clks",
            owner="ResidualPhotonRamsey",
            cast=int,
        )

        ro_fq = self._resolve_readout_frequency()
        qb_fq = self._resolve_qubit_frequency(detune=qb_detuning)

        prog = cQED_programs.residual_photon_ramsey(
            test_ro_op, delay_clks,
            t_relax_clks, t_buffer_clks,
            prep_e, test_ro_amp,
            r90, r180, qb_therm, n_avg,
            qb_el=attr.qb_el,
            bindings=self._bindings_or_none,
            readout=self.readout_handle,
        )

        return ProgramBuildResult(
            program=prog,
            n_total=n_avg,
            processors=(
                pp.proc_default,
                pp.proc_attach("delays", delay_clks * 4),
            ),
            experiment_name="ResidualPhotonRamsey",
            params={
                "t_R_begin": t_R_begin, "t_R_end": t_R_end, "dt": dt,
                "test_ro_op": test_ro_op, "qb_detuning": qb_detuning,
                "t_relax_ns": t_relax_ns, "t_buffer_ns": t_buffer_ns,
                "r90": r90, "r180": r180, "prep_e": prep_e,
                "test_ro_amp": test_ro_amp, "n_avg": n_avg,
                "qb_therm_clks": qb_therm,
            },
            resolved_frequencies={attr.ro_el: ro_fq, attr.qb_el: qb_fq},
            bindings_snapshot=self._serialize_bindings(),
            builder_function="cQED_programs.residual_photon_ramsey",
            sweep_axes={"delays": delay_clks * 4},
        )

    def run(
        self,
        t_R_begin: int,
        t_R_end: int,
        dt: int,
        test_ro_op: str,
        qb_detuning: int = 0,
        t_relax_ns: int = 40,
        t_buffer_ns: int = 400,
        r90: str = "x90",
        r180: str = "x180",
        prep_e: bool = False,
        test_ro_amp: float = 1.0,
        measure_ro_op: str = "readout_long",
        n_avg: int = 1000,
        qb_therm_clks: int | None = None,
        **kw,
    ) -> RunResult:
        build = self.build_program(
            t_R_begin=t_R_begin, t_R_end=t_R_end, dt=dt,
            test_ro_op=test_ro_op, qb_detuning=qb_detuning,
            t_relax_ns=t_relax_ns, t_buffer_ns=t_buffer_ns,
            r90=r90, r180=r180, prep_e=prep_e,
            test_ro_amp=test_ro_amp, measure_ro_op=measure_ro_op,
            n_avg=n_avg, qb_therm_clks=qb_therm_clks, **kw,
        )
        result = self.run_program(
            build.program, n_total=build.n_total,
            processors=list(build.processors),
        )
        self.save_output(result.output, "residualPhotonRamsey")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, p0=None, **kw) -> AnalysisResult:
        delays = result.output.extract("delays")
        S = result.output.extract("S")
        ydata, proj_center, proj_direction = project_complex_to_line_real(S)

        A_guess = float((ydata.max() - ydata.min()) / 2)
        T2_guess = float(delays[-1]) / 3
        offset_guess = float(ydata.mean())
        auto_p0 = [A_guess, T2_guess, 1.0, 0.0, 0.0, offset_guess]

        fit = fit_and_wrap(delays, ydata, T2_ramsey_model,
                           p0 if p0 is not None else auto_p0,
                           model_name="residual_photon_ramsey", **kw)

        metrics: dict[str, Any] = {}
        if fit.params:
            metrics["T2"] = fit.params["T2"]

        analysis = AnalysisResult.from_run(
            result,
            fit=fit,
            metrics=metrics,
            metadata={
                "signal_projection": {
                    "center_real": float(np.real(proj_center)),
                    "center_imag": float(np.imag(proj_center)),
                    "direction_real": float(np.real(proj_direction)),
                    "direction_imag": float(np.imag(proj_direction)),
                }
            },
        )
        analysis.data["projected_S"] = ydata
        return analysis

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        delays = analysis.data.get("delays")
        ydata = analysis.data.get("projected_S")
        if delays is None or ydata is None:
            return None
        ydata = np.asarray(ydata, dtype=float)
        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 5))
        else:
            fig = ax.figure

        ax.scatter(delays / 1e3, ydata, s=5, label="Data")
        if analysis.fit and analysis.fit.params:
            p = analysis.fit.params
            x_fit = np.linspace(delays.min(), delays.max(), 500)
            y_fit = T2_ramsey_model(x_fit, p["A"], p["T2"], p["n"], p["f_det"], p["phi"], p["offset"])
            ax.plot(x_fit / 1e3, y_fit, "r-", lw=2,
                    label=build_fit_legend(analysis.fit))

        ax.set_xlabel("Delay (us)")
        ax.set_ylabel("Projected Signal (a.u.)")
        ax.set_title("Residual Photon Ramsey")
        ax.legend(
            bbox_to_anchor=(1.05, 1), loc='upper left',
            fontsize=10, borderaxespad=0.0,
        )
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig
