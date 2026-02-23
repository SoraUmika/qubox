"""T2 coherence experiments (Ramsey & Echo) and residual photon Ramsey."""
from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib.pyplot as plt

from ..experiment_base import ExperimentBase, create_clks_array
from ..config_builder import ConfigSettings
from ..result import AnalysisResult, FitResult
from ...analysis import post_process as pp
from ...analysis.fitting import fit_and_wrap, build_fit_legend
from ...analysis.cQED_models import T2_ramsey_model, T2_echo_model
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
        *,
        qb_detune_MHz: float | None = None,
    ) -> RunResult:
        attr = self.attr

        if qb_detune_MHz is not None:
            qb_detune = int(float(qb_detune_MHz) * 1e6)

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

    def analyze(self, result: RunResult, *, update_calibration: bool = False, p0=None, **kw) -> AnalysisResult:
        delays = result.output.extract("delays")
        S = result.output.extract("S")
        ydata = np.real(S)
        qb_detune = result.output.extract("qb_detune")

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
                        "path": f"coherence.{self.attr.qb_el}.T2_ramsey",
                        "value": float(fit.params["T2"]),
                    },
                },
                {
                    "op": "SetCalibration",
                    "payload": {
                        "path": f"coherence.{self.attr.qb_el}.T2_star_us",
                        "value": float(fit.params["T2"] / 1e3),
                    },
                },
            ])

            if bool(kw.get("apply_frequency_correction", False)):
                sign = float(kw.get("freq_correction_sign", -1.0))
                correction_hz = sign * float(fit.params["f_det"]) * 1e9
                current_qb = float(self.attr.qb_fq)
                corrected_qb = current_qb + correction_hz
                metrics["qb_freq_correction_Hz"] = correction_hz
                metrics["qb_freq_corrected_Hz"] = corrected_qb
                metadata.setdefault("proposed_patch_ops", []).append(
                    {
                        "op": "SetCalibration",
                        "payload": {
                            "path": f"frequencies.{self.attr.qb_el}.qubit_freq",
                            "value": corrected_qb,
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
        ax.set_ylabel("Re(S)")
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

    def analyze(self, result: RunResult, *, update_calibration: bool = False, p0=None, **kw) -> AnalysisResult:
        delays = result.output.extract("delays")
        S = result.output.extract("S")
        ydata = np.real(S)

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
                        "path": f"coherence.{self.attr.qb_el}.T2_echo",
                        "value": float(fit.params["T2_echo"]),
                    },
                },
                {
                    "op": "SetCalibration",
                    "payload": {
                        "path": f"coherence.{self.attr.qb_el}.T2_echo_us",
                        "value": float(fit.params["T2_echo"] / 1e3),
                    },
                },
            ])

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
        ax.set_ylabel("Re(S)")
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
            attr.qb_el, test_ro_op, delay_clks,
            int(t_relax / 4), int(t_buffer / 4),
            prep_e, test_ro_amp,
            r90, r180, attr.qb_therm_clks, n_avg,
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

    def analyze(self, result: RunResult, *, update_calibration: bool = False, p0=None, **kw) -> AnalysisResult:
        delays = result.output.extract("delays")
        S = result.output.extract("S")
        mag = np.abs(S)

        A_guess = float((mag.max() - mag.min()) / 2)
        T2_guess = float(delays[-1]) / 3
        offset_guess = float(mag.mean())
        auto_p0 = [A_guess, T2_guess, 1.0, 0.0, 0.0, offset_guess]

        fit = fit_and_wrap(delays, mag, T2_ramsey_model,
                           p0 if p0 is not None else auto_p0,
                           model_name="residual_photon_ramsey", **kw)

        metrics: dict[str, Any] = {}
        if fit.params:
            metrics["T2"] = fit.params["T2"]

        return AnalysisResult.from_run(result, fit=fit, metrics=metrics)

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
            y_fit = T2_ramsey_model(x_fit, p["A"], p["T2"], p["n"], p["f_det"], p["phi"], p["offset"])
            ax.plot(x_fit / 1e3, y_fit, "r-", lw=2,
                    label=build_fit_legend(analysis.fit))

        ax.set_xlabel("Delay (us)")
        ax.set_ylabel("Magnitude")
        ax.set_title("Residual Photon Ramsey")
        ax.legend(
            bbox_to_anchor=(1.05, 1), loc='upper left',
            fontsize=10, borderaxespad=0.0,
        )
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig
