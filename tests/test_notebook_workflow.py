from __future__ import annotations

from pathlib import Path

import numpy as np

from qubox.compat import notebook_workflow


class FakeRegistry:
    def __init__(self, base):
        self.base = Path(base)

    def cooldown_path(self, sample_id: str, cooldown_id: str) -> Path:
        return self.base / sample_id / "cooldowns" / cooldown_id


def test_save_stage_checkpoint_serializes_numpy_scalars(monkeypatch, tmp_path):
    monkeypatch.setattr(notebook_workflow, "SampleRegistry", FakeRegistry)

    path = notebook_workflow.save_stage_checkpoint(
        registry_base=tmp_path,
        sample_id="sampleA",
        cooldown_id="cd1",
        stage_name="05_qubit_spectroscopy_pulse_calibration",
        status="calibrated",
        summary="checkpoint",
        advisory_outputs={"f0": np.float64(6.1e9)},
        metrics={"g_pi": np.float32(0.81)},
    )
    payload = notebook_workflow.load_stage_checkpoint(
        registry_base=tmp_path,
        sample_id="sampleA",
        cooldown_id="cd1",
        stage_name="05_qubit_spectroscopy_pulse_calibration",
    )

    assert path.exists()
    assert payload is not None
    assert payload["advisory_outputs"]["f0"] == 6.1e9
    assert payload["metrics"]["g_pi"] == np.float32(0.81).item()


def test_preview_or_apply_patch_ops_calls_orchestrator(monkeypatch):
    calls: list[tuple[object, bool]] = []

    class FakeOrchestrator:
        def __init__(self, session_obj):
            self.session_obj = session_obj

        def apply_patch(self, patch, dry_run=True):
            calls.append((patch, dry_run))
            return {
                "dry_run": dry_run,
                "n_updates": len(patch.updates),
                "preview": [{"op": update.op, "payload": update.payload} for update in patch.updates],
                "sync_ok": True,
            }

    monkeypatch.setattr(notebook_workflow, "CalibrationOrchestrator", FakeOrchestrator)

    patch, preview, apply_result = notebook_workflow.preview_or_apply_patch_ops(
        object(),
        reason="Apply test patch",
        proposed_patch_ops=[
            {
                "op": "SetCalibration",
                "payload": {"path": "cqed_params.transmon.qubit_freq", "value": 6.15e9},
            }
        ],
        apply=True,
        print_fn=lambda *_args, **_kwargs: None,
    )

    assert patch is not None
    assert preview is not None
    assert apply_result is not None
    assert [dry_run for _, dry_run in calls] == [True, False]


def test_ensure_primitive_rotations_registers_missing_ops(monkeypatch):
    class DummyPulseManager:
        def __init__(self):
            self.created = []

        def get_pulseOp_by_element_op(self, element, op, strict=False):
            if strict and op in {"x180", "x90"}:
                raise KeyError(op)
            return object()

        def create_control_pulse(self, **kwargs):
            self.created.append(kwargs)

    class DummySession:
        def __init__(self):
            self.pulse_mgr = DummyPulseManager()
            self.burn_calls = []

        def burn_pulses(self, include_volatile=True):
            self.burn_calls.append(include_volatile)

    monkeypatch.setattr(notebook_workflow, "drag_gaussian_pulse_waveforms", lambda **_kwargs: ([0.1, 0.2], [0.0, 0.0]))
    monkeypatch.setattr(
        notebook_workflow,
        "register_rotations_from_ref_iq",
        lambda *_args, **_kwargs: ["ref_r180", "x180", "x90"],
    )

    session = DummySession()
    result = notebook_workflow.ensure_primitive_rotations(
        session,
        qb_element="transmon",
        amplitude=0.1,
        length=16,
        sigma=2.0,
        alpha=0.0,
        anharmonicity_hz=-255e6,
    )

    assert result["created"] is True
    assert result["created_ops"] == ["ref_r180", "x180", "x90"]
    assert session.burn_calls == [True]
    assert session.pulse_mgr.created[0]["op"] == "ref_r180"