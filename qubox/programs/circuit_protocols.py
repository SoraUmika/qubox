from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .circuit_ir import (
    CalibrationReference,
    CircuitBlock,
    ConditionalGate,
    Gate,
    GateCondition,
    MeasurementRecord,
    MeasurementSchema,
    ParameterSource,
    QuantumCircuit,
    StreamSpec,
)
from .measurement import StateRule


def _protocol_block(*, label: str, stop: int, lanes: tuple[str, ...]) -> CircuitBlock:
    return CircuitBlock(
        label=label,
        start=0,
        stop=stop,
        block_type="protocol",
        lanes=lanes,
    )


def _default_active_reset_rule(readout: str) -> StateRule:
    return StateRule(
        kind="I_threshold",
        threshold=ParameterSource(
            calibration=CalibrationReference("discrimination", readout, "threshold"),
            default=0.0,
        ),
        sense="greater",
        rotation_angle=ParameterSource(
            calibration=CalibrationReference("discrimination", readout, "angle"),
            default=0.0,
        ),
        metadata={"source": "CalibrationStore.discrimination"},
    )


def _iq_schema(
    *,
    key: str,
    operation: str = "readout",
    state_rule: StateRule | None = None,
    derived_state_name: str | None = None,
    metadata: dict[str, Any] | None = None,
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
        state_rule=state_rule,
        derived_state_name=derived_state_name,
        metadata=dict(metadata or {}),
    )


@dataclass(frozen=True)
class RamseyProtocol:
    qubit: str = "qubit"
    readout: str = "readout"
    tau_clks: int = 0
    r90_op: str = "x90"
    measure_operation: str = "readout"
    n_shots: int = 1

    def build(self) -> QuantumCircuit:
        measure_key = "ramsey_readout"
        gates = (
            Gate(name="qubit_rotation", target=self.qubit, params={"op": self.r90_op, "angle": "pi/2"}),
            Gate(name="idle", target=self.qubit, duration_clks=int(self.tau_clks)),
            Gate(name="qubit_rotation", target=self.qubit, params={"op": self.r90_op, "angle": "pi/2"}),
            Gate(
                name="measure_iq",
                target=self.readout,
                params={"measure_key": measure_key, "kind": "iq", "operation": self.measure_operation},
            ),
        )
        return QuantumCircuit(
            name="ramsey",
            gates=gates,
            metadata={"n_shots": int(self.n_shots), "protocol": "ramsey"},
            measurement_schema=MeasurementSchema(
                records=(_iq_schema(key=measure_key, operation=self.measure_operation),)
            ),
            blocks=(_protocol_block(label="Ramsey", stop=len(gates), lanes=(self.qubit, self.readout)),),
        )


@dataclass(frozen=True)
class EchoProtocol:
    qubit: str = "qubit"
    readout: str = "readout"
    tau_clks: int = 0
    r90_op: str = "x90"
    r180_op: str = "x180"
    measure_operation: str = "readout"
    n_shots: int = 1

    def build(self) -> QuantumCircuit:
        half_tau = int(self.tau_clks) // 2
        measure_key = "echo_readout"
        gates = (
            Gate(name="qubit_rotation", target=self.qubit, params={"op": self.r90_op, "angle": "pi/2"}),
            Gate(name="idle", target=self.qubit, duration_clks=half_tau),
            Gate(name="qubit_rotation", target=self.qubit, params={"op": self.r180_op, "angle": "pi"}),
            Gate(name="idle", target=self.qubit, duration_clks=half_tau),
            Gate(name="qubit_rotation", target=self.qubit, params={"op": self.r90_op, "angle": "pi/2"}),
            Gate(
                name="measure_iq",
                target=self.readout,
                params={"measure_key": measure_key, "kind": "iq", "operation": self.measure_operation},
            ),
        )
        return QuantumCircuit(
            name="echo",
            gates=gates,
            metadata={"n_shots": int(self.n_shots), "protocol": "echo"},
            measurement_schema=MeasurementSchema(
                records=(_iq_schema(key=measure_key, operation=self.measure_operation),)
            ),
            blocks=(_protocol_block(label="Echo", stop=len(gates), lanes=(self.qubit, self.readout)),),
        )


@dataclass(frozen=True)
class ActiveResetProtocol:
    qubit: str = "qubit"
    readout: str = "readout"
    pi_op: str = "x180"
    measure_operation: str = "readout"
    iterations: int = 1
    n_shots: int = 1
    enable_real_time_branching: bool = False
    state_rule: StateRule | None = None

    def build(self) -> QuantumCircuit:
        if int(self.iterations) < 1:
            raise ValueError("ActiveResetProtocol requires iterations >= 1.")

        rule = self.state_rule if self.state_rule is not None else _default_active_reset_rule(self.readout)
        gates: list[Gate] = []
        schema_records: list[MeasurementRecord] = []
        warnings: list[str] = []

        for index in range(int(self.iterations)):
            measure_key = f"active_reset_m{index}"
            gates.append(
                Gate(
                    name="measure_iq",
                    target=self.readout,
                    params={
                        "measure_key": measure_key,
                        "kind": "iq",
                        "operation": self.measure_operation,
                    },
                    tags=("active_reset",),
                )
            )
            schema_records.append(
                _iq_schema(
                    key=measure_key,
                    operation=self.measure_operation,
                    state_rule=rule,
                    derived_state_name="state",
                    metadata={"protocol": "active_reset"},
                )
            )
            if self.enable_real_time_branching:
                conditional_pi = ConditionalGate(
                    gate=Gate(
                        name="qubit_rotation",
                        target=self.qubit,
                        params={"op": self.pi_op, "angle": "pi"},
                    ),
                    condition=GateCondition(measurement_key=measure_key, source="state", comparator="truthy"),
                    tags=("active_reset", "real_time"),
                )
                gates.append(conditional_pi.to_gate())

        if not self.enable_real_time_branching:
            warnings.append(
                "Active reset is analysis-only in CircuitCompiler: MeasureIQ is emitted at program time, "
                "then derive_state and next-shot conditional action happen after the run. "
                "Set enable_real_time_branching=True to request a real-time branch."
            )

        block_metadata = {
            "mode": "real_time_branching_requested" if self.enable_real_time_branching else "analysis_only",
            "analysis_steps": (
                []
                if self.enable_real_time_branching
                else [
                    {
                        "measure_key": record.key,
                        "state_output": record.state_output_name(),
                        "action": "external/next-shot conditional action",
                    }
                    for record in schema_records
                ]
            ),
        }
        return QuantumCircuit(
            name="active_reset",
            gates=tuple(gates),
            metadata={
                "n_shots": int(self.n_shots),
                "protocol": "active_reset",
                "iterations": int(self.iterations),
                "real_time_branching": bool(self.enable_real_time_branching),
                "warnings": warnings,
            },
            measurement_schema=MeasurementSchema(records=tuple(schema_records)),
            blocks=(
                CircuitBlock(
                    label="ActiveReset",
                    start=0,
                    stop=len(gates),
                    block_type="protocol",
                    lanes=(self.qubit, self.readout),
                    metadata=block_metadata,
                ),
            ),
        )


def make_ramsey_circuit(**kwargs) -> QuantumCircuit:
    return RamseyProtocol(**kwargs).build()


def make_echo_circuit(**kwargs) -> QuantumCircuit:
    return EchoProtocol(**kwargs).build()


def make_active_reset_circuit(**kwargs) -> QuantumCircuit:
    return ActiveResetProtocol(**kwargs).build()
