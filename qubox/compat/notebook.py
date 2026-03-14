"""Notebook-facing compatibility surface under the `qubox` namespace.

This module centralizes runtime surfaces that still live in `qubox_v2_legacy`
so notebooks can import only from `qubox`, `qubox.compat`, and `qubox_tools`.
"""

from __future__ import annotations

from importlib import import_module

_ATTR_MAP = {
    # Common experiment classes used by the notebooks
    "ResonatorSpectroscopy": ("qubox_v2_legacy.experiments", "ResonatorSpectroscopy"),
    "ResonatorPowerSpectroscopy": ("qubox_v2_legacy.experiments", "ResonatorPowerSpectroscopy"),
    "ResonatorSpectroscopyX180": ("qubox_v2_legacy.experiments", "ResonatorSpectroscopyX180"),
    "ReadoutTrace": ("qubox_v2_legacy.experiments", "ReadoutTrace"),
    "QubitSpectroscopy": ("qubox_v2_legacy.experiments", "QubitSpectroscopy"),
    "QubitSpectroscopyEF": ("qubox_v2_legacy.experiments", "QubitSpectroscopyEF"),
    "PowerRabi": ("qubox_v2_legacy.experiments", "PowerRabi"),
    "TemporalRabi": ("qubox_v2_legacy.experiments", "TemporalRabi"),
    "T1Relaxation": ("qubox_v2_legacy.experiments", "T1Relaxation"),
    "T2Ramsey": ("qubox_v2_legacy.experiments", "T2Ramsey"),
    "T2Echo": ("qubox_v2_legacy.experiments", "T2Echo"),
    "IQBlob": ("qubox_v2_legacy.experiments", "IQBlob"),
    "ReadoutGEDiscrimination": ("qubox_v2_legacy.experiments", "ReadoutGEDiscrimination"),
    "ReadoutWeightsOptimization": ("qubox_v2_legacy.experiments", "ReadoutWeightsOptimization"),
    "ReadoutButterflyMeasurement": ("qubox_v2_legacy.experiments", "ReadoutButterflyMeasurement"),
    "CalibrateReadoutFull": ("qubox_v2_legacy.experiments", "CalibrateReadoutFull"),
    "AllXY": ("qubox_v2_legacy.experiments", "AllXY"),
    "DRAGCalibration": ("qubox_v2_legacy.experiments", "DRAGCalibration"),
    "RandomizedBenchmarking": ("qubox_v2_legacy.experiments", "RandomizedBenchmarking"),
    "PulseTrainCalibration": ("qubox_v2_legacy.experiments", "PulseTrainCalibration"),
    "StorageSpectroscopy": ("qubox_v2_legacy.experiments", "StorageSpectroscopy"),
    "NumSplittingSpectroscopy": ("qubox_v2_legacy.experiments", "NumSplittingSpectroscopy"),
    "StorageChiRamsey": ("qubox_v2_legacy.experiments", "StorageChiRamsey"),
    "FockResolvedSpectroscopy": ("qubox_v2_legacy.experiments", "FockResolvedSpectroscopy"),
    "FockResolvedT1": ("qubox_v2_legacy.experiments", "FockResolvedT1"),
    "FockResolvedRamsey": ("qubox_v2_legacy.experiments", "FockResolvedRamsey"),
    "FockResolvedPowerRabi": ("qubox_v2_legacy.experiments", "FockResolvedPowerRabi"),
    "QubitStateTomography": ("qubox_v2_legacy.experiments", "QubitStateTomography"),
    "StorageWignerTomography": ("qubox_v2_legacy.experiments", "StorageWignerTomography"),
    "SNAPOptimization": ("qubox_v2_legacy.experiments", "SNAPOptimization"),
    "SPAFluxOptimization": ("qubox_v2_legacy.experiments", "SPAFluxOptimization"),
    "SPAPumpFrequencyOptimization": ("qubox_v2_legacy.experiments", "SPAPumpFrequencyOptimization"),
    # Calibration / devices / core helpers
    "ReadoutConfig": ("qubox_v2_legacy.experiments.calibration", "ReadoutConfig"),
    "CalibrationReadoutFull": ("qubox_v2_legacy.experiments.calibration.readout", "CalibrationReadoutFull"),
    "CalibrationOrchestrator": ("qubox_v2_legacy.calibration", "CalibrationOrchestrator"),
    "MixerCalibrationConfig": ("qubox_v2_legacy.calibration", "MixerCalibrationConfig"),
    "SAMeasurementHelper": ("qubox_v2_legacy.calibration", "SAMeasurementHelper"),
    "Patch": ("qubox_v2_legacy.calibration.contracts", "Patch"),
    "CalibrationStore": ("qubox_v2_legacy.calibration.store", "CalibrationStore"),
    "SampleRegistry": ("qubox_v2_legacy.devices", "SampleRegistry"),
    "SampleInfo": ("qubox_v2_legacy.devices", "SampleInfo"),
    "SessionState": ("qubox_v2_legacy.core.session_state", "SessionState"),
    "ArtifactManager": ("qubox_v2_legacy.core.artifact_manager", "ArtifactManager"),
    "cleanup_artifacts": ("qubox_v2_legacy.core.artifact_manager", "cleanup_artifacts"),
    "preflight_check": ("qubox_v2_legacy.core.preflight", "preflight_check"),
    "save_config_snapshot": ("qubox_v2_legacy.core.artifacts", "save_config_snapshot"),
    "save_run_summary": ("qubox_v2_legacy.core.artifacts", "save_run_summary"),
    "validate_config_dir": ("qubox_v2_legacy.core.schemas", "validate_config_dir"),
    "ContextMismatchError": ("qubox_v2_legacy.core.errors", "ContextMismatchError"),
    "ExperimentContext": ("qubox_v2_legacy.core.experiment_context", "ExperimentContext"),
    "RunResult": ("qubox_v2_legacy.experiments.result", "RunResult"),
    "AnalysisResult": ("qubox_v2_legacy.experiments.result", "AnalysisResult"),
    "ProgramBuildResult": ("qubox_v2_legacy.experiments.result", "ProgramBuildResult"),
    # Programs / tools / verification / hardware helpers
    "measureMacro": ("qubox_v2_legacy.programs.macros.measure", "measureMacro"),
    "continuous_wave": ("qubox_v2_legacy.programs.builders.utility", "continuous_wave"),
    "QuboxSimulationConfig": ("qubox_v2_legacy.hardware.program_runner", "QuboxSimulationConfig"),
    "drag_gaussian_pulse_waveforms": ("qubox_v2_legacy.tools.waveforms", "drag_gaussian_pulse_waveforms"),
    "kaiser_pulse_waveforms": ("qubox_v2_legacy.tools.waveforms", "kaiser_pulse_waveforms"),
    "register_rotations_from_ref_iq": ("qubox_v2_legacy.tools.generators", "register_rotations_from_ref_iq"),
    "ensure_displacement_ops": ("qubox_v2_legacy.tools.generators", "ensure_displacement_ops"),
    "run_all_checks": ("qubox_v2_legacy.verification.waveform_regression", "run_all_checks"),
}

_MODULE_MAP = {
    "readout_mod": "qubox_v2_legacy.experiments.calibration.readout",
    "gates_mod": "qubox_v2_legacy.experiments.calibration.gates",
}

__all__ = sorted([*_ATTR_MAP.keys(), *_MODULE_MAP.keys()])


def __getattr__(name: str):
    if name in _ATTR_MAP:
        module_name, attr_name = _ATTR_MAP[name]
        value = getattr(import_module(module_name), attr_name)
        globals()[name] = value
        return value
    if name in _MODULE_MAP:
        module = import_module(_MODULE_MAP[name])
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
