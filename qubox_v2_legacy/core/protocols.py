# qubox_v2/core/protocols.py
"""
Protocol interfaces that define the contracts between qubox subsystems.

Using typing.Protocol (structural subtyping) so implementations don't need
to inherit — they just need to have the right methods.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Protocol, Union, runtime_checkable

import numpy as np


# ---------------------------------------------------------------------------
# Hardware Control
# ---------------------------------------------------------------------------
@runtime_checkable
class HardwareController(Protocol):
    """Contract for controlling OPX+/Octave hardware."""

    def set_element_lo(self, element: str, lo_freq: float) -> None: ...
    def set_element_fq(self, element: str, freq: float) -> None: ...
    def set_octave_output(self, element: str, mode: Any) -> None: ...
    def set_octave_gain(self, element: str, gain: float) -> None: ...
    def get_element_lo(self, element: str) -> float: ...
    def get_element_if(self, element: str) -> float: ...
    def calculate_el_if_fq(self, element: str, freq: float, **kw) -> float: ...


@runtime_checkable
class ProgramRunner(Protocol):
    """Contract for executing QUA programs."""

    def run_program(self, qua_prog: Any, n_total: int, **kw) -> Any: ...
    def simulate(self, program: Any, *, duration: int, **kw) -> Any: ...
    def halt_job(self) -> None: ...


@runtime_checkable
class ConfigEngine(Protocol):
    """Contract for hardware config loading/saving/patching."""

    def load_hardware(self, path: Any) -> None: ...
    def save_hardware(self, path: Any) -> None: ...
    def build_qm_config(self) -> dict: ...
    def apply_changes(self, **kw) -> None: ...


# ---------------------------------------------------------------------------
# Pulse Management
# ---------------------------------------------------------------------------
@runtime_checkable
class PulseManager(Protocol):
    """Contract for pulse/waveform lifecycle."""

    def add_waveform(self, name: str, kind: str, sample: Any, **kw) -> None: ...
    def add_pulse(self, name: str, op_type: str, length: int, I_wf: str, Q_wf: str, **kw) -> None: ...
    def burn_to_config(self, cfg: dict, **kw) -> dict: ...


# ---------------------------------------------------------------------------
# Device Management
# ---------------------------------------------------------------------------
@runtime_checkable
class DeviceController(Protocol):
    """Contract for external instrument management."""

    def get(self, name: str, connect: bool = True) -> Any: ...
    def apply(self, name: str, **settings: Any) -> None: ...
    def exists(self, name: str) -> bool: ...


# ---------------------------------------------------------------------------
# Experiment
# ---------------------------------------------------------------------------
@runtime_checkable
class Experiment(Protocol):
    """
    Contract for a single experiment type.

    Each experiment knows how to:
    1. Build its QUA program (returning a ``ProgramBuildResult``)
    2. Run it (via a ProgramRunner)
    3. Simulate it (via a ProgramRunner)
    4. Post-process results
    """

    @property
    def name(self) -> str: ...

    def build_program(self, **params: Any) -> Any: ...
    def simulate(self, sim_config: Any = None, **params: Any) -> Any: ...
    def run(self, **params: Any) -> Any: ...
    def process(self, raw_output: Any, **params: Any) -> Any: ...
