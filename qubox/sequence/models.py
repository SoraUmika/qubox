from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True)
class Condition:
    """Execution-time condition for a control operation."""

    measurement_key: str
    source: str = "state"
    comparator: str = "truthy"
    value: Any = True


@dataclass(frozen=True)
class Operation:
    """Semantic control intent."""

    kind: str
    target: str | tuple[str, ...]
    params: dict[str, Any] = field(default_factory=dict)
    duration_clks: int | None = None
    tags: tuple[str, ...] = ()
    condition: Condition | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    label: str | None = None

    @property
    def targets(self) -> tuple[str, ...]:
        if isinstance(self.target, str):
            return (self.target,)
        return tuple(self.target)

    def with_condition(self, condition: Condition) -> "Operation":
        return replace(self, condition=condition)

    def to_text_line(self, *, index: int) -> str:
        parts = [
            f"{index:02d}",
            self.label or self.kind,
            f"kind={self.kind}",
            f"targets={','.join(self.targets)}",
        ]
        if self.params:
            parts.append(f"params={self.params}")
        if self.duration_clks is not None:
            parts.append(f"duration_clks={int(self.duration_clks)}")
        if self.condition is not None:
            parts.append(
                "condition="
                f"{self.condition.measurement_key}.{self.condition.source}"
                f" {self.condition.comparator} {self.condition.value!r}"
            )
        if self.tags:
            parts.append(f"tags={','.join(self.tags)}")
        return " | ".join(parts)


@dataclass
class Sequence:
    """Ordered control body for custom experiments."""

    name: str = "sequence"
    operations: list[Operation] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add(self, operation: Operation) -> "Sequence":
        self.operations.append(operation)
        return self

    def extend(self, operations: list[Operation] | tuple[Operation, ...]) -> "Sequence":
        self.operations.extend(operations)
        return self

    def repeat(
        self,
        count: int,
        operations: list[Operation] | tuple[Operation, ...],
        *,
        label: str | None = None,
    ) -> "Sequence":
        if count < 1:
            raise ValueError("repeat() requires count >= 1.")
        tagged = list(operations)
        if label:
            tagged = [
                replace(op, tags=tuple(op.tags) + (f"repeat:{label}",))
                for op in tagged
            ]
        for _ in range(int(count)):
            self.operations.extend(tagged)
        return self

    def conditional(
        self,
        condition: Condition,
        operations: list[Operation] | tuple[Operation, ...],
        *,
        label: str | None = None,
    ) -> "Sequence":
        tagged = list(operations)
        if label:
            tagged = [
                replace(op, tags=tuple(op.tags) + (f"branch:{label}",))
                for op in tagged
            ]
        self.operations.extend(op.with_condition(condition) for op in tagged)
        return self

    def to_text(self) -> str:
        lines = [f"sequence: {self.name}"]
        for index, operation in enumerate(self.operations):
            lines.append(operation.to_text_line(index=index))
        return "\n".join(lines) + "\n"

    def to_control_program(
        self,
        *,
        sweep: SweepPlan | None = None,
        acquisition: AcquisitionSpec | None = None,
    ) -> ControlProgram:
        from ..control.adapters import sequence_to_control_program

        return sequence_to_control_program(self, sweep=sweep, acquisition=acquisition)

    def inspect(self) -> str:
        return self.to_text()
