# qubox_v2/calibration/models.py
"""Pydantic v2 models for calibration data entries.

Every calibration artifact is a typed, serializable model that can
be round-tripped through JSON without loss of information.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import numpy as np
from pydantic import BaseModel, ConfigDict, field_serializer, field_validator


# ---------------------------------------------------------------------------
# Custom serializers for numpy
# ---------------------------------------------------------------------------
def _ndarray_to_list(v: Any) -> Any:
    if isinstance(v, np.ndarray):
        return v.tolist()
    return v


# ---------------------------------------------------------------------------
# Readout discrimination parameters
# ---------------------------------------------------------------------------
class DiscriminationParams(BaseModel):
    """Parameters for single-shot readout state discrimination."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    threshold: float
    angle: float
    mu_g: list[float]              # [I, Q] centroid for |g>
    mu_e: list[float]              # [I, Q] centroid for |e>
    sigma_g: float
    sigma_e: float
    fidelity: float | None = None
    confusion_matrix: list[list[float]] | None = None

    # Readout calibration metadata — for reproducibility
    n_shots: int | None = None
    integration_time_ns: int | None = None
    demod_weights: list[str] | None = None
    state_prep_ops: list[str] | None = None


class ReadoutQuality(BaseModel):
    """Readout quality metrics from butterfly measurement."""

    alpha: float | None = None
    beta: float | None = None
    F: float | None = None         # assignment fidelity
    Q: float | None = None         # QND-ness
    V: float | None = None         # visibility
    t01: float | None = None       # 0->1 transition probability
    t10: float | None = None       # 1->0 transition probability
    confusion_matrix: list[list[float]] | None = None
    affine_n: dict[str, list[float]] | None = None

    # Readout calibration metadata — for reproducibility
    n_shots: int | None = None
    integration_time_ns: int | None = None
    demod_weights: list[str] | None = None
    state_prep_ops: list[str] | None = None


# ---------------------------------------------------------------------------
# Element frequency calibration
# ---------------------------------------------------------------------------
class ElementFrequencies(BaseModel):
    """Calibrated frequencies for a quantum element.

    Frequency convention
    --------------------
    An element may store its drive frequency in one of two ways:

    1. **LO + IF pair** — ``rf_freq = lo_freq + if_freq``.
       Standard for OPX elements driven through an Octave up-converter.
       ``if_freq`` may be negative (lower sideband).

    2. **Explicit rf_freq** — absolute RF frequency in Hz.
       Used when the element is driven directly or when only the
       calibrated transition frequency is known (e.g. ``qubit_freq``).

    Both representations may coexist.  When present, the relationship
    ``rf_freq == lo_freq + if_freq`` must hold.

    Only fields with actual calibrated values should be populated.
    Unset fields default to ``None`` and are omitted from the persisted
    JSON to avoid misleading placeholders.
    """

    lo_freq: float | None = None   # Hz — local oscillator frequency
    if_freq: float | None = None   # Hz — intermediate frequency (may be negative)
    rf_freq: float | None = None   # Hz — absolute RF drive frequency
    resonator_freq: float | None = None  # Hz — calibrated resonator/readout frequency
    qubit_freq: float | None = None   # Hz — GE transition frequency (legacy / canonical GE slot)
    storage_freq: float | None = None    # Hz — storage cavity frequency
    ef_freq: float | None = None      # Hz — EF transition frequency (canonical EF slot)
    anharmonicity: float | None = None
    fock_freqs: list[float] | None = None
    chi: float | None = None       # dispersive shift (Hz)
    chi2: float | None = None
    chi3: float | None = None
    kappa: float | None = None     # linewidth (Hz)
    kerr: float | None = None      # self-Kerr (Hz)
    kerr2: float | None = None


# ---------------------------------------------------------------------------
# Coherence measurements
# ---------------------------------------------------------------------------
class CoherenceParams(BaseModel):
    """Coherence time calibration results."""

    T1: float | None = None        # seconds
    T1_us: float | None = None     # microseconds (convenience, from T1 experiment)
    T2_ramsey: float | None = None  # seconds
    T2_star_us: float | None = None  # microseconds (convenience, from Ramsey)
    T2_echo: float | None = None   # seconds
    T2_echo_us: float | None = None  # microseconds (convenience, from echo)
    qb_therm_clks: int | None = None  # qubit thermalization wait (clock cycles)
    ro_therm_clks: int | None = None  # readout cooldown wait (clock cycles)
    st_therm_clks: int | None = None  # storage cooldown wait (clock cycles)
    timestamp: str | None = None


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
    """Calibrated pulse parameters (e.g., from Rabi, DRAG cal).

    Only true calibration primitives (e.g. ``ge_ref_r180``, ``ge_sel_ref_r180``)
    should be stored here.  Derived pulses like ``ge_x180``, ``ge_y180``, etc.
    are generated programmatically from the reference pulse and must NOT
    appear in ``calibration.json``.

    The ``transition`` field records which qubit transition this pulse
    belongs to (``"ge"`` or ``"ef"``).  Legacy records without a
    transition field are assumed to be ``"ge"``.
    """

    pulse_name: str
    element: str | None = None
    transition: str | None = None  # "ge" or "ef"; None treated as "ge"
    amplitude: float | None = None
    length: int | None = None      # ns
    sigma: float | None = None
    drag_coeff: float | None = None
    detuning: float | None = None
    phase_offset: float | None = None  # radians (from pulse-train tomography)
    timestamp: str | None = None


# ---------------------------------------------------------------------------
# Generic fit result record
# ---------------------------------------------------------------------------
class FitRecord(BaseModel):
    """Stores a fit result with metadata."""

    experiment: str
    model_name: str
    params: dict[str, float]
    uncertainties: dict[str, float] | None = None
    reduced_chi2: float | None = None
    timestamp: str | None = None
    metadata: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Calibration context (sample + cooldown identity)
# ---------------------------------------------------------------------------
class CalibrationContext(BaseModel):
    """Sample and cooldown context embedded in calibration data.

    When present, this block binds a calibration file to a specific
    sample, cooldown cycle, and hardware wiring revision so that
    stale calibrations cannot be silently reused across setups.
    """

    sample_id: str = ""
    cooldown_id: str = ""
    wiring_rev: str = ""
    schema_version: str = "4.0.0"
    config_hash: str | None = None
    created: str | None = None


# ---------------------------------------------------------------------------
# Top-level calibration data container
# ---------------------------------------------------------------------------
class CalibrationData(BaseModel):
    """Root container for all calibration data in a session.

    As of v5.0.0, all per-element dicts are keyed by **physical channel ID**
    (``ChannelRef.canonical_id``, e.g. ``"con1:analog_in:1"``) rather than
    element name strings.  An ``alias_index`` maps human-friendly names
    to physical IDs for backward compatibility.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    version: str = "5.1.0"
    context: CalibrationContext | None = None

    # PRIMARY KEY: physical channel ID (ChannelRef.canonical_id) or legacy element name
    discrimination: dict[str, DiscriminationParams] = {}
    readout_quality: dict[str, ReadoutQuality] = {}
    cqed_params: dict[str, CQEDParams] = {}

    # Legacy stores retained for backward compatibility and migration.
    frequencies: dict[str, ElementFrequencies] = {}
    coherence: dict[str, CoherenceParams] = {}
    pulse_calibrations: dict[str, PulseCalibration] = {}

    # Fit history (keyed by experiment name)
    fit_history: dict[str, list[FitRecord]] = {}

    # Advanced calibration data
    pulse_train_results: dict[str, "PulseTrainResult"] = {}
    fock_sqr_calibrations: dict[str, list["FockSQRCalibration"]] = {}
    multi_state_calibration: dict[str, "MultiStateCalibration"] = {}

    # ALIAS INDEX: maps human-friendly names to physical IDs
    # e.g. {"resonator": "oct1:RF_in:1", "qubit": "oct1:RF_out:3"}
    alias_index: dict[str, str] = {}

    # Timestamps
    created: str | None = None
    last_modified: str | None = None


# ---------------------------------------------------------------------------
# Pulse train tomography result
# ---------------------------------------------------------------------------
class PulseTrainResult(BaseModel):
    """Stores amp_err, phase_err, delta, zeta from pulse-train tomography."""

    element: str
    transition: str | None = None  # "ge" or "ef"; None treated as "ge"
    amp_err: float
    phase_err: float
    delta: float = 0.0
    zeta: float = 0.0
    rotation_pulse: str = "ge_x180"
    N_values: list[int] = []
    timestamp: str | None = None


# ---------------------------------------------------------------------------
# Fock-resolved SQR gate calibration
# ---------------------------------------------------------------------------
class FockSQRCalibration(BaseModel):
    """Per-Fock SQR gate calibration."""

    fock_number: int
    model_type: str = ""
    params: dict[str, float] = {}
    fidelity: float | None = None
    timestamp: str | None = None


# ---------------------------------------------------------------------------
# Multi-state affine calibration
# ---------------------------------------------------------------------------
class MultiStateCalibration(BaseModel):
    """Multi-alpha 6-state affine calibration maps."""

    element: str
    alpha_values: list[float] = []
    affine_matrix: list[list[float]] = []
    offset_vector: list[float] = []
    state_labels: list[str] = []
    timestamp: str | None = None
