"""Notebook-facing import surface for the ``qubox`` package.

``qubox.notebook`` exports the symbols most commonly needed in experiment
notebooks.  Infrastructure and calibration internals live in
``qubox.notebook.advanced`` — import from there when needed.

Workflow primitives (stage checkpoints, fit gates, patch preview) are also
available from :mod:`qubox.workflow` for scripts and CI.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Session & workflow (what every notebook needs)
# ---------------------------------------------------------------------------
from .runtime import (
    NotebookSessionBootstrap,
    close_shared_session,
    get_shared_session,
    open_shared_session,
    require_shared_session,
    resolve_active_mixer_targets,
    restore_shared_session,
)
from .workflow import (
    NotebookStageContext,
    NotebookWorkflowConfig,
    build_notebook_workflow_config,
    ensure_primitive_rotations,
    fit_center_inside_window,
    fit_quality_gate,
    load_legacy_reference,
    load_stage_checkpoint,
    open_notebook_stage,
    preview_or_apply_patch_ops,
    save_stage_checkpoint,
    get_notebook_stage_checkpoint_path,
)

# ---------------------------------------------------------------------------
# Experiment classes (the primary user surface)
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
from ..experiments.result import RunResult, AnalysisResult, ProgramBuildResult

# ---------------------------------------------------------------------------
# Waveform generators (commonly used for pulse definition)
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
# Calibration essentials (user-tier)
# ---------------------------------------------------------------------------
from ..calibration import (
    CalibrationOrchestrator,
    Patch,
    UpdateOp,
    MixerCalibrationConfig,
    SAMeasurementHelper,
)

# ---------------------------------------------------------------------------
# Hardware definition
# ---------------------------------------------------------------------------
from ..core.hardware_definition import HardwareDefinition

# ---------------------------------------------------------------------------
# Hardware / program utilities
# ---------------------------------------------------------------------------
from ..programs.macros.measure import measureMacro
from ..programs.builders.utility import continuous_wave
from ..hardware.program_runner import QuboxSimulationConfig

__all__ = [
    # session & workflow
    "NotebookSessionBootstrap",
    "close_shared_session",
    "get_shared_session",
    "open_shared_session",
    "require_shared_session",
    "resolve_active_mixer_targets",
    "restore_shared_session",
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
    "RunResult",
    "AnalysisResult",
    "ProgramBuildResult",
    # waveform
    "drag_gaussian_pulse_waveforms",
    "kaiser_pulse_waveforms",
    "register_rotations_from_ref_iq",
    "ensure_displacement_ops",
    # calibration essentials
    "CalibrationOrchestrator",
    "Patch",
    "UpdateOp",
    "MixerCalibrationConfig",
    "SAMeasurementHelper",
    # hardware
    "HardwareDefinition",
    "measureMacro",
    "continuous_wave",
    "QuboxSimulationConfig",
]
