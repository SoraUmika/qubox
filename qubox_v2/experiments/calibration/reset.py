"""Qubit reset and leakage benchmarking experiments."""
from __future__ import annotations

from typing import Any

from ..experiment_base import ExperimentBase
from ...analysis import post_process as pp
from ...hardware.program_runner import RunResult
from ...programs import cQED_programs


class QubitResetBenchmark(ExperimentBase):
    """Qubit reset fidelity benchmark.

    Prepares random bit sequences and measures reset quality
    (conditional and unconditional error rates).
    """

    def run(
        self,
        bit_size: int = 1_000,
        num_shots: int = 20_000,
        r180: str = "x180",
        random_seed: int | None = None,
    ) -> RunResult:
        attr = self.attr
        self.set_standard_frequencies()

        prog = cQED_programs.qubit_reset_benchmark(
            attr.qb_el, bit_size, r180,
            attr.qb_therm_clks, num_shots,
            random_seed=random_seed,
        )
        result = self.run_program(
            prog, n_total=num_shots,
            processors=[pp.proc_default],
        )
        self.save_output(result.output, "qubitResetBenchmark")
        return result


class ActiveQubitResetBenchmark(ExperimentBase):
    """Active reset effectiveness measurement.

    Uses post-selection and multi-measurement correction to
    characterize active reset quality.
    """

    def run(
        self,
        post_sel_policy: str,
        post_sel_kwargs: dict | None = None,
        show_analysis: bool = True,
        MAX_PREP_TRIALS: int = 100,
        n_shots: int = 10_000,
    ) -> RunResult:
        attr = self.attr
        self.set_standard_frequencies()

        prog = cQED_programs.active_qubit_reset_benchmark(
            attr.qb_el, attr.ro_el,
            post_sel_policy, post_sel_kwargs or {},
            MAX_PREP_TRIALS, attr.qb_therm_clks, n_shots,
        )
        result = self.run_program(
            prog, n_total=n_shots,
            processors=[pp.proc_default],
        )
        self.save_output(result.output, "activeResetBenchmark")
        return result


class ReadoutLeakageBenchmarking(ExperimentBase):
    """Readout leakage to higher transmon states benchmark."""

    def run(
        self,
        control_bits: list[int],
        r180: str = "x180",
        num_sequences: int = 10,
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        self.set_standard_frequencies()

        prog = cQED_programs.readout_leakage_benchmarking(
            attr.qb_el, attr.ro_el, control_bits,
            r180, num_sequences,
            attr.qb_therm_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[pp.proc_default],
        )
        self.save_output(result.output, "readoutLeakageBenchmark")
        return result
