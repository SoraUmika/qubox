"""Fock-manifold-resolved experiments."""
from __future__ import annotations

from typing import Any, Union

import numpy as np
import matplotlib.pyplot as plt

from ..experiment_base import ExperimentBase, create_clks_array
from ..result import AnalysisResult, FitResult
from ...analysis import post_process as pp
from ...analysis.fitting import fit_and_wrap, build_fit_legend
from ...analysis.cQED_models import (
    qubit_spec_model,
    T1_relaxation_model,
    T2_ramsey_model,
    power_rabi_model,
)
from ...hardware.program_runner import RunResult
from ...programs import cQED_programs


class FockResolvedSpectroscopy(ExperimentBase):
    """Fock-resolved spectroscopy with post-selection.

    Probes qubit spectroscopy conditioned on photon number via
    selective pi-pulses and double post-selection.
    """

    def run(
        self,
        probe_fqs: list[float] | np.ndarray,
        *,
        state_prep: Any,
        sel_r180: str = "sel_x180",
        calibrate_ref_r180_S: bool = True,
        n_avg: int = 100,
    ) -> RunResult:
        attr = self.attr
        self.set_standard_frequencies()

        prog = cQED_programs.fock_resolved_spectroscopy(
            attr.qb_el, attr.st_el,
            np.asarray(probe_fqs),
            state_prep, sel_r180,
            calibrate_ref_r180_S,
            attr.qb_therm_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[pp.proc_default],
        )
        self.save_output(result.output, "fockResolvedSpectroscopy")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        S = result.output.extract("S")
        metrics: dict[str, Any] = {}

        if S is not None:
            # S may be 2D (n_fock, n_freqs) or 1D
            if S.ndim == 2:
                n_fock = S.shape[0]
                fock_freqs: list[float] = []
                for n in range(n_fock):
                    mag = np.abs(S[n])
                    fock_freqs.append(float(mag.min()))  # placeholder
                metrics["n_fock"] = n_fock
            else:
                mag = np.abs(S)
                metrics["n_points"] = int(len(mag))

        return AnalysisResult.from_run(result, metrics=metrics)

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        S = analysis.data.get("S")
        if S is None:
            return None

        if S.ndim == 2:
            n_fock = S.shape[0]
            fig, axes = plt.subplots(1, n_fock, figsize=(5 * n_fock, 4), squeeze=False)
            axes = axes[0]
            for n in range(n_fock):
                mag = np.abs(S[n])
                axes[n].plot(mag, "o-", ms=3)
                axes[n].set_title(f"Fock |{n}>")
                axes[n].set_xlabel("Point Index")
                axes[n].set_ylabel("Magnitude")
                axes[n].grid(True, alpha=0.3)
        else:
            if ax is None:
                fig, ax = plt.subplots(figsize=(10, 5))
            else:
                fig = ax.figure
            mag = np.abs(S)
            ax.plot(mag, "o-", ms=3)
            ax.set_xlabel("Point Index")
            ax.set_ylabel("Magnitude")
            ax.set_title("Fock-Resolved Spectroscopy")
            ax.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.show()
        return fig


class FockResolvedT1(ExperimentBase):
    """T1 relaxation measurement in individual Fock manifolds."""

    def run(
        self,
        fock_fqs: list[float] | np.ndarray,
        fock_disps: list[str],
        delay_end: int,
        dt: int,
        delay_begin: int = 4,
        sel_r180: str = "sel_x180",
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        delay_clks = create_clks_array(delay_begin, delay_end, dt, time_per_clk=4)

        self.set_standard_frequencies()

        prog = cQED_programs.fock_resolved_T1_relaxation(
            attr.qb_el, attr.st_el,
            np.asarray(fock_fqs), fock_disps,
            delay_clks, sel_r180,
            attr.qb_therm_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("delays", delay_clks * 4),
            ],
        )
        self.save_output(result.output, "fockResolvedT1")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, p0=None, **kw) -> AnalysisResult:
        delays = result.output.extract("delays")
        S = result.output.extract("S")
        metrics: dict[str, Any] = {}
        fits: dict[str, FitResult] = {}

        if S is not None and delays is not None:
            # S may be 2D (n_fock, n_delays) for per-Fock data
            if S.ndim == 2:
                n_fock = S.shape[0]
                for n in range(n_fock):
                    mag = np.abs(S[n])
                    A_guess = float(mag[0] - mag[-1])
                    T1_guess = float(delays[-1]) / 3
                    offset_guess = float(mag[-1])
                    auto_p0 = [A_guess, T1_guess, offset_guess]

                    fit = fit_and_wrap(delays, mag, T1_relaxation_model,
                                       p0 if p0 is not None else auto_p0,
                                       model_name=f"T1_fock_{n}", **kw)
                    fits[f"fock_{n}"] = fit
                    if fit.params:
                        metrics[f"T1_fock_{n}"] = fit.params["T1"]
            else:
                mag = np.abs(S)
                A_guess = float(mag[0] - mag[-1])
                T1_guess = float(delays[-1]) / 3
                offset_guess = float(mag[-1])
                auto_p0 = [A_guess, T1_guess, offset_guess]

                fit = fit_and_wrap(delays, mag, T1_relaxation_model,
                                   p0 if p0 is not None else auto_p0,
                                   model_name="T1_fock", **kw)
                fits["fock_0"] = fit
                if fit.params:
                    metrics["T1_fock_0"] = fit.params["T1"]

        return AnalysisResult.from_run(result, fit=fits.get("fock_0"), fits=fits, metrics=metrics)

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        delays = analysis.data.get("delays")
        S = analysis.data.get("S")
        if delays is None or S is None:
            return None

        if S.ndim == 2:
            n_fock = S.shape[0]
            fig, axes = plt.subplots(1, n_fock, figsize=(5 * n_fock, 4), squeeze=False)
            axes = axes[0]
            all_fits = analysis.fits or {}
            for n in range(n_fock):
                mag = np.abs(S[n])
                axes[n].scatter(delays / 1e3, mag, s=5, label="Data")

                fock_fit = all_fits.get(f"fock_{n}")
                if fock_fit and fock_fit.params:
                    p = fock_fit.params
                    x_fit = np.linspace(delays.min(), delays.max(), 300)
                    y_fit = T1_relaxation_model(x_fit, p["A"], p["T1"], p["offset"])
                    axes[n].plot(x_fit / 1e3, y_fit, "r-", lw=2,
                                label=build_fit_legend(fock_fit))

                axes[n].set_title(f"Fock |{n}> T1")
                axes[n].set_xlabel("Delay (us)")
                axes[n].set_ylabel("Magnitude")
                axes[n].legend(
                    bbox_to_anchor=(1.05, 1), loc='upper left',
                    fontsize=9, borderaxespad=0.0,
                )
                axes[n].grid(True, alpha=0.3)
        else:
            if ax is None:
                fig, ax = plt.subplots(figsize=(10, 5))
            else:
                fig = ax.figure
            mag = np.abs(S)
            ax.scatter(delays / 1e3, mag, s=5, label="Data")
            if analysis.fit and analysis.fit.params:
                p = analysis.fit.params
                x_fit = np.linspace(delays.min(), delays.max(), 300)
                y_fit = T1_relaxation_model(x_fit, p["A"], p["T1"], p["offset"])
                ax.plot(x_fit / 1e3, y_fit, "r-", lw=2,
                        label=build_fit_legend(analysis.fit))
            ax.set_xlabel("Delay (us)")
            ax.set_ylabel("Magnitude")
            ax.set_title("Fock-Resolved T1")
            ax.legend(
                bbox_to_anchor=(1.05, 1), loc='upper left',
                fontsize=10, borderaxespad=0.0,
            )
            ax.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.show()
        return fig


class FockResolvedRamsey(ExperimentBase):
    """Ramsey measurement in individual Fock manifolds.

    Per-Fock selective pi/2 with independent displacement
    per manifold; detuning sweep.
    """

    def run(
        self,
        fock_fqs: list[float] | np.ndarray,
        detunings: list[float] | np.ndarray,
        disps: list[str],
        delay_end: int,
        dt: int,
        delay_begin: int = 4,
        sel_r90: str = "sel_x90",
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        delay_clks = create_clks_array(delay_begin, delay_end, dt, time_per_clk=4)

        self.set_standard_frequencies()

        prog = cQED_programs.fock_resolved_qb_ramsey(
            attr.qb_el, attr.st_el,
            np.asarray(fock_fqs), np.asarray(detunings),
            disps, delay_clks, sel_r90,
            attr.qb_therm_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("delays", delay_clks * 4),
            ],
        )
        self.save_output(result.output, "fockResolvedRamsey")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, p0=None, **kw) -> AnalysisResult:
        delays = result.output.extract("delays")
        S = result.output.extract("S")
        metrics: dict[str, Any] = {}
        fits: dict[str, FitResult] = {}

        if S is not None and delays is not None:
            if S.ndim == 2:
                n_fock = S.shape[0]
                for n in range(n_fock):
                    mag = np.abs(S[n])
                    A_guess = float((mag.max() - mag.min()) / 2)
                    T2_guess = float(delays[-1]) / 3
                    offset_guess = float(mag.mean())
                    auto_p0 = [A_guess, T2_guess, 1.0, 0.0, 0.0, offset_guess]

                    fit = fit_and_wrap(delays, mag, T2_ramsey_model,
                                       p0 if p0 is not None else auto_p0,
                                       model_name=f"T2_fock_{n}", **kw)
                    fits[f"fock_{n}"] = fit
                    if fit.params:
                        metrics[f"T2_fock_{n}"] = fit.params["T2"]
            else:
                mag = np.abs(S)
                A_guess = float((mag.max() - mag.min()) / 2)
                T2_guess = float(delays[-1]) / 3
                offset_guess = float(mag.mean())
                auto_p0 = [A_guess, T2_guess, 1.0, 0.0, 0.0, offset_guess]

                fit = fit_and_wrap(delays, mag, T2_ramsey_model,
                                   p0 if p0 is not None else auto_p0,
                                   model_name="T2_fock", **kw)
                fits["fock_0"] = fit
                if fit.params:
                    metrics["T2_fock_0"] = fit.params["T2"]

        return AnalysisResult.from_run(result, fit=fits.get("fock_0"), fits=fits, metrics=metrics)

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        delays = analysis.data.get("delays")
        S = analysis.data.get("S")
        if delays is None or S is None:
            return None

        if S.ndim == 2:
            n_fock = S.shape[0]
            fig, axes = plt.subplots(1, n_fock, figsize=(5 * n_fock, 4), squeeze=False)
            axes = axes[0]
            all_fits = analysis.fits or {}
            for n in range(n_fock):
                mag = np.abs(S[n])
                axes[n].scatter(delays / 1e3, mag, s=5, label="Data")

                fock_fit = all_fits.get(f"fock_{n}")
                if fock_fit and fock_fit.params:
                    p = fock_fit.params
                    x_fit = np.linspace(delays.min(), delays.max(), 500)
                    y_fit = T2_ramsey_model(x_fit, p["A"], p["T2"], p["n"],
                                            p["f_det"], p["phi"], p["offset"])
                    axes[n].plot(x_fit / 1e3, y_fit, "r-", lw=2,
                                label=build_fit_legend(fock_fit))
                    axes[n].set_title(f"Fock |{n}> T2={p['T2']/1e3:.2f} us")
                else:
                    axes[n].set_title(f"Fock |{n}> Ramsey")

                axes[n].set_xlabel("Delay (us)")
                axes[n].set_ylabel("Magnitude")
                axes[n].legend(
                    bbox_to_anchor=(1.05, 1), loc='upper left',
                    fontsize=9, borderaxespad=0.0,
                )
                axes[n].grid(True, alpha=0.3)
        else:
            if ax is None:
                fig, ax = plt.subplots(figsize=(10, 5))
            else:
                fig = ax.figure
            mag = np.abs(S)
            ax.scatter(delays / 1e3, mag, s=5, label="Data")
            if analysis.fit and analysis.fit.params:
                p = analysis.fit.params
                x_fit = np.linspace(delays.min(), delays.max(), 500)
                y_fit = T2_ramsey_model(x_fit, p["A"], p["T2"], p["n"],
                                        p["f_det"], p["phi"], p["offset"])
                ax.plot(x_fit / 1e3, y_fit, "r-", lw=2,
                        label=build_fit_legend(analysis.fit))
            ax.set_xlabel("Delay (us)")
            ax.set_ylabel("Magnitude")
            ax.set_title("Fock-Resolved Ramsey")
            ax.legend(
                bbox_to_anchor=(1.05, 1), loc='upper left',
                fontsize=10, borderaxespad=0.0,
            )
            ax.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.show()
        return fig


class FockResolvedPowerRabi(ExperimentBase):
    """Power Rabi oscillations in Fock manifolds.

    Sweeps gain across Fock-number-resolved qubit transitions.
    """

    def run(
        self,
        fock_fqs: list[float] | np.ndarray,
        gains: list[float] | np.ndarray,
        sel_qb_pulse: str,
        disp_n_list: list[str],
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        self.set_standard_frequencies()

        prog = cQED_programs.fock_resolved_power_rabi(
            attr.qb_el, attr.st_el,
            np.asarray(fock_fqs), np.asarray(gains),
            sel_qb_pulse, disp_n_list,
            attr.qb_therm_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("gains", np.asarray(gains)),
            ],
        )
        self.save_output(result.output, "fockResolvedPowerRabi")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, p0=None, **kw) -> AnalysisResult:
        gains = result.output.extract("gains")
        S = result.output.extract("S")
        metrics: dict[str, Any] = {}
        fits: dict[str, FitResult] = {}

        if S is not None and gains is not None:
            if S.ndim == 2:
                n_fock = S.shape[0]
                for n in range(n_fock):
                    mag = np.abs(S[n])
                    A_guess = float((mag.max() - mag.min()) / 2)
                    g_pi_guess = float(gains[np.argmin(mag)])
                    offset_guess = float(mag.mean())
                    auto_p0 = [A_guess, g_pi_guess, offset_guess]

                    fit = fit_and_wrap(gains, mag, power_rabi_model,
                                       p0 if p0 is not None else auto_p0,
                                       model_name=f"rabi_fock_{n}", **kw)
                    fits[f"fock_{n}"] = fit
                    if fit.params:
                        metrics[f"g_pi_fock_{n}"] = fit.params["g_pi"]
            else:
                mag = np.abs(S)
                A_guess = float((mag.max() - mag.min()) / 2)
                g_pi_guess = float(gains[np.argmin(mag)])
                offset_guess = float(mag.mean())
                auto_p0 = [A_guess, g_pi_guess, offset_guess]

                fit = fit_and_wrap(gains, mag, power_rabi_model,
                                   p0 if p0 is not None else auto_p0,
                                   model_name="rabi_fock", **kw)
                fits["fock_0"] = fit
                if fit.params:
                    metrics["g_pi_fock_0"] = fit.params["g_pi"]

        return AnalysisResult.from_run(result, fit=fits.get("fock_0"), fits=fits, metrics=metrics)

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        gains = analysis.data.get("gains")
        S = analysis.data.get("S")
        if gains is None or S is None:
            return None

        if S.ndim == 2:
            n_fock = S.shape[0]
            fig, axes = plt.subplots(1, n_fock, figsize=(5 * n_fock, 4), squeeze=False)
            axes = axes[0]
            all_fits = analysis.fits or {}
            for n in range(n_fock):
                mag = np.abs(S[n])
                axes[n].scatter(gains, mag, s=5, label="Data")

                fock_fit = all_fits.get(f"fock_{n}")
                if fock_fit and fock_fit.params:
                    p = fock_fit.params
                    x_fit = np.linspace(gains.min(), gains.max(), 300)
                    y_fit = power_rabi_model(x_fit, p["A"], p["g_pi"], p["offset"])
                    axes[n].plot(x_fit, y_fit, "r-", lw=2,
                                label=build_fit_legend(fock_fit))
                    axes[n].axvline(p["g_pi"], color="green", ls="--", alpha=0.7,
                                   label=f"g_pi={p['g_pi']:.4f}")

                axes[n].set_title(f"Fock |{n}> Power Rabi")
                axes[n].set_xlabel("Gain")
                axes[n].set_ylabel("Magnitude")
                axes[n].legend(
                    bbox_to_anchor=(1.05, 1), loc='upper left',
                    fontsize=9, borderaxespad=0.0,
                )
                axes[n].grid(True, alpha=0.3)
        else:
            if ax is None:
                fig, ax = plt.subplots(figsize=(10, 5))
            else:
                fig = ax.figure
            mag = np.abs(S)
            ax.scatter(gains, mag, s=5, label="Data")
            if analysis.fit and analysis.fit.params:
                p = analysis.fit.params
                x_fit = np.linspace(gains.min(), gains.max(), 300)
                y_fit = power_rabi_model(x_fit, p["A"], p["g_pi"], p["offset"])
                ax.plot(x_fit, y_fit, "r-", lw=2,
                        label=build_fit_legend(analysis.fit))
            ax.set_xlabel("Gain")
            ax.set_ylabel("Magnitude")
            ax.set_title("Fock-Resolved Power Rabi")
            ax.legend(
                bbox_to_anchor=(1.05, 1), loc='upper left',
                fontsize=10, borderaxespad=0.0,
            )
            ax.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.show()
        return fig
