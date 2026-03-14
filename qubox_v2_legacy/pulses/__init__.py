# qubox_v2/pulses/__init__.py
"""Pulse and waveform management layer.

Two main entry points:

* ``PulseOperationManager`` – full-featured manager used by the legacy
  ``cQED_Experiment`` and ``ExperimentRunner``.
* ``PulseRegistry`` – simplified, clean API for adding / modifying / removing
  pulses without touching the underlying store internals.
"""
from .manager import PulseOperationManager, build_pulse_operation_manager_from_config
from .pulse_registry import PulseRegistry

__all__ = [
    "PulseOperationManager",
    "build_pulse_operation_manager_from_config",
    "PulseRegistry",
]
