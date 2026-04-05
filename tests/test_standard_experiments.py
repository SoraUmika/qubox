"""Tests for the 20 standard experiment templates.

Each test verifies that:
1. The correct template name is routed
2. The ExecutionRequest is well-formed (kind, template, targets, shots)
3. All sub-libraries are accessible on ExperimentLibrary
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qubox import Session
from qubox.data import ExecutionRequest
from qubox.experiments.templates.library import (
    CalibrationExperimentLibrary,
    ExperimentLibrary,
    ReadoutExperimentLibrary,
    StorageExperimentLibrary,
    TomographyExperimentLibrary,
)


# ---------------------------------------------------------------------------
# Test infrastructure (reused from test_qubox_public_api.py)
# ---------------------------------------------------------------------------

class DummyCalibration:
    path = "calibration.json"

    def to_dict(self):
        return {"version": "5.1.0", "cqed_params": {"transmon": {"qubit_freq": 6.1e9}}}

    def get_discrimination(self, readout):
        return type("Disc", (), {"threshold": 0.12, "angle": 0.34})()


class DummyPulse:
    def get_pulseOp_by_element_op(self, target, op, strict=False):
        return type("Pulse", (), {"length": 32})()


class DummyHardware:
    elements = {"transmon": {}, "resonator": {}, "storage": {}}


class DummyLegacySession:
    def __init__(self):
        self.calibration = DummyCalibration()
        self.pulse_mgr = DummyPulse()
        self.hw = DummyHardware()

    def context_snapshot(self):
        return type(
            "Ctx", (),
            {
                "qb_el": "transmon", "ro_el": "resonator", "st_el": "storage",
                "qb_fq": 6.15e9, "ro_fq": 8.60e9, "st_fq": 5.35e9,
                "anharmonicity": -250e6,
            },
        )()

    def get_therm_clks(self, channel, default=None):
        return {"qubit": 2500, "readout": 1200}.get(channel, default)


class DummyBackend:
    """Records requests instead of running them."""

    def __init__(self):
        self.requests: list[tuple[str, ExecutionRequest]] = []

    def run(self, request: ExecutionRequest):
        self.requests.append(("run", request))
        return request

    def build(self, request: ExecutionRequest):
        self.requests.append(("build", request))
        return request


def make_session() -> Session:
    session = Session(DummyLegacySession())
    session._backend = DummyBackend()
    return session


# ---------------------------------------------------------------------------
# Sub-library availability
# ---------------------------------------------------------------------------

def test_experiment_library_has_all_sub_libraries():
    session = make_session()
    exp = session.exp
    assert isinstance(exp, ExperimentLibrary)
    assert isinstance(exp.readout, ReadoutExperimentLibrary)
    assert isinstance(exp.calibration, CalibrationExperimentLibrary)
    assert isinstance(exp.storage, StorageExperimentLibrary)
    assert isinstance(exp.tomography, TomographyExperimentLibrary)
    assert hasattr(exp, "qubit")
    assert hasattr(exp, "resonator")
    assert hasattr(exp, "reset")


# ---------------------------------------------------------------------------
# 1. Readout Trace
# ---------------------------------------------------------------------------

def test_readout_trace():
    session = make_session()
    result = session.exp.readout.trace(readout="rr0", drive_frequency=8.61e9, n_avg=500)
    assert isinstance(result, ExecutionRequest)
    assert result.template == "readout.trace"
    assert result.targets == {"readout": "rr0"}
    assert result.shots == 500


# ---------------------------------------------------------------------------
# 2. Resonator Spectroscopy (existing)
# ---------------------------------------------------------------------------

def test_resonator_spectroscopy():
    session = make_session()
    freq = session.sweep.linspace(-5e6, 5e6, 11, center="readout")
    result = session.exp.resonator.spectroscopy(readout="rr0", freq=freq, n_avg=200)
    assert result.template == "resonator.spectroscopy"
    assert result.shots == 200


# ---------------------------------------------------------------------------
# 3. Resonator Power Spectroscopy
# ---------------------------------------------------------------------------

def test_resonator_power_spectroscopy():
    session = make_session()
    freq = session.sweep.linspace(-5e6, 5e6, 11, center="readout")
    result = session.exp.resonator.power_spectroscopy(
        readout="rr0", freq=freq, gain_min=1e-3, gain_max=0.5, n_avg=100,
    )
    assert isinstance(result, ExecutionRequest)
    assert result.template == "resonator.power_spectroscopy"
    assert result.shots == 100


# ---------------------------------------------------------------------------
# 4. Qubit Spectroscopy (existing)
# ---------------------------------------------------------------------------

def test_qubit_spectroscopy():
    session = make_session()
    freq = session.sweep.linspace(-30e6, 30e6, 5, center="q0.ge")
    result = session.exp.qubit.spectroscopy(
        qubit="q0", readout="rr0", freq=freq, drive_amp=0.02, n_avg=200,
    )
    assert result.template == "qubit.spectroscopy"
    assert result.targets == {"qubit": "q0", "readout": "rr0"}


# ---------------------------------------------------------------------------
# 5. Temporal Rabi
# ---------------------------------------------------------------------------

def test_temporal_rabi():
    session = make_session()
    dur = session.sweep.linspace(4, 200, 50, parameter="duration")
    result = session.exp.qubit.temporal_rabi(
        qubit="q0", readout="rr0", duration=dur, pulse="x180", n_avg=1000,
    )
    assert result.template == "qubit.temporal_rabi"
    assert result.shots == 1000


# ---------------------------------------------------------------------------
# 6. Power Rabi (existing)
# ---------------------------------------------------------------------------

def test_power_rabi():
    session = make_session()
    amp = session.sweep.linspace(0.01, 1.0, 50, parameter="amplitude")
    result = session.exp.qubit.power_rabi(
        qubit="q0", readout="rr0", amplitude=amp, n_avg=500,
    )
    assert result.template == "qubit.power_rabi"
    assert result.shots == 500


# ---------------------------------------------------------------------------
# 7. Time Rabi Chevron
# ---------------------------------------------------------------------------

def test_time_rabi_chevron():
    session = make_session()
    result = session.exp.qubit.time_rabi_chevron(
        qubit="q0", readout="rr0",
        freq_span=10e6, df=100e3, max_duration=200, dt=4, n_avg=500,
    )
    assert result.template == "qubit.time_rabi_chevron"
    assert result.shots == 500
    assert result.params["freq_span"] == 10e6
    assert result.params["max_duration"] == 200


# ---------------------------------------------------------------------------
# 8. Power Rabi Chevron
# ---------------------------------------------------------------------------

def test_power_rabi_chevron():
    session = make_session()
    result = session.exp.qubit.power_rabi_chevron(
        qubit="q0", readout="rr0",
        freq_span=10e6, df=100e3, max_gain=1.0, dg=0.02, n_avg=500,
    )
    assert result.template == "qubit.power_rabi_chevron"
    assert result.params["max_gain"] == 1.0


# ---------------------------------------------------------------------------
# 9. T1 Relaxation
# ---------------------------------------------------------------------------

def test_t1():
    session = make_session()
    delay = session.sweep.linspace(4, 40000, 100, parameter="delay")
    result = session.exp.qubit.t1(qubit="q0", readout="rr0", delay=delay, n_avg=1000)
    assert result.template == "qubit.t1"
    assert result.shots == 1000


# ---------------------------------------------------------------------------
# 10. T2 Ramsey (existing)
# ---------------------------------------------------------------------------

def test_ramsey():
    session = make_session()
    delay = session.sweep.linspace(4, 2000, 100, parameter="delay")
    result = session.exp.qubit.ramsey(
        qubit="q0", readout="rr0", delay=delay, detuning=0.5e6, n_avg=500,
    )
    assert result.template == "qubit.ramsey"
    assert result.params["detuning"] == 0.5e6


# ---------------------------------------------------------------------------
# 11. T2 Echo
# ---------------------------------------------------------------------------

def test_echo():
    session = make_session()
    delay = session.sweep.linspace(8, 4000, 100, parameter="delay")
    result = session.exp.qubit.echo(qubit="q0", readout="rr0", delay=delay, n_avg=1000)
    assert result.template == "qubit.echo"
    assert result.shots == 1000


# ---------------------------------------------------------------------------
# 12. IQ Blobs
# ---------------------------------------------------------------------------

def test_iq_blobs():
    session = make_session()
    result = session.exp.readout.iq_blobs(qubit="q0", readout="rr0", n_runs=2000)
    assert result.template == "readout.iq_blobs"
    assert result.shots == 2000


# ---------------------------------------------------------------------------
# 13. AllXY
# ---------------------------------------------------------------------------

def test_all_xy():
    session = make_session()
    result = session.exp.calibration.all_xy(qubit="q0", readout="rr0", n_avg=1000)
    assert result.template == "calibration.all_xy"
    assert result.shots == 1000


# ---------------------------------------------------------------------------
# 14. DRAG Calibration
# ---------------------------------------------------------------------------

def test_drag():
    session = make_session()
    amps = np.linspace(-0.5, 0.5, 51)
    result = session.exp.calibration.drag(qubit="q0", readout="rr0", amps=amps, n_avg=500)
    assert result.template == "calibration.drag"
    assert result.shots == 500
    assert np.array_equal(result.params["amps"], amps)


# ---------------------------------------------------------------------------
# 15. Readout Butterfly
# ---------------------------------------------------------------------------

def test_butterfly():
    session = make_session()
    result = session.exp.readout.butterfly(qubit="q0", readout="rr0", n_samples=10_000)
    assert result.template == "readout.butterfly"
    assert result.shots == 10_000


# ---------------------------------------------------------------------------
# 16. Qubit State Tomography
# ---------------------------------------------------------------------------

def test_qubit_state_tomography():
    session = make_session()

    def my_prep():
        pass

    result = session.exp.tomography.qubit_state(
        qubit="q0", readout="rr0", state_prep=my_prep, n_avg=1000,
    )
    assert result.template == "tomography.qubit_state"
    assert result.params["state_prep"] is my_prep


# ---------------------------------------------------------------------------
# 17. Storage Spectroscopy
# ---------------------------------------------------------------------------

def test_storage_spectroscopy():
    session = make_session()
    freq = session.sweep.linspace(-5e6, 5e6, 101, center="q0.ge")
    result = session.exp.storage.spectroscopy(
        qubit="q0", readout="rr0", storage="st0",
        freq=freq, disp="disp_n1", storage_therm_time=50000, n_avg=500,
    )
    assert result.template == "storage.spectroscopy"
    assert result.targets == {"qubit": "q0", "readout": "rr0", "storage": "st0"}
    assert result.params["disp"] == "disp_n1"


# ---------------------------------------------------------------------------
# 18. Storage T1 Decay
# ---------------------------------------------------------------------------

def test_storage_t1_decay():
    session = make_session()
    delay = session.sweep.linspace(4, 40000, 100, parameter="delay")
    result = session.exp.storage.t1_decay(
        qubit="q0", readout="rr0", storage="st0",
        delay=delay, fock_fqs=[5.123e9], fock_disps=["disp_n1"], n_avg=500,
    )
    assert result.template == "storage.t1_decay"
    assert "storage" in result.targets


# ---------------------------------------------------------------------------
# 19. Number Splitting Spectroscopy
# ---------------------------------------------------------------------------

def test_num_splitting():
    session = make_session()
    result = session.exp.storage.num_splitting(
        qubit="q0", readout="rr0", storage="st0",
        rf_centers=[5.1e9, 5.09e9], rf_spans=[2e6, 2e6], df=50e3, n_avg=500,
    )
    assert result.template == "storage.num_splitting"
    assert result.params["rf_centers"] == [5.1e9, 5.09e9]


# ---------------------------------------------------------------------------
# 20. Wigner Tomography
# ---------------------------------------------------------------------------

def test_wigner_tomography():
    session = make_session()

    def state_prep():
        pass

    x = np.linspace(-3, 3, 21)
    p = np.linspace(-3, 3, 21)
    result = session.exp.tomography.wigner(
        qubit="q0", readout="rr0", storage="st0",
        state_prep=state_prep, x_vals=x, p_vals=p,
        base_alpha=10.0, n_avg=200,
    )
    assert result.template == "tomography.wigner"
    assert result.params["state_prep"] is state_prep
    assert result.shots == 200


# ---------------------------------------------------------------------------
# Active Reset (existing, still works)
# ---------------------------------------------------------------------------

def test_active_reset():
    session = make_session()
    result = session.exp.reset.active(qubit="q0", readout="rr0", threshold="calibrated", n_avg=200)
    assert result.template == "reset.active"
    assert result.shots == 200


# ---------------------------------------------------------------------------
# Adapter registry completeness
# ---------------------------------------------------------------------------

EXPECTED_TEMPLATES = [
    "readout.trace",
    "resonator.spectroscopy",
    "resonator.power_spectroscopy",
    "qubit.spectroscopy",
    "qubit.temporal_rabi",
    "qubit.power_rabi",
    "qubit.time_rabi_chevron",
    "qubit.power_rabi_chevron",
    "qubit.t1",
    "qubit.ramsey",
    "qubit.echo",
    "readout.iq_blobs",
    "calibration.all_xy",
    "calibration.drag",
    "readout.butterfly",
    "tomography.qubit_state",
    "storage.spectroscopy",
    "storage.t1_decay",
    "storage.num_splitting",
    "tomography.wigner",
    "reset.active",
]


import pytest


def _has_qm_sdk() -> bool:
    try:
        import qm  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.mark.skipif(
    not _has_qm_sdk(),
    reason="Requires qm SDK for legacy adapter imports",
)
def test_all_standard_templates_registered():
    from qubox.backends.qm.runtime import _load_adapters

    adapters = _load_adapters()
    for tmpl in EXPECTED_TEMPLATES:
        assert tmpl in adapters, f"Template {tmpl!r} not found in adapter registry"
    assert len(adapters) >= len(EXPECTED_TEMPLATES)
