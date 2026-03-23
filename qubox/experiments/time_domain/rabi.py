"""Rabi oscillation experiments."""
from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib.pyplot as plt

from ..experiment_base import ExperimentBase, create_clks_array
from ..result import AnalysisResult, FitResult, ProgramBuildResult
from ...analysis import post_process as pp
from ...analysis.fitting import fit_and_wrap, build_fit_legend
from ...analysis.cQED_models import power_rabi_model, temporal_rabi_model
from ...analysis.analysis_tools import project_complex_to_line_real
from ...hardware.program_runner import RunResult
from ...programs import api as cQED_programs
from ...programs.circuit_runner import CircuitRunner, make_power_rabi_circuit
from ...programs.macros.measure import measureMacro
from ...programs.measurement import try_build_readout_snapshot_from_macro
from ...pulses.manager import MAX_AMPLITUDE


def _resolve_qb_therm_clks(exp: ExperimentBase, value: int | None, owner: str) -> int:
    return int(exp.resolve_override_or_attr(
        value=value,
        attr_name="qb_therm_clks",
        owner=owner,
        cast=int,
    ))


def _power_rabi_projected_model(g, A, g_pi, phi, offset):
    return offset + A * np.cos(np.pi * (g / g_pi) + phi)


_power_rabi_projected_model.equation = r'$y = offset + A\cos\!\left(\pi\,g/g_{\pi} + \phi\right)$'


class TemporalRabi(ExperimentBase):
    """Qubit Rabi oscillations vs pulse duration."""

    def _build_impl(
        self,
        pulse: str,
        pulse_len_begin: int,
        pulse_len_end: int,
        dt: int = 4,
        pulse_gain: float = 1.0,
        n_avg: int = 1000,
        qb_therm_clks: int | None = None,
    ) -> ProgramBuildResult:
        attr = self.attr
        pulse_clks = create_clks_array(pulse_len_begin, pulse_len_end, dt, time_per_clk=4)
        qb_therm_clks = _resolve_qb_therm_clks(self, qb_therm_clks, "TemporalRabi")

        ro_fq = self._resolve_readout_frequency()
        qb_fq = self._resolve_qubit_frequency()

        prog = cQED_programs.temporal_rabi(
            pulse, pulse_clks, pulse_gain, qb_therm_clks, n_avg,
            qb_el=attr.qb_el,
            bindings=self._bindings_or_none,
        )

        return ProgramBuildResult(
            program=prog,
            n_total=n_avg,
            processors=(
                pp.proc_default,
                pp.proc_attach("pulse_durations", pulse_clks * 4),
            ),
            experiment_name="TemporalRabi",
            params={
                "pulse": pulse, "pulse_len_begin": pulse_len_begin,
                "pulse_len_end": pulse_len_end, "dt": dt,
                "pulse_gain": pulse_gain, "n_avg": n_avg,
                "qb_therm_clks": qb_therm_clks,
            },
            resolved_frequencies={attr.ro_el: ro_fq, attr.qb_el: qb_fq},
            bindings_snapshot=self._serialize_bindings(),
            builder_function="cQED_programs.temporal_rabi",
            sweep_axes={"pulse_durations": pulse_clks * 4},
            measure_macro_state=try_build_readout_snapshot_from_macro(),
        )

    def run(
        self,
        pulse: str,
        pulse_len_begin: int,
        pulse_len_end: int,
        dt: int = 4,
        pulse_gain: float = 1.0,
        n_avg: int = 1000,
        qb_therm_clks: int | None = None,
    ) -> RunResult:
        build = self.build_program(
            pulse=pulse, pulse_len_begin=pulse_len_begin,
            pulse_len_end=pulse_len_end, dt=dt,
            pulse_gain=pulse_gain, n_avg=n_avg,
            qb_therm_clks=qb_therm_clks,
        )
        result = self.run_program(
            build.program, n_total=build.n_total,
            processors=list(build.processors),
        )
        self._run_params = {"op": pulse}
        self.save_output(result.output, "temporalRabi")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, p0=None, **kw) -> AnalysisResult:
        durations = result.output.extract("pulse_durations")
        S = result.output.extract("S")
        projected_S, proj_center, proj_direction = project_complex_to_line_real(S)
        min_r2 = float(kw.pop("min_r2", 0.80))

        # --- Auto guess p0 from projected signal ---
        dt = float(durations[1] - durations[0]) if len(durations) > 1 else 1.0
        fft_vals = np.abs(np.fft.rfft(projected_S - projected_S.mean()))
        fft_freqs = np.fft.rfftfreq(len(projected_S), d=dt)
        f_Rabi_guess = float(fft_freqs[1:][np.argmax(fft_vals[1:])]) if len(fft_vals) > 1 and len(fft_freqs) > 1 else 1e-3

        A_guess = float((projected_S.max() - projected_S.min()) / 2)
        T_decay_guess = float(durations[-1] - durations[0]) / 3 if len(durations) > 1 else 100.0
        offset_guess = float(projected_S.mean())
        phi_guess = 0.0

        auto_p0 = [A_guess, f_Rabi_guess, T_decay_guess, phi_guess, offset_guess]
        p0_used = p0 if p0 is not None else auto_p0

        fit = fit_and_wrap(
            durations,
            projected_S,
            temporal_rabi_model,
            p0_used,
            model_name="temporal_rabi",
            **kw,
        )

        metrics: dict[str, Any] = {}
        if fit.params:
            metrics["f_Rabi"] = fit.params["f_Rabi"]
            metrics["T_decay"] = fit.params["T_decay"]
            if fit.params["f_Rabi"] != 0:
                metrics["pi_length"] = 1.0 / (2 * fit.params["f_Rabi"])

        analysis = AnalysisResult.from_run(
            result,
            fit=fit,
            metrics=metrics,
            metadata={
                "p0_used": {
                    "A": float(p0_used[0]),
                    "f_Rabi": float(p0_used[1]),
                    "T_decay": float(p0_used[2]),
                    "phi": float(p0_used[3]),
                    "offset": float(p0_used[4]),
                },
                "fit_params_summary": (
                    {k: float(v) for k, v in fit.params.items()} if fit.params else {}
                ),
                "signal_projection": {
                    "center_real": float(np.real(proj_center)),
                    "center_imag": float(np.imag(proj_center)),
                    "direction_real": float(np.real(proj_direction)),
                    "direction_imag": float(np.imag(proj_direction)),
                },
            },
        )

        # Persist projected signal for plotting/debugging
        analysis.data["projected_S"] = projected_S

        if update_calibration and self.calibration_store and fit.params:
            if fit.params["f_Rabi"] != 0:
                target_op = self._run_params.get("op") if hasattr(self, "_run_params") else "ge_ref_r180"
                sweep_lo = float(np.min(durations))
                sweep_hi = float(np.max(durations))
                self.guarded_calibration_commit(
                    analysis=analysis,
                    run_result=result,
                    calibration_tag=f"temporal_rabi_{target_op}",
                    min_r2=min_r2,
                    required_metrics={"pi_length": (sweep_lo, sweep_hi)},
                    extra_metadata={"sweep_min_ns": sweep_lo, "sweep_max_ns": sweep_hi, "target_op": target_op},
                    apply_update=lambda: self.calibration_store.set_pulse_calibration(
                        name=target_op, pi_length=1.0 / (2 * fit.params["f_Rabi"]),
                    ),
                )

        return analysis

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        durations = analysis.data.get("pulse_durations")
        ydata = analysis.data.get("projected_S")
        if durations is None or ydata is None:
            return None
        ydata = np.asarray(ydata, dtype=float)
        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 5))
        else:
            fig = ax.figure

        ax.scatter(durations, ydata, s=5, label="Data")
        if analysis.fit and analysis.fit.params:
            p = analysis.fit.params
            x_fit = np.linspace(durations.min(), durations.max(), 500)
            y_fit = temporal_rabi_model(x_fit, p["A"], p["f_Rabi"], p["T_decay"], p["phi"], p["offset"])
            ax.plot(x_fit, y_fit, "r-", lw=2,
                    label=build_fit_legend(analysis.fit))

        ax.set_xlabel("Pulse Duration (ns)")
        ax.set_ylabel("Projected Signal (a.u.)")
        ax.set_title("Temporal Rabi")
        ax.legend(
            bbox_to_anchor=(1.05, 1), loc='upper left',
            fontsize=10, borderaxespad=0.0,
        )
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig


class PowerRabi(ExperimentBase):
    """Qubit Rabi oscillations vs amplitude/gain."""

    def _build_impl(
        self,
        max_gain: float,
        dg: float = 1e-3,
        op: str = "ge_ref_r180",
        length: int | None = None,
        truncate_clks: int | None = None,
        n_avg: int = 1000,
        qb_therm_clks: int | None = None,
        *,
        use_circuit_runner: bool = True,
    ) -> ProgramBuildResult:
        attr = self.attr
        gains = np.arange(-max_gain, max_gain + 1e-12, dg, dtype=float)

        pulse_info = self.pulse_mgr.get_pulseOp_by_element_op(attr.qb_el, op)
        if not length:
            length = pulse_info.length

        I_wf, Q_wf = pulse_info.I_wf, pulse_info.Q_wf
        peak_amp = max(np.abs(I_wf).max(), np.abs(Q_wf).max())
        if peak_amp * max_gain > MAX_AMPLITUDE:
            raise ValueError(
                f"Max gain {max_gain} too high for pulse {op} "
                f"(peak={peak_amp:.3f}, max={MAX_AMPLITUDE/peak_amp:.3f})"
            )

        pulse_clock_len = round(length / 4)
        ro_fq = self._resolve_readout_frequency()
        qb_fq = self._resolve_qubit_frequency()
        qb_therm_clks = _resolve_qb_therm_clks(self, qb_therm_clks, "PowerRabi")

        builder_function = "cQED_programs.power_rabi"
        if use_circuit_runner:
            try:
                circuit, sweep = make_power_rabi_circuit(
                    qb_el=attr.qb_el,
                    qb_therm_clks=int(qb_therm_clks),
                    pulse_clock_len=pulse_clock_len,
                    n_avg=n_avg,
                    op=op,
                    truncate_clks=truncate_clks,
                    gains=gains,
                )
                compiled = CircuitRunner(self._ctx).compile(circuit, sweep=sweep)
                prog = compiled.program
                builder_function = "CircuitRunner.power_rabi"
            except Exception:
                prog = cQED_programs.power_rabi(
                    pulse_clock_len, gains, qb_therm_clks,
                    op, truncate_clks, n_avg,
                    qb_el=attr.qb_el,
                    bindings=self._bindings_or_none,
                )
        else:
            prog = cQED_programs.power_rabi(
                pulse_clock_len, gains, qb_therm_clks,
                op, truncate_clks, n_avg,
                qb_el=attr.qb_el,
                bindings=self._bindings_or_none,
            )

        return ProgramBuildResult(
            program=prog,
            n_total=n_avg,
            processors=(
                pp.proc_default,
                pp.proc_attach("gains", gains),
            ),
            experiment_name="PowerRabi",
            params={
                "max_gain": max_gain, "dg": dg, "op": op,
                "length": length, "truncate_clks": truncate_clks,
                "n_avg": n_avg, "qb_therm_clks": qb_therm_clks,
            },
            resolved_frequencies={attr.ro_el: ro_fq, attr.qb_el: qb_fq},
            bindings_snapshot=self._serialize_bindings(),
            builder_function=builder_function,
            sweep_axes={"gains": gains},
            measure_macro_state=try_build_readout_snapshot_from_macro(),
        )

    def run(
        self,
        max_gain: float,
        dg: float = 1e-3,
        op: str = "ge_ref_r180",
        length: int | None = None,
        truncate_clks: int | None = None,
        n_avg: int = 1000,
        qb_therm_clks: int | None = None,
        *,
        use_circuit_runner: bool = True,
    ) -> RunResult:
        build = self.build_program(
            max_gain=max_gain, dg=dg, op=op,
            length=length, truncate_clks=truncate_clks, n_avg=n_avg,
            qb_therm_clks=qb_therm_clks,
            use_circuit_runner=use_circuit_runner,
        )
        result = self.run_program(
            build.program, n_total=build.n_total,
            processors=list(build.processors),
        )
        self._run_params = {"op": op}
        self.save_output(result.output, "powerRabi")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, p0=None, **kw) -> AnalysisResult:
        gains = result.output.extract("gains")
        S = result.output.extract("S")
        projected_S, proj_center, proj_direction = project_complex_to_line_real(S)

        # --- Auto guess p0 from projected signal ---
        A_guess = float((projected_S.max() - projected_S.min()) / 2)

        pos_mask = gains > 0
        if np.any(pos_mask):
            g_pi_guess = float(gains[pos_mask][np.argmin(projected_S[pos_mask])])
        else:
            g_pi_guess = float(gains[np.argmin(projected_S)])

        offset_guess = float(projected_S.mean())

        auto_p0 = [A_guess, g_pi_guess, 0.0, offset_guess]
        candidate_p0s: list[list[float]] = []
        if p0 is not None:
            if len(p0) >= 4:
                candidate_p0s.append([float(p0[0]), float(p0[1]), float(p0[2]), float(p0[3])])
            elif len(p0) == 3:
                candidate_p0s.append([float(p0[0]), float(p0[1]), 0.0, float(p0[2])])
        candidate_p0s.append([float(auto_p0[0]), float(auto_p0[1]), float(auto_p0[2]), float(auto_p0[3])])

        best_fit = None
        best_p0 = candidate_p0s[0]
        best_score = float("-inf")
        for candidate in candidate_p0s:
            fit_try = fit_and_wrap(
                gains,
                projected_S,
                _power_rabi_projected_model,
                candidate,
                model_name="power_rabi_projected",
                **kw,
            )
            r2 = getattr(fit_try, "r_squared", None)
            score = float(r2) if isinstance(r2, (int, float)) else float("-inf")
            if fit_try.params and score >= best_score:
                best_fit = fit_try
                best_p0 = candidate
                best_score = score

        if best_fit is None:
            best_fit = fit_and_wrap(
                gains,
                projected_S,
                _power_rabi_projected_model,
                candidate_p0s[-1],
                model_name="power_rabi_projected",
                **kw,
            )
            best_p0 = candidate_p0s[-1]

        fit = best_fit
        p0_used = best_p0

        metrics: dict[str, Any] = {}
        if fit.params:
            metrics["g_pi"] = fit.params["g_pi"]
            metrics["A"] = fit.params["A"]
            metrics["phi"] = fit.params["phi"]
            metrics["offset"] = fit.params["offset"]

        metadata: dict[str, Any] = {
            "calibration_kind": "pi_amp",
            "target_op": (self._run_params.get("op") if hasattr(self, "_run_params") else "ge_ref_r180"),
            "units": {"g_pi": "a.u."},
            "p0_used": {
                "A": float(p0_used[0]),
                "g_pi": float(p0_used[1]),
                "phi": float(p0_used[2]),
                "offset": float(p0_used[3]),
            },
            "fit_params_summary": (
                {k: float(v) for k, v in fit.params.items()} if fit.params else {}
            ),
        }

        if update_calibration and fit.params:
            target_op = metadata["target_op"]
            g_pi = float(fit.params["g_pi"])
            current_amp = None
            if self.calibration_store is not None:
                current_cal = self.calibration_store.get_pulse_calibration(target_op)
                if current_cal is not None and getattr(current_cal, "amplitude", None) is not None:
                    current_amp = float(current_cal.amplitude)

            patched_amp = g_pi if current_amp is None else (current_amp * g_pi)
            metadata["amplitude_patch_mode"] = (
                "absolute_g_pi_fallback" if current_amp is None else "scale_current_by_g_pi"
            )
            metadata["amplitude_patch_current"] = current_amp
            metadata["amplitude_patch_g_pi"] = g_pi
            metadata["amplitude_patch_value"] = patched_amp
            metadata.setdefault("proposed_patch_ops", []).append(
                {
                    "op": "SetCalibration",
                    "payload": {
                        "path": f"pulse_calibrations.{target_op}.amplitude",
                        "value": patched_amp,
                    },
                }
            )
            metadata.setdefault("proposed_patch_ops", []).append(
                {
                    "op": "TriggerPulseRecompile",
                    "payload": {"include_volatile": True},
                }
            )

        metadata["signal_projection"] = {
            "center_real": float(np.real(proj_center)),
            "center_imag": float(np.imag(proj_center)),
            "direction_real": float(np.real(proj_direction)),
            "direction_imag": float(np.imag(proj_direction)),
        }

        analysis = AnalysisResult.from_run(result, fit=fit, metrics=metrics, metadata=metadata)
        analysis.data["projected_S"] = projected_S

        return analysis

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        gains = analysis.data.get("gains")
        ydata = analysis.data.get("projected_S")
        if gains is None or ydata is None:
            return None

        if ax is None:
            fig, ax = plt.subplots(figsize=(12, 5))
        else:
            fig = ax.figure

        ax.scatter(gains, ydata, s=5, label="Data")
        if analysis.fit and analysis.fit.params:
            p = analysis.fit.params
            x_fit = np.linspace(gains.min(), gains.max(), 500)
            y_fit = _power_rabi_projected_model(x_fit, p["A"], p["g_pi"], p["phi"], p["offset"])
            ax.plot(x_fit, y_fit, "r-", lw=2,
                    label=build_fit_legend(analysis.fit))
            ax.axvline(p["g_pi"], color="green", ls="--", lw=1, alpha=0.7,
                       label=f"pi-pulse gain = {p['g_pi']:.4f}")

        ax.set_xlabel("Qubit Amplitude")
        ax.set_ylabel("Projected Signal (a.u.)")
        ax.set_title("Power Rabi")
        ax.legend(
            bbox_to_anchor=(1.05, 1), loc='upper left',
            fontsize=10, borderaxespad=0.0,
        )
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig


class SequentialQubitRotations(ExperimentBase):
    """Apply a sequence of qubit rotation gates and measure."""

    def _build_impl(
        self,
        rotations: list[str] | None = None,
        apply_avg: bool = False,
        n_shots: int = 1000,
        qb_therm_clks: int | None = None,
    ) -> ProgramBuildResult:
        if rotations is None:
            rotations = ["x180"]
        attr = self.attr
        qb_therm_clks = _resolve_qb_therm_clks(self, qb_therm_clks, "SequentialQubitRotations")

        ro_fq = self._resolve_readout_frequency()
        qb_fq = self._resolve_qubit_frequency()

        prog = cQED_programs.sequential_qb_rotations(
            attr.qb_el, rotations, apply_avg, qb_therm_clks, n_shots,
            bindings=self._bindings_or_none,
        )

        return ProgramBuildResult(
            program=prog,
            n_total=n_shots,
            processors=(
                pp.proc_default,
                pp.proc_attach("rotations", rotations),
            ),
            experiment_name="SequentialQubitRotations",
            params={
                "rotations": rotations, "apply_avg": apply_avg,
                "n_shots": n_shots, "qb_therm_clks": qb_therm_clks,
            },
            resolved_frequencies={attr.ro_el: ro_fq, attr.qb_el: qb_fq},
            bindings_snapshot=self._serialize_bindings(),
            builder_function="cQED_programs.sequential_qb_rotations",
        )

    def run(
        self,
        rotations: list[str] | None = None,
        apply_avg: bool = False,
        n_shots: int = 1000,
        qb_therm_clks: int | None = None,
    ) -> RunResult:
        build = self.build_program(
            rotations=rotations, apply_avg=apply_avg, n_shots=n_shots,
            qb_therm_clks=qb_therm_clks,
        )
        return self.run_program(
            build.program, n_total=build.n_total,
            processors=list(build.processors),
        )

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        S = result.output.extract("S")
        rotations = result.output.extract("rotations")
        metrics: dict[str, Any] = {"n_rotations": len(rotations) if rotations is not None else 0}
        return AnalysisResult.from_run(result, metrics=metrics)

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        S = analysis.data.get("S")
        if S is None:
            return None
        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 5))
        else:
            fig = ax.figure
        ax.plot(np.abs(S), "o-", ms=4)
        ax.set_xlabel("Rotation Index")
        ax.set_ylabel("Magnitude")
        ax.set_title("Sequential Qubit Rotations")
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig
