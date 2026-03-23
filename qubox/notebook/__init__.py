"""Notebook-facing import surface for the ``qubox`` package.

``qubox.notebook`` centralises all runtime symbols needed by experiment
notebooks so they can import from a single, stable location.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Waveform generators (qubox.tools)
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
# Calibration stack (qubox.calibration)
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
    MixerCalibrationConfig,
    SAMeasurementHelper,
)

# ---------------------------------------------------------------------------
# Device registry (qubox.devices)
# ---------------------------------------------------------------------------
from ..devices import SampleRegistry, SampleInfo

# ---------------------------------------------------------------------------
# Artifacts (qubox.artifacts)
# ---------------------------------------------------------------------------
from ..artifacts import (
    ArtifactManager,
    save_config_snapshot,
    save_run_summary,
    cleanup_artifacts,
)

# ---------------------------------------------------------------------------
# Preflight (qubox.preflight)
# ---------------------------------------------------------------------------
from ..preflight import preflight_check

# ---------------------------------------------------------------------------
# Schemas (qubox.schemas)
# ---------------------------------------------------------------------------
from ..schemas import validate_config_dir, ValidationResult

# ---------------------------------------------------------------------------
# Hardware definition (qubox.core)
# ---------------------------------------------------------------------------
from ..core.hardware_definition import HardwareDefinition

# ---------------------------------------------------------------------------
# Notebook runtime — session bootstrap and sharing
# ---------------------------------------------------------------------------
from .runtime import (
    NotebookSessionBootstrap,
    close_shared_session,
    get_notebook_session_bootstrap_path,
    get_shared_session,
    load_notebook_session_bootstrap,
    open_shared_session,
    register_shared_session,
    require_shared_session,
    resolve_active_mixer_targets,
    restore_shared_session,
    save_notebook_session_bootstrap,
)

# ---------------------------------------------------------------------------
# Notebook workflow — stage management, checkpoints, fit helpers
# ---------------------------------------------------------------------------
from .workflow import (
    NotebookStageContext,
    NotebookWorkflowConfig,
    build_notebook_workflow_config,
    ensure_primitive_rotations,
    fit_center_inside_window,
    fit_quality_gate,
    get_notebook_stage_checkpoint_path,
    load_legacy_reference,
    load_stage_checkpoint,
    open_notebook_stage,
    preview_or_apply_patch_ops,
    save_stage_checkpoint,
)

# ---------------------------------------------------------------------------
# Core types, errors, context
# ---------------------------------------------------------------------------
from ..core.errors import ContextMismatchError
from ..session.context import ExperimentContext, compute_wiring_rev
from ..session.state import SessionState

# ---------------------------------------------------------------------------
# Experiment classes (qubox.experiments)
# ---------------------------------------------------------------------------
from ..experiments import (
    # Spectroscopy
    ResonatorSpectroscopy,
    ResonatorPowerSpectroscopy,
    ResonatorSpectroscopyX180,
    ReadoutTrace,
    QubitSpectroscopy,
    QubitSpectroscopyEF,
    # Time-domain
    PowerRabi,
    TemporalRabi,
    T1Relaxation,
    T2Ramsey,
    T2Echo,
    # Readout calibration
    IQBlob,
    ReadoutGEDiscrimination,
    ReadoutWeightsOptimization,
    ReadoutButterflyMeasurement,
    CalibrateReadoutFull,
    # Gate calibration
    AllXY,
    DRAGCalibration,
    RandomizedBenchmarking,
    PulseTrainCalibration,
    # Storage / cavity
    StorageSpectroscopy,
    NumSplittingSpectroscopy,
    StorageChiRamsey,
    FockResolvedSpectroscopy,
    FockResolvedT1,
    FockResolvedRamsey,
    FockResolvedPowerRabi,
    # Tomography
    QubitStateTomography,
    StorageWignerTomography,
    SNAPOptimization,
    # SPA
    SPAFluxOptimization,
    SPAPumpFrequencyOptimization,
)
from ..experiments.calibration import ReadoutConfig
from ..experiments.calibration.readout import CalibrateReadoutFull as CalibrationReadoutFull  # noqa: F811
from ..experiments.result import RunResult, AnalysisResult, ProgramBuildResult

# ---------------------------------------------------------------------------
# Hardware / program utilities
# ---------------------------------------------------------------------------
from ..programs.macros.measure import measureMacro
from ..programs.builders.utility import continuous_wave
from ..hardware.program_runner import QuboxSimulationConfig

# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------
from ..verification.waveform_regression import run_all_checks

# ---------------------------------------------------------------------------
# Module aliases
# ---------------------------------------------------------------------------
from ..experiments.calibration import readout as readout_mod  # noqa: F811
from ..experiments.calibration import gates as gates_mod

__all__ = [
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
    "MixerCalibrationConfig",
    "SAMeasurementHelper",
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
    # hardware definition
    "HardwareDefinition",
    # notebook runtime
    "NotebookSessionBootstrap",
    "close_shared_session",
    "get_notebook_session_bootstrap_path",
    "get_shared_session",
    "load_notebook_session_bootstrap",
    "open_shared_session",
    "register_shared_session",
    "require_shared_session",
    "resolve_active_mixer_targets",
    "restore_shared_session",
    "save_notebook_session_bootstrap",
    # notebook workflow
    "NotebookStageContext",
    "NotebookWorkflowConfig",
    "build_notebook_workflow_config",
    "ensure_primitive_rotations",
    "fit_center_inside_window",
    "fit_quality_gate",
    "get_notebook_stage_checkpoint_path",
    "load_legacy_reference",
    "load_stage_checkpoint",
    "open_notebook_stage",
    "preview_or_apply_patch_ops",
    "save_stage_checkpoint",
    # core
    "ContextMismatchError",
    "ExperimentContext",
    "compute_wiring_rev",
    "SessionState",
    # experiments
    "ResonatorSpectroscopy",
    "ResonatorPowerSpectroscopy",
    "ResonatorSpectroscopyX180",
    "ReadoutTrace",
    "QubitSpectroscopy",
    "QubitSpectroscopyEF",
    "PowerRabi",
    "TemporalRabi",
    "T1Relaxation",
    "T2Ramsey",
    "T2Echo",
    "IQBlob",
    "ReadoutGEDiscrimination",
    "ReadoutWeightsOptimization",
    "ReadoutButterflyMeasurement",
    "CalibrateReadoutFull",
    "AllXY",
    "DRAGCalibration",
    "RandomizedBenchmarking",
    "PulseTrainCalibration",
    "StorageSpectroscopy",
    "NumSplittingSpectroscopy",
    "StorageChiRamsey",
    "FockResolvedSpectroscopy",
    "FockResolvedT1",
    "FockResolvedRamsey",
    "FockResolvedPowerRabi",
    "QubitStateTomography",
    "StorageWignerTomography",
    "SNAPOptimization",
    "SPAFluxOptimization",
    "SPAPumpFrequencyOptimization",
    "ReadoutConfig",
    "CalibrationReadoutFull",
    "RunResult",
    "AnalysisResult",
    "ProgramBuildResult",
    # hardware / program utilities
    "measureMacro",
    "continuous_wave",
    "QuboxSimulationConfig",
    "run_all_checks",
    # module aliases
    "readout_mod",
    "gates_mod",
]
