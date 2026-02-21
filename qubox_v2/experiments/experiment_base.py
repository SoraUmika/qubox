"""qubox_v2.experiments.experiment_base
======================================
Base class for modular experiment types.

Each experiment class wraps one or more QUA program factories from
``qubox_v2.programs.cQED_programs`` and provides a consistent interface
for building, running, and post-processing results.

Experiment classes are lightweight — they hold a reference to the
experiment *context* (``cQED_Experiment`` or ``ExperimentRunner``) which
provides hardware control, pulse management, device access, and
calibration storage.

Usage::

    from qubox_v2.experiments.spectroscopy import ResonatorSpectroscopy

    exp = cQED_Experiment(...)
    spec = ResonatorSpectroscopy(exp)
    result = spec.run(readout_op="readout", rf_begin=8.6e9, rf_end=8.62e9, df=50e3)
"""
from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any

import numpy as np

from ..programs import cQED_programs
from ..analysis import post_process as pp
from ..analysis.output import Output
from ..core.logging import get_logger
from ..hardware.program_runner import RunResult

if TYPE_CHECKING:
    from ..analysis.cQED_attributes import cQED_attributes
    from ..devices.device_manager import DeviceManager
    from ..pulses.manager import PulseOperationManager

_logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Utility functions (formerly module-level in legacy_experiment.py)
# ---------------------------------------------------------------------------
from .config_builder import ConfigSettings

def create_if_frequencies(
    el: str, start_fq: float, end_fq: float, df: float,
    lo_freq: float, base_if_freq: float = ConfigSettings.BASE_IF,
) -> np.ndarray:
    """Compute IF frequency array for a sweep, validating bounds."""
    up_converted_if = lo_freq + base_if_freq
    max_bandwidth = abs(ConfigSettings.MAX_IF_BANDWIDTH - abs(base_if_freq))
    sweep_min = up_converted_if - max_bandwidth
    sweep_max = up_converted_if

    if not (sweep_min <= start_fq <= end_fq <= sweep_max):
        raise ValueError(
            f"Sweep range [{start_fq/1e6:.1f}, {end_fq/1e6:.1f}] MHz outside "
            f"[{sweep_min/1e6:.1f}, {sweep_max/1e6:.1f}] MHz for element "
            f"'{el}' (LO={lo_freq/1e6:.1f}, IF={base_if_freq/1e6:.1f} MHz)"
        )
    return np.arange(start_fq - lo_freq, end_fq - lo_freq - 0.1, df, dtype=int)


def create_clks_array(
    t_begin: float, t_end: float, dt: float,
    time_per_clk: float = 4,
) -> np.ndarray:
    """Convert time range to clock-cycle array with rounding warnings."""
    if t_end < t_begin:
        raise ValueError("t_end must be >= t_begin")
    if dt <= 0:
        raise ValueError("dt must be positive")

    def _snap(v, label):
        snapped = round(v / time_per_clk) * time_per_clk
        if snapped != v:
            warnings.warn(
                f"{label} {v} rounded to {snapped} (grid={time_per_clk})",
                RuntimeWarning, stacklevel=3,
            )
        return snapped

    t_begin = _snap(t_begin, "t_begin")
    t_end = _snap(t_end, "t_end")
    dt = _snap(dt, "dt")

    clk_begin = int(t_begin // time_per_clk)
    clk_end = int(t_end // time_per_clk)
    clk_step = int(dt // time_per_clk)
    return np.arange(clk_begin, clk_end + 1, clk_step, dtype=int)


def make_lo_segments(rf_begin: float, rf_end: float) -> list[float]:
    """Compute LO frequency list for multi-segment coarse sweeps."""
    M = ConfigSettings.MAX_IF_BANDWIDTH
    B = ConfigSettings.BASE_IF
    if M <= abs(B):
        raise ValueError("MAX_IF_BANDWIDTH must be greater than |BASE_IF|")
    span = M + B
    if (rf_end - rf_begin) <= span:
        return [rf_begin + M]
    los: list[float] = []
    LO = rf_begin + M
    last = rf_end - B
    while LO < last:
        los.append(LO)
        LO += span
    if los[-1] < last:
        los.append(last)
    return los


def if_freqs_for_segment(LO: float, rf_end: float, df: float) -> np.ndarray:
    """Compute IF frequency array for one segment of a coarse sweep."""
    M = ConfigSettings.MAX_IF_BANDWIDTH
    B = ConfigSettings.BASE_IF
    max_if = (rf_end - LO) if (rf_end - LO) < (M + B) else B
    return np.arange(-M, max_if + 1e-12, df, dtype=int)


def merge_segment_outputs(
    outputs: list[Output], freqs: list[np.ndarray],
) -> Output:
    """Stitch multiple segment outputs into one."""
    merged: dict[str, Any] = {}
    for key in outputs[0]:
        vals = [o[key] for o in outputs if key in o]
        if isinstance(vals[0], np.ndarray):
            try:
                merged[key] = np.concatenate(vals, axis=0)
            except Exception:
                merged[key] = vals
        elif isinstance(vals[0], list):
            merged[key] = sum(vals, [])
        else:
            merged[key] = vals[0] if all(v == vals[0] for v in vals) else vals
    merged["frequencies"] = np.concatenate(freqs, axis=0)
    return Output(merged)


# ---------------------------------------------------------------------------
# ExperimentBase
# ---------------------------------------------------------------------------
class ExperimentBase:
    """Base class for modular experiment types.

    Provides unified access to the experiment infrastructure regardless
    of whether the context is a ``cQED_Experiment`` (legacy) or the
    new ``ExperimentRunner``.

    Parameters
    ----------
    ctx
        Experiment context — either ``cQED_Experiment`` or
        ``ExperimentRunner``.
    """

    def __init__(self, ctx: Any) -> None:
        self._ctx = ctx

    @property
    def name(self) -> str:
        return type(self).__name__

    # ------------------------------------------------------------------
    # Context accessors (work with both legacy and new interfaces)
    # ------------------------------------------------------------------
    @property
    def attr(self) -> cQED_attributes:
        return self._ctx.attributes

    @property
    def pulse_mgr(self) -> PulseOperationManager:
        return getattr(self._ctx, "pulseOpMngr",
                       getattr(self._ctx, "pulse_mgr", None))

    @property
    def hw(self):
        """Hardware controller (QuaProgramManager or HardwareController)."""
        return getattr(self._ctx, "quaProgMngr",
                       getattr(self._ctx, "hw", None))

    @property
    def device_manager(self) -> DeviceManager | None:
        return getattr(self._ctx, "device_manager", None)

    @property
    def measure_macro(self):
        """Access the measurement macro singleton."""
        from ..programs.macros.measure import measureMacro
        return measureMacro

    # ------------------------------------------------------------------
    # Common helpers
    # ------------------------------------------------------------------
    def set_standard_frequencies(self, *, qb_fq: float | None = None) -> None:
        """Set readout and qubit element frequencies to calibrated values."""
        mm = self.measure_macro
        self.hw.set_element_fq(self.attr.ro_el, mm._drive_frequency)
        self.hw.set_element_fq(self.attr.qb_el, qb_fq or self.attr.qb_fq)

    def get_readout_lo(self) -> float:
        return self.hw.get_element_lo(self.attr.ro_el)

    def get_qubit_lo(self) -> float:
        return self.hw.get_element_lo(self.attr.qb_el)

    def run_program(
        self, prog, *, n_total: int, processors: list | None = None,
        process_in_sim: bool = False, **kw,
    ) -> RunResult:
        """Run a QUA program via the hardware controller."""
        return self.hw.run_program(
            prog, n_total=n_total,
            processors=processors or [pp.proc_default],
            process_in_sim=process_in_sim, **kw,
        )

    def save_output(self, output, tag: str = "") -> None:
        """Persist experiment output to disk."""
        if hasattr(self._ctx, "save_output"):
            self._ctx.save_output(output, tag)

    # ------------------------------------------------------------------
    # Default protocol methods (override in subclasses)
    # ------------------------------------------------------------------
    def build_program(self, **params: Any) -> Any:
        raise NotImplementedError(
            f"{self.name}.build_program() not implemented"
        )

    def run(self, **params: Any) -> RunResult:
        raise NotImplementedError(
            f"{self.name}.run() not implemented"
        )

    def process(self, raw_output: Any, **params: Any) -> Any:
        """Post-process raw output. Default: return as-is."""
        return raw_output
