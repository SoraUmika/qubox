"""qubox.core.errors — exception hierarchy.

Migrated from ``qubox_v2_legacy.core.errors`` with no external dependencies.
"""
from __future__ import annotations


class QuboxError(Exception):
    """Base class for all qubox exceptions."""


class ConfigError(QuboxError):
    """Raised for invalid or missing configuration."""


class ConnectionError(QuboxError):  # noqa: A001  (shadows built-in intentionally)
    """Raised when a hardware connection cannot be established."""


class JobError(QuboxError):
    """Raised when a QM job fails or times out."""


class DeviceError(QuboxError):
    """Raised for device-level failures (calibration state, hardware faults)."""


class PulseError(QuboxError):
    """Raised for invalid pulse definitions or registration failures."""


class CalibrationError(QuboxError):
    """Raised for calibration data consistency or validation failures."""


class ContextMismatchError(QuboxError):
    """Raised when the session context does not match the on-disk calibration.

    Typical causes:
    - Loading a calibration file made for a different sample.
    - Hardware.json has been changed (wiring_rev mismatch).
    """
