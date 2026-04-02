"""Qubit spectroscopy experiments."""
from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib.pyplot as plt

from ..experiment_base import (
    ExperimentBase, create_if_frequencies,
    make_lo_segments, if_freqs_for_segment, merge_segment_outputs,
)
from ..result import AnalysisResult, FitResult, ProgramBuildResult
from qubox_tools.algorithms import post_process as pp
from qubox_tools.fitting.routines import fit_and_wrap, build_fit_legend
from qubox_tools.fitting.cqed import qubit_spec_model
from qubox_tools.data.containers import Output
from ...hardware.program_runner import ExecMode, RunResult
from ...programs import api as cQED_programs
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


def _resolve_qb_therm_clks(exp: ExperimentBase, value: int | None, owner: str) -> int:
    return int(exp.resolve_override_or_attr(
        value=value,
        attr_name="qb_therm_clks",
        owner=owner,
        cast=int,
    ))


class QubitSpectroscopy(ExperimentBase):
    """Single-LO qubit spectroscopy scan over IF frequencies."""

    def _build_impl(
        self,
        pulse: str,
        rf_begin: float,
        rf_end: float,
        df: float,
        qb_gain: float,
        qb_len: int,
        n_avg: int = 1000,
        transition: str = "ge",
        qb_therm_clks: int | None = None,
    ) -> ProgramBuildResult:
        attr = self.attr
        lo_qb = self.get_qubit_lo()
        if_freqs = create_if_frequencies(attr.qb_el, rf_begin, rf_end, df, lo_freq=lo_qb)
        qb_therm = _resolve_qb_therm_clks(self, qb_therm_clks, "QubitSpectroscopy")

        ro_fq = self._resolve_readout_frequency()

        prog = cQED_programs.qubit_spectroscopy(
            pulse, if_freqs, qb_gain, qb_len,
            qb_therm, n_avg,
            qb_el=attr.qb_el,
            bindings=self._bindings_or_none,
            readout=self.readout_handle,
        )

        return ProgramBuildResult(
            program=prog,
            n_total=n_avg,
            processors=(
                pp.proc_default,
                pp.proc_attach("frequencies", lo_qb + if_freqs),
            ),
            experiment_name="QubitSpectroscopy",
            params={
                "pulse": pulse, "rf_begin": rf_begin, "rf_end": rf_end,
                "df": df, "qb_gain": qb_gain, "qb_len": qb_len,
                "n_avg": n_avg, "transition": transition,
                "qb_therm_clks": qb_therm,
            },
            resolved_frequencies={attr.ro_el: ro_fq},
            bindings_snapshot=self._serialize_bindings(),
            builder_function="cQED_programs.qubit_spectroscopy",
            sweep_axes={"frequencies": lo_qb + if_freqs},
        )

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
        qb_therm_clks: int | None = None,
    ) -> RunResult:
        build = self.build_program(
            pulse=pulse, rf_begin=rf_begin, rf_end=rf_end, df=df,
            qb_gain=qb_gain, qb_len=qb_len, n_avg=n_avg,
            transition=transition, qb_therm_clks=qb_therm_clks,
        )
        result = self.run_program(
            build.program, n_total=build.n_total,
            processors=list(build.processors),
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
            cqed_field = "ef_freq" if freq_field == "ef_freq" else "qubit_freq"
            metadata.setdefault("proposed_patch_ops", []).append(
                {
                    "op": "SetCalibration",
                    "payload": {
                        "path": f"cqed_params.transmon.{cqed_field}",
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

    def _build_impl(self, **kw):
        raise NotImplementedError(
            "QubitSpectroscopyCoarse uses a multi-LO segment loop and cannot "
            "produce a single ProgramBuildResult. Use run() directly."
        )

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
        qb_therm_clks: int | None = None,
    ) -> RunResult:
        attr = self.attr
        lo_list = make_lo_segments(rf_begin, rf_end)
        qb_therm = _resolve_qb_therm_clks(self, qb_therm_clks, "QubitSpectroscopyCoarse")

        seg_results: list[RunResult] = []
        all_freqs: list[np.ndarray] = []

        for LO in lo_list:
            self.hw.set_element_lo(attr.qb_el, LO)
            ifs = if_freqs_for_segment(LO, rf_end, df)

            prog = cQED_programs.qubit_spectroscopy(
                pulse, ifs, qb_gain, qb_len,
                qb_therm, n_avg,
                qb_el=attr.qb_el,
                bindings=self._bindings_or_none,
                readout=self.readout_handle,
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
            cqed_field = "ef_freq" if freq_field == "ef_freq" else "qubit_freq"
            metadata.setdefault("proposed_patch_ops", []).append(
                {
                    "op": "SetCalibration",
                    "payload": {
                        "path": f"cqed_params.transmon.{cqed_field}",
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

    def _build_impl(
        self,
        pulse: str,
        rf_begin: float,
        rf_end: float,
        df: float,
        qb_gain: float,
        qb_len: int,
        n_avg: int = 1000,
        ge_prep_pulse: str = "ge_x180",
        qb_therm_clks: int | None = None,
    ) -> ProgramBuildResult:
        attr = self.attr
        lo_qb = self.get_qubit_lo()
        if_freqs = create_if_frequencies(attr.qb_el, rf_begin, rf_end, df, lo_freq=lo_qb)
        qb_therm = _resolve_qb_therm_clks(self, qb_therm_clks, "QubitSpectroscopyEF")

        ro_fq = self._resolve_readout_frequency()
        qb_fq = self._resolve_qubit_frequency()
        qb_if = int(qb_fq - lo_qb)

        prog = cQED_programs.qubit_spectroscopy_ef(
            pulse, if_freqs,
            qb_if,
            qb_gain, qb_len, ge_prep_pulse, qb_therm, n_avg,
            qb_el=attr.qb_el,
            bindings=self._bindings_or_none,
            readout=self.readout_handle,
        )

        return ProgramBuildResult(
            program=prog,
            n_total=n_avg,
            processors=(
                pp.proc_default,
                pp.proc_attach("frequencies", lo_qb + if_freqs),
            ),
            experiment_name="QubitSpectroscopyEF",
            params={
                "pulse": pulse, "rf_begin": rf_begin, "rf_end": rf_end,
                "df": df, "qb_gain": qb_gain, "qb_len": qb_len,
                "n_avg": n_avg, "ge_prep_pulse": ge_prep_pulse,
                "qb_therm_clks": qb_therm,
            },
            resolved_frequencies={attr.ro_el: ro_fq, attr.qb_el: qb_fq},
            bindings_snapshot=self._serialize_bindings(),
            builder_function="cQED_programs.qubit_spectroscopy_ef",
            sweep_axes={"frequencies": lo_qb + if_freqs},
        )

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
        qb_therm_clks: int | None = None,
    ) -> RunResult:
        build = self.build_program(
            pulse=pulse, rf_begin=rf_begin, rf_end=rf_end, df=df,
            qb_gain=qb_gain, qb_len=qb_len, n_avg=n_avg,
            ge_prep_pulse=ge_prep_pulse, qb_therm_clks=qb_therm_clks,
        )
        result = self.run_program(
            build.program, n_total=build.n_total,
            processors=list(build.processors),
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
                        "path": "cqed_params.transmon.ef_freq",
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
