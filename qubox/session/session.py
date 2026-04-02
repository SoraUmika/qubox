from __future__ import annotations

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
    :attr:`legacy_session` when you need something not surfaced here.
    """

    legacy_session_cls = None

    def __init__(self, legacy_session):
        self._legacy = legacy_session
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
        if cls.legacy_session_cls is None:
            from qubox.experiments.session import SessionManager

            cls.legacy_session_cls = SessionManager
        legacy = cls.legacy_session_cls(
            sample_id=sample_id,
            cooldown_id=cooldown_id,
            registry_base=registry_base,
            simulation_mode=simulation_mode,
            **kwargs,
        )
        if connect:
            legacy.open()
        return cls(legacy)

    # ------------------------------------------------------------------
    # Direct sub-system properties (no forwarding / no deprecation)
    # ------------------------------------------------------------------

    @property
    def legacy_session(self):
        """The underlying ``SessionManager`` instance."""
        return self._legacy

    @property
    def backend(self):
        if self._backend is None:
            from ..backends.qm import QMRuntime

            self._backend = QMRuntime(self)
        return self._backend

    @property
    def hardware(self):
        """``HardwareController`` — element LO/IF/gain, QM instance."""
        return self._legacy.hardware

    @property
    def config_engine(self):
        """``ConfigEngine`` — load / save / build QM config dicts."""
        return self._legacy.config_engine

    @property
    def calibration(self):
        """``CalibrationStore`` — frequency, coherence, discrimination data."""
        return self._legacy.calibration

    @property
    def pulse_mgr(self):
        """``PulseOperationManager`` — pulse operation registry."""
        return self._legacy.pulse_mgr

    @property
    def runner(self):
        """``ProgramRunner`` — execute / simulate QUA programs."""
        return self._legacy.runner

    @property
    def devices(self):
        """``DeviceManager`` — external device lifecycle."""
        return self._legacy.devices

    @property
    def orchestrator(self):
        """``CalibrationOrchestrator`` — experiment → calibration pipeline."""
        return self._legacy.orchestrator

    @property
    def simulation_mode(self) -> bool:
        """True if this session was opened in simulation mode (no RF outputs)."""
        return self._legacy.simulation_mode

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> "Session":
        self._legacy.open()
        return self

    def close(self) -> None:
        self._legacy.close()

    # ------------------------------------------------------------------
    # Sequence / circuit builders
    # ------------------------------------------------------------------

    def sequence(self, name: str = "sequence", **metadata: Any) -> Sequence:
        return Sequence(name=name, metadata=dict(metadata))

    def circuit(self, name: str = "circuit", **metadata: Any) -> QuantumCircuit:
        return QuantumCircuit(name=name, metadata=dict(metadata))

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
        ctx = self._legacy.context_snapshot()
        hardware_elements = set((getattr(self._legacy.hardware, "elements", {}) or {}).keys())
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
        ctx = self._legacy.context_snapshot()
        if token in {"qubit.ge", "qb.ge", "q0.ge"}:
            return float(getattr(ctx, "qb_fq"))
        if token in {"qubit.ef", "qb.ef", "q0.ef"}:
            freqs = self._legacy.calibration.get_frequencies(self.resolve_alias("qubit", role_hint="qubit"))
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
        pulse = self._legacy.pulse_mgr.get_pulseOp_by_element_op(target, op, strict=False)
        if pulse is not None and getattr(pulse, "length", None) is not None:
            return int(pulse.length)
        return default

    def resolve_discrimination(self, readout: str):
        return self._legacy.calibration.get_discrimination(readout)

    def get_thermalization_clks(self, channel: str, default: int | None = None) -> int | None:
        return self._legacy.get_therm_clks(channel, default=default)

    # ------------------------------------------------------------------
    # Commonly-used delegations
    # ------------------------------------------------------------------

    def context_snapshot(self):
        """Return a ``DeviceMetadata`` snapshot from the calibration store."""
        return self._legacy.context_snapshot()

    @property
    def experiment_path(self) -> str:
        """Filesystem path for experiment artifacts."""
        return self._legacy.experiment_path

    @property
    def context(self):
        """Live context reference (mutable) from ``SessionManager``."""
        return self._legacy.context

    # ------------------------------------------------------------------
    # Catch-all delegation to SessionManager
    # ------------------------------------------------------------------

    def __getattr__(self, name: str):
        """Forward any remaining attribute access to the underlying SessionManager."""
        try:
            return getattr(self._legacy, name)
        except AttributeError:
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute {name!r}"
            ) from None
