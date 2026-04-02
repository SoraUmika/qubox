"""Storage resonator spectroscopy and dynamics experiments."""
from __future__ import annotations

import logging
from typing import Any, Union

import numpy as np
import matplotlib.pyplot as plt

from ..experiment_base import (
    ExperimentBase, create_if_frequencies, create_clks_array,
    make_lo_segments, if_freqs_for_segment, merge_segment_outputs,
)
from ..result import AnalysisResult, FitResult, ProgramBuildResult
from qubox_tools.algorithms import post_process as pp
from qubox_tools.fitting.routines import fit_and_wrap, build_fit_legend
from qubox_tools.fitting.cqed import (
    chi_ramsey_model,
    resonator_spec_model,
    T2_ramsey_model,
)
from qubox_tools.data.containers import Output
from ...hardware.program_runner import ExecMode, RunResult
from ...programs import api as cQED_programs

logger = logging.getLogger(__name__)


def _resolve_storage_therm_clks(
    exp: ExperimentBase,
    value: int | None,
    owner: str,
) -> int:
    return exp.resolve_override_or_attr(
        value=value,
        attr_name="st_therm_clks",
        owner=owner,
        cast=int,
    )


class StorageSpectroscopy(ExperimentBase):
    """Storage resonator frequency sweep with selective qubit rotation."""

    def _build_impl(
        self,
        disp: str,
        rf_begin: float,
        rf_end: float,
        df: float,
        storage_therm_time: int,
        sel_r180: str = "sel_x180",
        n_avg: int = 1000,
    ) -> ProgramBuildResult:
        attr = self.attr
        lo_freq = self.hw.get_element_lo(attr.st_el)
        if_freqs = create_if_frequencies(attr.st_el, rf_begin, rf_end, df, lo_freq)

        ro_fq = self._resolve_readout_frequency()
        qb_fq = self._resolve_qubit_frequency()

        prog = cQED_programs.storage_spectroscopy(
            attr.qb_el, attr.st_el, disp, sel_r180,
            if_freqs, storage_therm_time, n_avg,
            bindings=self._bindings_or_none,
            readout=self.readout_handle,
        )

        return ProgramBuildResult(
            program=prog,
            n_total=n_avg,
            processors=(
                pp.proc_default,
                pp.proc_attach("frequencies", lo_freq + if_freqs),
            ),
            experiment_name="StorageSpectroscopy",
            params={
                "disp": disp, "rf_begin": rf_begin, "rf_end": rf_end,
                "df": df, "storage_therm_time": storage_therm_time,
                "sel_r180": sel_r180, "n_avg": n_avg,
            },
            resolved_frequencies={attr.ro_el: ro_fq, attr.qb_el: qb_fq},
            bindings_snapshot=self._serialize_bindings(),
            builder_function="cQED_programs.storage_spectroscopy",
            sweep_axes={"frequencies": lo_freq + if_freqs},
        )

    def run(
        self,
        disp: str,
        rf_begin: float,
        rf_end: float,
        df: float,
        storage_therm_time: int,
        sel_r180: str = "sel_x180",
        n_avg: int = 1000,
    ) -> RunResult:
        build = self.build_program(
            disp=disp, rf_begin=rf_begin, rf_end=rf_end, df=df,
            storage_therm_time=storage_therm_time,
            sel_r180=sel_r180, n_avg=n_avg,
        )
        result = self.run_program(
            build.program, n_total=build.n_total,
            processors=list(build.processors),
        )
        self.save_output(result.output, "storageSpectroscopy")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, p0=None, **kw) -> AnalysisResult:
        freqs = result.output.extract("frequencies")
        S = result.output.extract("S")
        mag = np.abs(S)

        f0_guess = freqs[np.argmin(mag)]
        kappa_guess = (freqs[-1] - freqs[0]) / 20
        A_guess = float(mag.min() - mag.max())
        offset_guess = float(mag.max())
        auto_p0 = [f0_guess, kappa_guess, A_guess, offset_guess]

        fit = fit_and_wrap(freqs, mag, resonator_spec_model,
                           p0 if p0 is not None else auto_p0,
                           model_name="storage_lorentzian", **kw)

        metrics: dict[str, Any] = {}
        if fit.params:
            metrics["f_storage"] = fit.params["f0"]
            metrics["kappa"] = fit.params["kappa"]

        metadata: dict[str, Any] = {
            "calibration_kind": "storage_freq",
            "units": {"f_storage": "Hz", "f_storage_MHz": "MHz", "kappa": "Hz"},
        }
        if fit.params:
            metrics["f_storage_MHz"] = float(fit.params["f0"] / 1e6)

        if update_calibration and fit.params:
            metadata.setdefault("proposed_patch_ops", []).extend([
                {
                    "op": "SetCalibration",
                    "payload": {
                        "path": "cqed_params.storage.qubit_freq",
                        "value": float(fit.params["f0"]),
                    },
                },
                {
                    "op": "SetCalibration",
                    "payload": {
                        "path": "cqed_params.storage.kappa",
                        "value": float(fit.params["kappa"]),
                    },
                },
            ])

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
            y_fit = resonator_spec_model(x_fit, p["f0"], p["kappa"], p["A"], p["offset"])
            ax.plot(x_fit / 1e6, y_fit, "r-", lw=2,
                    label=build_fit_legend(analysis.fit))

        ax.set_xlabel("Frequency (MHz)")
        ax.set_ylabel("Magnitude")
        ax.set_title("Storage Spectroscopy")
        ax.legend(
            bbox_to_anchor=(1.05, 1), loc='upper left',
            fontsize=10, borderaxespad=0.0,
        )
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig


class StorageSpectroscopyCoarse(ExperimentBase):
    """Multi-LO storage spectroscopy for wide frequency sweeps."""

    def _build_impl(self, **kw):
        raise NotImplementedError(
            "StorageSpectroscopyCoarse uses a multi-LO segment loop and cannot "
            "produce a single ProgramBuildResult. Use run() directly."
        )

    def run(
        self,
        rf_begin: float,
        rf_end: float,
        df: float,
        storage_therm_time: int,
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        lo_list = make_lo_segments(rf_begin, rf_end)

        seg_results: list[RunResult] = []
        all_freqs: list[np.ndarray] = []

        for LO in lo_list:
            self.hw.set_element_lo(attr.st_el, LO)
            ifs = if_freqs_for_segment(LO, rf_end, df)

            prog = cQED_programs.storage_spectroscopy(
                attr.qb_el, attr.st_el, "const_alpha", "sel_x180",
                ifs, storage_therm_time, n_avg,
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
            metadata={"segments": len(seg_results)},
        )
        self.save_output(final_output, "storageSpectroscopyCoarse")
        return final

    def analyze(self, result: RunResult, *, update_calibration: bool = False, p0=None, **kw) -> AnalysisResult:
        freqs = result.output.extract("frequencies")
        S = result.output.extract("S")
        mag = np.abs(S)

        f0_guess = freqs[np.argmin(mag)]
        kappa_guess = (freqs[-1] - freqs[0]) / 20
        A_guess = float(mag.min() - mag.max())
        offset_guess = float(mag.max())
        auto_p0 = [f0_guess, kappa_guess, A_guess, offset_guess]

        fit = fit_and_wrap(freqs, mag, resonator_spec_model,
                           p0 if p0 is not None else auto_p0,
                           model_name="storage_lorentzian_coarse", **kw)

        metrics: dict[str, Any] = {}
        if fit.params:
            metrics["f_storage"] = fit.params["f0"]
            metrics["kappa"] = fit.params["kappa"]

        metadata: dict[str, Any] = {
            "calibration_kind": "storage_freq",
            "units": {"f_storage": "Hz", "kappa": "Hz"},
        }

        if update_calibration and fit.params:
            metadata.setdefault("proposed_patch_ops", []).extend([
                {
                    "op": "SetCalibration",
                    "payload": {
                        "path": "cqed_params.storage.qubit_freq",
                        "value": float(fit.params["f0"]),
                    },
                },
                {
                    "op": "SetCalibration",
                    "payload": {
                        "path": "cqed_params.storage.kappa",
                        "value": float(fit.params["kappa"]),
                    },
                },
            ])

        return AnalysisResult.from_run(result, fit=fit, metrics=metrics, metadata=metadata)

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
            y_fit = resonator_spec_model(x_fit, p["f0"], p["kappa"], p["A"], p["offset"])
            ax.plot(x_fit / 1e6, y_fit, "r-", lw=2,
                    label=build_fit_legend(analysis.fit))

        ax.set_xlabel("Frequency (MHz)")
        ax.set_ylabel("Magnitude")
        ax.set_title("Storage Spectroscopy (Coarse)")
        ax.legend(
            bbox_to_anchor=(1.05, 1), loc='upper left',
            fontsize=10, borderaxespad=0.0,
        )
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig


class NumSplittingSpectroscopy(ExperimentBase):
    """Photon number splitting spectroscopy.

    Probes qubit spectroscopy peaks at individual Fock-number-dependent
    frequencies to resolve photon-number-dependent shifts.
    """

    def _build_impl(
        self,
        rf_centers: list[float] | np.ndarray,
        rf_spans: list[float] | np.ndarray,
        df: float,
        sel_r180: str = "sel_x180",
        state_prep: Any = None,
        n_avg: int = 1000,
        *,
        st_therm_clks: int | None = None,
        allow_default_state_prep: bool = False,
    ) -> ProgramBuildResult:
        attr = self.attr
        st_therm_clks = _resolve_storage_therm_clks(
            self, st_therm_clks, "NumSplittingSpectroscopy"
        )

        ro_fq = self._resolve_readout_frequency()
        qb_fq = self._resolve_qubit_frequency()

        # Default no-op prep is deprecated; require explicit notebook-provided state_prep.
        if state_prep is None:
            if not allow_default_state_prep:
                raise ValueError(
                    "state_prep is required for NumSplittingSpectroscopy. "
                    "Define an explicit preparation macro in your notebook and pass it via state_prep=. "
                    "Temporary compatibility path: set allow_default_state_prep=True to use legacy no-op prep."
                )
            from qm.qua import wait
            def state_prep():
                wait(4)

        # Build IF frequency list from RF centers/spans/df relative to qubit LO
        lo_freq = self.get_qubit_lo()
        if_list: list[int] = []
        rf_list: list[float] = []
        for center, span in zip(rf_centers, rf_spans):
            fqs = np.arange(center - span / 2, center + span / 2 + df / 2, df)
            for fq in fqs:
                if_list.append(int(fq - lo_freq))
                rf_list.append(float(fq))
        if_frequencies = np.array(if_list, dtype=int)

        prog = cQED_programs.num_splitting_spectroscopy(
            state_prep, attr.qb_el, attr.st_el,
            sel_r180, if_frequencies,
            st_therm_clks, n_avg,
            bindings=self._bindings_or_none,
            readout=self.readout_handle,
        )

        return ProgramBuildResult(
            program=prog,
            n_total=n_avg,
            processors=(
                pp.proc_default,
                pp.proc_attach("frequencies", np.array(rf_list)),
            ),
            experiment_name="NumSplittingSpectroscopy",
            params={
                "rf_centers": list(rf_centers), "rf_spans": list(rf_spans),
                "df": df, "sel_r180": sel_r180, "n_avg": n_avg,
                "st_therm_clks": st_therm_clks,
            },
            resolved_frequencies={attr.ro_el: ro_fq, attr.qb_el: qb_fq},
            bindings_snapshot=self._serialize_bindings(),
            builder_function="cQED_programs.num_splitting_spectroscopy",
            sweep_axes={"frequencies": np.array(rf_list)},
        )

    def run(
        self,
        rf_centers: list[float] | np.ndarray,
        rf_spans: list[float] | np.ndarray,
        df: float,
        sel_r180: str = "sel_x180",
        state_prep: Any = None,
        n_avg: int = 1000,
        *,
        st_therm_clks: int | None = None,
        allow_default_state_prep: bool = False,
    ) -> RunResult:
        build = self.build_program(
            rf_centers=rf_centers, rf_spans=rf_spans, df=df,
            sel_r180=sel_r180, state_prep=state_prep, n_avg=n_avg,
            st_therm_clks=st_therm_clks,
            allow_default_state_prep=allow_default_state_prep,
        )
        result = self.run_program(
            build.program, n_total=build.n_total,
            processors=list(build.processors),
        )
        self.save_output(result.output, "numSplittingSpectroscopy")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        if update_calibration:
            logger.warning(
                "NumSplittingSpectroscopy.analyze(): update_calibration=True is not yet "
                "implemented. Use the CalibrationOrchestrator for calibration patching."
            )
        S = result.output.extract("S")
        metrics: dict[str, Any] = {}

        if S is not None:
            mag = np.abs(S)
            metrics["n_peaks"] = int(len(mag))

        return AnalysisResult.from_run(result, metrics=metrics)

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        S = analysis.data.get("S")
        if S is None:
            return None

        mag = np.abs(S)
        freqs = analysis.data.get("frequencies")

        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 5))
        else:
            fig = ax.figure

        if freqs is not None and len(freqs) == len(mag):
            ax.plot(freqs / 1e6, mag, "o-", ms=4, label="Data")
            ax.set_xlabel("Frequency (MHz)")
        else:
            ax.plot(mag, "o-", ms=4, label="Data")
            ax.set_xlabel("Point Index")
        ax.set_ylabel("Magnitude")
        ax.set_title("Number Splitting Spectroscopy")
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig


class StorageRamsey(ExperimentBase):
    """Storage resonator decoherence via Ramsey interferometry."""

    def _build_impl(
        self,
        delay_ticks: np.ndarray | list[int],
        st_detune: int = 0,
        disp_pulse: str = "const_alpha",
        sel_r180: str = "sel_x180",
        n_avg: int = 200,
        st_therm_clks: int | None = None,
    ) -> ProgramBuildResult:
        attr = self.attr
        st_therm_clks = _resolve_storage_therm_clks(self, st_therm_clks, "StorageRamsey")

        ro_fq = self._resolve_readout_frequency()
        qb_fq = self._resolve_qubit_frequency()

        prog = cQED_programs.storage_ramsey(
            attr.ro_el, attr.qb_el, attr.st_el,
            disp_pulse, sel_r180,
            np.asarray(delay_ticks, dtype=int),
            st_therm_clks, n_avg,
            bindings=self._bindings_or_none,
            readout=self.readout_handle,
        )

        return ProgramBuildResult(
            program=prog,
            n_total=n_avg,
            processors=(
                pp.proc_default,
                pp.proc_attach("delays", np.asarray(delay_ticks) * 4),
            ),
            experiment_name="StorageRamsey",
            params={
                "st_detune": st_detune, "disp_pulse": disp_pulse,
                "sel_r180": sel_r180, "n_avg": n_avg,
                "st_therm_clks": st_therm_clks,
            },
            resolved_frequencies={attr.ro_el: ro_fq, attr.qb_el: qb_fq},
            bindings_snapshot=self._serialize_bindings(),
            builder_function="cQED_programs.storage_ramsey",
            sweep_axes={"delays": np.asarray(delay_ticks) * 4},
        )

    def run(
        self,
        delay_ticks: np.ndarray | list[int],
        st_detune: int = 0,
        disp_pulse: str = "const_alpha",
        sel_r180: str = "sel_x180",
        n_avg: int = 200,
        st_therm_clks: int | None = None,
    ) -> RunResult:
        build = self.build_program(
            delay_ticks=delay_ticks, st_detune=st_detune,
            disp_pulse=disp_pulse, sel_r180=sel_r180, n_avg=n_avg,
            st_therm_clks=st_therm_clks,
        )
        result = self.run_program(
            build.program, n_total=build.n_total,
            processors=list(build.processors),
        )
        self.save_output(result.output, "storageRamsey")
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
                           model_name="storage_ramsey", **kw)

        metrics: dict[str, Any] = {}
        if fit.params:
            metrics["T2_storage"] = fit.params["T2"]

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
        ax.set_title("Storage Ramsey")
        ax.legend(
            bbox_to_anchor=(1.05, 1), loc='upper left',
            fontsize=10, borderaxespad=0.0,
        )
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig


class StorageChiRamsey(ExperimentBase):
    """Storage chi (dispersive shift) measurement via Ramsey.

    Measures the cavity-qubit dispersive coupling chi by performing
    Ramsey around a single Fock frequency.
    """

    def _build_impl(
        self,
        fock_fq: float,
        delay_ticks: np.ndarray | list[int],
        disp_pulse: str = "const_alpha",
        x90_pulse: str = "x90",
        n_avg: int = 200,
        st_therm_clks: int | None = None,
    ) -> ProgramBuildResult:
        attr = self.attr
        st_therm_clks = _resolve_storage_therm_clks(self, st_therm_clks, "StorageChiRamsey")

        ro_fq = self._resolve_readout_frequency()
        qb_fq = self._resolve_qubit_frequency()

        # Guard: measureMacro must be configured before running chi Ramsey
        from ...programs.macros.measure import measureMacro
        if not measureMacro._demod_weight_sets:
            raise RuntimeError(
                "measureMacro has no outputs configured. "
                "Run CalibrateReadoutFull (or measureMacro.set_outputs()) first."
            )

        prog = cQED_programs.storage_chi_ramsey(
            attr.ro_el, attr.qb_el, attr.st_el,
            disp_pulse, x90_pulse,
            np.asarray(delay_ticks, dtype=int),
            st_therm_clks, n_avg,
            bindings=self._bindings_or_none,
            readout=self.readout_handle,
        )

        return ProgramBuildResult(
            program=prog,
            n_total=n_avg,
            processors=(
                pp.proc_default,
                pp.proc_attach("delays", np.asarray(delay_ticks) * 4),
            ),
            experiment_name="StorageChiRamsey",
            params={
                "fock_fq": fock_fq, "disp_pulse": disp_pulse,
                "x90_pulse": x90_pulse, "n_avg": n_avg,
                "st_therm_clks": st_therm_clks,
            },
            resolved_frequencies={attr.ro_el: ro_fq, attr.qb_el: qb_fq},
            bindings_snapshot=self._serialize_bindings(),
            builder_function="cQED_programs.storage_chi_ramsey",
            sweep_axes={"delays": np.asarray(delay_ticks) * 4},
        )

    def run(
        self,
        fock_fq: float,
        delay_ticks: np.ndarray | list[int],
        disp_pulse: str = "const_alpha",
        x90_pulse: str = "x90",
        n_avg: int = 200,
        st_therm_clks: int | None = None,
    ) -> RunResult:
        build = self.build_program(
            fock_fq=fock_fq, delay_ticks=delay_ticks,
            disp_pulse=disp_pulse, x90_pulse=x90_pulse, n_avg=n_avg,
            st_therm_clks=st_therm_clks,
        )
        result = self.run_program(
            build.program, n_total=build.n_total,
            processors=list(build.processors),
        )
        self.save_output(result.output, "storageChiRamsey")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, p0=None, **kw) -> AnalysisResult:
        delays = result.output.extract("delays")
        S = result.output.extract("S")
        mag = np.abs(S)

        P0_guess = float(mag.mean())
        A_guess = float((mag.max() - mag.min()) / 2)
        T2_guess = float(delays[-1]) / 3
        nbar_guess = 1.0
        # Estimate chi from FFT; delays in ns so chi in 1/ns (GHz)
        detrended = mag - mag.mean()
        dt = float(delays[1] - delays[0]) if len(delays) > 1 else 1.0
        fft_vals = np.abs(np.fft.rfft(detrended))
        fft_freqs = np.fft.rfftfreq(len(detrended), d=dt)
        if len(fft_vals) > 2:
            chi_guess = float(fft_freqs[1:][np.argmax(fft_vals[1:])])
        else:
            chi_guess = 1.0 / float(delays[-1])
        auto_p0 = [P0_guess, A_guess, T2_guess, nbar_guess, chi_guess, 0.0]

        fit = fit_and_wrap(delays, mag, chi_ramsey_model,
                           p0 if p0 is not None else auto_p0,
                           model_name="chi_ramsey", **kw)

        metrics: dict[str, Any] = {}
        if fit.params:
            metrics["chi"] = fit.params["chi"]
            metrics["nbar"] = fit.params["nbar"]
            metrics["T2_eff"] = fit.params["T2_eff"]

        analysis = AnalysisResult.from_run(result, fit=fit, metrics=metrics)

        if update_calibration and self.calibration_store and fit.params:
            self.guarded_calibration_commit(
                analysis=analysis,
                run_result=result,
                calibration_tag="storage_chi_ramsey",
                require_fit=False,
                required_metrics={"chi": (None, None)},
                apply_update=lambda: self.calibration_store.set_frequencies(
                    self.attr.st_el, chi=fit.params["chi"],
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
            y_fit = chi_ramsey_model(x_fit, p["P0"], p["A"], p["T2_eff"], p["nbar"], p["chi"], p["t0"])
            ax.plot(x_fit / 1e3, y_fit, "r-", lw=2,
                    label=build_fit_legend(analysis.fit))

        ax.set_xlabel("Delay (us)")
        ax.set_ylabel("Magnitude")
        ax.set_title("Storage Chi Ramsey")
        ax.legend(
            bbox_to_anchor=(1.05, 1), loc='upper left',
            fontsize=10, borderaxespad=0.0,
        )
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig


class StoragePhaseEvolution(ExperimentBase):
    """Storage state phase evolution tracking with SNAP gates."""

    def _build_impl(
        self,
        fock_probe_fqs: list[float] | np.ndarray,
        snap_list: list,
        delay_clks: np.ndarray | list[int],
        disp_alpha_pulse: str = "disp_alpha",
        disp_eps_pulse: str = "disp_epsilon",
        sel_r180_pulse: str = "sel_x180",
        n_avg: int = 200,
        st_therm_clks: int | None = None,
    ) -> ProgramBuildResult:
        attr = self.attr
        st_therm_clks = _resolve_storage_therm_clks(
            self, st_therm_clks, "StoragePhaseEvolution"
        )

        ro_fq = self._resolve_readout_frequency()
        qb_fq = self._resolve_qubit_frequency()

        # Convert absolute Fock probe frequencies to IFs relative to qubit LO
        lo_freq = self.get_qubit_lo()
        fock_probe_ifs = np.array([int(fq - lo_freq) for fq in fock_probe_fqs], dtype=int)
        fock0_if = int(qb_fq - lo_freq)

        prog = cQED_programs.phase_evolution_prog(
            attr.ro_el, attr.qb_el, attr.st_el,
            disp_alpha_pulse, disp_eps_pulse,
            sel_r180_pulse,
            fock0_if, fock_probe_ifs,
            np.asarray(delay_clks, dtype=int),
            snap_list,
            st_therm_clks, n_avg,
            bindings=self._bindings_or_none,
            readout=self.readout_handle,
        )

        return ProgramBuildResult(
            program=prog,
            n_total=n_avg,
            processors=(pp.proc_default,),
            experiment_name="StoragePhaseEvolution",
            params={
                "disp_alpha_pulse": disp_alpha_pulse,
                "disp_eps_pulse": disp_eps_pulse,
                "sel_r180_pulse": sel_r180_pulse, "n_avg": n_avg,
                "st_therm_clks": st_therm_clks,
            },
            resolved_frequencies={attr.ro_el: ro_fq, attr.qb_el: qb_fq},
            bindings_snapshot=self._serialize_bindings(),
            builder_function="cQED_programs.phase_evolution_prog",
            sweep_axes={},
        )

    def run(
        self,
        fock_probe_fqs: list[float] | np.ndarray,
        snap_list: list,
        delay_clks: np.ndarray | list[int],
        disp_alpha_pulse: str = "disp_alpha",
        disp_eps_pulse: str = "disp_epsilon",
        sel_r180_pulse: str = "sel_x180",
        n_avg: int = 200,
        st_therm_clks: int | None = None,
    ) -> RunResult:
        build = self.build_program(
            fock_probe_fqs=fock_probe_fqs, snap_list=snap_list,
            delay_clks=delay_clks, disp_alpha_pulse=disp_alpha_pulse,
            disp_eps_pulse=disp_eps_pulse, sel_r180_pulse=sel_r180_pulse,
            n_avg=n_avg, st_therm_clks=st_therm_clks,
        )
        result = self.run_program(
            build.program, n_total=build.n_total,
            processors=list(build.processors),
        )
        self.save_output(result.output, "storagePhaseEvolution")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        S = result.output.extract("S")
        metrics: dict[str, Any] = {}
        if S is not None:
            metrics["n_points"] = int(len(S))
        return AnalysisResult.from_run(result, metrics=metrics)

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        S = analysis.data.get("S")
        if S is None:
            return None

        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 5))
        else:
            fig = ax.figure

        ax.plot(np.angle(S), "o-", ms=4, label="Phase")
        ax.set_xlabel("Point Index")
        ax.set_ylabel("Phase (rad)")
        ax.set_title("Storage Phase Evolution")
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig
