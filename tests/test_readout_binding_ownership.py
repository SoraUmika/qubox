from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from qubox.calibration.store import CalibrationStore
from qubox.core.bindings import (
    ChannelRef,
    InputBinding,
    OutputBinding,
    ReadoutBinding,
    ReadoutCal,
    ReadoutHandle,
)
from qubox.core.measurement_config import MeasurementConfig
from qubox.core.pulse_op import PulseOp
from qubox.experiments.experiment_base import ExperimentBase


def _make_readout_binding(*, active_op: str = "readout") -> ReadoutBinding:
    pulse_op = PulseOp(
        element="resonator",
        op=active_op,
        pulse="readout_pulse",
        type="measurement",
        length=96,
        int_weights_mapping={
            "rot_cos": "rot_cosine_weights",
            "rot_sin": "rot_sine_weights",
            "rot_m_sin": "rot_minus_sine_weights",
        },
    )
    return ReadoutBinding(
        drive_out=OutputBinding(
            channel=ChannelRef("oct1", "RF_out", 1),
            lo_frequency=7.9e9,
        ),
        acquire_in=InputBinding(
            channel=ChannelRef("oct1", "RF_in", 1),
            lo_frequency=7.9e9,
        ),
        pulse_op=pulse_op,
        active_op=active_op,
        demod_weight_sets=[["rot_cos", "rot_sin"], ["rot_m_sin", "rot_cos"]],
        discrimination={
            "threshold": 0.12,
            "angle": 0.34,
            "fidelity": 96.5,
            "fidelity_definition": "balanced_assignment",
            "sigma_g": 0.01,
            "sigma_e": 0.02,
        },
        quality={
            "F": 97.0,
            "confusion_matrix": np.asarray(((0.98, 0.02), (0.03, 0.97))),
        },
        drive_frequency=8.15e9,
        gain=0.7,
    )


def test_readout_binding_sync_accepts_alias_lookup_keys(tmp_path) -> None:
    store = CalibrationStore(tmp_path / "calibration.json")
    store.register_alias("resonator", "oct1:RF_in:1")
    store.set_discrimination(
        "resonator",
        threshold=0.23,
        angle=0.45,
        fidelity=95.0,
        fidelity_definition="balanced_assignment",
        mu_g=(0.1, -0.2),
        mu_e=(0.3, 0.4),
        sigma_g=0.11,
        sigma_e=0.22,
    )
    store.set_readout_quality(
        "resonator",
        F=94.0,
        confusion_matrix=((0.9, 0.1), (0.2, 0.8)),
    )

    binding = _make_readout_binding()
    binding.sync_from_calibration(store, lookup_keys=("resonator",))

    assert binding.discrimination["threshold"] == pytest.approx(0.23)
    assert binding.discrimination["angle"] == pytest.approx(0.45)
    assert binding.discrimination["fidelity_definition"] == "balanced_assignment"
    assert binding.discrimination["sigma_g"] == pytest.approx(0.11)
    assert np.allclose(binding.quality["confusion_matrix"], np.asarray(((0.9, 0.1), (0.2, 0.8))))

    cal = ReadoutCal.from_calibration_store(
        store,
        ("resonator", binding.physical_id),
        drive_freq=8.15e9,
    )
    assert cal.threshold == pytest.approx(0.23)
    assert cal.fidelity == pytest.approx(94.0)
    assert cal.sigma_e == pytest.approx(0.22)


def test_measurement_config_round_trip_preserves_explicit_readout_handle_state() -> None:
    binding = _make_readout_binding(active_op="readout_rotated")
    cal = ReadoutCal.from_readout_binding(binding)
    handle = ReadoutHandle(
        binding=binding,
        cal=cal,
        element="resonator",
        operation="readout_rotated",
        gain=binding.gain,
        demod_weight_sets=(("rot_cos", "rot_sin"), ("rot_m_sin", "rot_cos")),
    )

    config = MeasurementConfig.from_readout_handle(handle, source="unit_test")
    round_trip = MeasurementConfig.from_dict(config.to_dict())

    assert round_trip.operation == "readout_rotated"
    assert round_trip.drive_frequency == pytest.approx(8.15e9)
    assert round_trip.weight_sets == (("rot_cos", "rot_sin"), ("rot_m_sin", "rot_cos"))
    assert round_trip.threshold == pytest.approx(0.12)
    assert round_trip.fidelity_definition == "balanced_assignment"
    assert np.allclose(
        np.asarray(round_trip.confusion_matrix),
        np.asarray(((0.98, 0.02), (0.03, 0.97))),
    )


def test_experiment_base_readout_handle_prefers_binding_active_operation() -> None:
    binding = _make_readout_binding(active_op="custom_readout")
    cal = ReadoutCal.from_readout_binding(binding)
    base_handle = ReadoutHandle(
        binding=binding,
        cal=cal,
        element="resonator",
        operation="custom_readout",
        gain=binding.gain,
        demod_weight_sets=(("rot_cos", "rot_sin"), ("rot_m_sin", "rot_cos")),
    )
    calls: list[tuple[str, str]] = []

    class _StubPulseManager:
        @staticmethod
        def get_pulseOp_by_element_op(element: str, operation: str, strict: bool = False) -> PulseOp | None:
            _ = strict
            if element == "resonator" and operation == "custom_readout":
                return binding.pulse_op
            return None

    class _StubSession:
        pulse_mgr = _StubPulseManager()
        bindings = SimpleNamespace(readout=binding)

        @staticmethod
        def context_snapshot():
            return SimpleNamespace(ro_el="resonator")

        @staticmethod
        def readout_handle(alias: str = "resonator", operation: str = "readout") -> ReadoutHandle:
            calls.append((alias, operation))
            return base_handle

    experiment = ExperimentBase(_StubSession())
    readout = experiment.readout_handle

    assert calls == [("resonator", "custom_readout")]
    assert readout.operation == "custom_readout"
    assert readout.cal.weight_keys == ("rot_cos", "rot_sin", "rot_m_sin")
    assert readout.cal.drive_frequency == pytest.approx(8.15e9)
