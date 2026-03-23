from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from qubox.analysis.cQED_attributes import cQED_attributes
from qubox.calibration.store import CalibrationStore
from qubox.experiments.calibration.gates import AllXY
from qubox.experiments.calibration.readout import IQBlob
from qubox.experiments.cavity.storage import NumSplittingSpectroscopy
from qubox.experiments.spectroscopy.qubit import QubitSpectroscopy
from qubox.experiments.spectroscopy.resonator import ResonatorSpectroscopy
from qubox.experiments.time_domain.coherence import T2Ramsey
from qubox.experiments.time_domain.rabi import PowerRabi
from qubox.programs.circuit_runner import CircuitRunner, Gate, QuantumCircuit


class _FakeHW:
    def __init__(self) -> None:
        self.elements = {"qubit": {}, "resonator": {}, "storage": {}}
        self._fq: dict[str, float] = {}

    def set_element_fq(self, element: str, fq: float) -> None:
        self._fq[element] = float(fq)

    def get_element_lo(self, element: str) -> float:
        return {"qubit": 6.0e9, "resonator": 8.8e9, "storage": 7.2e9}.get(element, 0.0)

    def get_element_if(self, element: str) -> float:
        return self._fq.get(element, 0.0) - self.get_element_lo(element)


class _FakePulseInfo:
    def __init__(self, length: int = 64) -> None:
        self.length = length
        self.I_wf = np.ones(length)
        self.Q_wf = np.zeros(length)
        self.op = "readout"
        self.int_weights_mapping = {
            "cos": "cos",
            "sin": "sin",
            "minus_sin": "minus_sin",
        }


class _FakePulseMgr:
    def get_pulseOp_by_element_op(self, element: str, op: str, strict: bool = True):
        return _FakePulseInfo()


class _FakeCtx:
    def __init__(self, calibration: CalibrationStore) -> None:
        self.calibration = calibration
        self.hw = _FakeHW()
        self.pulseOpMngr = _FakePulseMgr()
        self.bindings = SimpleNamespace(
            qubit=SimpleNamespace(lo_frequency=6.0e9),
            readout=SimpleNamespace(
                drive_out=SimpleNamespace(lo_frequency=8.8e9),
                drive_frequency=8.6e9,
            ),
            storage=None,
        )
        self.experiment_path = Path(".")

    def context_snapshot(self) -> cQED_attributes:
        return cQED_attributes(qb_el="qubit", ro_el="resonator", st_el="storage")


def _make_ctx(
    tmp_path: Path,
    *,
    qb_therm_clks: int | None = 4321,
    ro_therm_clks: int | None = 2468,
    st_therm_clks: int | None = 1357,
    qubit_freq: float = 6.15e9,
    resonator_freq: float = 8.6e9,
    storage_freq: float = 7.15e9,
) -> _FakeCtx:
    store = CalibrationStore(tmp_path / "calibration.json")
    store.set_cqed_params("transmon", qubit_freq=qubit_freq, qb_therm_clks=qb_therm_clks)
    store.set_cqed_params("resonator", resonator_freq=resonator_freq, ro_therm_clks=ro_therm_clks, lo_freq=8.8e9)
    store.set_cqed_params("storage", storage_freq=storage_freq, st_therm_clks=st_therm_clks)
    store.save()
    return _FakeCtx(store)


def test_allxy_override_beats_calibration(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "qubox_v2.experiments.calibration.gates.cQED_programs.all_xy",
        lambda *args, **kwargs: ("all_xy", args, kwargs),
    )
    exp = AllXY(_make_ctx(tmp_path, qb_therm_clks=5000))

    build = exp.build_program(qb_therm_clks=1234, n_avg=16)

    assert build.params["qb_therm_clks"] == 1234
    assert build.resolved_parameter_sources["qb_therm_clks"]["source"] == "override"


def test_power_rabi_uses_calibration_when_no_override(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "qubox_v2.experiments.time_domain.rabi.cQED_programs.power_rabi",
        lambda *args, **kwargs: ("power_rabi", args, kwargs),
    )
    exp = PowerRabi(_make_ctx(tmp_path, qb_therm_clks=6789))

    build = exp.build_program(
        max_gain=0.1,
        dg=0.05,
        op="ge_ref_r180",
        n_avg=8,
        use_circuit_runner=False,
    )

    assert build.params["qb_therm_clks"] == 6789
    assert build.resolved_parameter_sources["qb_therm_clks"]["source"] == "calibration"


def test_power_rabi_missing_calibration_raises_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "qubox_v2.experiments.time_domain.rabi.cQED_programs.power_rabi",
        lambda *args, **kwargs: ("power_rabi", args, kwargs),
    )
    exp = PowerRabi(_make_ctx(tmp_path, qb_therm_clks=None))

    with pytest.raises(ValueError, match="qb_therm_clks"):
        exp.build_program(
            max_gain=0.1,
            dg=0.05,
            op="ge_ref_r180",
            n_avg=8,
            use_circuit_runner=False,
        )


def test_allxy_missing_calibration_raises_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "qubox_v2.experiments.calibration.gates.cQED_programs.all_xy",
        lambda *args, **kwargs: ("all_xy", args, kwargs),
    )
    exp = AllXY(_make_ctx(tmp_path, qb_therm_clks=None))

    with pytest.raises(ValueError, match="qb_therm_clks"):
        exp.build_program(n_avg=8)


def test_resonator_spectroscopy_override_beats_calibration(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "qubox_v2.experiments.spectroscopy.resonator.cQED_programs.resonator_spectroscopy",
        lambda *args, **kwargs: ("res_spec", args, kwargs),
    )
    exp = ResonatorSpectroscopy(_make_ctx(tmp_path, ro_therm_clks=3000))

    build = exp.build_program(
        readout_op="readout",
        rf_begin=8.59e9,
        rf_end=8.60e9,
        df=1.0e6,
        n_avg=4,
        ro_therm_clks=111,
    )

    assert build.params["ro_therm_clks"] == 111
    assert build.resolved_parameter_sources["ro_therm_clks"]["source"] == "override"


def test_t2_ramsey_uses_calibration_when_no_override(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "qubox_v2.experiments.time_domain.coherence.cQED_programs.T2_ramsey",
        lambda *args, **kwargs: ("t2_ramsey", args, kwargs),
    )
    exp = T2Ramsey(_make_ctx(tmp_path, qb_therm_clks=3456))

    build = exp.build_program(
        r90="ge_x90",
        qb_detune=1_000_000,
        delay_begin=16,
        delay_end=64,
        dt=16,
        n_avg=4,
    )

    assert build.params["qb_therm_clks"] == 3456
    assert build.resolved_parameter_sources["qb_therm_clks"]["source"] == "calibration"


def test_qubit_spectroscopy_uses_calibration_when_no_override(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "qubox_v2.experiments.spectroscopy.qubit.cQED_programs.qubit_spectroscopy",
        lambda *args, **kwargs: ("qb_spec", args, kwargs),
    )
    exp = QubitSpectroscopy(_make_ctx(tmp_path, qb_therm_clks=2222))

    build = exp.build_program(
        pulse="x180",
        rf_begin=5.95e9,
        rf_end=5.96e9,
        df=1.0e6,
        qb_gain=0.1,
        qb_len=64,
        n_avg=4,
    )

    assert build.params["qb_therm_clks"] == 2222
    assert build.resolved_parameter_sources["qb_therm_clks"]["source"] == "calibration"


def test_num_splitting_uses_storage_calibration_when_no_override(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "qubox_v2.experiments.cavity.storage.cQED_programs.num_splitting_spectroscopy",
        lambda *args, **kwargs: ("num_split", args, kwargs),
    )
    exp = NumSplittingSpectroscopy(_make_ctx(tmp_path, st_therm_clks=7777))

    build = exp.build_program(
        rf_centers=[6.11e9],
        rf_spans=[1.0e6],
        df=0.5e6,
        n_avg=4,
        state_prep=lambda: None,
    )

    assert build.params["st_therm_clks"] == 7777
    assert build.resolved_parameter_sources["st_therm_clks"]["source"] == "calibration"


def test_iq_blob_missing_calibration_raises_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "qubox_v2.experiments.calibration.readout.cQED_programs.iq_blobs",
        lambda *args, **kwargs: ("iq_blobs", args, kwargs),
    )
    exp = IQBlob(_make_ctx(tmp_path, qb_therm_clks=None))

    with pytest.raises(ValueError, match="qb_therm_clks"):
        exp.build_program(n_runs=8)


def test_circuit_runner_xy_pair_requires_resolved_qb_therm_clks(tmp_path):
    runner = CircuitRunner(_make_ctx(tmp_path))
    circuit = QuantumCircuit(
        name="xy_pair",
        gates=(Gate(name="xy", target="qubit"),),
        metadata={"qb_el": "qubit", "n_avg": 8},
    )

    with pytest.raises(ValueError, match="qb_therm_clks"):
        runner.compile(circuit)
