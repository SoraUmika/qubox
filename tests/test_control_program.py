from __future__ import annotations

from qubox.circuit import QuantumCircuit, QuantumGate
from qubox.backends.qm.lowering import lower_to_legacy_circuit
from qubox.control import (
    AcquireInstruction,
    BarrierInstruction,
    ControlDuration,
    ControlProgram,
    PulseInstruction,
    SemanticGateInstruction,
    WaitInstruction,
)
from qubox.sequence import AcquisitionSpec, Condition, Operation, Sequence, SweepAxis, SweepPlan


class _LoweringSession:
    def resolve_alias(self, alias, *, role_hint=None):
        mapping = {
            "q0": "transmon",
            "qubit": "transmon",
            "rr0": "resonator",
            "readout": "resonator",
        }
        return mapping.get(alias, alias)

    def resolve_discrimination(self, readout):
        return type("Disc", (), {"threshold": 0.12, "angle": 0.34})()


def test_sequence_to_control_program_preserves_instruction_kinds_and_provenance() -> None:
    sequence = Sequence(name="demo")
    sequence.add(
        Operation(
            kind="qubit_rotation",
            target="q0",
            params={"op": "x90", "angle": "pi/2"},
            label="prep",
        )
    )
    sequence.add(Operation(kind="idle", target="q0", duration_clks=24, label="gap"))
    sequence.add(Operation(kind="frame_update", target="q0", params={"phase": 0.25}, label="vz"))
    sequence.add(
        Operation(
            kind="measure",
            target="rr0",
            params={"mode": "iq", "operation": "readout", "measure_key": "m0"},
            condition=Condition(measurement_key="flag", source="state"),
            label="readout",
        )
    )

    program = sequence.to_control_program()

    assert isinstance(program, ControlProgram)
    assert [instruction.kind for instruction in program.instructions] == [
        "semantic_gate",
        "wait",
        "frame_update",
        "acquire",
    ]
    assert isinstance(program.instructions[0], SemanticGateInstruction)
    assert isinstance(program.instructions[1], WaitInstruction)
    assert isinstance(program.instructions[3], AcquireInstruction)
    assert program.instructions[0].provenance is not None
    assert program.instructions[0].provenance.source_type == "sequence"
    assert program.instructions[0].provenance.source_index == 0
    assert program.instructions[1].duration is not None
    assert program.instructions[1].duration.unit == "clks"
    assert program.instructions[3].condition is not None
    assert program.instructions[3].condition.measurement_key == "flag"


def test_quantum_circuit_to_control_program_appends_acquisition_and_sweep() -> None:
    circuit = QuantumCircuit(name="pulse_test", metadata={"family": "demo"})
    circuit.add(
        QuantumGate(
            kind="play",
            target="drive0",
            params={"op": "gaussian_drive", "amplitude": 0.15, "detune": 2.5e6},
            duration_clks=40,
            label="manual_pulse",
        )
    )

    sweep = SweepPlan(
        axes=(SweepAxis(parameter="pulse.amplitude", values=(0.1, 0.2), unit="arb"),),
        averaging=7,
    )
    acquisition = AcquisitionSpec(kind="iq", target="rr0", operation="readout", key="final")

    program = circuit.to_control_program(sweep=sweep, acquisition=acquisition)

    assert program.name == "pulse_test"
    assert program.metadata["family"] == "demo"
    assert program.sweep_plan.averaging == 7
    assert len(program.sweep_plan.axes) == 1
    assert program.sweep_plan.axes[0].parameter == "pulse.amplitude"
    assert [instruction.kind for instruction in program.instructions] == ["pulse", "acquire"]
    assert isinstance(program.instructions[0], PulseInstruction)
    assert program.instructions[0].operation == "gaussian_drive"
    assert program.instructions[0].detuning_hz == 2.5e6
    assert isinstance(program.instructions[1], AcquireInstruction)
    assert program.instructions[1].key == "final"
    assert program.instructions[1].provenance is not None
    assert program.instructions[1].provenance.source_label == "implicit_acquisition"


def test_control_program_payload_and_text_are_stable() -> None:
    sequence = Sequence(name="payload_demo")
    sequence.add(Operation(kind="play", target="drive0", params={"op": "flat_top", "phase": 0.5}))
    program = sequence.to_control_program()

    payload = program.to_payload()
    text = program.inspect()

    assert payload["name"] == "payload_demo"
    assert payload["instructions"][0]["kind"] == "pulse"
    assert "control_program: payload_demo" in text
    assert "phase_rad=0.5" in text


def test_control_program_lowers_to_legacy_circuit_with_phase_wrapping_and_barrier() -> None:
    program = ControlProgram(
        name="native_control",
        instructions=(
            PulseInstruction(
                targets=("q0",),
                operation="x90",
                phase_rad=0.5,
                duration=ControlDuration(16),
                label="prep",
            ),
            BarrierInstruction(targets=("q0", "rr0"), label="sync"),
            AcquireInstruction(target="rr0", mode="iq", operation="readout", key="m0", label="readout"),
        ),
    )

    legacy = lower_to_legacy_circuit(_LoweringSession(), body=program, sweep=None, acquisition=None)

    assert [gate.name for gate in legacy.gates] == ["frame_update", "play", "frame_update", "align", "measure_iq"]
    assert legacy.gates[0].target == "transmon"
    assert legacy.gates[0].params["phase"] == 0.5
    assert legacy.gates[2].params["phase"] == -0.5
    assert legacy.gates[3].target == ("transmon", "resonator")
    assert legacy.measurement_schema.records[0].key == "m0"