from __future__ import annotations

from qubox_v2_legacy.programs.circuit_runner import (
    Gate as LegacyGate,
    GateCondition as LegacyGateCondition,
    MeasurementRecord,
    MeasurementSchema,
    QuantumCircuit as LegacyQuantumCircuit,
    StreamSpec,
)
from qubox_v2_legacy.programs.measurement import StateRule

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


def _condition_to_legacy(condition: Condition | None) -> LegacyGateCondition | None:
    if condition is None:
        return None
    return LegacyGateCondition(
        measurement_key=condition.measurement_key,
        source=condition.source,
        comparator=condition.comparator,
        value=condition.value,
    )


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


def lower_to_legacy_circuit(
    session,
    *,
    body: Sequence | QuantumCircuit,
    sweep: SweepPlan | None,
    acquisition,
) -> LegacyQuantumCircuit:
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
        target = operation.target

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
