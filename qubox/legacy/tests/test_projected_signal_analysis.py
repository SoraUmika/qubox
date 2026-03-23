from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from qubox.legacy.experiments.result import FitResult
from qubox.legacy.experiments.time_domain.coherence import T2Echo, T2Ramsey
from qubox.legacy.experiments.time_domain.rabi import PowerRabi, TemporalRabi
from qubox.legacy.experiments.time_domain.relaxation import T1Relaxation


class _FakeOutput(dict):
    def extract(self, key: str):
        return self[key]


def _run_result(**payload):
    return SimpleNamespace(output=_FakeOutput(payload), metadata={})


def test_temporal_rabi_analysis_fits_projected_signal(monkeypatch):
    durations = np.array([10.0, 20.0, 30.0])
    raw_signal = np.array([1.0 + 2.0j, 2.0 + 3.0j, 3.0 + 4.0j])
    projected = np.array([0.2, -0.1, 0.3])
    captured: dict[str, np.ndarray] = {}

    monkeypatch.setattr(
        "qubox.legacy.experiments.time_domain.rabi.project_complex_to_line_real",
        lambda samples: (projected.copy(), 1.0 + 0.5j, 0.0 + 1.0j),
    )

    def fake_fit(x, y, model, p0, model_name, **kwargs):
        captured["x"] = np.asarray(x, dtype=float)
        captured["y"] = np.asarray(y, dtype=float)
        return FitResult(
            model_name=model_name,
            params={"A": 0.4, "f_Rabi": 0.05, "T_decay": 60.0, "phi": 0.1, "offset": -0.2},
            success=True,
        )

    monkeypatch.setattr("qubox.legacy.experiments.time_domain.rabi.fit_and_wrap", fake_fit)

    analysis = TemporalRabi.__new__(TemporalRabi).analyze(_run_result(pulse_durations=durations, S=raw_signal))

    assert np.allclose(captured["x"], durations)
    assert np.allclose(captured["y"], projected)
    assert np.allclose(analysis.data["projected_S"], projected)
    assert analysis.metrics["pi_length"] == 10.0


def test_power_rabi_analysis_fits_projected_i_quadrature(monkeypatch):
    gains = np.array([-0.2, 0.0, 0.2, 0.4])
    raw_signal = np.array([1.0 + 0.2j, 0.8 + 0.1j, 0.1 - 0.1j, -0.2 - 0.3j])
    projected = np.array([0.6, 0.4, -0.2, -0.5])
    captured: dict[str, list[np.ndarray]] = {"ys": []}

    monkeypatch.setattr(
        "qubox.legacy.experiments.time_domain.rabi.project_complex_to_line_real",
        lambda samples: (projected.copy(), 1.2 + 0.3j, 1.0 + 0.0j),
    )

    def fake_fit(x, y, model, p0, model_name, **kwargs):
        captured["ys"].append(np.asarray(y, dtype=float))
        return FitResult(
            model_name=model_name,
            params={"A": 0.55, "g_pi": 0.2, "phi": 0.0, "offset": 0.05},
            success=True,
            r_squared=0.9,
        )

    monkeypatch.setattr("qubox.legacy.experiments.time_domain.rabi.fit_and_wrap", fake_fit)

    analysis = PowerRabi.__new__(PowerRabi).analyze(_run_result(gains=gains, S=raw_signal))

    assert all(np.allclose(y, projected) for y in captured["ys"])
    assert np.allclose(analysis.data["projected_S"], projected)
    assert analysis.metrics["g_pi"] == 0.2


def test_t1_analysis_fits_projected_signal_and_persists_it(monkeypatch):
    delays = np.array([0.0, 40.0, 80.0])
    raw_signal = np.array([1.0 + 1.0j, 0.7 + 0.4j, 0.4 + 0.1j])
    projected = np.array([0.9, 0.5, 0.2])
    captured: dict[str, np.ndarray] = {}

    monkeypatch.setattr(
        "qubox.legacy.experiments.time_domain.relaxation.project_complex_to_line_real",
        lambda samples: (projected.copy(), 0.0 + 0.0j, 1.0 + 0.0j),
    )

    def fake_fit(x, y, model, p0, model_name, **kwargs):
        captured["y"] = np.asarray(y, dtype=float)
        return FitResult(
            model_name=model_name,
            params={"A": 0.7, "T1": 120.0, "offset": 0.1},
            success=True,
        )

    monkeypatch.setattr("qubox.legacy.experiments.time_domain.relaxation.fit_and_wrap", fake_fit)

    analysis = T1Relaxation.__new__(T1Relaxation).analyze(_run_result(delays=delays, S=raw_signal))

    assert np.allclose(captured["y"], projected)
    assert np.allclose(analysis.data["projected_S"], projected)
    assert analysis.metrics["T1_us"] == 0.12


def test_coherence_analyses_fit_projected_signal_and_persist_it(monkeypatch):
    delays = np.array([0.0, 80.0, 160.0])
    raw_signal = np.array([0.5 + 0.2j, 0.1 - 0.3j, -0.2 - 0.4j])
    projected = np.array([0.4, -0.1, -0.3])
    captures: dict[str, list[np.ndarray]] = {"ramsey": [], "echo": []}

    monkeypatch.setattr(
        "qubox.legacy.experiments.time_domain.coherence.project_complex_to_line_real",
        lambda samples: (projected.copy(), -0.2 + 0.1j, 0.0 + 1.0j),
    )

    def fake_fit(x, y, model, p0, model_name, **kwargs):
        key = "ramsey" if model_name == "T2_ramsey" else "echo"
        captures[key].append(np.asarray(y, dtype=float))
        params = (
            {"A": 0.5, "T2": 400.0, "n": 1.0, "f_det": 0.002, "phi": 0.1, "offset": 0.0}
            if model_name == "T2_ramsey"
            else {"A": 0.5, "T2_echo": 700.0, "n": 1.0, "offset": 0.0}
        )
        return FitResult(model_name=model_name, params=params, success=True)

    monkeypatch.setattr("qubox.legacy.experiments.time_domain.coherence.fit_and_wrap", fake_fit)

    ramsey = T2Ramsey.__new__(T2Ramsey).analyze(_run_result(delays=delays, S=raw_signal, qb_detune=2_000_000))
    echo = T2Echo.__new__(T2Echo).analyze(_run_result(delays=delays, S=raw_signal))

    assert all(np.allclose(y, projected) for y in captures["ramsey"])
    assert all(np.allclose(y, projected) for y in captures["echo"])
    assert np.allclose(ramsey.data["projected_S"], projected)
    assert np.allclose(echo.data["projected_S"], projected)
    assert ramsey.metrics["T2_star_us"] == 0.4
    assert echo.metrics["T2_echo_us"] == 0.7
