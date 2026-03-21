# qubox_v2/hardware/__init__.py
"""
Hardware abstraction layer — split from the monolithic QuaProgramManager.

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
from .qua_program_manager import QuaProgramManager

__all__ = [
    "ConfigEngine",
    "HardwareController",
    "ProgramRunner",
    "RunResult",
    "ExecMode",
    "QueueManager",
    "QuaProgramManager",
]
