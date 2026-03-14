"""Canonical qubox public API.

`qubox` is the new user-facing package. The older `qubox_v2` package remains
available as a compatibility layer while the refactor is staged.
"""
from __future__ import annotations

from .calibration import CalibrationProposal, CalibrationSnapshot
from .circuit import QuantumCircuit, QuantumGate
from .data import ExecutionRequest, ExperimentResult
from .sequence import AcquisitionSpec, Condition, Operation, Sequence, SweepAxis, SweepPlan
from .session import Session

__version__ = "3.0.0"

__all__ = [
    "__version__",
    "AcquisitionSpec",
    "CalibrationProposal",
    "CalibrationSnapshot",
    "Condition",
    "ExecutionRequest",
    "ExperimentResult",
    "Operation",
    "QuantumCircuit",
    "QuantumGate",
    "Sequence",
    "Session",
    "SweepAxis",
    "SweepPlan",
]
