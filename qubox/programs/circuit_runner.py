from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any
from pathlib import Path

import numpy as np
from qm import generate_qua_script
from qm.qua import dual_demod

from . import api as cQED_programs
from .measurement import MeasureSpec, StateRule, build_readout_snapshot_from_macro
from .macros.measure import measureMacro
from .gate_tuning import GateTuningStore

_UNSET = object()


def _stable_payload(value: Any) -> Any:
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
    return json.dumps(_stable_payload(value), sort_keys=True, separators=(",", ":"), default=str)


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

    def validate(self) -> "MeasurementSchema":
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


@dataclass(frozen=True)
class ConditionalGate:
    gate: "Gate"
    condition: GateCondition
    tags: tuple[str, ...] = ()

    def to_gate(self) -> "Gate":
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

    def with_stable_gate_names(self) -> "QuantumCircuit":
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

    def draw_pulses(self, runner: "CircuitRunner", **kwargs):
        return runner.visualize_pulses(self, **kwargs)


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


class CircuitRunner:
    """Circuit-based compiler facade (simulator-first).

    This initial implementation intentionally compiles through the same
    program-builder layer used by legacy experiment flows, then validates
    physical fidelity via serialized QUA script comparison.
    """

    def __init__(self, session: Any):
        self.session = session
        store = getattr(session, "gate_tuning_store", None)
        self.gate_tuning_store = store if isinstance(store, GateTuningStore) else GateTuningStore()

    def _apply_gate_tuning(self, circuit: QuantumCircuit) -> QuantumCircuit:
        circuit = circuit.with_stable_gate_names()
        md = dict(circuit.metadata)
        applied: list[dict[str, Any]] = []

        qb_el = md.get("qb_el")
        op = md.get("op")
        if isinstance(qb_el, str) and isinstance(op, str):
            tuned = self.gate_tuning_store.resolve(target=qb_el, operation=op)
            if tuned is not None:
                md.setdefault("tuning", {})
                md["tuning"].update(tuned)
                applied.append(tuned)

        if applied:
            md["tuning_applied"] = applied
        return QuantumCircuit(name=circuit.name, gates=circuit.gates, metadata=md)

    def compile(self, circuit: QuantumCircuit, *, sweep: SweepSpec | None = None) -> CircuitBuildResult:
        circuit = self._apply_gate_tuning(circuit)
        name = circuit.name.lower().strip()
        if name == "power_rabi":
            return self._compile_power_rabi(circuit, sweep)
        if name == "t1":
            return self._compile_t1(circuit, sweep)
        if name == "readout_ge_discrimination":
            return self._compile_ge(circuit, sweep)
        if name == "readout_butterfly":
            return self._compile_butterfly(circuit, sweep)
        if name == "xy_pair":
            return self._compile_xy_pair(circuit, sweep)
        raise ValueError(f"Unsupported circuit name: {circuit.name!r}")

    def compile_program(self, circuit: QuantumCircuit, *, n_shots: int | None = None):
        from .circuit_compiler import CircuitCompiler

        return CircuitCompiler(self.session).compile(circuit, n_shots=n_shots)

    def compile_v2(self, circuit: QuantumCircuit, *, n_shots: int | None = None):
        """Deprecated alias for :meth:`compile_program`."""
        import warnings as _w

        _w.warn(
            "CircuitRunner.compile_v2() is deprecated — use compile_program() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.compile_program(circuit, n_shots=n_shots)

    def visualize_pulses(
        self,
        circuit: QuantumCircuit,
        *,
        sweep: SweepSpec | None = None,
        duration_ns: int = 4000,
        controllers: tuple[str, ...] = ("con1",),
        by_element: bool = True,
        zoom_ns: tuple[float, float] | None = None,
        save_path: str | None = None,
    ):
        import matplotlib.pyplot as plt

        runner = getattr(self.session, "runner", None)
        if runner is None:
            return self._visualize_pulses_from_timing_model(
                circuit,
                zoom_ns=zoom_ns,
                save_path=save_path,
            )

        build = self.compile(circuit, sweep=sweep)
        sim = runner.simulate(build.program, duration=duration_ns, plot=False, controllers=controllers)

        channel_data: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for ctrl in controllers:
            if ctrl not in sim:
                continue
            con = sim[ctrl]
            for name, arr in con.analog.items():
                fs = con.analog_sampling_rate.get(name, 1e9)
                t = (np.arange(len(arr)) / float(fs)) * 1e9
                channel_data[f"{ctrl}:{name}"] = (t, np.asarray(arr))

        if not channel_data:
            raise RuntimeError("No simulated analog channels available for pulse visualization.")

        groups: dict[str, list[str]] = {}
        for ch in channel_data:
            if by_element and ":" in ch:
                element = ch.split(":", 2)[-1].split(":")[0]
                groups.setdefault(element, []).append(ch)
            else:
                groups.setdefault("all", []).append(ch)

        fig, axes = plt.subplots(len(groups), 1, figsize=(11, max(3.0, 2.7 * len(groups))), sharex=True)
        if not isinstance(axes, np.ndarray):
            axes = np.array([axes])

        boundaries_ns = []
        cursor = 0.0
        for gate in circuit.with_stable_gate_names().gates:
            boundaries_ns.append((cursor, gate.instance_name or gate.name))
            cursor += float((gate.duration_clks or 0) * 4)

        for ax, (group, channels) in zip(axes, groups.items()):
            for ch in sorted(channels):
                t, y = channel_data[ch]
                ax.plot(t, y, label=ch, linewidth=1.2)
            for x, name in boundaries_ns:
                if x > 0:
                    ax.axvline(x, color="gray", linestyle="--", alpha=0.25)
                    ax.text(x, 0.95, name, transform=ax.get_xaxis_transform(), fontsize=7, rotation=90, va="top")
            ax.set_ylabel("Amplitude")
            ax.set_title(f"Element: {group}")
            ax.grid(alpha=0.25)
            ax.legend(fontsize=8, loc="upper right")

        axes[-1].set_xlabel("Time (ns)")
        if zoom_ns is not None:
            axes[-1].set_xlim(float(zoom_ns[0]), float(zoom_ns[1]))
        fig.suptitle(f"Compiled Pulse Visualization: {circuit.name}", y=1.02)
        fig.tight_layout()

        if save_path:
            out = Path(save_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(out)
        return fig

    def _visualize_pulses_from_timing_model(
        self,
        circuit: QuantumCircuit,
        *,
        zoom_ns: tuple[float, float] | None = None,
        save_path: str | None = None,
    ):
        import matplotlib.pyplot as plt

        pulse_mgr = getattr(self.session, "pulse_mgr", None)
        if pulse_mgr is None:
            raise RuntimeError("Session has no pulse manager for timing-model pulse visualization.")

        traces: dict[str, dict[str, list[float]]] = {}
        cursor_ns = 0
        boundaries: list[tuple[float, str]] = []

        for gate in circuit.with_stable_gate_names().gates:
            boundaries.append((float(cursor_ns), gate.instance_name or gate.name))
            target = gate.target if isinstance(gate.target, str) else (gate.target[0] if gate.target else "")
            op = str(gate.params.get("op", ""))

            duration_ns = int((gate.duration_clks or 0) * 4)
            i_wave: list[float] = []
            q_wave: list[float] = []

            if target and op:
                pulse = pulse_mgr.get_pulseOp_by_element_op(target, op, strict=False)
                if pulse is not None:
                    i_wave = list(np.asarray(getattr(pulse, "I_wf", []) or [], dtype=float))
                    q_wave = list(np.asarray(getattr(pulse, "Q_wf", []) or [], dtype=float))
                    tuned = self.gate_tuning_store.resolve(target=target, operation=op)
                    if tuned is not None:
                        scale = float(tuned.get("amplitude_scale", 1.0))
                        i_wave = [v * scale for v in i_wave]
                        q_wave = [v * scale for v in q_wave]
                    duration_ns = max(duration_ns, len(i_wave), len(q_wave))

            duration_ns = max(duration_ns, 4)
            if not i_wave:
                i_wave = [0.0] * duration_ns
            if not q_wave:
                q_wave = [0.0] * duration_ns

            if len(i_wave) < duration_ns:
                i_wave.extend([0.0] * (duration_ns - len(i_wave)))
            if len(q_wave) < duration_ns:
                q_wave.extend([0.0] * (duration_ns - len(q_wave)))

            elem = target or "global"
            traces.setdefault(elem, {"I": [], "Q": []})
            traces[elem]["I"].extend(i_wave)
            traces[elem]["Q"].extend(q_wave)

            cursor_ns += duration_ns

        if not traces:
            raise RuntimeError("No pulse traces available from timing model.")

        fig, axes = plt.subplots(len(traces), 1, figsize=(11, max(3.0, 2.7 * len(traces))), sharex=True)
        if not isinstance(axes, np.ndarray):
            axes = np.array([axes])

        for ax, (elem, comps) in zip(axes, sorted(traces.items())):
            t = np.arange(len(comps["I"]), dtype=float)
            ax.plot(t, np.asarray(comps["I"]), label=f"{elem}:I", linewidth=1.2)
            ax.plot(t, np.asarray(comps["Q"]), label=f"{elem}:Q", linewidth=1.2)
            for x, name in boundaries:
                if x > 0:
                    ax.axvline(x, color="gray", linestyle="--", alpha=0.25)
                    ax.text(x, 0.95, name, transform=ax.get_xaxis_transform(), fontsize=7, rotation=90, va="top")
            ax.set_ylabel("Amplitude")
            ax.set_title(f"Element: {elem} (compiled timing model)")
            ax.grid(alpha=0.25)
            ax.legend(fontsize=8, loc="upper right")

        axes[-1].set_xlabel("Time (ns)")
        if zoom_ns is not None:
            axes[-1].set_xlim(float(zoom_ns[0]), float(zoom_ns[1]))
        fig.suptitle(f"Compiled Pulse Visualization (timing-model fallback): {circuit.name}", y=1.02)
        fig.tight_layout()

        if save_path:
            out = Path(save_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(out)
        return fig

    def serialize(self, build: CircuitBuildResult) -> str:
        cfg = self.session.config_engine.build_qm_config()
        return generate_qua_script(build.program, cfg)

    @staticmethod
    def _maybe_snapshot() -> dict[str, Any] | None:
        try:
            return build_readout_snapshot_from_macro()
        except Exception:
            return None

    def _compile_power_rabi(self, circuit: QuantumCircuit, sweep: SweepSpec | None) -> CircuitBuildResult:
        params = dict(circuit.metadata)
        qb_el = params["qb_el"]
        op = params.get("op", "ge_ref_r180")
        qb_therm_clks = int(params["qb_therm_clks"])
        pulse_clock_len = int(params["pulse_clock_len"])
        truncate_clks = params.get("truncate_clks", None)
        n_avg = int(params["n_avg"])

        if sweep is None or not sweep.axes:
            raise ValueError("power_rabi requires one sweep axis for gains")
        gains = np.asarray(sweep.axes[0].values, dtype=float)
        tuning = params.get("tuning") or {}
        gain_scale = float(tuning.get("amplitude_scale", 1.0))
        gains = gains * gain_scale
        params["applied_gain_scale"] = gain_scale

        prog = cQED_programs.power_rabi(
            pulse_clock_len,
            gains,
            qb_therm_clks,
            op,
            truncate_clks,
            n_avg,
            qb_el=qb_el,
            bindings=getattr(self.session, "bindings", None),
            readout=self.session.readout_handle(),
        )
        snapshot = self._maybe_snapshot()
        return CircuitBuildResult(name="PowerRabi", program=prog, sweep=sweep, readout_snapshot=snapshot, metadata=params)

    def _compile_xy_pair(self, circuit: QuantumCircuit, sweep: SweepSpec | None) -> CircuitBuildResult:
        params = dict(circuit.metadata)
        qb_el = params["qb_el"]
        if "qb_therm_clks" not in params:
            raise ValueError(
                "CircuitRunner.xy_pair requires 'qb_therm_clks' in circuit metadata. "
                "Resolve it from calibration or pass it explicitly before compiling."
            )
        qb_therm_clks = int(params["qb_therm_clks"])
        n_avg = int(params.get("n_avg", 64))

        op_a = str(params.get("op_a", "x180"))
        op_b = str(params.get("op_b", "x90"))
        tuning = params.get("tuning") or {}
        params["applied_gain_scale"] = float(tuning.get("amplitude_scale", 1.0))

        prog = cQED_programs.all_xy(qb_el, [(op_a, op_b)], qb_therm_clks, n_avg, readout=self.session.readout_handle())
        snapshot = self._maybe_snapshot()
        return CircuitBuildResult(
            name="XYPair",
            program=prog,
            sweep=sweep or SweepSpec(averaging=n_avg),
            readout_snapshot=snapshot,
            metadata=params,
        )

    def _compile_t1(self, circuit: QuantumCircuit, sweep: SweepSpec | None) -> CircuitBuildResult:
        params = dict(circuit.metadata)
        qb_el = params["qb_el"]
        r180 = params.get("r180", "x180")
        qb_therm_clks = int(params["qb_therm_clks"])
        n_avg = int(params["n_avg"])

        if sweep is None or not sweep.axes:
            raise ValueError("t1 requires one sweep axis for wait cycles")
        wait_cycles = np.asarray(sweep.axes[0].values, dtype=int)

        prog = cQED_programs.T1_relaxation(
            r180,
            wait_cycles,
            qb_therm_clks,
            n_avg,
            qb_el=qb_el,
            bindings=getattr(self.session, "bindings", None),
            readout=self.session.readout_handle(),
        )
        snapshot = self._maybe_snapshot()
        return CircuitBuildResult(name="T1Relaxation", program=prog, sweep=sweep, readout_snapshot=snapshot, metadata=params)

    def _compile_ge(self, circuit: QuantumCircuit, sweep: SweepSpec | None) -> CircuitBuildResult:
        params = dict(circuit.metadata)
        ro_el = params["ro_el"]
        qb_el = params["qb_el"]
        measure_op = params["measure_op"]
        r180 = params.get("r180", "x180")
        qb_therm_clks = int(params["qb_therm_clks"])
        n_samples = int(params["n_samples"])
        drive_frequency = float(params["drive_frequency"])

        pulse_info = self.session.pulse_mgr.get_pulseOp_by_element_op(ro_el, measure_op, strict=False)
        if pulse_info is None:
            raise RuntimeError(f"Missing pulse mapping for ro_el={ro_el!r}, op={measure_op!r}")

        weight_mapping = pulse_info.int_weights_mapping or {}
        is_readout = (pulse_info.op == "readout")
        op_prefix = "" if is_readout else f"{pulse_info.op}_"
        default_keys = (f"{op_prefix}cos" if op_prefix else "cos", f"{op_prefix}sin" if op_prefix else "sin", f"{op_prefix}minus_sin" if op_prefix else "minus_sin")
        base_weight_keys = params.get("base_weight_keys") or default_keys
        cos_key, sin_key, m_sin_key = base_weight_keys

        if cos_key not in weight_mapping or sin_key not in weight_mapping or m_sin_key not in weight_mapping:
            raise RuntimeError(
                f"Integration weights not found for keys={base_weight_keys!r}. Available={sorted(weight_mapping.keys())}"
            )

        measureMacro.set_demodulator(dual_demod.full)
        measureMacro.set_pulse_op(
            pulse_info,
            active_op=measure_op,
            weights=[[cos_key, sin_key], [m_sin_key, cos_key]],
            weight_len=pulse_info.length,
        )
        measureMacro.set_drive_frequency(drive_frequency)

        prog = cQED_programs.iq_blobs(ro_el, qb_el, r180, qb_therm_clks, n_samples, bindings=getattr(self.session, "bindings", None), readout=self.session.readout_handle())
        snapshot = self._maybe_snapshot()
        return CircuitBuildResult(name="ReadoutGEDiscrimination", program=prog, sweep=sweep or SweepSpec(averaging=n_samples), readout_snapshot=snapshot, metadata=params)

    def _compile_butterfly(self, circuit: QuantumCircuit, sweep: SweepSpec | None) -> CircuitBuildResult:
        params = dict(circuit.metadata)
        qb_el = params["qb_el"]
        r180 = params.get("r180", "x180")
        n_samples = int(params["n_samples"])
        max_trials = int(params.get("M0_MAX_TRIALS", 16))
        prep_policy = str(params["prep_policy"])
        prep_kwargs = dict(params.get("prep_kwargs") or {})

        prog = cQED_programs.readout_butterfly_measurement(
            qb_el,
            r180,
            prep_policy,
            prep_kwargs,
            max_trials,
            n_samples,
            bindings=getattr(self.session, "bindings", None),
            readout=self.session.readout_handle(),
        )
        snapshot = self._maybe_snapshot()
        return CircuitBuildResult(name="ReadoutButterflyMeasurement", program=prog, sweep=sweep or SweepSpec(averaging=n_samples), readout_snapshot=snapshot, metadata=params)

    @staticmethod
    def _diff_scripts(legacy_script: str, new_script: str) -> dict[str, Any]:
        if legacy_script == new_script:
            return {"status": "identical", "notes": []}

        legacy_lines = [ln.rstrip() for ln in legacy_script.splitlines() if ln.strip()]
        new_lines = [ln.rstrip() for ln in new_script.splitlines() if ln.strip()]

        if len(legacy_lines) == len(new_lines) and sorted(legacy_lines) == sorted(new_lines):
            return {
                "status": "functionally_equivalent_with_timing_notes",
                "notes": ["Line ordering differs but statement multiset matches."],
            }

        return {
            "status": "behaviorally_different",
            "notes": [
                f"Legacy lines={len(legacy_lines)}, New lines={len(new_lines)}",
                "Instruction bodies differ beyond benign reorderings.",
            ],
        }


def make_power_rabi_circuit(*, qb_el: str, qb_therm_clks: int, pulse_clock_len: int, n_avg: int, op: str = "ge_ref_r180", truncate_clks: int | None = None, gains: np.ndarray | None = None) -> tuple[QuantumCircuit, SweepSpec]:
    gains = np.asarray(gains if gains is not None else np.linspace(-0.2, 0.2, 9), dtype=float)
    circuit = QuantumCircuit(
        name="power_rabi",
        gates=(
            Gate("play", target=qb_el, params={"op": op, "amp": "gain"}),
            Gate("measure", target="readout", params={"kind": "iq"}),
        ),
        metadata={
            "qb_el": qb_el,
            "qb_therm_clks": int(qb_therm_clks),
            "pulse_clock_len": int(pulse_clock_len),
            "n_avg": int(n_avg),
            "op": op,
            "truncate_clks": truncate_clks,
        },
    )
    sweep = SweepSpec(axes=(SweepAxis(key="gains", values=gains),), averaging=int(n_avg))
    return circuit, sweep


def make_t1_circuit(*, qb_el: str, qb_therm_clks: int, n_avg: int, waits_clks: np.ndarray, r180: str = "x180") -> tuple[QuantumCircuit, SweepSpec]:
    waits_clks = np.asarray(waits_clks, dtype=int)
    circuit = QuantumCircuit(
        name="t1",
        gates=(
            Gate("play", target=qb_el, params={"op": r180}),
            Gate("wait", target=qb_el, params={"clks": "delay"}),
            Gate("measure", target="readout", params={"kind": "iq"}),
        ),
        metadata={
            "qb_el": qb_el,
            "qb_therm_clks": int(qb_therm_clks),
            "n_avg": int(n_avg),
            "r180": r180,
        },
    )
    sweep = SweepSpec(axes=(SweepAxis(key="wait_cycles", values=waits_clks),), averaging=int(n_avg))
    return circuit, sweep


def make_ge_discrimination_circuit(*, ro_el: str, qb_el: str, measure_op: str, drive_frequency: float, qb_therm_clks: int, n_samples: int, r180: str = "x180", base_weight_keys: tuple[str, str, str] | None = None) -> tuple[QuantumCircuit, SweepSpec]:
    circuit = QuantumCircuit(
        name="readout_ge_discrimination",
        gates=(Gate("measure", target=ro_el, params={"kind": "discriminate"}),),
        metadata={
            "ro_el": ro_el,
            "qb_el": qb_el,
            "measure_op": measure_op,
            "drive_frequency": float(drive_frequency),
            "qb_therm_clks": int(qb_therm_clks),
            "n_samples": int(n_samples),
            "r180": r180,
            "base_weight_keys": base_weight_keys,
        },
    )
    return circuit, SweepSpec(axes=(), averaging=int(n_samples))


def make_butterfly_circuit(*, qb_el: str, n_samples: int, prep_policy: str, prep_kwargs: dict[str, Any], r180: str = "x180", max_trials: int = 16) -> tuple[QuantumCircuit, SweepSpec]:
    circuit = QuantumCircuit(
        name="readout_butterfly",
        gates=(Gate("measure", target="readout", params={"kind": "butterfly"}),),
        metadata={
            "qb_el": qb_el,
            "n_samples": int(n_samples),
            "prep_policy": prep_policy,
            "prep_kwargs": dict(prep_kwargs),
            "r180": r180,
            "M0_MAX_TRIALS": int(max_trials),
        },
    )
    return circuit, SweepSpec(axes=(), averaging=int(n_samples))


def make_xy_pair_circuit(
    *,
    qb_el: str,
    qb_therm_clks: int,
    n_avg: int = 64,
    op_a: str = "x180",
    op_b: str = "x90",
    name_a: str | None = None,
    name_b: str | None = None,
) -> tuple[QuantumCircuit, SweepSpec]:
    circuit = QuantumCircuit(
        name="xy_pair",
        gates=(
            Gate("X", target=qb_el, params={"family": "X", "op": op_a, "angle": "pi"}, duration_clks=16, instance_name=name_a),
            Gate("X", target=qb_el, params={"family": "X", "op": op_b, "angle": "pi/2"}, duration_clks=8, instance_name=name_b),
            Gate("measure", target="readout", params={"kind": "iq"}, duration_clks=8),
        ),
        metadata={
            "qb_el": qb_el,
            "qb_therm_clks": int(qb_therm_clks),
            "n_avg": int(n_avg),
            "op_a": op_a,
            "op_b": op_b,
        },
    )
    return circuit, SweepSpec(axes=(), averaging=int(n_avg))


IntentGate = Gate
Circuit = QuantumCircuit
