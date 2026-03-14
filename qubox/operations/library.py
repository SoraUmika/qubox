from __future__ import annotations

import math

from ..circuit import QuantumGate
from ..sequence.models import Operation


class OperationLibrary:
    """Calibration-aware semantic operations."""

    def __init__(self, session):
        self.session = session

    def _resolve_target(self, alias: str, *, role: str | None = None) -> str:
        return self.session.resolve_alias(alias, role_hint=role)

    def _clks(self, duration: int | float, *, unit: str = "clks") -> int:
        if unit == "clks":
            return int(duration)
        if unit == "ns":
            return max(int(round(float(duration) / 4.0)), 0)
        raise ValueError("Unsupported time unit; use 'clks' or 'ns'.")

    def x90(self, target: str, *, op: str = "x90") -> QuantumGate:
        return QuantumGate(
            kind="qubit_rotation",
            target=self._resolve_target(target, role="qubit"),
            params={"op": op, "angle": "pi/2", "family": "X90"},
            label=f"{target}:X90",
        )

    def x180(self, target: str, *, op: str = "x180") -> QuantumGate:
        return QuantumGate(
            kind="qubit_rotation",
            target=self._resolve_target(target, role="qubit"),
            params={"op": op, "angle": "pi", "family": "X180"},
            label=f"{target}:X180",
        )

    def y90(self, target: str, *, op: str = "y90") -> QuantumGate:
        return QuantumGate(
            kind="qubit_rotation",
            target=self._resolve_target(target, role="qubit"),
            params={"op": op, "angle": "pi/2", "family": "Y90"},
            label=f"{target}:Y90",
        )

    def y180(self, target: str, *, op: str = "y180") -> QuantumGate:
        return QuantumGate(
            kind="qubit_rotation",
            target=self._resolve_target(target, role="qubit"),
            params={"op": op, "angle": "pi", "family": "Y180"},
            label=f"{target}:Y180",
        )

    def virtual_z(self, target: str, *, phase: float) -> Operation:
        return Operation(
            kind="frame_update",
            target=self._resolve_target(target, role="qubit"),
            params={"phase": float(phase)},
            label=f"{target}:VirtualZ",
        )

    def wait(self, target: str, duration: int | float, *, unit: str = "clks") -> Operation:
        return Operation(
            kind="idle",
            target=self._resolve_target(target),
            duration_clks=self._clks(duration, unit=unit),
            label=f"{target}:Wait",
        )

    def measure(
        self,
        target: str,
        *,
        mode: str = "iq",
        operation: str = "readout",
        key: str | None = None,
    ) -> Operation:
        return Operation(
            kind="measure",
            target=self._resolve_target(target, role="readout"),
            params={"mode": mode, "operation": operation, "measure_key": key},
            label=f"{target}:Measure",
        )

    def play(
        self,
        target: str,
        *,
        operation: str,
        amplitude: float | None = None,
        duration_clks: int | None = None,
        detune: float | None = None,
    ) -> Operation:
        params = {"op": operation}
        if amplitude is not None:
            params["amplitude"] = float(amplitude)
        if detune is not None:
            params["detune"] = float(detune)
        return Operation(
            kind="play",
            target=self._resolve_target(target),
            params=params,
            duration_clks=duration_clks,
            label=f"{target}:Play[{operation}]",
        )

    def displacement(self, target: str, *, amp: float, phase: float = 0.0) -> QuantumGate:
        alpha = complex(float(amp) * math.cos(phase), float(amp) * math.sin(phase))
        return QuantumGate(
            kind="displacement",
            target=self._resolve_target(target, role="storage"),
            params={"alpha": alpha, "amp": float(amp), "phase": float(phase)},
            label=f"{target}:Displace",
        )

    def sqr(self, target: str, *, thetas, phis) -> QuantumGate:
        return QuantumGate(
            kind="sqr",
            target=self._resolve_target(target, role="storage"),
            params={"thetas": tuple(thetas), "phis": tuple(phis)},
            label=f"{target}:SQR",
        )

    def reset(
        self,
        target: str,
        *,
        mode: str = "passive",
        readout: str | None = None,
        threshold: float | str | None = None,
        max_attempts: int = 1,
        real_time: bool = False,
        operation: str = "readout",
        pi_op: str = "x180",
    ) -> Operation:
        qubit = self._resolve_target(target, role="qubit")
        if mode == "passive":
            return self.wait(qubit, self.session.get_thermalization_clks("qubit") or 0)

        readout_target = self._resolve_target(readout or "readout", role="readout")
        return Operation(
            kind="reset",
            target=(qubit, readout_target),
            params={
                "mode": mode,
                "threshold": threshold,
                "max_attempts": int(max_attempts),
                "real_time": bool(real_time),
                "operation": operation,
                "pi_op": pi_op,
            },
            tags=("reset", mode),
            label=f"{target}:Reset[{mode}]",
        )
