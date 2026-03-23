from __future__ import annotations

import json
from pathlib import Path

from qubox.compat import notebook_runtime


def test_open_shared_session_reuses_live_session_and_persists_bootstrap(monkeypatch, tmp_path):
    calls: list[dict[str, object]] = []

    class DummySession:
        def close(self):
            return None

    class FakeSessionApi:
        @staticmethod
        def open(**kwargs):
            calls.append(dict(kwargs))
            return DummySession()

    class FakeRegistry:
        def __init__(self, base):
            self.base = Path(base)

        def cooldown_path(self, sample_id: str, cooldown_id: str) -> Path:
            return self.base / sample_id / "cooldowns" / cooldown_id

    monkeypatch.setattr(notebook_runtime, "Session", FakeSessionApi)
    monkeypatch.setattr(notebook_runtime, "SampleRegistry", FakeRegistry)
    monkeypatch.setattr(notebook_runtime, "_SHARED_NOTEBOOK_SESSIONS", {})
    monkeypatch.setattr(notebook_runtime, "_DEFAULT_SHARED_SESSION_KEY", None)

    session1 = notebook_runtime.open_shared_session(
        sample_id="sampleA",
        cooldown_id="cd1",
        registry_base=tmp_path,
        qop_ip="10.157.36.68",
        cluster_name="Cluster_2",
    )
    session2 = notebook_runtime.open_shared_session(
        sample_id="sampleA",
        cooldown_id="cd1",
        registry_base=tmp_path,
        qop_ip="10.157.36.68",
        cluster_name="Cluster_2",
    )

    bootstrap_path = notebook_runtime.get_notebook_session_bootstrap_path(
        sample_id="sampleA",
        cooldown_id="cd1",
        registry_base=tmp_path,
    )
    payload = json.loads(bootstrap_path.read_text(encoding="utf-8"))

    assert session1 is session2
    assert len(calls) == 1
    assert payload["sample_id"] == "sampleA"
    assert payload["cooldown_id"] == "cd1"
    assert payload["cluster_name"] == "Cluster_2"

    monkeypatch.setattr(notebook_runtime, "_SHARED_NOTEBOOK_SESSIONS", {})
    monkeypatch.setattr(notebook_runtime, "_DEFAULT_SHARED_SESSION_KEY", None)

    restored = notebook_runtime.require_shared_session(bootstrap_path=bootstrap_path)

    assert isinstance(restored, DummySession)
    assert len(calls) == 2
    assert calls[-1]["sample_id"] == "sampleA"
    assert calls[-1]["cooldown_id"] == "cd1"


def test_resolve_active_mixer_targets_reports_all_active_outputs():
    class DummyHardware:
        def __init__(self):
            self._lo = {
                "resonator": 8.8e9,
                "resonator_gf": 3.5e9,
                "transmon": 6.2e9,
                "storage": 5.4e9,
                "storage_gf": 7.0e9,
            }
            self._if = {name: -50e6 for name in self._lo}

        def get_active_mixer_elements(self, *, include_skipped: bool = False):
            payload = {
                "active": list(self._lo.keys()),
                "skipped": ["__oct__resonator_analyzer"],
            }
            if include_skipped:
                return payload
            return payload["active"]

        def get_element_lo(self, element: str) -> float:
            return self._lo[element]

        def get_element_if(self, element: str) -> float:
            return self._if[element]

    session = type("DummySession", (), {"hw": DummyHardware()})()

    payload = notebook_runtime.resolve_active_mixer_targets(session, include_skipped=True)

    assert [row["element"] for row in payload["active"]] == [
        "resonator",
        "resonator_gf",
        "transmon",
        "storage",
        "storage_gf",
    ]
    assert payload["skipped"] == ["__oct__resonator_analyzer"]
    assert payload["active"][0]["rf_hz"] == 8.75e9