from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from qm.qua import (
    align,
    amp,
    declare,
    declare_stream,
    fixed,
    for_,
    frame_rotation_2pi,
    play,
    program,
    save,
    stream_processing,
    update_frequency,
    wait,
)

from ..core.types import MAX_AMPLITUDE
from ..experiments.result import ProgramBuildResult
from ..gates.hardware.displacement import DisplacementHardware
from ..gates.hardware.qubit_rotation import QubitRotationHardware
from ..gates.hardware.sqr import SQRHardware
from ..programs.macros.measure import measureMacro
from ..programs.measurement import (
    MeasureSpec,
    StateRule,
    emit_measurement_spec,
    try_build_readout_snapshot_from_macro,
)
from ..tools.waveforms import drag_gaussian_pulse_waveforms
from .circuit_postprocess import build_state_derivation_processor
from .circuit_runner import (
    CalibrationReference,
    Gate,
    MeasurementRecord,
    MeasurementSchema,
    ParameterSource,
    QuantumCircuit,
    _UNSET,
    _stable_payload,
)


@dataclass(frozen=True)
class ResolvedParameter:
    value: Any
    source: str
    reference: str | None = None
    attr_fallback: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "value": _stable_payload(self.value),
            "source": self.source,
        }
        if self.reference is not None:
            payload["reference"] = self.reference
        if self.attr_fallback is not None:
            payload["attr_fallback"] = self.attr_fallback
        return payload


@dataclass(frozen=True)
class InstructionTraceEntry:
    op: str
    target: str | None = None
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {"op": self.op}
        if self.target is not None:
            payload["target"] = self.target
        if self.params:
            payload["params"] = _stable_payload(self.params)
        return payload


@dataclass(frozen=True)
class GateResolution:
    gate_index: int
    gate_name: str
    gate_type: str
    targets: tuple[str, ...]
    parameters: dict[str, ResolvedParameter] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_index": self.gate_index,
            "gate_name": self.gate_name,
            "gate_type": self.gate_type,
            "targets": list(self.targets),
            "parameters": {name: value.to_dict() for name, value in sorted(self.parameters.items())},
        }


@dataclass(frozen=True)
class ResolutionReport:
    circuit_name: str
    circuit_text: str
    gates: tuple[GateResolution, ...]
    trace: tuple[InstructionTraceEntry, ...]
    resolved_frequencies: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "circuit_name": self.circuit_name,
            "circuit_text": self.circuit_text,
            "resolved_frequencies": {key: float(value) for key, value in sorted(self.resolved_frequencies.items())},
            "gates": [gate.to_dict() for gate in self.gates],
            "trace": [entry.to_dict() for entry in self.trace],
        }

    def to_text(self) -> str:
        lines = [f"circuit: {self.circuit_name}"]
        lines.append("frequencies:")
        if self.resolved_frequencies:
            for element, freq in sorted(self.resolved_frequencies.items()):
                lines.append(f"- {element}: {freq:.12g}")
        else:
            lines.append("- <none>")
        lines.append("gates:")
        for gate in self.gates:
            lines.append(
                f"- [{gate.gate_index:02d}] {gate.gate_name} type={gate.gate_type} targets={','.join(gate.targets)}"
            )
            if gate.parameters:
                for key, value in sorted(gate.parameters.items()):
                    ref = f" ref={value.reference}" if value.reference else ""
                    fallback = f" fallback={value.attr_fallback}" if value.attr_fallback else ""
                    lines.append(
                        f"  {key}={_stable_payload(value.value)} source={value.source}{ref}{fallback}"
                    )
        lines.append("trace:")
        for entry in self.trace:
            target = f" target={entry.target}" if entry.target else ""
            params = f" params={_stable_payload(entry.params)}" if entry.params else ""
            lines.append(f"- {entry.op}{target}{params}")
        return "\n".join(lines) + "\n"


@dataclass
class _HardwareContextProxy:
    mgr: Any
    snapshot: Any

    def context_snapshot(self):
        return self.snapshot


@dataclass
class _MeasurementRuntime:
    record: MeasurementRecord
    variables: dict[str, Any]
    streams: dict[str, Any]

    def target_names(self) -> list[str]:
        out: list[str] = []
        for stream in self.record.streams:
            if stream.qua_type == "fixed":
                out.append(stream.name)
        return out


class CircuitRunnerV2:
    def __init__(self, session: Any):
        self.session = session
        self.attr = self._context_snapshot()
        self.calibration = getattr(session, "calibration", None)
        self.pulse_mgr = getattr(session, "pulse_mgr", getattr(session, "pulseOpMngr", None))
        self.hw = getattr(session, "hw", getattr(session, "quaProgMngr", None))
        if self.pulse_mgr is None:
            raise RuntimeError("CircuitRunnerV2 requires a pulse manager on the session context.")
        self._trace: list[InstructionTraceEntry] = []
        self._gate_resolutions: list[GateResolution] = []
        self._base_frequencies: dict[str, float] = {}
        self._current_if: dict[str, int] = {}
        self._resolved_state_rules: dict[str, StateRule] = {}
        self._post_processing_plan: list[dict[str, Any]] = []

    def compile(self, circuit: QuantumCircuit, *, n_shots: int | None = None) -> ProgramBuildResult:
        circuit = circuit.with_stable_gate_names()
        n_total = int(n_shots if n_shots is not None else circuit.metadata.get("n_shots", 1))
        if n_total <= 0:
            raise ValueError("CircuitRunnerV2 requires n_shots >= 1.")

        self._trace = []
        self._gate_resolutions = []
        self._base_frequencies = {}
        self._current_if = {}
        self._resolved_state_rules = {}
        self._post_processing_plan = []

        measurement_schema = self._normalize_measurement_schema(circuit)
        measurement_schema.validate()
        post_shot_wait_clks = int(circuit.metadata.get("post_shot_wait_clks", 0) or 0)

        with program() as prog:
            shot = declare(int)
            shot_stream = declare_stream()
            measurement_runtimes = self._declare_measurements(measurement_schema)

            with for_(shot, 0, shot < n_total, shot + 1):
                for index, gate in enumerate(circuit.gates):
                    self._lower_gate(
                        gate,
                        gate_index=index,
                        measurements=measurement_runtimes,
                    )
                if post_shot_wait_clks > 0:
                    wait(post_shot_wait_clks)
                    self._trace.append(
                        InstructionTraceEntry(
                            op="wait",
                            params={"duration_clks": post_shot_wait_clks},
                        )
                    )
                save(shot, shot_stream)

            with stream_processing():
                for runtime in measurement_runtimes.values():
                    for stream in runtime.record.streams:
                        node = runtime.streams[stream.name]
                        if stream.qua_type == "bool":
                            node = node.boolean_to_int()
                        for dim in self._resolve_shape(stream.shape, n_total=n_total):
                            node = node.buffer(dim)
                        output_name = runtime.record.output_name(stream.name)
                        if stream.aggregate == "average":
                            node.average().save(output_name)
                        elif stream.aggregate == "save":
                            node.save(output_name)
                        else:
                            node.save_all(output_name)
                shot_stream.save("iteration")

        report = ResolutionReport(
            circuit_name=circuit.name,
            circuit_text=circuit.to_text(),
            gates=tuple(self._gate_resolutions),
            trace=tuple(self._trace),
            resolved_frequencies=dict(self._base_frequencies),
        )
        flattened_sources = self._flatten_gate_sources(self._gate_resolutions)
        params = {
            "circuit_name": circuit.name,
            "n_shots": n_total,
            "circuit_text": circuit.to_text(),
            **dict(circuit.metadata),
        }
        metadata = {
            "circuit_text": circuit.to_text(),
            "diagram_text": circuit.to_diagram_text(),
            "measurement_schema": measurement_schema.to_payload(),
            "resolution_report": report.to_dict(),
            "resolution_report_text": report.to_text(),
            "instruction_trace": [entry.to_dict() for entry in report.trace],
            "display_blocks": _stable_payload(circuit.blocks),
            "post_processing": _stable_payload(self._post_processing_plan),
            "compiler_warnings": list(circuit.metadata.get("warnings", [])),
        }

        processors: tuple[Any, ...] = ()
        if self._resolved_state_rules:
            processors = (
                build_state_derivation_processor(
                    measurement_schema,
                    resolved_rules=self._resolved_state_rules,
                ),
            )

        return ProgramBuildResult(
            program=prog,
            n_total=n_total,
            processors=processors,
            experiment_name="CircuitRunnerV2",
            params=params,
            resolved_frequencies=dict(self._base_frequencies),
            resolved_parameter_sources=flattened_sources,
            builder_function="CircuitRunnerV2.compile",
            sweep_axes=None,
            measure_macro_state=self._measure_macro_state(),
            metadata=metadata,
        )

    def _context_snapshot(self):
        snapshot = getattr(self.session, "context_snapshot", None)
        if callable(snapshot):
            return snapshot()
        attr = getattr(self.session, "attributes", None)
        if attr is not None:
            return attr
        raise RuntimeError("CircuitRunnerV2 requires a context_snapshot() or attributes on the session.")

    def _normalize_measurement_schema(self, circuit: QuantumCircuit) -> MeasurementSchema:
        if circuit.measurement_schema.records:
            return circuit.measurement_schema

        records: list[MeasurementRecord] = []
        for gate in circuit.gates:
            if gate.gate_type not in {"measure", "measure_iq"}:
                continue
            key = str(gate.params.get("measure_key") or gate.instance_name or gate.resolved_name(index=len(records)))
            state_rule = gate.params.get("state_rule")
            derived_state_name = gate.params.get("derived_state_name")
            records.append(
                MeasurementRecord(
                    key=key,
                    kind=str(gate.params.get("kind", "iq")),
                    operation=str(gate.params.get("operation") or gate.params.get("op") or "readout"),
                    with_state=False,
                    streams=tuple(
                        self._default_stream(name=name, qua_type=qua_type)
                        for name, qua_type in (("I", "fixed"), ("Q", "fixed"))
                    ),
                    state_rule=state_rule if isinstance(state_rule, StateRule) else None,
                    derived_state_name=str(derived_state_name) if derived_state_name is not None else None,
                )
            )
        return MeasurementSchema(records=tuple(records))

    def _default_stream(self, *, name: str, qua_type: str):
        from .circuit_runner import StreamSpec

        return StreamSpec(name=name, qua_type=qua_type, shape=("shots",), aggregate="save_all")

    def _declare_measurements(self, schema: MeasurementSchema) -> dict[str, _MeasurementRuntime]:
        runtimes: dict[str, _MeasurementRuntime] = {}
        for record in schema.records:
            variables: dict[str, Any] = {}
            streams: dict[str, Any] = {}
            for stream in record.streams:
                if stream.qua_type == "fixed":
                    variables[stream.name] = declare(fixed)
                elif stream.qua_type == "bool":
                    variables[stream.name] = declare(bool)
                else:
                    variables[stream.name] = declare(int)
                streams[stream.name] = declare_stream()
            runtimes[record.key] = _MeasurementRuntime(
                record=record,
                variables=variables,
                streams=streams,
            )
        return runtimes

    def _resolve_shape(self, shape: tuple[str | int, ...], *, n_total: int) -> list[int]:
        dims: list[int] = []
        for dim in shape:
            if dim == "shots":
                dims.append(int(n_total))
            elif isinstance(dim, str):
                raise ValueError(f"Unsupported symbolic stream dimension: {dim!r}")
            else:
                dims.append(int(dim))
        return dims

    def _lower_gate(self, gate: Gate, *, gate_index: int, measurements: dict[str, _MeasurementRuntime]) -> None:
        resolved_params: dict[str, ResolvedParameter] = {}
        targets = tuple(self._resolve_target(target) for target in gate.targets)
        gate_type = gate.gate_type

        if gate_type in {"measure", "measure_iq"}:
            self._lower_measure_gate(
                gate,
                gate_index=gate_index,
                targets=targets,
                measurements=measurements,
                resolved_params=resolved_params,
            )
        elif gate_type in {"idle", "wait"}:
            self._lower_idle_gate(gate, targets=targets, resolved_params=resolved_params)
        elif gate_type == "frame_update":
            self._lower_frame_update(gate, targets=targets, resolved_params=resolved_params)
        elif gate_type in {"play", "play_pulse"}:
            self._lower_play_pulse(
                gate,
                target=targets[0],
                measurements=measurements,
                resolved_params=resolved_params,
            )
        elif gate_type in {"qubit_rotation", "X", "Y"}:
            self._lower_qubit_rotation(
                gate,
                gate_index=gate_index,
                target=targets[0],
                measurements=measurements,
                resolved_params=resolved_params,
            )
        elif gate_type == "displacement":
            self._lower_displacement(gate, target=targets[0], resolved_params=resolved_params)
        elif gate_type == "sqr":
            self._lower_sqr(gate, target=targets[0], resolved_params=resolved_params)
        else:
            raise ValueError(f"Unsupported intent gate type: {gate_type!r}")

        self._gate_resolutions.append(
            GateResolution(
                gate_index=gate_index,
                gate_name=gate.instance_name or gate.resolved_name(index=gate_index),
                gate_type=gate.gate_type,
                targets=targets,
                parameters=resolved_params,
            )
        )

    def _lower_measure_gate(
        self,
        gate: Gate,
        *,
        gate_index: int,
        targets: tuple[str, ...],
        measurements: dict[str, _MeasurementRuntime],
        resolved_params: dict[str, ResolvedParameter],
    ) -> None:
        target = targets[0]
        key = str(gate.params.get("measure_key") or gate.instance_name or gate.resolved_name(index=gate_index))
        runtime = measurements.get(key)
        if runtime is None:
            raise ValueError(f"Measurement gate {key!r} has no matching measurement schema entry.")

        operation = str(gate.params.get("operation") or gate.params.get("op") or runtime.record.operation)
        drive_frequency = self._base_frequency_for(target)
        resolved_params["operation"] = ResolvedParameter(value=operation, source="override")
        resolved_params["drive_frequency"] = ResolvedParameter(value=drive_frequency, source="calibration")

        self._configure_measure_macro(target=target, operation=operation, drive_frequency=drive_frequency)
        align()

        measure_spec = MeasureSpec(kind=str(gate.params.get("kind", runtime.record.kind)))
        target_vars = [runtime.variables[name] for name in runtime.target_names()]
        emit_measurement_spec(
            measure_spec,
            targets=target_vars if target_vars else None,
            with_state=False,
            state=None,
        )
        for stream_name, qua_var in runtime.variables.items():
            save(qua_var, runtime.streams[stream_name])

        self._trace.append(
            InstructionTraceEntry(
                op="measure",
                target=target,
                params={
                    "measure_key": key,
                    "operation": operation,
                    "kind": measure_spec.kind,
                    "with_state": False,
                    "streams": [runtime.record.output_name(stream.name) for stream in runtime.record.streams],
                },
            )
        )
        state_params = self._resolve_state_rule_metadata(
            gate,
            runtime=runtime,
        )
        resolved_params.update(state_params)

    def _resolve_state_rule_metadata(
        self,
        gate: Gate,
        *,
        runtime: _MeasurementRuntime,
    ) -> dict[str, ResolvedParameter]:
        if runtime.record.state_rule is None:
            return {}

        rule = runtime.record.state_rule
        derived_name = runtime.record.derived_state_name or "state"
        resolved: dict[str, ResolvedParameter] = {
            f"{derived_name}.kind": ResolvedParameter(value=rule.kind, source="override"),
            f"{derived_name}.sense": ResolvedParameter(value=rule.sense, source="override"),
        }

        threshold = self._resolve_param(gate, f"{derived_name}.threshold", rule.threshold, required=True)
        resolved[f"{derived_name}.threshold"] = threshold

        rotation_value = 0.0
        if rule.rotation_angle is not None:
            rotation = self._resolve_param(
                gate,
                f"{derived_name}.rotation_angle",
                rule.rotation_angle,
                required=False,
            )
            resolved[f"{derived_name}.rotation_angle"] = rotation
            rotation_value = float(rotation.value if rotation.value is not None else 0.0)

        self._resolved_state_rules[runtime.record.key] = StateRule(
            kind=rule.kind,
            threshold=float(threshold.value),
            sense=str(rule.sense or "greater"),
            rotation_angle=rotation_value if rule.rotation_angle is not None else None,
            metadata=dict(rule.metadata),
        )
        self._post_processing_plan.append(
            {
                "op": "derive_state",
                "measure_key": runtime.record.key,
                "input_streams": [
                    runtime.record.output_name("I"),
                    runtime.record.output_name("Q"),
                ],
                "output": runtime.record.state_output_name(),
                "rule": _stable_payload(self._resolved_state_rules[runtime.record.key]),
                "timing": "post_run_analysis",
            }
        )
        return resolved

    def _lower_idle_gate(
        self,
        gate: Gate,
        *,
        targets: tuple[str, ...],
        resolved_params: dict[str, ResolvedParameter],
    ) -> None:
        duration = gate.duration_clks
        if duration is None:
            resolved = self._resolve_param(
                gate,
                "duration_clks",
                gate.params.get("duration_clks"),
                required=True,
            )
            duration = int(resolved.value)
            resolved_params["duration_clks"] = resolved
        else:
            resolved_params["duration_clks"] = ResolvedParameter(value=int(duration), source="override")
        if int(duration) < 0:
            raise ValueError("Idle duration must be >= 0 clock cycles.")
        if int(duration) > 0:
            wait(int(duration), *targets)
            self._trace.append(
                InstructionTraceEntry(
                    op="wait",
                    target=",".join(targets),
                    params={"duration_clks": int(duration)},
                )
            )

    def _lower_frame_update(
        self,
        gate: Gate,
        *,
        targets: tuple[str, ...],
        resolved_params: dict[str, ResolvedParameter],
    ) -> None:
        did_anything = False

        if gate.params.get("phase") is not None:
            phase = self._resolve_param(
                gate,
                "phase",
                gate.params.get("phase"),
                required=True,
            )
            resolved_params["phase"] = phase
            turns = float(phase.value) / (2.0 * math.pi)
            for target in targets:
                frame_rotation_2pi(turns, target)
                self._trace.append(
                    InstructionTraceEntry(
                        op="frame_rotation_2pi",
                        target=target,
                        params={"turns": turns},
                    )
                )
            did_anything = True

        detune = gate.params.get("detune")
        if detune is not None:
            detune_resolved = self._resolve_param(gate, "detune", detune, required=False)
            resolved_params["detune"] = detune_resolved
            if detune_resolved.value is not None:
                for target in targets:
                    self._emit_frequency_update(target, detune_hz=float(detune_resolved.value))
                did_anything = True

        if gate.params.get("rf_hz") is not None:
            rf_hz = self._resolve_param(gate, "rf_hz", gate.params.get("rf_hz"), required=True)
            resolved_params["rf_hz"] = rf_hz
            for target in targets:
                lo = self._lo_frequency_for(target)
                if lo is None:
                    raise ValueError(f"Cannot lower rf_hz frame update for {target!r} without a known LO.")
                target_if = int(round(float(rf_hz.value) - float(lo)))
                update_frequency(target, target_if)
                self._current_if[target] = target_if
                self._trace.append(
                    InstructionTraceEntry(
                        op="update_frequency",
                        target=target,
                        params={"if_hz": target_if, "rf_hz": float(rf_hz.value)},
                    )
                )
            did_anything = True

        if gate.params.get("if_hz") is not None:
            if_hz = self._resolve_param(gate, "if_hz", gate.params.get("if_hz"), required=True)
            resolved_params["if_hz"] = if_hz
            for target in targets:
                update_frequency(target, int(if_hz.value))
                self._current_if[target] = int(if_hz.value)
                self._trace.append(
                    InstructionTraceEntry(
                        op="update_frequency",
                        target=target,
                        params={"if_hz": int(if_hz.value)},
                    )
                )
            did_anything = True

        if not did_anything:
            raise ValueError("FrameUpdate requires at least one of phase, detune, rf_hz, or if_hz.")

    def _lower_play_pulse(
        self,
        gate: Gate,
        *,
        target: str,
        measurements: dict[str, _MeasurementRuntime],
        resolved_params: dict[str, ResolvedParameter],
    ) -> None:
        op = self._resolve_param(gate, "op", gate.params.get("op") or gate.params.get("operation"), required=True)
        resolved_params["op"] = op
        operation_handle: Any = str(op.value)
        play_kwargs: dict[str, Any] = {}

        amplitude = gate.params.get("amplitude")
        if amplitude is not None:
            amp_resolved = self._resolve_param(gate, "amplitude", amplitude, required=True)
            self._validate_amplitude(float(amp_resolved.value))
            resolved_params["amplitude"] = amp_resolved
            operation_handle = str(op.value) * amp(float(amp_resolved.value))

        duration_value = gate.duration_clks if gate.duration_clks is not None else gate.params.get("duration_clks")
        if duration_value is not None:
            duration = self._resolve_param(gate, "duration_clks", duration_value, required=True)
            resolved_params["duration_clks"] = duration
            play_kwargs["duration"] = int(duration.value)

        detune = gate.params.get("detune")
        if detune is not None:
            detune_resolved = self._resolve_param(gate, "detune", detune, required=False)
            resolved_params["detune"] = detune_resolved
            if detune_resolved.value is not None:
                self._emit_frequency_update(target, detune_hz=float(detune_resolved.value))

        condition = self._condition_expression(gate, measurements=measurements)
        if condition is None:
            play(operation_handle, target, **play_kwargs)
        else:
            play(operation_handle, target, condition=condition, **play_kwargs)
        self._trace.append(
            InstructionTraceEntry(
                op="play",
                target=target,
                params={
                    "operation": str(operation_handle),
                    **play_kwargs,
                    **(
                        {"amplitude": resolved_params["amplitude"].value}
                        if "amplitude" in resolved_params
                        else {}
                    ),
                    **({"condition": gate.condition.to_text()} if gate.condition is not None else {}),
                },
            )
        )

    def _lower_qubit_rotation(
        self,
        gate: Gate,
        *,
        gate_index: int,
        target: str,
        measurements: dict[str, _MeasurementRuntime],
        resolved_params: dict[str, ResolvedParameter],
    ) -> None:
        op_handle, play_kwargs = self._resolve_qubit_rotation_op(
            gate,
            gate_index=gate_index,
            target=target,
            resolved_params=resolved_params,
        )
        condition = self._condition_expression(gate, measurements=measurements)
        if condition is None:
            play(op_handle, target, **play_kwargs)
        else:
            play(op_handle, target, condition=condition, **play_kwargs)
        self._trace.append(
            InstructionTraceEntry(
                op="play",
                target=target,
                params={
                    "operation": str(op_handle),
                    **play_kwargs,
                    **(
                        {"amplitude": resolved_params["amplitude"].value}
                        if "amplitude" in resolved_params
                        else {}
                    ),
                    **({"condition": gate.condition.to_text()} if gate.condition is not None else {}),
                },
            )
        )

    def _lower_displacement(
        self,
        gate: Gate,
        *,
        target: str,
        resolved_params: dict[str, ResolvedParameter],
    ) -> None:
        alpha = self._resolve_param(gate, "alpha", gate.params.get("alpha"), required=True)
        resolved_params["alpha"] = alpha
        hardware = DisplacementHardware(alpha=complex(alpha.value), target=target)
        hardware.build(hw_ctx=_HardwareContextProxy(mgr=self.pulse_mgr, snapshot=self.attr))
        play(hardware.op, target)
        self._trace.append(
            InstructionTraceEntry(
                op="play",
                target=target,
                params={"operation": hardware.op},
            )
        )

    def _lower_sqr(
        self,
        gate: Gate,
        *,
        target: str,
        resolved_params: dict[str, ResolvedParameter],
    ) -> None:
        thetas = self._resolve_param(gate, "thetas", gate.params.get("thetas"), required=True)
        phis = self._resolve_param(gate, "phis", gate.params.get("phis"), required=True)
        resolved_params["thetas"] = thetas
        resolved_params["phis"] = phis

        theta_values = np.asarray(thetas.value, dtype=float)
        hardware = SQRHardware(
            thetas=theta_values,
            phis=np.asarray(phis.value, dtype=float),
            d_lambda=np.asarray(gate.params.get("d_lambda", np.zeros_like(theta_values)), dtype=float),
            d_alpha=np.asarray(gate.params.get("d_alpha", np.zeros_like(theta_values)), dtype=float),
            d_omega=np.asarray(gate.params.get("d_omega", np.zeros_like(theta_values)), dtype=float),
            target=target,
        )
        hardware.build(hw_ctx=_HardwareContextProxy(mgr=self.pulse_mgr, snapshot=self.attr))
        play(hardware.op, target)
        self._trace.append(
            InstructionTraceEntry(
                op="play",
                target=target,
                params={"operation": hardware.op},
            )
        )

    def _resolve_qubit_rotation_op(
        self,
        gate: Gate,
        *,
        gate_index: int,
        target: str,
        resolved_params: dict[str, ResolvedParameter],
    ) -> tuple[Any, dict[str, Any]]:
        base_rf = self._base_frequency_for(target)
        resolved_params.setdefault("base_frequency", ResolvedParameter(value=base_rf, source="calibration"))
        policy = str(gate.params.get("implementation_policy") or gate.metadata.get("implementation_policy") or "").lower()
        op = gate.params.get("op")
        angle = gate.params.get("angle")
        phase = gate.params.get("phase", 0.0)
        detune = gate.params.get("detune")

        if detune is not None:
            detune_resolved = self._resolve_param(gate, "detune", detune, required=False)
            resolved_params["detune"] = detune_resolved
            if detune_resolved.value is not None:
                self._emit_frequency_update(target, detune_hz=float(detune_resolved.value))

        if op is not None and policy in {"", "operation", "direct"}:
            resolved_params["op"] = ResolvedParameter(value=str(op), source="override")
            play_kwargs: dict[str, Any] = {}
            operation_handle = str(op)
            amplitude = gate.params.get("amplitude")
            if amplitude is not None:
                amp_resolved = self._resolve_param(gate, "amplitude", amplitude, required=True)
                self._validate_amplitude(float(amp_resolved.value))
                resolved_params["amplitude"] = amp_resolved
                operation_handle = str(op) * amp(float(amp_resolved.value))
            if gate.duration_clks is not None:
                play_kwargs["duration"] = int(gate.duration_clks)
                resolved_params["duration_clks"] = ResolvedParameter(value=int(gate.duration_clks), source="override")
            return operation_handle, play_kwargs

        if policy in {"hardware_reference", "reference_rotation"}:
            theta_value = float(angle if angle is not None else math.pi)
            phase_value = float(phase)
            reference_pulse = str(gate.params.get("reference_pulse", "x180_pulse"))
            resolved_params["angle"] = ResolvedParameter(value=theta_value, source="override")
            resolved_params["phase"] = ResolvedParameter(value=phase_value, source="override")
            resolved_params["reference_pulse"] = ResolvedParameter(value=reference_pulse, source="override")
            resolved_params["implementation_policy"] = ResolvedParameter(value="hardware_reference", source="override")
            hardware = QubitRotationHardware(
                theta=theta_value,
                phi=phase_value,
                ref_x180_pulse=reference_pulse,
                target=target,
            )
            hardware.build(hw_ctx=_HardwareContextProxy(mgr=self.pulse_mgr, snapshot=self.attr))
            return hardware.op, {}

        raw_drag = gate.params.get("drag_coeff", 0.0)
        drag_hint = raw_drag if isinstance(raw_drag, (int, float)) else 0.0
        pulse_policy = policy or ("drag_gaussian" if float(drag_hint or 0.0) else "gaussian")
        amplitude = self._resolve_param(gate, "amplitude", gate.params.get("amplitude"), required=True)
        length = self._resolve_param(
            gate,
            "length",
            gate.params.get("length_ns", gate.params.get("length")),
            required=False,
        )
        sigma = self._resolve_param(
            gate,
            "sigma",
            gate.params.get("sigma"),
            required=False,
        )
        drag_coeff = self._resolve_param(
            gate,
            "drag_coeff",
            gate.params.get("drag_coeff"),
            required=False,
        )
        anharmonicity = self._resolve_param(
            gate,
            "anharmonicity",
            gate.params.get("anharmonicity"),
            required=False,
        )
        resolved_params["implementation_policy"] = ResolvedParameter(value=pulse_policy, source="override")
        resolved_params["amplitude"] = amplitude
        if length.value is not None:
            resolved_params["length"] = length
        if sigma.value is not None:
            resolved_params["sigma"] = sigma
        if drag_coeff.value is not None:
            resolved_params["drag_coeff"] = drag_coeff
        if anharmonicity.value is not None:
            resolved_params["anharmonicity"] = anharmonicity

        amplitude_value = float(amplitude.value)
        self._validate_amplitude(amplitude_value)
        length_ns = int(length.value if length.value is not None else max(16, int((gate.duration_clks or 4) * 4)))
        sigma_value = float(sigma.value if sigma.value is not None else max(length_ns / 6.0, 1.0))
        drag_value = float(drag_coeff.value if drag_coeff.value is not None else 0.0)
        anharmonicity_value = float(
            anharmonicity.value
            if anharmonicity.value is not None
            else getattr(self.attr, "anharmonicity", -200e6) or -200e6
        )

        if pulse_policy == "square":
            I_samples = [amplitude_value] * length_ns
            Q_samples = [0.0] * length_ns
        elif pulse_policy == "gaussian":
            I_samples, Q_samples = drag_gaussian_pulse_waveforms(
                amplitude=amplitude_value,
                length=length_ns,
                sigma=sigma_value,
                alpha=0.0,
                anharmonicity=anharmonicity_value,
            )
        elif pulse_policy == "drag_gaussian":
            I_samples, Q_samples = drag_gaussian_pulse_waveforms(
                amplitude=amplitude_value,
                length=length_ns,
                sigma=sigma_value,
                alpha=drag_value,
                anharmonicity=anharmonicity_value,
            )
        else:
            raise ValueError(f"Unsupported qubit rotation implementation policy: {pulse_policy!r}")

        phase_value = float(phase or 0.0)
        if phase_value:
            z = np.asarray(I_samples, dtype=float) + 1j * np.asarray(Q_samples, dtype=float)
            z = z * np.exp(-1j * phase_value)
            I_samples = np.real(z).tolist()
            Q_samples = np.imag(z).tolist()
            resolved_params["phase"] = ResolvedParameter(value=phase_value, source="override")
        if angle is not None:
            resolved_params["angle"] = ResolvedParameter(value=angle, source="override")

        op_id = gate.instance_name or gate.resolved_name(index=gate_index)
        self.pulse_mgr.create_control_pulse(
            element=target,
            op=op_id,
            length=length_ns,
            I_samples=I_samples,
            Q_samples=Q_samples,
            persist=False,
            override=True,
        )
        return op_id, {}

    def _emit_frequency_update(self, element: str, *, detune_hz: float = 0.0) -> None:
        base_rf = self._base_frequency_for(element)
        lo = self._lo_frequency_for(element)
        if lo is None:
            raise ValueError(f"Cannot emit update_frequency for {element!r} without a known LO frequency.")
        target_rf = float(base_rf) + float(detune_hz)
        target_if = int(round(target_rf - lo))
        if self._current_if.get(element) == target_if:
            return
        update_frequency(element, target_if)
        self._current_if[element] = target_if
        self._trace.append(
            InstructionTraceEntry(
                op="update_frequency",
                target=element,
                params={"if_hz": target_if, "rf_hz": target_rf},
            )
        )

    def _base_frequency_for(self, element: str) -> float:
        if element in self._base_frequencies:
            return self._base_frequencies[element]
        category, attr_name = self._element_category(element)
        freq_value = None
        if self.calibration is not None:
            freq_entry = self.calibration.get_frequencies(element)
            if freq_entry is not None:
                field = {
                    "readout": "resonator_freq",
                    "qubit": "qubit_freq",
                    "storage": "storage_freq",
                }[category]
                freq_value = getattr(freq_entry, field, None)
                if freq_value is None and getattr(freq_entry, "rf_freq", None) is not None:
                    freq_value = getattr(freq_entry, "rf_freq", None)
                if (
                    freq_value is None
                    and getattr(freq_entry, "lo_freq", None) is not None
                    and getattr(freq_entry, "if_freq", None) is not None
                ):
                    freq_value = float(freq_entry.lo_freq) + float(freq_entry.if_freq)
        if freq_value is None:
            freq_value = getattr(self.attr, attr_name, None)
        if freq_value is None:
            raise ValueError(f"Missing base frequency for element {element!r}.")
        self._base_frequencies[element] = float(freq_value)
        lo = self._lo_frequency_for(element)
        if lo is not None:
            self._current_if[element] = int(round(float(freq_value) - lo))
        return float(freq_value)

    def _lo_frequency_for(self, element: str) -> float | None:
        if self.hw is not None:
            getter = getattr(self.hw, "get_element_lo", None)
            if callable(getter):
                try:
                    return float(getter(element))
                except Exception:
                    pass
        bindings = getattr(self.session, "bindings", None)
        if bindings is not None:
            if element == getattr(self.attr, "qb_el", None):
                lo = getattr(getattr(bindings, "qubit", None), "lo_frequency", None)
                if lo is not None:
                    return float(lo)
            if element == getattr(self.attr, "ro_el", None):
                lo = getattr(getattr(getattr(bindings, "readout", None), "drive_out", None), "lo_frequency", None)
                if lo is not None:
                    return float(lo)
            if element == getattr(self.attr, "st_el", None):
                lo = getattr(getattr(bindings, "storage", None), "lo_frequency", None)
                if lo is not None:
                    return float(lo)
        return None

    def _element_category(self, element: str) -> tuple[str, str]:
        if element == getattr(self.attr, "ro_el", None):
            return "readout", "ro_fq"
        if element == getattr(self.attr, "st_el", None):
            return "storage", "st_fq"
        return "qubit", "qb_fq"

    def _resolve_target(self, target: str) -> str:
        aliases = {
            "qubit": getattr(self.attr, "qb_el", None),
            "qb": getattr(self.attr, "qb_el", None),
            "readout": getattr(self.attr, "ro_el", None),
            "ro": getattr(self.attr, "ro_el", None),
            "resonator": getattr(self.attr, "ro_el", None),
            "storage": getattr(self.attr, "st_el", None),
            "st": getattr(self.attr, "st_el", None),
        }
        resolved = aliases.get(target, target)
        return str(resolved or target)

    def _resolve_param(
        self,
        gate: Gate,
        name: str,
        value: Any,
        *,
        required: bool,
    ) -> ResolvedParameter:
        if isinstance(value, ParameterSource):
            if value.has_override():
                return ResolvedParameter(value=value.override, source="override")
            if value.calibration is not None:
                cal_value = self._lookup_calibration(value.calibration)
                if cal_value is not None:
                    return ResolvedParameter(
                        value=cal_value,
                        source="calibration",
                        reference=value.calibration.path(),
                    )
            if value.attr_fallback is not None:
                attr_value = getattr(self.attr, value.attr_fallback, None)
                if attr_value is not None:
                    return ResolvedParameter(
                        value=attr_value,
                        source="cQED_attributes",
                        attr_fallback=value.attr_fallback,
                    )
            if value.default is not _UNSET:
                return ResolvedParameter(value=value.default, source="default")
            if required or value.required:
                ref = value.calibration.path() if value.calibration is not None else None
                raise ValueError(
                    f"Gate {gate.gate_type!r} is missing required parameter {name!r}. "
                    f"reference={ref!r} attr_fallback={value.attr_fallback!r}"
                )
            return ResolvedParameter(value=None, source="unset")

        if value is None:
            if required:
                raise ValueError(f"Gate {gate.gate_type!r} is missing required parameter {name!r}.")
            return ResolvedParameter(value=None, source="unset")

        return ResolvedParameter(value=value, source="override")

    def _lookup_calibration(self, reference: CalibrationReference) -> Any:
        if self.calibration is None:
            return None
        namespace = reference.namespace.lower()
        key = reference.key
        field = reference.field
        if namespace in {"pulse", "pulse_calibration"}:
            obj = self.calibration.get_pulse_calibration(key)
        elif namespace in {"cqed", "cqed_params"}:
            obj = self.calibration.get_cqed_params(key)
        elif namespace in {"frequencies", "frequency"}:
            obj = self.calibration.get_frequencies(key)
        elif namespace == "discrimination":
            obj = self.calibration.get_discrimination(key)
        elif namespace in {"readout_quality", "quality"}:
            obj = self.calibration.get_readout_quality(key)
        else:
            raise ValueError(f"Unsupported calibration namespace: {reference.namespace!r}")
        return None if obj is None else getattr(obj, field, None)

    def _condition_expression(self, gate: Gate, *, measurements: dict[str, _MeasurementRuntime]):
        if gate.condition is None:
            return None
        runtime = measurements.get(gate.condition.measurement_key)
        if runtime is None:
            raise ValueError(
                f"Conditional gate {gate.instance_name!r} references unknown measurement key "
                f"{gate.condition.measurement_key!r}."
            )
        source_name = gate.condition.source
        derived_source = runtime.record.derived_state_name or "state"
        if runtime.record.state_rule is not None and source_name == derived_source:
            raise RuntimeError(
                "compile_v2 does not support real-time branching on post-processed derived state "
                f"{gate.condition.measurement_key}.{source_name}. "
                "Compilation emits IQ streams plus StateRule metadata only; apply derive_state() in analysis "
                "or implement a true QUA branch path before enabling real-time branching."
            )
        source_var = None
        source_var = runtime.variables.get(source_name)
        if source_var is None:
            raise ValueError(
                f"Conditional gate {gate.instance_name!r} references missing measurement source "
                f"{source_name!r}."
            )
        comparator = gate.condition.comparator
        if comparator == "truthy":
            return source_var
        value = gate.condition.value
        if comparator == "==":
            return source_var == value
        if comparator == ">":
            return source_var > value
        if comparator == "<":
            return source_var < value
        raise ValueError(f"Unsupported gate condition comparator: {comparator!r}")

    def _configure_measure_macro(self, *, target: str, operation: str, drive_frequency: float) -> None:
        pulse_info = self.pulse_mgr.get_pulseOp_by_element_op(target, operation, strict=False)
        if pulse_info is None:
            raise RuntimeError(f"Missing readout pulse mapping for target={target!r}, operation={operation!r}")

        weight_mapping = pulse_info.int_weights_mapping or {}
        cos_key, sin_key, minus_sin_key = self._default_weight_keys(operation=operation, mapping=weight_mapping)

        measureMacro.set_pulse_op(
            pulse_info,
            active_op=operation,
            weights=[[cos_key, sin_key], [minus_sin_key, cos_key]],
            weight_len=getattr(pulse_info, "length", None),
        )
        measureMacro.set_drive_frequency(float(drive_frequency))

    def _default_weight_keys(self, *, operation: str, mapping: dict[str, str] | str) -> tuple[str, str, str]:
        if not isinstance(mapping, dict):
            return ("cos", "sin", "minus_sin")
        prefix = "" if operation == "readout" else f"{operation}_"
        candidates = [
            (f"{prefix}cos", f"{prefix}sin", f"{prefix}minus_sin"),
            ("cos", "sin", "minus_sin"),
        ]
        for triplet in candidates:
            if all(key in mapping for key in triplet):
                return triplet
        return ("cos", "sin", "minus_sin")

    def _validate_amplitude(self, value: float) -> None:
        if abs(float(value)) > float(MAX_AMPLITUDE):
            raise ValueError(
                f"Amplitude {value:.6g} exceeds MAX_AMPLITUDE={float(MAX_AMPLITUDE):.6g}."
            )

    def _flatten_gate_sources(self, gates: list[GateResolution]) -> dict[str, dict[str, Any]]:
        flattened: dict[str, dict[str, Any]] = {}
        for gate in gates:
            for name, value in sorted(gate.parameters.items()):
                flattened[f"{gate.gate_name}.{name}"] = value.to_dict()
        return flattened

    def _measure_macro_state(self) -> dict[str, Any] | None:
        try:
            snap = getattr(measureMacro, "_snapshot", None)
            if callable(snap):
                return snap()
        except Exception:
            pass
        return try_build_readout_snapshot_from_macro()
