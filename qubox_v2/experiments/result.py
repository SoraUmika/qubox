"""qubox_v2.experiments.result
==============================
Unified result containers for experiment runs, analysis, and simulation.

``RunResult`` already exists in ``hardware.program_runner`` and is
re-exported here for convenience.  ``AnalysisResult`` adds fitted
parameters, quality metrics, and optional plot artifacts on top of
the raw ``RunResult``.

``ProgramBuildResult`` captures an immutable snapshot of a built QUA
program together with resolved parameters and provenance metadata.
``SimulationResult`` wraps simulated waveform samples with the full
provenance chain.

Usage::

    from qubox_v2.experiments.result import RunResult, AnalysisResult
    from qubox_v2.experiments.result import ProgramBuildResult, SimulationResult

    result: RunResult = experiment.run(...)
    analysis = AnalysisResult.from_run(result, fit_params={...})

    build: ProgramBuildResult = experiment.build_program(...)
    sim: SimulationResult = experiment.simulate(...)
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import numpy as np

# Re-export for convenience
from ..hardware.program_runner import RunResult  # noqa: F401


@dataclass
class FitResult:
    """Fitted parameter set from curve-fitting an experiment."""

    model_name: str
    """Name of the fit model (e.g. 'lorentzian', 'exponential_decay')."""

    params: dict[str, float]
    """Best-fit parameter values."""

    uncertainties: dict[str, float] = field(default_factory=dict)
    """Parameter uncertainties (1-sigma)."""

    r_squared: float | None = None
    """Goodness-of-fit metric."""

    residuals: np.ndarray | None = None
    """Fit residuals array."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional fit metadata (e.g. bounds, method, n_iterations)."""


@dataclass
class AnalysisResult:
    """Container for post-processed experiment results.

    Wraps a ``RunResult`` with fitted parameters, derived quantities,
    and quality metrics.
    """

    data: dict[str, Any]
    """Processed experimental data (frequencies, amplitudes, phases, etc.)."""

    fit: FitResult | None = None
    """Primary fit result, if applicable."""

    fits: dict[str, FitResult] = field(default_factory=dict)
    """Named collection of fit results for multi-fit experiments."""

    metrics: dict[str, Any] = field(default_factory=dict)
    """Scalar quality metrics (fidelity, SNR, T1, T2, etc.)."""

    source: RunResult | None = None
    """Original ``RunResult`` this analysis was derived from."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Freeform metadata (experiment name, parameters, timestamp)."""

    @classmethod
    def from_run(
        cls,
        run_result: RunResult,
        *,
        fit: FitResult | None = None,
        fits: dict[str, FitResult] | None = None,
        metrics: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "AnalysisResult":
        """Create an AnalysisResult from a RunResult.

        Parameters
        ----------
        metadata : dict, optional
            Additional metadata to merge with the RunResult's own metadata.
            Keys supplied here take precedence over RunResult.metadata.
        """
        data = dict(run_result.output) if run_result.output else {}
        base_metadata = dict(run_result.metadata) if run_result.metadata else {}
        if metadata:
            base_metadata.update(metadata)
        return cls(
            data=data,
            fit=fit,
            fits=fits or {},
            metrics=metrics or {},
            source=run_result,
            metadata=base_metadata,
        )

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from data dict."""
        return self.data.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def __contains__(self, key: str) -> bool:
        return key in self.data


# ---------------------------------------------------------------------------
# Build / Simulation types (v2.2 — program-as-artifact)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ProgramBuildResult:
    """Immutable snapshot produced by ``ExperimentBase.build_program()``.

    Contains everything needed to **execute** or **simulate** a QUA program,
    plus provenance metadata for reproducibility.
    """

    # ── Core payload ──
    program: Any
    """The QUA program object (``qm.qua._Program``)."""

    n_total: int
    """Total shot count for progress tracking and result shaping."""

    processors: tuple[Callable, ...] = ()
    """Post-processing pipeline to apply to raw output."""

    # ── Provenance ──
    experiment_name: str = ""
    """Fully qualified experiment class name (e.g. ``"PowerRabi"``)."""

    params: dict[str, Any] = field(default_factory=dict)
    """Frozen copy of the resolved parameters used to build the program."""

    resolved_frequencies: dict[str, float] = field(default_factory=dict)
    """``{element_name: frequency_hz}`` — exact frequencies to set before
    program execution or simulation."""

    bindings_snapshot: dict[str, Any] | None = None
    """Serialisable snapshot of ``ExperimentBindings`` state."""

    # ── Optional metadata ──
    builder_function: str | None = None
    """Name of the ``cQED_programs.*`` function that built the program."""

    sweep_axes: dict[str, Any] | None = None
    """``{axis_name: array_or_description}`` for each swept parameter."""

    measure_macro_state: dict[str, Any] | None = None
    """Snapshot of ``measureMacro`` configuration at build time."""

    timestamp: str = field(default_factory=lambda: _dt.datetime.now().isoformat())
    """ISO-8601 build time."""

    run_program_kwargs: dict[str, Any] = field(default_factory=dict)
    """Additional kwargs to forward to ``run_program()``."""


@dataclass
class SimulationResult:
    """Result of simulating a QUA program.

    Carries both the simulated waveform samples and the full provenance
    chain back to the build step.
    """

    samples: Any
    """Relabelled ``SimulatorSamples`` (dict[controller → samples]).
    Keys are ``element:I`` / ``element:Q`` after relabelling."""

    build: ProgramBuildResult
    """The build result that produced the program being simulated."""

    config_snapshot: dict[str, Any] = field(default_factory=dict)
    """QM config dict used for simulation (deep copy at sim time)."""

    sim_config: Any = None
    """The ``QuboxSimulationConfig`` used."""

    duration_ns: int = 4000
    """Actual simulation duration in nanoseconds."""

    def analog_channels(self) -> dict[str, np.ndarray]:
        """Flatten all analog channels across controllers into a single dict."""
        out: dict[str, np.ndarray] = {}
        for ctrl, con in (self.samples or {}).items():
            for name, arr in getattr(con, "analog", {}).items():
                out[f"{ctrl}:{name}"] = np.asarray(arr)
        return out

    def digital_channels(self) -> dict[str, np.ndarray]:
        """Flatten all digital channels across controllers into a single dict."""
        out: dict[str, np.ndarray] = {}
        for ctrl, con in (self.samples or {}).items():
            for name, arr in getattr(con, "digital", {}).items():
                out[f"{ctrl}:{name}"] = np.asarray(arr)
        return out
