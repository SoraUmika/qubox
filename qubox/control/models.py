from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any


def _stable_payload(value: Any) -> Any:
    if hasattr(value, "to_payload") and callable(value.to_payload):
        return value.to_payload()
    if isinstance(value, complex):
        return {"real": value.real, "imag": value.imag}
    if isinstance(value, dict):
        return {str(key): _stable_payload(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_stable_payload(item) for item in value]
    if hasattr(value, "tolist") and callable(value.tolist):
        try:
            return value.tolist()
        except Exception:
            return str(value)
    return value


def _stable_text(value: Any) -> str:
    return json.dumps(_stable_payload(value), sort_keys=True, separators=(",", ":"), default=str)


def _text_with_common_fields(
    *,
    parts: list[str],
    duration: ControlDuration | None,
    condition: ControlCondition | None,
    tags: tuple[str, ...],
    label: str | None,
    provenance: ProvenanceTag | None,
) -> str:
    if duration is not None:
        parts.append(f"duration={duration.to_text()}")
    if condition is not None:
        parts.append(f"condition={condition.to_text()}")
    if tags:
        parts.append(f"tags={','.join(tags)}")
    if label is not None:
        parts.append(f"label={label}")
    if provenance is not None:
        parts.append(f"source={provenance.to_text()}")
    return " | ".join(parts)


def _common_payload(
    *,
    duration: ControlDuration | None,
    condition: ControlCondition | None,
    tags: tuple[str, ...],
    label: str | None,
    metadata: dict[str, Any],
    provenance: ProvenanceTag | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "metadata": _stable_payload(metadata),
        "tags": list(tags),
        "label": label,
        "provenance": _stable_payload(provenance),
    }
    if duration is not None:
        payload["duration"] = duration.to_payload()
    if condition is not None:
        payload["condition"] = condition.to_payload()
    return payload


@dataclass(frozen=True)
class ControlDuration:
    value: Any
    unit: str = "clks"

    def to_payload(self) -> dict[str, Any]:
        return {"value": _stable_payload(self.value), "unit": self.unit}

    def to_text(self) -> str:
        return f"{_stable_text(self.value)} {self.unit}"


@dataclass(frozen=True)
class ControlCondition:
    measurement_key: str
    source: str = "state"
    comparator: str = "truthy"
    value: Any = True

    def to_payload(self) -> dict[str, Any]:
        return {
            "measurement_key": self.measurement_key,
            "source": self.source,
            "comparator": self.comparator,
            "value": _stable_payload(self.value),
        }

    def to_text(self) -> str:
        if self.comparator == "truthy":
            return f"{self.measurement_key}.{self.source}"
        return f"{self.measurement_key}.{self.source} {self.comparator} {_stable_text(self.value)}"


@dataclass(frozen=True)
class ProvenanceTag:
    source_type: str
    source_name: str
    source_index: int | None = None
    source_label: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "source_name": self.source_name,
            "source_index": self.source_index,
            "source_label": self.source_label,
            "metadata": _stable_payload(self.metadata),
        }

    def to_text(self) -> str:
        text = f"{self.source_type}:{self.source_name}"
        if self.source_index is not None:
            text += f"#{self.source_index}"
        if self.source_label:
            text += f"[{self.source_label}]"
        return text


@dataclass(frozen=True)
class ControlSweepAxis:
    parameter: str
    values: tuple[Any, ...]
    spacing: str = "custom"
    center: str | float | None = None
    unit: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "parameter": self.parameter,
            "values": _stable_payload(self.values),
            "spacing": self.spacing,
            "center": _stable_payload(self.center),
            "unit": self.unit,
            "metadata": _stable_payload(self.metadata),
        }

    def to_text(self) -> str:
        parts = [f"parameter={self.parameter}", f"values={_stable_text(self.values)}", f"spacing={self.spacing}"]
        if self.center is not None:
            parts.append(f"center={_stable_text(self.center)}")
        if self.unit is not None:
            parts.append(f"unit={self.unit}")
        return " | ".join(parts)


@dataclass(frozen=True)
class ControlSweepPlan:
    axes: tuple[ControlSweepAxis, ...] = ()
    averaging: int = 1

    def to_payload(self) -> dict[str, Any]:
        return {
            "axes": [_stable_payload(axis) for axis in self.axes],
            "averaging": self.averaging,
        }

    def to_text_lines(self) -> list[str]:
        lines = [f"averaging={self.averaging}"]
        for axis in self.axes:
            lines.append(f"- {axis.to_text()}")
        return lines


@dataclass(frozen=True)
class SemanticGateInstruction:
    gate_type: str
    targets: tuple[str, ...]
    params: dict[str, Any] = field(default_factory=dict)
    duration: ControlDuration | None = None
    condition: ControlCondition | None = None
    tags: tuple[str, ...] = ()
    label: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    provenance: ProvenanceTag | None = None

    @property
    def kind(self) -> str:
        return "semantic_gate"

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "kind": self.kind,
            "gate_type": self.gate_type,
            "targets": list(self.targets),
            "params": _stable_payload(self.params),
        }
        payload.update(
            _common_payload(
                duration=self.duration,
                condition=self.condition,
                tags=self.tags,
                label=self.label,
                metadata=self.metadata,
                provenance=self.provenance,
            )
        )
        return payload

    def to_text_line(self, *, index: int) -> str:
        parts = [
            f"{index:02d}",
            self.kind,
            f"gate_type={self.gate_type}",
            f"targets={','.join(self.targets)}",
        ]
        if self.params:
            parts.append(f"params={_stable_text(self.params)}")
        return _text_with_common_fields(
            parts=parts,
            duration=self.duration,
            condition=self.condition,
            tags=self.tags,
            label=self.label,
            provenance=self.provenance,
        )


@dataclass(frozen=True)
class PulseInstruction:
    targets: tuple[str, ...]
    operation: str | None = None
    amplitude: Any = None
    phase_rad: Any = None
    detuning_hz: Any = None
    duration: ControlDuration | None = None
    params: dict[str, Any] = field(default_factory=dict)
    condition: ControlCondition | None = None
    tags: tuple[str, ...] = ()
    label: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    provenance: ProvenanceTag | None = None

    @property
    def kind(self) -> str:
        return "pulse"

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "kind": self.kind,
            "targets": list(self.targets),
            "operation": self.operation,
            "amplitude": _stable_payload(self.amplitude),
            "phase_rad": _stable_payload(self.phase_rad),
            "detuning_hz": _stable_payload(self.detuning_hz),
            "params": _stable_payload(self.params),
        }
        payload.update(
            _common_payload(
                duration=self.duration,
                condition=self.condition,
                tags=self.tags,
                label=self.label,
                metadata=self.metadata,
                provenance=self.provenance,
            )
        )
        return payload

    def to_text_line(self, *, index: int) -> str:
        parts = [f"{index:02d}", self.kind, f"targets={','.join(self.targets)}"]
        if self.operation is not None:
            parts.append(f"operation={self.operation}")
        if self.amplitude is not None:
            parts.append(f"amplitude={_stable_text(self.amplitude)}")
        if self.phase_rad is not None:
            parts.append(f"phase_rad={_stable_text(self.phase_rad)}")
        if self.detuning_hz is not None:
            parts.append(f"detuning_hz={_stable_text(self.detuning_hz)}")
        if self.params:
            parts.append(f"params={_stable_text(self.params)}")
        return _text_with_common_fields(
            parts=parts,
            duration=self.duration,
            condition=self.condition,
            tags=self.tags,
            label=self.label,
            provenance=self.provenance,
        )


@dataclass(frozen=True)
class WaitInstruction:
    targets: tuple[str, ...]
    duration: ControlDuration
    condition: ControlCondition | None = None
    tags: tuple[str, ...] = ()
    label: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    provenance: ProvenanceTag | None = None

    @property
    def kind(self) -> str:
        return "wait"

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "kind": self.kind,
            "targets": list(self.targets),
        }
        payload.update(
            _common_payload(
                duration=self.duration,
                condition=self.condition,
                tags=self.tags,
                label=self.label,
                metadata=self.metadata,
                provenance=self.provenance,
            )
        )
        return payload

    def to_text_line(self, *, index: int) -> str:
        return _text_with_common_fields(
            parts=[f"{index:02d}", self.kind, f"targets={','.join(self.targets)}"],
            duration=self.duration,
            condition=self.condition,
            tags=self.tags,
            label=self.label,
            provenance=self.provenance,
        )


@dataclass(frozen=True)
class BarrierInstruction:
    targets: tuple[str, ...]
    tags: tuple[str, ...] = ()
    label: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    provenance: ProvenanceTag | None = None

    @property
    def kind(self) -> str:
        return "barrier"

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "kind": self.kind,
            "targets": list(self.targets),
        }
        payload.update(
            _common_payload(
                duration=None,
                condition=None,
                tags=self.tags,
                label=self.label,
                metadata=self.metadata,
                provenance=self.provenance,
            )
        )
        return payload

    def to_text_line(self, *, index: int) -> str:
        return _text_with_common_fields(
            parts=[f"{index:02d}", self.kind, f"targets={','.join(self.targets)}"],
            duration=None,
            condition=None,
            tags=self.tags,
            label=self.label,
            provenance=self.provenance,
        )


@dataclass(frozen=True)
class FrameUpdateInstruction:
    target: str
    phase_rad: Any
    condition: ControlCondition | None = None
    tags: tuple[str, ...] = ()
    label: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    provenance: ProvenanceTag | None = None

    @property
    def kind(self) -> str:
        return "frame_update"

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "kind": self.kind,
            "target": self.target,
            "phase_rad": _stable_payload(self.phase_rad),
        }
        payload.update(
            _common_payload(
                duration=None,
                condition=self.condition,
                tags=self.tags,
                label=self.label,
                metadata=self.metadata,
                provenance=self.provenance,
            )
        )
        return payload

    def to_text_line(self, *, index: int) -> str:
        return _text_with_common_fields(
            parts=[f"{index:02d}", self.kind, f"target={self.target}", f"phase_rad={_stable_text(self.phase_rad)}"],
            duration=None,
            condition=self.condition,
            tags=self.tags,
            label=self.label,
            provenance=self.provenance,
        )


@dataclass(frozen=True)
class FrequencyUpdateInstruction:
    target: str
    frequency_hz: Any
    condition: ControlCondition | None = None
    tags: tuple[str, ...] = ()
    label: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    provenance: ProvenanceTag | None = None

    @property
    def kind(self) -> str:
        return "frequency_update"

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "kind": self.kind,
            "target": self.target,
            "frequency_hz": _stable_payload(self.frequency_hz),
        }
        payload.update(
            _common_payload(
                duration=None,
                condition=self.condition,
                tags=self.tags,
                label=self.label,
                metadata=self.metadata,
                provenance=self.provenance,
            )
        )
        return payload

    def to_text_line(self, *, index: int) -> str:
        return _text_with_common_fields(
            parts=[
                f"{index:02d}",
                self.kind,
                f"target={self.target}",
                f"frequency_hz={_stable_text(self.frequency_hz)}",
            ],
            duration=None,
            condition=self.condition,
            tags=self.tags,
            label=self.label,
            provenance=self.provenance,
        )


@dataclass(frozen=True)
class AcquireInstruction:
    target: str
    mode: str = "iq"
    operation: str = "readout"
    key: str | None = None
    condition: ControlCondition | None = None
    tags: tuple[str, ...] = ()
    label: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    provenance: ProvenanceTag | None = None

    @property
    def kind(self) -> str:
        return "acquire"

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "kind": self.kind,
            "target": self.target,
            "mode": self.mode,
            "operation": self.operation,
            "key": self.key,
        }
        payload.update(
            _common_payload(
                duration=None,
                condition=self.condition,
                tags=self.tags,
                label=self.label,
                metadata=self.metadata,
                provenance=self.provenance,
            )
        )
        return payload

    def to_text_line(self, *, index: int) -> str:
        parts = [
            f"{index:02d}",
            self.kind,
            f"target={self.target}",
            f"mode={self.mode}",
            f"operation={self.operation}",
        ]
        if self.key is not None:
            parts.append(f"key={self.key}")
        return _text_with_common_fields(
            parts=parts,
            duration=None,
            condition=self.condition,
            tags=self.tags,
            label=self.label,
            provenance=self.provenance,
        )


ControlInstruction = (
    SemanticGateInstruction
    | PulseInstruction
    | WaitInstruction
    | BarrierInstruction
    | FrameUpdateInstruction
    | FrequencyUpdateInstruction
    | AcquireInstruction
)


@dataclass(frozen=True)
class ControlProgram:
    name: str = "control_program"
    instructions: tuple[ControlInstruction, ...] = ()
    sweep_plan: ControlSweepPlan = field(default_factory=ControlSweepPlan)
    metadata: dict[str, Any] = field(default_factory=dict)

    def append(self, instruction: ControlInstruction) -> "ControlProgram":
        return replace(self, instructions=self.instructions + (instruction,))

    def extend(self, instructions: tuple[ControlInstruction, ...] | list[ControlInstruction]) -> "ControlProgram":
        return replace(self, instructions=self.instructions + tuple(instructions))

    def has_acquire(self) -> bool:
        return any(isinstance(instruction, AcquireInstruction) for instruction in self.instructions)

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "instructions": [_stable_payload(instruction) for instruction in self.instructions],
            "sweep_plan": self.sweep_plan.to_payload(),
            "metadata": _stable_payload(self.metadata),
        }

    def to_text(self) -> str:
        lines = [f"control_program: {self.name}"]
        if self.sweep_plan.axes:
            lines.append("sweep_plan:")
            for line in self.sweep_plan.to_text_lines():
                lines.append(f"  {line}")
        for index, instruction in enumerate(self.instructions):
            lines.append(instruction.to_text_line(index=index))
        return "\n".join(lines) + "\n"

    def inspect(self) -> str:
        return self.to_text()