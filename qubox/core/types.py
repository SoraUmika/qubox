"""qubox.core.types — hardware-level enumerations and constants.

Migrated from ``qubox_v2_legacy.core.types`` with no external dependencies.
"""
from __future__ import annotations

from enum import Enum


class ExecMode(str, Enum):
    """Execution mode for a QM program."""

    HARDWARE = "hardware"
    SIMULATION = "simulation"


class PulseType(str, Enum):
    """Pulse envelope shape category."""

    CONSTANT = "constant"
    ARBITRARY = "arbitrary"
    DRAG = "drag"


class WaveformType(str, Enum):
    """Waveform envelope family."""

    GAUSSIAN = "gaussian"
    COSINE = "cosine"
    FLATTOP = "flattop"
    CONSTANT = "constant"
    KAISER = "kaiser"
    SLEPIAN = "slepian"


class DemodMode(str, Enum):
    """Demodulation / integration mode."""

    FULL = "full"
    SLICED = "sliced"
    ACCUMULATED = "accumulated"


class WeightLabel(str, Enum):
    """Integration weight channel labels (OPX convention)."""

    COSINE = "cos"
    SINE = "sin"


# ---------------------------------------------------------------------------
# Hardware constants
# ---------------------------------------------------------------------------

#: OPX+ DAC safe output limit (volts peak).
MAX_AMPLITUDE: float = 0.45

#: Typical base amplitude used in coherent pulse calibration.
BASE_AMPLITUDE: float = 0.24

#: OPX clock cycle in nanoseconds (all pulse lengths must be multiples).
CLOCK_CYCLE_NS: int = 4
