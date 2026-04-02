"""qubox.calibration.store_models — Pydantic v2 calibration data models.

Migrated from ``qubox_v2_legacy.calibration.models`` with no changes to
logic.  All models are standalone (no qubox_v2_legacy imports).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Readout discrimination
# ---------------------------------------------------------------------------

class DiscriminationParams(BaseModel):
    """Parameters for single-shot readout state discrimination."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    threshold: float
    angle: float
    mu_g: list[float]   # [I, Q] centroid for |g>
    mu_e: list[float]   # [I, Q] centroid for |e>
    sigma_g: float
    sigma_e: float
    fidelity: float | None = None
    confusion_matrix: list[list[float]] | None = None

    n_shots: int | None = None
    integration_time_ns: int | None = None
    demod_weights: list[str] | None = None
    state_prep_ops: list[str] | None = None


class ReadoutQuality(BaseModel):
    """Readout quality metrics from butterfly measurement."""

    alpha: float | None = None
    beta: float | None = None
    F: float | None = None      # assignment fidelity
    Q: float | None = None      # QND-ness
    V: float | None = None      # visibility
    t01: float | None = None    # 0→1 transition probability
    t10: float | None = None    # 1→0 transition probability
    confusion_matrix: list[list[float]] | None = None
    affine_n: dict[str, list[float]] | None = None

    n_shots: int | None = None
    integration_time_ns: int | None = None
    demod_weights: list[str] | None = None
    state_prep_ops: list[str] | None = None


# ---------------------------------------------------------------------------
# Element frequency calibration
# ---------------------------------------------------------------------------

class ElementFrequencies(BaseModel):
    """Calibrated frequencies for a quantum element.

    Both LO+IF and absolute rf_freq representations are supported.
    Only fields with actual calibrated values should be set; unset fields
    are ``None`` and omitted from the persisted JSON.
    """

    lo_freq: float | None = None
    if_freq: float | None = None
    rf_freq: float | None = None
    resonator_freq: float | None = None
    qubit_freq: float | None = None
    storage_freq: float | None = None
    ef_freq: float | None = None
    anharmonicity: float | None = None
    fock_freqs: list[float] | None = None
    chi: float | None = None
    chi2: float | None = None
    chi3: float | None = None
    kappa: float | None = None
    kerr: float | None = None
    kerr2: float | None = None


# ---------------------------------------------------------------------------
# Coherence parameters
# ---------------------------------------------------------------------------

class CoherenceParams(BaseModel):
    """Coherence time calibration results."""

    T1: float | None = None           # seconds
    T1_us: float | None = None        # microseconds (convenience)
    T2_ramsey: float | None = None    # seconds
    T2_star_us: float | None = None   # microseconds (convenience)
    T2_echo: float | None = None      # seconds
    T2_echo_us: float | None = None   # microseconds (convenience)
    qb_therm_clks: int | None = None
    ro_therm_clks: int | None = None
    st_therm_clks: int | None = None
    timestamp: str | None = None


# ---------------------------------------------------------------------------
# cQED Hamiltonian parameters (unified element record)
# ---------------------------------------------------------------------------

class CQEDParams(BaseModel):
    """Hamiltonian-level physical parameters for a cQED element alias."""

    resonator_freq: float | None = None
    kappa: float | None = None
    qubit_freq: float | None = None
    storage_freq: float | None = None
    ef_freq: float | None = None
    anharmonicity: float | None = None
    fock_freqs: list[float] | None = None
    chi: float | None = None
    chi2: float | None = None
    chi3: float | None = None
    kerr: float | None = None
    kerr2: float | None = None

    T1: float | None = None
    T1_us: float | None = None
    T2_ramsey: float | None = None
    T2_star_us: float | None = None
    T2_echo: float | None = None
    T2_echo_us: float | None = None
    qb_therm_clks: int | None = None
    ro_therm_clks: int | None = None
    st_therm_clks: int | None = None

    lo_freq: float | None = None
    if_freq: float | None = None
    rf_freq: float | None = None


# ---------------------------------------------------------------------------
# Pulse calibration record
# ---------------------------------------------------------------------------

class PulseCalibration(BaseModel):
    """Calibrated pulse parameters (e.g., from Rabi, DRAG calibration).

    Only reference primitives (e.g. ``ge_ref_r180``) should be stored here.
    Derived pulses (``ge_x180``, ``ge_y90``, etc.) are generated from the
    reference and must NOT appear in calibration.json.
    """

    pulse_name: str
    element: str | None = None
    transition: str | None = None   # "ge" or "ef"; None treated as "ge"
    amplitude: float | None = None
    length: int | None = None       # ns
    sigma: float | None = None
    drag_coeff: float | None = None
    detuning: float | None = None
    phase_offset: float | None = None   # radians
    timestamp: str | None = None


# ---------------------------------------------------------------------------
# Fit record
# ---------------------------------------------------------------------------

class FitRecord(BaseModel):
    """Single fit result with metadata, used for fit history."""

    experiment: str
    model_name: str
    params: dict[str, float]
    uncertainties: dict[str, float] | None = None
    reduced_chi2: float | None = None
    timestamp: str | None = None
    metadata: dict[str, Any] | None = None

    @classmethod
    def from_fit_result(cls, fit: Any, experiment: str) -> "FitRecord":
        """Create from an :class:`~qubox.experiments.result.FitResult`.

        Parameters
        ----------
        fit : FitResult
            The runtime fit result.
        experiment : str
            Name of the experiment that produced the fit.
        """
        import datetime

        return cls(
            experiment=experiment,
            model_name=getattr(fit, "model_name", "unknown"),
            params=dict(getattr(fit, "params", {})),
            uncertainties=dict(fit.uncertainties) if getattr(fit, "uncertainties", None) else None,
            reduced_chi2=None,
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            metadata={
                **(getattr(fit, "metadata", None) or {}),
                "success": getattr(fit, "success", None),
                "reason": getattr(fit, "reason", None),
                "r_squared": getattr(fit, "r_squared", None),
            },
        )


# ---------------------------------------------------------------------------
# Calibration context block
# ---------------------------------------------------------------------------

class CalibrationContext(BaseModel):
    """Sample and cooldown identity block embedded in calibration data."""

    sample_id: str = ""
    cooldown_id: str = ""
    wiring_rev: str = ""
    schema_version: str = "4.0.0"
    config_hash: str | None = None
    created: str | None = None


# ---------------------------------------------------------------------------
# Advanced calibration records
# ---------------------------------------------------------------------------

class PulseTrainResult(BaseModel):
    """Stores amp_err, phase_err, delta, zeta from pulse-train tomography."""

    element: str
    transition: str | None = None
    amp_err: float
    phase_err: float
    delta: float = 0.0
    zeta: float = 0.0
    rotation_pulse: str = "ge_x180"
    N_values: list[int] = []
    timestamp: str | None = None


class FockSQRCalibration(BaseModel):
    """Per-Fock SQR gate calibration."""

    fock_number: int
    model_type: str = ""
    params: dict[str, float] = {}
    fidelity: float | None = None
    timestamp: str | None = None


class MultiStateCalibration(BaseModel):
    """Multi-alpha 6-state affine calibration maps."""

    element: str
    alpha_values: list[float] = []
    affine_matrix: list[list[float]] = []
    offset_vector: list[float] = []
    state_labels: list[str] = []
    timestamp: str | None = None


# ---------------------------------------------------------------------------
# Root calibration data container
# ---------------------------------------------------------------------------

class CalibrationData(BaseModel):
    """Root container for all calibration data in a session.

    Version 5.1.0: all per-element dicts may be keyed by physical channel ID
    or legacy element name strings; an ``alias_index`` bridges the two.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    version: str = "5.1.0"
    context: CalibrationContext | None = None

    discrimination: dict[str, DiscriminationParams] = {}
    readout_quality: dict[str, ReadoutQuality] = {}
    cqed_params: dict[str, CQEDParams] = {}

    # Legacy stores retained for migration
    frequencies: dict[str, ElementFrequencies] = {}
    coherence: dict[str, CoherenceParams] = {}
    pulse_calibrations: dict[str, PulseCalibration] = {}

    fit_history: dict[str, list[FitRecord]] = {}

    pulse_train_results: dict[str, PulseTrainResult] = {}
    fock_sqr_calibrations: dict[str, list[FockSQRCalibration]] = {}
    multi_state_calibration: dict[str, MultiStateCalibration] = {}

    alias_index: dict[str, str] = {}

    created: str | None = None
    last_modified: str | None = None
