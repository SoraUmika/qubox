from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..circuit import QuantumCircuit
from ..sequence import Sequence, SweepAxis, SweepFactory, SweepPlan
from ..sequence.acquisition import AcquisitionFactory


class Session:
    """Canonical runtime entry point for the qubox API.

    Wraps the infrastructure ``SessionManager`` and exposes commonly needed
    sub-systems as direct properties.  There is **no** generic attribute
    forwarding — access the underlying ``SessionManager`` explicitly via
    :attr:`session_manager` when you need something not surfaced here.
    """

    session_manager_cls = None

    def __init__(self, session_manager):
        self._session_manager = session_manager
        self.sweep = SweepFactory()
        self.acquire = AcquisitionFactory()
        from ..experiments import ExperimentLibrary, WorkflowLibrary
        from ..operations import OperationLibrary

        self._backend = None
        self.ops = OperationLibrary(self)
        self.gates = self.ops
        self.exp = ExperimentLibrary(self)
        self.workflow = WorkflowLibrary(self)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def open(
        cls,
        *,
        sample_id: str,
        cooldown_id: str,
        registry_base: str | Path | None = None,
        simulation_mode: bool = True,
        connect: bool = True,
        **kwargs: Any,
    ) -> "Session":
        """Open a new Session.

        Parameters
        ----------
        simulation_mode:
            When *True* (the default), the session is opened without
            activating any hardware outputs.  ``hardware.open_qm()`` is
            skipped so no ``QuantumMachine`` instance is created and RF
            outputs are never enabled.  The QMM connection is still
            established, so ``experiment.simulate()`` works normally.  Any
            call to ``runner.run_program()`` raises ``JobError``.  Set to
            *False* to enable real hardware execution.
        """
        if cls.session_manager_cls is None:
            from qubox.experiments.session import SessionManager

            cls.session_manager_cls = SessionManager
        session_manager = cls.session_manager_cls(
            sample_id=sample_id,
            cooldown_id=cooldown_id,
            registry_base=registry_base,
            simulation_mode=simulation_mode,
            **kwargs,
        )
        if connect:
            session_manager.open()
        return cls(session_manager)

    # ------------------------------------------------------------------
    # Direct sub-system properties (no forwarding / no deprecation)
    # ------------------------------------------------------------------

    @property
    def session_manager(self):
        """The underlying ``SessionManager`` instance."""
        return self._session_manager

    @property
    def backend(self):
        if self._backend is None:
            from ..backends.qm import QMRuntime

            self._backend = QMRuntime(self)
        return self._backend

    @property
    def hardware(self):
        """``HardwareController`` — element LO/IF/gain, QM instance."""
        return self._session_manager.hardware

    @property
    def config_engine(self):
        """``ConfigEngine`` — load / save / build QM config dicts."""
        return self._session_manager.config_engine

    @property
    def calibration(self):
        """``CalibrationStore`` — frequency, coherence, discrimination data."""
        return self._session_manager.calibration

    @property
    def pulse_mgr(self):
        """``PulseOperationManager`` — pulse operation registry."""
        return self._session_manager.pulse_mgr

    @property
    def runner(self):
        """``ProgramRunner`` — execute / simulate QUA programs."""
        return self._session_manager.runner

    @property
    def devices(self):
        """``DeviceManager`` — external device lifecycle."""
        return self._session_manager.devices

    @property
    def orchestrator(self):
        """``CalibrationOrchestrator`` — experiment → calibration pipeline."""
        return self._session_manager.orchestrator

    @property
    def simulation_mode(self) -> bool:
        """True if this session was opened in simulation mode (no RF outputs)."""
        return self._session_manager.simulation_mode

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> "Session":
        self._session_manager.open()
        return self

    def close(self) -> None:
        self._session_manager.close()

    # ------------------------------------------------------------------
    # Sequence / circuit builders
    # ------------------------------------------------------------------

    def sequence(self, name: str = "sequence", **metadata: Any) -> Sequence:
        return Sequence(name=name, metadata=dict(metadata))

    def circuit(self, name: str = "circuit", **metadata: Any) -> QuantumCircuit:
        return QuantumCircuit(name=name, metadata=dict(metadata))

    def control_program(self, name: str = "control_program", **metadata: Any):
        from ..control import ControlProgram

        return ControlProgram(name=name, metadata=dict(metadata))

    def to_control_program(
        self,
        body: Any,
        *,
        sweep: Any = None,
        acquisition: Any = None,
    ):
        from ..control import ControlProgram

        if isinstance(body, ControlProgram):
            if sweep is not None or acquisition is not None:
                raise TypeError(
                    "Cannot apply sweep/acquisition overrides to an existing ControlProgram; "
                    "modify the program directly or pass a Sequence or QuantumCircuit."
                )
            return body

        converter = getattr(body, "to_control_program", None)
        if callable(converter):
            return converter(sweep=sweep, acquisition=acquisition)

        raise TypeError("Expected a Sequence, QuantumCircuit, or ControlProgram.")

    def realize_control_program(self, body: Any):
        from ..control import realize_control_program

        return realize_control_program(self, self.to_control_program(body))

    def ensure_sweep_plan(self, value, *, averaging: int = 1) -> SweepPlan:
        if value is None:
            return SweepPlan(axes=(), averaging=int(averaging))
        if isinstance(value, SweepPlan):
            return value
        if isinstance(value, SweepAxis):
            return SweepPlan(axes=(value,), averaging=int(averaging))
        raise TypeError("Expected a SweepAxis or SweepPlan.")

    # ------------------------------------------------------------------
    # Resolution helpers
    # ------------------------------------------------------------------

    def resolve_alias(self, alias: str, *, role_hint: str | None = None) -> str:
        alias_text = str(alias)
        ctx = self._session_manager.context_snapshot()
        hardware = getattr(self._session_manager, "hardware", getattr(self._session_manager, "hw", None))
        hardware_elements = set((getattr(hardware, "elements", {}) or {}).keys())
        if alias_text in hardware_elements:
            return alias_text

        lowered = alias_text.lower()
        if role_hint in {"qubit", "qb"} or lowered in {"qubit", "qb"} or lowered.startswith("q"):
            return str(getattr(ctx, "qb_el", alias_text) or alias_text)
        if role_hint in {"readout", "ro", "resonator"} or lowered in {"readout", "ro", "resonator"} or lowered.startswith("rr"):
            return str(getattr(ctx, "ro_el", alias_text) or alias_text)
        if role_hint in {"storage", "st"} or lowered in {"storage", "st"}:
            return str(getattr(ctx, "st_el", alias_text) or alias_text)
        return alias_text

    def resolve_center(self, center: str | float) -> float:
        if isinstance(center, (int, float)):
            return float(center)
        token = str(center).strip().lower()
        ctx = self._session_manager.context_snapshot()
        if token in {"qubit.ge", "qb.ge", "q0.ge"}:
            return float(getattr(ctx, "qb_fq"))
        if token in {"qubit.ef", "qb.ef", "q0.ef"}:
            freqs = self._session_manager.calibration.get_frequencies(self.resolve_alias("qubit", role_hint="qubit"))
            if freqs is not None and getattr(freqs, "ef_freq", None) is not None:
                return float(freqs.ef_freq)
            anh = float(getattr(ctx, "anharmonicity", 0.0) or 0.0)
            return float(getattr(ctx, "qb_fq")) + anh
        if token in {"readout", "resonator", "rr0", "rr0.ro"}:
            return float(getattr(ctx, "ro_fq"))
        if token in {"storage", "st", "storage.ge"}:
            return float(getattr(ctx, "st_fq"))
        raise KeyError(f"Unknown sweep center token: {center!r}")

    def resolve_pulse_length(self, target: str, op: str, *, default: int | None) -> int | None:
        pulse = self._session_manager.pulse_mgr.get_pulseOp_by_element_op(target, op, strict=False)
        if pulse is not None and getattr(pulse, "length", None) is not None:
            return int(pulse.length)
        return default

    def resolve_discrimination(self, readout: str):
        return self._session_manager.calibration.get_discrimination(readout)

    def get_thermalization_clks(self, channel: str, default: int | None = None) -> int | None:
        return self._session_manager.get_therm_clks(channel, default=default)

    # ------------------------------------------------------------------
    # Commonly-used delegations
    # ------------------------------------------------------------------

    def context_snapshot(self):
        """Return a ``DeviceMetadata`` snapshot from the calibration store."""
        return self._session_manager.context_snapshot()

    @property
    def experiment_path(self) -> str:
        """Filesystem path for experiment artifacts."""
        return self._session_manager.experiment_path

    @property
    def context(self):
        """Live context reference (mutable) from ``SessionManager``."""
        return self._session_manager.context

    @property
    def bindings(self):
        """``ExperimentBindings`` instance from ``SessionManager``."""
        return self._session_manager.bindings

    def save_pulses(self) -> None:
        """Persist pulse definitions to disk."""
        self._session_manager.save_pulses()

    def burn_pulses(self, *, include_volatile: bool = True) -> None:
        """Push registered pulses into the QM config dict."""
        self._session_manager.burn_pulses(include_volatile=include_volatile)

    def save_output(self, output: Any, tag: str) -> None:
        """Persist experiment output to disk."""
        self._session_manager.save_output(output, tag)

    def readout_handle(self, alias: str = "resonator", operation: str = "readout"):
        """Return the session's readout handle for program builders."""
        return self._session_manager.readout_handle(alias=alias, operation=operation)


@dataclass
class SessionFactory:
    """Pre-configured session factory for programmatic / agent workflows.

    Stores connection parameters once, then stamps out ``Session`` instances
    via :meth:`create` without requiring notebook globals or interactive setup.

    Example::

        factory = SessionFactory(
            sample_id="qubit_A",
            cooldown_id="cd_2026_04",
            registry_base="/data/registry",
            qop_ip="10.157.36.68",
            cluster_name="Cluster_2",
        )
        session = factory.create()                        # simulation
        session_hw = factory.create(simulation_mode=False) # hardware
    """

    sample_id: str
    cooldown_id: str
    registry_base: str | Path | None = None
    qop_ip: str | None = None
    cluster_name: str | None = None
    simulation_mode: bool = True
    connect: bool = True
    extra_kwargs: dict[str, Any] = field(default_factory=dict)

    def create(self, *, simulation_mode: bool | None = None, connect: bool | None = None, **overrides: Any) -> Session:
        """Create and return a new :class:`Session`.

        Parameters
        ----------
        simulation_mode : bool, optional
            Override the factory default.
        connect : bool, optional
            Override the factory default.
        **overrides
            Additional keyword arguments forwarded to ``Session.open``.
        """
        kwargs: dict[str, Any] = dict(self.extra_kwargs)
        if self.qop_ip is not None:
            kwargs.setdefault("qop_ip", self.qop_ip)
        if self.cluster_name is not None:
            kwargs.setdefault("cluster_name", self.cluster_name)
        kwargs.update(overrides)
        return Session.open(
            sample_id=self.sample_id,
            cooldown_id=self.cooldown_id,
            registry_base=self.registry_base,
            simulation_mode=simulation_mode if simulation_mode is not None else self.simulation_mode,
            connect=connect if connect is not None else self.connect,
            **kwargs,
        )
