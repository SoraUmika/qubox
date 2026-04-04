from __future__ import annotations

from numbers import Real

from qubox.programs.circuit_ir import (
    Gate as LegacyGate,
    GateCondition as LegacyGateCondition,
    MeasurementRecord,
    MeasurementSchema,
    QuantumCircuit as LegacyQuantumCircuit,
    StreamSpec,
)
from qubox.programs.measurement import StateRule

from ...control.models import (
    AcquireInstruction,
    BarrierInstruction,
    ControlCondition,
    ControlProgram,
    FrameUpdateInstruction,
    FrequencyUpdateInstruction,
    PulseInstruction,
    SemanticGateInstruction,
    WaitInstruction,
)
from ...circuit import QuantumCircuit
from ...sequence import Operation, Sequence, SweepPlan
from ...sequence.models import Condition


def _measurement_record(
    *,
    key: str,
    operation: str,
    mode: str,
    state_rule: StateRule | None = None,
) -> MeasurementRecord:
    return MeasurementRecord(
        key=key,
        kind="iq",
        operation=operation,
        with_state=False,
        streams=(
            StreamSpec(name="I", qua_type="fixed", shape=("shots",), aggregate="save_all"),
            StreamSpec(name="Q", qua_type="fixed", shape=("shots",), aggregate="save_all"),
        ),
        state_rule=state_rule if mode in {"classified", "population"} else None,
        derived_state_name="state" if mode in {"classified", "population"} else None,
    )


def _state_rule_from_session(session, readout: str) -> StateRule | None:
    discrimination = session.resolve_discrimination(readout)
    if discrimination is None:
        return None
    return StateRule(
        kind="I_threshold",
        threshold=float(discrimination.threshold),
        sense="greater",
        rotation_angle=float(discrimination.angle),
        metadata={"source": "CalibrationStore.discrimination"},
    )


def _condition_to_legacy(condition: Condition | ControlCondition | None) -> LegacyGateCondition | None:
    if condition is None:
        return None
    return LegacyGateCondition(
        measurement_key=condition.measurement_key,
        source=condition.source,
        comparator=condition.comparator,
        value=condition.value,
    )


def _resolve_targets(session, targets: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(session.resolve_alias(str(target)) for target in targets)


def _collapse_targets(targets: tuple[str, ...]) -> str | tuple[str, ...]:
    if len(targets) == 1:
        return targets[0]
    return targets


def _instruction_metadata(metadata, provenance) -> dict:
    merged = dict(metadata or {})
    if provenance is not None:
        merged["control_provenance"] = provenance.to_payload()
    return merged


def _duration_to_clks(duration) -> int | None:
    if duration is None:
        return None
    unit = str(duration.unit).lower()
    value = duration.value
    if unit == "clks":
        return int(value)
    if unit == "ns":
        return max(int(round(float(value) / 4.0)), 0)
    raise ValueError(f"Unsupported ControlDuration unit for QM lowering: {duration.unit!r}")


def _phase_value(value, *, field_name: str) -> float:
    if not isinstance(value, Real):
        raise ValueError(f"{field_name} must be a real numeric value for QM lowering.")
    return float(value)


def _expand_reset(session, operation: Operation) -> list[Operation]:
    qubit, readout = operation.targets
    mode = str(operation.params.get("mode", "passive")).lower()
    if mode == "passive":
        return [session.ops.wait(qubit, session.get_thermalization_clks("qubit") or 0)]

    threshold = operation.params.get("threshold")
    if threshold in (None, "calibrated"):
        disc = session.resolve_discrimination(readout)
        threshold_value = float(disc.threshold) if disc is not None else 0.0
    else:
        threshold_value = float(threshold)

    max_attempts = int(operation.params.get("max_attempts", 1) or 1)
    measure_op = str(operation.params.get("operation", "readout"))
    pi_op = str(operation.params.get("pi_op", "x180"))
    expanded: list[Operation] = []
    for index in range(max_attempts):
        measure_key = f"reset_{qubit}_{index}"
        expanded.append(
            Operation(
                kind="measure",
                target=readout,
                params={"mode": "iq", "operation": measure_op, "measure_key": measure_key},
                tags=tuple(operation.tags) + ("reset",),
                label=f"{qubit}:ResetMeasure",
            )
        )
        expanded.append(
            Operation(
                kind="qubit_rotation",
                target=qubit,
                params={"op": pi_op, "angle": "pi", "family": "ResetPi"},
                condition=Condition(
                    measurement_key=measure_key,
                    source="I",
                    comparator=">",
                    value=threshold_value,
                ),
                tags=tuple(operation.tags) + ("reset",),
                label=f"{qubit}:ResetPi",
            )
        )
    return expanded


def _normalize_operations(session, body: Sequence | QuantumCircuit):
    if isinstance(body, QuantumCircuit):
        name = body.name
        operations = list(body.to_sequence().operations)
        metadata = dict(body.metadata)
    else:
        name = body.name
        operations = list(body.operations)
        metadata = dict(body.metadata)

    expanded: list[Operation] = []
    for operation in operations:
        if operation.kind == "reset":
            expanded.extend(_expand_reset(session, operation))
        else:
            expanded.append(operation)
    return name, expanded, metadata


def _normalize_control_program(acquisition, program: ControlProgram):
    instructions = list(program.instructions)
    if acquisition is not None and not any(isinstance(instruction, AcquireInstruction) for instruction in instructions):
        instructions.append(
            AcquireInstruction(
                target=acquisition.target,
                mode=acquisition.kind,
                operation=acquisition.operation,
                key=acquisition.key,
                metadata=dict(acquisition.metadata),
            )
        )
    return program.name, instructions, dict(program.metadata)


def _control_instruction_to_legacy(session, instruction, *, index: int):
    if isinstance(instruction, AcquireInstruction):
        if instruction.condition is not None:
            raise ValueError("Conditional AcquireInstruction is not supported by QM lowering yet.")
        readout = session.resolve_alias(str(instruction.target), role_hint="readout")
        measure_key = str(instruction.key or f"m{index}")
        mode = str(instruction.mode or "iq").lower()
        measure_operation = str(instruction.operation or "readout")
        record = _measurement_record(
            key=measure_key,
            operation=measure_operation,
            mode=mode,
            state_rule=_state_rule_from_session(session, readout),
        )
        gate = LegacyGate(
            name="measure_iq",
            target=readout,
            params={"measure_key": measure_key, "kind": "iq", "operation": measure_operation},
            tags=tuple(instruction.tags),
            instance_name=instruction.label,
            metadata=_instruction_metadata({"gate_type": "measure", **instruction.metadata}, instruction.provenance),
        )
        return [gate], [record]

    if isinstance(instruction, WaitInstruction):
        targets = _resolve_targets(session, instruction.targets)
        return [
            LegacyGate(
                name="idle",
                target=_collapse_targets(targets),
                params={},
                duration_clks=_duration_to_clks(instruction.duration),
                tags=tuple(instruction.tags),
                instance_name=instruction.label,
                condition=_condition_to_legacy(instruction.condition),
                metadata=_instruction_metadata({"gate_type": "idle", **instruction.metadata}, instruction.provenance),
            )
        ], []

    if isinstance(instruction, BarrierInstruction):
        targets = _resolve_targets(session, instruction.targets)
        return [
            LegacyGate(
                name="align",
                target=_collapse_targets(targets),
                params={},
                tags=tuple(instruction.tags),
                instance_name=instruction.label,
                metadata=_instruction_metadata({"gate_type": "align", **instruction.metadata}, instruction.provenance),
            )
        ], []

    if isinstance(instruction, FrameUpdateInstruction):
        target = session.resolve_alias(str(instruction.target))
        return [
            LegacyGate(
                name="frame_update",
                target=target,
                params={"phase": instruction.phase_rad},
                tags=tuple(instruction.tags),
                instance_name=instruction.label,
                condition=_condition_to_legacy(instruction.condition),
                metadata=_instruction_metadata({"gate_type": "frame_update", **instruction.metadata}, instruction.provenance),
            )
        ], []

    if isinstance(instruction, FrequencyUpdateInstruction):
        target = session.resolve_alias(str(instruction.target))
        return [
            LegacyGate(
                name="frame_update",
                target=target,
                params={"rf_hz": instruction.frequency_hz},
                tags=tuple(instruction.tags),
                instance_name=instruction.label,
                condition=_condition_to_legacy(instruction.condition),
                metadata=_instruction_metadata({"gate_type": "frame_update", **instruction.metadata}, instruction.provenance),
            )
        ], []

    if isinstance(instruction, PulseInstruction):
        targets = _resolve_targets(session, instruction.targets)
        if len(targets) != 1:
            raise ValueError("QM lowering currently supports PulseInstruction on exactly one target.")
        if instruction.operation is None:
            raise ValueError("PulseInstruction.operation is required for QM lowering.")

        gates: list[LegacyGate] = []
        target = targets[0]
        phase_value = instruction.phase_rad
        if phase_value is not None:
            phase = _phase_value(phase_value, field_name="PulseInstruction.phase_rad")
            gates.append(
                LegacyGate(
                    name="frame_update",
                    target=target,
                    params={"phase": phase},
                    tags=tuple(instruction.tags),
                    instance_name=f"{instruction.label}:phase_pre" if instruction.label else None,
                    condition=_condition_to_legacy(instruction.condition),
                    metadata=_instruction_metadata(
                        {"gate_type": "frame_update", "control_phase_scope": "local_pre", **instruction.metadata},
                        instruction.provenance,
                    ),
                )
            )

        play_params = {"op": instruction.operation, **dict(instruction.params)}
        if instruction.amplitude is not None:
            play_params["amplitude"] = instruction.amplitude
        if instruction.detuning_hz is not None:
            play_params["detune"] = instruction.detuning_hz
        gates.append(
            LegacyGate(
                name="play",
                target=target,
                params=play_params,
                duration_clks=_duration_to_clks(instruction.duration),
                tags=tuple(instruction.tags),
                instance_name=instruction.label,
                condition=_condition_to_legacy(instruction.condition),
                metadata=_instruction_metadata({"gate_type": "play", **instruction.metadata}, instruction.provenance),
            )
        )

        if phase_value is not None:
            phase = _phase_value(phase_value, field_name="PulseInstruction.phase_rad")
            gates.append(
                LegacyGate(
                    name="frame_update",
                    target=target,
                    params={"phase": -phase},
                    tags=tuple(instruction.tags),
                    instance_name=f"{instruction.label}:phase_post" if instruction.label else None,
                    condition=_condition_to_legacy(instruction.condition),
                    metadata=_instruction_metadata(
                        {"gate_type": "frame_update", "control_phase_scope": "local_post", **instruction.metadata},
                        instruction.provenance,
                    ),
                )
            )
        return gates, []

    if isinstance(instruction, SemanticGateInstruction):
        targets = _resolve_targets(session, instruction.targets)
        return [
            LegacyGate(
                name=instruction.gate_type,
                target=_collapse_targets(targets),
                params=dict(instruction.params),
                duration_clks=_duration_to_clks(instruction.duration),
                tags=tuple(instruction.tags),
                instance_name=instruction.label,
                condition=_condition_to_legacy(instruction.condition),
                metadata=_instruction_metadata(
                    {"gate_type": instruction.gate_type, **instruction.metadata},
                    instruction.provenance,
                ),
            )
        ], []

    raise TypeError(f"Unsupported control instruction type: {type(instruction).__name__}")


def lower_to_legacy_circuit(
    session,
    *,
    body: Sequence | QuantumCircuit | ControlProgram,
    sweep: SweepPlan | None,
    acquisition,
) -> LegacyQuantumCircuit:
    if isinstance(body, ControlProgram):
        name, instructions, metadata = _normalize_control_program(acquisition, body)
        records: list[MeasurementRecord] = []
        gates: list[LegacyGate] = []

        for index, instruction in enumerate(instructions):
            new_gates, new_records = _control_instruction_to_legacy(session, instruction, index=index)
            gates.extend(new_gates)
            records.extend(new_records)

        control_sweep = body.sweep_plan if getattr(body.sweep_plan, "axes", ()) else None
        effective_sweep = sweep if sweep is not None else control_sweep
        if effective_sweep is not None:
            metadata.setdefault(
                "sweep_axes",
                [
                    {
                        "parameter": axis.parameter,
                        "values": list(axis.values),
                        "center": axis.center,
                        "unit": axis.unit,
                        "metadata": dict(axis.metadata) if getattr(axis, "metadata", None) else {},
                    }
                    for axis in effective_sweep.axes
                ],
            )
            metadata.setdefault("n_shots", int(effective_sweep.averaging))

        return LegacyQuantumCircuit(
            name=name,
            gates=tuple(gates),
            metadata=metadata,
            measurement_schema=MeasurementSchema(records=tuple(records)),
        )

    name, operations, metadata = _normalize_operations(session, body)
    records: list[MeasurementRecord] = []
    gates: list[LegacyGate] = []

    if acquisition is not None and not any(op.kind == "measure" for op in operations):
        operations.append(
            Operation(
                kind="measure",
                target=session.resolve_alias(acquisition.target, role_hint="readout"),
                params={
                    "mode": acquisition.kind,
                    "operation": acquisition.operation,
                    "measure_key": acquisition.key,
                },
                label=f"{acquisition.target}:Measure",
            )
        )

    for index, operation in enumerate(operations):
        gate_type = operation.kind
        params = dict(operation.params)
        targets = _resolve_targets(session, operation.targets)
        target = _collapse_targets(targets)

        if gate_type == "measure":
            readout = session.resolve_alias(str(target), role_hint="readout")
            measure_key = str(params.get("measure_key") or f"m{index}")
            mode = str(params.get("mode", "iq")).lower()
            measure_operation = str(params.get("operation", "readout"))
            records.append(
                _measurement_record(
                    key=measure_key,
                    operation=measure_operation,
                    mode=mode,
                    state_rule=_state_rule_from_session(session, readout),
                )
            )
            gates.append(
                LegacyGate(
                    name="measure_iq",
                    target=readout,
                    params={"measure_key": measure_key, "kind": "iq", "operation": measure_operation},
                    tags=tuple(operation.tags),
                    instance_name=operation.label,
                    condition=_condition_to_legacy(operation.condition),
                    metadata={"gate_type": "measure"},
                )
            )
            continue

        legacy_name = gate_type
        if gate_type in {"wait", "idle"}:
            legacy_name = "idle"
        elif gate_type in {"align", "barrier"}:
            legacy_name = "align"
        elif gate_type == "play":
            legacy_name = "play"
        elif gate_type in {"qubit_rotation", "x", "y"}:
            legacy_name = "qubit_rotation"

        gates.append(
            LegacyGate(
                name=legacy_name,
                target=target,
                params=dict(params),
                duration_clks=operation.duration_clks,
                tags=tuple(operation.tags),
                instance_name=operation.label,
                condition=_condition_to_legacy(operation.condition),
                metadata={"gate_type": legacy_name},
            )
        )

    if sweep is not None:
        metadata.setdefault(
            "sweep_axes",
            [
                {
                    "parameter": axis.parameter,
                    "values": list(axis.values),
                    "center": axis.center,
                    "unit": axis.unit,
                    "metadata": dict(axis.metadata) if hasattr(axis, "metadata") and axis.metadata else {},
                }
                for axis in sweep.axes
            ],
        )
        metadata.setdefault("n_shots", int(sweep.averaging))

    return LegacyQuantumCircuit(
        name=name,
        gates=tuple(gates),
        metadata=metadata,
        measurement_schema=MeasurementSchema(records=tuple(records)),
    )
