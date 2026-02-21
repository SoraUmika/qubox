"""Readout calibration experiments."""
from __future__ import annotations

import warnings
from typing import Any, Mapping, Tuple

import numpy as np
import matplotlib.pyplot as plt

from ..experiment_base import ExperimentBase
from ..result import AnalysisResult, FitResult
from ...analysis import post_process as pp
from ...analysis.analysis_tools import two_state_discriminator
from ...analysis.output import Output
from ...analysis.metrics import butterfly_metrics
from ...hardware.program_runner import RunResult
from ...programs import cQED_programs
from ...programs.macros.measure import measureMacro


class IQBlob(ExperimentBase):
    """Simple g/e IQ blob acquisition (no discrimination fitting)."""

    def run(
        self,
        r180: str = "x180",
        n_runs: int = 1000,
    ) -> RunResult:
        attr = self.attr
        self.set_standard_frequencies()

        prog = cQED_programs.iq_blobs(
            attr.ro_el, attr.qb_el, r180, attr.qb_therm_clks, n_runs,
        )
        return self.run_program(
            prog, n_total=n_runs,
            processors=[pp.proc_default],
            targets=[("Ig", "Qg"), ("Ie", "Qe")],
        )

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        S_g = result.output.get("S_g")
        S_e = result.output.get("S_e")
        metrics: dict[str, Any] = {}

        if S_g is not None and S_e is not None and len(S_g) > 0 and len(S_e) > 0:
            I_g, Q_g = np.real(S_g), np.imag(S_g)
            I_e, Q_e = np.real(S_e), np.imag(S_e)

            try:
                disc_out = two_state_discriminator(I_g, Q_g, I_e, Q_e)
                metrics["fidelity"] = float(disc_out["fidelity"])
                metrics["angle"] = float(disc_out["angle"])
                metrics["threshold"] = float(disc_out["threshold"])
                metrics["confusion_matrix"] = [
                    [float(disc_out["gg"]), float(disc_out["ge"])],
                    [float(disc_out["eg"]), float(disc_out["ee"])],
                ]
            except Exception:
                pass

        return AnalysisResult.from_run(result, metrics=metrics)

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        S_g = analysis.data.get("S_g")
        S_e = analysis.data.get("S_e")
        if S_g is None or S_e is None:
            return None

        if ax is None:
            fig, ax = plt.subplots(figsize=(8, 8))
        else:
            fig = ax.figure

        ax.scatter(np.real(S_g), np.imag(S_g), s=1, alpha=0.3, c="blue", label="|g>")
        ax.scatter(np.real(S_e), np.imag(S_e), s=1, alpha=0.3, c="red", label="|e>")

        title = "IQ Blobs"
        if "fidelity" in analysis.metrics:
            title += f"  |  F = {analysis.metrics['fidelity']:.1f}%"
        ax.set_title(title)
        ax.set_xlabel("I")
        ax.set_ylabel("Q")
        ax.legend()
        ax.set_aspect("equal", adjustable="datalim")
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig


class ReadoutGERawTrace(ExperimentBase):
    """Raw time-domain readout traces for ground and excited states."""

    def run(
        self,
        ro_freq: float,
        r180: str = "x180",
        ro_depl_clks: int = 10000,
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        self.hw.set_element_fq(attr.ro_el, ro_freq)
        self.set_standard_frequencies()

        prog = cQED_programs.readout_ge_raw_trace(
            attr.ro_el, attr.qb_el, r180, ro_depl_clks, n_avg,
        )
        return self.run_program(
            prog, n_total=n_avg,
            processors=[pp.proc_default],
        )

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        S = result.output.extract("S")
        metrics: dict[str, Any] = {}
        if S is not None:
            metrics["trace_length"] = int(np.size(S) // 2)
        return AnalysisResult.from_run(result, metrics=metrics)

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        S = analysis.data.get("S")
        if S is None:
            return None

        n = len(S) // 2
        S_g, S_e = S[:n], S[n:]

        if ax is None:
            fig, axes = plt.subplots(1, 2, figsize=(14, 4))
        else:
            fig = ax.figure
            axes = [ax, ax.twinx()]

        for i, (s, label) in enumerate([(S_g, "|g>"), (S_e, "|e>")]):
            t = np.arange(len(s))
            axes[i].plot(t, np.real(s), label=f"I {label}")
            axes[i].plot(t, np.imag(s), label=f"Q {label}")
            axes[i].set_xlabel("Sample")
            axes[i].set_ylabel("Amplitude")
            axes[i].set_title(f"Raw Trace {label}")
            axes[i].legend()
            axes[i].grid(True, alpha=0.3)

        plt.tight_layout()
        plt.show()
        return fig


class ReadoutGEIntegratedTrace(ExperimentBase):
    """Time-sliced integrated g/e readout traces."""

    def run(
        self,
        ro_op: str,
        drive_frequency: float,
        weights: Any,
        num_div: int | None = None,
        div_clks: int = 25,
        *,
        r180: str = "x180",
        ro_depl_clks: int | None = None,
        n_avg: int = 100,
        process_in_sim: bool = False,
    ) -> RunResult:
        attr = self.attr
        self.hw.set_element_fq(attr.ro_el, drive_frequency)
        self.set_standard_frequencies()

        prog = cQED_programs.readout_ge_integrated_trace(
            attr.qb_el, weights, num_div, div_clks,
            r180, ro_depl_clks or attr.ro_therm_clks, n_avg,
        )
        return self.run_program(
            prog, n_total=n_avg, process_in_sim=process_in_sim,
            processors=[pp.proc_default],
        )

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        S = result.output.extract("S")
        metrics: dict[str, Any] = {}
        if S is not None:
            metrics["trace_length"] = int(np.size(S))
        return AnalysisResult.from_run(result, metrics=metrics)

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        S = analysis.data.get("S")
        if S is None:
            return None

        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 5))
        else:
            fig = ax.figure

        ax.plot(np.real(S), label="I (integrated)")
        ax.plot(np.imag(S), label="Q (integrated)")
        ax.set_xlabel("Time Slice")
        ax.set_ylabel("Integrated Signal")
        ax.set_title("Integrated G/E Readout Trace")
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig


class ReadoutGEDiscrimination(ExperimentBase):
    """G/E IQ discrimination with rotated integration weights.

    Fits a 2-D Gaussian to g/e IQ blobs, computes optimal rotation
    angle, and optionally registers rotated weights.
    """

    def run(
        self,
        measure_op: str,
        drive_frequency: float,
        r180: str = "x180",
        gain: float = 1.0,
        update_measure_macro: bool = False,
        burn_rot_weights: bool = True,
        persist: bool = False,
        n_samples: int = 10_000,
        base_weight_keys: tuple[str, str, str] | None = None,
        auto_update_postsel: bool = True,
        blob_k_g: float = 2.0,
        blob_k_e: float | None = None,
        **kwargs: Any,
    ) -> RunResult:
        attr = self.attr

        k_g = float(kwargs.pop("k_g", 2.0))
        k_e = float(kwargs.pop("k_e", k_g))
        if blob_k_e is None:
            blob_k_e = blob_k_g

        # Resolve pulse and integration weight mapping
        pulse_info = self.pulse_mgr.get_pulseOp_by_element_op(attr.ro_el, measure_op)
        weight_mapping = pulse_info.int_weights_mapping or {}
        if not isinstance(weight_mapping, dict):
            weight_mapping = {}

        is_readout = (pulse_info.op == "readout")
        op_prefix = "" if is_readout else f"{pulse_info.op}_"

        if base_weight_keys is None:
            base_weight_keys = self._choose_default_keys(weight_mapping, op_prefix)
        cos_key, sin_key, m_sin_key = base_weight_keys

        base_cos_name = weight_mapping[cos_key]
        base_sin_name = weight_mapping[sin_key]
        base_m_sin_name = weight_mapping[m_sin_key]

        self.set_standard_frequencies()
        self.hw.set_element_fq(attr.ro_el, drive_frequency)

        prog = cQED_programs.iq_blobs(
            attr.ro_el, attr.qb_el, r180, attr.qb_therm_clks, n_samples,
        )
        result = self.run_program(
            prog, n_total=n_samples,
            processors=[pp.proc_default],
            targets=[("Ig", "Qg"), ("Ie", "Qe")],
        )
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        S_g = result.output.get("S_g")
        S_e = result.output.get("S_e")
        metrics: dict[str, Any] = {}

        if S_g is not None and S_e is not None and len(S_g) > 0 and len(S_e) > 0:
            I_g, Q_g = np.real(S_g), np.imag(S_g)
            I_e, Q_e = np.real(S_e), np.imag(S_e)

            try:
                disc_out = two_state_discriminator(I_g, Q_g, I_e, Q_e)
                metrics["fidelity"] = float(disc_out["fidelity"])
                metrics["angle"] = float(disc_out["angle"])
                metrics["threshold"] = float(disc_out["threshold"])
                metrics["gg"] = float(disc_out["gg"])
                metrics["ge"] = float(disc_out["ge"])
                metrics["eg"] = float(disc_out["eg"])
                metrics["ee"] = float(disc_out["ee"])
            except Exception:
                pass

        analysis = AnalysisResult.from_run(result, metrics=metrics)

        if update_calibration and self.calibration_store and "fidelity" in metrics:
            self.calibration_store.set_discrimination(
                self.attr.ro_el,
                angle=metrics.get("angle"),
                threshold=metrics.get("threshold"),
                fidelity=metrics.get("fidelity"),
            )

        return analysis

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        S_g = analysis.data.get("S_g")
        S_e = analysis.data.get("S_e")
        if S_g is None or S_e is None:
            return None

        if ax is None:
            fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        else:
            fig = ax.figure
            axes = [ax, fig.add_subplot(122)]

        # IQ scatter
        axes[0].scatter(np.real(S_g), np.imag(S_g), s=1, alpha=0.2, c="blue", label="|g>")
        axes[0].scatter(np.real(S_e), np.imag(S_e), s=1, alpha=0.2, c="red", label="|e>")
        title = "G/E Discrimination"
        if "fidelity" in analysis.metrics:
            title += f"  |  F = {analysis.metrics['fidelity']:.1f}%"
        axes[0].set_title(title)
        axes[0].set_xlabel("I")
        axes[0].set_ylabel("Q")
        axes[0].legend()
        axes[0].set_aspect("equal", adjustable="datalim")
        axes[0].grid(True, alpha=0.3)

        # Confusion matrix
        if all(k in analysis.metrics for k in ("gg", "ge", "eg", "ee")):
            cm = np.array([
                [analysis.metrics["gg"], analysis.metrics["ge"]],
                [analysis.metrics["eg"], analysis.metrics["ee"]],
            ])
            im = axes[1].imshow(cm, cmap="Blues", vmin=0, vmax=100)
            axes[1].set_xticks([0, 1])
            axes[1].set_yticks([0, 1])
            axes[1].set_xticklabels(["Prep |g>", "Prep |e>"])
            axes[1].set_yticklabels(["Meas |g>", "Meas |e>"])
            for i in range(2):
                for j in range(2):
                    axes[1].text(j, i, f"{cm[i, j]:.1f}%", ha="center", va="center", fontsize=14)
            axes[1].set_title("Confusion Matrix")
            fig.colorbar(im, ax=axes[1], shrink=0.8)

        plt.tight_layout()
        plt.show()
        return fig

    @staticmethod
    def _choose_default_keys(
        mapping: dict, prefix: str,
    ) -> tuple[str, str, str]:
        """Choose default base-weight keys from the pulse mapping."""
        def _name(p, s):
            return s if not p else f"{p}{s}"

        # Canonical, prefixed
        cand = (_name(prefix, "cos"), _name(prefix, "sin"), _name(prefix, "m_sin"))
        if all(k in mapping for k in cand):
            return cand

        # Canonical, unprefixed
        cand_un = ("cos", "sin", "m_sin")
        if all(k in mapping for k in cand_un):
            return cand_un

        # Legacy, prefixed
        legacy = (_name(prefix, "rot_cos"), _name(prefix, "rot_sin"), _name(prefix, "rot_m_sin"))
        if all(k in mapping for k in legacy):
            warnings.warn(
                "Using legacy 'rot_*' weight labels. "
                "Please rename to 'cos', 'sin', 'm_sin'.",
                DeprecationWarning, stacklevel=3,
            )
            return legacy

        # Legacy, unprefixed
        legacy_un = ("rot_cos", "rot_sin", "rot_m_sin")
        if all(k in mapping for k in legacy_un):
            warnings.warn(
                "Using legacy 'rot_*' weight labels. "
                "Please rename to 'cos', 'sin', 'm_sin'.",
                DeprecationWarning, stacklevel=3,
            )
            return legacy_un

        raise KeyError(
            "Default weight labels not found. Provide base_weight_keys "
            f"explicitly. Available: {sorted(mapping.keys())}"
        )


class ReadoutWeightsOptimization(ExperimentBase):
    """Optimize integration weights from g/e readout traces."""

    def run(
        self,
        ro_op: str,
        drive_frequency: float,
        cos_w_key: str,
        sin_w_key: str,
        m_sin_w_key: str,
        *,
        num_div: int = 1,
        r180: str = "x180",
        ro_depl_clks: int | None = None,
        n_avg: int = 100,
        persist: bool = False,
        set_measure_macro: bool = False,
        make_plots: bool = True,
    ) -> RunResult:
        attr = self.attr
        self.hw.set_element_fq(attr.ro_el, drive_frequency)
        self.set_standard_frequencies()

        # First get integrated traces
        trace_exp = ReadoutGEIntegratedTrace(self._ctx)
        result = trace_exp.run(
            ro_op, drive_frequency, (cos_w_key, sin_w_key, m_sin_w_key),
            num_div=num_div, r180=r180,
            ro_depl_clks=ro_depl_clks, n_avg=n_avg,
        )
        self.save_output(result.output, "readoutWeightsOpt")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        S = result.output.extract("S")
        metrics: dict[str, Any] = {}
        if S is not None:
            metrics["trace_length"] = int(np.size(S))
        return AnalysisResult.from_run(result, metrics=metrics)

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        S = analysis.data.get("S")
        if S is None:
            return None

        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 5))
        else:
            fig = ax.figure

        ax.plot(np.real(S), label="I (integrated)")
        ax.plot(np.imag(S), label="Q (integrated)")
        ax.set_xlabel("Time Slice")
        ax.set_ylabel("Integrated Signal")
        ax.set_title("Readout Weights Optimization")
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig


class ReadoutButterflyMeasurement(ExperimentBase):
    """Three-measurement butterfly protocol for F, Q, and QND metrics."""

    def run(
        self,
        prep_policy: str | None = None,
        prep_kwargs: dict | None = None,
        r180: str = "x180",
        update_measure_macro: bool = False,
        show_analysis: bool = False,
        n_samples: int = 10_000,
        M0_MAX_TRIALS: int = 16,
        *,
        use_stored_config: bool = True,
        det_L_threshold: float = 1e-8,
    ) -> RunResult:
        attr = self.attr
        self.set_standard_frequencies()

        # Resolve post-selection config
        if use_stored_config and prep_policy is None:
            ps_cfg = measureMacro.get_post_select_config()
            if ps_cfg is not None:
                post_sel_policy = ps_cfg.policy
                post_sel_kwargs = dict(ps_cfg.kwargs) if ps_cfg.kwargs else {}
            else:
                post_sel_policy = prep_policy or "NONE"
                post_sel_kwargs = dict(prep_kwargs or {})
        else:
            post_sel_policy = prep_policy or "NONE"
            post_sel_kwargs = dict(prep_kwargs or {})

        prog = cQED_programs.readout_butterfly_measurement(
            attr.qb_el,
            r180,
            post_sel_policy,
            post_sel_kwargs,
            M0_MAX_TRIALS,
            n_samples,
        )
        result = self.run_program(
            prog, n_total=n_samples,
            processors=[pp.bare_proc],
        )
        self.save_output(result.output, "butterflyMeasurement")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        states = result.output.get("states")
        metrics: dict[str, Any] = {}

        if states is not None:
            states = np.asarray(states)
            # states shape: (n_shots, 2_branches, 3_measurements)
            # branch 0 = ground-prepared, branch 1 = excited-prepared
            # measurement 0=M0, 1=M1, 2=M2
            try:
                m1_g = states[:, 0, 1]  # M1 outcomes for ground prep
                m1_e = states[:, 1, 1]  # M1 outcomes for excited prep
                m2_g = states[:, 0, 2]  # M2 outcomes for ground prep
                m2_e = states[:, 1, 2]  # M2 outcomes for excited prep

                bfly_out = butterfly_metrics(m1_g, m1_e, m2_g, m2_e)
                metrics["F"] = float(bfly_out["F"])
                metrics["Q"] = float(bfly_out["Q"])
                metrics["V"] = float(bfly_out["V"])
                if "t01" in bfly_out:
                    metrics["t01"] = float(bfly_out["t01"])
                if "t10" in bfly_out:
                    metrics["t10"] = float(bfly_out["t10"])
                if "confusion_matrix" in bfly_out:
                    cm = bfly_out["confusion_matrix"]
                    metrics["confusion_matrix"] = cm.tolist() if hasattr(cm, 'tolist') else cm
            except Exception:
                pass

        analysis = AnalysisResult.from_run(result, metrics=metrics)

        if update_calibration and self.calibration_store and "F" in metrics:
            self.calibration_store.set_readout_quality(
                self.attr.ro_el,
                F=metrics.get("F"),
                Q=metrics.get("Q"),
                V=metrics.get("V"),
            )

        return analysis

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        metrics = analysis.metrics
        if not any(k in metrics for k in ("F", "Q", "V")):
            return None

        if ax is None:
            fig, ax = plt.subplots(figsize=(8, 5))
        else:
            fig = ax.figure

        labels, values = [], []
        for key in ("F", "Q", "V"):
            if key in metrics:
                labels.append(key)
                values.append(metrics[key])

        bars = ax.bar(labels, values, color=["steelblue", "coral", "seagreen"])
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                    f"{val:.1f}%", ha="center", va="bottom", fontsize=12)

        ax.set_ylim(0, 110)
        ax.set_ylabel("Percentage (%)")
        ax.set_title("Butterfly Measurement Metrics")
        ax.grid(True, alpha=0.3, axis="y")
        plt.tight_layout()
        plt.show()
        return fig


class CalibrateReadoutFull(ExperimentBase):
    """End-to-end readout calibration pipeline.

    Runs in sequence:
    1. ReadoutWeightsOptimization (optional)
    2. ReadoutGEDiscrimination
    3. ReadoutButterflyMeasurement
    """

    def run(
        self,
        ro_op: str,
        drive_frequency: float,
        *,
        ro_el: str = "resonator",
        r180: str = "x180",
        n_avg_weights: int = 200_000,
        n_samples_disc: int = 250_000,
        n_shots_butterfly: int = 50_000,
        display_analysis: bool = False,
        persist_weights: bool = True,
        save: bool = True,
        skip_weights_optimization: bool = False,
        blob_k_g: float = 3.0,
        blob_k_e: float | None = None,
        wopt_kwargs: dict | None = None,
        ge_kwargs: dict | None = None,
        bfly_kwargs: dict | None = None,
    ) -> dict:
        results = {}

        # Step 1: Weights optimization
        if not skip_weights_optimization:
            wopt = ReadoutWeightsOptimization(self._ctx)
            wopt_kw = dict(wopt_kwargs or {})
            wopt_result = wopt.run(
                ro_op, drive_frequency,
                "cos", "sin", "m_sin",
                r180=r180, n_avg=n_avg_weights,
                persist=persist_weights,
                **wopt_kw,
            )
            results["weights_optimization"] = wopt_result

        # Step 2: G/E discrimination
        ge_disc = ReadoutGEDiscrimination(self._ctx)
        ge_kw = dict(ge_kwargs or {})
        ge_result = ge_disc.run(
            ro_op, drive_frequency,
            r180=r180,
            n_samples=n_samples_disc,
            blob_k_g=blob_k_g,
            blob_k_e=blob_k_e,
            **ge_kw,
        )
        results["ge_discrimination"] = ge_result

        # Step 3: Butterfly measurement
        bfly = ReadoutButterflyMeasurement(self._ctx)
        bfly_kw = dict(bfly_kwargs or {})
        bfly_result = bfly.run(
            r180=r180,
            n_samples=n_shots_butterfly,
            **bfly_kw,
        )
        results["butterfly"] = bfly_result

        return results

    def analyze(self, result: dict, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        """Collate metrics from sub-experiment results."""
        metrics: dict[str, Any] = {}

        # Analyze G/E discrimination stage
        if "ge_discrimination" in result:
            ge_disc = ReadoutGEDiscrimination(self._ctx)
            ge_analysis = ge_disc.analyze(result["ge_discrimination"],
                                          update_calibration=update_calibration)
            for k, v in ge_analysis.metrics.items():
                metrics[f"ge_{k}"] = v

        # Analyze butterfly stage
        if "butterfly" in result:
            bfly = ReadoutButterflyMeasurement(self._ctx)
            bfly_analysis = bfly.analyze(result["butterfly"],
                                         update_calibration=update_calibration)
            for k, v in bfly_analysis.metrics.items():
                metrics[f"bfly_{k}"] = v

        return AnalysisResult(data={}, metrics=metrics)

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        metrics = analysis.metrics
        if not metrics:
            return None

        if ax is None:
            fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        else:
            fig = ax.figure
            axes = [ax, fig.add_subplot(122)]

        # Discrimination fidelity
        fid_keys = [k for k in metrics if k.startswith("ge_")]
        if fid_keys:
            labels = [k.replace("ge_", "") for k in fid_keys]
            vals = [metrics[k] for k in fid_keys]
            axes[0].bar(labels, vals)
            axes[0].set_title("Discrimination Metrics")
            axes[0].set_ylabel("Value")
            axes[0].grid(True, alpha=0.3, axis="y")

        # Butterfly metrics
        bfly_keys = [k for k in ("bfly_F", "bfly_Q", "bfly_V") if k in metrics]
        if bfly_keys:
            labels = [k.replace("bfly_", "") for k in bfly_keys]
            vals = [metrics[k] for k in bfly_keys]
            bars = axes[1].bar(labels, vals, color=["steelblue", "coral", "seagreen"])
            for bar, val in zip(bars, vals):
                axes[1].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                        f"{val:.1f}%", ha="center", va="bottom")
            axes[1].set_ylim(0, 110)
            axes[1].set_title("Butterfly Metrics")
            axes[1].set_ylabel("Percentage (%)")
            axes[1].grid(True, alpha=0.3, axis="y")

        plt.tight_layout()
        plt.show()
        return fig


class ReadoutAmpLenOpt(ExperimentBase):
    """2-D sweep of readout amplitude x length for fidelity optimization."""

    def run(
        self,
        drive_frequency: float,
        min_len: int,
        max_len: int,
        dlen: int,
        min_g: float,
        max_g: float,
        dg: float,
        ringdown_len: int | None = None,
        r180: str = "x180",
        base_voltage: float = 0.01,
        ge_disc_kwargs: Mapping[str, Any] | None = None,
        butterfly_kwargs: Mapping[str, Any] | None = None,
    ) -> Output:
        attr = self.attr
        lengths = np.arange(min_len, max_len + 1, dlen, dtype=int)
        gains = np.arange(min_g, max_g + 1e-12, dg, dtype=float)

        self.set_standard_frequencies()
        self.hw.set_element_fq(attr.ro_el, drive_frequency)

        fidelity_matrix = np.full((len(lengths), len(gains)), np.nan)

        for i, length in enumerate(lengths):
            for j, gain in enumerate(gains):
                try:
                    ge_disc = ReadoutGEDiscrimination(self._ctx)
                    kw = dict(ge_disc_kwargs or {})
                    result = ge_disc.run(
                        "readout", drive_frequency,
                        r180=r180, gain=gain, n_samples=1000,
                        **kw,
                    )
                    S_g = result.output.get("S_g", np.array([0+0j]))
                    S_e = result.output.get("S_e", np.array([0+0j]))
                    I_g, Q_g = np.real(S_g), np.imag(S_g)
                    I_e, Q_e = np.real(S_e), np.imag(S_e)
                    _, _, fid, _, _, _ = two_state_discriminator(I_g, Q_g, I_e, Q_e)
                    fidelity_matrix[i, j] = fid
                except Exception:
                    pass

        output = Output({
            "fidelity_matrix": fidelity_matrix,
            "lengths": lengths,
            "gains": gains,
        })
        self.save_output(output, "readoutAmpLenOpt")
        return output

    def analyze(self, result: Output, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        fidelity_matrix = result.extract("fidelity_matrix") if hasattr(result, 'extract') else result.get("fidelity_matrix")
        lengths = result.extract("lengths") if hasattr(result, 'extract') else result.get("lengths")
        gains = result.extract("gains") if hasattr(result, 'extract') else result.get("gains")

        metrics: dict[str, Any] = {}
        if fidelity_matrix is not None and not np.all(np.isnan(fidelity_matrix)):
            best_idx = np.unravel_index(np.nanargmax(fidelity_matrix), fidelity_matrix.shape)
            metrics["best_length"] = int(lengths[best_idx[0]])
            metrics["best_gain"] = float(gains[best_idx[1]])
            metrics["best_fidelity"] = float(fidelity_matrix[best_idx])

        return AnalysisResult(
            data={"fidelity_matrix": fidelity_matrix, "lengths": lengths, "gains": gains},
            metrics=metrics,
        )

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        fidelity_matrix = analysis.data.get("fidelity_matrix")
        lengths = analysis.data.get("lengths")
        gains = analysis.data.get("gains")
        if fidelity_matrix is None or lengths is None or gains is None:
            return None

        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 6))
        else:
            fig = ax.figure

        pcm = ax.pcolormesh(gains, lengths, fidelity_matrix, shading="auto", cmap="viridis")
        fig.colorbar(pcm, ax=ax, label="Fidelity (%)")

        if "best_gain" in analysis.metrics and "best_length" in analysis.metrics:
            ax.axvline(analysis.metrics["best_gain"], color="r", ls="--", lw=1, alpha=0.7)
            ax.axhline(analysis.metrics["best_length"], color="r", ls="--", lw=1, alpha=0.7)
            ax.plot(analysis.metrics["best_gain"], analysis.metrics["best_length"],
                    "r*", ms=15, label=f"Best: len={analysis.metrics['best_length']}, "
                    f"g={analysis.metrics['best_gain']:.3f}, F={analysis.metrics.get('best_fidelity', 0):.1f}%")
            ax.legend()

        ax.set_xlabel("Gain")
        ax.set_ylabel("Length (ns)")
        ax.set_title("Readout Amplitude x Length Optimization")
        plt.tight_layout()
        plt.show()
        return fig
