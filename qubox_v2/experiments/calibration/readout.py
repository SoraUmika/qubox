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
from ...analysis.metrics import butterfly_metrics, gaussian2D_score, wilson_interval
from ...core.logging import get_logger
from ...hardware.program_runner import RunResult
from ...programs import cQED_programs
from ...programs.macros.measure import measureMacro
from .readout_config import ReadoutConfig

_logger = get_logger(__name__)

# Default non-Gaussianity warning threshold
_DEFAULT_GAUSSIANITY_WARN = 2.0
# Minimum sample count for reliable discrimination
_MIN_SAMPLES_DISC = 100


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
        metadata: dict[str, Any] = {}

        if S_g is not None and S_e is not None and len(S_g) > 0 and len(S_e) > 0:
            I_g, Q_g = np.real(S_g), np.imag(S_g)
            I_e, Q_e = np.real(S_e), np.imag(S_e)

            # Non-Gaussianity check (Section 6A)
            ng_threshold = kw.get("gaussianity_warn_threshold", _DEFAULT_GAUSSIANITY_WARN)
            for label, Iv, Qv in [("g", I_g, Q_g), ("e", I_e, Q_e)]:
                ng_score = gaussian2D_score(Iv, Qv)
                metrics[f"gaussianity_{label}"] = float(ng_score) if np.isfinite(ng_score) else None
                if np.isfinite(ng_score) and ng_score > ng_threshold:
                    _logger.warning(
                        "IQ blob |%s> has high non-Gaussianity score: %.2f (threshold=%.2f)",
                        label, ng_score, ng_threshold,
                    )

            try:
                disc_out = two_state_discriminator(I_g, Q_g, I_e, Q_e)
                metrics["fidelity"] = float(disc_out["fidelity"])
                metrics["angle"] = float(disc_out["angle"])
                metrics["threshold"] = float(disc_out["threshold"])
                metrics["confusion_matrix"] = [
                    [float(disc_out["gg"]), float(disc_out["ge"])],
                    [float(disc_out["eg"]), float(disc_out["ee"])],
                ]
            except (ValueError, np.linalg.LinAlgError) as exc:
                _logger.warning("IQBlob discrimination failed: %s", exc)
                metadata["diagnostics"] = f"Discrimination failed: {exc}"
            except Exception as exc:
                _logger.error("Unexpected error in IQ discrimination: %s", exc)
                metadata["diagnostics"] = f"Unexpected discrimination error: {exc}"

        return AnalysisResult.from_run(result, metrics=metrics, metadata=metadata)

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
            attr.qb_el, r180, attr.qb_therm_clks, ro_depl_clks, n_avg,
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
        pulse_info = self.pulse_mgr.get_pulseOp_by_element_op(attr.ro_el, measure_op, strict=False)
        if pulse_info is None:
            raise RuntimeError(
                f"No pulse registered for (element={attr.ro_el!r}, op={measure_op!r}). "
                "Register the measure operation before running GE discrimination."
            )
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

        # Store params so analyze() can build rotated weights
        self._run_params = {
            "measure_op": measure_op,
            "burn_rot_weights": burn_rot_weights,
            "persist": persist,
            "base_cos_name": base_cos_name,
            "base_sin_name": base_sin_name,
            "base_m_sin_name": base_m_sin_name,
            "pulse_info": pulse_info,
            "op_prefix": op_prefix,
            "is_readout": is_readout,
            "auto_update_postsel": auto_update_postsel,
            "blob_k_g": blob_k_g,
            "blob_k_e": blob_k_e,
        }

        _logger.info("GE discrimination: n_samples=%d, measure_op=%r", n_samples, measure_op)

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
        metadata: dict[str, Any] = {}

        if S_g is not None and S_e is not None and len(S_g) > 0 and len(S_e) > 0:
            I_g, Q_g = np.real(S_g), np.imag(S_g)
            I_e, Q_e = np.real(S_e), np.imag(S_e)

            # Minimum sample count check (Section 2D)
            n_g, n_e = len(S_g), len(S_e)
            min_samples = kw.get("min_samples", _MIN_SAMPLES_DISC)
            if n_g < min_samples or n_e < min_samples:
                _logger.warning(
                    "Low sample count for discrimination: n_g=%d, n_e=%d (minimum=%d). "
                    "Results may be unreliable.",
                    n_g, n_e, min_samples,
                )
                metadata["diagnostics"] = f"Low sample count: n_g={n_g}, n_e={n_e}"

            # Non-Gaussianity check (Section 6A)
            ng_threshold = kw.get("gaussianity_warn_threshold", _DEFAULT_GAUSSIANITY_WARN)
            for label, Iv, Qv in [("g", I_g, Q_g), ("e", I_e, Q_e)]:
                ng_score = gaussian2D_score(Iv, Qv)
                metrics[f"gaussianity_{label}"] = float(ng_score) if np.isfinite(ng_score) else None
                if np.isfinite(ng_score) and ng_score > ng_threshold:
                    _logger.warning(
                        "GE blob |%s> non-Gaussianity score: %.2f (threshold=%.2f)",
                        label, ng_score, ng_threshold,
                    )

            try:
                disc_out = two_state_discriminator(I_g, Q_g, I_e, Q_e)
                metrics["fidelity"] = float(disc_out["fidelity"])
                metrics["angle"] = float(disc_out["angle"])
                metrics["threshold"] = float(disc_out["threshold"])
                metrics["gg"] = float(disc_out["gg"])
                metrics["ge"] = float(disc_out["ge"])
                metrics["eg"] = float(disc_out["eg"])
                metrics["ee"] = float(disc_out["ee"])

                # Additional metrics for post-selection
                for key in ("rot_mu_g", "rot_mu_e", "sigma_g", "sigma_e"):
                    if key in disc_out:
                        val = disc_out[key]
                        if isinstance(val, (complex, np.complexfloating)):
                            val = val.real
                        metrics[key] = float(val)

                _logger.info(
                    "GE discrimination fidelity=%.2f%%, angle=%.4f rad, threshold=%.4g",
                    metrics["fidelity"], metrics["angle"], metrics["threshold"],
                )
            except (ValueError, np.linalg.LinAlgError) as exc:
                _logger.warning("GE discrimination failed: %s", exc)
                metadata["diagnostics"] = (
                    metadata.get("diagnostics", "") + f" Discrimination failed: {exc}"
                ).strip()
            except Exception as exc:
                _logger.error("Unexpected error in GE discrimination: %s", exc)
                metadata["diagnostics"] = (
                    metadata.get("diagnostics", "") + f" Unexpected error: {exc}"
                ).strip()

            # Cross-validation for unbiased fidelity (Section 6C)
            cv_split = kw.get("cv_split_ratio", 0.0)
            if cv_split > 0 and "fidelity" in metrics:
                cv_fid = self._cross_validated_fidelity(I_g, Q_g, I_e, Q_e, cv_split)
                if cv_fid is not None:
                    metrics["cv_fidelity"] = cv_fid
                    _logger.info("Cross-validated fidelity: %.2f%%", cv_fid)

        analysis = AnalysisResult.from_run(result, metrics=metrics, metadata=metadata)

        # Build rotated integration weights if run() stored params
        if hasattr(self, "_run_params") and "angle" in metrics:
            try:
                self._build_rotated_weights(metrics)
                _logger.info("Rotated integration weights built and registered")
            except Exception as exc:
                _logger.warning("Rotated weight construction failed: %s", exc)
                warnings.warn(f"Rotated weight construction failed: {exc}")

        if update_calibration and self.calibration_store and "fidelity" in metrics:
            self.calibration_store.set_discrimination(
                self.attr.ro_el,
                angle=metrics.get("angle"),
                threshold=metrics.get("threshold"),
                fidelity=metrics.get("fidelity"),
                mu_g=[metrics.get("rot_mu_g", 0.0), 0.0],
                mu_e=[metrics.get("rot_mu_e", 0.0), 0.0],
                sigma_g=metrics.get("sigma_g"),
                sigma_e=metrics.get("sigma_e"),
            )

        return analysis

    @staticmethod
    def _cross_validated_fidelity(
        I_g: np.ndarray, Q_g: np.ndarray,
        I_e: np.ndarray, Q_e: np.ndarray,
        split_ratio: float = 0.2,
    ) -> float | None:
        """Split IQ data into train/test for unbiased fidelity.

        Parameters
        ----------
        split_ratio : float
            Fraction of data held out for testing (0-1).

        Returns
        -------
        float | None
            Cross-validated fidelity (0-100), or None on failure.
        """
        try:
            n_g, n_e = len(I_g), len(I_e)
            n_test_g = max(1, int(n_g * split_ratio))
            n_test_e = max(1, int(n_e * split_ratio))

            rng = np.random.default_rng(42)
            idx_g = rng.permutation(n_g)
            idx_e = rng.permutation(n_e)

            # Train on majority
            train_disc = two_state_discriminator(
                I_g[idx_g[n_test_g:]], Q_g[idx_g[n_test_g:]],
                I_e[idx_e[n_test_e:]], Q_e[idx_e[n_test_e:]],
            )
            angle = train_disc["angle"]
            threshold = train_disc["threshold"]

            # Evaluate on held-out test set
            C, S = np.cos(-angle), np.sin(-angle)
            test_Ig = I_g[idx_g[:n_test_g]]
            test_Qg = Q_g[idx_g[:n_test_g]]
            test_Ie = I_e[idx_e[:n_test_e]]
            test_Qe = Q_e[idx_e[:n_test_e]]

            Ig_rot = C * test_Ig - S * test_Qg
            Ie_rot = C * test_Ie - S * test_Qe

            gg = np.sum(Ig_rot < threshold) / len(Ig_rot)
            ee = np.sum(Ie_rot > threshold) / len(Ie_rot)
            return float(100.0 * (gg + ee) / 2.0)
        except Exception:
            return None

    def _build_rotated_weights(self, metrics: dict) -> None:
        """Build rotated integration weights from discrimination angle.

        Matches the legacy convention:
          rot_cos:   I-channel = C,  Q-channel = -S
          rot_sin:   I-channel = S,  Q-channel =  C
          rot_m_sin: I-channel = -S, Q-channel = -C

        where C = cos(-angle), S = sin(-angle).
        """
        params = self._run_params
        angle = float(metrics["angle"])
        C = float(np.cos(-angle))
        S = float(np.sin(-angle))

        pulse_info = params["pulse_info"]
        op_prefix = params["op_prefix"]
        persist = params["persist"]
        burn_rot_weights = params["burn_rot_weights"]
        base_cos_name = params["base_cos_name"]
        base_sin_name = params["base_sin_name"]

        def _name(prefix, suffix):
            return suffix if not prefix else f"{prefix}{suffix}"

        rot_cos_name = _name(op_prefix, "rot_cos")
        rot_sin_name = _name(op_prefix, "rot_sin")
        rot_m_sin_name = _name(op_prefix, "rot_m_sin")

        pm = self.pulse_mgr
        base_is_segmented = pm.is_segmented_integration_weight(base_cos_name)

        if not base_is_segmented:
            L = int(pulse_info.length or 0)
            if L <= 0:
                return
            pm.add_int_weight(rot_cos_name,   C,  -S, L, persist=persist)
            pm.add_int_weight(rot_sin_name,   S,   C, L, persist=persist)
            pm.add_int_weight(rot_m_sin_name, -S, -C, L, persist=persist)
        else:
            cos_cos_segs, cos_sin_segs = pm.get_integration_weight_segments(base_cos_name)
            sin_cos_segs, sin_sin_segs = pm.get_integration_weight_segments(base_sin_name)

            rc_cos = pm.lincomb_segments(C,  -S, cos_cos_segs, sin_cos_segs)
            rc_sin = pm.lincomb_segments(C,  -S, cos_sin_segs, sin_sin_segs)
            pm.add_int_weight_segments(rot_cos_name, rc_cos, rc_sin, persist=persist)

            rs_cos = pm.lincomb_segments(S,   C, cos_cos_segs, sin_cos_segs)
            rs_sin = pm.lincomb_segments(S,   C, cos_sin_segs, sin_sin_segs)
            pm.add_int_weight_segments(rot_sin_name, rs_cos, rs_sin, persist=persist)

            rm_cos = pm.lincomb_segments(-S, -C, cos_cos_segs, sin_cos_segs)
            rm_sin = pm.lincomb_segments(-S, -C, cos_sin_segs, sin_sin_segs)
            pm.add_int_weight_segments(rot_m_sin_name, rm_cos, rm_sin, persist=persist)

        # Update pulse mapping (+ synonyms matching legacy)
        for lab, iw in (
            (_name(op_prefix, "rot_cos"),    rot_cos_name),
            (_name(op_prefix, "rot_sin"),    rot_sin_name),
            (_name(op_prefix, "rot_m_sin"),  rot_m_sin_name),
            (_name(op_prefix, "rot_cosine"), rot_cos_name),
            (_name(op_prefix, "rot_sine"),   rot_sin_name),
        ):
            pm.append_integration_weight_mapping(
                pulse_info.pulse, lab, iw, override=True
            )

        if burn_rot_weights:
            self.burn_pulses(include_volatile=True)

    def plot(self, analysis: AnalysisResult, *, ax=None,
             show_rotated: bool = True, interactive: bool = False, **kwargs):
        S_g = analysis.data.get("S_g")
        S_e = analysis.data.get("S_e")
        if S_g is None or S_e is None:
            return None

        # Try Plotly if interactive requested (Section 4D)
        if interactive:
            fig = self._plot_interactive(analysis)
            if fig is not None:
                return fig

        has_rotation = show_rotated and "angle" in analysis.metrics
        n_plots = 3 if has_rotation else 2

        if ax is None:
            fig, axes = plt.subplots(1, n_plots, figsize=(7 * n_plots, 6))
            if n_plots == 1:
                axes = [axes]
        else:
            fig = ax.figure
            axes = [ax] + [fig.add_subplot(1, n_plots, i + 2) for i in range(n_plots - 1)]

        # Panel 0: IQ scatter
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

        # Panel 1: Confusion matrix
        if all(k in analysis.metrics for k in ("gg", "ge", "eg", "ee")):
            cm = np.array([
                [analysis.metrics["gg"], analysis.metrics["ge"]],
                [analysis.metrics["eg"], analysis.metrics["ee"]],
            ]) * 100  # convert 0-1 fractions to percentages
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

        # Panel 2: Rotated IQ blobs with threshold line (Section 4A)
        if has_rotation and n_plots == 3:
            angle = analysis.metrics["angle"]
            threshold = analysis.metrics.get("threshold", 0.0)

            # Use stored rotated data if available, otherwise recompute
            Sg_rot = analysis.data.get("Sg_rot")
            Se_rot = analysis.data.get("Se_rot")
            if Sg_rot is None or Se_rot is None:
                rot = np.exp(-1j * angle)
                Sg_rot = np.asarray(S_g) * rot
                Se_rot = np.asarray(S_e) * rot

            axes[2].scatter(np.real(Sg_rot), np.imag(Sg_rot), s=1, alpha=0.2, c="blue", label="|g>")
            axes[2].scatter(np.real(Se_rot), np.imag(Se_rot), s=1, alpha=0.2, c="red", label="|e>")
            axes[2].axvline(x=threshold, color="k", ls="--", lw=1.5, label=f"thr={threshold:.4g}")
            axes[2].set_title("Rotated IQ + Threshold")
            axes[2].set_xlabel("I_rot")
            axes[2].set_ylabel("Q_rot")
            axes[2].legend()
            axes[2].set_aspect("equal", adjustable="datalim")
            axes[2].grid(True, alpha=0.3)

        plt.tight_layout()
        plt.show()
        return fig

    def _plot_interactive(self, analysis: AnalysisResult):
        """Create interactive Plotly figure if plotly is available."""
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots
        except ImportError:
            _logger.debug("Plotly not available, falling back to matplotlib")
            return None

        S_g = analysis.data.get("S_g")
        S_e = analysis.data.get("S_e")
        if S_g is None or S_e is None:
            return None

        fig = make_subplots(rows=1, cols=2,
                            subplot_titles=("Raw IQ", "Rotated IQ"))

        fig.add_trace(go.Scattergl(
            x=np.real(S_g), y=np.imag(S_g),
            mode="markers", marker=dict(size=2, color="blue", opacity=0.3),
            name="|g>",
        ), row=1, col=1)
        fig.add_trace(go.Scattergl(
            x=np.real(S_e), y=np.imag(S_e),
            mode="markers", marker=dict(size=2, color="red", opacity=0.3),
            name="|e>",
        ), row=1, col=1)

        # Rotated panel
        if "angle" in analysis.metrics:
            angle = analysis.metrics["angle"]
            threshold = analysis.metrics.get("threshold", 0.0)
            rot = np.exp(-1j * angle)
            Sg_rot = np.asarray(S_g) * rot
            Se_rot = np.asarray(S_e) * rot

            fig.add_trace(go.Scattergl(
                x=np.real(Sg_rot), y=np.imag(Sg_rot),
                mode="markers", marker=dict(size=2, color="blue", opacity=0.3),
                name="|g> rot", showlegend=False,
            ), row=1, col=2)
            fig.add_trace(go.Scattergl(
                x=np.real(Se_rot), y=np.imag(Se_rot),
                mode="markers", marker=dict(size=2, color="red", opacity=0.3),
                name="|e> rot", showlegend=False,
            ), row=1, col=2)
            fig.add_vline(x=threshold, line_dash="dash", line_color="black",
                          row=1, col=2)

        title = "G/E Discrimination"
        if "fidelity" in analysis.metrics:
            title += f"  |  F = {analysis.metrics['fidelity']:.1f}%"
        fig.update_layout(title_text=title, height=500, width=1100)
        fig.show()
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
    """Optimize integration weights from g/e readout traces.

    Computes the normalised ``g_e`` difference trace, builds segmented
    integration weights (cos/sin/m_sin triplet), and registers them in
    the :class:`PulseOperationManager`.
    """

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
        revert_on_no_improvement: bool = False,
    ) -> RunResult:
        attr = self.attr
        self.hw.set_element_fq(attr.ro_el, drive_frequency)
        self.set_standard_frequencies()

        # Store run params for analyze()
        self._run_params = {
            "ro_op": ro_op,
            "cos_w_key": cos_w_key,
            "sin_w_key": sin_w_key,
            "m_sin_w_key": m_sin_w_key,
            "persist": persist,
            "set_measure_macro": set_measure_macro,
            "revert_on_no_improvement": revert_on_no_improvement,
        }

        _logger.info(
            "Weight optimization: ro_op=%r, n_avg=%d, persist=%s",
            ro_op, n_avg, persist,
        )

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
        """Compute ge_diff_norm, build segmented weights, register in PulseOperationManager."""
        metrics: dict[str, Any] = {}
        metadata: dict[str, Any] = {}

        g_trace = result.output.get("g_trace")
        e_trace = result.output.get("e_trace")
        div_clks = result.output.get("div_clks")

        if g_trace is None or e_trace is None or div_clks is None:
            # Fallback: just report basic trace length
            S = result.output.extract("S") if hasattr(result.output, "extract") else None
            if S is not None:
                metrics["trace_length"] = int(np.size(S))
            _logger.warning("Missing g_trace/e_trace/div_clks — skipping weight optimization")
            metadata["diagnostics"] = "Missing trace data for weight optimization"
            return AnalysisResult.from_run(result, metrics=metrics, metadata=metadata)

        # Build ge_diff_norm (ported from legacy_experiment.py:2289-2306)
        ge_diff = np.asarray(e_trace) - np.asarray(g_trace)
        ge_diff_norm = self._normalize_complex_array(ge_diff)

        metrics["trace_length"] = int(len(ge_diff))
        metrics["ge_diff_norm_max"] = float(np.max(np.abs(ge_diff_norm)))

        # Build segmented weights
        Re = ge_diff_norm.real
        Im = ge_diff_norm.imag
        nRe = -Re
        nIm = -Im

        seg_cosine_cos = self._segments_per_slice(Re, div_clks)
        seg_cosine_sin = self._segments_per_slice(nIm, div_clks)
        seg_sine_cos = self._segments_per_slice(Im, div_clks)
        seg_sine_sin = self._segments_per_slice(Re, div_clks)
        seg_minus_sin_cos = self._segments_per_slice(nIm, div_clks)
        seg_minus_sin_sin = self._segments_per_slice(nRe, div_clks)

        # Register weights if run() stored params
        if hasattr(self, "_run_params"):
            try:
                self._register_optimized_weights(
                    seg_cosine_cos, seg_cosine_sin,
                    seg_sine_cos, seg_sine_sin,
                    seg_minus_sin_cos, seg_minus_sin_sin,
                    div_clks,
                )
                _logger.info("Optimised segmented weights registered in PulseOperationManager")
            except Exception as exc:
                _logger.error("Weight registration failed: %s", exc)
                metadata["diagnostics"] = f"Weight registration failed: {exc}"

        # Weight version tracking (Section 1D)
        if update_calibration and self.calibration_store:
            self.calibration_store.store_weight_snapshot(
                self.attr.ro_el,
                {"ge_diff_norm_max": metrics["ge_diff_norm_max"],
                 "trace_length": metrics["trace_length"]},
            )

        return AnalysisResult.from_run(result, metrics=metrics, metadata=metadata)

    def _register_optimized_weights(
        self,
        seg_cos_cos, seg_cos_sin,
        seg_sin_cos, seg_sin_sin,
        seg_msin_cos, seg_msin_sin,
        div_clks,
    ) -> None:
        """Register optimised segmented weights in PulseOperationManager."""
        params = self._run_params
        ro_op = params["ro_op"]
        cos_w_key = params["cos_w_key"]
        sin_w_key = params["sin_w_key"]
        m_sin_w_key = params["m_sin_w_key"]
        persist = params["persist"]
        set_measure_macro = params["set_measure_macro"]

        attr = self.attr
        pm = self.pulse_mgr

        # Resolve pulse info for weight mapping
        pulseOp = pm.get_pulseOp_by_element_op(attr.ro_el, ro_op)
        if pulseOp is None:
            raise RuntimeError(f"No pulse registered for ({attr.ro_el!r}, {ro_op!r})")
        pulse = pulseOp.pulse
        weight_mapping = pulseOp.int_weights_mapping or {}

        cos_weights = weight_mapping.get(cos_w_key, cos_w_key)
        sin_weights = weight_mapping.get(sin_w_key, sin_w_key)
        m_sin_weights = weight_mapping.get(m_sin_w_key, m_sin_w_key)

        opt_cos_label = f"opt_{cos_weights}"
        opt_sin_label = f"opt_{sin_weights}"
        opt_m_sin_label = f"opt_{m_sin_weights}"

        pm.add_int_weight_segments(opt_cos_label, seg_cos_cos, seg_cos_sin, persist=persist)
        pm.add_int_weight_segments(opt_sin_label, seg_sin_cos, seg_sin_sin, persist=persist)
        pm.add_int_weight_segments(opt_m_sin_label, seg_msin_cos, seg_msin_sin, persist=persist)

        opt_cos_key = f"opt_{cos_w_key}"
        opt_sin_key = f"opt_{sin_w_key}"
        opt_m_sin_key = f"opt_{m_sin_w_key}"

        pm.append_integration_weight_mapping(pulse, opt_cos_key, opt_cos_label, override=True)
        pm.append_integration_weight_mapping(pulse, opt_sin_key, opt_sin_label, override=True)
        pm.append_integration_weight_mapping(pulse, opt_m_sin_key, opt_m_sin_label, override=True)

        if set_measure_macro:
            measureMacro.set_outputs(
                [[opt_cos_key, opt_sin_key], [opt_m_sin_key, opt_cos_key]],
                weight_len=int(div_clks * 4),
            )
            self.burn_pulses(include_volatile=True)
            _logger.info("measureMacro updated with optimised weights")

    @staticmethod
    def _normalize_complex_array(arr: np.ndarray) -> np.ndarray:
        """Normalise complex array: unit norm, then scale by max abs."""
        arr = np.asarray(arr)
        norm = np.sqrt(np.sum(np.abs(arr) ** 2))
        if norm == 0:
            return arr
        arr = arr / norm
        mx = np.max(np.abs(arr))
        return arr / (mx if mx != 0 else 1.0)

    @staticmethod
    def _segments_per_slice(vec: np.ndarray, L_clks: int) -> list[tuple[float, int]]:
        """Convert weight vector to segmented weight format."""
        vec = np.asarray(vec, dtype=float).tolist()
        return [(a, int(4 * L_clks)) for a in vec]

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

        _logger.info("Butterfly measurement: n_samples=%d, policy=%r", n_samples, post_sel_policy)

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
        metadata: dict[str, Any] = {}

        if states is not None:
            states = np.asarray(states)

            # Validate states shape (Section 2C)
            if states.ndim != 3 or states.shape[1] != 2 or states.shape[2] != 3:
                _logger.error(
                    "Butterfly states has unexpected shape %s, expected (n_shots, 2, 3)",
                    states.shape,
                )
                metadata["diagnostics"] = f"Invalid states shape: {states.shape}"
                return AnalysisResult.from_run(result, metrics=metrics, metadata=metadata)

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

                # Propagate Lambda_M validity (Section 2E)
                lm_valid = bfly_out.get("Lambda_M_valid", True)
                metrics["Lambda_M_valid"] = bool(lm_valid)
                if not lm_valid:
                    note = bfly_out.get("note", "Lambda_M invalid")
                    metadata["diagnostics"] = note
                    _logger.warning("Butterfly Lambda_M invalid: %s", note)
                else:
                    _logger.info(
                        "Butterfly metrics: F=%.4f, Q=%.4f, V=%.4f, t01=%.4f, t10=%.4f",
                        metrics.get("F", float("nan")),
                        metrics.get("Q", float("nan")),
                        metrics.get("V", float("nan")),
                        metrics.get("t01", float("nan")),
                        metrics.get("t10", float("nan")),
                    )
            except (ValueError, np.linalg.LinAlgError) as exc:
                _logger.warning("Butterfly metrics computation failed: %s", exc)
                metadata["diagnostics"] = f"Butterfly analysis failed: {exc}"
            except Exception as exc:
                _logger.error("Unexpected error in butterfly analysis: %s", exc)
                metadata["diagnostics"] = f"Unexpected butterfly error: {exc}"

        analysis = AnalysisResult.from_run(result, metrics=metrics, metadata=metadata)

        if update_calibration and self.calibration_store and "F" in metrics:
            self.calibration_store.set_readout_quality(
                self.attr.ro_el,
                F=metrics.get("F"),
                Q=metrics.get("Q"),
                V=metrics.get("V"),
                t01=metrics.get("t01"),
                t10=metrics.get("t10"),
            )

        # T1 decay correction (Section 6D)
        if self.calibration_store and "F" in metrics:
            try:
                coherence = self.calibration_store.get_coherence(self.attr.qb_el)
                if coherence and coherence.T1 is not None and coherence.T1 > 0:
                    T1 = coherence.T1
                    # Estimate readout duration from measure macro
                    active_len = getattr(measureMacro, "active_length", lambda: None)()
                    if active_len is not None and active_len > 0:
                        t_readout = active_len * 4e-9  # clock cycles to seconds
                        decay_factor = float(np.exp(-t_readout / T1))
                        metrics["T1_decay_factor"] = decay_factor
                        if decay_factor > 0:
                            metrics["T1_corrected_F"] = float(metrics["F"] / decay_factor)
                        _logger.info(
                            "T1 decay correction: readout=%.0f ns, T1=%.1f us, factor=%.4f",
                            t_readout * 1e9, T1 * 1e6, decay_factor,
                        )
            except Exception:
                pass  # T1 correction is optional, never fail on it

        return analysis

    def plot(self, analysis: AnalysisResult, *, ax=None,
             show_histogram: bool = False, **kwargs):
        metrics = analysis.metrics
        if not any(k in metrics for k in ("F", "Q", "V")):
            return None

        n_plots = 2 if show_histogram else 1
        if ax is None:
            fig, axes = plt.subplots(1, n_plots, figsize=(8 * n_plots, 5))
            if n_plots == 1:
                axes = [axes]
        else:
            fig = ax.figure
            axes = [ax]
            if show_histogram:
                axes.append(fig.add_subplot(1, 2, 2))

        # Panel 0: F/Q/V bar chart with Wilson CI error bars (Section 4B)
        labels_frac, values_frac = [], []
        for key in ("F", "Q", "V"):
            if key in metrics:
                labels_frac.append(key)
                values_frac.append(metrics[key])

        values_pct = [v * 100 for v in values_frac]

        # Compute Wilson CI error bars
        n_shots = 0
        states = analysis.data.get("states")
        if states is not None:
            n_shots = len(np.asarray(states))
        elif analysis.source and analysis.source.metadata:
            n_shots = analysis.source.metadata.get("n_total", 0)

        if n_shots > 0:
            errors_lo, errors_hi = [], []
            for frac in values_frac:
                lo, hi = wilson_interval(frac, n_shots)
                errors_lo.append((frac - lo) * 100)
                errors_hi.append((hi - frac) * 100)
            bars = axes[0].bar(labels_frac, values_pct,
                               yerr=[errors_lo, errors_hi], capsize=5,
                               color=["steelblue", "coral", "seagreen"])
        else:
            bars = axes[0].bar(labels_frac, values_pct,
                               color=["steelblue", "coral", "seagreen"])

        for bar, val in zip(bars, values_pct):
            axes[0].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                         f"{val:.1f}%", ha="center", va="bottom", fontsize=12)

        axes[0].set_ylim(0, 110)
        axes[0].set_ylabel("Percentage (%)")
        axes[0].set_title("Butterfly Measurement Metrics")
        axes[0].grid(True, alpha=0.3, axis="y")

        # Panel 1: 2D histogram of M1 vs M2 outcomes (Section 4C)
        if show_histogram and len(axes) > 1 and states is not None:
            states_arr = np.asarray(states)
            if states_arr.ndim == 3 and states_arr.shape[1] == 2 and states_arr.shape[2] == 3:
                # Build 2x2 contingency: M1 vs M2 for ground-prepared branch
                m1 = states_arr[:, 0, 1]
                m2 = states_arr[:, 0, 2]
                contingency = np.zeros((2, 2))
                for a in (0, 1):
                    for b in (0, 1):
                        contingency[a, b] = np.sum((m1 == a) & (m2 == b))
                contingency /= max(1, len(m1))

                im = axes[1].imshow(contingency * 100, cmap="Blues", vmin=0)
                axes[1].set_xticks([0, 1])
                axes[1].set_yticks([0, 1])
                axes[1].set_xticklabels(["M2=0", "M2=1"])
                axes[1].set_yticklabels(["M1=0", "M1=1"])
                for i in range(2):
                    for j in range(2):
                        axes[1].text(j, i, f"{contingency[i, j] * 100:.1f}%",
                                     ha="center", va="center", fontsize=12)
                axes[1].set_title("M1 vs M2 (|g> prep)")
                fig.colorbar(im, ax=axes[1], shrink=0.8, label="%")

        plt.tight_layout()
        plt.show()
        return fig


class CalibrateReadoutFull(ExperimentBase):
    """End-to-end readout calibration pipeline.

    Runs in sequence:
    1. ReadoutWeightsOptimization (optional)
    2. ReadoutGEDiscrimination
    3. ReadoutButterflyMeasurement

    Supports iterative convergence (Section 3) and a unified
    :class:`ReadoutConfig` object (Section 5).
    """

    def run(
        self,
        ro_op: str | None = None,
        drive_frequency: float | None = None,
        *,
        config: ReadoutConfig | None = None,
        # Keep all existing kwargs for backward compatibility
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
        burn_rot_weights: bool = True,
        wopt_kwargs: dict | None = None,
        ge_kwargs: dict | None = None,
        bfly_kwargs: dict | None = None,
    ) -> dict:
        # Build effective config: ReadoutConfig takes precedence if supplied
        if config is not None:
            cfg = config
        else:
            cfg = ReadoutConfig(
                ro_op=ro_op or "readout",
                drive_frequency=drive_frequency,
                ro_el=ro_el,
                r180=r180,
                skip_weights_optimization=skip_weights_optimization,
                n_avg_weights=n_avg_weights,
                persist_weights=persist_weights,
                n_samples_disc=n_samples_disc,
                burn_rot_weights=burn_rot_weights,
                blob_k_g=blob_k_g,
                blob_k_e=blob_k_e,
                n_shots_butterfly=n_shots_butterfly,
                display_analysis=display_analysis,
                save=save,
                wopt_kwargs=dict(wopt_kwargs or {}),
                ge_kwargs=dict(ge_kwargs or {}),
                bfly_kwargs=dict(bfly_kwargs or {}),
            )

        # Resolve positional ro_op / drive_frequency if not in config
        eff_ro_op = cfg.ro_op
        eff_drive_freq = cfg.drive_frequency
        if ro_op is not None:
            eff_ro_op = ro_op
        if drive_frequency is not None:
            eff_drive_freq = drive_frequency
        if eff_drive_freq is None:
            raise ValueError("drive_frequency is required")

        _logger.info("CalibrateReadoutFull pipeline starting")

        results: dict[str, Any] = {}

        # Step 1: Weights optimization (runs once)
        if not cfg.skip_weights_optimization:
            _logger.info("Step 1: Weight optimization")
            wopt = ReadoutWeightsOptimization(self._ctx)
            wopt_kw = dict(cfg.wopt_kwargs)
            wopt_result = wopt.run(
                eff_ro_op, eff_drive_freq,
                cfg.cos_weight_key, cfg.sin_weight_key, cfg.m_sin_weight_key,
                r180=cfg.r180, n_avg=cfg.n_avg_weights,
                persist=cfg.persist_weights,
                revert_on_no_improvement=cfg.revert_on_no_improvement,
                **wopt_kw,
            )
            results["weights_optimization"] = wopt_result

        # Steps 2+3: Iterative discrimination + butterfly (Section 3)
        ge_kw = dict(cfg.ge_kwargs)
        bfly_kw = dict(cfg.bfly_kwargs)
        prev_fidelity = None
        iteration_results: list[dict] = []

        for iteration in range(cfg.max_iterations):
            if cfg.max_iterations > 1:
                _logger.info("Calibration iteration %d/%d", iteration + 1, cfg.max_iterations)

            # Adaptive sample count (Section 3B)
            n_disc = cfg.n_samples_disc
            if cfg.adaptive_samples and iteration == 0 and cfg.max_iterations > 1:
                n_disc = max(cfg.min_samples_disc, cfg.n_samples_disc // 4)
            elif cfg.adaptive_samples and iteration > 0 and prev_fidelity is not None:
                fid_frac = prev_fidelity / 100.0
                lo, hi = wilson_interval(fid_frac, n_disc)
                uncertainty = (hi - lo) * 100
                if uncertainty > cfg.fidelity_tolerance:
                    n_disc = min(cfg.n_samples_disc, n_disc * 2)
                    _logger.info(
                        "Increasing samples to %d (uncertainty=%.2f%%)",
                        n_disc, uncertainty,
                    )

            # Step 2: G/E discrimination
            _logger.info("Step 2: GE discrimination (n_samples=%d)", n_disc)
            ge_disc = ReadoutGEDiscrimination(self._ctx)
            ge_result = ge_disc.run(
                eff_ro_op, eff_drive_freq,
                r180=cfg.r180,
                n_samples=n_disc,
                burn_rot_weights=cfg.burn_rot_weights,
                blob_k_g=cfg.blob_k_g,
                blob_k_e=cfg.blob_k_e,
                **ge_kw,
            )

            # Step 3: Butterfly measurement
            _logger.info("Step 3: Butterfly measurement (n_shots=%d)", cfg.n_shots_butterfly)
            bfly = ReadoutButterflyMeasurement(self._ctx)
            bfly_result = bfly.run(
                r180=cfg.r180,
                n_samples=cfg.n_shots_butterfly,
                **bfly_kw,
            )

            # Extract fidelity for convergence check
            ge_analysis = ge_disc.analyze(ge_result)
            current_fidelity = ge_analysis.metrics.get("fidelity", 0.0)

            iteration_results.append({
                "ge_result": ge_result,
                "bfly_result": bfly_result,
                "fidelity": current_fidelity,
                "n_disc": n_disc,
            })

            # Check convergence (Section 3A)
            if prev_fidelity is not None and cfg.max_iterations > 1:
                delta = abs(current_fidelity - prev_fidelity)
                _logger.info(
                    "Fidelity: %.2f%% (delta=%.2f%%, tolerance=%.2f%%)",
                    current_fidelity, delta, cfg.fidelity_tolerance,
                )
                if delta < cfg.fidelity_tolerance:
                    _logger.info("Fidelity converged after %d iterations", iteration + 1)
                    break

            prev_fidelity = current_fidelity

        # Store final iteration's results
        if iteration_results:
            results["ge_discrimination"] = iteration_results[-1]["ge_result"]
            results["butterfly"] = iteration_results[-1]["bfly_result"]
        if len(iteration_results) > 1:
            results["iterations"] = iteration_results
            results["n_iterations"] = len(iteration_results)

        _logger.info("CalibrateReadoutFull pipeline complete")
        return results

    def analyze(self, result: dict, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        """Collate metrics from sub-experiment results."""
        metrics: dict[str, Any] = {}
        metadata: dict[str, Any] = {}

        # Analyze G/E discrimination stage
        ge_analysis = None
        if "ge_discrimination" in result:
            ge_disc = ReadoutGEDiscrimination(self._ctx)
            ge_analysis = ge_disc.analyze(result["ge_discrimination"],
                                          update_calibration=update_calibration, **kw)
            for k, v in ge_analysis.metrics.items():
                metrics[f"ge_{k}"] = v

        # Analyze butterfly stage
        bfly_analysis = None
        if "butterfly" in result:
            bfly = ReadoutButterflyMeasurement(self._ctx)
            bfly_analysis = bfly.analyze(result["butterfly"],
                                         update_calibration=update_calibration, **kw)
            for k, v in bfly_analysis.metrics.items():
                metrics[f"bfly_{k}"] = v

        # Store sub-analysis results in metadata for retrieval
        if ge_analysis is not None:
            metadata["ge_analysis"] = ge_analysis
        if bfly_analysis is not None:
            metadata["bfly_analysis"] = bfly_analysis
        if "n_iterations" in result:
            metrics["n_iterations"] = result["n_iterations"]

        return AnalysisResult(data={}, metrics=metrics, metadata=metadata)

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
            # butterfly_metrics returns fractions (0-1); convert to percentages
            vals = [metrics[k] * 100 for k in bfly_keys]
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
                    disc_out = two_state_discriminator(I_g, Q_g, I_e, Q_e)
                    fid = disc_out["fidelity"]
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
