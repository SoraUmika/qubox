"""Calibration experiment modules.

Readout calibration
-------------------
IQBlob
    Simple g/e IQ blob acquisition.
ReadoutGERawTrace
    Raw time-domain readout trace for ground/excited.
ReadoutGEIntegratedTrace
    Time-sliced integrated g/e traces.
ReadoutGEDiscrimination
    G/E IQ discrimination with weight rotation.
ReadoutWeightsOptimization
    Optimize integration weights from g/e traces.
ReadoutButterflyMeasurement
    Three-measurement butterfly protocol (F, Q, QND).
CalibrateReadoutFull
    End-to-end readout calibration pipeline.
ReadoutAmpLenOpt
    2-D sweep of readout amplitude x length for fidelity.

Gate calibration
----------------
AllXY
    21-gate-pair error benchmarking.
DRAGCalibration
    DRAG coefficient optimization.
QubitPulseTrain
    Amplitude calibration via pulse repetition.
RandomizedBenchmarking
    Standard and interleaved randomized benchmarking.

Reset / leakage
----------------
QubitResetBenchmark
    Qubit reset fidelity benchmark.
ActiveQubitResetBenchmark
    Active reset effectiveness measurement.
ReadoutLeakageBenchmarking
    Readout leakage to other states.
"""
from .readout import (
    IQBlob,
    ReadoutGERawTrace,
    ReadoutGEIntegratedTrace,
    ReadoutGEDiscrimination,
    ReadoutWeightsOptimization,
    ReadoutButterflyMeasurement,
    CalibrateReadoutFull,
    CalibrationReadoutFull,
    ReadoutAmpLenOpt,
)
from .readout_config import ReadoutConfig
from .gates import (
    AllXY,
    DRAGCalibration,
    QubitPulseTrain,
    QubitPulseTrainLegacy,
    RandomizedBenchmarking,
)
from .reset import (
    QubitResetBenchmark,
    ActiveQubitResetBenchmark,
    ReadoutLeakageBenchmarking,
)

__all__ = [
    "IQBlob",
    "ReadoutGERawTrace",
    "ReadoutGEIntegratedTrace",
    "ReadoutGEDiscrimination",
    "ReadoutWeightsOptimization",
    "ReadoutButterflyMeasurement",
    "CalibrateReadoutFull",
    "CalibrationReadoutFull",
    "ReadoutAmpLenOpt",
    "ReadoutConfig",
    "AllXY",
    "DRAGCalibration",
    "QubitPulseTrain",
    "QubitPulseTrainLegacy",
    "RandomizedBenchmarking",
    "QubitResetBenchmark",
    "ActiveQubitResetBenchmark",
    "ReadoutLeakageBenchmarking",
]
