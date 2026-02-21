"""Gate calibration experiments."""
from __future__ import annotations

from typing import Any

import numpy as np

from ..experiment_base import ExperimentBase
from ...analysis import post_process as pp
from ...hardware.program_runner import RunResult
from ...programs import cQED_programs


class AllXY(ExperimentBase):
    """All-XY gate error benchmarking (21 gate pairs).

    Each of 21 combinations of two single-qubit gates is applied,
    and the resulting population is measured to diagnose systematic
    gate errors.
    """

    def run(
        self,
        gate_indices: list[int] | None = None,
        prefix: str = "",
        qb_detuning: int = 0,
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        self.set_standard_frequencies(qb_fq=attr.qb_fq + qb_detuning)

        prog = cQED_programs.all_xy(
            attr.qb_el, n_avg, attr.qb_therm_clks,
            gate_indices=gate_indices, prefix=prefix,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[pp.proc_default],
        )
        self.save_output(result.output, "allXY")
        return result


class DRAGCalibration(ExperimentBase):
    """DRAG coefficient optimization (Yale method).

    Sweeps the DRAG amplitude parameter to minimize leakage to
    higher transmon levels.
    """

    def run(
        self,
        amps: np.ndarray | list[float],
        base_alpha: float,
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        amps = np.asarray(amps, dtype=float)

        self.set_standard_frequencies()

        prog = cQED_programs.drag_calibration_YALE(
            attr.qb_el, amps, base_alpha, attr.qb_therm_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("amps", amps),
            ],
        )
        self.save_output(result.output, "dragCalibration")
        return result


class QubitPulseTrainLegacy(ExperimentBase):
    """Legacy pulse train amplitude calibration.

    Applies K*N repeated rotation pulses per cycle and checks
    amplitude independence of P_e(N).
    """

    def run(
        self,
        N_values: list[int] | np.ndarray,
        K: int = 2,
        rotation_pulse: str = "x180",
        n_avg: int = 1000,
        r90_pulse: str = "x90",
    ) -> RunResult:
        attr = self.attr
        self.set_standard_frequencies()

        prog = cQED_programs.qubit_pulse_train_legacy(
            attr.qb_el, N_values, K, rotation_pulse,
            r90_pulse, attr.qb_therm_clks, n_avg,
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
            attr.qb_el, N_values, reference_pulse, rotation_pulse,
            run_reference, attr.qb_therm_clks, n_avg,
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


class RandomizedBenchmarking(ExperimentBase):
    """Standard and interleaved randomized benchmarking.

    Runs random Clifford sequences of varying depth to extract
    average gate fidelity. Supports interleaving a specific gate.
    """

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

        prog = cQED_programs.randomized_benchmarking(
            attr.qb_el, m_list, num_sequence, n_avg,
            attr.qb_therm_clks,
            interleave_op=interleave_op,
            primitives_by_id=primitives_by_id,
            primitive_prefix=primitive_prefix,
            max_sequences_per_compile=max_sequences_per_compile,
            guard_clks=guard_clks,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("m_list", np.asarray(m_list)),
            ],
        )
        self.save_output(result.output, "randomizedBenchmarking")
        return result
