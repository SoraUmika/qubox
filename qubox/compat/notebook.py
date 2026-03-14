"""Notebook-facing compatibility surface under the `qubox` namespace.

This module centralizes runtime surfaces that still live in `qubox_v2` so
notebooks can import only from `qubox`, `qubox.compat`, and `qubox_tools`.
"""

from __future__ import annotations

from importlib import import_module

_ATTR_MAP = {
    # Common experiment classes used by the notebooks
    "ResonatorSpectroscopy": ("qubox_v2.experiments", "ResonatorSpectroscopy"),
    "ResonatorPowerSpectroscopy": ("qubox_v2.experiments", "ResonatorPowerSpectroscopy"),
    "ResonatorSpectroscopyX180": ("qubox_v2.experiments", "ResonatorSpectroscopyX180"),
    "ReadoutTrace": ("qubox_v2.experiments", "ReadoutTrace"),
    "QubitSpectroscopy": ("qubox_v2.experiments", "QubitSpectroscopy"),
    "QubitSpectroscopyEF": ("qubox_v2.experiments", "QubitSpectroscopyEF"),
    "PowerRabi": ("qubox_v2.experiments", "PowerRabi"),
    "TemporalRabi": ("qubox_v2.experiments", "TemporalRabi"),
    "T1Relaxation": ("qubox_v2.experiments", "T1Relaxation"),
    "T2Ramsey": ("qubox_v2.experiments", "T2Ramsey"),
    "T2Echo": ("qubox_v2.experiments", "T2Echo"),
    "IQBlob": ("qubox_v2.experiments", "IQBlob"),
    "ReadoutGEDiscrimination": ("qubox_v2.experiments", "ReadoutGEDiscrimination"),
    "ReadoutWeightsOptimization": ("qubox_v2.experiments", "ReadoutWeightsOptimization"),
    "ReadoutButterflyMeasurement": ("qubox_v2.experiments", "ReadoutButterflyMeasurement"),
    "CalibrateReadoutFull": ("qubox_v2.experiments", "CalibrateReadoutFull"),
    "AllXY": ("qubox_v2.experiments", "AllXY"),
    "DRAGCalibration": ("qubox_v2.experiments", "DRAGCalibration"),
    "RandomizedBenchmarking": ("qubox_v2.experiments", "RandomizedBenchmarking"),
    "PulseTrainCalibration": ("qubox_v2.experiments", "PulseTrainCalibration"),
    "StorageSpectroscopy": ("qubox_v2.experiments", "StorageSpectroscopy"),
    "NumSplittingSpectroscopy": ("qubox_v2.experiments", "NumSplittingSpectroscopy"),
    "StorageChiRamsey": ("qubox_v2.experiments", "StorageChiRamsey"),
    "FockResolvedSpectroscopy": ("qubox_v2.experiments", "FockResolvedSpectroscopy"),
    "FockResolvedT1": ("qubox_v2.experiments", "FockResolvedT1"),
    "FockResolvedRamsey": ("qubox_v2.experiments", "FockResolvedRamsey"),
    "FockResolvedPowerRabi": ("qubox_v2.experiments", "FockResolvedPowerRabi"),
    "QubitStateTomography": ("qubox_v2.experiments", "QubitStateTomography"),
    "StorageWignerTomography": ("qubox_v2.experiments", "StorageWignerTomography"),
    "SNAPOptimization": ("qubox_v2.experiments", "SNAPOptimization"),
    "SPAFluxOptimization": ("qubox_v2.experiments", "SPAFluxOptimization"),
    "SPAPumpFrequencyOptimization": ("qubox_v2.experiments", "SPAPumpFrequencyOptimization"),
    # Calibration / devices / core helpers
    "ReadoutConfig": ("qubox_v2.experiments.calibration", "ReadoutConfig"),
    "CalibrationReadoutFull": ("qubox_v2.experiments.calibration.readout", "CalibrationReadoutFull"),
    "CalibrationOrchestrator": ("qubox_v2.calibration", "CalibrationOrchestrator"),
    "MixerCalibrationConfig": ("qubox_v2.calibration", "MixerCalibrationConfig"),
    "SAMeasurementHelper": ("qubox_v2.calibration", "SAMeasurementHelper"),
    "Patch": ("qubox_v2.calibration.contracts", "Patch"),
    "CalibrationStore": ("qubox_v2.calibration.store", "CalibrationStore"),
    "SampleRegistry": ("qubox_v2.devices", "SampleRegistry"),
    "SampleInfo": ("qubox_v2.devices", "SampleInfo"),
    "SessionState": ("qubox_v2.core.session_state", "SessionState"),
    "ArtifactManager": ("qubox_v2.core.artifact_manager", "ArtifactManager"),
    "cleanup_artifacts": ("qubox_v2.core.artifact_manager", "cleanup_artifacts"),
    "preflight_check": ("qubox_v2.core.preflight", "preflight_check"),
    "save_config_snapshot": ("qubox_v2.core.artifacts", "save_config_snapshot"),
    "validate_config_dir": ("qubox_v2.core.schemas", "validate_config_dir"),
    "ContextMismatchError": ("qubox_v2.core.errors", "ContextMismatchError"),
    "ExperimentContext": ("qubox_v2.core.experiment_context", "ExperimentContext"),
    # Programs / tools / verification / hardware helpers
    "measureMacro": ("qubox_v2.programs.macros.measure", "measureMacro"),
    "continuous_wave": ("qubox_v2.programs.builders.utility", "continuous_wave"),
    "QuboxSimulationConfig": ("qubox_v2.hardware.program_runner", "QuboxSimulationConfig"),
    "drag_gaussian_pulse_waveforms": ("qubox_v2.tools.waveforms", "drag_gaussian_pulse_waveforms"),
    "kaiser_pulse_waveforms": ("qubox_v2.tools.waveforms", "kaiser_pulse_waveforms"),
    "register_rotations_from_ref_iq": ("qubox_v2.tools.generators", "register_rotations_from_ref_iq"),
    "ensure_displacement_ops": ("qubox_v2.tools.generators", "ensure_displacement_ops"),
    "run_all_checks": ("qubox_v2.verification.waveform_regression", "run_all_checks"),
}

_MODULE_MAP = {
    "readout_mod": "qubox_v2.experiments.calibration.readout",
    "gates_mod": "qubox_v2.experiments.calibration.gates",
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
