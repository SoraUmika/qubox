"""qubox.core — foundational types, errors, and persistence utilities.

All symbols here are free of ``qubox_v2_legacy`` dependencies and can be
imported safely in any context.
"""

from .errors import (
    QuboxError,
    ConfigError,
    ConnectionError,
    JobError,
    DeviceError,
    PulseError,
    CalibrationError,
    ContextMismatchError,
)
from .types import (
    ExecMode,
    PulseType,
    WaveformType,
    DemodMode,
    WeightLabel,
    MAX_AMPLITUDE,
    BASE_AMPLITUDE,
    CLOCK_CYCLE_NS,
)

__all__ = [
    # errors
    "QuboxError",
    "ConfigError",
    "ConnectionError",
    "JobError",
    "DeviceError",
    "PulseError",
    "CalibrationError",
    "ContextMismatchError",
    # types
    "ExecMode",
    "PulseType",
    "WaveformType",
    "DemodMode",
    "WeightLabel",
    "MAX_AMPLITUDE",
    "BASE_AMPLITUDE",
    "CLOCK_CYCLE_NS",
]
