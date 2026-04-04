from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import numpy as np

from qubox.calibration.store import CalibrationStore
from qubox.core.bindings import (
    ChannelRef,
    ExperimentBindings,
    InputBinding,
    OutputBinding,
    ReadoutBinding,
    ReadoutCal,
    ReadoutHandle,
)
from qubox.core.pulse_op import PulseOp
from qubox.experiments.spectroscopy.resonator import ResonatorSpectroscopy
from qm.exceptions import QMSimulationError
from tools.validate_standard_experiments_simulation import (
    DEFAULT_QB_THERM,
    DEFAULT_RO_THERM,
    DEFAULT_ST_THERM,
    _build_waveform_metadata_samples,
    _build_waveform_report_samples,
    inject_calibration_data,
    register_simulation_pulses,
    simulate_program,
)


class _FakeReadoutBinding:
    def __init__(self) -> None:
        self.sync_calls = 0
        self.last_lookup_keys = None
        self.pulse_op = None
        self.active_op = None
        self.drive_frequency = None

    def sync_from_calibration(self, cal_store, lookup_keys=None) -> None:
        _ = cal_store
        self.sync_calls += 1
        self.last_lookup_keys = lookup_keys


def test_inject_calibration_data_updates_store_and_syncs_binding(tmp_path) -> None:
    calibration = CalibrationStore(tmp_path / "calibration.json")
    readout_binding = _FakeReadoutBinding()
    attr = SimpleNamespace(
        qb_el="transmon_sim",
        ro_el="resonator_sim",
        st_el="storage_sim",
    )
    session = SimpleNamespace(
        calibration=calibration,
        context_snapshot=lambda: attr,
        bindings=SimpleNamespace(readout=readout_binding),
    )

    inject_calibration_data(session)

    disc = calibration.get_discrimination(attr.ro_el)
    ro_freqs = calibration.get_frequencies(attr.ro_el)
    qb_params = calibration.get_cqed_params(attr.qb_el)
    st_params = calibration.get_cqed_params(attr.st_el)

    assert disc is not None
    assert disc.threshold == 0.0
    assert disc.angle == 0.0
    assert disc.mu_g == [-0.1, 0.0]
    assert disc.mu_e == [0.1, 0.0]

    assert ro_freqs is not None
    assert ro_freqs.resonator_freq == 8.596e9
    assert qb_params is not None
    assert qb_params.qb_therm_clks == DEFAULT_QB_THERM
    assert qb_params.qubit_freq == 6.15e9
    assert st_params is not None
    assert st_params.st_therm_clks == DEFAULT_ST_THERM
    assert calibration.get_cqed_params(attr.ro_el).ro_therm_clks == DEFAULT_RO_THERM

    assert readout_binding.sync_calls == 1
    assert readout_binding.last_lookup_keys is None


class _FakePulseManager:
    def __init__(self) -> None:
        self.registered: list[tuple[PulseOp, bool, bool]] = []

    def register_pulse_op(self, pulse_op: PulseOp, *, override: bool = False, persist: bool = True) -> None:
        self.registered.append((pulse_op, override, persist))

    def create_control_pulse(
        self,
        *,
        element: str,
        op: str,
        length: int,
        pulse_name: str,
        I_wf_name: str,
        Q_wf_name: str,
        I_samples,
        Q_samples,
        persist: bool = False,
        override: bool = True,
    ) -> None:
        pulse_op = PulseOp(
            element=element,
            op=op,
            pulse=pulse_name,
            type="control",
            length=length,
            I_wf_name=I_wf_name,
            Q_wf_name=Q_wf_name,
            I_wf=np.asarray(I_samples, dtype=float),
            Q_wf=np.asarray(Q_samples, dtype=float),
        )
        self.register_pulse_op(pulse_op, override=override, persist=persist)


class _FakeConfigEngine:
    def __init__(self) -> None:
        self.merge_calls: list[tuple[object, bool]] = []

    def merge_pulses(self, pulse_mgr, include_volatile: bool = False) -> None:
        self.merge_calls.append((pulse_mgr, include_volatile))


def test_register_simulation_pulses_configures_binding_backed_readout(tmp_path) -> None:
    calibration = CalibrationStore(tmp_path / "calibration.json")
    readout_binding = _FakeReadoutBinding()
    pulse_mgr = _FakePulseManager()
    config_engine = _FakeConfigEngine()
    attr = SimpleNamespace(
        qb_el="transmon_sim",
        ro_el="resonator_sim",
        st_el="storage_sim",
    )
    session = SimpleNamespace(
        calibration=calibration,
        pulse_mgr=pulse_mgr,
        config_engine=config_engine,
        context_snapshot=lambda: attr,
        bindings=SimpleNamespace(readout=readout_binding),
    )

    inject_calibration_data(session)
    register_simulation_pulses(session)

    assert readout_binding.active_op == "readout"
    assert readout_binding.pulse_op is not None
    assert readout_binding.pulse_op.element == attr.ro_el
    assert readout_binding.pulse_op.op == "readout"
    assert readout_binding.drive_frequency == 8.596e9
    assert readout_binding.sync_calls == 2
    assert readout_binding.last_lookup_keys == (attr.ro_el,)
    assert config_engine.merge_calls == [(pulse_mgr, True)]
    assert len(pulse_mgr.registered) >= 13


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
        discrimination={"threshold": 0.12, "angle": 0.34},
        quality={},
        drive_frequency=8.15e9,
        gain=0.7,
    )


def test_resonator_spectroscopy_uses_explicit_readout_handle_for_readout_op(monkeypatch) -> None:
    binding = _make_readout_binding(active_op="readout")
    cal = ReadoutCal.from_readout_binding(binding)
    base_handle = ReadoutHandle(
        binding=binding,
        cal=cal,
        element="resonator",
        operation="readout",
        gain=binding.gain,
        demod_weight_sets=(("rot_cos", "rot_sin"), ("rot_m_sin", "rot_cos")),
    )
    readout_calls: list[tuple[str, str]] = []
    captured = {}

    def _stub_builder(if_freqs, ro_therm, n_avg, *, ro_el, bindings, readout):
        captured["if_freqs"] = np.asarray(if_freqs)
        captured["ro_therm"] = ro_therm
        captured["n_avg"] = n_avg
        captured["ro_el"] = ro_el
        captured["bindings"] = bindings
        captured["readout"] = readout
        return {"operation": readout.operation}

    monkeypatch.setattr(
        "qubox.experiments.spectroscopy.resonator.cQED_programs.resonator_spectroscopy",
        _stub_builder,
    )

    class _StubSession:
        pulse_mgr = SimpleNamespace()
        hardware = SimpleNamespace(elements={})
        bindings = ExperimentBindings(
            qubit=OutputBinding(channel=ChannelRef("oct1", "RF_out", 2), lo_frequency=5.9e9),
            readout=binding,
            storage=OutputBinding(channel=ChannelRef("oct1", "RF_out", 3), lo_frequency=5.1e9),
        )

        @staticmethod
        def context_snapshot():
            return SimpleNamespace(ro_el="resonator", qb_el="transmon", st_el="storage")

        @staticmethod
        def readout_handle(alias: str = "resonator", operation: str = "readout") -> ReadoutHandle:
            readout_calls.append((alias, operation))
            return replace(base_handle, operation=operation)

    exp = ResonatorSpectroscopy(_StubSession())
    monkeypatch.setattr(exp, "get_readout_lo", lambda: 8.60e9)

    build = exp.build_program(
        readout_op="readout_rotated",
        rf_begin=8.578e9,
        rf_end=8.580e9,
        df=1e6,
        n_avg=1,
        ro_therm_clks=16,
    )

    assert readout_calls == [("resonator", "readout_rotated")]
    assert captured["readout"].operation == "readout_rotated"
    assert build.readout_state["source"] == "ReadoutHandle"
    assert build.readout_state["operation"] == "readout_rotated"


class _FakeWaveformJob:
    def __init__(self, *, fail_pulls: bool = False) -> None:
        self.fail_pulls = fail_pulls
        self.pull_attempts = 0

    def get_simulated_samples(self):
        self.pull_attempts += 1
        if self.fail_pulls:
            raise QMSimulationError("Error while pulling samples")
        raise AssertionError("This test should only exercise the fallback path")

    @staticmethod
    def simulated_analog_waveforms():
        return {
            "controllers": {
                "con1": {
                    "ports": {
                        1: [
                            {"timestamp": 4, "duration": 3, "name": "readout"},
                            {"timestamp": 10, "duration": 2, "name": "drive"},
                        ]
                    }
                }
            },
            "elements": {},
        }

    @staticmethod
    def simulated_digital_waveforms():
        return {
            "controllers": {
                "con1": {
                    "ports": {
                        9: [{"timestamp": 6, "duration": 4, "name": "marker"}]
                    }
                }
            },
            "elements": {},
        }


class _WrappedFakeWaveformJob(_FakeWaveformJob):
    @staticmethod
    def simulated_analog_waveforms():
        return {"waveforms": _FakeWaveformJob.simulated_analog_waveforms()}

    @staticmethod
    def simulated_digital_waveforms():
        return {"waveforms": _FakeWaveformJob.simulated_digital_waveforms()}


class _FakeControllerWaveformReport:
    def get_report_by_output_ports(self):
        return SimpleNamespace(
            flat_analog_out={
                "1-1": [
                    SimpleNamespace(timestamp=4, ends_at=7),
                    SimpleNamespace(timestamp=10, ends_at=12),
                ]
            },
            flat_digital_out={
                "1-9": [SimpleNamespace(timestamp=6, ends_at=10)]
            },
        )


class _FakeWaveformReport:
    def report_by_controllers(self):
        return {"con1": _FakeControllerWaveformReport()}


class _FakeWaveformReportJob(_FakeWaveformJob):
    @staticmethod
    def get_simulated_waveform_report():
        return _FakeWaveformReport()

    @staticmethod
    def simulated_analog_waveforms():
        return None

    @staticmethod
    def simulated_digital_waveforms():
        return None


def test_build_waveform_metadata_samples_creates_activity_arrays() -> None:
    samples = _build_waveform_metadata_samples(_FakeWaveformJob(), duration_ns=16)

    assert samples is not None
    assert np.all(samples["con1"].analog["1-1"][4:7] > 0)
    assert np.all(samples["con1"].analog["1-1"][10:12] > 0)
    assert np.all(samples["con1"].digital["1-9"][6:10])


def test_build_waveform_metadata_samples_accepts_wrapped_waveform_reports() -> None:
    samples = _build_waveform_metadata_samples(_WrappedFakeWaveformJob(), duration_ns=16)

    assert samples is not None
    assert np.all(samples["con1"].analog["1-1"][4:7] > 0)
    assert np.all(samples["con1"].digital["1-9"][6:10])


def test_build_waveform_report_samples_creates_activity_arrays() -> None:
    samples = _build_waveform_report_samples(_FakeWaveformReportJob(), duration_ns=16)

    assert samples is not None
    assert np.all(samples["con1"].analog["1-1"][4:7] > 0)
    assert np.all(samples["con1"].analog["1-1"][10:12] > 0)
    assert np.all(samples["con1"].digital["1-9"][6:10])


def test_simulate_program_falls_back_to_waveform_report_when_sample_pull_fails() -> None:
    fake_job = _FakeWaveformReportJob(fail_pulls=True)
    fake_qmm = SimpleNamespace(simulate=lambda cfg, program, sim_config: fake_job)
    session = SimpleNamespace(
        config_engine=SimpleNamespace(build_qm_config=lambda: {"elements": {}}),
        runner=SimpleNamespace(_qmm=fake_qmm),
    )

    sim_samples, elapsed, sample_source = simulate_program(session, program=object(), duration_ns=16)

    assert elapsed >= 0.0
    assert sample_source == "waveform_report"
    assert fake_job.pull_attempts == 3
    assert np.all(sim_samples["con1"].analog["1-1"][4:7] > 0)
    assert np.all(sim_samples["con1"].digital["1-9"][6:10])
