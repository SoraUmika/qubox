from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import threading
import warnings

import pytest

from qubox.core.errors import ConfigError, ConnectionError
from qubox.core.preflight import preflight_check as core_preflight_check
from qubox.core.utils import resolve_qop_host
from qubox.devices.registry import SampleRegistry
from qubox.experiments.base import ExperimentRunner
from qubox.experiments.config_builder import ConfigBuilder
from qubox.experiments.session import SessionManager
from qubox.hardware.controller import HardwareController
from qubox.hardware.config_engine import ConfigEngine
from qubox.preflight import preflight_check as public_preflight_check
from qubox.pulses.factory import PulseFactory


class _DummyConfigEngine:
    def __init__(self, hardware_path: str | Path) -> None:
        self.hardware_path = Path(hardware_path)
        self.hardware_extras: dict[str, str] = {}


def _write_hardware_json(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")


def test_resolve_qop_host_prefers_explicit_value() -> None:
    assert resolve_qop_host(" 10.157.36.68 ", {"qop_ip": "127.0.0.1"}) == "10.157.36.68"


def test_resolve_qop_host_uses_persisted_hardware_extras() -> None:
    assert resolve_qop_host(None, {"qop_ip": "10.157.36.68"}) == "10.157.36.68"


def test_resolve_qop_host_returns_none_without_configuration() -> None:
    assert resolve_qop_host(None, {}) is None
    assert resolve_qop_host("   ", {}) is None


def test_experiment_runner_requires_qop_host(monkeypatch, tmp_path: Path) -> None:
    _write_hardware_json(tmp_path / "config" / "hardware.json")
    monkeypatch.setattr("qubox.experiments.base.ConfigEngine", _DummyConfigEngine)

    with pytest.raises(ConfigError, match="QOP host is required"):
        ExperimentRunner(tmp_path)


def test_session_manager_requires_qop_host(monkeypatch, tmp_path: Path) -> None:
    registry = SampleRegistry(tmp_path)
    registry.create_sample("sampleA")
    registry.create_cooldown("sampleA", "cd1")
    _write_hardware_json(registry.sample_path("sampleA") / "config" / "hardware.json")
    monkeypatch.setattr("qubox.experiments.session.ConfigEngine", _DummyConfigEngine)

    with pytest.raises(ConfigError, match="QOP host is required"):
        SessionManager(sample_id="sampleA", cooldown_id="cd1", registry_base=tmp_path)


def test_experiment_runner_run_rejects_simulate_mode() -> None:
    runner = SimpleNamespace(run_program=lambda *_args, **_kwargs: None)
    exp = ExperimentRunner.__new__(ExperimentRunner)
    exp.runner = runner

    with pytest.raises(ValueError, match="hardware-only"):
        ExperimentRunner.run(exp, object(), mode="simulate")


def test_public_preflight_reexports_core_implementation() -> None:
    assert public_preflight_check is core_preflight_check


def test_session_manager_close_continues_after_calibration_save_failure() -> None:
    calls: list[str] = []

    class _Calibration:
        def save(self) -> None:
            calls.append("calibration")
            raise RuntimeError("boom")

    session = SessionManager.__new__(SessionManager)
    session.hardware = SimpleNamespace(close=lambda: calls.append("hardware"))
    session.devices = SimpleNamespace(
        handles={"dev1": SimpleNamespace(disconnect=lambda: calls.append("disconnect_dev1"))}
    )
    session.save_pulses = lambda: calls.append("pulses")
    session.save_runtime_settings = lambda: calls.append("runtime")
    session.calibration = _Calibration()
    session.persist_measure_config = lambda: calls.append("measure")
    session._opened = True
    session._last_close_report = None

    SessionManager.close(session)

    assert calls == ["hardware", "disconnect_dev1", "pulses", "runtime", "calibration", "measure"]
    assert session._opened is False
    assert session._last_close_report is not None
    assert session._last_close_report["errors"] == ["saving calibration"]
    assert any(
        step["step"] == "saving measureConfig.json on close" and step["ok"]
        for step in session._last_close_report["steps"]
    )


def test_hardware_controller_uses_resolved_qmm_endpoint() -> None:
    controller = HardwareController.__new__(HardwareController)
    controller._qmm = SimpleNamespace(
        _server_details=SimpleNamespace(
            host="ignored-host",
            port=1,
            connection_details=SimpleNamespace(host="10.157.36.68", port=9510),
        )
    )

    assert controller._get_qmm_endpoint() == ("10.157.36.68", 9510)


def test_hardware_controller_open_qm_rejects_unreachable_endpoint() -> None:
    calls: list[str] = []
    controller = HardwareController.__new__(HardwareController)
    controller._lock = threading.RLock()
    controller.qm = None
    controller._qmm = SimpleNamespace(open_qm=lambda *_args, **_kwargs: calls.append("open_qm"))
    controller.config = SimpleNamespace(build_qm_config=lambda: {})
    controller._build_element_table = lambda: {}

    def _fail_reachability(timeout: float = 2.0) -> None:
        calls.append("reachability")
        raise ConnectionError("QM endpoint 10.157.36.68:9510 is unreachable before open_qm: timed out")

    controller._ensure_qmm_endpoint_reachable = _fail_reachability

    with pytest.raises(ConnectionError, match="unreachable before open_qm"):
        HardwareController.open_qm(controller)

    assert calls == ["reachability"]
    assert controller.qm is None


def test_config_engine_build_qm_config_excludes_deprecated_version_field(tmp_path: Path) -> None:
    hardware_path = tmp_path / "hardware.json"
    hardware_path.write_text(
        json.dumps({"version": 1, "controllers": {}, "octaves": {}, "elements": {}}),
        encoding="utf-8",
    )

    engine = ConfigEngine(hardware_path)
    cfg = engine.build_qm_config()

    assert "version" not in cfg
    assert engine.hardware_base is not None
    assert engine.hardware_base["version"] == 1


def test_config_builder_to_dict_excludes_deprecated_version_field() -> None:
    cfg = ConfigBuilder().to_dict()

    assert "version" not in cfg
    assert cfg["controllers"] == {}
    assert cfg["octaves"] == {}


def test_arbitrary_blob_shape_compiles_without_deprecation_warning() -> None:
    factory = PulseFactory(
        {
            "specs": {
                "blob": {
                    "shape": "arbitrary_blob",
                    "element": "qubit",
                    "op": "x180",
                    "params": {"length": 4},
                }
            }
        }
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        i_wf, q_wf, meta = factory.compile_one("blob")

    assert caught == []
    assert i_wf == [0.0, 0.0, 0.0, 0.0]
    assert q_wf == [0.0, 0.0, 0.0, 0.0]
    assert meta["shape"] == "arbitrary_blob"
