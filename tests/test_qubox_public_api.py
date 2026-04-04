from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qubox import ExperimentResult, Session
from qubox.calibration import CalibrationProposal
from qubox.control import ControlDuration, PulseInstruction
from qubox import notebook
from qubox.data import ExecutionRequest


class DummyCalibration:
    path = "calibration.json"

    def __init__(self):
        self._applied = []

    def to_dict(self):
        return {"version": "5.1.0", "cqed_params": {"transmon": {"qubit_freq": 6.1e9}}}

    def get_discrimination(self, readout):
        return type("Disc", (), {"threshold": 0.12, "angle": 0.34})()


class DummyPulse:
    def get_pulseOp_by_element_op(self, target, op, strict=False):
        return type("Pulse", (), {"length": 32})()


class DummyHardware:
    elements = {"transmon": {}, "resonator": {}, "storage": {}}


class DummyOrchestrator:
    def __init__(self):
        self.calls = []

    def apply_patch(self, patch, dry_run=True):
        self.calls.append((patch, dry_run))
        return {"dry_run": dry_run, "n_updates": len(patch.updates)}


class DummyLegacySession:
    def __init__(self):
        self.calibration = DummyCalibration()
        self.pulse_mgr = DummyPulse()
        self.hw = DummyHardware()
        self.orchestrator = DummyOrchestrator()

    def context_snapshot(self):
        return type(
            "Ctx",
            (),
            {
                "qb_el": "transmon",
                "ro_el": "resonator",
                "st_el": "storage",
                "qb_fq": 6.15e9,
                "ro_fq": 8.60e9,
                "st_fq": 5.35e9,
                "anharmonicity": -250e6,
            },
        )()

    def get_therm_clks(self, channel, default=None):
        return {"qubit": 2500, "qb": 2500, "readout": 1200}.get(channel, default)


class DummyBackend:
    def __init__(self):
        self.requests = []

    def run(self, request):
        self.requests.append(("run", request))
        return request

    def build(self, request):
        self.requests.append(("build", request))
        return request


def make_session() -> Session:
    session = Session(DummyLegacySession())
    session._backend = DummyBackend()
    return session


def test_session_open_uses_configured_session_manager_class(monkeypatch):
    calls = {}

    class DummyManager:
        def __init__(self, **kwargs):
            calls["kwargs"] = kwargs

        def open(self):
            calls["opened"] = True

    monkeypatch.setattr(Session, "session_manager_cls", DummyManager)
    session = Session.open(sample_id="sampleA", cooldown_id="cd1", connect=True, registry_base="E:/qubox")
    assert isinstance(session, Session)
    assert isinstance(session.session_manager, DummyManager)
    assert calls["kwargs"]["sample_id"] == "sampleA"
    assert calls["kwargs"]["cooldown_id"] == "cd1"
    assert calls["opened"] is True


def test_sequence_and_operation_library_are_available_without_qm():
    session = make_session()
    seq = session.sequence("demo")
    seq.add(session.ops.x90("q0"))
    seq.add(session.ops.wait("q0", 200))
    seq.add(session.ops.virtual_z("q0", phase=0.25))
    assert seq.name == "demo"
    assert [op.kind for op in seq.operations] == ["qubit_rotation", "idle", "frame_update"]
    assert session.resolve_alias("q0", role_hint="qubit") == "transmon"
    assert session.resolve_alias("rr0", role_hint="readout") == "resonator"


def test_custom_request_uses_sequence_and_sweep_plan():
    session = make_session()
    seq = session.sequence("ramsey_custom")
    seq.add(session.ops.x90("q0"))
    seq.add(session.ops.wait("q0", 200))
    seq.add(session.ops.measure("rr0", mode="iq"))
    sweep = session.sweep.param("wait.duration").values([100, 200, 400])

    request = session.exp.custom(sequence=seq, sweep=sweep, analysis="ramsey_like", n_avg=11)
    assert isinstance(request, ExecutionRequest)
    assert request.kind == "custom"
    assert request.template == "ramsey_custom"
    assert request.analysis == "ramsey_like"
    assert request.shots == 11
    assert request.sweep.axes[0].parameter == "wait.duration"


def test_control_program_helpers_are_available_without_qm():
    session = make_session()
    seq = session.sequence("control_seq")
    seq.add(session.ops.x90("q0"))

    converted = session.to_control_program(seq)
    realized = session.realize_control_program(seq)
    manual = session.control_program("manual_native").append(
        PulseInstruction(targets=("q0",), operation="x90", duration=ControlDuration(16))
    )
    request = session.exp.custom(control=manual, execute=False)

    assert converted.name == "control_seq"
    assert realized.instructions[0].kind == "pulse"
    assert realized.instructions[0].operation == "x90"
    assert realized.instructions[0].targets == ("transmon",)
    assert request.control_program is manual
    assert request.template == "manual_native"
    assert session.to_control_program(manual) is manual


def test_standard_template_request_is_canonical():
    session = make_session()
    freq = session.sweep.linspace(-30e6, 30e6, 5, center="q0.ge")
    request = session.exp.qubit.spectroscopy(
        qubit="q0",
        readout="rr0",
        freq=freq,
        drive_amp=0.02,
        n_avg=123,
    )
    assert isinstance(request, ExecutionRequest)
    assert request.kind == "template"
    assert request.template == "qubit.spectroscopy"
    assert request.targets == {"qubit": "q0", "readout": "rr0"}
    assert request.shots == 123


def test_result_proposal_round_trip():
    session = make_session()
    result = ExperimentResult(
        request=ExecutionRequest(kind="template", template="qubit.spectroscopy"),
        analysis=type(
            "Analysis",
            (),
            {
                "metadata": {
                    "proposed_patch_ops": [
                        {
                            "op": "SetCalibration",
                            "payload": {"path": "cqed_params.transmon.qubit_freq", "value": 6.152e9},
                        }
                    ]
                }
            },
        )(),
    )
    proposal = result.proposal()
    assert isinstance(proposal, CalibrationProposal)
    preview = proposal.apply(session, dry_run=True)
    assert preview["dry_run"] is True
    assert preview["n_updates"] == 1


def test_notebook_surface_is_lazy():
    assert "QubitSpectroscopy" in notebook.__all__
    assert "ReadoutHandle" in notebook.__all__
    assert "MeasurementConfig" in notebook.__all__
    assert "PostSelectionConfig" in notebook.__all__
    assert "RunResult" in notebook.__all__
    assert "save_run_summary" in notebook.__all__
    assert "HardwareDefinition" in notebook.__all__
    assert "open_shared_session" in notebook.__all__
    assert "require_shared_session" in notebook.__all__
    assert "resolve_active_mixer_targets" in notebook.__all__
    assert "open_notebook_stage" in notebook.__all__
    assert "save_stage_checkpoint" in notebook.__all__
    assert "preview_or_apply_patch_ops" in notebook.__all__
    assert "ensure_primitive_rotations" in notebook.__all__
