from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")


def _golden_path(name: str) -> Path:
    return Path(__file__).with_name("golden") / name


def _read_golden(name: str) -> str:
    return _golden_path(name).read_text(encoding="utf-8")


def _stable_json(payload) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _build_snapshot(build) -> str:
    return (
        "diagram_text:\n"
        f"{build.metadata['diagram_text']}"
        "\nmeasurement_schema:\n"
        f"{_stable_json(build.metadata['measurement_schema'])}"
        "\ninstruction_trace:\n"
        f"{_stable_json(build.metadata['instruction_trace'])}"
        "\nresolution_report:\n"
        f"{build.metadata['resolution_report_text']}"
        "\npost_processing:\n"
        f"{_stable_json(build.metadata['post_processing'])}"
    )


def test_single_qubit_rotation_override_beats_calibration_and_policy_selection(fake_session, gate_arch_modules):
    Gate = gate_arch_modules.circuit_runner.Gate
    QuantumCircuit = gate_arch_modules.circuit_runner.QuantumCircuit
    MeasurementSchema = gate_arch_modules.circuit_runner.MeasurementSchema
    ParameterSource = gate_arch_modules.circuit_runner.ParameterSource
    CalibrationReference = gate_arch_modules.circuit_runner.CalibrationReference
    CircuitCompiler = gate_arch_modules.circuit_compiler.CircuitCompiler

    outputs: dict[str, tuple[list[float], list[float], dict[str, dict[str, object]]]] = {}
    for policy in ("drag_gaussian", "gaussian", "square"):
        gate = Gate(
            name="qubit_rotation",
            target="qubit",
            params={
                "implementation_policy": policy,
                "amplitude": ParameterSource(
                    calibration=CalibrationReference("pulse_calibration", "ge_ref_r180", "amplitude"),
                    override=0.19,
                ),
                "length": ParameterSource(
                    calibration=CalibrationReference("pulse_calibration", "ge_ref_r180", "length"),
                ),
                "sigma": ParameterSource(
                    calibration=CalibrationReference("pulse_calibration", "ge_ref_r180", "sigma"),
                ),
                "drag_coeff": ParameterSource(
                    calibration=CalibrationReference("pulse_calibration", "ge_ref_r180", "drag_coeff"),
                ),
            },
        )
        circuit = QuantumCircuit(
            name=f"policy_{policy}",
            gates=(gate,),
            metadata={"n_shots": 1},
            measurement_schema=MeasurementSchema(),
        )
        build = CircuitCompiler(fake_session).compile(circuit)
        named_gate = circuit.with_stable_gate_names().gates[0]
        pulse = fake_session.pulse_mgr.get_pulseOp_by_element_op("qubit", named_gate.instance_name, strict=False)
        assert pulse is not None
        I_wf, Q_wf = fake_session.pulse_mgr.get_pulse_waveforms(pulse.pulse)
        assert isinstance(I_wf, list)
        assert isinstance(Q_wf, list)
        outputs[policy] = (I_wf, Q_wf, build.resolved_parameter_sources)

        amp_key = f"{named_gate.instance_name}.amplitude"
        assert build.resolved_parameter_sources[amp_key]["source"] == "override"

    drag_I, drag_Q, _ = outputs["drag_gaussian"]
    gauss_I, gauss_Q, _ = outputs["gaussian"]
    square_I, square_Q, _ = outputs["square"]

    assert max(abs(x) for x in drag_Q) > 0.0
    assert all(abs(x) < 1e-12 for x in gauss_Q)
    assert all(abs(x) < 1e-12 for x in square_Q)
    assert len({round(x, 9) for x in square_I}) == 1
    assert len({round(x, 9) for x in gauss_I}) > 1


def test_derive_state_supports_rotation_and_sense(gate_arch_modules):
    StateRule = gate_arch_modules.circuit_protocols.StateRule
    from qubox.programs.measurement import derive_state as derive_state_helper

    iq = {"I": np.array([0.0, 0.3, -0.2]), "Q": np.array([0.0, 0.0, 0.2])}
    gt_rule = StateRule(kind="I_threshold", threshold=0.1, sense="greater", rotation_angle=0.0)
    lt_rule = StateRule(kind="I_threshold", threshold=0.1, sense="less", rotation_angle=-(np.pi / 2))

    assert derive_state_helper(iq, gt_rule).tolist() == [False, True, False]
    assert derive_state_helper(iq, lt_rule).tolist() == [True, True, False]


def test_measurement_schema_validate_accepts_iq_outputs_and_namespaced_streams(gate_arch_modules):
    MeasurementRecord = gate_arch_modules.circuit_runner.MeasurementRecord
    MeasurementSchema = gate_arch_modules.circuit_runner.MeasurementSchema
    StreamSpec = gate_arch_modules.circuit_runner.StreamSpec

    schema = MeasurementSchema(
        records=(
            MeasurementRecord(
                key="m0",
                kind="iq",
                operation="readout",
                streams=(
                    StreamSpec(name="I", qua_type="fixed", shape=("shots",), aggregate="save_all"),
                    StreamSpec(name="Q", qua_type="fixed", shape=("shots",), aggregate="save_all"),
                ),
            ),
        )
    )

    assert schema.validate() is schema
    assert schema.to_payload()["records"][0]["streams"][0]["output_name"] == "m0.I"


def test_measurement_schema_validate_rejects_missing_q_stream(gate_arch_modules):
    MeasurementRecord = gate_arch_modules.circuit_runner.MeasurementRecord
    MeasurementSchema = gate_arch_modules.circuit_runner.MeasurementSchema
    StreamSpec = gate_arch_modules.circuit_runner.StreamSpec

    schema = MeasurementSchema(
        records=(
            MeasurementRecord(
                key="m0",
                kind="iq",
                operation="readout",
                streams=(StreamSpec(name="I", qua_type="fixed", shape=("shots",), aggregate="save_all"),),
            ),
        )
    )

    with pytest.raises(ValueError, match="missing required stream"):
        schema.validate()


def test_measurement_schema_validate_rejects_false_state_claim(gate_arch_modules):
    MeasurementRecord = gate_arch_modules.circuit_runner.MeasurementRecord
    MeasurementSchema = gate_arch_modules.circuit_runner.MeasurementSchema
    StreamSpec = gate_arch_modules.circuit_runner.StreamSpec

    schema = MeasurementSchema(
        records=(
            MeasurementRecord(
                key="m0",
                kind="iq",
                operation="readout",
                with_state=True,
                streams=(
                    StreamSpec(name="I", qua_type="fixed", shape=("shots",), aggregate="save_all"),
                    StreamSpec(name="Q", qua_type="fixed", shape=("shots",), aggregate="save_all"),
                ),
            ),
        )
    )

    with pytest.raises(ValueError, match="claims a produced state output"):
        schema.validate()


def test_ramsey_protocol_compilation_sequence_schema_and_diagram(fake_session, gate_arch_modules):
    circuit = gate_arch_modules.circuit_protocols.RamseyProtocol(tau_clks=12, n_shots=3).build()
    build = gate_arch_modules.circuit_compiler.CircuitCompiler(fake_session).compile(circuit)

    assert [gate.gate_type for gate in circuit.gates] == [
        "qubit_rotation",
        "idle",
        "qubit_rotation",
        "measure_iq",
    ]
    assert circuit.blocks[0].label == "Ramsey"

    trace = build.metadata["instruction_trace"]
    assert [entry["op"] for entry in trace] == ["play", "wait", "play", "measure"]
    assert trace[-1]["params"]["streams"] == ["ramsey_readout.I", "ramsey_readout.Q"]

    schema = circuit.measurement_schema.records[0]
    assert schema.key == "ramsey_readout"
    assert [stream.name for stream in schema.streams] == ["I", "Q"]
    assert schema.state_rule is None

    compiled_schema = build.metadata["measurement_schema"]["records"][0]
    assert compiled_schema["key"] == "ramsey_readout"
    assert [stream["output_name"] for stream in compiled_schema["streams"]] == [
        "ramsey_readout.I",
        "ramsey_readout.Q",
    ]
    assert build.metadata["diagram_text"] == circuit.to_diagram_text()


def test_echo_protocol_compilation_sequence(fake_session, gate_arch_modules):
    circuit = gate_arch_modules.circuit_protocols.EchoProtocol(tau_clks=20, n_shots=2).build()
    build = gate_arch_modules.circuit_compiler.CircuitCompiler(fake_session).compile(circuit)

    assert [gate.gate_type for gate in circuit.gates] == [
        "qubit_rotation",
        "idle",
        "qubit_rotation",
        "idle",
        "qubit_rotation",
        "measure_iq",
    ]
    assert [entry["op"] for entry in build.metadata["instruction_trace"]] == [
        "play",
        "wait",
        "play",
        "wait",
        "play",
        "measure",
    ]


def test_active_reset_defaults_to_analysis_only(fake_session, gate_arch_modules):
    circuit = gate_arch_modules.circuit_protocols.ActiveResetProtocol(iterations=1, n_shots=2).build()
    build = gate_arch_modules.circuit_compiler.CircuitCompiler(fake_session).compile(circuit)

    assert [gate.gate_type for gate in circuit.gates] == ["measure_iq"]
    assert build.metadata["compiler_warnings"] == [
        "Active reset is analysis-only in CircuitCompiler: MeasureIQ is emitted at program time, then derive_state and next-shot conditional action happen after the run. Set enable_real_time_branching=True to request a real-time branch."
    ]

    schema = circuit.measurement_schema.records[0]
    assert schema.state_rule is not None
    assert schema.derived_state_name == "state"
    assert schema.with_state is False
    assert [stream.name for stream in schema.streams] == ["I", "Q"]

    trace = build.metadata["instruction_trace"]
    assert [entry["op"] for entry in trace] == ["measure"]
    assert len(build.processors) == 1
    assert build.metadata["post_processing"][0]["timing"] == "post_run_analysis"
    assert "analysis-only" in build.metadata["diagram_text"]
    assert "derive_state(active_reset_m0.state)" in build.metadata["diagram_text"]


def test_active_reset_post_processing_derives_state_after_run(fake_session, gate_arch_modules):
    circuit = gate_arch_modules.circuit_protocols.ActiveResetProtocol(iterations=1, n_shots=2).build()
    build = gate_arch_modules.circuit_compiler.CircuitCompiler(fake_session).compile(circuit)
    processor = build.processors[0]

    output = processor(
        {
            "active_reset_m0.I": np.array([0.0, 0.2, -0.1]),
            "active_reset_m0.Q": np.array([0.0, 0.0, 0.0]),
        }
    )

    assert output["active_reset_m0.state"].tolist() == [False, True, False]


def test_active_reset_real_time_branching_fails_loudly(fake_session, gate_arch_modules):
    circuit = gate_arch_modules.circuit_protocols.ActiveResetProtocol(
        iterations=1,
        n_shots=2,
        enable_real_time_branching=True,
    ).build()

    assert "rt-branch requested" in circuit.to_diagram_text()
    assert "IF active_reset_m0.state" in circuit.to_diagram_text()

    with pytest.raises(RuntimeError, match="does not support real-time branching on post-processed derived state"):
        gate_arch_modules.circuit_compiler.CircuitCompiler(fake_session).compile(circuit)


def test_frequency_resolution_records_base_plan_and_update_order(fake_session, gate_arch_modules):
    Gate = gate_arch_modules.circuit_runner.Gate
    QuantumCircuit = gate_arch_modules.circuit_runner.QuantumCircuit
    MeasurementSchema = gate_arch_modules.circuit_runner.MeasurementSchema

    measure_record = gate_arch_modules.circuit_protocols._iq_schema(key="ro", operation="readout")
    circuit = QuantumCircuit(
        name="freq",
        gates=(
            Gate(name="qubit_rotation", target="qubit", params={"op": "x180", "detune": 2.5e6}),
            Gate(name="measure_iq", target="readout", params={"measure_key": "ro", "kind": "iq", "operation": "readout"}),
        ),
        metadata={"n_shots": 1},
        measurement_schema=MeasurementSchema(records=(measure_record,)),
    )
    build = gate_arch_modules.circuit_compiler.CircuitCompiler(fake_session).compile(circuit)

    assert build.resolved_frequencies == {"qubit": 6.05e9, "readout": 8.10e9}
    trace = build.metadata["instruction_trace"]
    assert [entry["op"] for entry in trace] == ["update_frequency", "play", "measure"]
    assert trace[0]["params"]["if_hz"] == 52_500_000


def test_display_plot_groups_protocol_block(fake_session, gate_arch_modules):
    circuit = gate_arch_modules.circuit_protocols.ActiveResetProtocol(iterations=1, n_shots=2).build()
    fig = circuit.draw(include_gate_names=True)
    assert len(fig.axes) == 1
    assert len(fig.axes[0].patches) >= len(circuit.gates) + len(circuit.blocks)


def test_cluster1_runner_dry_run_is_default(fake_session, gate_arch_modules):
    circuit = gate_arch_modules.circuit_protocols.RamseyProtocol(tau_clks=8, n_shots=2).build()
    execution = gate_arch_modules.circuit_execution.run_compiled_circuit(fake_session, circuit)

    assert execution.dry_run is True
    assert execution.cluster_name == "Cluster_1"
    assert execution.run_result is None
    assert fake_session.hw.run_calls == []
    assert execution.diagram_text == circuit.to_diagram_text()


def test_cluster1_runner_rejects_any_other_cluster(fake_session, gate_arch_modules):
    circuit = gate_arch_modules.circuit_protocols.RamseyProtocol(tau_clks=8, n_shots=2).build()
    with pytest.raises(ValueError, match="Only 'Cluster_1' is allowed"):
        gate_arch_modules.circuit_execution.run_compiled_circuit(
            fake_session,
            circuit,
            cluster="Cluster_2",
            run_on_opx=True,
        )
    assert fake_session.hw.run_calls == []


def test_cluster1_runner_requires_unambiguous_cluster_for_hardware_run(fake_session, gate_arch_modules):
    circuit = gate_arch_modules.circuit_protocols.RamseyProtocol(tau_clks=8, n_shots=2).build()
    ambiguous = SimpleNamespace(**vars(fake_session))
    del ambiguous.cluster_name
    with pytest.raises(RuntimeError, match="cluster is ambiguous"):
        gate_arch_modules.circuit_execution.run_compiled_circuit(
            ambiguous,
            circuit,
            run_on_opx=True,
        )


def test_cluster1_runner_executes_only_when_explicit(fake_session, gate_arch_modules):
    circuit = gate_arch_modules.circuit_protocols.RamseyProtocol(tau_clks=8, n_shots=2).build()
    execution = gate_arch_modules.circuit_execution.run_compiled_circuit(
        fake_session,
        circuit,
        run_on_opx=True,
        execution_kwargs={"print_report": False},
    )

    assert execution.dry_run is False
    assert execution.run_result is not None
    assert len(fake_session.hw.run_calls) == 1
    assert fake_session.hw.run_calls[0]["kwargs"]["print_report"] is False


def test_ramsey_circuit_text_matches_golden(gate_arch_modules):
    circuit = gate_arch_modules.circuit_protocols.RamseyProtocol(tau_clks=12, n_shots=3).build()
    assert circuit.to_text() == _read_golden("ramsey_circuit.txt")


def test_ramsey_diagram_matches_golden(gate_arch_modules):
    circuit = gate_arch_modules.circuit_protocols.RamseyProtocol(tau_clks=12, n_shots=3).build()
    assert circuit.to_diagram_text() == _read_golden("ramsey_diagram.txt")


def test_ramsey_resolution_report_matches_golden(fake_session, gate_arch_modules):
    circuit = gate_arch_modules.circuit_protocols.RamseyProtocol(tau_clks=12, n_shots=3).build()
    build = gate_arch_modules.circuit_compiler.CircuitCompiler(fake_session).compile(circuit)
    assert build.metadata["resolution_report_text"] == _read_golden("ramsey_resolution.txt")


def test_ramsey_measurement_schema_matches_golden(fake_session, gate_arch_modules):
    circuit = gate_arch_modules.circuit_protocols.RamseyProtocol(tau_clks=12, n_shots=3).build()
    build = gate_arch_modules.circuit_compiler.CircuitCompiler(fake_session).compile(circuit)
    assert _stable_json(build.metadata["measurement_schema"]) == _read_golden("ramsey_measurement_schema.json")


def test_active_reset_real_time_circuit_text_matches_golden(gate_arch_modules):
    circuit = gate_arch_modules.circuit_protocols.ActiveResetProtocol(
        iterations=1,
        n_shots=2,
        enable_real_time_branching=True,
    ).build()
    assert circuit.to_text() == _read_golden("active_reset_circuit.txt")


def test_active_reset_analysis_snapshot_matches_golden(fake_session, gate_arch_modules):
    circuit = gate_arch_modules.circuit_protocols.ActiveResetProtocol(iterations=1, n_shots=2).build()
    build = gate_arch_modules.circuit_compiler.CircuitCompiler(fake_session).compile(circuit)

    assert _build_snapshot(build) == _read_golden("active_reset_analysis_snapshot.txt")
