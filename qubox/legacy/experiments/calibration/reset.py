"""Qubit reset and leakage benchmarking experiments."""
from __future__ import annotations

from typing import Any

from ..experiment_base import ExperimentBase
from ..result import ProgramBuildResult
from ...analysis import post_process as pp
from ...hardware.program_runner import RunResult
from ...programs import api as cQED_programs
from ...programs.measurement import try_build_readout_snapshot_from_macro


class QubitResetBenchmark(ExperimentBase):
    """Qubit reset fidelity benchmark.

    Prepares random bit sequences and measures reset quality
    (conditional and unconditional error rates).
    """

    def _build_impl(
        self,
        bit_size: int = 1_000,
        num_shots: int = 20_000,
        r180: str = "x180",
        random_seed: int | None = None,
        qb_therm_clks: int | None = None,
    ) -> ProgramBuildResult:
        attr = self.attr
        qb_therm = self.resolve_override_or_attr(
            value=qb_therm_clks,
            attr_name="qb_therm_clks",
            owner="QubitResetBenchmark",
            cast=int,
        )

        prog = cQED_programs.qubit_reset_benchmark(
            attr.qb_el, bit_size, r180,
            qb_therm, num_shots,
            random_seed=random_seed,
        )
        return ProgramBuildResult(
            program=prog,
            n_total=num_shots,
            processors=(pp.proc_default,),
            experiment_name="QubitResetBenchmark",
            params={
                "bit_size": bit_size,
                "num_shots": num_shots,
                "r180": r180,
                "random_seed": random_seed,
                "qb_therm_clks": qb_therm,
            },
            resolved_frequencies={
                attr.ro_el: self._resolve_readout_frequency(),
                attr.qb_el: self._resolve_qubit_frequency(),
            },
            bindings_snapshot=self._serialize_bindings(),
            builder_function="cQED_programs.qubit_reset_benchmark",
            measure_macro_state=try_build_readout_snapshot_from_macro(),
        )

    def run(
        self,
        bit_size: int = 1_000,
        num_shots: int = 20_000,
        r180: str = "x180",
        random_seed: int | None = None,
        qb_therm_clks: int | None = None,
    ) -> RunResult:
        build = self.build_program(
            bit_size=bit_size,
            num_shots=num_shots,
            r180=r180,
            random_seed=random_seed,
            qb_therm_clks=qb_therm_clks,
        )
        result = self.run_program(
            build.program, n_total=build.n_total,
            processors=list(build.processors),
        )
        self.save_output(result.output, "qubitResetBenchmark")
        return result


class ActiveQubitResetBenchmark(ExperimentBase):
    """Active reset effectiveness measurement.

    Uses post-selection and multi-measurement correction to
    characterize active reset quality.
    """

    def _build_impl(
        self,
        post_sel_policy: str,
        post_sel_kwargs: dict | None = None,
        show_analysis: bool = True,
        MAX_PREP_TRIALS: int = 100,
        n_shots: int = 10_000,
        qb_therm_clks: int | None = None,
    ) -> ProgramBuildResult:
        attr = self.attr
        qb_therm = self.resolve_override_or_attr(
            value=qb_therm_clks,
            attr_name="qb_therm_clks",
            owner="ActiveQubitResetBenchmark",
            cast=int,
        )

        prog = cQED_programs.active_qubit_reset_benchmark(
            attr.qb_el, attr.ro_el,
            post_sel_policy, post_sel_kwargs or {},
            MAX_PREP_TRIALS, qb_therm, n_shots,
        )
        return ProgramBuildResult(
            program=prog,
            n_total=n_shots,
            processors=(pp.proc_default,),
            experiment_name="ActiveQubitResetBenchmark",
            params={
                "post_sel_policy": post_sel_policy,
                "post_sel_kwargs": dict(post_sel_kwargs or {}),
                "show_analysis": bool(show_analysis),
                "MAX_PREP_TRIALS": MAX_PREP_TRIALS,
                "n_shots": n_shots,
                "qb_therm_clks": qb_therm,
            },
            resolved_frequencies={
                attr.ro_el: self._resolve_readout_frequency(),
                attr.qb_el: self._resolve_qubit_frequency(),
            },
            bindings_snapshot=self._serialize_bindings(),
            builder_function="cQED_programs.active_qubit_reset_benchmark",
            measure_macro_state=try_build_readout_snapshot_from_macro(),
        )

    def run(
        self,
        post_sel_policy: str,
        post_sel_kwargs: dict | None = None,
        show_analysis: bool = True,
        MAX_PREP_TRIALS: int = 100,
        n_shots: int = 10_000,
        qb_therm_clks: int | None = None,
    ) -> RunResult:
        build = self.build_program(
            post_sel_policy=post_sel_policy,
            post_sel_kwargs=post_sel_kwargs,
            show_analysis=show_analysis,
            MAX_PREP_TRIALS=MAX_PREP_TRIALS,
            n_shots=n_shots,
            qb_therm_clks=qb_therm_clks,
        )
        result = self.run_program(
            build.program, n_total=build.n_total,
            processors=list(build.processors),
        )
        self.save_output(result.output, "activeResetBenchmark")
        return result


class ReadoutLeakageBenchmarking(ExperimentBase):
    """Readout leakage to higher transmon states benchmark."""

    def _build_impl(
        self,
        control_bits: list[int],
        r180: str = "x180",
        num_sequences: int = 10,
        n_avg: int = 1000,
        qb_therm_clks: int | None = None,
    ) -> ProgramBuildResult:
        attr = self.attr
        qb_therm = self.resolve_override_or_attr(
            value=qb_therm_clks,
            attr_name="qb_therm_clks",
            owner="ReadoutLeakageBenchmarking",
            cast=int,
        )

        prog = cQED_programs.readout_leakage_benchmarking(
            attr.qb_el, attr.ro_el, control_bits,
            r180, num_sequences,
            qb_therm, n_avg,
        )
        return ProgramBuildResult(
            program=prog,
            n_total=n_avg,
            processors=(pp.proc_default,),
            experiment_name="ReadoutLeakageBenchmarking",
            params={
                "control_bits": list(control_bits),
                "r180": r180,
                "num_sequences": num_sequences,
                "n_avg": n_avg,
                "qb_therm_clks": qb_therm,
            },
            resolved_frequencies={
                attr.ro_el: self._resolve_readout_frequency(),
                attr.qb_el: self._resolve_qubit_frequency(),
            },
            bindings_snapshot=self._serialize_bindings(),
            builder_function="cQED_programs.readout_leakage_benchmarking",
            measure_macro_state=try_build_readout_snapshot_from_macro(),
        )

    def run(
        self,
        control_bits: list[int],
        r180: str = "x180",
        num_sequences: int = 10,
        n_avg: int = 1000,
        qb_therm_clks: int | None = None,
    ) -> RunResult:
        build = self.build_program(
            control_bits=control_bits,
            r180=r180,
            num_sequences=num_sequences,
            n_avg=n_avg,
            qb_therm_clks=qb_therm_clks,
        )
        result = self.run_program(
            build.program, n_total=build.n_total,
            processors=list(build.processors),
        )
        self.save_output(result.output, "readoutLeakageBenchmark")
        return result
