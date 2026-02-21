# qubox_v2/calibration/__init__.py
"""Calibration data storage and retrieval.

Provides typed, JSON-backed persistence for calibration parameters
(readout discrimination, element frequencies, fitted models, etc.)
with snapshot/history support.
"""
from .store import CalibrationStore
from .models import (
    CalibrationData,
    CoherenceParams,
    DiscriminationParams,
    ElementFrequencies,
    FitRecord,
    FockSQRCalibration,
    MultiStateCalibration,
    PulseCalibration,
    PulseTrainResult,
    ReadoutQuality,
)
from .algorithms import (
    apply_affine_correction,
    compute_corrected_knobs,
    fit_chi_ramsey,
    fit_fock_sqr,
    fit_multi_alpha_affine,
    fit_number_splitting,
    fit_pulse_train,
    optimize_fock_sqr_iterative,
    optimize_fock_sqr_spsa,
)
from .mixer_calibration import (
    ManualMixerCalibrator,
    MixerCalibrationConfig,
    SAMeasurementHelper,
)

__all__ = [
    # Store
    "CalibrationStore",
    # Models
    "CalibrationData",
    "CoherenceParams",
    "DiscriminationParams",
    "ElementFrequencies",
    "FitRecord",
    "FockSQRCalibration",
    "MultiStateCalibration",
    "PulseCalibration",
    "PulseTrainResult",
    "ReadoutQuality",
    # Algorithms
    "apply_affine_correction",
    "compute_corrected_knobs",
    "fit_chi_ramsey",
    "fit_fock_sqr",
    "fit_multi_alpha_affine",
    "fit_number_splitting",
    "fit_pulse_train",
    "optimize_fock_sqr_iterative",
    "optimize_fock_sqr_spsa",
    # Mixer calibration
    "ManualMixerCalibrator",
    "MixerCalibrationConfig",
    "SAMeasurementHelper",
]
