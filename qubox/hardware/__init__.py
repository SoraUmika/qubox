# qubox/hardware/__init__.py
"""
Hardware abstraction layer.

Components:
    ConfigEngine     — Load / save / patch / build QM config dicts
    HardwareController — Live element control (LO, IF, gain, output mode)
    ProgramRunner    — Execute / simulate QUA programs
    QueueManager     — Multi-user job queue operations
    OctaveManager    — Octave-specific calibration & LO routing
"""
from .config_engine import ConfigEngine
from .controller import HardwareController
from .program_runner import ProgramRunner, RunResult, ExecMode
from .queue_manager import QueueManager

__all__ = [
    "ConfigEngine",
    "HardwareController",
    "ProgramRunner",
    "RunResult",
    "ExecMode",
    "QueueManager",
]
