# qubox_v2/core/types.py
"""Shared type aliases, enums, and constants used across qubox."""
from __future__ import annotations

from enum import Enum, auto
from typing import Union

import numpy as np


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class ExecMode(str, Enum):
    """Program execution mode."""
    RUN = "run"
    SIMULATE = "simulate"
    CONTINUOUS_WAVE = "cw"


class PulseType(str, Enum):
    """QM pulse operation type."""
    CONTROL = "control"
    MEASUREMENT = "measurement"


class WaveformType(str, Enum):
    """QM waveform type."""
    CONSTANT = "constant"
    ARBITRARY = "arbitrary"


class DemodMode(str, Enum):
    """Demodulation mode for measurement."""
    FULL = "full"
    SLICED = "sliced"
    ACCUMULATED = "accumulated"
    MOVING_WINDOW = "moving_window"


class WeightLabel(str, Enum):
    """Standard integration weight labels."""
    COS = "cos"
    SIN = "sin"
    MINUS_SIN = "minus_sin"


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
WaveformSamples = Union[float, list[float], np.ndarray]
"""A waveform: scalar (constant) or array (arbitrary)."""

FrequencyHz = float
"""Frequency in Hz."""

ClockCycles = int
"""Duration in QM clock cycles (1 cc = 4 ns)."""

Nanoseconds = int
"""Duration in nanoseconds (must be divisible by 4 for QM)."""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_AMPLITUDE: float = 0.45
"""Maximum safe output amplitude (V) for OPX+ DAC."""

BASE_AMPLITUDE: float = 0.24
"""Default constant-pulse amplitude (V)."""

CLOCK_CYCLE_NS: int = 4
"""Duration of one QM clock cycle in nanoseconds."""
