"""Sweep strategies for the circuit compiler.

A ``SweepStrategy`` maps a sweep parameter name to a QUA application mode and
emits the appropriate QUA instructions at the top of each sweep loop iteration.

Built-in strategies cover the four common sweep types:

* **frequency** — calls ``update_frequency(target, var)``
* **amplitude** — stores the QUA variable for use by play lowerers via ``amp(var)``
* **wait** — stores the QUA variable for use by idle lowerers via ``wait(var, ...)``
* **phase** — calls ``frame_rotation_2pi(var, target)``

Custom experiments can register additional strategies via
:pymethod:`CircuitCompiler.register_sweep_strategy`.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SweepStrategy(Protocol):
    """Protocol for sweep-axis application strategies.

    Each strategy knows:

    * ``qua_type`` — the QUA variable type to declare (``"fixed"`` or ``"int"``).
    * ``apply()`` — emits QUA instructions at the top of the sweep loop body.
    """

    qua_type: str

    def apply(self, ctx: Any, qua_var: Any, target: str | None, parameter: str) -> None:
        """Emit QUA instructions to apply the sweep variable.

        Parameters
        ----------
        ctx:
            The compiler instance (satisfies :class:`CompilationContext`).
        qua_var:
            The declared QUA variable for this sweep axis.
        target:
            The resolved element name, or *None* if no target is available.
        parameter:
            The sweep parameter name (for tracing / diagnostics).
        """
        ...


# ---------------------------------------------------------------------------
# Built-in strategies
# ---------------------------------------------------------------------------

class FrequencySweepStrategy:
    """Emits ``update_frequency(target, var)`` each iteration."""

    qua_type = "int"

    def apply(self, ctx: Any, qua_var: Any, target: str | None, parameter: str) -> None:
        if target is None:
            return
        from qm.qua import update_frequency

        from .circuit_compiler import InstructionTraceEntry

        update_frequency(target, qua_var)
        ctx._trace.append(InstructionTraceEntry(
            op="update_frequency",
            target=target,
            params={"source": "sweep_axis", "parameter": parameter},
        ))


class AmplitudeSweepStrategy:
    """Stores the sweep variable for later use via ``amp(var)`` in play lowerers."""

    qua_type = "fixed"

    def apply(self, ctx: Any, qua_var: Any, target: str | None, parameter: str) -> None:
        ctx._sweep_amplitude_var = qua_var


class WaitSweepStrategy:
    """Stores the sweep variable for later use via ``wait(var, ...)`` in idle lowerers."""

    qua_type = "int"

    def apply(self, ctx: Any, qua_var: Any, target: str | None, parameter: str) -> None:
        ctx._sweep_wait_var = qua_var


class PhaseSweepStrategy:
    """Emits ``frame_rotation_2pi(var, target)`` each iteration."""

    qua_type = "fixed"

    def apply(self, ctx: Any, qua_var: Any, target: str | None, parameter: str) -> None:
        if target is None:
            return
        from qm.qua import frame_rotation_2pi

        from .circuit_compiler import InstructionTraceEntry

        frame_rotation_2pi(qua_var, target)
        ctx._trace.append(InstructionTraceEntry(
            op="frame_rotation_2pi",
            target=target,
            params={"source": "sweep_axis", "parameter": parameter},
        ))


# ---------------------------------------------------------------------------
# Parameter name → strategy classification
# ---------------------------------------------------------------------------

_PARAMETER_ALIASES: dict[str, str] = {}


def _normalize(name: str) -> str:
    return name.lower().replace("_", "").replace("-", "").replace(" ", "")


def _build_alias_table() -> dict[str, str]:
    """Build a lookup table mapping normalized parameter names to strategy keys."""
    table: dict[str, str] = {}
    for alias in ("frequency", "freq", "iffrequency", "iffreq", "rffrequency", "rffreq"):
        table[alias] = "frequency"
    for alias in ("amplitude", "gain", "amp", "power"):
        table[alias] = "amplitude"
    for alias in ("duration", "delay", "wait", "idletime", "waittime", "waitclks", "delayclks"):
        table[alias] = "wait"
    for alias in ("phase", "phi", "rotation", "framerotation"):
        table[alias] = "phase"
    return table


_PARAMETER_ALIASES = _build_alias_table()


def classify_sweep_parameter(parameter: str, *, custom_aliases: dict[str, str] | None = None) -> str:
    """Map a sweep parameter name to a strategy key.

    Returns ``"metadata_only"`` if no strategy matches.
    """
    norm = _normalize(parameter)
    if custom_aliases:
        hit = custom_aliases.get(norm)
        if hit is not None:
            return hit
    return _PARAMETER_ALIASES.get(norm, "metadata_only")


# ---------------------------------------------------------------------------
# Default strategy registry builder
# ---------------------------------------------------------------------------

def build_default_sweep_registry() -> dict[str, SweepStrategy]:
    """Return the default strategy-key → SweepStrategy mapping."""
    return {
        "frequency": FrequencySweepStrategy(),
        "amplitude": AmplitudeSweepStrategy(),
        "wait": WaitSweepStrategy(),
        "phase": PhaseSweepStrategy(),
    }
