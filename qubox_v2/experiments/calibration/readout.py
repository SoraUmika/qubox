"""Readout calibration experiments."""
from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any, Mapping, Tuple

import numpy as np
import matplotlib.pyplot as plt
from qm.qua import dual_demod

from ..experiment_base import ExperimentBase
from ..result import AnalysisResult, FitResult
from ...analysis import post_process as pp
from ...analysis.analysis_tools import two_state_discriminator
from ...analysis.output import Output
from ...analysis.metrics import butterfly_metrics, gaussian2D_score, wilson_interval
from ...analysis.post_selection import PostSelectionConfig
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
        qb_therm_clks = self.get_therm_clks("qb", fallback=0) or 0

        prog = cQED_programs.iq_blobs(
            attr.ro_el, attr.qb_el, r180, qb_therm_clks, n_runs,
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
                metrics["rotation_convention"] = "S_rot = S * exp(+1j*angle)"
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
        qb_therm_clks = self.get_therm_clks("qb", fallback=0) or 0

        prog = cQED_programs.readout_ge_raw_trace(
            attr.qb_el, r180, qb_therm_clks, ro_depl_clks, n_avg,
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
        *,
        r180: str = "x180",
        ro_depl_clks: int | None = None,
        n_avg: int = 100,
        process_in_sim: bool = False,
    ) -> RunResult:
        attr = self.attr
        self.hw.set_element_fq(attr.ro_el, drive_frequency)
        self.measure_macro.set_drive_frequency(drive_frequency)
        self.set_standard_frequencies()
        ro_therm_clks = self.get_therm_clks("ro", fallback=0) or 0

        resolved_weights = weights
        if isinstance(weights, (list, tuple)) and len(weights) == 3 and all(isinstance(w, str) for w in weights):
            cos_w, sin_w, m_sin_w = weights
            resolved_weights = [cos_w, sin_w, m_sin_w, cos_w]
            _logger.warning(
                "ReadoutGEIntegratedTrace.run received 3 weights; expanding to legacy 4-output form "
                "[cos, sin, m_sin, cos]. Pass 4 weights explicitly to silence this warning."
            )

        # Resolve pulse length and compute div_clks (legacy parity)
        pulseOp = self.pulse_mgr.get_pulseOp_by_element_op(attr.ro_el, ro_op)
        if pulseOp is None:
            raise RuntimeError(
                f"No pulse registered for (element={attr.ro_el!r}, op={ro_op!r}). "
                "Register the readout operation before running integrated trace."
            )
        pulse_len = int(pulseOp.length)  # in ns

        # Pre-compute valid (num_div, div_clks) pairs (legacy parity):
        #   pulse_len % d == 0  AND  (pulse_len // d) % 4 == 0
        valid_pairs = [
            (d, pulse_len // d // 4)
            for d in range(1, pulse_len + 1)
            if pulse_len % d == 0 and ((pulse_len // d) % 4 == 0)
        ]
        if not valid_pairs:
            raise ValueError(
                f"readout_ge_integrated_trace: no valid num_div for pulse_len={pulse_len} ns. "
                "pulse_len must be tileable into slices that are integer multiples of 4 ns."
            )

        if num_div is None:
            num_div = max(d for d, _ in valid_pairs)
        if num_div <= 0:
            raise ValueError(f"num_div must be > 0, got {num_div}")
        if not any(d == num_div for d, _ in valid_pairs):
            raise ValueError(
                f"readout_ge_integrated_trace: invalid num_div={num_div} for "
                f"pulse_len={pulse_len} ns. "
                f"Valid (num_div, div_clks): {valid_pairs}"
            )

        div_clks = (pulse_len // num_div) // 4

        # Legacy parity: push/restore measureMacro around program construction
        measureMacro.push_settings()
        measureMacro.set_pulse_op(pulseOp, active_op=ro_op)

        prog = cQED_programs.readout_ge_integrated_trace(
            attr.qb_el, resolved_weights, num_div, div_clks,
            r180, ro_depl_clks or ro_therm_clks, n_avg,
        )

        # Legacy parity: post-processing to create g_trace/e_trace from II/IQ/QI/QQ
        def _divide_array_in_half(arr):
            split_index = len(arr) // 2
            return arr[:split_index], arr[split_index:]

        def _post_proc(out, **_):
            II = out.get("II")
            IQ = out.get("IQ")
            QI = out.get("QI")
            QQ = out.get("QQ")
            if II is None or IQ is None or QI is None or QQ is None:
                return out

            IIg, IIe = _divide_array_in_half(np.asarray(II))
            IQg, IQe = _divide_array_in_half(np.asarray(IQ))
            QIg, QIe = _divide_array_in_half(np.asarray(QI))
            QQg, QQe = _divide_array_in_half(np.asarray(QQ))

            Ig = IIg + IQg
            Ie = IIe + IQe
            Qg = QIg + QQg
            Qe = QIe + QQe

            out["g_trace"] = Ig + 1j * Qg
            out["e_trace"] = Ie + 1j * Qe
            out["div_clks"] = div_clks
            out["num_div"] = num_div
            time_list = np.arange(div_clks * 4, pulse_len + 1, 4 * div_clks)
            out["time_list"] = time_list
            return out

        measureMacro.restore_settings()

        return self.run_program(
            prog, n_total=n_avg, process_in_sim=process_in_sim,
            processors=[_post_proc],
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
        ro_element: str | None = None,
        r180: str = "x180",
        gain: float = 1.0,
        update_measure_macro: bool = False,
        burn_rot_weights: bool = True,
        apply_rotated_weights: bool = True,
        persist: bool = False,
        n_samples: int = 10_000,
        base_weight_keys: tuple[str, str, str] | None = None,
        auto_update_postsel: bool = True,
        blob_k_g: float = 2.0,
        blob_k_e: float | None = None,
        **kwargs: Any,
    ) -> RunResult:
        attr = self.attr
        readout_element = ro_element or attr.ro_el

        legacy_update_measure = kwargs.pop("update_measureMacro", None)
        if legacy_update_measure is not None:
            update_measure_macro = bool(legacy_update_measure)

        legacy_k = kwargs.pop("k", None)
        legacy_k_g = kwargs.pop("k_g", None)
        legacy_k_e = kwargs.pop("k_e", None)

        if legacy_k_g is not None and blob_k_g == 2.0:
            blob_k_g = float(legacy_k_g)
        elif legacy_k is not None and blob_k_g == 2.0:
            blob_k_g = float(legacy_k)

        if blob_k_e is None:
            if legacy_k_e is not None:
                blob_k_e = float(legacy_k_e)
            elif legacy_k_g is not None:
                blob_k_e = float(legacy_k_g)
            elif legacy_k is not None:
                blob_k_e = float(legacy_k)
            else:
                blob_k_e = blob_k_g

        # Resolve pulse and integration weight mapping
        pulse_info = self.pulse_mgr.get_pulseOp_by_element_op(readout_element, measure_op, strict=False)
        if pulse_info is None:
            raise RuntimeError(
                f"No pulse registered for (element={readout_element!r}, op={measure_op!r}). "
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

        # Ensure measure macro uses the resolved readout element/op mapping for this run.
        # Keep both references in sync because notebook reloads can leave
        # `readout.py` and `cQED_programs.py` holding different measureMacro objects.
        macro_refs = [measureMacro]
        prog_measure_macro = getattr(cQED_programs, "measureMacro", None)
        if prog_measure_macro is not None and all(prog_measure_macro is not ref for ref in macro_refs):
            macro_refs.append(prog_measure_macro)

        for macro in macro_refs:
            # Force canonical dual-demod path for IQ blob acquisition.
            # This clears any stale sliced/per-output demodulator settings.
            macro.set_demodulator(dual_demod.full)
            macro.set_pulse_op(
                pulse_info,
                active_op=measure_op,
                weights=[[cos_key, sin_key], [m_sin_key, cos_key]],
                weight_len=pulse_info.length,
            )
            macro.set_drive_frequency(drive_frequency)

        # Store params so analyze() can build rotated weights
        self._run_params = {
            "readout_element": readout_element,
            "measure_op": measure_op,
            "burn_rot_weights": burn_rot_weights,
            "apply_rotated_weights": apply_rotated_weights,
            "update_measure_macro": update_measure_macro,
            "drive_frequency": drive_frequency,
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
        cfg_engine = getattr(self._ctx, "config_engine", None)
        qm_ops = {}
        if cfg_engine is not None:
            cfg = cfg_engine.build_qm_config()
            qm_ops = (cfg.get("elements", {}).get(readout_element, {}).get("operations", {}) or {})
        _logger.info(
            "GE discrimination mapping: element=%s op=%s pulse=%s available_ops=%s",
            readout_element,
            measure_op,
            qm_ops.get(measure_op) if qm_ops else None,
            sorted(qm_ops.keys()),
        )

        self.set_standard_frequencies()
        self.hw.set_element_fq(readout_element, drive_frequency)

        prog = cQED_programs.iq_blobs(
            readout_element, attr.qb_el, r180, attr.qb_therm_clks, n_samples,
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
                metrics["rotation_convention"] = "S_rot = S * exp(+1j*angle)"
                metrics["threshold"] = float(disc_out["threshold"])
                metrics["gg"] = float(disc_out["gg"])
                metrics["ge"] = float(disc_out["ge"])
                metrics["eg"] = float(disc_out["eg"])
                metrics["ee"] = float(disc_out["ee"])

                # Legacy-compatible rotation coefficients (phi=-angle)
                phi = -metrics["angle"]
                C = float(np.cos(phi))
                S_ = float(np.sin(phi))
                metrics["w_plus_cos"] = C
                metrics["w_plus_sin"] = -S_
                metrics["w_minus_sin"] = -S_
                metrics["w_minus_cos"] = -C

                # Additional metrics for post-selection
                for key in ("rot_mu_g", "rot_mu_e", "unrot_mu_g", "unrot_mu_e", "sigma_g", "sigma_e"):
                    if key in disc_out:
                        val = disc_out[key]
                        if isinstance(val, (complex, np.complexfloating)):
                            metrics[key] = complex(val)
                        else:
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
            apply = self._run_params.get("apply_rotated_weights", True)
            allow_inline = bool(getattr(self._ctx, "allow_inline_mutations", False))
            if apply:
                if allow_inline:
                    try:
                        self._build_rotated_weights(metrics)
                        if self._run_params.get("update_measure_macro", False):
                            self._apply_rotated_measure_macro(metrics)
                            if self._run_params.get("persist", False):
                                self._persist_measure_macro_state()
                        _logger.info("Rotated integration weights computed AND applied")
                        # Post-check: validate weights are present in config
                        validation = self.verify_rotated_weights()
                        metadata["rotated_weights_validation"] = validation
                        if validation.get("all_valid"):
                            _logger.info("Rotated weights validation PASSED")
                        else:
                            _logger.warning(
                                "Rotated weights validation FAILED: %s",
                                validation.get("errors", []),
                            )
                    except Exception as exc:
                        _logger.warning("Rotated weight construction failed: %s", exc)
                        warnings.warn(f"Rotated weight construction failed: {exc}")
                else:
                    metadata.setdefault("proposed_patch_ops", []).extend([
                        {
                            "op": "SetMeasureWeights",
                            "payload": {
                                "element": self._run_params.get("readout_element"),
                                "operation": self._run_params.get("measure_op"),
                                "weights": "rotated_from_angle",
                                "angle": metrics.get("angle"),
                            },
                        },
                        {
                            "op": "TriggerPulseRecompile",
                            "payload": {"include_volatile": True},
                        },
                    ])
                    if self._run_params.get("persist", False):
                        metadata.setdefault("proposed_patch_ops", []).append(
                            {"op": "PersistMeasureConfig", "payload": {}}
                        )
                    _logger.info("Strict mode: rotated weight/macro updates emitted as patch intent")
            else:
                _logger.info(
                    "Rotated integration weights computed (angle=%.4f rad) "
                    "but NOT applied (apply_rotated_weights=False)",
                    metrics["angle"],
                )

        # Auto-update post-selection config (legacy parity: auto_update_postsel)
        if hasattr(self, "_run_params") and self._run_params.get("auto_update_postsel", False):
            if all(k in metrics for k in ("threshold", "rot_mu_g", "rot_mu_e")):
                allow_inline = bool(getattr(self._ctx, "allow_inline_mutations", False))
                if allow_inline:
                    try:
                        blob_k_g = self._run_params.get("blob_k_g", 2.0)
                        blob_k_e = self._run_params.get("blob_k_e", blob_k_g)
                        ps_cfg = PostSelectionConfig.from_discrimination_results(
                            metrics, blob_k_g=blob_k_g, blob_k_e=blob_k_e,
                        )
                        measureMacro.set_post_select_config(ps_cfg)
                        _logger.info("Post-selection config updated from GE discrimination")
                    except Exception as exc:
                        _logger.warning("Failed to build PostSelectionConfig: %s", exc)
                else:
                    metadata.setdefault("diagnostics", "")
                    metadata["diagnostics"] = (
                        (metadata["diagnostics"] + " | ") if metadata["diagnostics"] else ""
                    ) + "Strict mode: skipped inline post-selection config update"
                    _logger.info("Strict mode: skipped inline post-selection config update")

        if update_calibration and self.calibration_store and "fidelity" in metrics:
            min_fidelity = float(kw.get("min_fidelity", 70.0))
            max_abs_angle = float(kw.get("max_abs_angle", np.pi))
            self.guarded_calibration_commit(
                analysis=analysis,
                run_result=result,
                calibration_tag="readout_ge_discrimination",
                require_fit=False,
                required_metrics={
                    "fidelity": (min_fidelity, 100.0),
                    "angle": (-max_abs_angle, max_abs_angle),
                },
                apply_update=lambda: self.calibration_store.set_discrimination(
                    self.attr.ro_el,
                    angle=metrics.get("angle"),
                    threshold=metrics.get("threshold"),
                    fidelity=metrics.get("fidelity"),
                    mu_g=[
                        float(np.real(metrics.get("rot_mu_g", 0.0 + 0.0j))),
                        float(np.imag(metrics.get("rot_mu_g", 0.0 + 0.0j))),
                    ],
                    mu_e=[
                        float(np.real(metrics.get("rot_mu_e", 0.0 + 0.0j))),
                        float(np.imag(metrics.get("rot_mu_e", 0.0 + 0.0j))),
                    ],
                    sigma_g=metrics.get("sigma_g"),
                    sigma_e=metrics.get("sigma_e"),
                ),
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
            C, S = np.cos(angle), np.sin(angle)
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

    def _apply_rotated_measure_macro(self, metrics: dict) -> None:
        """Update measureMacro with legacy-compatible rotated labels.

        Discrimination params are proposed via ``proposed_patch_ops`` in the
        analysis metadata rather than mutated directly on the singleton.
        """
        params = self._run_params
        pulse_info = params["pulse_info"]
        measure_op = params["measure_op"]
        drive_frequency = params["drive_frequency"]
        op_prefix = params["op_prefix"]

        def _name(prefix, suffix):
            return suffix if not prefix else f"{prefix}{suffix}"

        map_rot_cos = _name(op_prefix, "rot_cos")
        map_rot_sin = _name(op_prefix, "rot_sin")
        map_rot_m_sin = _name(op_prefix, "rot_m_sin")

        try:
            macro_refs = [measureMacro]
            prog_measure_macro = getattr(cQED_programs, "measureMacro", None)
            if prog_measure_macro is not None and all(prog_measure_macro is not ref for ref in macro_refs):
                macro_refs.append(prog_measure_macro)

            for mm in macro_refs:
                mm.set_pulse_op(
                    pulse_info,
                    active_op=measure_op,
                    weights=([map_rot_cos, map_rot_sin], [map_rot_m_sin, map_rot_cos]),
                    weight_len=pulse_info.length,
                )
                mm.set_drive_frequency(drive_frequency)
            _logger.info("measureMacro updated with rotated readout weights")
        except Exception as exc:
            _logger.warning("Failed to update measureMacro with rotated weights: %s", exc)

    def _persist_measure_macro_state(self) -> None:
        """Persist measureMacro via CalibrationOrchestrator patch application.

        Uses the ``PersistMeasureConfig`` patch operation rather than
        writing ``measureConfig.json`` directly from experiment code.
        """
        if hasattr(self, "_ctx") and hasattr(self._ctx, "calibration_orchestrator"):
            try:
                from ...calibration.contracts import Patch
                patch = Patch(reason="persist_measure_macro_state")
                patch.add("PersistMeasureConfig")
                self._ctx.calibration_orchestrator.apply_patch(patch)
                _logger.info("Persisted measureMacro state via orchestrator patch")
            except Exception as exc:
                _logger.warning("Failed to persist measureMacro via orchestrator: %s — falling back to direct save", exc)
                self._persist_measure_macro_state_direct()
        else:
            self._persist_measure_macro_state_direct()

    def _persist_measure_macro_state_direct(self) -> None:
        """Fallback: persist measureMacro directly (legacy path)."""
        exp_path = Path(getattr(self._ctx, "experiment_path", "."))
        dst = exp_path / "config" / "measureConfig.json"
        dst.parent.mkdir(parents=True, exist_ok=True)
        measureMacro.save_json(str(dst))
        _logger.info("Persisted measureMacro state to %s (direct)", dst)

    def verify_rotated_weights(self) -> dict[str, Any]:
        """Validate that rotated integration weights are properly applied.

        Checks:
        1. Weight definitions exist in the PulseOperationManager store.
        2. The measurement pulse mapping references the rotated labels.
        3. The built QM config includes the weight definitions.

        Returns
        -------
        dict
            Validation report with keys:
            - ``all_valid`` (bool): True if all checks pass.
            - ``weights_in_store`` (dict[str, bool]): per-weight existence.
            - ``weights_in_mapping`` (dict[str, bool]): per-label in pulse mapping.
            - ``weights_in_config`` (dict[str, bool]): per-weight in QM config.
            - ``errors`` (list[str]): human-readable error descriptions.
            - ``before_labels`` / ``after_labels``: base vs rotated label names.
        """
        if not hasattr(self, "_run_params"):
            return {"all_valid": False, "errors": ["No _run_params: run() was not called"]}

        params = self._run_params
        op_prefix = params["op_prefix"]
        pulse_info = params["pulse_info"]

        def _name(prefix, suffix):
            return suffix if not prefix else f"{prefix}{suffix}"

        rot_names = {
            "rot_cos": _name(op_prefix, "rot_cos"),
            "rot_sin": _name(op_prefix, "rot_sin"),
            "rot_m_sin": _name(op_prefix, "rot_m_sin"),
        }
        base_names = {
            "cos": params["base_cos_name"],
            "sin": params["base_sin_name"],
            "m_sin": params["base_m_sin_name"],
        }

        pm = self.pulse_mgr
        errors: list[str] = []

        # 1. Check weights exist in pulse manager store
        weights_in_store = {}
        for label, wname in rot_names.items():
            try:
                segs = pm.get_integration_weights(wname, strict=True)
                weights_in_store[wname] = True
            except (KeyError, Exception):
                weights_in_store[wname] = False
                errors.append(f"Weight '{wname}' not found in PulseOperationManager store")

        # 2. Check pulse mapping includes rotated labels
        weights_in_mapping = {}
        current_info = pm.get_pulseOp_by_element_op(
            self.attr.ro_el, params["measure_op"], strict=False,
        )
        if current_info and current_info.int_weights_mapping:
            mapping = current_info.int_weights_mapping
            for label, wname in rot_names.items():
                lbl = _name(op_prefix, label)
                found = lbl in mapping and mapping[lbl] == wname
                weights_in_mapping[lbl] = found
                if not found:
                    errors.append(
                        f"Pulse mapping missing or mismatched for label '{lbl}' "
                        f"(expected -> '{wname}')"
                    )
        else:
            errors.append("Could not retrieve pulse info to check mapping")

        # 3. Check compiled QM config (if available)
        weights_in_config = {}
        config = getattr(self.hw, "_config", None)
        if config is None:
            ce = getattr(self._ctx, "config_engine", None)
            if ce:
                config = getattr(ce, "config", None)
        if config and isinstance(config, dict):
            iw_section = config.get("integration_weights", {})
            for label, wname in rot_names.items():
                found = wname in iw_section
                weights_in_config[wname] = found
                if not found:
                    errors.append(
                        f"Weight '{wname}' not found in compiled QM config"
                    )
        else:
            # Config not accessible — not an error per se
            for wname in rot_names.values():
                weights_in_config[wname] = None  # unknown

        all_valid = len(errors) == 0
        report = {
            "all_valid": all_valid,
            "before_labels": base_names,
            "after_labels": rot_names,
            "weights_in_store": weights_in_store,
            "weights_in_mapping": weights_in_mapping,
            "weights_in_config": weights_in_config,
            "errors": errors,
        }

        if all_valid:
            _logger.info(
                "Rotated weight verification: PASSED. "
                "Active weights: %s", rot_names,
            )
        else:
            _logger.warning(
                "Rotated weight verification: %d issue(s). %s",
                len(errors), "; ".join(errors),
            )

        return report

    def plot(self, analysis: AnalysisResult, *, ax=None,
             show_rotated: bool = True, show_histogram: bool = True,
             interactive: bool = False, **kwargs):
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
        has_histogram = has_rotation and show_histogram
        n_plots = 2  # always: scatter + confusion
        if has_rotation:
            n_plots += 1  # rotated scatter
        if has_histogram:
            n_plots += 1  # histogram

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

        # Compute rotated blobs (shared by panels 2 and 3)
        Sg_rot, Se_rot = None, None
        if has_rotation:
            angle = analysis.metrics["angle"]
            threshold = analysis.metrics.get("threshold", 0.0)

            Sg_rot = analysis.data.get("Sg_rot")
            Se_rot = analysis.data.get("Se_rot")
            if Sg_rot is None or Se_rot is None:
                rot = np.exp(1j * angle)
                Sg_rot = np.asarray(S_g) * rot
                Se_rot = np.asarray(S_e) * rot

        # Panel 2: Rotated IQ blobs with threshold line (Section 4A)
        panel_idx = 2
        if has_rotation:
            axes[panel_idx].scatter(np.real(Sg_rot), np.imag(Sg_rot), s=1, alpha=0.2, c="blue", label="|g>")
            axes[panel_idx].scatter(np.real(Se_rot), np.imag(Se_rot), s=1, alpha=0.2, c="red", label="|e>")
            axes[panel_idx].axvline(x=threshold, color="k", ls="--", lw=1.5, label=f"thr={threshold:.4g}")
            axes[panel_idx].set_title("Rotated IQ + Threshold")
            axes[panel_idx].set_xlabel("I_rot")
            axes[panel_idx].set_ylabel("Q_rot")
            axes[panel_idx].legend()
            axes[panel_idx].set_aspect("equal", adjustable="datalim")
            axes[panel_idx].grid(True, alpha=0.3)
            panel_idx += 1

        # Panel 3: Rotated-I histogram (legacy parity: two_state_discriminator hist)
        if has_histogram and Sg_rot is not None and Se_rot is not None:
            Ig_rot = np.real(Sg_rot)
            Ie_rot = np.real(Se_rot)
            mu_g = analysis.metrics.get("rot_mu_g")
            mu_e = analysis.metrics.get("rot_mu_e")
            mu_g_I = float(np.real(mu_g)) if mu_g is not None else float(np.mean(Ig_rot))
            mu_e_I = float(np.real(mu_e)) if mu_e is not None else float(np.mean(Ie_rot))

            axes[panel_idx].hist(Ig_rot, bins=100, alpha=0.75, color="blue", label=r"$|g\rangle$")
            axes[panel_idx].hist(Ie_rot, bins=100, alpha=0.75, color="red", label=r"$|e\rangle$")
            axes[panel_idx].axvline(x=threshold, ls="--", color="k", alpha=0.6, label=f"$I_{{thr}}={threshold:.4g}$")
            axes[panel_idx].axvline(x=mu_g_I, ls="-.", color="blue", alpha=0.8, label=rf"$\mu_g={mu_g_I:.4g}$")
            axes[panel_idx].axvline(x=mu_e_I, ls="-.", color="red", alpha=0.8, label=rf"$\mu_e={mu_e_I:.4g}$")
            axes[panel_idx].set_xlabel(r"$I_\mathrm{rot}$")
            axes[panel_idx].set_ylabel("Counts")
            axes[panel_idx].set_title(r"$I_\mathrm{rot}$ Histogram")
            axes[panel_idx].legend(loc="best")
            axes[panel_idx].ticklabel_format(style="sci", axis="x", scilimits=(0, 0))

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
            rot = np.exp(1j * angle)
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
        cand = (_name(prefix, "cos"), _name(prefix, "sin"), _name(prefix, "minus_sin"))
        if all(k in mapping for k in cand):
            return cand

        # Canonical, unprefixed
        cand_un = ("cos", "sin", "minus_sin")
        if all(k in mapping for k in cand_un):
            return cand_un

        # Legacy, prefixed
        legacy = (_name(prefix, "rot_cos"), _name(prefix, "rot_sin"), _name(prefix, "rot_m_sin"))
        if all(k in mapping for k in legacy):
            return legacy

        # Legacy, unprefixed
        legacy_un = ("rot_cos", "rot_sin", "rot_m_sin")
        if all(k in mapping for k in legacy_un):
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
        self.measure_macro.set_drive_frequency(drive_frequency)
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
        trace_weights = [cos_w_key, sin_w_key, m_sin_w_key, cos_w_key]
        result = trace_exp.run(
            ro_op, drive_frequency, trace_weights,
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
        g_trace = np.asarray(g_trace)
        e_trace = np.asarray(e_trace)
        ge_diff = e_trace - g_trace
        ge_diff_norm = self._normalize_complex_array(ge_diff)

        metrics["trace_length"] = int(len(ge_diff))
        metrics["ge_diff_norm_max"] = float(np.max(np.abs(ge_diff_norm)))
        # Store computed traces for plotting (legacy parity)
        metrics["ge_diff"] = ge_diff
        metrics["ge_diff_norm"] = ge_diff_norm

        # Ensure traces are available to plot() via metadata
        # (analysis.data may not contain them if Output.__iter__ skips non-standard keys)
        metadata["g_trace"] = g_trace
        metadata["e_trace"] = e_trace
        metadata["time_list"] = result.output.get("time_list")

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
                allow_inline = bool(getattr(self._ctx, "allow_inline_mutations", False))
                if allow_inline:
                    self._register_optimized_weights(
                        seg_cosine_cos, seg_cosine_sin,
                        seg_sine_cos, seg_sine_sin,
                        seg_minus_sin_cos, seg_minus_sin_sin,
                        div_clks,
                    )
                    _logger.info("Optimised segmented weights registered in PulseOperationManager")
                else:
                    params = self._run_params
                    opt_cos_label = f"opt_{params['cos_w_key']}"
                    opt_sin_label = f"opt_{params['sin_w_key']}"
                    opt_m_sin_label = f"opt_{params['m_sin_w_key']}"
                    metadata.setdefault("proposed_patch_ops", []).append(
                        {
                            "op": "SetMeasureWeights",
                            "payload": {
                                "element": self.attr.ro_el,
                                "operation": params.get("ro_op"),
                                "weights": {
                                    opt_cos_label: {"cos": seg_cosine_cos, "sin": seg_cosine_sin},
                                    opt_sin_label: {"cos": seg_sine_cos, "sin": seg_sine_sin},
                                    opt_m_sin_label: {"cos": seg_minus_sin_cos, "sin": seg_minus_sin_sin},
                                },
                            },
                        }
                    )
                    metadata.setdefault("proposed_patch_ops", []).append(
                        {"op": "TriggerPulseRecompile", "payload": {"include_volatile": True}}
                    )
                    _logger.info("Strict mode: optimized weight registration emitted as patch intent")
            except Exception as exc:
                _logger.error("Weight registration failed: %s", exc)
                metadata["diagnostics"] = f"Weight registration failed: {exc}"

        # Store optimized weight keys in metrics (legacy parity)
        if hasattr(self, "_run_params"):
            params = self._run_params
            metrics["opt_cos_key"] = f"opt_{params['cos_w_key']}"
            metrics["opt_sin_key"] = f"opt_{params['sin_w_key']}"
            metrics["opt_m_sin_key"] = f"opt_{params['m_sin_w_key']}"

        # Weight version tracking (Section 1D)
        if update_calibration and self.calibration_store:
            allow_inline = bool(getattr(self._ctx, "allow_inline_mutations", False))
            if allow_inline:
                self.calibration_store.store_weight_snapshot(
                    self.attr.ro_el,
                    {"ge_diff_norm_max": metrics["ge_diff_norm_max"],
                     "trace_length": metrics["trace_length"]},
                )
            else:
                metadata.setdefault("proposed_patch_ops", []).append(
                    {
                        "op": "SetCalibration",
                        "payload": {
                            "path": f"discrimination.{self.attr.ro_el}.weight_snapshot",
                            "value": {
                                "ge_diff_norm_max": metrics["ge_diff_norm_max"],
                                "trace_length": metrics["trace_length"],
                            },
                        },
                    }
                )
                _logger.info("Strict mode: weight snapshot emitted as patch intent")

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
        g_trace = analysis.data.get("g_trace")
        e_trace = analysis.data.get("e_trace")
        time_list = analysis.data.get("time_list")

        # Fall back to metadata if traces are not in data
        if g_trace is None and analysis.metadata:
            g_trace = analysis.metadata.get("g_trace")
        if e_trace is None and analysis.metadata:
            e_trace = analysis.metadata.get("e_trace")
        if time_list is None and analysis.metadata:
            time_list = analysis.metadata.get("time_list")

        ge_diff_norm = analysis.metrics.get("ge_diff_norm")
        ge_diff = analysis.metrics.get("ge_diff")

        if g_trace is None or e_trace is None:
            return None

        g_trace = np.asarray(g_trace)
        e_trace = np.asarray(e_trace)

        # Build time axis: prefer stored time_list, else use index
        if time_list is not None:
            t = np.asarray(time_list)
        else:
            t = np.arange(len(g_trace))

        if ax is None:
            fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(14, 5))
        else:
            fig = ax.figure
            ax1, ax2, ax3 = ax, fig.add_subplot(132), fig.add_subplot(133)

        # Panel 1: ground trace (legacy parity)
        ax1.plot(t, g_trace.real, label="real")
        ax1.plot(t, g_trace.imag, label="imag")
        ax1.set_title("ground trace")
        ax1.set_xlabel("time [ns]")
        ax1.set_ylabel("demod [a.u.]")
        ax1.legend()

        # Panel 2: excited trace (legacy parity)
        ax2.plot(t, e_trace.real, label="real")
        ax2.plot(t, e_trace.imag, label="imag")
        ax2.set_title("excited trace")
        ax2.set_xlabel("time [ns]")
        ax2.set_ylabel("demod [a.u.]")
        ax2.legend()

        # Panel 3: normalized vs unnormalized ge_diff (legacy parity)
        if ge_diff_norm is not None:
            ge_diff_norm = np.asarray(ge_diff_norm)
            l1 = ax3.plot(t, ge_diff_norm.real, label="Re (norm)")
            l2 = ax3.plot(t, ge_diff_norm.imag, label="Im (norm)")
            ax3.set_title(r"|e$\rangle$ $-$ |g$\rangle$ (normalized)")
            ax3.set_xlabel("time [ns]")
            ax3.set_ylabel("norm diff [a.u.]")

            if ge_diff is not None:
                ge_diff = np.asarray(ge_diff)
                ax3b = ax3.twinx()
                l3 = ax3b.plot(t, ge_diff.real, "--", label="Re (unnorm)")
                l4 = ax3b.plot(t, ge_diff.imag, "--", label="Im (unnorm)")
                ax3b.set_ylabel("unnorm diff [a.u.]")
                lines = l1 + l2 + l3 + l4
                labels = [ln.get_label() for ln in lines]
                ax3.legend(lines, labels, loc="best")
            else:
                ax3.legend()
        else:
            ax3.set_title("ge diff (not available)")

        plt.tight_layout()
        plt.show()
        return fig


class ReadoutButterflyMeasurement(ExperimentBase):
    """Three-measurement butterfly protocol for F, Q, and QND metrics."""

    def run(
        self,
        prep_policy: str | None = None,
        prep_kwargs: dict | None = None,
        k: float | None = None,
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

        sync_info: dict[str, Any] = {
            "requested": bool(update_measure_macro),
            "applied": False,
            "reason": "not_requested",
        }
        if update_measure_macro:
            sync_info = self._sync_measure_macro_from_current_mapping(prefer_rotated=True)
            if sync_info.get("applied"):
                _logger.info(
                    "Butterfly measureMacro sync applied: element=%s op=%s weights=%s",
                    sync_info.get("element"),
                    sync_info.get("operation"),
                    sync_info.get("weights"),
                )
            else:
                _logger.warning(
                    "Butterfly measureMacro sync not applied: %s",
                    sync_info.get("reason", "unknown"),
                )

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

        if k is not None:
            k_val = float(k)
            policy_norm = str(post_sel_policy).upper()
            if policy_norm == "ZSCORE":
                post_sel_kwargs.setdefault("k", k_val)
            elif policy_norm == "BLOBS":
                if (
                    "rg2" not in post_sel_kwargs
                    and "re2" not in post_sel_kwargs
                    and "sigma_g" in post_sel_kwargs
                    and "sigma_e" in post_sel_kwargs
                ):
                    sigma_g = float(post_sel_kwargs["sigma_g"])
                    sigma_e = float(post_sel_kwargs["sigma_e"])
                    post_sel_kwargs["rg2"] = float((k_val * sigma_g) ** 2)
                    post_sel_kwargs["re2"] = float((k_val * sigma_e) ** 2)

        self._show_analysis = show_analysis
        self._run_params = {
            "post_sel_policy": post_sel_policy,
            "post_sel_kwargs": dict(post_sel_kwargs),
            "measure_macro_sync": dict(sync_info),
            "update_measure_macro": bool(update_measure_macro),
        }

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

    @staticmethod
    def _pick_weight_triplet(weight_mapping: dict[str, str], op_prefix: str) -> tuple[str, str, str] | None:
        def _name(prefix: str, suffix: str) -> str:
            return suffix if not prefix else f"{prefix}{suffix}"

        candidates = [
            (_name(op_prefix, "rot_cos"), _name(op_prefix, "rot_sin"), _name(op_prefix, "rot_m_sin")),
            ("rot_cos", "rot_sin", "rot_m_sin"),
            (_name(op_prefix, "cos"), _name(op_prefix, "sin"), _name(op_prefix, "minus_sin")),
            ("cos", "sin", "minus_sin"),
        ]
        for triplet in candidates:
            if all(k in weight_mapping for k in triplet):
                return triplet
        return None

    def _sync_measure_macro_from_current_mapping(self, *, prefer_rotated: bool = True) -> dict[str, Any]:
        _ = prefer_rotated  # kept for API clarity
        try:
            element = measureMacro.active_element()
        except Exception:
            element = self.attr.ro_el

        try:
            operation = measureMacro.active_op()
        except Exception:
            operation = "readout"

        pulse_info = self.pulse_mgr.get_pulseOp_by_element_op(element, operation, strict=False)
        if pulse_info is None:
            return {
                "requested": True,
                "applied": False,
                "reason": f"No pulse mapping for element={element!r}, op={operation!r}",
                "element": element,
                "operation": operation,
            }

        weight_mapping = pulse_info.int_weights_mapping or {}
        if not isinstance(weight_mapping, dict):
            weight_mapping = {}

        is_readout = (pulse_info.op == "readout")
        op_prefix = "" if is_readout else f"{pulse_info.op}_"
        triplet = self._pick_weight_triplet(weight_mapping, op_prefix)
        if triplet is None:
            return {
                "requested": True,
                "applied": False,
                "reason": f"No compatible weight labels found. Available: {sorted(weight_mapping.keys())}",
                "element": element,
                "operation": operation,
            }

        cos_key, sin_key, m_sin_key = triplet
        macro_refs = [measureMacro]
        prog_measure_macro = getattr(cQED_programs, "measureMacro", None)
        if prog_measure_macro is not None and all(prog_measure_macro is not ref for ref in macro_refs):
            macro_refs.append(prog_measure_macro)

        drive_frequency = measureMacro.get_drive_frequency()
        for mm in macro_refs:
            mm.set_pulse_op(
                pulse_info,
                active_op=operation,
                weights=[[cos_key, sin_key], [m_sin_key, cos_key]],
                weight_len=pulse_info.length,
            )
            if drive_frequency is not None:
                mm.set_drive_frequency(drive_frequency)

        return {
            "requested": True,
            "applied": True,
            "reason": "ok",
            "element": element,
            "operation": operation,
            "pulse": pulse_info.pulse,
            "weights": [cos_key, sin_key, m_sin_key],
        }

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        import pandas as pd

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

            # Extract boolean measurement outcomes (legacy parity)
            m0_g = states[:, 0, 0].astype(bool)
            m0_e = states[:, 1, 0].astype(bool)
            m1_g = states[:, 0, 1].astype(bool)
            m1_e = states[:, 1, 1].astype(bool)
            m2_g = states[:, 0, 2].astype(bool)
            m2_e = states[:, 1, 2].astype(bool)

            # Extract IQ data per measurement (legacy parity)
            # QUA program saves I0/Q0/I1/Q1/I2/Q2 as (n_shots, 2_branches)
            I0 = result.output.get("I0")
            Q0 = result.output.get("Q0")
            I1 = result.output.get("I1")
            Q1 = result.output.get("Q1")
            I2 = result.output.get("I2")
            Q2 = result.output.get("Q2")

            has_iq = all(x is not None for x in (I0, Q0, I1, Q1, I2, Q2))
            if has_iq:
                I0, Q0 = np.asarray(I0), np.asarray(Q0)
                I1, Q1 = np.asarray(I1), np.asarray(Q1)
                I2, Q2 = np.asarray(I2), np.asarray(Q2)

                # Build complex IQ blobs per measurement per branch (legacy parity)
                S0_g = I0[:, 0] + 1j * Q0[:, 0]
                S0_e = I0[:, 1] + 1j * Q0[:, 1]
                S1_g = I1[:, 0] + 1j * Q1[:, 0]
                S1_e = I1[:, 1] + 1j * Q1[:, 1]
                S2_g = I2[:, 0] + 1j * Q2[:, 0]
                S2_e = I2[:, 1] + 1j * Q2[:, 1]

                metrics["S0_g"] = S0_g
                metrics["S0_e"] = S0_e
                metrics["S1_g"] = S1_g
                metrics["S1_e"] = S1_e
                metrics["S2_g"] = S2_g
                metrics["S2_e"] = S2_e

            # Store boolean outcomes (legacy parity)
            metrics["m0_g"] = m0_g
            metrics["m0_e"] = m0_e
            metrics["m1_g"] = m1_g
            metrics["m1_e"] = m1_e
            metrics["m2_g"] = m2_g
            metrics["m2_e"] = m2_e

            # Per-measurement outcome probabilities (legacy parity)
            P0_g = float(1.0 - np.mean(m0_g))   # P(ground | ground prep, M0)
            P0_e = float(np.mean(m0_e))           # P(excited | excited prep, M0)
            P1_g = float(1.0 - np.mean(m1_g))   # P(ground | ground prep, M1)
            P1_e = float(np.mean(m1_e))           # P(excited | excited prep, M1)
            P2_g = float(1.0 - np.mean(m2_g))   # P(ground | ground prep, M2)
            P2_e = float(np.mean(m2_e))           # P(excited | excited prep, M2)

            butterfly_df = pd.DataFrame(
                {
                    "Ground (g)": [P0_g, P1_g, P2_g],
                    "Excited (e)": [P0_e, P1_e, P2_e],
                },
                index=["m0", "m1", "m2"],
            )
            metrics["butterfly_df"] = butterfly_df

            try:
                bfly_out = butterfly_metrics(m1_g, m1_e, m2_g, m2_e)
                metrics["F"] = float(bfly_out["F"])
                metrics["Q"] = float(bfly_out["Q"])
                metrics["V"] = float(bfly_out["V"])
                if "t01" in bfly_out:
                    metrics["t01"] = float(bfly_out["t01"])
                if "t10" in bfly_out:
                    metrics["t10"] = float(bfly_out["t10"])
                if "confusion_matrix" in bfly_out:
                    metrics["confusion_matrix"] = bfly_out["confusion_matrix"]
                if "transition_matrix" in bfly_out:
                    metrics["transition_matrix"] = bfly_out["transition_matrix"]

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

            # Extract acceptance statistics (legacy parity)
            acceptance_rate = result.output.get("acceptance_rate")
            average_tries = result.output.get("average_tries")
            if acceptance_rate is not None:
                metrics["acceptance_rate"] = float(np.mean(acceptance_rate))
            if average_tries is not None:
                metrics["average_tries"] = float(np.mean(average_tries))

        analysis = AnalysisResult.from_run(result, metrics=metrics, metadata=metadata)

        if update_calibration and self.calibration_store and "F" in metrics:
            min_F = float(kw.get("min_F", 0.50))
            min_Q = float(kw.get("min_Q", 0.50))
            self.guarded_calibration_commit(
                analysis=analysis,
                run_result=result,
                calibration_tag="readout_butterfly",
                require_fit=False,
                required_metrics={
                    "F": (min_F, 1.0),
                    "Q": (min_Q, 1.0),
                },
                apply_update=lambda: self.calibration_store.set_readout_quality(
                    self.attr.ro_el,
                    F=metrics.get("F"),
                    Q=metrics.get("Q"),
                    V=metrics.get("V"),
                    t01=metrics.get("t01"),
                    t10=metrics.get("t10"),
                ),
            )

        if hasattr(self, "_run_params") and self._run_params.get("update_measure_macro", False):
            # Emit proposed patch ops for readout quality update on measureMacro.
            # The CalibrationOrchestrator will apply these via SetMeasureQuality
            # rather than directly mutating the singleton from analyze().
            quality_payload: dict[str, Any] = {}
            for key in ("alpha", "beta", "F", "Q", "V", "t01", "t10"):
                if key in metrics:
                    quality_payload[key] = metrics[key]
            if "confusion_matrix" in metrics:
                quality_payload["confusion_matrix"] = metrics["confusion_matrix"]
            if "transition_matrix" in metrics:
                quality_payload["transition_matrix"] = metrics["transition_matrix"]
            if quality_payload:
                metadata.setdefault("proposed_patch_ops", []).append(
                    {
                        "op": "SetMeasureQuality",
                        "payload": quality_payload,
                    }
                )
            for key in ("F", "Q", "V", "t01", "t10"):
                if key in metrics:
                    metadata.setdefault("proposed_patch_ops", []).append(
                        {
                            "op": "SetCalibration",
                            "payload": {
                                "path": f"readout_quality.{self.attr.ro_el}.{key}",
                                "value": metrics.get(key),
                            },
                        }
                    )
            _logger.info("Butterfly readout-quality updates emitted as patch ops")

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

        # Legacy parity: show_analysis prints metrics and triggers discriminator plots
        show_analysis = kw.get("show_analysis", getattr(self, "_show_analysis", False))
        if show_analysis:
            # Print headline metrics (legacy parity)
            if "F" in metrics:
                print(f"Fidelity of M1: {metrics['F']:.4f}")
            if "Q" in metrics:
                print(f"QND-ness of M1: {metrics['Q']:.4f}")
            if "V" in metrics:
                print(f"Visibility of M1: {metrics['V']:.4f}")

            # Print probability table (legacy parity)
            if "butterfly_df" in metrics:
                print("\nSingle-shot outcome probabilities P(m_k | state_i):")
                try:
                    print(metrics["butterfly_df"].to_markdown(floatfmt=".4f"))
                except Exception:
                    print(metrics["butterfly_df"])

            # Print confusion matrix (legacy parity)
            if "confusion_matrix" in metrics:
                print("\nMeasurement confusion matrix Lambda_M = P(m1 | state_i):")
                cm = metrics["confusion_matrix"]
                try:
                    print(cm.to_markdown(floatfmt=".4f") if hasattr(cm, "to_markdown") else cm)
                except Exception:
                    print(cm)

            # Print transition matrix (legacy parity)
            if "transition_matrix" in metrics:
                print("\nPost-measurement transition matrix T = P(state_o | state_i):")
                tm = metrics["transition_matrix"]
                try:
                    print(tm.to_markdown(floatfmt=".4f") if hasattr(tm, "to_markdown") else tm)
                except Exception:
                    print(tm)

            # Print acceptance statistics (legacy parity)
            if "acceptance_rate" in metrics:
                print(f"\nacceptance rate: {metrics['acceptance_rate']:.4f}")
            if "average_tries" in metrics:
                print(f"average tries: {metrics['average_tries']:.2f}")

            # M0/M1/M2 discriminator plots (legacy parity)
            if all(k in metrics for k in ("S0_g", "S0_e", "S1_g", "S1_e", "S2_g", "S2_e")):
                try:
                    two_state_discriminator(
                        metrics["S0_g"].real, metrics["S0_g"].imag,
                        metrics["S0_e"].real, metrics["S0_e"].imag,
                        b_plot=True, plots=("raw_blob", "hist"), fig_title="M0 analysis",
                    )
                    two_state_discriminator(
                        metrics["S1_g"].real, metrics["S1_g"].imag,
                        metrics["S1_e"].real, metrics["S1_e"].imag,
                        b_plot=True, plots=("rot_blob", "hist", "info"), fig_title="M1 analysis",
                    )
                    two_state_discriminator(
                        metrics["S2_g"].real, metrics["S2_g"].imag,
                        metrics["S2_e"].real, metrics["S2_e"].imag,
                        b_plot=True, plots=("rot_blob", "hist", "info"), fig_title="M2 analysis",
                    )
                except Exception as exc:
                    _logger.warning("M0/M1/M2 discriminator plots skipped: %s", exc)

        return analysis

    def plot(self, analysis: AnalysisResult, *, ax=None,
             show_discriminator: bool = True, **kwargs):
        """Plot M0/M1/M2 discriminator analysis.

        Legacy parity: butterfly metrics (F, Q, V, tables) are printed
        by ``analyze(show_analysis=True)``, not plotted here.
        """
        metrics = analysis.metrics

        # M0/M1/M2 two-state discriminator plots (legacy parity)
        if show_discriminator:
            S0_g = metrics.get("S0_g")
            S0_e = metrics.get("S0_e")
            S1_g = metrics.get("S1_g")
            S1_e = metrics.get("S1_e")
            S2_g = metrics.get("S2_g")
            S2_e = metrics.get("S2_e")

            if all(x is not None for x in (S0_g, S0_e, S1_g, S1_e, S2_g, S2_e)):
                try:
                    two_state_discriminator(
                        S0_g.real, S0_g.imag, S0_e.real, S0_e.imag,
                        b_plot=True, plots=("raw_blob", "hist"),
                        fig_title="M0 analysis",
                    )
                    two_state_discriminator(
                        S1_g.real, S1_g.imag, S1_e.real, S1_e.imag,
                        b_plot=True, plots=("rot_blob", "hist", "info"),
                        fig_title="M1 analysis",
                    )
                    two_state_discriminator(
                        S2_g.real, S2_g.imag, S2_e.real, S2_e.imag,
                        b_plot=True, plots=("rot_blob", "hist", "info"),
                        fig_title="M2 analysis",
                    )
                except Exception as exc:
                    _logger.warning("M0/M1/M2 discriminator plots skipped: %s", exc)

        return None


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
        blob_k_g: float = 2.0,
        blob_k_e: float | None = None,
        k: float | None = None,
        M0_MAX_TRIALS: int = 16,
        burn_rot_weights: bool = True,
        wopt_kwargs: dict | None = None,
        ge_kwargs: dict | None = None,
        bfly_kwargs: dict | None = None,
    ) -> dict:
        k_value = float(k) if k is not None else None
        effective_blob_k_g = blob_k_g
        effective_blob_k_e = blob_k_e
        if k_value is not None and blob_k_g == 2.0:
            effective_blob_k_g = k_value
        if effective_blob_k_e is None and k_value is not None:
            effective_blob_k_e = k_value

        # Build effective config: ReadoutConfig takes precedence if supplied
        if config is not None:
            cfg = config
            cfg_k = float(cfg.k) if getattr(cfg, "k", None) is not None else None
            if cfg_k is not None and cfg.blob_k_g == 2.0:
                cfg.blob_k_g = cfg_k
            if cfg.blob_k_e is None and cfg_k is not None:
                cfg.blob_k_e = cfg_k
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
                blob_k_g=effective_blob_k_g,
                blob_k_e=effective_blob_k_e,
                k=k_value,
                n_shots_butterfly=n_shots_butterfly,
                M0_MAX_TRIALS=M0_MAX_TRIALS,
                display_analysis=display_analysis,
                save=save,
                wopt_kwargs=dict(wopt_kwargs or {}),
                ge_kwargs=dict(ge_kwargs or {}),
                bfly_kwargs=dict(bfly_kwargs or {}),
            )

        cfg.validate()

        # Resolve positional ro_op / drive_frequency if not in config
        eff_ro_op = cfg.resolved_ro_op()
        eff_drive_freq = cfg.drive_frequency
        if ro_op is not None:
            eff_ro_op = ro_op
        if drive_frequency is not None:
            eff_drive_freq = drive_frequency
        if eff_drive_freq is None:
            raise ValueError("drive_frequency is required")

        _logger.info("CalibrateReadoutFull pipeline starting")

        results: dict[str, Any] = {}

        # Default weight keys (overwritten if weight optimization runs)
        opt_cos_key = cfg.cos_weight_key
        opt_sin_key = cfg.sin_weight_key
        opt_m_sin_key = cfg.m_sin_weight_key

        # Step 1: Weights optimization (runs once)
        if not cfg.skip_weights_optimization:
            _logger.info("Step 1: Weight optimization")
            wopt = ReadoutWeightsOptimization(self._ctx)
            wopt_kw = dict(cfg.wopt_kwargs)
            wopt_set_measure_macro = bool(wopt_kw.pop("set_measure_macro", False))
            wopt_result = wopt.run(
                eff_ro_op, eff_drive_freq,
                cfg.cos_weight_key, cfg.sin_weight_key, cfg.m_sin_weight_key,
                r180=cfg.r180, n_avg=cfg.n_avg_weights,
                persist=cfg.persist_weights,
                set_measure_macro=wopt_set_measure_macro,
                revert_on_no_improvement=cfg.revert_on_no_improvement,
                **wopt_kw,
            )
            results["weights_optimization"] = wopt_result

            # Analyze to register optimized weights and extract opt_*_key (legacy parity)
            wopt.analyze(wopt_result)

        # Steps 2+3: Iterative discrimination + butterfly (Section 3)
        ge_kw = dict(cfg.ge_kwargs)
        bfly_kw = dict(cfg.bfly_kwargs)

        if "update_measureMacro" in ge_kw and "update_measure_macro" not in ge_kw:
            ge_kw["update_measure_macro"] = ge_kw.pop("update_measureMacro")

        ge_update_measure_macro = bool(ge_kw.pop("update_measure_macro", cfg.update_threshold))
        ge_persist = bool(ge_kw.pop("persist", cfg.update_weights))
        ge_apply_rotated_weights = bool(ge_kw.pop("apply_rotated_weights", cfg.update_weights))
        ge_n_samples_override = ge_kw.pop("n_samples", None)

        if "update_measureMacro" in bfly_kw and "update_measure_macro" not in bfly_kw:
            bfly_kw["update_measure_macro"] = bfly_kw.pop("update_measureMacro")

        bfly_update_measure_macro = bool(bfly_kw.pop("update_measure_macro", cfg.update_threshold))
        bfly_n_samples_override = bfly_kw.pop("n_samples", None)
        bfly_max_trials_override = bfly_kw.pop("M0_MAX_TRIALS", cfg.M0_MAX_TRIALS)

        pipeline_k = float(cfg.k) if getattr(cfg, "k", None) is not None else None
        if pipeline_k is not None:
            ge_kw.setdefault("k", pipeline_k)
            bfly_kw.setdefault("k", pipeline_k)
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

            cfg_samples_disc = cfg.resolved_n_samples_disc()
            ge_n_samples = int(ge_n_samples_override) if ge_n_samples_override is not None else int(cfg_samples_disc if n_disc == cfg.n_samples_disc else n_disc)

            # Step 2: G/E discrimination
            _logger.info("Step 2: GE discrimination (n_samples=%d)", ge_n_samples)
            ge_disc = ReadoutGEDiscrimination(self._ctx)
            ge_result = ge_disc.run(
                eff_ro_op, eff_drive_freq,
                r180=cfg.r180,
                n_samples=ge_n_samples,
                base_weight_keys=(opt_cos_key, opt_sin_key, opt_m_sin_key),
                update_measure_macro=ge_update_measure_macro,
                apply_rotated_weights=ge_apply_rotated_weights,
                persist=ge_persist,
                burn_rot_weights=cfg.burn_rot_weights,
                blob_k_g=cfg.blob_k_g,
                blob_k_e=cfg.blob_k_e,
                **ge_kw,
            )

            # Analyze GE discrimination BEFORE butterfly so PostSelectionConfig is set
            ge_analysis = ge_disc.analyze(ge_result)
            current_fidelity = ge_analysis.metrics.get("fidelity", 0.0)

            # Step 3: Butterfly measurement
            bfly_n_samples = (
                int(bfly_n_samples_override)
                if bfly_n_samples_override is not None
                else int(cfg.n_shots_butterfly)
            )
            bfly_max_trials = int(bfly_max_trials_override)

            _logger.info("Step 3: Butterfly measurement (n_shots=%d)", bfly_n_samples)
            bfly = ReadoutButterflyMeasurement(self._ctx)
            bfly_show = bfly_kw.pop("show_analysis", cfg.display_analysis)
            bfly_result = bfly.run(
                r180=cfg.r180,
                update_measure_macro=bfly_update_measure_macro,
                n_samples=bfly_n_samples,
                M0_MAX_TRIALS=bfly_max_trials,
                show_analysis=bfly_show,
                **bfly_kw,
            )

            # Legacy parity: run analysis immediately to trigger inline prints + plots
            if bfly_show:
                bfly.analyze(bfly_result)

            iteration_results.append({
                "ge_result": ge_result,
                "bfly_result": bfly_result,
                "fidelity": current_fidelity,
                "n_disc": ge_n_samples,
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

        # Explicit persistence policy (config driven)
        if cfg.save_to_config:
            allow_inline = bool(getattr(self._ctx, "allow_inline_mutations", False))
            if not allow_inline:
                _logger.info(
                    "Strict mode: run() skipped inline persistence. "
                    "Use CalibrationOrchestrator.apply_patch(...) for state updates."
                )
                return results
            if cfg.save_calibration_json and self.calibration_store is not None:
                try:
                    self.calibration_store.save()
                except Exception as exc:
                    _logger.warning("Failed to save calibration.json: %s", exc)

            if cfg.save_measure_config:
                try:
                    if hasattr(self._ctx, "calibration_orchestrator"):
                        from ...calibration.contracts import Patch
                        patch = Patch(reason="CalibrateReadoutFull_persist_final")
                        patch.add("PersistMeasureConfig")
                        self._ctx.calibration_orchestrator.apply_patch(patch)
                    else:
                        exp_path = Path(getattr(self._ctx, "experiment_path", "."))
                        dst = exp_path / "config" / "measureConfig.json"
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        measureMacro.save_json(str(dst))
                except Exception as exc:
                    _logger.warning("Failed to save measureConfig.json: %s", exc)

            if cfg.save_session_state:
                try:
                    save_pulses = getattr(self._ctx, "save_pulses", None)
                    save_attributes = getattr(self._ctx, "save_attributes", None)
                    if callable(save_pulses):
                        save_pulses()
                    if callable(save_attributes):
                        save_attributes()
                except Exception as exc:
                    _logger.warning("Failed to save session-specific config state: %s", exc)

            if cfg.save_calibration_db:
                _logger.warning(
                    "save_calibration_db=True requested, but readout pipeline does not "
                    "produce Octave mixer DB updates; skipping calibration_db.json write."
                )

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
                if k == "fidelity":
                    try:
                        v = float(v)
                    except (TypeError, ValueError):
                        pass
                    else:
                        if np.isfinite(v) and v > 1.0:
                            v /= 100.0
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
        """Print summary metrics from the full calibration pipeline.

        Legacy parity: individual sub-experiments handle their own
        plots (GE discrimination scatter, butterfly discriminator).
        The pipeline itself prints a text summary.
        """
        metrics = analysis.metrics
        if not metrics:
            return None

        # Print GE discrimination summary
        if "ge_fidelity" in metrics:
            ge_fid = metrics["ge_fidelity"]
            if isinstance(ge_fid, (int, float, np.floating)) and ge_fid <= 1.0:
                print(f"GE Discrimination fidelity: {ge_fid:.2%}")
            else:
                print(f"GE Discrimination fidelity: {ge_fid:.2f}%")
        if "ge_angle" in metrics:
            print(f"GE Discrimination angle: {metrics['ge_angle']:.4f} rad")
        if "ge_threshold" in metrics:
            print(f"GE Discrimination threshold: {metrics['ge_threshold']:.4g}")

        # Print butterfly summary
        if "bfly_F" in metrics:
            print(f"Butterfly F: {metrics['bfly_F']:.4f}")
        if "bfly_Q" in metrics:
            print(f"Butterfly Q: {metrics['bfly_Q']:.4f}")
        if "bfly_V" in metrics:
            print(f"Butterfly V: {metrics['bfly_V']:.4f}")
        if "n_iterations" in metrics:
            print(f"Iterations: {metrics['n_iterations']}")

        return None


class CalibrationReadoutFull(CalibrateReadoutFull):
    """Config-first wrapper for full readout calibration.

    This class enforces explicit configuration through ``readoutConfig``
    while delegating implementation to :class:`CalibrateReadoutFull`.
    """

    def run(
        self,
        readoutConfig: ReadoutConfig,
        **kwargs: Any,
    ) -> dict:
        if readoutConfig is None:
            raise ValueError("readoutConfig is required")
        if kwargs:
            unexpected = ", ".join(sorted(kwargs.keys()))
            raise ValueError(
                "CalibrationReadoutFull.run accepts only readoutConfig; "
                f"unexpected kwargs: {unexpected}"
            )
        return super().run(config=readoutConfig)


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
