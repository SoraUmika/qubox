"""Pulse operation descriptor.

Moved from ``qubox.analysis.pulseOp`` during the analysis → qubox_tools merge.
The old import path is deprecated; use ``qubox.core.pulse_op.PulseOp``.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class PulseOp:
    """Light wrapper for the information you pass into register_pulse_op."""

    element: str
    op: str
    pulse: str | None = None
    type: str | None = None  # "control" / "measurement"
    length: int | None = None
    digital_marker: bool | str = True
    I_wf_name: str | None = None
    Q_wf_name: str | None = None
    I_wf: list[float] | float | None = None
    Q_wf: list[float] | float | None = None

    int_weights_mapping: dict[str, str] | str | None = None
    int_weights_defs: dict[str, tuple[float, float, int]] | None = None

    def to_dict(self) -> dict:
        """Canonical JSON / snapshot representation.

        NOTE: intentionally drops I_wf and Q_wf (these can be large and
        are reconstructable from names or not needed in configs).
        """
        d = asdict(self)
        d.pop("I_wf", None)
        d.pop("Q_wf", None)
        return d

    def __repr__(self) -> str:
        return f"PulseOp({self.to_dict()!r})"
