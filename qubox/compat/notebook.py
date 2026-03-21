"""Notebook-facing compatibility surface under the ``qubox`` namespace.

This module centralises runtime symbols needed by notebooks so they can import
only from ``qubox``, ``qubox.compat``, and ``qubox_tools``.

Migration status
----------------
MIGRATED (no ``qubox_v2_legacy`` dependency):
    drag_gaussian_pulse_waveforms     → qubox.tools.waveforms
    kaiser_pulse_waveforms            → qubox.tools.waveforms
    register_rotations_from_ref_iq    → qubox.tools.generators
    ensure_displacement_ops           → qubox.tools.generators
    CalibrationOrchestrator           → qubox.calibration
    CalibrationStore                  → qubox.calibration
    Patch, UpdateOp, CalibrationResult, Artifact → qubox.calibration
    DiscriminationParams, ReadoutQuality, CQEDParams, PulseCalibration, FitRecord
                                      → qubox.calibration
    CalibrationData, CalibrationContext → qubox.calibration
    SampleRegistry, SampleInfo        → qubox.devices
    ArtifactManager, cleanup_artifacts → qubox.artifacts
    save_config_snapshot, save_run_summary → qubox.artifacts
    preflight_check                   → qubox.preflight
    validate_config_dir               → qubox.schemas
    ContextMismatchError              → qubox.core.errors
    ExperimentContext                 → qubox.session.context
    SessionState                      → qubox.session.state

MIGRATION BLOCKERS (still proxy to ``qubox_v2_legacy``):
    All experiment classes (QubitSpectroscopy, StorageWignerTomography, …)
    and low-level hardware utilities (measureMacro, continuous_wave,
    QuboxSimulationConfig, run_all_checks, readout_mod, gates_mod)
    remain in ``qubox_v2_legacy`` pending a full QUA-program-layer rewrite.
    Each entry in ``_LEGACY_ATTR_MAP`` below represents one remaining blocker.

    To complete the migration of an item:
      1. Implement or move the class/function into the appropriate
         ``qubox.*`` sub-package.
      2. Replace its entry in ``_LEGACY_ATTR_MAP`` with a direct import
         from that sub-package.
"""

from __future__ import annotations

from importlib import import_module

# ---------------------------------------------------------------------------
# MIGRATED: waveform generators now live in qubox.tools
# ---------------------------------------------------------------------------
from ..tools.waveforms import (
    drag_gaussian_pulse_waveforms,
    kaiser_pulse_waveforms,
)
from ..tools.generators import (
    register_rotations_from_ref_iq,
    ensure_displacement_ops,
)

# ---------------------------------------------------------------------------
# MIGRATED: calibration stack now lives in qubox.calibration
# ---------------------------------------------------------------------------
from ..calibration import (
    CalibrationOrchestrator,
    CalibrationStore,
    Patch,
    UpdateOp,
    CalibrationResult,
    Artifact,
    DiscriminationParams,
    ReadoutQuality,
    CQEDParams,
    CoherenceParams,
    ElementFrequencies,
    PulseCalibration,
    FitRecord,
    PulseTrainResult,
    FockSQRCalibration,
    MultiStateCalibration,
    CalibrationData,
    CalibrationContext,
    Transition,
    resolve_pulse_name,
    canonical_ref_pulse,
    canonical_derived_pulse,
    extract_transition,
    strip_transition_prefix,
    primitive_family,
    list_snapshots as list_calibration_snapshots,
    load_snapshot as load_calibration_snapshot,
    diff_snapshots as diff_calibration_snapshots,
    default_patch_rules,
)

# ---------------------------------------------------------------------------
# MIGRATED: device registry now lives in qubox.devices
# ---------------------------------------------------------------------------
from ..devices import SampleRegistry, SampleInfo

# ---------------------------------------------------------------------------
# MIGRATED: artifacts now live in qubox.artifacts
# ---------------------------------------------------------------------------
from ..artifacts import (
    ArtifactManager,
    save_config_snapshot,
    save_run_summary,
    cleanup_artifacts,
)

# ---------------------------------------------------------------------------
# MIGRATED: preflight check now lives in qubox.preflight
# ---------------------------------------------------------------------------
from ..preflight import preflight_check

# ---------------------------------------------------------------------------
# MIGRATED: schema validation now lives in qubox.schemas
# ---------------------------------------------------------------------------
from ..schemas import validate_config_dir, ValidationResult

# ---------------------------------------------------------------------------
# MIGRATED: core types, errors, context
# ---------------------------------------------------------------------------
from ..core.errors import ContextMismatchError
from ..session.context import ExperimentContext, compute_wiring_rev
from ..session.state import SessionState

# ---------------------------------------------------------------------------
# MIGRATION BLOCKERS: lazy proxies to qubox_v2_legacy
# ---------------------------------------------------------------------------
# Each key is the public name exposed to notebooks.
# Format: "PublicName": ("qubox_v2_legacy.module.path", "ClassName")
#
# TODO: as each item is migrated into qubox, replace its entry here with a
#       direct import and remove it from this map.

# ---------------------------------------------------------------------------
# MIGRATION BLOCKERS: lazy proxies to qubox_v2_legacy
# ---------------------------------------------------------------------------
# Only symbols that cannot yet be migrated (QUA-program-coupled experiments
# and hardware utilities) remain here.  Everything else is imported directly
# above.

_LEGACY_ATTR_MAP: dict[str, tuple[str, str]] = {
    # ── Spectroscopy experiments ──────────────────────────────────────────
    "ResonatorSpectroscopy":       ("qubox.legacy.experiments", "ResonatorSpectroscopy"),
    "ResonatorPowerSpectroscopy":  ("qubox.legacy.experiments", "ResonatorPowerSpectroscopy"),
    "ResonatorSpectroscopyX180":   ("qubox.legacy.experiments", "ResonatorSpectroscopyX180"),
    "ReadoutTrace":                ("qubox.legacy.experiments", "ReadoutTrace"),
    "QubitSpectroscopy":           ("qubox.legacy.experiments", "QubitSpectroscopy"),
    "QubitSpectroscopyEF":         ("qubox.legacy.experiments", "QubitSpectroscopyEF"),
    # ── Time-domain experiments ───────────────────────────────────────────
    "PowerRabi":                   ("qubox.legacy.experiments", "PowerRabi"),
    "TemporalRabi":                ("qubox.legacy.experiments", "TemporalRabi"),
    "T1Relaxation":                ("qubox.legacy.experiments", "T1Relaxation"),
    "T2Ramsey":                    ("qubox.legacy.experiments", "T2Ramsey"),
    "T2Echo":                      ("qubox.legacy.experiments", "T2Echo"),
    # ── Readout calibration experiments ──────────────────────────────────
    "IQBlob":                      ("qubox.legacy.experiments", "IQBlob"),
    "ReadoutGEDiscrimination":     ("qubox.legacy.experiments", "ReadoutGEDiscrimination"),
    "ReadoutWeightsOptimization":  ("qubox.legacy.experiments", "ReadoutWeightsOptimization"),
    "ReadoutButterflyMeasurement": ("qubox.legacy.experiments", "ReadoutButterflyMeasurement"),
    "CalibrateReadoutFull":        ("qubox.legacy.experiments", "CalibrateReadoutFull"),
    # ── Gate calibration experiments ──────────────────────────────────────
    "AllXY":                       ("qubox.legacy.experiments", "AllXY"),
    "DRAGCalibration":             ("qubox.legacy.experiments", "DRAGCalibration"),
    "RandomizedBenchmarking":      ("qubox.legacy.experiments", "RandomizedBenchmarking"),
    "PulseTrainCalibration":       ("qubox.legacy.experiments", "PulseTrainCalibration"),
    # ── Storage / cavity experiments ──────────────────────────────────────
    "StorageSpectroscopy":         ("qubox.legacy.experiments", "StorageSpectroscopy"),
    "NumSplittingSpectroscopy":    ("qubox.legacy.experiments", "NumSplittingSpectroscopy"),
    "StorageChiRamsey":            ("qubox.legacy.experiments", "StorageChiRamsey"),
    "FockResolvedSpectroscopy":    ("qubox.legacy.experiments", "FockResolvedSpectroscopy"),
    "FockResolvedT1":              ("qubox.legacy.experiments", "FockResolvedT1"),
    "FockResolvedRamsey":          ("qubox.legacy.experiments", "FockResolvedRamsey"),
    "FockResolvedPowerRabi":       ("qubox.legacy.experiments", "FockResolvedPowerRabi"),
    # ── Tomography experiments ─────────────────────────────────────────────
    "QubitStateTomography":        ("qubox.legacy.experiments", "QubitStateTomography"),
    "StorageWignerTomography":     ("qubox.legacy.experiments", "StorageWignerTomography"),
    "SNAPOptimization":            ("qubox.legacy.experiments", "SNAPOptimization"),
    # ── SPA experiments ───────────────────────────────────────────────────
    "SPAFluxOptimization":         ("qubox.legacy.experiments", "SPAFluxOptimization"),
    "SPAPumpFrequencyOptimization":("qubox.legacy.experiments", "SPAPumpFrequencyOptimization"),
    # ── Legacy-only experiment infrastructure ─────────────────────────────
    "ReadoutConfig":               ("qubox.legacy.experiments.calibration", "ReadoutConfig"),
    "CalibrationReadoutFull":      ("qubox.legacy.experiments.calibration.readout", "CalibrationReadoutFull"),
    "MixerCalibrationConfig":      ("qubox.legacy.calibration", "MixerCalibrationConfig"),
    "SAMeasurementHelper":         ("qubox.legacy.calibration", "SAMeasurementHelper"),
    # ── Experiment result types ────────────────────────────────────────────
    "RunResult":                   ("qubox.legacy.experiments.result", "RunResult"),
    "AnalysisResult":              ("qubox.legacy.experiments.result", "AnalysisResult"),
    "ProgramBuildResult":          ("qubox.legacy.experiments.result", "ProgramBuildResult"),
    # ── Hardware / program utilities ──────────────────────────────────────
    "measureMacro":                ("qubox.legacy.programs.macros.measure", "measureMacro"),
    "continuous_wave":             ("qubox.legacy.programs.builders.utility", "continuous_wave"),
    "QuboxSimulationConfig":       ("qubox.legacy.hardware.program_runner", "QuboxSimulationConfig"),
    # ── Verification ──────────────────────────────────────────────────────
    "run_all_checks":              ("qubox.legacy.verification.waveform_regression", "run_all_checks"),
}

_LEGACY_MODULE_MAP: dict[str, str] = {
    "readout_mod": "qubox.legacy.experiments.calibration.readout",
    "gates_mod":   "qubox.legacy.experiments.calibration.gates",
}

# Public names directly exported from this module (no lazy loading needed)
_MIGRATED_NAMES = {
    # waveform utilities
    "drag_gaussian_pulse_waveforms",
    "kaiser_pulse_waveforms",
    "register_rotations_from_ref_iq",
    "ensure_displacement_ops",
    # calibration stack
    "CalibrationOrchestrator",
    "CalibrationStore",
    "Patch",
    "UpdateOp",
    "CalibrationResult",
    "Artifact",
    "DiscriminationParams",
    "ReadoutQuality",
    "CQEDParams",
    "CoherenceParams",
    "ElementFrequencies",
    "PulseCalibration",
    "FitRecord",
    "PulseTrainResult",
    "FockSQRCalibration",
    "MultiStateCalibration",
    "CalibrationData",
    "CalibrationContext",
    "Transition",
    "resolve_pulse_name",
    "canonical_ref_pulse",
    "canonical_derived_pulse",
    "extract_transition",
    "strip_transition_prefix",
    "primitive_family",
    "list_calibration_snapshots",
    "load_calibration_snapshot",
    "diff_calibration_snapshots",
    "default_patch_rules",
    # devices
    "SampleRegistry",
    "SampleInfo",
    # artifacts
    "ArtifactManager",
    "save_config_snapshot",
    "save_run_summary",
    "cleanup_artifacts",
    # preflight
    "preflight_check",
    # schemas
    "validate_config_dir",
    "ValidationResult",
    # core
    "ContextMismatchError",
    "ExperimentContext",
    "compute_wiring_rev",
    "SessionState",
}

__all__ = sorted([
    *_MIGRATED_NAMES,
    *_LEGACY_ATTR_MAP.keys(),
    *_LEGACY_MODULE_MAP.keys(),
])


def __getattr__(name: str):
    if name in _LEGACY_ATTR_MAP:
        module_name, attr_name = _LEGACY_ATTR_MAP[name]
        value = getattr(import_module(module_name), attr_name)
        globals()[name] = value
        return value
    if name in _LEGACY_MODULE_MAP:
        module = import_module(_LEGACY_MODULE_MAP[name])
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
