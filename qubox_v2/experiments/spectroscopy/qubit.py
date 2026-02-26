"""Qubit spectroscopy experiments."""
from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib.pyplot as plt

from ..experiment_base import (
    ExperimentBase, create_if_frequencies,
    make_lo_segments, if_freqs_for_segment, merge_segment_outputs,
)
from ..result import AnalysisResult, FitResult
from ...analysis import post_process as pp
from ...analysis.fitting import fit_and_wrap, build_fit_legend
from ...analysis.cQED_models import qubit_spec_model
from ...analysis.output import Output
from ...hardware.program_runner import ExecMode, RunResult
from ...programs import cQED_programs
from ...programs.macros.measure import measureMacro
from ...calibration.transitions import Transition, DEFAULT_TRANSITION, resolve_pulse_name


# ---------------------------------------------------------------------------
# Transition → frequency-field routing
# ---------------------------------------------------------------------------
_TRANSITION_FREQ_MAP: dict[str, tuple[str, str]] = {
    # transition_value → (calibration_kind, ElementFrequencies field)
    "ge": ("qubit_freq", "qubit_freq"),
    "ef": ("ef_freq",    "ef_freq"),
}


class QubitSpectroscopy(ExperimentBase):
    """Single-LO qubit spectroscopy scan over IF frequencies."""

    def run(
        self,
        pulse: str,
        rf_begin: float,
        rf_end: float,
        df: float,
        qb_gain: float,
        qb_len: int,
        n_avg: int = 1000,
        transition: str = "ge",
    ) -> RunResult:
        attr = self.attr
        lo_qb = self.hw.get_element_lo(attr.qb_el)
        if_freqs = create_if_frequencies(attr.qb_el, rf_begin, rf_end, df, lo_freq=lo_qb)

        self.set_standard_frequencies()

        prog = cQED_programs.qubit_spectroscopy(
            pulse, attr.qb_el, if_freqs, qb_gain, qb_len,
            attr.qb_therm_clks, n_avg,
        )

        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("frequencies", lo_qb + if_freqs),
            ],
        )
        result.metadata = {**(result.metadata or {}), "transition": transition}
        self.save_output(result.output, "qubitSpectroscopy")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, p0=None, **kw) -> AnalysisResult:
        transition = (result.metadata or {}).get("transition", "ge")
        cal_kind, freq_field = _TRANSITION_FREQ_MAP.get(transition, ("qubit_freq", "qubit_freq"))

        freqs = result.output.extract("frequencies")
        S = result.output.extract("S")
        mag = np.abs(S)

        f0_guess = freqs[np.argmin(mag)]
        gamma_guess = (freqs[-1] - freqs[0]) / 20
        A_guess = float(mag.min() - mag.max())
        offset_guess = float(mag.max())
        auto_p0 = [f0_guess, gamma_guess, A_guess, offset_guess]

        fit = fit_and_wrap(freqs, mag, qubit_spec_model,
                           p0 if p0 is not None else auto_p0,
                           model_name="qubit_lorentzian", **kw)

        metrics: dict[str, Any] = {}
        if fit.params:
            metrics["f0"] = fit.params["f0"]
            metrics["gamma"] = fit.params["gamma"]

        metadata: dict[str, Any] = {
            "calibration_kind": cal_kind,
            "transition": transition,
            "units": {"f0": "Hz", "f0_MHz": "MHz"},
        }
        if fit.params:
            metrics["f0_MHz"] = float(fit.params["f0"] / 1e6)

        if update_calibration and fit.params:
            metadata.setdefault("proposed_patch_ops", []).append(
                {
                    "op": "SetCalibration",
                    "payload": {
                        "path": f"frequencies.{self.attr.qb_el}.{freq_field}",
                        "value": float(fit.params["f0"]),
                    },
                }
            )

        analysis = AnalysisResult.from_run(result, fit=fit, metrics=metrics, metadata=metadata)

        return analysis

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        freqs = analysis.data.get("frequencies")
        S = analysis.data.get("S")
        if freqs is None or S is None:
            return None

        mag = np.abs(S)
        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 5))
        else:
            fig = ax.figure

        ax.scatter(freqs / 1e6, mag, s=5, label="Data")
        if analysis.fit and analysis.fit.params:
            p = analysis.fit.params
            x_fit = np.linspace(freqs.min(), freqs.max(), 500)
            y_fit = qubit_spec_model(x_fit, p["f0"], p["gamma"], p["A"], p["offset"])
            ax.plot(x_fit / 1e6, y_fit, "r-", lw=2,
                    label=build_fit_legend(analysis.fit))

        ax.set_xlabel("Frequency (MHz)")
        ax.set_ylabel("Magnitude")
        ax.set_title("Qubit Spectroscopy")
        ax.legend(
            bbox_to_anchor=(1.05, 1), loc='upper left',
            fontsize=10, borderaxespad=0.0,
        )
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig


class QubitSpectroscopyCoarse(ExperimentBase):
    """Multi-LO qubit spectroscopy for wide frequency sweeps.

    Automatically segments the frequency range into multiple LO
    windows and stitches the results.
    """

    def run(
        self,
        pulse: str,
        rf_begin: float,
        rf_end: float,
        df: float,
        qb_gain: float,
        qb_len: int,
        n_avg: int = 1000,
        transition: str = "ge",
    ) -> RunResult:
        attr = self.attr
        lo_list = make_lo_segments(rf_begin, rf_end)

        seg_results: list[RunResult] = []
        all_freqs: list[np.ndarray] = []

        for LO in lo_list:
            self.hw.set_element_lo(attr.qb_el, LO)
            ifs = if_freqs_for_segment(LO, rf_end, df)

            prog = cQED_programs.qubit_spectroscopy(
                pulse, attr.qb_el, ifs, qb_gain, qb_len,
                attr.qb_therm_clks, n_avg,
            )
            rr = self.run_program(
                prog, n_total=n_avg,
                processors=[
                    pp.proc_default,
                    pp.proc_attach("frequencies", LO + ifs),
                ],
            )
            seg_results.append(rr)
            all_freqs.append(LO + ifs)

        final_output = merge_segment_outputs(
            [r.output for r in seg_results], all_freqs,
        )
        mode = seg_results[0].mode if seg_results else ExecMode.SIMULATE
        final = RunResult(
            mode=mode, output=final_output, sim_samples=None,
            metadata={"segments": len(seg_results), "transition": transition},
        )
        self.save_output(final_output, "qubitSpectroscopy")
        return final

    def analyze(self, result: RunResult, *, update_calibration: bool = False, p0=None, **kw) -> AnalysisResult:
        transition = (result.metadata or {}).get("transition", "ge")
        cal_kind, freq_field = _TRANSITION_FREQ_MAP.get(transition, ("qubit_freq", "qubit_freq"))

        freqs = result.output.extract("frequencies")
        S = result.output.extract("S")
        mag = np.abs(S)

        f0_guess = freqs[np.argmin(mag)]
        gamma_guess = (freqs[-1] - freqs[0]) / 20
        A_guess = float(mag.min() - mag.max())
        offset_guess = float(mag.max())
        auto_p0 = [f0_guess, gamma_guess, A_guess, offset_guess]

        fit = fit_and_wrap(freqs, mag, qubit_spec_model,
                           p0 if p0 is not None else auto_p0,
                           model_name="qubit_lorentzian_coarse", **kw)

        metrics: dict[str, Any] = {}
        if fit.params:
            metrics["f0"] = fit.params["f0"]
            metrics["gamma"] = fit.params["gamma"]

        metadata: dict[str, Any] = {
            "calibration_kind": cal_kind,
            "transition": transition,
            "units": {"f0": "Hz", "f0_MHz": "MHz"},
        }
        if fit.params:
            metrics["f0_MHz"] = float(fit.params["f0"] / 1e6)

        if update_calibration and fit.params:
            metadata.setdefault("proposed_patch_ops", []).append(
                {
                    "op": "SetCalibration",
                    "payload": {
                        "path": f"frequencies.{self.attr.qb_el}.{freq_field}",
                        "value": float(fit.params["f0"]),
                    },
                }
            )

        analysis = AnalysisResult.from_run(result, fit=fit, metrics=metrics, metadata=metadata)

        return analysis

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        freqs = analysis.data.get("frequencies")
        S = analysis.data.get("S")
        if freqs is None or S is None:
            return None

        mag = np.abs(S)
        if ax is None:
            fig, ax = plt.subplots(figsize=(12, 5))
        else:
            fig = ax.figure

        ax.scatter(freqs / 1e6, mag, s=3, label="Data")
        if analysis.fit and analysis.fit.params:
            p = analysis.fit.params
            x_fit = np.linspace(freqs.min(), freqs.max(), 1000)
            y_fit = qubit_spec_model(x_fit, p["f0"], p["gamma"], p["A"], p["offset"])
            ax.plot(x_fit / 1e6, y_fit, "r-", lw=2,
                    label=build_fit_legend(analysis.fit))

        ax.set_xlabel("Frequency (MHz)")
        ax.set_ylabel("Magnitude")
        ax.set_title("Qubit Spectroscopy (Coarse)")
        ax.legend(
            bbox_to_anchor=(1.05, 1), loc='upper left',
            fontsize=10, borderaxespad=0.0,
        )
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig


class QubitSpectroscopyEF(ExperimentBase):
    """e->f transition spectroscopy with prior pi-pulse excitation.

    The GE prep pulse (``ge_prep_pulse``) prepares |e> before sweeping
    the EF drive frequency.  Calibration writeback targets
    ``frequencies.<qb_el>.ef_freq`` via the ``"ef_freq"`` calibration kind.
    """

    def run(
        self,
        pulse: str,
        rf_begin: float,
        rf_end: float,
        df: float,
        qb_gain: float,
        qb_len: int,
        n_avg: int = 1000,
        ge_prep_pulse: str = "ge_x180",
    ) -> RunResult:
        attr = self.attr
        lo_qb = self.hw.get_element_lo(attr.qb_el)
        if_freqs = create_if_frequencies(attr.qb_el, rf_begin, rf_end, df, lo_freq=lo_qb)

        self.set_standard_frequencies()

        prog = cQED_programs.qubit_spectroscopy_ef(
            pulse, attr.qb_el, if_freqs,
            self.hw.get_element_if(attr.qb_el),
            qb_gain, qb_len, ge_prep_pulse, attr.qb_therm_clks, n_avg,
        )

        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("frequencies", lo_qb + if_freqs),
            ],
        )
        result.metadata = {
            **(result.metadata or {}),
            "transition": "ef",
            "ge_prep_pulse": ge_prep_pulse,
        }
        self.save_output(result.output, "qubit_efSpectroscopy")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, p0=None, **kw) -> AnalysisResult:
        freqs = result.output.extract("frequencies")
        S = result.output.extract("S")
        mag = np.abs(S)

        f0_guess = freqs[np.argmin(mag)]
        gamma_guess = (freqs[-1] - freqs[0]) / 20
        A_guess = float(mag.min() - mag.max())
        offset_guess = float(mag.max())
        auto_p0 = [f0_guess, gamma_guess, A_guess, offset_guess]

        fit = fit_and_wrap(freqs, mag, qubit_spec_model,
                           p0 if p0 is not None else auto_p0,
                           model_name="qubit_ef_lorentzian", **kw)

        metrics: dict[str, Any] = {}
        if fit.params:
            metrics["f0"] = fit.params["f0"]
            metrics["f_ef"] = fit.params["f0"]
            metrics["gamma"] = fit.params["gamma"]

        metadata: dict[str, Any] = {
            "calibration_kind": "ef_freq",
            "transition": "ef",
            "units": {"f0": "Hz", "f_ef": "Hz", "f0_MHz": "MHz"},
        }
        if fit.params:
            metrics["f0_MHz"] = float(fit.params["f0"] / 1e6)

        if update_calibration and fit.params:
            metadata.setdefault("proposed_patch_ops", []).append(
                {
                    "op": "SetCalibration",
                    "payload": {
                        "path": f"frequencies.{self.attr.qb_el}.ef_freq",
                        "value": float(fit.params["f0"]),
                    },
                }
            )

        return AnalysisResult.from_run(result, fit=fit, metrics=metrics, metadata=metadata)

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        freqs = analysis.data.get("frequencies")
        S = analysis.data.get("S")
        if freqs is None or S is None:
            return None

        mag = np.abs(S)
        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 5))
        else:
            fig = ax.figure

        ax.scatter(freqs / 1e6, mag, s=5, label="Data")
        if analysis.fit and analysis.fit.params:
            p = analysis.fit.params
            x_fit = np.linspace(freqs.min(), freqs.max(), 500)
            y_fit = qubit_spec_model(x_fit, p["f0"], p["gamma"], p["A"], p["offset"])
            ax.plot(x_fit / 1e6, y_fit, "r-", lw=2,
                    label=build_fit_legend(analysis.fit))

        ax.set_xlabel("Frequency (MHz)")
        ax.set_ylabel("Magnitude")
        ax.set_title("Qubit EF Spectroscopy")
        ax.legend(
            bbox_to_anchor=(1.05, 1), loc='upper left',
            fontsize=10, borderaxespad=0.0,
        )
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig
