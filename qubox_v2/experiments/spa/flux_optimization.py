"""SPA flux and pump optimization experiments."""
from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import matplotlib.pyplot as plt

from ..experiment_base import ExperimentBase
from ..result import AnalysisResult
from ...analysis import post_process as pp
from ...analysis.output import Output
from ...hardware.program_runner import RunResult
from ...programs import cQED_programs


class SPAFluxOptimization(ExperimentBase):
    """Flux bias sweep with SPA readout at multiple probe frequencies.

    Loops over DC flux setpoints via the device manager and measures
    SPA-enhanced readout at each point.
    """

    def run(
        self,
        dc_list: list[float] | np.ndarray,
        sample_fqs: list[float] | np.ndarray,
        n_avg: int,
        *,
        odc_name: str = "octodac_bf",
        odc_param: str = "voltage5",
        step: float = 0.005,
        delay_s: float = 0.1,
        use_absolute_ro_freqs: bool = True,
        ro_depl_clks: int | None = None,
    ) -> RunResult:
        attr = self.attr
        dm = self.device_manager
        if dm is None:
            raise RuntimeError("DeviceManager not available for SPA optimization.")

        self.set_standard_frequencies()

        results_matrix = []
        for dc_val in dc_list:
            dm.ramp(odc_name, odc_param, dc_val, step=step, delay_s=delay_s)

            prog = cQED_programs.SPA_flux_optimization(
                attr.ro_el, sample_fqs,
                ro_depl_clks or attr.ro_therm_clks,
                n_avg,
            )
            rr = self.run_program(
                prog, n_total=n_avg,
                processors=[pp.proc_default, pp.proc_magnitude],
            )
            results_matrix.append(rr.output)

        output = Output({
            "dc_values": np.asarray(dc_list),
            "sample_fqs": np.asarray(sample_fqs),
            "results": results_matrix,
        })
        self.save_output(output, "SPAFluxOptimization")
        return RunResult(
            mode=rr.mode, output=output, sim_samples=None,
            metadata={"n_dc_points": len(dc_list)},
        )

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        dc_values = result.output.extract("dc_values")
        sample_fqs = result.output.extract("sample_fqs")
        results_list = result.output.get("results", [])
        metrics: dict[str, Any] = {}

        if dc_values is not None and sample_fqs is not None and results_list:
            # Build magnitude matrix (n_dc x n_freq)
            mag_matrix = []
            for out in results_list:
                mag = out.get("magnitude", None)
                if mag is not None:
                    mag_matrix.append(np.asarray(mag))
            if mag_matrix:
                mag_2d = np.array(mag_matrix)
                best_idx = np.unravel_index(np.argmax(mag_2d), mag_2d.shape)
                metrics["best_dc"] = float(dc_values[best_idx[0]])
                metrics["best_freq"] = float(sample_fqs[best_idx[1]])
                metrics["peak_magnitude"] = float(mag_2d[best_idx])
                metrics["n_dc_points"] = len(dc_values)
                metrics["n_freq_points"] = len(sample_fqs)

        return AnalysisResult.from_run(result, metrics=metrics)

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        dc_values = analysis.data.get("dc_values")
        sample_fqs = analysis.data.get("sample_fqs")
        results_list = analysis.data.get("results", [])
        if dc_values is None or sample_fqs is None or not results_list:
            return None

        mag_matrix = []
        for out in results_list:
            mag = out.get("magnitude", None)
            if mag is not None:
                mag_matrix.append(np.asarray(mag))
        if not mag_matrix:
            return None

        mag_2d = np.array(mag_matrix)
        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 6))
        else:
            fig = ax.figure

        im = ax.pcolormesh(
            np.asarray(sample_fqs) / 1e6, np.asarray(dc_values),
            mag_2d, shading="auto",
        )
        fig.colorbar(im, ax=ax, label="Magnitude")

        best_dc = analysis.metrics.get("best_dc")
        best_freq = analysis.metrics.get("best_freq")
        if best_dc is not None and best_freq is not None:
            ax.axhline(best_dc, color="r", ls="--", alpha=0.5)
            ax.axvline(best_freq / 1e6, color="r", ls="--", alpha=0.5)
            ax.plot(best_freq / 1e6, best_dc, "rx", ms=12, mew=2)

        ax.set_xlabel("Probe Frequency (MHz)")
        ax.set_ylabel("DC Flux Bias (V)")
        ax.set_title("SPA Flux Optimization")
        plt.tight_layout()
        plt.show()
        return fig


class SPAFluxOptimization2(ExperimentBase):
    """Advanced SPA flux optimization with automated peak-finding.

    Supports three modes:
    - 'sweep': basic DC sweep (like SPAFluxOptimization)
    - 'scout': wide initial sweep to find candidate peaks
    - 'refine': narrow scan around best peak
    - 'lock': iterative convergence to optimal flux point
    """

    def run(
        self,
        dc_list: list[float] | np.ndarray,
        sample_fqs: list[float] | np.ndarray,
        n_avg: int,
        *,
        odc_name: str = "octodac_bf",
        odc_param: str = "voltage5",
        step: float = 0.005,
        delay_s: float = 0.1,
        use_absolute_ro_freqs: bool = True,
        ro_depl_clks: int | None = None,
        mode: str = "sweep",
        scout_window: float = 0.20,
        scout_step: float = 0.01,
        refine_half_width: float = 0.03,
        refine_step: float = 0.002,
        peak_score_thresh: float = 8.0,
        lock_delta: float = 0.001,
        lock_gain: float = 0.75,
        lock_max_iters: int = 25,
        lock_min_delta: float = 1e-4,
        lock_loss_frac: float = 0.6,
        approach_direction: str = "up",
        approach_reset: float | None = None,
    ) -> RunResult:
        # For 'sweep' mode, delegate to the basic optimizer
        if mode == "sweep":
            basic = SPAFluxOptimization(self._ctx)
            return basic.run(
                dc_list, sample_fqs, n_avg,
                odc_name=odc_name, odc_param=odc_param,
                step=step, delay_s=delay_s,
                use_absolute_ro_freqs=use_absolute_ro_freqs,
                ro_depl_clks=ro_depl_clks,
            )

        # For advanced modes (scout/refine/lock), use the algorithms module
        from ...analysis.algorithms import (
            scout_windows, refine_around, lock_to_peak_3pt,
            peak_score_robust,
        )

        attr = self.attr
        dm = self.device_manager
        if dm is None:
            raise RuntimeError("DeviceManager not available for SPA optimization.")

        self.set_standard_frequencies()

        def _measure_at_dc(dc_val: float) -> float:
            """Take a single measurement at a given DC point."""
            dm.ramp(odc_name, odc_param, dc_val, step=step, delay_s=delay_s)
            prog = cQED_programs.SPA_flux_optimization(
                attr.ro_el, sample_fqs,
                ro_depl_clks or attr.ro_therm_clks, n_avg,
            )
            rr = self.run_program(
                prog, n_total=n_avg,
                processors=[pp.proc_default, pp.proc_magnitude],
            )
            # Return peak score as the scalar objective
            mag = rr.output.get("magnitude", np.array([0]))
            return float(np.max(mag))

        if mode == "scout":
            best_dc = scout_windows(
                _measure_at_dc, dc_list,
                window=scout_window, step=scout_step,
            )
        elif mode == "refine":
            center = float(dc_list[len(dc_list) // 2])
            best_dc = refine_around(
                _measure_at_dc, center,
                half_width=refine_half_width, step=refine_step,
            )
        elif mode == "lock":
            center = float(dc_list[len(dc_list) // 2])
            best_dc = lock_to_peak_3pt(
                _measure_at_dc, center,
                delta=lock_delta, gain=lock_gain,
                max_iters=lock_max_iters,
            )
        else:
            raise ValueError(f"Unknown mode '{mode}'. Use sweep/scout/refine/lock.")

        output = Output({
            "best_dc": best_dc,
            "mode": mode,
        })
        return RunResult(mode="run", output=output, sim_samples=None)

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        mode = result.output.get("mode", "sweep")
        metrics: dict[str, Any] = {"mode": mode}

        if mode == "sweep":
            # Delegate to SPAFluxOptimization.analyze
            basic = SPAFluxOptimization(self._ctx)
            return basic.analyze(result, update_calibration=update_calibration, **kw)

        best_dc = result.output.get("best_dc", None)
        if best_dc is not None:
            metrics["best_dc"] = float(best_dc)

        return AnalysisResult.from_run(result, metrics=metrics)

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        mode = analysis.metrics.get("mode", "sweep")
        if mode == "sweep":
            basic = SPAFluxOptimization(self._ctx)
            return basic.plot(analysis, ax=ax, **kwargs)

        best_dc = analysis.metrics.get("best_dc")
        if best_dc is None:
            return None

        if ax is None:
            fig, ax = plt.subplots(figsize=(6, 4))
        else:
            fig = ax.figure

        ax.axhline(best_dc, color="r", lw=2, label=f"best DC = {best_dc:.5f} V")
        ax.set_ylabel("DC Flux Bias (V)")
        ax.set_title(f"SPA Flux Optimization ({mode})")
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig


class SPAPumpFrequencyOptimization(ExperimentBase):
    """SPA pump power × frequency 2-D optimization.

    Sweeps pump power and detuning coordinates while evaluating
    either assignment fidelity or butterfly QND metric at each point.
    """

    def run(
        self,
        readout_op: str,
        drive_frequency: float,
        pump_powers: list[float] | np.ndarray,
        pump_detunings: list[float] | np.ndarray,
        r180: str = "x180",
        samples_per_run: int = 25_000,
        metric: str = "assignment_fidelity",
        assignment_kwargs: dict[str, Any] | None = None,
        butterfly_kwargs: dict[str, Any] | None = None,
    ) -> RunResult:
        attr = self.attr
        dm = self.device_manager
        if dm is None:
            raise RuntimeError("DeviceManager not available for SPA optimization.")

        self.set_standard_frequencies()

        results = np.full((len(pump_powers), len(pump_detunings)), np.nan)

        from ..calibration.readout import (
            ReadoutGEDiscrimination,
            ReadoutButterflyMeasurement,
        )

        for i, power in enumerate(pump_powers):
            dm.get("signalcore_pump").do_set_power(power)
            for j, detune in enumerate(pump_detunings):
                dm.get("signalcore_pump").do_set_frequency(
                    drive_frequency * 2 + detune
                )

                try:
                    if metric == "assignment_fidelity":
                        ge = ReadoutGEDiscrimination(self._ctx)
                        kw = dict(assignment_kwargs or {})
                        result = ge.run(
                            readout_op, drive_frequency,
                            r180=r180, n_samples=samples_per_run, **kw,
                        )
                        I_g = result.output.get("I_g", np.array([0]))
                        Q_g = result.output.get("Q_g", np.array([0]))
                        I_e = result.output.get("I_e", np.array([0]))
                        Q_e = result.output.get("Q_e", np.array([0]))
                        from ...analysis.analysis_tools import two_state_discriminator
                        _, _, fid, _, _, _ = two_state_discriminator(
                            I_g, Q_g, I_e, Q_e,
                        )
                        results[i, j] = fid
                    else:
                        bfly = ReadoutButterflyMeasurement(self._ctx)
                        kw = dict(butterfly_kwargs or {})
                        result = bfly.run(
                            r180=r180, n_samples=samples_per_run, **kw,
                        )
                        results[i, j] = result.output.get("F", 0.0)
                except Exception:
                    pass

        output = Output({
            "metric_matrix": results,
            "pump_powers": np.asarray(pump_powers),
            "pump_detunings": np.asarray(pump_detunings),
            "metric": metric,
        })
        self.save_output(output, "SPAPumpFreqOpt")
        return RunResult(mode="run", output=output, sim_samples=None)

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        metric_matrix = result.output.extract("metric_matrix")
        pump_powers = result.output.extract("pump_powers")
        pump_detunings = result.output.extract("pump_detunings")
        metric_name = result.output.get("metric", "assignment_fidelity")
        metrics: dict[str, Any] = {"metric": metric_name}

        if metric_matrix is not None and pump_powers is not None and pump_detunings is not None:
            # Mask NaN entries before finding best
            valid = ~np.isnan(metric_matrix)
            if np.any(valid):
                masked = np.where(valid, metric_matrix, -np.inf)
                best_idx = np.unravel_index(np.argmax(masked), masked.shape)
                metrics["best_pump_power"] = float(pump_powers[best_idx[0]])
                metrics["best_pump_detuning"] = float(pump_detunings[best_idx[1]])
                metrics["best_metric"] = float(metric_matrix[best_idx])

        return AnalysisResult.from_run(result, metrics=metrics)

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        metric_matrix = analysis.data.get("metric_matrix")
        pump_powers = analysis.data.get("pump_powers")
        pump_detunings = analysis.data.get("pump_detunings")
        if metric_matrix is None or pump_powers is None or pump_detunings is None:
            return None

        metric_name = analysis.metrics.get("metric", "Metric")

        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 6))
        else:
            fig = ax.figure

        im = ax.pcolormesh(
            np.asarray(pump_detunings) / 1e6,
            np.asarray(pump_powers),
            np.asarray(metric_matrix),
            shading="auto",
        )
        fig.colorbar(im, ax=ax, label=metric_name)

        best_power = analysis.metrics.get("best_pump_power")
        best_detune = analysis.metrics.get("best_pump_detuning")
        if best_power is not None and best_detune is not None:
            ax.axhline(best_power, color="r", ls="--", alpha=0.5)
            ax.axvline(best_detune / 1e6, color="r", ls="--", alpha=0.5)
            ax.plot(best_detune / 1e6, best_power, "rx", ms=12, mew=2)

        ax.set_xlabel("Pump Detuning (MHz)")
        ax.set_ylabel("Pump Power (dBm)")
        ax.set_title(f"SPA Pump Optimization ({metric_name})")
        plt.tight_layout()
        plt.show()
        return fig
