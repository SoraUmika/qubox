"""qubox_v2.experiments.result
==============================
Unified result containers for experiment runs and analysis.

``RunResult`` already exists in ``hardware.program_runner`` and is
re-exported here for convenience.  ``AnalysisResult`` adds fitted
parameters, quality metrics, and optional plot artifacts on top of
the raw ``RunResult``.

Usage::

    from qubox_v2.experiments.result import RunResult, AnalysisResult

    result: RunResult = experiment.run(...)
    analysis = AnalysisResult.from_run(result, fit_params={...})
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

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
