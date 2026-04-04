"""Built-in gate lowerers for the standard gate types.

Each class is a callable that satisfies the :class:`GateLowerer` protocol.
They delegate to the corresponding ``_lower_*`` method on the compiler,
keeping the existing (well-tested) implementation intact while making
the dispatch mechanism pluggable.
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Measurement lowerer
# ---------------------------------------------------------------------------

class MeasurementLowerer:
    """Lowers ``measure`` and ``measure_iq`` gates."""

    def __call__(
        self,
        ctx: Any,
        gate: Any,
        *,
        gate_index: int,
        targets: tuple[str, ...],
        measurements: dict[str, Any],
        resolved_params: dict[str, Any],
    ) -> None:
        ctx._lower_measure_gate(
            gate,
            gate_index=gate_index,
            targets=targets,
            measurements=measurements,
            resolved_params=resolved_params,
        )


# ---------------------------------------------------------------------------
# Idle / wait lowerer
# ---------------------------------------------------------------------------

class IdleLowerer:
    """Lowers ``idle`` and ``wait`` gates."""

    def __call__(
        self,
        ctx: Any,
        gate: Any,
        *,
        gate_index: int,
        targets: tuple[str, ...],
        measurements: dict[str, Any],
        resolved_params: dict[str, Any],
    ) -> None:
        ctx._lower_idle_gate(gate, targets=targets, resolved_params=resolved_params)


# ---------------------------------------------------------------------------
# Frame-update lowerer
# ---------------------------------------------------------------------------

class FrameUpdateLowerer:
    """Lowers ``frame_update`` gates (phase rotation, detuning, IF/RF set)."""

    def __call__(
        self,
        ctx: Any,
        gate: Any,
        *,
        gate_index: int,
        targets: tuple[str, ...],
        measurements: dict[str, Any],
        resolved_params: dict[str, Any],
    ) -> None:
        ctx._lower_frame_update(gate, targets=targets, resolved_params=resolved_params)


class BarrierLowerer:
    """Lowers ``align`` and ``barrier`` gates."""

    def __call__(
        self,
        ctx: Any,
        gate: Any,
        *,
        gate_index: int,
        targets: tuple[str, ...],
        measurements: dict[str, Any],
        resolved_params: dict[str, Any],
    ) -> None:
        ctx._lower_barrier(gate, targets=targets, resolved_params=resolved_params)


# ---------------------------------------------------------------------------
# Play-pulse lowerer
# ---------------------------------------------------------------------------

class PlayPulseLowerer:
    """Lowers ``play`` and ``play_pulse`` gates."""

    def __call__(
        self,
        ctx: Any,
        gate: Any,
        *,
        gate_index: int,
        targets: tuple[str, ...],
        measurements: dict[str, Any],
        resolved_params: dict[str, Any],
    ) -> None:
        ctx._lower_play_pulse(
            gate,
            target=targets[0],
            measurements=measurements,
            resolved_params=resolved_params,
        )


# ---------------------------------------------------------------------------
# Qubit-rotation lowerer
# ---------------------------------------------------------------------------

class QubitRotationLowerer:
    """Lowers ``qubit_rotation``, ``X``, and ``Y`` gates."""

    def __call__(
        self,
        ctx: Any,
        gate: Any,
        *,
        gate_index: int,
        targets: tuple[str, ...],
        measurements: dict[str, Any],
        resolved_params: dict[str, Any],
    ) -> None:
        ctx._lower_qubit_rotation(
            gate,
            gate_index=gate_index,
            target=targets[0],
            measurements=measurements,
            resolved_params=resolved_params,
        )


# ---------------------------------------------------------------------------
# Displacement lowerer
# ---------------------------------------------------------------------------

class DisplacementLowerer:
    """Lowers ``displacement`` gates (coherent-state preparation)."""

    def __call__(
        self,
        ctx: Any,
        gate: Any,
        *,
        gate_index: int,
        targets: tuple[str, ...],
        measurements: dict[str, Any],
        resolved_params: dict[str, Any],
    ) -> None:
        ctx._lower_displacement(gate, target=targets[0], resolved_params=resolved_params)


# ---------------------------------------------------------------------------
# SQR lowerer
# ---------------------------------------------------------------------------

class SQRLowerer:
    """Lowers ``sqr`` gates (selective qubit rotation)."""

    def __call__(
        self,
        ctx: Any,
        gate: Any,
        *,
        gate_index: int,
        targets: tuple[str, ...],
        measurements: dict[str, Any],
        resolved_params: dict[str, Any],
    ) -> None:
        ctx._lower_sqr(gate, target=targets[0], resolved_params=resolved_params)


# ---------------------------------------------------------------------------
# Default registry builder
# ---------------------------------------------------------------------------

def build_default_registry() -> dict[str, Any]:
    """Return the default gate-type → lowerer mapping.

    This is called once by :class:`CircuitCompiler.__init__` to populate the
    built-in registry.
    """
    measure = MeasurementLowerer()
    idle = IdleLowerer()
    frame = FrameUpdateLowerer()
    barrier = BarrierLowerer()
    play = PlayPulseLowerer()
    rotation = QubitRotationLowerer()
    displacement = DisplacementLowerer()
    sqr = SQRLowerer()

    return {
        "measure": measure,
        "measure_iq": measure,
        "idle": idle,
        "wait": idle,
        "align": barrier,
        "barrier": barrier,
        "frame_update": frame,
        "play": play,
        "play_pulse": play,
        "qubit_rotation": rotation,
        "X": rotation,
        "Y": rotation,
        "displacement": displacement,
        "sqr": sqr,
    }
