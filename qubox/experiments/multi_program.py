"""Multi-program experiment base class (P2.1).

``MultiProgramExperiment`` extends :class:`ExperimentBase` for experiments
that build, run, and analyse **multiple** QUA programs in a single logical
experiment.  Examples include interleaved randomised benchmarking,
multi-sweep power-Rabi fans, and frequency-multiplexed readout
characterisation.

Usage::

    class InterleavedRB(MultiProgramExperiment):
        def build_programs(self, *, n_cliffords, n_random, **kw):
            programs = []
            for seed in range(n_random):
                programs.append(self._build_single_rb(n_cliffords, seed=seed))
            return programs

        def merge_results(self, results):
            # Average fidelities across random seeds
            ...

    exp = InterleavedRB(session)
    merged = exp.run_all(n_cliffords=20, n_random=30)

.. versionadded:: 2.1.0
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Sequence

from ..core.logging import get_logger
from .experiment_base import ExperimentBase
from .result import AnalysisResult, ProgramBuildResult

_logger = get_logger(__name__)


@dataclass
class MultiProgramResult:
    """Container for the combined result of a multi-program experiment.

    Attributes
    ----------
    individual_results : list[AnalysisResult]
        Per-program analysis results.
    merged : AnalysisResult | None
        Result of ``merge_results()``, if the subclass implements it.
    builds : list[ProgramBuildResult]
        Build artefacts for each program (provenance).
    metadata : dict
        Experiment-level metadata.
    """

    individual_results: list[AnalysisResult] = field(default_factory=list)
    merged: AnalysisResult | None = None
    builds: list[ProgramBuildResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class MultiProgramExperiment(ExperimentBase):
    """Base class for experiments that run multiple QUA programs.

    Subclasses **must** implement:

    * :meth:`build_programs` — return a list of ``ProgramBuildResult``.

    Subclasses **should** implement:

    * :meth:`analyze_single` — post-process a single run result.
    * :meth:`merge_results` — combine per-program results into one.

    The :meth:`run_all` convenience orchestrates the full lifecycle:
    build → run each → analyse each → merge.
    """

    # ------------------------------------------------------------------
    # Subclass hooks (override these)
    # ------------------------------------------------------------------
    def build_programs(self, **kwargs: Any) -> list[ProgramBuildResult]:
        """Build QUA programs for this experiment.

        Returns a list of :class:`ProgramBuildResult` objects that will
        be executed in sequence.

        Raises
        ------
        NotImplementedError
            Subclass must provide an implementation.
        """
        raise NotImplementedError(
            f"{self.name}.build_programs() must be overridden."
        )

    def analyze_single(
        self,
        run_result: Any,
        build: ProgramBuildResult,
        index: int,
        **kwargs: Any,
    ) -> AnalysisResult:
        """Post-process a single program's run result.

        Default implementation wraps the raw output into an
        :class:`AnalysisResult` without fitting.  Override for
        experiment-specific analysis.

        Parameters
        ----------
        run_result
            The raw ``RunResult`` from executing the program.
        build
            The ``ProgramBuildResult`` that produced this program.
        index
            Zero-based index of this program in the batch.

        Returns
        -------
        AnalysisResult
        """
        return AnalysisResult.from_run(
            run_result,
            metadata={"program_index": index, "experiment": self.name},
        )

    def merge_results(
        self,
        results: list[AnalysisResult],
        builds: list[ProgramBuildResult],
        **kwargs: Any,
    ) -> AnalysisResult | None:
        """Combine individual program results into a single merged result.

        Default returns ``None`` (no merging).  Override to implement
        averaging, concatenation, or other combination logic.
        """
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run_all(
        self,
        *,
        analyze: bool = True,
        merge: bool = True,
        run_kwargs: dict[str, Any] | None = None,
        **build_kwargs: Any,
    ) -> MultiProgramResult:
        """Build, execute, and optionally analyse all programs.

        Parameters
        ----------
        analyze : bool
            If True, call ``analyze_single`` on each result.
        merge : bool
            If True (and ``analyze`` is True), call ``merge_results``.
        run_kwargs : dict, optional
            Extra kwargs forwarded to ``hw.run_program(...)``.
        **build_kwargs
            Forwarded to ``build_programs()``.

        Returns
        -------
        MultiProgramResult
        """
        run_kwargs = dict(run_kwargs or {})

        _logger.info(
            "%s: building programs with %s",
            self.name,
            {k: repr(v)[:80] for k, v in build_kwargs.items()},
        )
        builds = self.build_programs(**build_kwargs)
        n = len(builds)
        _logger.info("%s: %d program(s) to execute", self.name, n)

        individual: list[AnalysisResult] = []
        for i, build in enumerate(builds):
            _logger.info("%s: running program %d/%d", self.name, i + 1, n)
            run_result = self._execute_build(build, **run_kwargs)

            if analyze:
                ar = self.analyze_single(run_result, build, index=i)
            else:
                ar = AnalysisResult.from_run(
                    run_result,
                    metadata={"program_index": i, "experiment": self.name},
                )
            individual.append(ar)

        merged = None
        if analyze and merge:
            merged = self.merge_results(individual, builds, **build_kwargs)
            if merged is not None:
                _logger.info("%s: merge complete", self.name)

        return MultiProgramResult(
            individual_results=individual,
            merged=merged,
            builds=builds,
            metadata={
                "experiment": self.name,
                "n_programs": n,
                "timestamp": _dt.datetime.now().isoformat(),
                "build_kwargs": {
                    k: repr(v)[:200] for k, v in build_kwargs.items()
                },
            },
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _execute_build(self, build: ProgramBuildResult, **run_kwargs: Any) -> Any:
        """Run a single ``ProgramBuildResult`` via the hardware controller.

        Subclasses can override to add pre/post hooks (e.g. frequency
        setting, pulse burn).
        """
        # Set element frequencies if provided
        hw = self.hw
        for element, freq in (build.resolved_frequencies or {}).items():
            try:
                hw.set_element_frequency(element, freq)
            except Exception as exc:
                _logger.warning(
                    "Could not set frequency for %s=%s: %s",
                    element, freq, exc,
                )

        return hw.run_program(
            build.program,
            n_total=build.n_total,
            processors=build.processors,
            **build.run_program_kwargs,
            **run_kwargs,
        )
