"""qubox.core.protocols — structural subtyping contracts for qubox subsystems.

Using ``typing.Protocol`` (structural subtyping) so implementations don't
need to inherit — they just need to have the right methods.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


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


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------
@runtime_checkable
class SessionProtocol(Protocol):
    """Minimal typed contract for a qubox session.

    Every experiment, template library, orchestrator, and backend should
    accept ``session: SessionProtocol`` instead of untyped ``ctx: Any``.
    The protocol captures the *intersection* of attributes that callers
    actually use, not the union of everything ``SessionManager`` exposes.
    """

    # -- Sub-system access --

    @property
    def hardware(self) -> Any: ...

    @property
    def config_engine(self) -> Any: ...

    @property
    def calibration(self) -> Any: ...

    @property
    def pulse_mgr(self) -> Any: ...

    @property
    def runner(self) -> Any: ...

    @property
    def devices(self) -> Any: ...

    @property
    def orchestrator(self) -> Any: ...

    @property
    def simulation_mode(self) -> bool: ...

    @property
    def experiment_path(self) -> str: ...

    # -- Context / snapshot --

    def context_snapshot(self) -> Any: ...

    # -- Resolution helpers --

    def resolve_alias(self, alias: str, *, role_hint: str | None = None) -> str: ...

    def resolve_center(self, center: str | float) -> float: ...

    def resolve_pulse_length(
        self, target: str, op: str, *, default: int | None,
    ) -> int | None: ...

    def resolve_discrimination(self, readout: str) -> Any: ...

    def get_thermalization_clks(
        self, channel: str, default: int | None = None,
    ) -> int | None: ...

    # -- Lifecycle --

    def connect(self) -> Any: ...

    def close(self) -> None: ...
