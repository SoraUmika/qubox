"""qubox.core — foundational types, errors, persistence, configuration, and logging.

Unified core module incorporating all formerly-legacy infrastructure.
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
from .logging import configure_global_logging, get_logger
from .config import (
    ControllerConfig,
    OctaveRFOutput,
    OctaveRFInput,
    OctaveConfig,
    ElementConfig,
    HardwareConfig,
    ExternalLOEntry,
    QuboxExtras,
)
from .experiment_context import ExperimentContext
from .hardware_definition import HardwareDefinition
from .device_metadata import DeviceMetadata
from .bindings import (
    ChannelRef,
    OutputBinding,
    InputBinding,
    ReadoutBinding,
    ExperimentBindings,
    DriveTarget,
    ReadoutCal,
    ReadoutHandle,
    ElementFreq,
    FrequencyPlan,
    ConfigBuilder,
)
from .types import (
    ExecMode,
    PulseType,
    WaveformType,
    DemodMode,
    WeightLabel,
    WaveformSamples,
    FrequencyHz,
    ClockCycles,
    Nanoseconds,
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
    # types & constants
    "ExecMode",
    "PulseType",
    "WaveformType",
    "DemodMode",
    "WeightLabel",
    "WaveformSamples",
    "FrequencyHz",
    "ClockCycles",
    "Nanoseconds",
    "MAX_AMPLITUDE",
    "BASE_AMPLITUDE",
    "CLOCK_CYCLE_NS",
    # logging
    "configure_global_logging",
    "get_logger",
    # config models
    "ControllerConfig",
    "OctaveRFOutput",
    "OctaveRFInput",
    "OctaveConfig",
    "ElementConfig",
    "HardwareConfig",
    "ExternalLOEntry",
    "QuboxExtras",
    # context & hardware
    "ExperimentContext",
    "HardwareDefinition",
    "DeviceMetadata",
    # bindings
    "ChannelRef",
    "OutputBinding",
    "InputBinding",
    "ReadoutBinding",
    "ExperimentBindings",
    "ConfigBuilder",
    "DriveTarget",
    "ReadoutCal",
    "ReadoutHandle",
    "ElementFreq",
    "FrequencyPlan",
]
