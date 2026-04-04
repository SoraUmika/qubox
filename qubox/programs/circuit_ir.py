"""qubox.programs.circuit_ir — Intermediate Representation types for quantum circuits.

Extracted from ``circuit_runner.py`` to decouple IR definitions from the
compilation facade.  All public types are re-exported from ``circuit_runner``
for backward compatibility.

IR hierarchy::

    Gate  →  QuantumCircuit  →  CircuitCompiler  →  ProgramBuildResult
              ├─ MeasurementSchema (records: MeasurementRecord)
              │    └─ StreamSpec
              ├─ CircuitBlock
              └─ ConditionalGate

    ParameterSource  →  CalibrationReference
    SweepSpec        →  SweepAxis
    CircuitBuildResult
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from .measurement import StateRule

# ---------------------------------------------------------------------------
# Sentinel & helpers
# ---------------------------------------------------------------------------

_UNSET = object()


def _stable_payload(value: Any) -> Any:
    """Recursively convert IR objects to JSON-safe dicts with stable key order."""
    if isinstance(value, CalibrationReference):
        return {
            "namespace": value.namespace,
            "key": value.key,
            "field": value.field,
        }
    if isinstance(value, ParameterSource):
        payload: dict[str, Any] = {}
        if value.override is not _UNSET:
            payload["override"] = _stable_payload(value.override)
        if value.calibration is not None:
            payload["calibration"] = _stable_payload(value.calibration)
        if value.attr_fallback is not None:
            payload["attr_fallback"] = value.attr_fallback
        if value.default is not _UNSET:
            payload["default"] = _stable_payload(value.default)
        if value.required:
            payload["required"] = True
        return payload
    if isinstance(value, GateCondition):
        return {
            "measurement_key": value.measurement_key,
            "source": value.source,
            "comparator": value.comparator,
            "value": _stable_payload(value.value),
        }
    if isinstance(value, StreamSpec):
        return {
            "name": value.name,
            "qua_type": value.qua_type,
            "shape": list(value.shape),
            "aggregate": value.aggregate,
        }
    if isinstance(value, StateRule):
        return {
            "kind": value.kind,
            "threshold": _stable_payload(value.threshold),
            "sense": value.sense,
            "rotation_angle": _stable_payload(value.rotation_angle),
            "metadata": _stable_payload(value.metadata),
        }
    if isinstance(value, MeasurementRecord):
        return value.to_payload()
    if isinstance(value, MeasurementSchema):
        return value.to_payload()
    if isinstance(value, CircuitBlock):
        return {
            "label": value.label,
            "start": value.start,
            "stop": value.stop,
            "block_type": value.block_type,
            "lanes": list(value.lanes),
            "metadata": _stable_payload(value.metadata),
        }
    if isinstance(value, Gate):
        return {
            "gate_type": value.gate_type,
            "targets": list(value.targets),
            "params": _stable_payload(value.params),
            "duration_clks": value.duration_clks,
            "tags": list(value.tags),
            "instance_name": value.instance_name,
            "condition": _stable_payload(value.condition),
            "metadata": _stable_payload(value.metadata),
        }
    if isinstance(value, dict):
        return {str(k): _stable_payload(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_stable_payload(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


def _stable_text(value: Any) -> str:
    """JSON-serialize *value* through ``_stable_payload`` for deterministic text."""
    return json.dumps(_stable_payload(value), sort_keys=True, separators=(",", ":"), default=str)


# ---------------------------------------------------------------------------
# Parameter resolution
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CalibrationReference:
    namespace: str
    key: str
    field: str

    def path(self) -> str:
        parts = [self.namespace]
        if self.key:
            parts.append(self.key)
        parts.append(self.field)
        return ".".join(parts)


@dataclass(frozen=True)
class ParameterSource:
    calibration: CalibrationReference | None = None
    override: Any = _UNSET
    attr_fallback: str | None = None
    default: Any = _UNSET
    required: bool = False

    def has_override(self) -> bool:
        return self.override is not _UNSET

    def has_default(self) -> bool:
        return self.default is not _UNSET


# ---------------------------------------------------------------------------
# Gate conditions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GateCondition:
    measurement_key: str
    source: str = "state"
    comparator: str = "truthy"
    value: Any = True

    def to_text(self) -> str:
        if self.comparator == "truthy":
            return f"{self.measurement_key}.{self.source}"
        return f"{self.measurement_key}.{self.source} {self.comparator} {_stable_text(self.value)}"


# ---------------------------------------------------------------------------
# Stream & measurement
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StreamSpec:
    name: str
    qua_type: str = "fixed"
    shape: tuple[str | int, ...] = ("shots",)
    aggregate: str = "save_all"

    def shape_text(self) -> str:
        return "x".join(str(dim) for dim in self.shape) if self.shape else "scalar"


@dataclass(frozen=True)
class MeasurementRecord:
    key: str
    kind: str = "iq"
    operation: str = "readout"
    with_state: bool = False
    streams: tuple[StreamSpec, ...] = (
        StreamSpec(name="I", qua_type="fixed"),
        StreamSpec(name="Q", qua_type="fixed"),
    )
    state_rule: StateRule | None = None
    derived_state_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def stream(self, name: str) -> StreamSpec | None:
        for stream in self.streams:
            if stream.name == name:
                return stream
        return None

    def output_name(self, stream_name: str) -> str:
        return f"{self.key}.{stream_name}"

    def state_output_name(self) -> str | None:
        if self.state_rule is None and self.derived_state_name is None:
            return None
        return f"{self.key}.{self.derived_state_name or 'state'}"

    def to_payload(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind,
            "operation": self.operation,
            "with_state": self.with_state,
            "streams": [
                {
                    **_stable_payload(stream),
                    "output_name": self.output_name(stream.name),
                }
                for stream in self.streams
            ],
            "state_rule": _stable_payload(self.state_rule),
            "derived_state_name": self.derived_state_name,
            "derived_state_output": self.state_output_name(),
            "metadata": _stable_payload(self.metadata),
        }

    def to_text_line(self) -> str:
        streams = ", ".join(
            f"{stream.name}->{self.output_name(stream.name)}:{stream.qua_type}[{stream.shape_text()}]/{stream.aggregate}"
            for stream in self.streams
        )
        state_text = ""
        if self.state_rule is not None:
            state_name = self.derived_state_name or "state"
            state_text = (
                f" derive={state_name}->{self.state_output_name()}:{self.state_rule.kind}"
                f" threshold={_stable_text(self.state_rule.threshold)}"
                f" sense={self.state_rule.sense}"
            )
            if self.state_rule.rotation_angle is not None:
                state_text += f" rotation={_stable_text(self.state_rule.rotation_angle)}"
        elif self.with_state:
            state_text = " with_state"
        return (
            f"- {self.key}: kind={self.kind} op={self.operation}{state_text} "
            f"streams=[{streams}]"
        )


@dataclass(frozen=True)
class MeasurementSchema:
    records: tuple[MeasurementRecord, ...] = ()

    def get(self, key: str) -> MeasurementRecord | None:
        for record in self.records:
            if record.key == key:
                return record
        return None

    def to_text(self) -> str:
        if not self.records:
            return "measurement_schema: []"
        lines = ["measurement_schema:"]
        for record in self.records:
            lines.append(record.to_text_line())
        return "\n".join(lines)

    def to_payload(self) -> dict[str, Any]:
        return {
            "records": [record.to_payload() for record in self.records],
        }

    def validate(self) -> MeasurementSchema:
        seen_keys: set[str] = set()
        seen_outputs: set[str] = set()
        valid_stream_types = {"fixed", "bool", "int"}
        valid_aggregates = {"save", "save_all", "average"}

        for record in self.records:
            key = str(record.key or "").strip()
            if not key:
                raise ValueError("MeasurementSchema requires every record to have a non-empty key.")
            if key in seen_keys:
                raise ValueError(f"MeasurementSchema record keys must be unique; duplicate {key!r}.")
            seen_keys.add(key)

            if not record.streams:
                raise ValueError(f"MeasurementSchema record {key!r} must declare at least one stream.")

            local_names: set[str] = set()
            for stream in record.streams:
                stream_name = str(stream.name or "").strip()
                if not stream_name:
                    raise ValueError(f"MeasurementSchema record {key!r} has an empty stream name.")
                if stream_name in local_names:
                    raise ValueError(
                        f"MeasurementSchema record {key!r} contains duplicate stream name {stream_name!r}."
                    )
                local_names.add(stream_name)

                if stream.qua_type not in valid_stream_types:
                    raise ValueError(
                        f"MeasurementSchema record {key!r} stream {stream_name!r} has unsupported qua_type "
                        f"{stream.qua_type!r}."
                    )
                if stream.aggregate not in valid_aggregates:
                    raise ValueError(
                        f"MeasurementSchema record {key!r} stream {stream_name!r} has unsupported aggregate "
                        f"{stream.aggregate!r}."
                    )
                for dim in stream.shape:
                    if dim == "shots":
                        continue
                    if isinstance(dim, int) and dim > 0:
                        continue
                    raise ValueError(
                        f"MeasurementSchema record {key!r} stream {stream_name!r} has invalid shape "
                        f"dimension {dim!r}."
                    )

                output_name = record.output_name(stream_name)
                if output_name in seen_outputs:
                    raise ValueError(
                        f"MeasurementSchema output names must be unique; duplicate {output_name!r}."
                    )
                seen_outputs.add(output_name)

            if str(record.kind or "").strip().lower() == "iq":
                required = {"I", "Q"}
                missing = sorted(required - local_names)
                if missing:
                    raise ValueError(
                        f"MeasurementSchema IQ record {key!r} is missing required stream(s): {missing!r}."
                    )

            if record.derived_state_name is not None and record.state_rule is None:
                raise ValueError(
                    f"MeasurementSchema record {key!r} declares derived_state_name without a StateRule."
                )

            if record.with_state and not any(stream.qua_type == "bool" for stream in record.streams):
                raise ValueError(
                    f"MeasurementSchema record {key!r} claims a produced state output but exposes no bool stream."
                )

            derived_output = record.state_output_name()
            if derived_output is not None:
                if derived_output in seen_outputs:
                    raise ValueError(
                        f"MeasurementSchema derived-state output names must be unique; duplicate {derived_output!r}."
                    )
                seen_outputs.add(derived_output)

        return self


# ---------------------------------------------------------------------------
# Circuit structure
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConditionalGate:
    gate: Gate
    condition: GateCondition
    tags: tuple[str, ...] = ()

    def to_gate(self) -> Gate:
        merged_tags = tuple(self.gate.tags) + tuple(self.tags)
        return replace(self.gate, condition=self.condition, tags=merged_tags)


@dataclass(frozen=True)
class CircuitBlock:
    label: str
    start: int
    stop: int
    block_type: str = "protocol"
    lanes: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_text_line(self) -> str:
        lane_text = ",".join(self.lanes) if self.lanes else "<all>"
        mode = self.metadata.get("mode")
        mode_text = f" mode={mode}" if mode else ""
        return (
            f"- {self.label}: type={self.block_type} "
            f"gates=[{int(self.start):02d},{int(self.stop):02d}) lanes={lane_text}{mode_text}"
        )


@dataclass(frozen=True)
class Gate:
    name: str
    target: str | tuple[str, ...]
    params: dict[str, Any] = field(default_factory=dict)
    duration_clks: int | None = None
    tags: tuple[str, ...] = ()
    instance_name: str | None = None
    condition: GateCondition | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def gate_type(self) -> str:
        explicit = self.metadata.get("gate_type")
        if explicit:
            return str(explicit)
        return str(self.name)

    @property
    def targets(self) -> tuple[str, ...]:
        if isinstance(self.target, str):
            return (self.target,)
        return tuple(self.target)

    def param(self, key: str, default: Any = None) -> Any:
        return self.params.get(key, default)

    def resolved_name(self, *, index: int) -> str:
        if self.instance_name:
            return self.instance_name

        family = str(self.params.get("family") or self.gate_type).strip().replace(" ", "")
        family = family[:1].upper() + family[1:]

        op = str(self.params.get("op", "")).lower()
        angle = self.params.get("angle", None)
        alpha = self.params.get("alpha", None)

        if angle is not None:
            angle_token = f"theta{angle}"
        elif alpha is not None:
            angle_token = f"alpha{alpha}"
        elif op in {"x180", "y180"}:
            angle_token = "pi"
        elif op in {"x90", "y90", "xn90", "yn90"}:
            angle_token = "pi2"
        elif op:
            angle_token = op
        else:
            angle_token = "param"

        target = self.target if isinstance(self.target, str) else "-".join(self.target)
        target_token = str(target).replace(" ", "")
        return f"{family}_{angle_token}_{target_token}_{index}"

    def to_text_line(self, *, index: int) -> str:
        name = self.instance_name or self.resolved_name(index=index)
        parts = [
            f"{index:02d}",
            name,
            f"type={self.gate_type}",
            f"targets={','.join(self.targets)}",
        ]
        if self.params:
            parts.append(f"params={_stable_text(self.params)}")
        if self.duration_clks is not None:
            parts.append(f"duration_clks={int(self.duration_clks)}")
        if self.condition is not None:
            parts.append(f"condition={self.condition.to_text()}")
        if self.tags:
            parts.append(f"tags={','.join(self.tags)}")
        return " | ".join(parts)


@dataclass(frozen=True)
class QuantumCircuit:
    name: str
    gates: tuple[Gate, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    measurement_schema: MeasurementSchema = field(default_factory=MeasurementSchema)
    blocks: tuple[CircuitBlock, ...] = ()

    def with_stable_gate_names(self) -> QuantumCircuit:
        named = tuple(
            Gate(
                name=g.name,
                target=g.target,
                params=dict(g.params),
                duration_clks=g.duration_clks,
                tags=tuple(g.tags),
                instance_name=g.resolved_name(index=i),
                condition=g.condition,
                metadata=dict(g.metadata),
            )
            for i, g in enumerate(self.gates)
        )
        return QuantumCircuit(
            name=self.name,
            gates=named,
            metadata=dict(self.metadata),
            measurement_schema=self.measurement_schema,
            blocks=self.blocks,
        )

    def to_text(self) -> str:
        circuit = self.with_stable_gate_names()
        lines = [f"circuit: {circuit.name}"]
        for i, gate in enumerate(circuit.gates):
            lines.append(gate.to_text_line(index=i))
        if circuit.blocks:
            lines.append("blocks:")
            for block in circuit.blocks:
                lines.append(block.to_text_line())
        lines.append(circuit.measurement_schema.to_text())
        return "\n".join(lines) + "\n"

    def lane_names(self) -> tuple[str, ...]:
        lanes: list[str] = []
        for gate in self.with_stable_gate_names().gates:
            for target in gate.targets:
                if target not in lanes:
                    lanes.append(target)
        for block in self.blocks:
            for lane in block.lanes:
                if lane not in lanes:
                    lanes.append(lane)
        return tuple(lanes)

    def to_diagram_text(self, *, cell_width: int = 20) -> str:
        from .circuit_display import circuit_to_diagram_text

        return circuit_to_diagram_text(self, cell_width=cell_width)

    def draw(
        self,
        *,
        figsize: tuple[float, float] | None = None,
        save_path: str | None = None,
        include_gate_names: bool = False,
    ):
        from .circuit_display import draw_circuit

        return draw_circuit(
            self,
            figsize=figsize,
            save_path=save_path,
            include_gate_names=include_gate_names,
        )

    def display(
        self,
        *,
        figsize: tuple[float, float] | None = None,
        save_path: str | None = None,
        include_gate_names: bool = False,
    ):
        return self.draw(
            figsize=figsize,
            save_path=save_path,
            include_gate_names=include_gate_names,
        )

    def draw_logical(
        self,
        *,
        include_instance_name: bool = True,
        figsize: tuple[float, float] | None = None,
        save_path: str | None = None,
    ):
        return self.draw(
            figsize=figsize,
            save_path=save_path,
            include_gate_names=include_instance_name,
        )

    def draw_pulses(self, runner: Any, **kwargs: Any):
        return runner.visualize_pulses(self, **kwargs)


# ---------------------------------------------------------------------------
# Sweep & build result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SweepAxis:
    key: str
    values: np.ndarray


@dataclass(frozen=True)
class SweepSpec:
    axes: tuple[SweepAxis, ...] = ()
    averaging: int = 1


@dataclass(frozen=True)
class CircuitBuildResult:
    name: str
    program: Any
    sweep: SweepSpec
    readout_snapshot: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    "_UNSET",
    "_stable_payload",
    "_stable_text",
    "CalibrationReference",
    "CircuitBlock",
    "CircuitBuildResult",
    "ConditionalGate",
    "Gate",
    "GateCondition",
    "MeasurementRecord",
    "MeasurementSchema",
    "ParameterSource",
    "QuantumCircuit",
    "StreamSpec",
    "SweepAxis",
    "SweepSpec",
]
