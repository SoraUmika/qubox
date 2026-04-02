"""Fock-manifold-resolved experiments."""
from __future__ import annotations

import logging
from typing import Any, Union

import numpy as np
import matplotlib.pyplot as plt

from ..experiment_base import ExperimentBase, create_clks_array
from ..result import AnalysisResult, FitResult, ProgramBuildResult
from qubox_tools.algorithms import post_process as pp
from qubox_tools.fitting.routines import fit_and_wrap, build_fit_legend
from qubox_tools.fitting.cqed import (
    qubit_spec_model,
    T1_relaxation_model,
    T2_ramsey_model,
    power_rabi_model,
)
from ...hardware.program_runner import RunResult
from ...programs import api as cQED_programs
from ...tools.generators import validate_displacement_ops

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


class FockResolvedSpectroscopy(ExperimentBase):
    """Fock-resolved spectroscopy with post-selection.

    Probes qubit spectroscopy conditioned on photon number via
    selective pi-pulses and double post-selection.
    """

    def _build_impl(
        self,
        probe_fqs: list[float] | np.ndarray,
        *,
        state_prep: Any = None,
        sel_r180: str = "sel_x180",
        calibrate_ref_r180_S: bool = True,
        n_avg: int = 100,
        st_therm_clks: int | None = None,
        allow_default_state_prep: bool = False,
    ) -> ProgramBuildResult:
        attr = self.attr
        st_therm_clks = _resolve_storage_therm_clks(
            self, st_therm_clks, "FockResolvedSpectroscopy"
        )

        ro_fq = self._resolve_readout_frequency()
        qb_fq = self._resolve_qubit_frequency()

        if state_prep is None:
            if not allow_default_state_prep:
                raise ValueError(
                    "state_prep is required for FockResolvedSpectroscopy. "
                    "Provide an explicit notebook-defined preparation macro via state_prep=. "
                    "Temporary compatibility path: set allow_default_state_prep=True to use legacy no-op prep."
                )
            from qm.qua import wait
            def state_prep():
                wait(4)

        # Convert absolute RF probe frequencies to IFs relative to qubit LO
        lo_freq = self.get_qubit_lo()
        fock_ifs = np.array([int(fq - lo_freq) for fq in probe_fqs], dtype=int)
        qb_if = int(qb_fq - lo_freq)

        prog = cQED_programs.fock_resolved_spectroscopy(
            attr.qb_el, state_prep,
            qb_if, fock_ifs,
            sel_r180, st_therm_clks, n_avg,
            sel_r180_transfer_calibration=calibrate_ref_r180_S,
            bindings=self._bindings_or_none,
            readout=self.readout_handle,
        )

        return ProgramBuildResult(
            program=prog,
            n_total=n_avg,
            processors=(
                lambda out: pp.proc_default(out, targets=[("I_sel", "Q_sel", "")]),
                pp.proc_attach("frequencies", np.array(probe_fqs, dtype=float)),
            ),
            experiment_name="FockResolvedSpectroscopy",
            params={
                "sel_r180": sel_r180,
                "calibrate_ref_r180_S": calibrate_ref_r180_S,
                "n_avg": n_avg,
                "st_therm_clks": st_therm_clks,
            },
            resolved_frequencies={attr.ro_el: ro_fq, attr.qb_el: qb_fq},
            bindings_snapshot=self._serialize_bindings(),
            builder_function="cQED_programs.fock_resolved_spectroscopy",
            sweep_axes={"frequencies": np.array(probe_fqs, dtype=float)},
        )

    def run(
        self,
        probe_fqs: list[float] | np.ndarray,
        *,
        state_prep: Any = None,
        sel_r180: str = "sel_x180",
        calibrate_ref_r180_S: bool = True,
        n_avg: int = 100,
        st_therm_clks: int | None = None,
        allow_default_state_prep: bool = False,
    ) -> RunResult:
        build = self.build_program(
            probe_fqs=probe_fqs, state_prep=state_prep,
            sel_r180=sel_r180, calibrate_ref_r180_S=calibrate_ref_r180_S,
            n_avg=n_avg, st_therm_clks=st_therm_clks,
            allow_default_state_prep=allow_default_state_prep,
        )
        result = self.run_program(
            build.program, n_total=build.n_total,
            processors=list(build.processors),
        )
        self.save_output(result.output, "fockResolvedSpectroscopy")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        if update_calibration:
            logger.warning(
                "FockResolvedSpectroscopy.analyze(): update_calibration=True is not yet "
                "implemented. Use the CalibrationOrchestrator for calibration patching."
            )
        if "S" not in result.output:
            logger.warning(
                "FockResolvedSpectroscopy: 'S' not found in output. "
                "Available keys: %s. Check that run() processors specify the "
                "correct I/Q targets for this program.",
                list(result.output.keys()) if hasattr(result.output, 'keys') else '(unknown)',
            )
            return AnalysisResult.from_run(result, metrics={})
        S = result.output.extract("S")
        frequencies = result.output.extract("frequencies")
        metrics: dict[str, Any] = {}

        if S is not None:
            # S may be 2D (n_fock, n_freqs) or 1D
            if S.ndim == 2:
                n_fock = S.shape[0]
                fock_freqs: list[float] = []
                for n in range(n_fock):
                    mag = np.abs(S[n])
                    # Extract peak frequency via argmin (dip = resonance)
                    if frequencies is not None and len(frequencies) == mag.shape[-1]:
                        fock_freqs.append(float(frequencies[np.argmin(mag)]))
                    else:
                        fock_freqs.append(float(np.argmin(mag)))
                metrics["n_fock"] = n_fock
                metrics["fock_freqs"] = fock_freqs
            else:
                mag = np.abs(S)
                metrics["n_points"] = int(len(mag))

        return AnalysisResult.from_run(result, metrics=metrics)

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        S = analysis.data.get("S")
        if S is None:
            return None

        freqs = analysis.data.get("frequencies")
        has_freqs = freqs is not None and len(freqs) > 0
        x_vals = freqs / 1e6 if has_freqs else None
        x_label = "Frequency (MHz)" if has_freqs else "Point Index"

        if S.ndim == 2:
            n_fock = S.shape[0]
            fig, axes = plt.subplots(1, n_fock, figsize=(5 * n_fock, 4), squeeze=False)
            axes = axes[0]
            for n in range(n_fock):
                mag = np.abs(S[n])
                x = x_vals if has_freqs else np.arange(len(mag))
                axes[n].plot(x, mag, "o-", ms=3)
                axes[n].set_title(f"Fock |{n}>")
                axes[n].set_xlabel(x_label)
                axes[n].set_ylabel("Magnitude")
                axes[n].grid(True, alpha=0.3)
        else:
            if ax is None:
                fig, ax = plt.subplots(figsize=(10, 5))
            else:
                fig = ax.figure
            mag = np.abs(S)
            x = x_vals if has_freqs else np.arange(len(mag))
            ax.plot(x, mag, "o-", ms=3)
            ax.set_xlabel(x_label)
            ax.set_ylabel("Magnitude")
            ax.set_title("Fock-Resolved Spectroscopy")
            ax.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.show()
        return fig


class FockResolvedT1(ExperimentBase):
    """T1 relaxation measurement in individual Fock manifolds."""

    def _build_impl(
        self,
        fock_fqs: list[float] | np.ndarray | None = None,
        fock_disps: list[str] | None = None,
        delay_end: int = 40000,
        dt: int = 200,
        delay_begin: int = 4,
        sel_r180: str = "sel_x180",
        n_avg: int = 1000,
        st_therm_clks: int | None = None,
    ) -> ProgramBuildResult:
        attr = self.attr
        st_therm_clks = _resolve_storage_therm_clks(self, st_therm_clks, "FockResolvedT1")

        if fock_fqs is None:
            if attr.fock_fqs is None:
                raise ValueError(
                    "fock_fqs not provided and not found in cqed_params.json. "
                    "Run NumSplittingSpectroscopy first."
                )
            fock_fqs = attr.fock_fqs

        if fock_disps is None:
            fock_disps = [f"disp_n{n}" for n in range(len(fock_fqs))]

        # ---- Fail-fast: verify displacement ops are registered ----
        missing = validate_displacement_ops(self.pulse_mgr, attr.st_el, fock_disps)
        if missing:
            raise RuntimeError(
                f"Missing displacement pulses on element {attr.st_el!r}: {missing}. "
                f"Register them first via:\n"
                f"  from qubox_v2.tools.generators import ensure_displacement_ops\n"
                f"  ensure_displacement_ops(session.pulse_mgr, element={attr.st_el!r}, n_max={len(fock_fqs)})\n"
                f"  session.burn_pulses()"
            )

        delay_clks = create_clks_array(delay_begin, delay_end, dt, time_per_clk=4)

        ro_fq = self._resolve_readout_frequency()
        qb_fq = self._resolve_qubit_frequency()

        # Convert absolute Fock frequencies to IFs relative to qubit LO
        lo_freq = self.get_qubit_lo()
        fock_ifs = np.array([int(fq - lo_freq) for fq in fock_fqs], dtype=int)

        prog = cQED_programs.fock_resolved_T1_relaxation(
            attr.qb_el, attr.st_el,
            fock_disps, fock_ifs,
            sel_r180, delay_clks,
            st_therm_clks, n_avg,
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
            experiment_name="FockResolvedT1",
            params={
                "delay_end": delay_end, "dt": dt, "delay_begin": delay_begin,
                "sel_r180": sel_r180, "n_avg": n_avg,
                "st_therm_clks": st_therm_clks,
            },
            resolved_frequencies={attr.ro_el: ro_fq, attr.qb_el: qb_fq},
            bindings_snapshot=self._serialize_bindings(),
            builder_function="cQED_programs.fock_resolved_T1_relaxation",
            sweep_axes={"delays": delay_clks * 4},
        )

    def run(
        self,
        fock_fqs: list[float] | np.ndarray | None = None,
        fock_disps: list[str] | None = None,
        delay_end: int = 40000,
        dt: int = 200,
        delay_begin: int = 4,
        sel_r180: str = "sel_x180",
        n_avg: int = 1000,
        st_therm_clks: int | None = None,
    ) -> RunResult:
        build = self.build_program(
            fock_fqs=fock_fqs, fock_disps=fock_disps,
            delay_end=delay_end, dt=dt, delay_begin=delay_begin,
            sel_r180=sel_r180, n_avg=n_avg, st_therm_clks=st_therm_clks,
        )
        result = self.run_program(
            build.program, n_total=build.n_total,
            processors=list(build.processors),
        )
        self.save_output(result.output, "fockResolvedT1")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, p0=None, **kw) -> AnalysisResult:
        if update_calibration:
            logger.warning(
                "FockResolvedT1.analyze(): update_calibration=True is not yet "
                "implemented. Use the CalibrationOrchestrator for calibration patching."
            )
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

    def _build_impl(
        self,
        fock_fqs: list[float] | np.ndarray | None = None,
        detunings: list[float] | np.ndarray | None = None,
        disps: list[str] | None = None,
        delay_end: int = 40000,
        dt: int = 100,
        delay_begin: int = 4,
        sel_r90: str = "sel_x90",
        n_avg: int = 1000,
        st_therm_clks: int | None = None,
    ) -> ProgramBuildResult:
        attr = self.attr
        st_therm_clks = _resolve_storage_therm_clks(
            self, st_therm_clks, "FockResolvedRamsey"
        )

        if fock_fqs is None:
            if attr.fock_fqs is None:
                raise ValueError(
                    "fock_fqs not provided and not found in cqed_params.json. "
                    "Run NumSplittingSpectroscopy first."
                )
            fock_fqs = attr.fock_fqs

        if detunings is None:
            detunings = [0.2e6]

        if disps is None:
            disps = [f"disp_n{n}" for n in range(len(fock_fqs))]

        # ---- Fail-fast: verify displacement ops are registered ----
        missing = validate_displacement_ops(self.pulse_mgr, attr.st_el, disps)
        if missing:
            raise RuntimeError(
                f"Missing displacement pulses on element {attr.st_el!r}: {missing}. "
                f"Register them first via:\n"
                f"  from qubox_v2.tools.generators import ensure_displacement_ops\n"
                f"  ensure_displacement_ops(session.pulse_mgr, element={attr.st_el!r}, n_max={len(fock_fqs)})\n"
                f"  session.burn_pulses()"
            )

        delay_clks = create_clks_array(delay_begin, delay_end, dt, time_per_clk=4)

        ro_fq = self._resolve_readout_frequency()
        qb_fq = self._resolve_qubit_frequency()

        # Convert absolute Fock frequencies to IFs relative to qubit LO
        lo_freq = self.get_qubit_lo()
        fock_ifs = np.array([int(fq - lo_freq) for fq in fock_fqs], dtype=int)

        prog = cQED_programs.fock_resolved_qb_ramsey(
            attr.qb_el, attr.st_el,
            fock_ifs, np.asarray(detunings),
            disps, sel_r90, delay_clks,
            st_therm_clks, n_avg,
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
            experiment_name="FockResolvedRamsey",
            params={
                "delay_end": delay_end, "dt": dt, "delay_begin": delay_begin,
                "sel_r90": sel_r90, "n_avg": n_avg,
                "st_therm_clks": st_therm_clks,
            },
            resolved_frequencies={attr.ro_el: ro_fq, attr.qb_el: qb_fq},
            bindings_snapshot=self._serialize_bindings(),
            builder_function="cQED_programs.fock_resolved_qb_ramsey",
            sweep_axes={"delays": delay_clks * 4},
        )

    def run(
        self,
        fock_fqs: list[float] | np.ndarray | None = None,
        detunings: list[float] | np.ndarray | None = None,
        disps: list[str] | None = None,
        delay_end: int = 40000,
        dt: int = 100,
        delay_begin: int = 4,
        sel_r90: str = "sel_x90",
        n_avg: int = 1000,
        st_therm_clks: int | None = None,
    ) -> RunResult:
        build = self.build_program(
            fock_fqs=fock_fqs, detunings=detunings, disps=disps,
            delay_end=delay_end, dt=dt, delay_begin=delay_begin,
            sel_r90=sel_r90, n_avg=n_avg, st_therm_clks=st_therm_clks,
        )
        result = self.run_program(
            build.program, n_total=build.n_total,
            processors=list(build.processors),
        )
        self.save_output(result.output, "fockResolvedRamsey")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, p0=None, **kw) -> AnalysisResult:
        if update_calibration:
            logger.warning(
                "FockResolvedRamsey.analyze(): update_calibration=True is not yet "
                "implemented. Use the CalibrationOrchestrator for calibration patching."
            )
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

    def _build_impl(
        self,
        fock_fqs: list[float] | np.ndarray | None = None,
        gains: list[float] | np.ndarray | None = None,
        sel_qb_pulse: str = "sel_x180",
        disp_n_list: list[str] | None = None,
        n_avg: int = 1000,
        st_therm_clks: int | None = None,
    ) -> ProgramBuildResult:
        attr = self.attr
        st_therm_clks = _resolve_storage_therm_clks(
            self, st_therm_clks, "FockResolvedPowerRabi"
        )

        ro_fq = self._resolve_readout_frequency()
        qb_fq = self._resolve_qubit_frequency()

        if fock_fqs is None:
            if attr.fock_fqs is None:
                raise ValueError(
                    "fock_fqs not provided and not found in cqed_params.json. "
                    "Run NumSplittingSpectroscopy first."
                )
            fock_fqs = attr.fock_fqs

        if gains is None:
            gains = np.linspace(0, 1.5, 50)

        if disp_n_list is None:
            disp_n_list = [f"disp_n{n}" for n in range(len(fock_fqs))]

        # ---- Fail-fast: verify displacement ops are registered ----
        missing = validate_displacement_ops(self.pulse_mgr, attr.st_el, disp_n_list)
        if missing:
            raise RuntimeError(
                f"Missing displacement pulses on element {attr.st_el!r}: {missing}. "
                f"Register them first via:\n"
                f"  from qubox_v2.tools.generators import ensure_displacement_ops\n"
                f"  ensure_displacement_ops(session.pulse_mgr, element={attr.st_el!r}, n_max={len(fock_fqs)})\n"
                f"  session.burn_pulses()"
            )

        # Convert absolute Fock frequencies to IFs relative to qubit LO
        lo_freq = self.get_qubit_lo()
        fock_ifs = np.array([int(fq - lo_freq) for fq in fock_fqs], dtype=int)

        prog = cQED_programs.fock_resolved_power_rabi(
            attr.qb_el, attr.st_el,
            np.asarray(gains), disp_n_list,
            fock_ifs, sel_qb_pulse,
            st_therm_clks, n_avg,
            bindings=self._bindings_or_none,
            readout=self.readout_handle,
        )

        return ProgramBuildResult(
            program=prog,
            n_total=n_avg,
            processors=(
                pp.proc_default,
                pp.proc_attach("gains", np.asarray(gains)),
            ),
            experiment_name="FockResolvedPowerRabi",
            params={
                "sel_qb_pulse": sel_qb_pulse, "n_avg": n_avg,
                "st_therm_clks": st_therm_clks,
            },
            resolved_frequencies={attr.ro_el: ro_fq, attr.qb_el: qb_fq},
            bindings_snapshot=self._serialize_bindings(),
            builder_function="cQED_programs.fock_resolved_power_rabi",
            sweep_axes={"gains": np.asarray(gains)},
        )

    def run(
        self,
        fock_fqs: list[float] | np.ndarray | None = None,
        gains: list[float] | np.ndarray | None = None,
        sel_qb_pulse: str = "sel_x180",
        disp_n_list: list[str] | None = None,
        n_avg: int = 1000,
        st_therm_clks: int | None = None,
    ) -> RunResult:
        build = self.build_program(
            fock_fqs=fock_fqs, gains=gains,
            sel_qb_pulse=sel_qb_pulse, disp_n_list=disp_n_list,
            n_avg=n_avg, st_therm_clks=st_therm_clks,
        )
        result = self.run_program(
            build.program, n_total=build.n_total,
            processors=list(build.processors),
        )
        self.save_output(result.output, "fockResolvedPowerRabi")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, p0=None, **kw) -> AnalysisResult:
        if update_calibration:
            logger.warning(
                "FockResolvedPowerRabi.analyze(): update_calibration=True is not yet "
                "implemented. Use the CalibrationOrchestrator for calibration patching."
            )
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
