"""qubox.core.types — hardware-level enumerations, type aliases, and constants.

Unified types module combining the v3 API enums and the legacy runtime
enums/aliases.  Both naming conventions are supported for backward
compatibility.
"""
from __future__ import annotations

from enum import Enum
from typing import Union

import numpy as np


# ---------------------------------------------------------------------------
# Execution mode
# ---------------------------------------------------------------------------
class ExecMode(str, Enum):
    """Execution mode for a QM program.

    v3 names: ``HARDWARE``, ``SIMULATION``
    Legacy names: ``RUN``, ``SIMULATE``, ``CONTINUOUS_WAVE``
    """
    HARDWARE = "hardware"
    SIMULATION = "simulation"
    # Legacy aliases
    RUN = "run"
    SIMULATE = "simulate"
    CONTINUOUS_WAVE = "cw"


# ---------------------------------------------------------------------------
# Pulse / waveform classification
# ---------------------------------------------------------------------------
class PulseType(str, Enum):
    """Pulse envelope shape category.

    v3 names: ``CONSTANT``, ``ARBITRARY``, ``DRAG``
    Legacy names: ``CONTROL``, ``MEASUREMENT``
    """
    CONSTANT = "constant"
    ARBITRARY = "arbitrary"
    DRAG = "drag"
    # Legacy aliases
    CONTROL = "control"
    MEASUREMENT = "measurement"


class WaveformType(str, Enum):
    """Waveform envelope family.

    v3 names: ``GAUSSIAN``, ``COSINE``, ``FLATTOP``, ``KAISER``, ``SLEPIAN``
    Legacy QM names: ``CONSTANT``, ``ARBITRARY``
    """
    GAUSSIAN = "gaussian"
    COSINE = "cosine"
    FLATTOP = "flattop"
    CONSTANT = "constant"
    KAISER = "kaiser"
    SLEPIAN = "slepian"
    # Legacy QM config-level type
    ARBITRARY = "arbitrary"


class DemodMode(str, Enum):
    """Demodulation / integration mode."""
    FULL = "full"
    SLICED = "sliced"
    ACCUMULATED = "accumulated"
    MOVING_WINDOW = "moving_window"


class WeightLabel(str, Enum):
    """Integration weight channel labels (OPX convention).

    v3 names: ``COSINE``, ``SINE``
    Legacy names: ``COS``, ``SIN``, ``MINUS_SIN``
    """
    COSINE = "cos"
    SINE = "sin"
    # Legacy aliases
    COS = "cos"
    SIN = "sin"
    MINUS_SIN = "minus_sin"


# ---------------------------------------------------------------------------
# Type aliases (from legacy runtime)
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
# Hardware constants
# ---------------------------------------------------------------------------

#: OPX+ DAC safe output limit (volts peak).
MAX_AMPLITUDE: float = 0.45

#: Typical base amplitude used in coherent pulse calibration.
BASE_AMPLITUDE: float = 0.24

#: OPX clock cycle in nanoseconds (all pulse lengths must be multiples).
CLOCK_CYCLE_NS: int = 4
