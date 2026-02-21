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


# ---------------------------------------------------------------------------
# Element frequency calibration
# ---------------------------------------------------------------------------
class ElementFrequencies(BaseModel):
    """Calibrated frequencies for a quantum element."""

    lo_freq: float                 # Hz
    if_freq: float                 # Hz
    qubit_freq: float | None = None
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
    T2_ramsey: float | None = None  # seconds
    T2_echo: float | None = None   # seconds
    timestamp: str | None = None


# ---------------------------------------------------------------------------
# Pulse calibration record
# ---------------------------------------------------------------------------
class PulseCalibration(BaseModel):
    """Calibrated pulse parameters (e.g., from Rabi, DRAG cal)."""

    pulse_name: str
    element: str
    amplitude: float | None = None
    length: int | None = None      # ns
    sigma: float | None = None
    drag_coeff: float | None = None
    detuning: float | None = None
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
# Top-level calibration data container
# ---------------------------------------------------------------------------
class CalibrationData(BaseModel):
    """Root container for all calibration data in a session."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    version: str = "3.0.0"

    # Keyed by element name
    discrimination: dict[str, DiscriminationParams] = {}
    readout_quality: dict[str, ReadoutQuality] = {}
    frequencies: dict[str, ElementFrequencies] = {}
    coherence: dict[str, CoherenceParams] = {}
    pulse_calibrations: dict[str, PulseCalibration] = {}

    # Fit history (keyed by experiment name)
    fit_history: dict[str, list[FitRecord]] = {}

    # Advanced calibration data
    pulse_train_results: dict[str, "PulseTrainResult"] = {}
    fock_sqr_calibrations: dict[str, list["FockSQRCalibration"]] = {}
    multi_state_calibration: dict[str, "MultiStateCalibration"] = {}

    # Timestamps
    created: str | None = None
    last_modified: str | None = None


# ---------------------------------------------------------------------------
# Pulse train tomography result
# ---------------------------------------------------------------------------
class PulseTrainResult(BaseModel):
    """Stores amp_err, phase_err, delta, zeta from pulse-train tomography."""

    element: str
    amp_err: float
    phase_err: float
    delta: float = 0.0
    zeta: float = 0.0
    rotation_pulse: str = "x180"
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
