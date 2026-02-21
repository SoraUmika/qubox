"""Resonator / readout spectroscopy experiments."""
from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib.pyplot as plt

from ..experiment_base import (
    ExperimentBase, create_if_frequencies, create_clks_array,
)
from ..result import AnalysisResult, FitResult
from ...analysis import post_process as pp
from ...analysis.analysis_tools import two_state_discriminator
from ...analysis.fitting import fit_and_wrap, generalized_fit, build_fit_legend
from ...analysis.cQED_models import resonator_spec_model
from ...hardware.program_runner import RunResult
from ...programs import cQED_programs
from ...programs.macros.measure import measureMacro


class ResonatorSpectroscopy(ExperimentBase):
    """Resonator frequency sweep.

    Sweeps the readout IF frequency while measuring IQ to find the
    resonator resonance.
    """

    def run(
        self,
        readout_op: str,
        rf_begin: float = 8605e6,
        rf_end: float = 8620e6,
        df: float = 50e3,
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        lo_freq = self.hw.get_element_lo(attr.ro_el)
        if_freqs = create_if_frequencies(attr.ro_el, rf_begin, rf_end, df, lo_freq)

        ro_info = self.pulse_mgr.get_pulseOp_by_element_op(attr.ro_el, readout_op)
        if ro_info is None:
            raise ValueError(
                f"No PulseOp for element={attr.ro_el!r}, op={readout_op!r}."
            )

        mm = measureMacro
        weight_len = int(ro_info.length) if ro_info.length is not None else None
        with mm.using_defaults(pulse_op=ro_info, active_op=readout_op, weight_len=weight_len):
            prog = cQED_programs.resonator_spectroscopy(
                attr.ro_el, if_freqs, attr.ro_therm_clks, n_avg,
            )
            return self.run_program(
                prog, n_total=n_avg,
                processors=[
                    pp.proc_default, pp.proc_magnitude,
                    pp.proc_attach("frequencies", lo_freq + if_freqs),
                ],
                axis=0,
            )

    def analyze(self, result: RunResult, *, update_calibration: bool = False, p0=None, **kw) -> AnalysisResult:
        freqs = result.output.extract("frequencies")
        mag = result.output.extract("magnitude")

        f0_guess = freqs[np.argmin(mag)]
        kappa_guess = (freqs[-1] - freqs[0]) / 20
        A_guess = float(mag.min() - mag.max())
        offset_guess = float(mag.max())
        auto_p0 = [f0_guess, kappa_guess, A_guess, offset_guess]

        fit = fit_and_wrap(freqs, mag, resonator_spec_model,
                           p0 if p0 is not None else auto_p0,
                           model_name="resonator_lorentzian", **kw)

        metrics = {}
        if fit.params:
            metrics["f0"] = fit.params["f0"]
            metrics["kappa"] = fit.params["kappa"]

        analysis = AnalysisResult.from_run(result, fit=fit, metrics=metrics)

        if update_calibration and self.calibration_store and fit.params:
            self.calibration_store.set_frequencies(
                self.attr.ro_el,
                lo_freq=self.get_readout_lo(),
                if_freq=fit.params["f0"] - self.get_readout_lo(),
            )

        return analysis

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        freqs = analysis.data.get("frequencies")
        mag = analysis.data.get("magnitude")
        if freqs is None or mag is None:
            return None

        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 5))
        else:
            fig = ax.figure

        ax.scatter(freqs / 1e6, mag, s=5, label="Data")
        if analysis.fit and analysis.fit.params:
            p = analysis.fit.params
            x_fit = np.linspace(freqs.min(), freqs.max(), 500)
            y_fit = resonator_spec_model(x_fit, p["f0"], p["kappa"], p["A"], p["offset"])
            ax.plot(x_fit / 1e6, y_fit, "r-", lw=2,
                    label=build_fit_legend(analysis.fit))

        ax.set_xlabel("Frequency (MHz)")
        ax.set_ylabel("Magnitude")
        ax.set_title("Resonator Spectroscopy")
        ax.legend(
            bbox_to_anchor=(1.05, 1), loc='upper left',
            fontsize=10, borderaxespad=0.0,
        )
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig


class ResonatorPowerSpectroscopy(ExperimentBase):
    """Resonator frequency × readout gain 2-D sweep."""

    def run(
        self,
        readout_op: str,
        rf_begin: float,
        rf_end: float,
        df: float,
        g_min: float = 1e-3,
        g_max: float = 0.5,
        N_a: int = 50,
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        lo_freq = self.hw.get_element_lo(attr.ro_el)
        if_freqs = create_if_frequencies(attr.ro_el, rf_begin, rf_end, df, lo_freq)
        gains = np.geomspace(g_min, g_max, N_a)

        ro_info = self.pulse_mgr.get_pulseOp_by_element_op(attr.ro_el, readout_op)
        if ro_info is None:
            raise ValueError(
                f"No PulseOp for element={attr.ro_el!r}, op={readout_op!r}."
            )

        mm = measureMacro
        weight_len = int(ro_info.length) if ro_info.length is not None else None
        with mm.using_defaults(pulse_op=ro_info, active_op=readout_op, weight_len=weight_len):
            prog = cQED_programs.resonator_power_spectroscopy(
                if_freqs, gains, attr.ro_therm_clks, n_avg,
            )
            result = self.run_program(
                prog, n_total=n_avg,
                processors=[
                    pp.proc_default,
                    pp.proc_attach("frequencies", lo_freq + if_freqs),
                    pp.proc_attach("gains", gains),
                ],
            )
        self.save_output(result.output, "cavityPowerSpectroscopy")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        freqs = result.output.extract("frequencies")
        gains = result.output.extract("gains")
        S = result.output.extract("S")
        magnitude = np.abs(S)

        metrics: dict[str, Any] = {}
        try:
            # S shape is (n_freqs, n_gains) from QUA stream ordering
            best_idx = np.unravel_index(np.argmin(magnitude), magnitude.shape)
            metrics["optimal_gain"] = float(gains[best_idx[1]])
            metrics["optimal_freq"] = float(freqs[best_idx[0]])
        except Exception:
            pass

        return AnalysisResult.from_run(result, metrics=metrics)

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        freqs = analysis.data.get("frequencies")
        gains = analysis.data.get("gains")
        S = analysis.data.get("S")
        if freqs is None or gains is None or S is None:
            return None

        magnitude = np.abs(S)
        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 6))
        else:
            fig = ax.figure

        pcm = ax.pcolormesh(freqs / 1e6, gains, magnitude.T, shading="nearest")
        fig.colorbar(pcm, ax=ax, label="Magnitude")

        if "optimal_freq" in analysis.metrics and "optimal_gain" in analysis.metrics:
            ax.axvline(analysis.metrics["optimal_freq"] / 1e6, color="r",
                       ls="--", lw=1, alpha=0.7)
            ax.axhline(analysis.metrics["optimal_gain"], color="r",
                       ls="--", lw=1, alpha=0.7)

        ax.set_xlabel("Frequency (MHz)")
        ax.set_ylabel("Gain")
        ax.set_title("Resonator Power Spectroscopy")
        plt.tight_layout()
        plt.show()
        return fig


class ResonatorSpectroscopyX180(ExperimentBase):
    """Resonator spectroscopy with qubit pi-pulse excitation."""

    def run(
        self,
        rf_begin: float,
        rf_end: float,
        df: float,
        r180: str = "x180",
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        lo_freq = self.hw.get_element_lo(attr.ro_el)
        if_freqs = create_if_frequencies(attr.ro_el, rf_begin, rf_end, df, lo_freq)

        self.set_standard_frequencies()

        prog = cQED_programs.resonator_spectroscopy_x180(
            attr.qb_el, if_freqs, r180,
            attr.ro_therm_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default, pp.proc_magnitude,
                pp.proc_attach("frequencies", lo_freq + if_freqs),
            ],
        )
        self.save_output(result.output, "resonatorX180")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, p0=None, **kw) -> AnalysisResult:
        freqs = result.output.extract("frequencies")
        mag = result.output.extract("magnitude")

        n = len(mag) // 2
        mag_g, mag_e = mag[:n], mag[n:]
        # frequencies array is not doubled — both halves share the same freq axis
        freqs_g = freqs
        freqs_e = freqs

        def _fit_half(f, m, label):
            f0_guess = f[np.argmin(m)]
            kappa_guess = (f[-1] - f[0]) / 20
            A_guess = float(m.min() - m.max())
            offset_guess = float(m.max())
            return fit_and_wrap(f, m, resonator_spec_model,
                                p0 if p0 is not None else [f0_guess, kappa_guess, A_guess, offset_guess],
                                model_name=f"resonator_{label}", **kw)

        fit_g = _fit_half(freqs_g, mag_g, "ground")
        fit_e = _fit_half(freqs_e, mag_e, "excited")

        metrics: dict[str, Any] = {}
        if fit_g.params:
            metrics["f0_g"] = fit_g.params["f0"]
        if fit_e.params:
            metrics["f0_e"] = fit_e.params["f0"]
        if fit_g.params and fit_e.params:
            metrics["chi"] = (fit_e.params["f0"] - fit_g.params["f0"]) / 2

        analysis = AnalysisResult.from_run(
            result, fits={"ground": fit_g, "excited": fit_e}, metrics=metrics,
        )

        if update_calibration and self.calibration_store and "chi" in metrics:
            self.calibration_store.set_frequencies(
                self.attr.ro_el, chi=metrics["chi"],
            )

        return analysis

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        freqs = analysis.data.get("frequencies")
        mag = analysis.data.get("magnitude")
        if freqs is None or mag is None:
            return None

        n = len(mag) // 2
        mag_g, mag_e = mag[:n], mag[n:]
        freqs_g = freqs
        freqs_e = freqs

        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 5))
        else:
            fig = ax.figure

        ax.scatter(freqs_g / 1e6, mag_g, s=5, c="blue", label="|g>")
        ax.scatter(freqs_e / 1e6, mag_e, s=5, c="red", label="|e>")

        fits = analysis.fits or {}
        for key, color in [("ground", "blue"), ("excited", "red")]:
            fit = fits.get(key)
            if fit and fit.params:
                p = fit.params
                f = freqs_g if key == "ground" else freqs_e
                x_fit = np.linspace(f.min(), f.max(), 500)
                y_fit = resonator_spec_model(x_fit, p["f0"], p["kappa"], p["A"], p["offset"])
                ax.plot(x_fit / 1e6, y_fit, color=color, lw=2,
                        label=build_fit_legend(fit))

        if "chi" in analysis.metrics:
            ax.set_title(f"Resonator X180  |  chi/2pi = {analysis.metrics['chi']/1e3:.1f} kHz")
        else:
            ax.set_title("Resonator Spectroscopy X180")

        ax.set_xlabel("Frequency (MHz)")
        ax.set_ylabel("Magnitude")
        ax.legend(
            bbox_to_anchor=(1.05, 1), loc='upper left',
            fontsize=10, borderaxespad=0.0,
        )
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig


class ReadoutTrace(ExperimentBase):
    """Raw ADC readout trace capture."""

    def run(
        self,
        drive_frequency: float,
        ro_therm_clks: int = 10000,
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        self.hw.set_element_fq(attr.ro_el, drive_frequency)

        prog = cQED_programs.readout_trace(
            ro_therm_clks, n_avg,
        )
        return self.run_program(
            prog, n_total=n_avg,
            processors=[pp.bare_proc],
        )

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        adc1 = result.output.get("adc1")
        adc2 = result.output.get("adc2")
        metrics: dict[str, Any] = {}
        if adc1 is not None:
            metrics["trace_length"] = int(np.size(adc1))
        return AnalysisResult.from_run(result, metrics=metrics)

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        adc1 = analysis.data.get("adc1")
        adc2 = analysis.data.get("adc2")
        if adc1 is None and adc2 is None:
            return None

        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 4))
        else:
            fig = ax.figure

        if adc1 is not None:
            t_ns = np.arange(len(adc1))
            ax.plot(t_ns, adc1, label="ADC1 (I)")
        if adc2 is not None:
            t_ns = np.arange(len(adc2))
            ax.plot(t_ns, adc2, label="ADC2 (Q)")
        ax.set_xlabel("Sample")
        ax.set_ylabel("Amplitude (V)")
        ax.set_title("Readout Trace")
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig


class ReadoutFrequencyOptimization(ExperimentBase):
    """Sweep readout frequency to maximize g/e discrimination fidelity."""

    def run(
        self,
        rf_begin: float,
        rf_end: float,
        df: float,
        ro_op: str | None = None,
        r180: str = "x180",
        n_runs: int = 1000,
    ) -> RunResult:
        attr = self.attr
        lo_freq = self.hw.get_element_lo(attr.ro_el)
        if_freqs = create_if_frequencies(attr.ro_el, rf_begin, rf_end, df, lo_freq)

        self.set_standard_frequencies()

        best_fidelity = -1.0
        fidelities = []

        for if_fq in if_freqs:
            self.hw.set_element_fq(attr.ro_el, lo_freq + float(if_fq))
            prog = cQED_programs.iq_blobs(
                attr.ro_el, attr.qb_el, r180, attr.qb_therm_clks, n_runs,
            )
            result = self.run_program(
                prog, n_total=n_runs,
                processors=[pp.proc_default],
                targets=[("Ig", "Qg"), ("Ie", "Qe")],
            )

            try:
                S_g = result.output["S_g"]
                S_e = result.output["S_e"]
                I_g, Q_g = np.real(S_g), np.imag(S_g)
                I_e, Q_e = np.real(S_e), np.imag(S_e)
                _, _, fid, _, _, _ = two_state_discriminator(I_g, Q_g, I_e, Q_e)
                fidelities.append(fid)
            except Exception:
                fidelities.append(0.0)

        from ...analysis.output import Output
        output = Output({
            "frequencies": lo_freq + if_freqs,
            "fidelities": np.array(fidelities),
            "best_freq": lo_freq + if_freqs[int(np.argmax(fidelities))],
        })
        self.save_output(output, "readoutFreqOpt")
        return RunResult(mode=result.mode, output=output, sim_samples=None)

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        freqs = result.output.extract("frequencies")
        fidelities = result.output.extract("fidelities")
        best_freq = result.output.extract("best_freq")

        metrics: dict[str, Any] = {}
        if fidelities is not None:
            metrics["best_fidelity"] = float(np.max(fidelities))
        if best_freq is not None:
            metrics["best_freq"] = float(best_freq)

        analysis = AnalysisResult.from_run(result, metrics=metrics)

        if update_calibration and self.calibration_store and "best_freq" in metrics:
            lo = self.get_readout_lo()
            self.calibration_store.set_frequencies(
                self.attr.ro_el, lo_freq=lo,
                if_freq=metrics["best_freq"] - lo,
            )

        return analysis

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        freqs = analysis.data.get("frequencies")
        fidelities = analysis.data.get("fidelities")
        if freqs is None or fidelities is None:
            return None

        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 5))
        else:
            fig = ax.figure

        ax.scatter(freqs / 1e6, fidelities, s=10)

        if "best_freq" in analysis.metrics:
            ax.axvline(analysis.metrics["best_freq"] / 1e6, color="r",
                       ls="--", lw=1.5, label=f"Best: {analysis.metrics['best_freq']/1e6:.3f} MHz")

        title = "Readout Frequency Optimization"
        if "best_fidelity" in analysis.metrics:
            title += f"  |  F = {analysis.metrics['best_fidelity']:.1f}%"
        ax.set_title(title)
        ax.set_xlabel("Frequency (MHz)")
        ax.set_ylabel("Fidelity (%)")
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig
