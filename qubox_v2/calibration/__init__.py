# qubox_v2/calibration/__init__.py
"""Calibration data storage and retrieval.

Provides typed, JSON-backed persistence for calibration parameters
(readout discrimination, element frequencies, fitted models, etc.)
with snapshot/history support.
"""
from .store import CalibrationStore
from .models import (
    CalibrationContext,
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
from .transitions import (
    Transition,
    DEFAULT_TRANSITION,
    TransitionLiteral,
    resolve_pulse_name,
    canonical_ref_pulse,
    canonical_derived_pulse,
    extract_transition,
    strip_transition_prefix,
    primitive_family,
    is_canonical,
    CANONICAL_REF_PULSES,
    CANONICAL_DERIVED_PULSES,
    ALL_CANONICAL,
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
try:
    from .mixer_calibration import (
        ManualMixerCalibrator,
        MixerCalibrationConfig,
        SAMeasurementHelper,
    )
except ImportError:  # pragma: no cover - optional lab dependency surface
    ManualMixerCalibrator = None
    MixerCalibrationConfig = None
    SAMeasurementHelper = None
from .contracts import Artifact, CalibrationResult, UpdateOp, Patch
from .orchestrator import CalibrationOrchestrator
from .patch_rules import (
    DragAlphaRule,
    DiscriminationRule,
    FrequencyRule,
    PiAmpRule,
    PulseTrainRule,
    ReadoutQualityRule,
    T1Rule,
    T2EchoRule,
    T2RamseyRule,
    WeightRegistrationRule,
    default_patch_rules,
)
try:
    from .pulse_train_tomo import (
        run_pulse_train_tomography,
        fit_pulse_train_model,
        fit_params_to_qubitrotation_knobs,
        pretty_knob_report,
        default_r0_dict,
        plot_meas_vs_fit,
    )
except ImportError:  # pragma: no cover - optional QM dependency surface
    run_pulse_train_tomography = None
    fit_pulse_train_model = None
    fit_params_to_qubitrotation_knobs = None
    pretty_knob_report = None
    default_r0_dict = None
    plot_meas_vs_fit = None

__all__ = [
    # Store
    "CalibrationStore",
    # Models
    "CalibrationContext",
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
    # Transition identity contracts
    "Transition",
    "DEFAULT_TRANSITION",
    "TransitionLiteral",
    "resolve_pulse_name",
    "canonical_ref_pulse",
    "canonical_derived_pulse",
    "extract_transition",
    "strip_transition_prefix",
    "primitive_family",
    "is_canonical",
    "CANONICAL_REF_PULSES",
    "CANONICAL_DERIVED_PULSES",
    "ALL_CANONICAL",
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
    # Orchestration contracts
    "Artifact",
    "CalibrationResult",
    "UpdateOp",
    "Patch",
    "CalibrationOrchestrator",
    "PiAmpRule",
    "PulseTrainRule",
    "T1Rule",
    "T2RamseyRule",
    "T2EchoRule",
    "FrequencyRule",
    "DragAlphaRule",
    "WeightRegistrationRule",
    "DiscriminationRule",
    "ReadoutQualityRule",
    "default_patch_rules",
    # Pulse-train tomography
    "run_pulse_train_tomography",
    "fit_pulse_train_model",
    "fit_params_to_qubitrotation_knobs",
    "pretty_knob_report",
    "default_r0_dict",
    "plot_meas_vs_fit",
]
