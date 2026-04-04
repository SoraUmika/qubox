from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any

import numpy as np

from ..gates.hardware.displacement import DisplacementHardware
from ..gates.hardware.qubit_rotation import QubitRotationHardware
from ..gates.hardware.sqr import SQRHardware
from .models import (
    AcquireInstruction,
    BarrierInstruction,
    ControlDuration,
    ControlProgram,
    FrameUpdateInstruction,
    FrequencyUpdateInstruction,
    PulseInstruction,
    SemanticGateInstruction,
    WaitInstruction,
)


@dataclass
class _HardwareContextProxy:
    mgr: Any
    snapshot: Any

    def context_snapshot(self):
        return self.snapshot


def _resolved_targets(session, targets: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(session.resolve_alias(str(target)) for target in targets)


def _parse_angle(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    token = str(value).strip().lower().replace(" ", "")
    table = {
        "0": 0.0,
        "pi": math.pi,
        "-pi": -math.pi,
        "pi/2": math.pi / 2.0,
        "-pi/2": -math.pi / 2.0,
        "pi/4": math.pi / 4.0,
        "-pi/4": -math.pi / 4.0,
    }
    if token in table:
        return table[token]
    raise ValueError(f"Unsupported symbolic angle token: {value!r}")


def _resolved_duration(session, target: str, op: str, fallback: ControlDuration | None) -> ControlDuration | None:
    pulse = session.pulse_mgr.get_pulseOp_by_element_op(target, op, strict=False)
    length = getattr(pulse, "length", None) if pulse is not None else None
    if length is not None:
        return ControlDuration(value=int(length), unit="clks")
    return fallback


def _unresolved(instruction: SemanticGateInstruction, *, error: Exception | None = None) -> SemanticGateInstruction:
    metadata = dict(instruction.metadata)
    metadata["control_realization"] = "unresolved"
    if error is not None:
        metadata["realization_error"] = str(error)
    return replace(instruction, metadata=metadata)


def _realize_qubit_rotation(session, instruction: SemanticGateInstruction):
    targets = _resolved_targets(session, instruction.targets)
    if len(targets) != 1:
        raise ValueError("qubit_rotation realization requires exactly one target")
    target = targets[0]
    params = dict(instruction.params)
    policy = str(params.get("implementation_policy") or instruction.metadata.get("implementation_policy") or "").lower()
    op = params.get("op")

    if op is not None and policy in {"", "operation", "direct"}:
        return PulseInstruction(
            targets=(target,),
            operation=str(op),
            amplitude=params.get("amplitude"),
            phase_rad=params.get("phase"),
            detuning_hz=params.get("detune"),
            duration=_resolved_duration(session, target, str(op), instruction.duration),
            params={
                key: value
                for key, value in params.items()
                if key not in {"op", "amplitude", "phase", "detune"}
            },
            condition=instruction.condition,
            tags=instruction.tags,
            label=instruction.label,
            metadata={**instruction.metadata, "control_realization": "mapped_operation"},
            provenance=instruction.provenance,
        )

    hardware = QubitRotationHardware(
        theta=_parse_angle(params.get("angle", math.pi)),
        phi=float(params.get("phase", 0.0) or 0.0),
        ref_x180_pulse=str(params.get("reference_pulse", "x180_pulse")),
        d_lambda=float(params.get("d_lambda", 0.0) or 0.0),
        d_alpha=float(params.get("d_alpha", 0.0) or 0.0),
        d_omega=float(params.get("d_omega", 0.0) or 0.0),
        target=target,
    )
    hardware.build(hw_ctx=_HardwareContextProxy(mgr=session.pulse_mgr, snapshot=session.context_snapshot()))
    return PulseInstruction(
        targets=(target,),
        operation=hardware.op,
        duration=_resolved_duration(session, target, hardware.op, instruction.duration),
        params={
            key: value
            for key, value in params.items()
            if key not in {"phase", "reference_pulse", "d_lambda", "d_alpha", "d_omega"}
        },
        condition=instruction.condition,
        tags=instruction.tags,
        label=instruction.label,
        metadata={**instruction.metadata, "control_realization": "hardware_reference"},
        provenance=instruction.provenance,
    )


def _realize_displacement(session, instruction: SemanticGateInstruction):
    targets = _resolved_targets(session, instruction.targets)
    if len(targets) != 1:
        raise ValueError("displacement realization requires exactly one target")
    target = targets[0]
    alpha = complex(instruction.params["alpha"])
    hardware = DisplacementHardware(alpha=alpha, target=target)
    hardware.build(hw_ctx=_HardwareContextProxy(mgr=session.pulse_mgr, snapshot=session.context_snapshot()))
    return PulseInstruction(
        targets=(target,),
        operation=hardware.op,
        duration=_resolved_duration(session, target, hardware.op, instruction.duration),
        params=dict(instruction.params),
        condition=instruction.condition,
        tags=instruction.tags,
        label=instruction.label,
        metadata={**instruction.metadata, "control_realization": "hardware_reference"},
        provenance=instruction.provenance,
    )


def _realize_sqr(session, instruction: SemanticGateInstruction):
    targets = _resolved_targets(session, instruction.targets)
    if len(targets) != 1:
        raise ValueError("sqr realization requires exactly one target")
    target = targets[0]
    thetas = np.asarray(instruction.params["thetas"], dtype=float)
    hardware = SQRHardware(
        thetas=thetas,
        phis=np.asarray(instruction.params["phis"], dtype=float),
        d_lambda=np.asarray(instruction.params.get("d_lambda", np.zeros_like(thetas)), dtype=float),
        d_alpha=np.asarray(instruction.params.get("d_alpha", np.zeros_like(thetas)), dtype=float),
        d_omega=np.asarray(instruction.params.get("d_omega", np.zeros_like(thetas)), dtype=float),
        target=target,
    )
    hardware.build(hw_ctx=_HardwareContextProxy(mgr=session.pulse_mgr, snapshot=session.context_snapshot()))
    return PulseInstruction(
        targets=(target,),
        operation=hardware.op,
        duration=_resolved_duration(session, target, hardware.op, instruction.duration),
        params=dict(instruction.params),
        condition=instruction.condition,
        tags=instruction.tags,
        label=instruction.label,
        metadata={**instruction.metadata, "control_realization": "hardware_reference"},
        provenance=instruction.provenance,
    )


def _realize_instruction(session, instruction):
    if isinstance(instruction, PulseInstruction):
        return replace(instruction, targets=_resolved_targets(session, instruction.targets))
    if isinstance(instruction, WaitInstruction):
        return replace(instruction, targets=_resolved_targets(session, instruction.targets))
    if isinstance(instruction, BarrierInstruction):
        return replace(instruction, targets=_resolved_targets(session, instruction.targets))
    if isinstance(instruction, FrameUpdateInstruction):
        return replace(instruction, target=session.resolve_alias(str(instruction.target)))
    if isinstance(instruction, FrequencyUpdateInstruction):
        return replace(instruction, target=session.resolve_alias(str(instruction.target)))
    if isinstance(instruction, AcquireInstruction):
        return replace(instruction, target=session.resolve_alias(str(instruction.target), role_hint="readout"))
    if not isinstance(instruction, SemanticGateInstruction):
        return instruction

    gate_type = str(instruction.gate_type).lower()
    if gate_type in {"idle", "wait"} and instruction.duration is not None:
        return WaitInstruction(
            targets=_resolved_targets(session, instruction.targets),
            duration=instruction.duration,
            condition=instruction.condition,
            tags=instruction.tags,
            label=instruction.label,
            metadata={**instruction.metadata, "control_realization": "semantic_wait"},
            provenance=instruction.provenance,
        )
    if gate_type in {"align", "barrier"}:
        return BarrierInstruction(
            targets=_resolved_targets(session, instruction.targets),
            tags=instruction.tags,
            label=instruction.label,
            metadata={**instruction.metadata, "control_realization": "semantic_barrier"},
            provenance=instruction.provenance,
        )

    try:
        if gate_type in {"qubit_rotation", "x", "y"}:
            return _realize_qubit_rotation(session, instruction)
        if gate_type == "displacement":
            return _realize_displacement(session, instruction)
        if gate_type == "sqr":
            return _realize_sqr(session, instruction)
    except Exception as exc:
        return _unresolved(instruction, error=exc)

    return _unresolved(instruction)


def realize_control_program(session, program: ControlProgram) -> ControlProgram:
    realized = tuple(_realize_instruction(session, instruction) for instruction in program.instructions)
    metadata = dict(program.metadata)
    metadata["control_realized"] = True
    return replace(program, instructions=realized, metadata=metadata)