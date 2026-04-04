"""Gate calibration experiments."""
from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib.pyplot as plt

from ..experiment_base import ExperimentBase
from ..result import AnalysisResult, FitResult, ProgramBuildResult
from qubox_tools.algorithms import post_process as pp
from qubox_tools.algorithms.transforms import project_complex_to_line_real
from qubox_tools.fitting.routines import fit_and_wrap, build_fit_legend
from qubox_tools.fitting.cqed import rb_survival_model
from qubox_tools.algorithms.core import random_sequences
from ...hardware.program_runner import RunResult
from ...programs import api as cQED_programs
from ...programs.measurement import build_readout_snapshot_from_handle
from ...calibration.pulse_train_tomo import (
    run_pulse_train_tomography,
    fit_pulse_train_model,
    fit_params_to_qubitrotation_knobs,
    default_r0_dict,
    plot_meas_vs_fit,
)


class AllXY(ExperimentBase):
    """All-XY gate error benchmarking (21 gate pairs).

    Each of 21 combinations of two single-qubit gates is applied,
    and the resulting population is measured to diagnose systematic
    gate errors.
    """

    # Standard 21 AllXY gate pairs (QM convention)
    _ALLXY_SEQUENCES = [
        ("r0", "r0"), ("x180", "x180"), ("y180", "y180"),
        ("x180", "y180"), ("y180", "x180"),
        ("x90", "r0"), ("y90", "r0"),
        ("x90", "y90"), ("y90", "x90"),
        ("x90", "y180"), ("y90", "x180"),
        ("x180", "y90"), ("y180", "x90"),
        ("x90", "x180"), ("x180", "x90"),
        ("y90", "y180"), ("y180", "y90"),
        ("x180", "r0"), ("y180", "r0"),
        ("x90", "x90"), ("y90", "y90"),
    ]

    # Expected <Z> for each pair (legacy parity):
    # 5 ground (+1), 12 superposition (0), 4 excited (-1)
    _ALLXY_IDEAL = np.array([
        1, 1, 1, 1, 1,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        -1, -1, -1, -1,
    ], dtype=float)

    def _build_impl(
        self,
        gate_indices: list[int] | None = None,
        prefix: str = "",
        qb_detuning: int = 0,
        n_avg: int = 1000,
        qb_therm_clks: int | None = None,
    ) -> ProgramBuildResult:
        attr = self.attr
        qb_therm = self.resolve_override_or_attr(
            value=qb_therm_clks,
            attr_name="qb_therm_clks",
            owner="AllXY",
            cast=int,
        )

        # Build rotation sequences
        if gate_indices is not None:
            ops = [self._ALLXY_SEQUENCES[i] for i in gate_indices]
        else:
            ops = list(self._ALLXY_SEQUENCES)

        if prefix:
            ops = [(f"{prefix}{g1}", f"{prefix}{g2}") for (g1, g2) in ops]

        prog = cQED_programs.all_xy(
            attr.qb_el, ops, qb_therm, n_avg,
            readout=self.readout_handle,
        )
        return ProgramBuildResult(
            program=prog,
            n_total=n_avg,
            processors=(pp.proc_default, pp.proc_attach("ops", ops)),
            experiment_name="AllXY",
            params={
                "gate_indices": list(gate_indices) if gate_indices is not None else None,
                "prefix": prefix,
                "qb_detuning": qb_detuning,
                "n_avg": n_avg,
                "qb_therm_clks": qb_therm,
            },
            resolved_frequencies={
                attr.ro_el: self._resolve_readout_frequency(),
                attr.qb_el: self.get_qubit_frequency() + qb_detuning,
            },
            bindings_snapshot=self._serialize_bindings(),
            builder_function="cQED_programs.all_xy",
            readout_state=build_readout_snapshot_from_handle(self.readout_handle),
            sweep_axes={"ops": ops},
        )

    def run(
        self,
        gate_indices: list[int] | None = None,
        prefix: str = "",
        qb_detuning: int = 0,
        n_avg: int = 1000,
        qb_therm_clks: int | None = None,
    ) -> RunResult:
        build = self.build_program(
            gate_indices=gate_indices,
            prefix=prefix,
            qb_detuning=qb_detuning,
            n_avg=n_avg,
            qb_therm_clks=qb_therm_clks,
        )
        result = self.run_program(
            build.program, n_total=build.n_total,
            processors=list(build.processors),
        )
        self.save_output(result.output, "allXY")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        # Legacy parity: interpret measured boolean stream as P_e and report
        # corrected sigma_z = P_g - P_e (|g> -> +1, |e> -> -1).
        confusion = kw.get("confusion", None)
        if confusion is None:
            confusion = self.get_confusion_matrix()

        Pe = result.output.get("Pe")
        used_confusion = False
        projection_meta = None
        analysis_path = "projected_fallback"
        if Pe is not None:
            Pe = result.output._format(Pe)
            pe_states = np.asarray(Pe, dtype=float)
            analysis_path = "discriminated"

            # Optional confusion-matrix correction (legacy parity).
            if confusion is not None:
                states = pp.ro_state_correct_proc(
                    {"Pe": pe_states},
                    targets=[("Pe", "sz")],
                    confusion=confusion,
                    to_sigmaz=True,
                ).get("sz", 1.0 - 2.0 * pe_states)
                used_confusion = True
            else:
                # Still report sigma_z even if no correction artifacts are loaded.
                states = 1.0 - 2.0 * pe_states
        else:
            # Fallback if Pe stream is unavailable.
            S = result.output.extract("S")
            projected, proj_center, proj_direction = project_complex_to_line_real(S)
            if projected.max() != projected.min():
                pe_states = (projected - projected.min()) / (projected.max() - projected.min())
            else:
                pe_states = projected
            states = 1.0 - 2.0 * np.asarray(pe_states, dtype=float)
            projection_meta = {
                "center_real": float(np.real(proj_center)),
                "center_imag": float(np.imag(proj_center)),
                "direction_real": float(np.real(proj_direction)),
                "direction_imag": float(np.imag(proj_direction)),
            }

        ideal = self._ALLXY_IDEAL
        if len(states) == len(ideal):
            gate_error = float(np.mean(np.abs(states - ideal)))
        else:
            gate_error = float("nan")

        metrics: dict[str, Any] = {
            "gate_error": gate_error,
            "states": states,
            "observable": "sigma_z",
            "state_mapping": {"g": +1.0, "e": -1.0},
            "used_confusion_correction": bool(used_confusion),
            "analysis_path": analysis_path,
        }
        metadata = {}
        if projection_meta is not None:
            metadata["signal_projection"] = projection_meta
        return AnalysisResult.from_run(result, metrics=metrics, metadata=metadata)

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        states = analysis.metrics.get("states", None)
        if states is None:
            S = analysis.data.get("S")
            if S is None:
                return None
            projected, _, _ = project_complex_to_line_real(S)
            if projected.max() != projected.min():
                pe_states = (projected - projected.min()) / (projected.max() - projected.min())
            else:
                pe_states = projected
            states = 1.0 - 2.0 * np.asarray(pe_states, dtype=float)

        if ax is None:
            fig, ax = plt.subplots(figsize=(12, 5))
        else:
            fig = ax.figure

        indices = np.arange(len(states))
        ax.stem(indices, states, linefmt="b-", markerfmt="bo", basefmt=" ", label="Measured")

        ideal = self._ALLXY_IDEAL
        if len(states) == len(ideal):
            ax.step(np.arange(len(ideal)), ideal, "r--", where="mid", lw=1.5, label="Ideal")

        title = "AllXY"
        if "gate_error" in analysis.metrics:
            title += f"  |  Gate Error = {analysis.metrics['gate_error']:.4f}"
        ax.set_title(title)
        ax.set_xlabel("Gate Pair Index")
        ax.set_ylabel(r"$\langle Z \rangle$")
        ax.set_ylim(-1.1, 1.1)
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig


class DRAGCalibration(ExperimentBase):
    """DRAG coefficient optimization (Yale method).

    Sweeps the DRAG amplitude parameter to minimize leakage to
    higher transmon levels.

    Legacy parity
    -------------
    The legacy workflow creates temporary DRAG waveforms with ``base_alpha``
    baked into the Q channel, registers them as volatile pulses
    (``x180_tmp``, etc.), and then sweeps ``amps`` as multipliers on the
    DRAG amplitude via the QUA ``amp()`` matrix.  This class replicates
    that behavior exactly so that the same ``amps`` sweep produces
    identical QUA programs and the resulting ``optimal_alpha`` is in the
    same units (``amps * base_alpha``).
    """

    def _build_impl(
        self,
        amps: np.ndarray | list[float],
        n_avg: int = 1000,
        *,
        base_alpha: float = 1.0,
        calibration_op: str = "ge_ref_r180",
        x180: str = "ge_x180",
        x90: str = "ge_x90",
        y180: str = "ge_y180",
        y90: str = "ge_y90",
        qb_therm_clks: int | None = None,
    ) -> ProgramBuildResult:
        """Run the Yale DRAG calibration sweep.

        Parameters
        ----------
        amps : array-like
            Dimensionless alpha multipliers to sweep.
        n_avg : int
            Number of averaging iterations.
        base_alpha : float
            Base DRAG coefficient baked into the temporary waveforms.
            The effective DRAG coefficient at each point is
            ``base_alpha * amps[i]``.  Set to 1.0 (default) so that the
            ``amps`` axis directly represents the DRAG coefficient.
        calibration_op : str
            Reference pulse calibration entry to read parameters from
            and to target for DRAG coefficient updates (default: ``"ge_ref_r180"``).
        x180, x90, y180, y90 : str
            Fallback pulse operation names (used only when ``base_alpha``
            is exactly 0, i.e. no temporary waveform generation).
        """
        from qubox.core.pulse_op import PulseOp
        from ...tools.waveforms import drag_gaussian_pulse_waveforms

        attr = self.attr
        amps = np.asarray(amps, dtype=float)

        if amps.ndim != 1 or amps.size == 0:
            raise ValueError("`amps` must be a non-empty 1D array-like.")
        if not np.all(np.isfinite(amps)):
            raise ValueError("`amps` must contain only finite numeric values.")

        # OPX amplitude matrix coefficients must satisfy |a| < 2.
        # Using |a| == 2 triggers runtime overflow errors on hardware.
        over_limit = np.abs(amps) >= 2.0
        if np.any(over_limit):
            max_abs = float(np.max(np.abs(amps)))
            raise ValueError(
                "DRAG sweep values in `amps` exceed OPX limits for amp-matrix scaling "
                f"(|a| must be < 2, got max |a|={max_abs:.6g}). "
                "Use a narrower range (legacy notebook uses -0.5 to 0.5)."
            )

        # ----- Legacy parity: generate DRAG waveforms with base_alpha -----
        # Retrieve pulse parameters from calibration store or attributes
        cal = self.calibration_store
        ref_cal = cal.get_pulse_calibration(calibration_op) if cal else None

        rlen = int(ref_cal.length) if (ref_cal and ref_cal.length) else getattr(attr, "rlen", 16)
        sigma = float(ref_cal.sigma) if (ref_cal and ref_cal.sigma) else rlen / 6.0
        anh = float(getattr(attr, "anharmonicity", 0) or -200e6)

        r180_amp = float(ref_cal.amplitude) if (ref_cal and ref_cal.amplitude) else getattr(attr, "r180_amp", 0.1)
        r90_amp = 0.5 * r180_amp

        # Build DRAG waveforms with base_alpha baked in
        ga_r180, dr_r180 = drag_gaussian_pulse_waveforms(r180_amp, rlen, sigma, base_alpha, anh)
        ga_r90, dr_r90 = drag_gaussian_pulse_waveforms(r90_amp, rlen, sigma, base_alpha, anh)

        # Complex waveforms (I = gaussian, Q = derivative)
        z_r180 = np.array(ga_r180) + 1j * np.array(dr_r180)
        z_r90 = np.array(ga_r90) + 1j * np.array(dr_r90)

        # Rotation by pi/2 to generate Y pulses from X pulses
        pi_rot = np.exp(1j * np.pi / 2)
        z_y180 = z_r180 * pi_rot
        z_y90 = z_r90 * pi_rot

        allow_inline = bool(getattr(self._ctx, "allow_inline_mutations", False))
        if allow_inline:
            # Register temporary volatile pulses
            # Legacy parity: pass numpy arrays directly (not .tolist())
            _tmp_pulses = [
                PulseOp(
                    element=attr.qb_el, op="x180_tmp", pulse="x180_tmp_pulse",
                    type="control", length=rlen,
                    I_wf_name="gauss_r180_tmp_wf", Q_wf_name="drag_r180_tmp_wf",
                    I_wf=z_r180.real, Q_wf=z_r180.imag,
                ),
                PulseOp(
                    element=attr.qb_el, op="y180_tmp", pulse="y180_tmp_pulse",
                    type="control", length=rlen,
                    I_wf_name="y180_tmp_I_wf", Q_wf_name="y180_tmp_Q_wf",
                    I_wf=z_y180.real, Q_wf=z_y180.imag,
                ),
                PulseOp(
                    element=attr.qb_el, op="x90_tmp", pulse="x90_tmp_pulse",
                    type="control", length=rlen,
                    I_wf_name="gauss_r90_tmp_wf", Q_wf_name="drag_r90_tmp_wf",
                    I_wf=z_r90.real, Q_wf=z_r90.imag,
                ),
                PulseOp(
                    element=attr.qb_el, op="y90_tmp", pulse="y90_tmp_pulse",
                    type="control", length=rlen,
                    I_wf_name="y90_tmp_I_wf", Q_wf_name="y90_tmp_Q_wf",
                    I_wf=z_y90.real, Q_wf=z_y90.imag,
                ),
            ]

            pm = self.pulse_mgr
            for p in _tmp_pulses:
                pm.register_pulse_op(p, override=True, persist=False)

            self.burn_pulses()
            x180_op, x90_op, y180_op, y90_op = "x180_tmp", "x90_tmp", "y180_tmp", "y90_tmp"
        else:
            x180_op, x90_op, y180_op, y90_op = "x180", "x90", "y180", "y90"

        qb_therm = self.resolve_override_or_attr(
            value=qb_therm_clks,
            attr_name="qb_therm_clks",
            owner="DRAGCalibration",
            cast=int,
        )

        # Build QUA program using temporary ops
        prog = cQED_programs.drag_calibration_YALE(
            attr.qb_el, amps,
            x180_op, x90_op, y180_op, y90_op,
            qb_therm, n_avg,
            readout=self.readout_handle,
        )
        return ProgramBuildResult(
            program=prog,
            n_total=n_avg,
            processors=(
                pp.proc_default,
                pp.proc_attach("amps", amps),
                pp.proc_attach("base_alpha", float(base_alpha)),
                pp.proc_attach("pulse_len", int(rlen)),
            ),
            experiment_name="DRAGCalibration",
            params={
                "amps": amps.tolist(),
                "n_avg": n_avg,
                "base_alpha": float(base_alpha),
                "calibration_op": calibration_op,
                "x180": x180,
                "x90": x90,
                "y180": y180,
                "y90": y90,
                "qb_therm_clks": qb_therm,
            },
            resolved_frequencies={
                attr.ro_el: self._resolve_readout_frequency(),
                attr.qb_el: self._resolve_qubit_frequency(),
            },
            bindings_snapshot=self._serialize_bindings(),
            builder_function="cQED_programs.drag_calibration_YALE",
            readout_state=build_readout_snapshot_from_handle(self.readout_handle),
            sweep_axes={"amps": amps},
            run_program_kwargs={"targets": [("I1", "Q1"), ("I2", "Q2")]},
        )

    def run(
        self,
        amps: np.ndarray | list[float],
        n_avg: int = 1000,
        *,
        base_alpha: float = 1.0,
        calibration_op: str = "ge_ref_r180",
        x180: str = "ge_x180",
        x90: str = "ge_x90",
        y180: str = "ge_y180",
        y90: str = "ge_y90",
        qb_therm_clks: int | None = None,
    ) -> RunResult:
        build = self.build_program(
            amps=amps,
            n_avg=n_avg,
            base_alpha=base_alpha,
            calibration_op=calibration_op,
            x180=x180,
            x90=x90,
            y180=y180,
            y90=y90,
            qb_therm_clks=qb_therm_clks,
        )
        result = self.run_program(
            build.program,
            n_total=build.n_total,
            processors=list(build.processors),
            **(build.run_program_kwargs or {}),
        )
        self._run_params = {"calibration_op": calibration_op}
        self.save_output(result.output, "dragCalibration")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        from qubox_tools.algorithms.core import find_roots

        amps = result.output.extract("amps")
        base_alpha = result.output.get("base_alpha", 1.0)
        if isinstance(base_alpha, np.ndarray):
            base_alpha = float(base_alpha)

        S_1 = result.output.get("S_1")
        S_2 = result.output.get("S_2")

        # DRAG optimal alpha: difference of two sequences should cross zero
        # Legacy parity: use S.real (not magnitude)
        I_diff = np.real(S_1) - np.real(S_2)

        metrics: dict[str, Any] = {}

        # Use find_roots for robust zero-crossing detection (legacy parity)
        roots = find_roots(amps, I_diff)
        if len(roots) > 0:
            # Scale by base_alpha to get effective DRAG coefficient
            possible_alpha_candidates = np.array(roots) * base_alpha
            metrics["optimal_alpha"] = float(possible_alpha_candidates[0])
            metrics["alpha_candidates"] = possible_alpha_candidates.tolist()
        else:
            # Fallback: pick amplitude with smallest |I_diff|
            metrics["optimal_alpha"] = float(amps[np.argmin(np.abs(I_diff))]) * base_alpha
            metrics["alpha_candidates"] = []

        metrics["base_alpha"] = base_alpha

        metadata: dict[str, Any] = {
            "calibration_kind": "drag_alpha",
            "target_op": (self._run_params.get("calibration_op") if hasattr(self, "_run_params") else "ge_ref_r180"),
            "units": {"optimal_alpha": "a.u."},
            "quality_gate_required": True,
        }

        if update_calibration:
            target_op = metadata["target_op"]
            # Only patch the reference pulse — derived primitives (x180, y180, …)
            # inherit drag_coeff via the PulseFactory rotation_derived mechanism
            # and must NOT be stored in calibration.json.
            metadata.setdefault("proposed_patch_ops", []).extend([
                {
                    "op": "SetCalibration",
                    "payload": {
                        "path": f"pulse_calibrations.{target_op}.drag_coeff",
                        "value": float(metrics["optimal_alpha"]),
                    },
                },
                {
                    "op": "TriggerPulseRecompile",
                    "payload": {"include_volatile": True},
                },
            ])

        analysis = AnalysisResult.from_run(result, metrics=metrics, metadata=metadata)

        return analysis

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        amps = analysis.data.get("amps")
        S_1 = analysis.data.get("S_1")
        S_2 = analysis.data.get("S_2")
        if amps is None or S_1 is None or S_2 is None:
            return None

        base_alpha = analysis.metrics.get("base_alpha", 1.0)
        I_diff = np.real(S_1) - np.real(S_2)

        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 6))
        else:
            fig = ax.figure

        # Legacy parity: line plots with markers (not scatter)
        ax.plot(amps, np.real(S_1), 'o-', linewidth=2, markersize=4,
                label=r'$X_{180} - Y_{90}$ sequence')
        ax.plot(amps, np.real(S_2), 's-', linewidth=2, markersize=4,
                label=r'$Y_{180} - X_{90}$ sequence')
        ax.axhline(y=0, color='gray', linestyle='--', linewidth=1, alpha=0.5,
                    label=r'$\langle\sigma_z\rangle = 0$')

        ax.set_xlabel(r"DRAG amplitude scaling factor ($\alpha$)", fontsize=12)
        ax.set_ylabel(r"$\langle\sigma_z\rangle$", fontsize=12)
        ax.set_title(
            f"DRAG Calibration (Yale Method) - base $\\alpha$ = {base_alpha}",
            fontsize=14, fontweight='bold',
        )

        # Mark crossing points (legacy parity)
        alpha_candidates = analysis.metrics.get("alpha_candidates", [])
        if alpha_candidates:
            for root_alpha in alpha_candidates:
                # Convert back to amps-axis units for the vertical line
                root_amp = root_alpha / base_alpha if base_alpha != 0 else root_alpha
                ax.axvline(x=root_amp, color='red', linestyle=':', linewidth=1.5, alpha=0.7)

        if "optimal_alpha" in analysis.metrics:
            opt = analysis.metrics["optimal_alpha"]
            opt_amp = opt / base_alpha if base_alpha != 0 else opt
            ax.axvline(opt_amp, color="r", ls="--", lw=1.5,
                       label=f"Optimal $\\alpha$ = {opt:.4f}")

        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=11)
        plt.tight_layout()
        plt.show()
        return fig


class RandomizedBenchmarking(ExperimentBase):
    """Standard and interleaved randomized benchmarking.

    Runs random Clifford sequences of varying depth to extract
    average gate fidelity. Supports interleaving a specific gate.
    """

    def _build_impl(self, **kw):
        raise NotImplementedError(
            "RandomizedBenchmarking compiles/executes many batched programs per run "
            "and does not map to a single ProgramBuildResult."
        )

    # Canonical 1Q Clifford set (24 elements decomposed into 7 primitives)
    _CLIFFORD_1Q_SEQS = [
        ["r0"],
        ["x180"],
        ["x90"],
        ["xn90"],
        ["y180"],
        ["y90"],
        ["yn90"],
        ["x180", "y180"],
        ["x180", "y90"],
        ["x180", "yn90"],
        ["x90", "y180"],
        ["x90", "y90"],
        ["x90", "yn90"],
        ["xn90", "y180"],
        ["xn90", "y90"],
        ["xn90", "yn90"],
        ["y90", "x90"],
        ["y90", "xn90"],
        ["yn90", "x90"],
        ["yn90", "xn90"],
        ["x90", "y90", "x90"],
        ["x90", "y90", "xn90"],
        ["x90", "yn90", "x90"],
        ["x90", "yn90", "xn90"],
    ]

    _CANON_PRIMITIVES = ["r0", "x180", "x90", "xn90", "y180", "y90", "yn90"]

    @staticmethod
    def _build_clifford_unitaries():
        """Build the 24 Clifford 2x2 unitaries from decompositions."""
        def _rot(pauli: str, theta: float) -> np.ndarray:
            I2 = np.eye(2, dtype=complex)
            X = np.array([[0, 1], [1, 0]], dtype=complex)
            Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
            P = {"x": X, "y": Y}[pauli.lower()]
            return np.cos(theta / 2) * I2 - 1j * np.sin(theta / 2) * P

        PRIM_U = {
            "r0":   np.eye(2, dtype=complex),
            "x90":  _rot("x", +np.pi / 2),
            "xn90": _rot("x", -np.pi / 2),
            "x180": _rot("x", +np.pi),
            "y90":  _rot("y", +np.pi / 2),
            "yn90": _rot("y", -np.pi / 2),
            "y180": _rot("y", +np.pi),
        }

        def cliff_U(seq_ops):
            U = np.eye(2, dtype=complex)
            for op in seq_ops:
                U = PRIM_U[op] @ U
            return U

        return [cliff_U(seq) for seq in RandomizedBenchmarking._CLIFFORD_1Q_SEQS], PRIM_U

    @staticmethod
    def _find_inverse_clifford(U_target, cliff_U_list, tol=1e-6):
        """Find the Clifford index whose unitary equals U_target."""
        overlaps = [abs(np.trace(Uk.conj().T @ U_target)) / 2.0 for Uk in cliff_U_list]
        k = int(np.argmax(overlaps))
        if overlaps[k] < (1 - tol):
            raise RuntimeError(f"Could not match inverse to a Clifford. best overlap={overlaps[k]:.9f}")
        return k

    def run(
        self,
        m_list: list[int],
        num_sequence: int,
        n_avg: int = 1000,
        *,
        interleave_op: str | None = None,
        primitives_by_id: dict[int, str] | None = None,
        primitive_prefix: str = "",
        max_sequences_per_compile: int = 10,
        guard_clks: int = 18,
        qb_therm_clks: int | None = None,
    ) -> RunResult:
        attr = self.attr
        qb_therm = self.resolve_override_or_attr(
            value=qb_therm_clks,
            attr_name="qb_therm_clks",
            owner="RandomizedBenchmarking",
            cast=int,
        )
        self.set_standard_frequencies()

        CLIFF_SEQS = self._CLIFFORD_1Q_SEQS
        CANON = self._CANON_PRIMITIVES
        n_cliff = len(CLIFF_SEQS)

        CLIFF_U, PRIM_U = self._build_clifford_unitaries()

        # Build primitives_by_id mapping
        if primitives_by_id is None:
            primitives_by_id = {
                i: f"{primitive_prefix}{c}" for i, c in enumerate(CANON)
            }

        # Build canonical name → ID mapping
        canon2id: dict[str, int] = {}
        for pid, opname in primitives_by_id.items():
            opname_str = str(opname)
            if opname_str in CANON:
                canon2id[opname_str] = int(pid)
            else:
                for c in CANON:
                    if opname_str.endswith(c):
                        canon2id[c] = int(pid)
                        break

        missing = [c for c in CANON if c not in canon2id]
        if missing:
            raise ValueError(f"primitives_by_id missing canonical mappings: {missing}")

        # Determine primitive clock cycles from pulse manager
        prim_op_for_timing = primitives_by_id.get(canon2id.get("x90", 0))
        if prim_op_for_timing:
            op_info = self.pulse_mgr.get_pulseOp_by_element_op(attr.qb_el, str(prim_op_for_timing))
            primitive_clks = int(op_info.length) // 4 if op_info and op_info.length else 4
        else:
            primitive_clks = 4

        # Interleave setup
        interleave_sentinel = int(max(primitives_by_id.keys())) + 1
        do_interleave = interleave_op is not None
        interleave_clks = None
        g_idx = None

        if do_interleave:
            op_str = str(interleave_op).strip()
            g_canon = None
            for c in CANON:
                if op_str == c or op_str.endswith(c):
                    g_canon = c
                    break
            if g_canon is None:
                raise ValueError(
                    f"interleave_op='{op_str}' is not recognized as a single-primitive Clifford.\n"
                    f"It must be (or end with) one of: {CANON}"
                )
            g_idx = CLIFF_SEQS.index([g_canon])
            op_info = self.pulse_mgr.get_pulseOp_by_element_op(attr.qb_el, op_str)
            interleave_clks = int(op_info.length) // 4 if op_info and op_info.length else primitive_clks

        # Generate random Clifford sequences and expand to primitive IDs
        m_list_int = [int(m) for m in m_list]
        n_m = len(m_list_int)

        # Collect results from batched program runs
        from qubox_tools.data.containers import Output
        from ...hardware.program_runner import ExecMode

        I_mat = np.full((n_m, num_sequence), np.nan, dtype=float)
        Q_mat = np.full((n_m, num_sequence), np.nan, dtype=float)

        B = int(max_sequences_per_compile)
        programs = []
        queued_meta = []

        for m_idx, m in enumerate(m_list_int):
            seqs = random_sequences(num_sequence, m, low=0, high=n_cliff, replace=True)

            ids_full_list: list[list[int]] = []

            for seq_idx, seq in enumerate(seqs):
                seq = list(map(int, seq))

                if not do_interleave:
                    U = np.eye(2, dtype=complex)
                    for c_idx in seq:
                        U = CLIFF_U[int(c_idx)] @ U
                    inv_idx = self._find_inverse_clifford(U.conj().T, CLIFF_U)

                    ops_full = []
                    for k in (seq + [int(inv_idx)]):
                        ops_full.extend(CLIFF_SEQS[int(k)])
                    ids_full = [canon2id[op] for op in ops_full]
                else:
                    U = np.eye(2, dtype=complex)
                    for c_idx in seq:
                        U = CLIFF_U[int(c_idx)] @ U
                        U = CLIFF_U[int(g_idx)] @ U
                    inv_idx = self._find_inverse_clifford(U.conj().T, CLIFF_U)

                    ids_full = []
                    for c_idx in seq:
                        ops = CLIFF_SEQS[int(c_idx)]
                        ids_full.extend([canon2id[o] for o in ops])
                        ids_full.append(int(interleave_sentinel))

                    ops_inv = CLIFF_SEQS[int(inv_idx)]
                    ids_full.extend([canon2id[o] for o in ops_inv])

                ids_full_list.append(ids_full)

            # Batch sequences into programs
            for start in range(0, num_sequence, B):
                end = min(start + B, num_sequence)
                batch_sequences_ids = ids_full_list[start:end]

                prog = cQED_programs.randomized_benchmarking(
                    qb_el=attr.qb_el,
                    sequences_ids=batch_sequences_ids,
                    qb_therm_clks=qb_therm,
                    n_avg=n_avg,
                    primitives_by_id=primitives_by_id,
                    primitive_clks=int(primitive_clks),
                    guard_clks=int(guard_clks),
                    interleave_op=(str(interleave_op) if do_interleave else None),
                    interleave_clks=(int(interleave_clks) if do_interleave else None),
                    interleave_sentinel=int(interleave_sentinel),
                    readout=self.readout_handle,
                )
                programs.append(prog)
                queued_meta.append(dict(m_idx=int(m_idx), start=int(start), end=int(end)))

        # Run all batched programs — collect both I/Q and Pe (state discrimination)
        runres_template = None
        Pe_mat = np.full((n_m, num_sequence), np.nan, dtype=float)
        for meta, prog in zip(queued_meta, programs):
            result = self.run_program(
                prog, n_total=n_avg,
                processors=[pp.proc_default],
            )
            if runres_template is None:
                runres_template = result

            I_batch = np.real(np.asarray(result.output.extract("S"), dtype=complex))
            Q_batch = np.imag(np.asarray(result.output.extract("S"), dtype=complex))

            # Legacy parity: also extract Pe (boolean_to_int averaged)
            Pe_raw = result.output.get("Pe")
            Pe_batch = result.output._format(Pe_raw) if Pe_raw is not None else None

            m_idx = meta["m_idx"]
            start = meta["start"]
            end = meta["end"]

            I_mat[m_idx, start:end] = I_batch
            Q_mat[m_idx, start:end] = Q_batch
            if Pe_batch is not None:
                Pe_mat[m_idx, start:end] = np.asarray(Pe_batch, dtype=float)

        # Average over sequences for each depth
        I_avg = np.nanmean(I_mat, axis=1)
        Q_avg = np.nanmean(Q_mat, axis=1)
        S_avg = I_avg + 1j * Q_avg
        Pe_avg = np.nanmean(Pe_mat, axis=1) if not np.all(np.isnan(Pe_mat)) else None

        output_dict = {
            "S": S_avg,
            "m_list": np.asarray(m_list_int),
            "I_matrix": I_mat,
            "Q_matrix": Q_mat,
        }
        if Pe_avg is not None:
            output_dict["Pe"] = Pe_avg
            output_dict["Pe_matrix"] = Pe_mat

        output = Output(output_dict)
        self.save_output(output, "randomizedBenchmarking")

        if runres_template is not None:
            runres_template.output = output
            return runres_template
        return RunResult(mode=ExecMode.HARDWARE, output=output, sim_samples=None)

    def analyze(self, result: RunResult, *, update_calibration: bool = False, p0=None, **kw) -> AnalysisResult:
        m_list = result.output.extract("m_list")

        # Legacy parity: prefer Pe (state discrimination probability) over raw IQ
        Pe_raw = result.output.get("Pe")
        Pe = result.output._format(Pe_raw) if Pe_raw is not None else None
        if Pe is not None:
            survival = np.asarray(Pe, dtype=float)
            # Apply confusion-matrix correction if available
            confusion = kw.pop("confusion", None)
            if confusion is None:
                confusion = self.get_confusion_matrix()
            if confusion is not None:
                corrected = pp.ro_state_correct_proc(
                    {"Pe": survival},
                    targets=[("Pe", "Pe_corr")],
                    confusion=confusion,
                )
                survival = corrected.get("Pe_corr", survival)
        else:
            # Fallback: use real part of S
            S = result.output.extract("S")
            survival = np.real(S)

        # Initial guesses for rb_survival_model(m, p, A, B)
        p_guess = 0.99
        A_guess = float(survival[0] - survival[-1])
        B_guess = float(survival[-1])
        auto_p0 = [p_guess, A_guess, B_guess]

        fit = fit_and_wrap(m_list.astype(float), survival, rb_survival_model,
                           p0 if p0 is not None else auto_p0,
                           model_name="rb_survival", **kw)

        metrics: dict[str, Any] = {}
        if fit.params:
            p = fit.params["p"]
            metrics["p"] = p
            # Single-qubit RB: F_avg = (1 + p) / 2
            metrics["avg_gate_fidelity"] = (1 + p) / 2
            metrics["error_per_gate"] = (1 - p) / 2

        return AnalysisResult.from_run(result, fit=fit, metrics=metrics)

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        m_list = analysis.data.get("m_list")
        if m_list is None:
            return None

        # Prefer Pe data; fall back to np.real(S)
        Pe = analysis.data.get("Pe")
        if Pe is not None:
            survival = np.asarray(Pe, dtype=float)
        else:
            S = analysis.data.get("S")
            if S is None:
                return None
            survival = np.real(S)
        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 5))
        else:
            fig = ax.figure

        ax.scatter(m_list, survival, s=10, label="Data")
        if analysis.fit and analysis.fit.params:
            p = analysis.fit.params
            x_fit = np.linspace(float(m_list.min()), float(m_list.max()), 500)
            y_fit = rb_survival_model(x_fit, p["p"], p["A"], p["B"])
            ax.plot(x_fit, y_fit, "r-", lw=2,
                    label=build_fit_legend(analysis.fit))

        ax.set_xlabel("Clifford Depth (m)")
        ax.set_ylabel("Survival Probability")
        title = "Randomized Benchmarking"
        if "avg_gate_fidelity" in analysis.metrics:
            title += f"  |  F = {analysis.metrics['avg_gate_fidelity']:.5f}"
        ax.set_title(title)
        ax.legend(
            bbox_to_anchor=(1.05, 1), loc='upper left',
            fontsize=10, borderaxespad=0.0,
        )
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig


class PulseTrainCalibration(ExperimentBase):
    """Pulse-train tomography for arbitrary rotation calibration.

    Runs full 3-axis qubit state tomography at each N value with multiple
    initial state preparations. Fits the Bloch-vector evolution using
    DE+LS global optimisation to extract amplitude error, phase error,
    detuning, and per-step Z rotation (zeta). Converts fit parameters
    to QubitRotation knob corrections (d_lambda, d_alpha, d_omega).

    Protocol
    --------
    For each N in N_values, for each prep in prep_defs:
        ``prep_fn()`` -> ``align()`` -> ``arb_rot.play() x N`` -> ``align()`` -> tomo(sx,sy,sz)

    The ``run()`` method wraps ``run_pulse_train_tomography()`` and stores
    the Bloch-vector data in a RunResult.  The ``analyze()`` method wraps
    ``fit_pulse_train_model()`` and ``fit_params_to_qubitrotation_knobs()``.
    """

    def _build_impl(self, **kw):
        raise NotImplementedError(
            "PulseTrainCalibration orchestrates tomography runs over N and prep sets "
            "and does not compile to one ProgramBuildResult."
        )

    def run(
        self,
        arb_rot,
        prep_defs: dict,
        N_values,
        n_avg: int = 20000,
        *,
        verbose: bool = True,
        sanity_check: bool = True,
        theta: float = np.pi,
        phi: float = 0.0,
    ) -> RunResult:
        """Run the pulse-train tomography sweep.

        Parameters
        ----------
        arb_rot
            QubitRotation gate under test (must have ``.play()`` method).
        prep_defs : dict
            Map label -> QUA callable (or None for ground state).
            Standard: ``{"g": None, "e": prep_e, "+x": prep_px, ...}``
        N_values : array-like of int
            Number of rotation-pulse repetitions to sweep.
        n_avg : int
            Averaging iterations.
        verbose, sanity_check : bool
            Passed to ``run_pulse_train_tomography``.
        theta, phi : float
            Nominal rotation angle and phase (stored as metadata).
        """
        from qubox_tools.data.containers import Output
        from ...hardware.program_runner import RunResult as RR, ExecMode

        meas, prep_check = run_pulse_train_tomography(
            experiment=self._ctx,
            arb_rot=arb_rot,
            prep_defs=prep_defs,
            N_values=N_values,
            n_avg=n_avg,
            verbose=verbose,
            sanity_check=sanity_check,
        )

        N_arr = np.asarray(N_values, int)
        output_dict = {
            "N_values": N_arr,
            "theta": float(theta),
            "phi": float(phi),
            "n_avg": int(n_avg),
            "prep_keys": list(meas.keys()),
        }
        for key, arr in meas.items():
            output_dict[f"meas_{key}"] = np.asarray(arr, float)
        if prep_check is not None:
            for key, arr in prep_check.items():
                output_dict[f"prep_check_{key}"] = np.asarray(arr, float)

        output = Output(output_dict)
        self.save_output(output, "pulseTrainCalibration")
        return RR(mode=ExecMode.HARDWARE, output=output, sim_samples=None)

    @staticmethod
    def _reconstruct_meas(result) -> dict:
        """Reconstruct meas dict from RunResult output."""
        keys = result.output.get("prep_keys", [])
        if isinstance(keys, np.ndarray):
            keys = keys.tolist()
        return {
            key: np.asarray(result.output.get(f"meas_{key}"), float)
            for key in keys
        }

    def analyze(
        self,
        result: RunResult,
        *,
        update_calibration: bool = False,
        fit_zeta: bool = True,
        bounds: dict | None = None,
        multi_seed: bool = True,
        seeds=None,
        seed_select: str = "ls",
        residual_mode: str = "dir",
        fit_relax: bool = False,
        t_step: float | None = None,
        verbose: bool = True,
        dt_s: float | None = None,
        n_samp: int | None = None,
        d_omega_sign: float = 1.0,
        **kw,
    ) -> AnalysisResult:
        """Analyse pulse-train tomography data.

        Runs DE+LS global fit, optionally converts to QubitRotation knobs.

        Parameters
        ----------
        fit_zeta : bool
            Fit per-step Z rotation parameter.
        bounds : dict or None
            Parameter bounds for DE optimiser.
        multi_seed, seeds, seed_select : multi-seed controls.
        residual_mode : str
            ``"dir"`` (normalised), ``"raw"``, or ``"both"``.
        dt_s, n_samp : float, int
            Pulse duration info for knob conversion.  Both required
            to compute ``d_lambda``, ``d_alpha``, ``d_omega``.
        d_omega_sign : float
            Sign convention for detuning -> d_omega conversion.
        """
        N_values = np.asarray(result.output.extract("N_values"), int)
        theta = float(result.output.get("theta", np.pi))
        phi = float(result.output.get("phi", 0.0))
        meas = self._reconstruct_meas(result)

        p_hat, de, ls, pred_fit, fit_meta = fit_pulse_train_model(
            meas=meas, N_values=N_values, theta=theta, phi=phi,
            r0_dict=default_r0_dict(),
            fit_zeta=fit_zeta,
            bounds=bounds,
            multi_seed=multi_seed, seeds=seeds, seed_select=seed_select,
            residual_mode=residual_mode,
            fit_relax=fit_relax, t_step=t_step,
            verbose=verbose,
            **kw,
        )

        metrics: dict[str, Any] = {
            "amp_err": p_hat["amp_err"],
            "phase_err": p_hat["phase_err"],
            "delta": p_hat["delta"],
            "zeta": p_hat.get("zeta", 0.0),
            "de_sse": float(de.fun),
            "ls_cost": float(ls.cost),
            "ls_success": bool(ls.success),
        }

        if dt_s is not None and n_samp is not None:
            knobs = fit_params_to_qubitrotation_knobs(
                amp_err_hat=p_hat["amp_err"],
                phase_err_hat=p_hat["phase_err"],
                delta_hat=p_hat["delta"],
                dt_s=dt_s, n_samp=n_samp,
                d_omega_sign=d_omega_sign,
            )
            metrics.update(knobs)

        metadata: dict[str, Any] = {
            "calibration_kind": "pulse_train",
            "fit_meta": fit_meta,
        }

        for key, arr in pred_fit.items():
            result.output[f"pred_fit_{key}"] = np.asarray(arr, float)

        fit = FitResult(
            model_name="pulse_train_tomo",
            params=dict(p_hat),
        )
        return AnalysisResult.from_run(result, fit=fit, metrics=metrics, metadata=metadata)

    def plot(self, analysis: AnalysisResult, *, residual_mode: str = "both", **kwargs):
        """Plot measured Bloch vectors vs fit, per-prep panels."""
        N_values = np.asarray(analysis.data.get("N_values"), int)
        theta = float(analysis.data.get("theta", np.pi))
        phi = float(analysis.data.get("phi", 0.0))
        keys = analysis.data.get("prep_keys", [])
        if isinstance(keys, np.ndarray):
            keys = keys.tolist()

        meas = {k: np.asarray(analysis.data.get(f"meas_{k}"), float) for k in keys}
        pred_fit = {k: np.asarray(analysis.data.get(f"pred_fit_{k}"), float) for k in keys}
        p_hat = analysis.fit.params if analysis.fit else {}
        fit_meta = (analysis.metadata or {}).get("fit_meta", {})

        plot_meas_vs_fit(
            meas=meas, pred_fit=pred_fit,
            N_values=N_values, theta=theta, phi=phi,
            p_hat=p_hat, fit_meta=fit_meta,
            residual_mode=residual_mode,
        )

