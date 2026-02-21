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

    # Expected Pe for each pair: 5 ground, 12 superposition, 4 excited
    _ALLXY_IDEAL = np.array([
        0, 0, 0, 0, 0,
        0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5,
        1, 1, 1, 1,
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
            processors=[pp.proc_default],
        )
        self.save_output(result.output, "allXY")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        S = result.output.extract("S")
        mag = np.abs(S)

        # Normalize to [0, 1] range
        if mag.max() != mag.min():
            states = (mag - mag.min()) / (mag.max() - mag.min())
        else:
            states = mag

        ideal = self._ALLXY_IDEAL
        if len(states) == len(ideal):
            gate_error = float(np.mean(np.abs(states - ideal)))
        else:
            gate_error = float("nan")

        metrics: dict[str, Any] = {"gate_error": gate_error}
        return AnalysisResult.from_run(result, metrics=metrics)

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
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
        ax.set_ylabel("Normalized Population")
        ax.set_ylim(-0.1, 1.1)
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig


class DRAGCalibration(ExperimentBase):
    """DRAG coefficient optimization (Yale method).

    Sweeps the DRAG amplitude parameter to minimize leakage to
    higher transmon levels.
    """

    def run(
        self,
        amps: np.ndarray | list[float],
        n_avg: int = 1000,
        *,
        x180: str = "x180",
        x90: str = "x90",
        y180: str = "y180",
        y90: str = "y90",
    ) -> RunResult:
        attr = self.attr
        amps = np.asarray(amps, dtype=float)

        self.set_standard_frequencies()

        prog = cQED_programs.drag_calibration_YALE(
            attr.qb_el, amps, x180, x90, y180, y90,
            attr.qb_therm_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("amps", amps),
            ],
            targets=[("I1", "Q1"), ("I2", "Q2")],
        )
        self.save_output(result.output, "dragCalibration")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        amps = result.output.extract("amps")
        S_1 = result.output.get("S_1")
        S_2 = result.output.get("S_2")

        # DRAG optimal alpha: difference of two sequences should cross zero
        I_diff = np.real(S_1) - np.real(S_2)

        # Find zero-crossing in I difference
        metrics: dict[str, Any] = {}
        sign_changes = np.where(np.diff(np.sign(I_diff)))[0]
        if len(sign_changes) > 0:
            idx = sign_changes[0]
            # Linear interpolation for precise crossing
            x0, x1 = float(amps[idx]), float(amps[idx + 1])
            y0, y1 = float(I_diff[idx]), float(I_diff[idx + 1])
            if y1 != y0:
                optimal_alpha = x0 - y0 * (x1 - x0) / (y1 - y0)
            else:
                optimal_alpha = (x0 + x1) / 2
            metrics["optimal_alpha"] = optimal_alpha
        else:
            metrics["optimal_alpha"] = float(amps[np.argmin(np.abs(I_diff))])

        analysis = AnalysisResult.from_run(result, metrics=metrics)

        if update_calibration and self.calibration_store:
            self.calibration_store.set_pulse_calibration(
                name="x180", drag_coeff=metrics["optimal_alpha"],
            )

        return analysis

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        amps = analysis.data.get("amps")
        S_1 = analysis.data.get("S_1")
        S_2 = analysis.data.get("S_2")
        if amps is None or S_1 is None or S_2 is None:
            return None

        I_diff = np.real(S_1) - np.real(S_2)
        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 5))
        else:
            fig = ax.figure

        ax.scatter(amps, np.real(S_1), s=5, c="blue", alpha=0.5, label="Seq 1 (I)")
        ax.scatter(amps, np.real(S_2), s=5, c="red", alpha=0.5, label="Seq 2 (I)")
        ax.plot(amps, I_diff, "k-", lw=1.5, label="Difference")
        ax.axhline(0, color="gray", ls="-", lw=0.5, alpha=0.5)

        if "optimal_alpha" in analysis.metrics:
            ax.axvline(analysis.metrics["optimal_alpha"], color="r", ls="--", lw=1.5,
                       label=f"Optimal alpha = {analysis.metrics['optimal_alpha']:.4f}")

        ax.set_xlabel("DRAG Amplitude")
        ax.set_ylabel("I (a.u.)")
        ax.set_title("DRAG Calibration")
        ax.legend()
        ax.grid(True, alpha=0.3)
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
        S = result.output.extract("S")
        I_vals = np.real(S)
        Q_vals = np.imag(S)

        # Compute amplitude error from deviation of I/Q vs N
        metrics: dict[str, Any] = {}
        if len(I_vals) > 1:
            # Ideal: I should be constant for perfect pi-pulses
            metrics["I_std"] = float(np.std(I_vals))
            metrics["Q_std"] = float(np.std(Q_vals))
            metrics["amp_err"] = float(np.std(np.abs(S)))

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

        # Run all batched programs
        runres_template = None
        for meta, prog in zip(queued_meta, programs):
            result = self.run_program(
                prog, n_total=n_avg,
                processors=[pp.proc_default],
            )
            if runres_template is None:
                runres_template = result

            I_batch = np.real(np.asarray(result.output.extract("S"), dtype=complex))
            Q_batch = np.imag(np.asarray(result.output.extract("S"), dtype=complex))

            m_idx = meta["m_idx"]
            start = meta["start"]
            end = meta["end"]

            I_mat[m_idx, start:end] = I_batch
            Q_mat[m_idx, start:end] = Q_batch

        # Average over sequences for each depth
        I_avg = np.nanmean(I_mat, axis=1)
        Q_avg = np.nanmean(Q_mat, axis=1)
        S_avg = I_avg + 1j * Q_avg

        output = Output({
            "S": S_avg,
            "m_list": np.asarray(m_list_int),
            "I_matrix": I_mat,
            "Q_matrix": Q_mat,
        })
        self.save_output(output, "randomizedBenchmarking")

        if runres_template is not None:
            runres_template.output = output
            return runres_template
        return RunResult(mode=ExecMode.HARDWARE, output=output, sim_samples=None)

    def analyze(self, result: RunResult, *, update_calibration: bool = False, p0=None, **kw) -> AnalysisResult:
        m_list = result.output.extract("m_list")
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
        S = analysis.data.get("S")
        if m_list is None or S is None:
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
