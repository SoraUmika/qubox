# qubox_v2/experiments/configs.py
"""Typed, frozen configuration dataclasses for experiments.

Each experiment has a dedicated ``*Config`` that captures its physics
parameters as an immutable snapshot.  These replace the previous pattern of
passing 5-10 kwargs through ``run()``.

Benefits:
- Type-safe, IDE-discoverable parameters with sensible defaults.
- Immutable -- safe to cache, log, and reproduce.
- Compose with ``dataclasses.replace()`` for parameter sweeps.

Example::

    from qubox_v2.experiments.configs import PowerRabiConfig

    cfg = PowerRabiConfig(max_gain=0.4, n_avg=2000)
    result = rabi.run(cfg, drive=qb, readout=ro)

    # Parameter sweep via replace
    from dataclasses import replace
    for gain in [0.1, 0.2, 0.3]:
        result = rabi.run(replace(cfg, max_gain=gain), drive=qb, readout=ro)
"""
from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Time-domain experiments
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PowerRabiConfig:
    """Physics parameters for a power Rabi experiment.

    Attributes
    ----------
    op : str
        QUA pulse operation to sweep (default ``"ge_ref_r180"``).
    max_gain : float
        Maximum gain amplitude for the sweep.
    dg : float
        Gain step size.
    n_avg : int
        Number of averages per point.
    length : int | None
        Pulse length override in ns.  ``None`` uses the pulse default.
    truncate_clks : int | None
        Truncation in clock cycles.  ``None`` disables truncation.
    """

    op: str = "ge_ref_r180"
    max_gain: float = 0.5
    dg: float = 1e-3
    n_avg: int = 1000
    length: int | None = None
    truncate_clks: int | None = None


@dataclass(frozen=True)
class TemporalRabiConfig:
    """Physics parameters for a temporal (time) Rabi experiment.

    Attributes
    ----------
    pulse : str
        QUA pulse operation to use.
    pulse_len_begin : int
        Start of pulse-length sweep in ns.
    pulse_len_end : int
        End of pulse-length sweep in ns.
    dt : int
        Step size in ns.
    pulse_gain : float
        Fixed gain amplitude during the sweep.
    n_avg : int
        Number of averages per point.
    """

    pulse: str = "ge_ref_r180"
    pulse_len_begin: int = 4
    pulse_len_end: int = 1000
    dt: int = 4
    pulse_gain: float = 1.0
    n_avg: int = 1000


@dataclass(frozen=True)
class T1RelaxationConfig:
    """Physics parameters for a T1 relaxation experiment.

    Attributes
    ----------
    r180 : str
        Pi-pulse operation (default ``"x180"``).
    delay_begin : int
        Start of delay sweep in ns.
    delay_end : int
        End of delay sweep in ns.
    dt : int
        Delay step size in ns.
    n_avg : int
        Number of averages per point.
    """

    r180: str = "x180"
    delay_begin: int = 4
    delay_end: int = 50_000
    dt: int = 500
    n_avg: int = 2000


@dataclass(frozen=True)
class T2RamseyConfig:
    """Physics parameters for a T2 Ramsey experiment.

    Attributes
    ----------
    r90 : str
        Pi/2-pulse operation (default ``"x90"``).
    qb_detune_MHz : float
        Qubit detuning in MHz for the artificial oscillation.
    delay_begin : int
        Start of delay sweep in ns.
    delay_end : int
        End of delay sweep in ns.
    dt : int
        Delay step size in ns.
    n_avg : int
        Number of averages per point.
    """

    r90: str = "x90"
    qb_detune_MHz: float = 0.2
    delay_begin: int = 4
    delay_end: int = 40_000
    dt: int = 100
    n_avg: int = 4000


@dataclass(frozen=True)
class T2EchoConfig:
    """Physics parameters for a T2 echo (Hahn echo) experiment.

    Attributes
    ----------
    r180 : str
        Pi-pulse operation (default ``"x180"``).
    r90 : str
        Pi/2-pulse operation (default ``"x90"``).
    delay_begin : int
        Start of delay sweep in ns.
    delay_end : int
        End of delay sweep in ns.
    dt : int
        Delay step size in ns.
    n_avg : int
        Number of averages per point.
    """

    r180: str = "x180"
    r90: str = "x90"
    delay_begin: int = 8
    delay_end: int = 50_000
    dt: int = 500
    n_avg: int = 2000


# ---------------------------------------------------------------------------
# Spectroscopy experiments
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ResonatorSpectroscopyConfig:
    """Physics parameters for resonator spectroscopy.

    Attributes
    ----------
    readout_op : str
        Readout pulse operation.
    rf_begin : float
        Start of RF frequency sweep in Hz.
    rf_end : float
        End of RF frequency sweep in Hz.
    df : float
        Frequency step in Hz.
    n_avg : int
        Number of averages per point.
    """

    readout_op: str = "readout"
    rf_begin: float = 8.5e9
    rf_end: float = 8.7e9
    df: float = 100e3
    n_avg: int = 1000


@dataclass(frozen=True)
class QubitSpectroscopyConfig:
    """Physics parameters for qubit spectroscopy.

    Attributes
    ----------
    saturation_op : str
        Saturation pulse operation.
    rf_begin : float
        Start of RF frequency sweep in Hz.
    rf_end : float
        End of RF frequency sweep in Hz.
    df : float
        Frequency step in Hz.
    saturation_amp : float
        Saturation pulse amplitude.
    n_avg : int
        Number of averages per point.
    """

    saturation_op: str = "saturation"
    rf_begin: float = 6.0e9
    rf_end: float = 6.5e9
    df: float = 100e3
    saturation_amp: float = 1.0
    n_avg: int = 1000


# ---------------------------------------------------------------------------
# Cavity experiments
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class StorageSpectroscopyConfig:
    """Physics parameters for storage cavity spectroscopy.

    Attributes
    ----------
    disp : str
        Displacement pulse operation (default ``"const_alpha"``).
    sel_r180 : str
        Number-selective pi-pulse (default ``"sel_x180"``).
    rf_begin : float
        Start of RF frequency sweep in Hz.
    rf_end : float
        End of RF frequency sweep in Hz.
    df : float
        Frequency step in Hz.
    storage_therm_clks : int
        Thermalization wait for storage cavity in clock cycles.
    n_avg : int
        Number of averages per point.
    """

    disp: str = "const_alpha"
    sel_r180: str = "sel_x180"
    rf_begin: float = 5.0e9
    rf_end: float = 5.5e9
    df: float = 200e3
    storage_therm_clks: int = 500_000
    n_avg: int = 50
