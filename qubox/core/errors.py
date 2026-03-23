"""qubox.core.errors — unified exception hierarchy.

Canonical exception hierarchy for the qubox package.  All qubox exceptions
inherit from :class:`QuboxError` so callers can catch them with a single
``except QuboxError`` if desired.
"""
from __future__ import annotations


class QuboxError(Exception):
    """Base class for all qubox exceptions."""


class ConfigError(QuboxError):
    """Invalid or missing configuration."""


class ConnectionError(QuboxError):  # noqa: A001  (shadows built-in intentionally)
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
    """Device/cooldown/wiring context mismatch during calibration load.

    Inherits from :class:`ConfigError` for backward compatibility with
    legacy code that catches ``ConfigError``.
    """
