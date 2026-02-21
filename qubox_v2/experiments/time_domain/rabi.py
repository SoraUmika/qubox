"""Rabi oscillation experiments."""
from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib.pyplot as plt

from ..experiment_base import ExperimentBase, create_clks_array
from ..result import AnalysisResult, FitResult
from ...analysis import post_process as pp
from ...analysis.fitting import fit_and_wrap, build_fit_legend
from ...analysis.cQED_models import power_rabi_model, temporal_rabi_model
from ...hardware.program_runner import RunResult
from ...programs import cQED_programs
from ...programs.macros.measure import measureMacro
from ...pulses.manager import MAX_AMPLITUDE


class TemporalRabi(ExperimentBase):
    """Qubit Rabi oscillations vs pulse duration."""

    def run(
        self,
        pulse: str,
        pulse_len_begin: int,
        pulse_len_end: int,
        dt: int = 4,
        pulse_gain: float = 1.0,
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        pulse_clks = create_clks_array(pulse_len_begin, pulse_len_end, dt, time_per_clk=4)

        self.set_standard_frequencies()

        prog = cQED_programs.temporal_rabi(
            attr.qb_el, pulse, pulse_clks, pulse_gain, attr.qb_therm_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("pulse_durations", pulse_clks * 4),
            ],
        )
        self.save_output(result.output, "temporalRabi")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, p0=None, **kw) -> AnalysisResult:
        durations = result.output.extract("pulse_durations")
        S = result.output.extract("S")
        mag = np.abs(S)

        # Estimate Rabi frequency from FFT
        dt = float(durations[1] - durations[0]) if len(durations) > 1 else 1.0
        fft_vals = np.abs(np.fft.rfft(mag - mag.mean()))
        fft_freqs = np.fft.rfftfreq(len(mag), d=dt)
        f_Rabi_guess = float(fft_freqs[1:][np.argmax(fft_vals[1:])]) if len(fft_vals) > 1 else 1e-3

        A_guess = float((mag.max() - mag.min()) / 2)
        T_decay_guess = float(durations[-1] - durations[0]) / 3
        offset_guess = float(mag.mean())
        auto_p0 = [A_guess, f_Rabi_guess, T_decay_guess, 0.0, offset_guess]

        fit = fit_and_wrap(durations, mag, temporal_rabi_model,
                           p0 if p0 is not None else auto_p0,
                           model_name="temporal_rabi", **kw)

        metrics: dict[str, Any] = {}
        if fit.params:
            metrics["f_Rabi"] = fit.params["f_Rabi"]
            metrics["T_decay"] = fit.params["T_decay"]
            if fit.params["f_Rabi"] != 0:
                metrics["pi_length"] = 1.0 / (2 * fit.params["f_Rabi"])

        analysis = AnalysisResult.from_run(result, fit=fit, metrics=metrics)

        if update_calibration and self.calibration_store and fit.params:
            if fit.params["f_Rabi"] != 0:
                self.calibration_store.set_pulse_calibration(
                    name="x180", pi_length=1.0 / (2 * fit.params["f_Rabi"]),
                )

        return analysis

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        durations = analysis.data.get("pulse_durations")
        S = analysis.data.get("S")
        if durations is None or S is None:
            return None

        mag = np.abs(S)
        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 5))
        else:
            fig = ax.figure

        ax.scatter(durations, mag, s=5, label="Data")
        if analysis.fit and analysis.fit.params:
            p = analysis.fit.params
            x_fit = np.linspace(durations.min(), durations.max(), 500)
            y_fit = temporal_rabi_model(x_fit, p["A"], p["f_Rabi"], p["T_decay"], p["phi"], p["offset"])
            ax.plot(x_fit, y_fit, "r-", lw=2,
                    label=build_fit_legend(analysis.fit))

        ax.set_xlabel("Pulse Duration (ns)")
        ax.set_ylabel("Magnitude")
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

    def run(
        self,
        max_gain: float,
        dg: float = 1e-3,
        op: str = "x180",
        length: int | None = None,
        truncate_clks: int | None = None,
        n_avg: int = 1000,
    ) -> RunResult:
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
        self.set_standard_frequencies()

        prog = cQED_programs.power_rabi(
            attr.qb_el, pulse_clock_len, gains, attr.qb_therm_clks,
            op, truncate_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("gains", gains),
            ],
        )
        self.save_output(result.output, "powerRabi")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, p0=None, **kw) -> AnalysisResult:
        gains = result.output.extract("gains")
        S = result.output.extract("S")
        mag = np.abs(S)

        A_guess = float((mag.max() - mag.min()) / 2)
        # g_pi: gain at first minimum (positive side)
        pos_mask = gains > 0
        if np.any(pos_mask):
            g_pi_guess = float(gains[pos_mask][np.argmin(mag[pos_mask])])
        else:
            g_pi_guess = float(gains[np.argmin(mag)])
        offset_guess = float(mag.mean())
        auto_p0 = [A_guess, g_pi_guess, offset_guess]

        fit = fit_and_wrap(gains, mag, power_rabi_model,
                           p0 if p0 is not None else auto_p0,
                           model_name="power_rabi", **kw)

        metrics: dict[str, Any] = {}
        if fit.params:
            metrics["g_pi"] = fit.params["g_pi"]

        analysis = AnalysisResult.from_run(result, fit=fit, metrics=metrics)

        if update_calibration and self.calibration_store and fit.params:
            self.calibration_store.set_pulse_calibration(
                name="x180", amplitude=fit.params["g_pi"],
            )

        return analysis

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        gains = analysis.data.get("gains")
        S = analysis.data.get("S")
        if gains is None or S is None:
            return None

        mag = np.abs(S)
        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 5))
        else:
            fig = ax.figure

        ax.scatter(gains, mag, s=5, label="Data")
        if analysis.fit and analysis.fit.params:
            p = analysis.fit.params
            x_fit = np.linspace(gains.min(), gains.max(), 500)
            y_fit = power_rabi_model(x_fit, p["A"], p["g_pi"], p["offset"])
            ax.plot(x_fit, y_fit, "r-", lw=2,
                    label=build_fit_legend(analysis.fit))
            ax.axvline(p["g_pi"], color="green", ls="--", lw=1, alpha=0.7,
                       label=f"pi-pulse gain = {p['g_pi']:.4f}")

        ax.set_xlabel("Gain")
        ax.set_ylabel("Magnitude")
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

    def run(
        self,
        rotations: list[str] | None = None,
        apply_avg: bool = False,
        n_shots: int = 1000,
    ) -> RunResult:
        if rotations is None:
            rotations = ["x180"]
        attr = self.attr
        self.set_standard_frequencies()

        prog = cQED_programs.sequential_qb_rotations(
            attr.qb_el, rotations, apply_avg, attr.qb_therm_clks, n_shots,
        )
        return self.run_program(
            prog, n_total=n_shots,
            processors=[
                pp.proc_default,
                pp.proc_attach("rotations", rotations),
            ],
        )
