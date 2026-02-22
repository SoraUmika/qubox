"""Gate calibration experiments."""
from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib.pyplot as plt

from ..experiment_base import ExperimentBase
from ..result import AnalysisResult, FitResult
from ...analysis import post_process as pp
from ...analysis.fitting import fit_and_wrap, build_fit_legend
from ...analysis.cQED_models import rb_survival_model
from ...analysis.algorithms import random_sequences
from ...hardware.program_runner import RunResult
from ...programs import cQED_programs


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

    def run(
        self,
        gate_indices: list[int] | None = None,
        prefix: str = "",
        qb_detuning: int = 0,
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        self.set_standard_frequencies(qb_fq=attr.qb_fq + qb_detuning)

        # Build rotation sequences
        if gate_indices is not None:
            ops = [self._ALLXY_SEQUENCES[i] for i in gate_indices]
        else:
            ops = list(self._ALLXY_SEQUENCES)

        if prefix:
            ops = [(f"{prefix}{g1}", f"{prefix}{g2}") for (g1, g2) in ops]

        prog = cQED_programs.all_xy(
            attr.qb_el, ops, attr.qb_therm_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[pp.proc_default, pp.proc_attach("ops", ops)],
        )
        self.save_output(result.output, "allXY")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        # Legacy parity: interpret measured boolean stream as P_e and report
        # corrected sigma_z = P_g - P_e (|g> -> +1, |e> -> -1).
        Pe = result.output.get("Pe")
        used_confusion = False
        if Pe is not None:
            Pe = result.output._format(Pe)
            pe_states = np.asarray(Pe, dtype=float)

            # Optional confusion-matrix correction (legacy parity).
            confusion = kw.get("confusion", None)
            if confusion is None:
                from ...programs.macros.measure import measureMacro
                confusion = measureMacro._ro_quality_params.get("confusion_matrix", None)

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
            mag = np.abs(S)
            if mag.max() != mag.min():
                pe_states = (mag - mag.min()) / (mag.max() - mag.min())
            else:
                pe_states = mag
            states = 1.0 - 2.0 * np.asarray(pe_states, dtype=float)

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
        }
        return AnalysisResult.from_run(result, metrics=metrics)

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        states = analysis.metrics.get("states", None)
        if states is None:
            S = analysis.data.get("S")
            if S is None:
                return None
            mag = np.abs(S)
            if mag.max() != mag.min():
                states = (mag - mag.min()) / (mag.max() - mag.min())
            else:
                states = mag

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

    def run(
        self,
        amps: np.ndarray | list[float],
        n_avg: int = 1000,
        *,
        base_alpha: float = 1.0,
        x180: str = "x180",
        x90: str = "x90",
        y180: str = "y180",
        y90: str = "y90",
    ) -> RunResult:
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
        x180, x90, y180, y90 : str
            Fallback pulse operation names (used only when ``base_alpha``
            is exactly 0, i.e. no temporary waveform generation).
        """
        from ...analysis.pulseOp import PulseOp
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

        self.set_standard_frequencies()

        # ----- Legacy parity: generate DRAG waveforms with base_alpha -----
        # Retrieve pulse parameters from calibration store or attributes
        cal = self.calibration_store
        ref_cal = cal.get_pulse_calibration("ref_r180") if cal else None

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

        # Build QUA program using temporary ops
        prog = cQED_programs.drag_calibration_YALE(
            attr.qb_el, amps,
            "x180_tmp", "x90_tmp", "y180_tmp", "y90_tmp",
            attr.qb_therm_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("amps", amps),
                pp.proc_attach("base_alpha", float(base_alpha)),
                pp.proc_attach("pulse_len", int(rlen)),
            ],
            targets=[("I1", "Q1"), ("I2", "Q2")],
        )
        self.save_output(result.output, "dragCalibration")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        from ...analysis.algorithms import find_roots

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

        analysis = AnalysisResult.from_run(result, metrics=metrics)

        if update_calibration and self.calibration_store:
            alpha_lo = float(np.min(amps) * base_alpha) if len(amps) else None
            alpha_hi = float(np.max(amps) * base_alpha) if len(amps) else None
            self.guarded_calibration_commit(
                analysis=analysis,
                run_result=result,
                calibration_tag="drag_calibration_x180",
                require_fit=False,
                required_metrics={"optimal_alpha": (alpha_lo, alpha_hi)},
                apply_update=lambda: (
                    self.calibration_store.set_pulse_calibration(
                        name="ref_r180", drag_coeff=metrics["optimal_alpha"],
                    ),
                    self.calibration_store.set_pulse_calibration(
                        name="x180", drag_coeff=metrics["optimal_alpha"],
                    ),
                ),
            )

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


class QubitPulseTrainLegacy(ExperimentBase):
    """Legacy pulse train amplitude calibration.

    Applies N repeated rotation pulses after a reference pulse and checks
    amplitude independence of the measured signal.
    """

    def run(
        self,
        N_values: list[int] | np.ndarray,
        rotation_pulse: str = "x180",
        n_avg: int = 1000,
        reference_pulse: str = "x90",
    ) -> RunResult:
        attr = self.attr
        self.set_standard_frequencies()

        # Look up pulse durations (in clock cycles) from pulse manager
        ref_info = self.pulse_mgr.get_pulseOp_by_element_op(attr.qb_el, reference_pulse)
        rot_info = self.pulse_mgr.get_pulseOp_by_element_op(attr.qb_el, rotation_pulse)
        if ref_info is None:
            raise ValueError(f"No PulseOp found for '{reference_pulse}' on '{attr.qb_el}'")
        if rot_info is None:
            raise ValueError(f"No PulseOp found for '{rotation_pulse}' on '{attr.qb_el}'")

        reference_clks = int(ref_info.length) // 4
        rotation_clks = int(rot_info.length) // 4

        prog = cQED_programs.qubit_pulse_train_legacy(
            attr.qb_el, reference_pulse, rotation_pulse,
            reference_clks, rotation_clks,
            N_values, attr.qb_therm_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("N_values", np.asarray(N_values)),
            ],
        )
        self.save_output(result.output, "qubitPulseTrainLegacy")
        return result


class QubitPulseTrain(ExperimentBase):
    """Improved pulse train amplitude calibration.

    Optionally includes zero-amplitude reference measurements
    for background subtraction.
    """

    def run(
        self,
        N_values: list[int] | np.ndarray,
        reference_pulse: str = "x90",
        rotation_pulse: str = "x180",
        run_reference: bool = False,
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        self.set_standard_frequencies()

        prog = cQED_programs.qubit_pulse_train(
            attr.qb_el, reference_pulse, rotation_pulse,
            N_values, attr.qb_therm_clks, n_avg,
            run_reference,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("N_values", np.asarray(N_values)),
            ],
        )
        self.save_output(result.output, "qubitPulseTrain")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        N_values = result.output.extract("N_values")

        # Legacy parity: prefer state discrimination (Pe) over raw I/Q
        # QUA program saves "state" (boolean_to_int averaged) for pulse train
        Pe = result.output.get("state")
        if Pe is not None:
            Pe = result.output._format(Pe)
        if Pe is None:
            Pe = result.output.get("Pe")
            if Pe is not None:
                Pe = result.output._format(Pe)

        S = result.output.extract("S")
        I_vals = np.real(S)
        Q_vals = np.imag(S)

        # Optional confusion-matrix correction
        if Pe is not None:
            Pe = np.asarray(Pe, dtype=float)
            confusion = kw.get("confusion", None)
            if confusion is None:
                from ...programs.macros.measure import measureMacro
                confusion = measureMacro._ro_quality_params.get("confusion_matrix", None)
            if confusion is not None:
                corrected = pp.ro_state_correct_proc(
                    {"Pe": Pe},
                    targets=[("Pe", "Pe_corr")],
                    confusion=confusion,
                )
                Pe = corrected.get("Pe_corr", Pe)

        # Compute amplitude error from deviation vs N
        metrics: dict[str, Any] = {}
        if len(I_vals) > 1:
            metrics["I_std"] = float(np.std(I_vals))
            metrics["Q_std"] = float(np.std(Q_vals))
            metrics["amp_err"] = float(np.std(np.abs(S)))
        if Pe is not None:
            metrics["Pe"] = Pe

        return AnalysisResult.from_run(result, metrics=metrics)

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        N_values = analysis.data.get("N_values")
        S = analysis.data.get("S")
        if N_values is None or S is None:
            return None

        if ax is None:
            fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        else:
            fig = ax.figure
            axes = [ax, ax.twinx()]

        axes[0].scatter(N_values, np.real(S), s=5, c="blue", label="I")
        axes[0].scatter(N_values, np.imag(S), s=5, c="red", label="Q")
        axes[0].set_xlabel("N (pulse repetitions)")
        axes[0].set_ylabel("I / Q (a.u.)")
        axes[0].set_title("Pulse Train: I/Q vs N")
        axes[0].legend()
        axes[0].grid(True, alpha=0.3)

        axes[1].scatter(N_values, np.abs(S), s=5, c="green", label="|S|")
        axes[1].set_xlabel("N (pulse repetitions)")
        axes[1].set_ylabel("Magnitude")
        title = "Pulse Train: Magnitude vs N"
        if "amp_err" in analysis.metrics:
            title += f"  |  amp_err = {analysis.metrics['amp_err']:.4f}"
        axes[1].set_title(title)
        axes[1].legend()
        axes[1].grid(True, alpha=0.3)

        plt.tight_layout()
        plt.show()
        return fig


class RandomizedBenchmarking(ExperimentBase):
    """Standard and interleaved randomized benchmarking.

    Runs random Clifford sequences of varying depth to extract
    average gate fidelity. Supports interleaving a specific gate.
    """

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
    ) -> RunResult:
        attr = self.attr
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
        from ...analysis.output import Output
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
                    qb_therm_clks=attr.qb_therm_clks,
                    n_avg=n_avg,
                    primitives_by_id=primitives_by_id,
                    primitive_clks=int(primitive_clks),
                    guard_clks=int(guard_clks),
                    interleave_op=(str(interleave_op) if do_interleave else None),
                    interleave_clks=(int(interleave_clks) if do_interleave else None),
                    interleave_sentinel=int(interleave_sentinel),
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
                from ...programs.macros.measure import measureMacro
                confusion = measureMacro._ro_quality_params.get("confusion_matrix", None)
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
