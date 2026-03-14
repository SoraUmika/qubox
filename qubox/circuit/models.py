from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..sequence.models import Operation, Sequence


@dataclass(frozen=True)
class QuantumGate(Operation):
    """Circuit-friendly alias for gate-like operations."""


@dataclass
class QuantumCircuit:
    """Convenient gate-sequence view over the shared Sequence IR."""

    name: str = "circuit"
    gates: list[Operation] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add(self, gate: Operation) -> "QuantumCircuit":
        self.gates.append(gate)
        return self

    def add_gate(self, gate: Operation) -> "QuantumCircuit":
        return self.add(gate)

    def to_sequence(self) -> Sequence:
        return Sequence(
            name=self.name,
            operations=list(self.gates),
            metadata=dict(self.metadata),
        )

    def inspect(self) -> str:
        return self.to_sequence().inspect()
