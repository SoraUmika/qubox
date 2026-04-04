from __future__ import annotations

from typing import Any

from ..circuit.models import QuantumCircuit
from ..sequence.acquisition import AcquisitionSpec
from ..sequence.models import Condition, Operation, Sequence
from ..sequence.sweeps import SweepAxis, SweepPlan
from .models import (
    AcquireInstruction,
    BarrierInstruction,
    ControlCondition,
    ControlDuration,
    ControlProgram,
    ControlSweepAxis,
    ControlSweepPlan,
    FrameUpdateInstruction,
    FrequencyUpdateInstruction,
    ProvenanceTag,
    PulseInstruction,
    SemanticGateInstruction,
    WaitInstruction,
)


def _condition_to_control(condition: Condition | None) -> ControlCondition | None:
    if condition is None:
        return None
    return ControlCondition(
        measurement_key=condition.measurement_key,
        source=condition.source,
        comparator=condition.comparator,
        value=condition.value,
    )


def _duration_from_operation(operation: Operation) -> ControlDuration | None:
    if operation.duration_clks is None:
        return None
    return ControlDuration(value=int(operation.duration_clks), unit="clks")


def _sweep_axis_to_control(axis: SweepAxis) -> ControlSweepAxis:
    return ControlSweepAxis(
        parameter=axis.parameter,
        values=tuple(axis.values),
        spacing=axis.spacing,
        center=axis.center,
        unit=axis.unit,
        metadata=dict(axis.metadata),
    )


def _sweep_plan_to_control(sweep: SweepPlan | None) -> ControlSweepPlan:
    if sweep is None:
        return ControlSweepPlan()
    return ControlSweepPlan(
        axes=tuple(_sweep_axis_to_control(axis) for axis in sweep.axes),
        averaging=int(sweep.averaging),
    )


def _provenance(
    *,
    source_type: str,
    source_name: str,
    index: int | None,
    label: str | None,
    metadata: dict[str, Any] | None = None,
) -> ProvenanceTag:
    return ProvenanceTag(
        source_type=source_type,
        source_name=source_name,
        source_index=index,
        source_label=label,
        metadata=dict(metadata or {}),
    )


def _remaining_params(params: dict[str, Any], *names: str) -> dict[str, Any]:
    excluded = set(names)
    return {key: value for key, value in params.items() if key not in excluded}


def _operation_to_instruction(
    operation: Operation,
    *,
    source_type: str,
    source_name: str,
    index: int,
) -> Any:
    condition = _condition_to_control(operation.condition)
    duration = _duration_from_operation(operation)
    provenance = _provenance(
        source_type=source_type,
        source_name=source_name,
        index=index,
        label=operation.label,
        metadata={"operation_kind": operation.kind},
    )
    tags = tuple(operation.tags)
    metadata = dict(operation.metadata)

    if operation.kind in {"idle", "wait"}:
        if duration is None:
            raise ValueError("Wait-like operations require duration_clks when lowering to ControlProgram.")
        return WaitInstruction(
            targets=operation.targets,
            duration=duration,
            condition=condition,
            tags=tags,
            label=operation.label,
            metadata=metadata,
            provenance=provenance,
        )

    if operation.kind == "align":
        return BarrierInstruction(
            targets=operation.targets,
            tags=tags,
            label=operation.label,
            metadata=metadata,
            provenance=provenance,
        )

    if operation.kind == "frame_update":
        return FrameUpdateInstruction(
            target=operation.targets[0],
            phase_rad=operation.params.get("phase"),
            condition=condition,
            tags=tags,
            label=operation.label,
            metadata=metadata,
            provenance=provenance,
        )

    if operation.kind == "frequency_update":
        return FrequencyUpdateInstruction(
            target=operation.targets[0],
            frequency_hz=operation.params.get("frequency_hz", operation.params.get("frequency")),
            condition=condition,
            tags=tags,
            label=operation.label,
            metadata=metadata,
            provenance=provenance,
        )

    if operation.kind == "measure":
        return AcquireInstruction(
            target=operation.targets[0],
            mode=str(operation.params.get("mode", "iq")),
            operation=str(operation.params.get("operation", "readout")),
            key=operation.params.get("measure_key"),
            condition=condition,
            tags=tags,
            label=operation.label,
            metadata={**metadata, **_remaining_params(operation.params, "mode", "operation", "measure_key")},
            provenance=provenance,
        )

    if operation.kind == "play":
        return PulseInstruction(
            targets=operation.targets,
            operation=operation.params.get("op"),
            amplitude=operation.params.get("amplitude"),
            phase_rad=operation.params.get("phase"),
            detuning_hz=operation.params.get("detune"),
            duration=duration,
            params=_remaining_params(operation.params, "op", "amplitude", "phase", "detune"),
            condition=condition,
            tags=tags,
            label=operation.label,
            metadata=metadata,
            provenance=provenance,
        )

    return SemanticGateInstruction(
        gate_type=operation.kind,
        targets=operation.targets,
        params=dict(operation.params),
        duration=duration,
        condition=condition,
        tags=tags,
        label=operation.label,
        metadata=metadata,
        provenance=provenance,
    )


def _maybe_append_acquisition(
    instructions: list[Any],
    *,
    acquisition: AcquisitionSpec | None,
    source_type: str,
    source_name: str,
) -> list[Any]:
    if acquisition is None:
        return instructions
    if any(isinstance(instruction, AcquireInstruction) for instruction in instructions):
        return instructions
    instructions.append(
        AcquireInstruction(
            target=acquisition.target,
            mode=acquisition.kind,
            operation=acquisition.operation,
            key=acquisition.key,
            metadata=dict(acquisition.metadata),
            provenance=_provenance(
                source_type=source_type,
                source_name=source_name,
                index=None,
                label="implicit_acquisition",
                metadata={"source": "AcquisitionSpec"},
            ),
        )
    )
    return instructions


def sequence_to_control_program(
    sequence: Sequence,
    *,
    sweep: SweepPlan | None = None,
    acquisition: AcquisitionSpec | None = None,
) -> ControlProgram:
    instructions = [
        _operation_to_instruction(operation, source_type="sequence", source_name=sequence.name, index=index)
        for index, operation in enumerate(sequence.operations)
    ]
    instructions = _maybe_append_acquisition(
        instructions,
        acquisition=acquisition,
        source_type="sequence",
        source_name=sequence.name,
    )
    return ControlProgram(
        name=sequence.name,
        instructions=tuple(instructions),
        sweep_plan=_sweep_plan_to_control(sweep),
        metadata=dict(sequence.metadata),
    )


def circuit_to_control_program(
    circuit: QuantumCircuit,
    *,
    sweep: SweepPlan | None = None,
    acquisition: AcquisitionSpec | None = None,
) -> ControlProgram:
    instructions = [
        _operation_to_instruction(operation, source_type="circuit", source_name=circuit.name, index=index)
        for index, operation in enumerate(circuit.gates)
    ]
    instructions = _maybe_append_acquisition(
        instructions,
        acquisition=acquisition,
        source_type="circuit",
        source_name=circuit.name,
    )
    return ControlProgram(
        name=circuit.name,
        instructions=tuple(instructions),
        sweep_plan=_sweep_plan_to_control(sweep),
        metadata=dict(circuit.metadata),
    )