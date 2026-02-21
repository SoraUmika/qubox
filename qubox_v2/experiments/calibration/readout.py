"""Readout calibration experiments."""
from __future__ import annotations

import warnings
from typing import Any, Mapping, Tuple

import numpy as np

from ..experiment_base import ExperimentBase
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
            attr.qb_el, r180, attr.qb_therm_clks, n_runs,
        )
        return self.run_program(
            prog, n_total=n_runs,
            processors=[pp.proc_default],
        )


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
        self.set_standard_frequencies()

        prog = cQED_programs.readout_ge_integrated_trace(
            attr.ro_el, attr.qb_el, ro_op, weights, num_div,
            r180, ro_depl_clks or attr.ro_therm_clks, n_avg,
        )
        return self.run_program(
            prog, n_total=n_avg, process_in_sim=process_in_sim,
            processors=[pp.proc_default],
        )


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
            attr.qb_el, r180, attr.qb_therm_clks, n_samples,
        )
        result = self.run_program(
            prog, n_total=n_samples,
            processors=[pp.proc_default],
        )
        return result

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

        prog = cQED_programs.readout_butterfly_measurement(
            attr.qb_el, attr.ro_el, r180,
            attr.qb_therm_clks, n_samples,
            M0_MAX_TRIALS=M0_MAX_TRIALS,
        )
        result = self.run_program(
            prog, n_total=n_samples,
            processors=[pp.proc_default],
        )
        self.save_output(result.output, "butterflyMeasurement")
        return result


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
                    I_g = result.output.get("I_g", np.array([0]))
                    I_e = result.output.get("I_e", np.array([0]))
                    Q_g = result.output.get("Q_g", np.array([0]))
                    Q_e = result.output.get("Q_e", np.array([0]))
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
