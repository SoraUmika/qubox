"""Gate lowering protocol and compilation context.

The ``GateLowerer`` protocol defines the interface for pluggable gate-type
handlers.  Each lowerer receives a :class:`CompilationContext` (which exposes
the compiler surface needed for QUA emission) together with the gate to lower.

Built-in gate types (measure, idle, play, qubit_rotation, displacement, sqr,
frame_update) are registered automatically by :class:`CircuitCompiler`.
Custom experiments can add new gate types at runtime via
:pymethod:`CircuitCompiler.register_lowerer`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ..circuit_runner import Gate, MeasurementSchema
    from ..programs.measurement import StateRule


# ---------------------------------------------------------------------------
# CompilationContext — the compiler surface exposed to lowerers
# ---------------------------------------------------------------------------

@runtime_checkable
class CompilationContext(Protocol):
    """Surface that gate lowerers use to interact with the compiler.

    This is satisfied by :class:`CircuitCompiler` itself, so the compiler is
    passed directly — avoiding a heavyweight wrapper dataclass.
    """

    # -- read-only session state --
    attr: Any
    calibration: Any
    pulse_mgr: Any
    hw: Any

    # -- mutable compilation state --
    _trace: list[Any]
    _base_frequencies: dict[str, float]
    _current_if: dict[str, int]
    _resolved_state_rules: dict[str, Any]
    _post_processing_plan: list[dict[str, Any]]

    # -- helpers --
    def _resolve_param(self, gate: Any, name: str, value: Any, *, required: bool) -> Any: ...
    def _base_frequency_for(self, element: str) -> float: ...
    def _lo_frequency_for(self, element: str) -> float | None: ...
    def _emit_frequency_update(self, element: str, *, detune_hz: float = 0.0) -> None: ...
    def _resolve_target(self, target: str) -> str: ...
    def _validate_amplitude(self, value: float) -> None: ...
    def _configure_measure_macro(self, *, target: str, operation: str, drive_frequency: float) -> None: ...
    def _condition_expression(self, gate: Any, *, measurements: dict[str, Any]) -> Any: ...
    def _resolve_qubit_rotation_op(
        self, gate: Any, *, gate_index: int, target: str, resolved_params: dict[str, Any],
    ) -> tuple[Any, dict[str, Any]]: ...
    def _resolve_state_rule_metadata(self, gate: Any, *, runtime: Any) -> dict[str, Any]: ...


# ---------------------------------------------------------------------------
# GateLowerer — the pluggable gate handler protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class GateLowerer(Protocol):
    """Protocol for a single gate-type lowering handler.

    Implementations receive the full compilation context (the compiler) plus
    gate-specific arguments.  They emit QUA instructions and append to the
    compiler's trace / resolution lists.
    """

    def __call__(
        self,
        ctx: CompilationContext,
        gate: Any,
        *,
        gate_index: int,
        targets: tuple[str, ...],
        measurements: dict[str, Any],
        resolved_params: dict[str, Any],
    ) -> None:
        """Lower *gate* into QUA instructions.

        Parameters
        ----------
        ctx:
            The compiler instance (satisfies :class:`CompilationContext`).
        gate:
            The ``Gate`` to lower.
        gate_index:
            Position of the gate in the circuit gate list.
        targets:
            Resolved element names for the gate's targets.
        measurements:
            Map of measurement key → ``_MeasurementRuntime``.
        resolved_params:
            Dict to populate with :class:`ResolvedParameter` entries for the
            resolution report.
        """
        ...
