"""Minimal tests for CalibrationStore persistence.

Run with: pytest tests/test_calibration_store.py -v
No hardware connection required.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from qubox_v2.calibration.store import CalibrationStore
from qubox_v2.calibration.models import CalibrationData


@pytest.fixture
def cal_path(tmp_path: Path) -> Path:
    """Return a path inside a temp directory for a calibration file."""
    return tmp_path / "config" / "calibration.json"


class TestCalibrationPersistence:
    """Tests that calibration data survives a save/reload cycle."""

    def test_file_created_on_init(self, cal_path: Path):
        """File is written when CalibrationStore creates defaults."""
        assert not cal_path.exists()
        CalibrationStore(cal_path)
        assert cal_path.exists(), "calibration.json was not created on init"

        raw = json.loads(cal_path.read_text(encoding="utf-8"))
        assert raw["version"] == "3.0.0"
        assert raw["created"] is not None

    def test_roundtrip_discrimination(self, cal_path: Path):
        """Data written via set_discrimination survives save -> reload."""
        store = CalibrationStore(cal_path)
        store.set_discrimination(
            "resonator",
            threshold=0.003,
            angle=1.23,
            mu_g=[0.0, 0.0],
            mu_e=[0.01, 0.0],
            sigma_g=0.001,
            sigma_e=0.001,
            fidelity=0.97,
        )
        store.save()

        store2 = CalibrationStore(cal_path)
        disc = store2.get_discrimination("resonator")
        assert disc is not None
        assert abs(disc.threshold - 0.003) < 1e-9
        assert abs(disc.fidelity - 0.97) < 1e-9

    def test_roundtrip_frequencies(self, cal_path: Path):
        """Frequency calibrations survive save/reload."""
        store = CalibrationStore(cal_path)
        store.set_frequencies(
            "storage", lo_freq=5.4e9, if_freq=-159e6,
            qubit_freq=5.241e9, kappa=50e3,
        )
        store.save()

        store2 = CalibrationStore(cal_path)
        freqs = store2.get_frequencies("storage")
        assert freqs is not None
        assert abs(freqs.qubit_freq - 5.241e9) < 1.0
        assert abs(freqs.kappa - 50e3) < 1.0

    def test_auto_save(self, cal_path: Path):
        """auto_save=True writes after each mutation."""
        store = CalibrationStore(cal_path, auto_save=True)
        store.set_coherence("qubit", T1=25e3)

        # Re-read from disk without explicit save()
        store2 = CalibrationStore(cal_path)
        coh = store2.get_coherence("qubit")
        assert coh is not None
        assert abs(coh.T1 - 25e3) < 1e-6

    def test_atomic_write_leaves_valid_file(self, cal_path: Path):
        """After save(), file is always valid JSON."""
        store = CalibrationStore(cal_path)
        store.set_coherence("qubit", T1=25e3, T2_ramsey=12e3)
        store.save()

        raw = json.loads(cal_path.read_text(encoding="utf-8"))
        data = CalibrationData.model_validate(raw)
        assert data.coherence["qubit"].T1 == pytest.approx(25e3)

    def test_summary_method(self, cal_path: Path):
        """summary() returns a non-empty diagnostic string."""
        store = CalibrationStore(cal_path)
        store.set_coherence("qubit", T1=25e3)
        s = store.summary()
        assert "CalibrationStore" in s
        assert "coherence: 1 entries" in s
        assert "qubit" in s

    def test_set_frequencies_merge_preserves_existing(self, cal_path: Path):
        """set_frequencies with partial kwargs preserves other fields."""
        store = CalibrationStore(cal_path)
        store.set_frequencies("storage", lo_freq=5.4e9, if_freq=-159e6)
        # Now update only kappa — lo_freq/if_freq should be preserved
        store.set_frequencies("storage", kappa=50e3)
        freqs = store.get_frequencies("storage")
        assert freqs is not None
        assert abs(freqs.lo_freq - 5.4e9) < 1.0, "lo_freq was overwritten"
        assert abs(freqs.kappa - 50e3) < 1.0
