# qubox_v2/core/errors.py
"""
Unified exception hierarchy for the qubox package.

All qubox exceptions inherit from QuboxError so callers can catch
them with a single ``except QuboxError`` if desired.
"""


class QuboxError(RuntimeError):
    """Base exception for all qubox errors."""


class ConfigError(QuboxError):
    """Invalid or missing configuration."""


class ConnectionError(QuboxError):
    """Communication failure with OPX+ / Octave / external instrument."""


class JobError(QuboxError):
    """QUA job submission, execution, or fetch failure."""


class DeviceError(QuboxError):
    """External-device driver error (SignalCore, OctoDac, etc.)."""


class PulseError(QuboxError):
    """Invalid pulse definition (amplitude, length, waveform reference)."""


class CalibrationError(QuboxError):
    """Octave or element calibration failure."""


class ContextMismatchError(ConfigError):
    """Device/cooldown/wiring context mismatch during calibration load."""
