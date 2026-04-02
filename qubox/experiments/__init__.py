"""Experiment framework: base class, runner, and modular experiment types.

Provides both the v3 namespace API (``ExperimentLibrary``, ``WorkflowLibrary``)
and all concrete experiment classes.

Sub-packages group experiments by physics domain:

* ``spectroscopy/`` — resonator, qubit, and readout spectroscopy
* ``time_domain/`` — Rabi, T1, T2, chevrons
* ``calibration/`` — readout calibration, gate calibration, benchmarking
* ``cavity/`` — storage resonator, Fock-resolved, number splitting
* ``tomography/`` — state, Fock, and Wigner tomography
* ``spa/`` — SPA flux and pump optimization
"""

from .templates import ExperimentLibrary
from .workflows import WorkflowLibrary
from .decorator import experiment, get_registered_experiments, lookup_experiment

from .base import ExperimentRunner
from .experiment_base import ExperimentBase

# Re-export all experiment classes for convenience
from .spectroscopy import (
    ResonatorSpectroscopy,
    ResonatorPowerSpectroscopy,
    ResonatorSpectroscopyX180,
    ReadoutTrace,
    ReadoutFrequencyOptimization,
    QubitSpectroscopy,
    QubitSpectroscopyCoarse,
    QubitSpectroscopyEF,
)
from .time_domain import (
    TemporalRabi,
    PowerRabi,
    SequentialQubitRotations,
    T1Relaxation,
    T2Ramsey,
    T2Echo,
    ResidualPhotonRamsey,
    TimeRabiChevron,
    PowerRabiChevron,
    RamseyChevron,
)
from .calibration import (
    IQBlob,
    ReadoutGERawTrace,
    ReadoutGEIntegratedTrace,
    ReadoutGEDiscrimination,
    ReadoutWeightsOptimization,
    ReadoutButterflyMeasurement,
    CalibrateReadoutFull,
    CalibrationReadoutFull,
    ReadoutAmpLenOpt,
    AllXY,
    DRAGCalibration,
    RandomizedBenchmarking,
    PulseTrainCalibration,
    QubitResetBenchmark,
    ActiveQubitResetBenchmark,
    ReadoutLeakageBenchmarking,
)
from .cavity import (
    StorageSpectroscopy,
    StorageSpectroscopyCoarse,
    NumSplittingSpectroscopy,
    StorageRamsey,
    StorageChiRamsey,
    StoragePhaseEvolution,
    FockResolvedSpectroscopy,
    FockResolvedT1,
    FockResolvedRamsey,
    FockResolvedPowerRabi,
)
from .tomography import (
    QubitStateTomography,
    FockResolvedStateTomography,
    StorageWignerTomography,
    SNAPOptimization,
)
from .spa import (
    SPAFluxOptimization,
    SPAFluxOptimization2,
    SPAPumpFrequencyOptimization,
)

__all__ = [
    # v3 API
    "ExperimentLibrary",
    "WorkflowLibrary",
    # Infrastructure
    "ExperimentRunner",
    "ExperimentBase",
    # Spectroscopy
    "ResonatorSpectroscopy",
    "ResonatorPowerSpectroscopy",
    "ResonatorSpectroscopyX180",
    "ReadoutTrace",
    "ReadoutFrequencyOptimization",
    "QubitSpectroscopy",
    "QubitSpectroscopyCoarse",
    "QubitSpectroscopyEF",
    # Time domain
    "TemporalRabi",
    "PowerRabi",
    "SequentialQubitRotations",
    "T1Relaxation",
    "T2Ramsey",
    "T2Echo",
    "ResidualPhotonRamsey",
    "TimeRabiChevron",
    "PowerRabiChevron",
    "RamseyChevron",
    # Calibration
    "IQBlob",
    "ReadoutGERawTrace",
    "ReadoutGEIntegratedTrace",
    "ReadoutGEDiscrimination",
    "ReadoutWeightsOptimization",
    "ReadoutButterflyMeasurement",
    "CalibrateReadoutFull",
    "CalibrationReadoutFull",
    "ReadoutAmpLenOpt",
    "AllXY",
    "DRAGCalibration",
    "RandomizedBenchmarking",
    "PulseTrainCalibration",
    "QubitResetBenchmark",
    "ActiveQubitResetBenchmark",
    "ReadoutLeakageBenchmarking",
    # Cavity / Fock
    "StorageSpectroscopy",
    "StorageSpectroscopyCoarse",
    "NumSplittingSpectroscopy",
    "StorageRamsey",
    "StorageChiRamsey",
    "StoragePhaseEvolution",
    "FockResolvedSpectroscopy",
    "FockResolvedT1",
    "FockResolvedRamsey",
    "FockResolvedPowerRabi",
    # Tomography
    "QubitStateTomography",
    "FockResolvedStateTomography",
    "StorageWignerTomography",
    "SNAPOptimization",
    # SPA
    "SPAFluxOptimization",
    "SPAFluxOptimization2",
    "SPAPumpFrequencyOptimization",
]
