"""Canonical qubox public API.

``qubox`` is the unified package for cQED experiment orchestration,
hardware control, and analysis.

Subpackages
-----------
qubox.notebook
    Notebook-facing import surface: experiment classes, calibration stack,
    session bootstrap, and workflow helpers.
"""
from __future__ import annotations

from .calibration import CalibrationProposal, CalibrationSnapshot
from .circuit import QuantumCircuit, QuantumGate
from .core.device_metadata import DeviceMetadata
from .core.protocols import SessionProtocol
from .data import ExecutionRequest, ExperimentResult, RunManifest
from .sequence import AcquisitionSpec, Condition, Operation, Sequence, SweepAxis, SweepPlan
from .session import Session, SessionFactory

__version__ = "3.0.0"

__all__ = [
    "__version__",
    "AcquisitionSpec",
    "CalibrationProposal",
    "CalibrationSnapshot",
    "Condition",
    "DeviceMetadata",
    "ExecutionRequest",
    "ExperimentResult",
    "Operation",
    "QuantumCircuit",
    "QuantumGate",
    "RunManifest",
    "Sequence",
    "Session",
    "SessionFactory",
    "SessionProtocol",
    "SweepAxis",
    "SweepPlan",
]
