"""Time-domain experiment modules.

Classes
-------
TemporalRabi
    Qubit Rabi oscillations vs pulse duration.
PowerRabi
    Qubit Rabi oscillations vs pulse amplitude/gain.
T1Relaxation
    Energy relaxation time measurement.
T2Ramsey
    Ramsey interferometry (T2*) measurement.
T2Echo
    Hahn spin-echo (T2echo) measurement.
TimeRabiChevron
    2-D Rabi vs detuning and duration.
PowerRabiChevron
    2-D Rabi vs detuning and amplitude.
RamseyChevron
    2-D Ramsey vs detuning and delay.
SequentialQubitRotations
    Apply a sequence of qubit rotations and measure.
ResidualPhotonRamsey
    Cavity residual-photon characterization via Ramsey.
"""
from .rabi import TemporalRabi, PowerRabi, SequentialQubitRotations
from .relaxation import T1Relaxation
from .coherence import T2Ramsey, T2Echo, ResidualPhotonRamsey
from .chevron import TimeRabiChevron, PowerRabiChevron, RamseyChevron

__all__ = [
    "TemporalRabi",
    "PowerRabi",
    "SequentialQubitRotations",
    "T1Relaxation",
    "T2Ramsey",
    "T2Echo",
    "ResidualPhotonRamsey",
    "TimeRabiChevron",
    "PowerRabiChevron",
    "RamseyChevron",
]
