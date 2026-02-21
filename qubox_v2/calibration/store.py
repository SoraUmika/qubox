# qubox_v2/calibration/store.py
"""JSON-backed calibration data store with typed access and history.

Usage::

    store = CalibrationStore("./experiment/config/calibration.json")

    # Store discrimination results
    store.set_discrimination("resonator", DiscriminationParams(...))

    # Retrieve
    disc = store.get_discrimination("resonator")

    # Save to disk
    store.save()

    # Create a timestamped snapshot before making changes
    store.snapshot("pre_optimization")
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.logging import get_logger
from .models import (
    CalibrationData,
    CoherenceParams,
    DiscriminationParams,
    ElementFrequencies,
    FitRecord,
    FockSQRCalibration,
    MultiStateCalibration,
    PulseCalibration,
    PulseTrainResult,
    ReadoutQuality,
)

_logger = get_logger(__name__)


class CalibrationStore:
    """Typed, versioned calibration data with JSON persistence.

    Parameters
    ----------
    path : str | Path
        Path to the calibration JSON file.  Created if it does not exist.
    auto_save : bool
        If True, every mutating method automatically saves to disk.
    """

    def __init__(self, path: str | Path, *, auto_save: bool = False) -> None:
        self._path = Path(path)
        self._auto_save = auto_save
        self._data = self._load_or_create()

    # ------------------------------------------------------------------
    # Load / create
    # ------------------------------------------------------------------
    def _load_or_create(self) -> CalibrationData:
        if self._path.exists():
            _logger.info("Loading calibration from %s", self._path)
            with open(self._path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            return CalibrationData.model_validate(raw)
        _logger.info("No calibration file found — creating defaults at %s", self._path)
        data = CalibrationData(created=datetime.now().isoformat())
        return data

    # ------------------------------------------------------------------
    # Discrimination
    # ------------------------------------------------------------------
    def get_discrimination(self, element: str) -> DiscriminationParams | None:
        return self._data.discrimination.get(element)

    def set_discrimination(self, element: str, params: DiscriminationParams | None = None, **kw) -> None:
        if params is None:
            existing = self._data.discrimination.get(element)
            if existing:
                merged = existing.model_dump()
                merged.update({k: v for k, v in kw.items() if v is not None})
                params = DiscriminationParams(**merged)
            else:
                params = DiscriminationParams(**kw)
        self._data.discrimination[element] = params
        self._touch()

    # ------------------------------------------------------------------
    # Readout quality
    # ------------------------------------------------------------------
    def get_readout_quality(self, element: str) -> ReadoutQuality | None:
        return self._data.readout_quality.get(element)

    def set_readout_quality(self, element: str, params: ReadoutQuality | None = None, **kw) -> None:
        if params is None:
            existing = self._data.readout_quality.get(element)
            if existing:
                merged = existing.model_dump()
                merged.update({k: v for k, v in kw.items() if v is not None})
                params = ReadoutQuality(**merged)
            else:
                params = ReadoutQuality(**kw)
        self._data.readout_quality[element] = params
        self._touch()

    # ------------------------------------------------------------------
    # Frequencies
    # ------------------------------------------------------------------
    def get_frequencies(self, element: str) -> ElementFrequencies | None:
        return self._data.frequencies.get(element)

    def set_frequencies(self, element: str, freqs: ElementFrequencies | None = None, **kw) -> None:
        if freqs is None:
            existing = self._data.frequencies.get(element)
            if existing:
                merged = existing.model_dump()
                merged.update({k: v for k, v in kw.items() if v is not None})
                freqs = ElementFrequencies(**merged)
            else:
                kw.setdefault("lo_freq", 0.0)
                kw.setdefault("if_freq", 0.0)
                freqs = ElementFrequencies(**kw)
        self._data.frequencies[element] = freqs
        self._touch()

    # ------------------------------------------------------------------
    # Coherence
    # ------------------------------------------------------------------
    def get_coherence(self, element: str) -> CoherenceParams | None:
        return self._data.coherence.get(element)

    def set_coherence(self, element: str, params: CoherenceParams | None = None, **kw) -> None:
        if params is None:
            existing = self._data.coherence.get(element)
            if existing:
                merged = existing.model_dump()
                merged.update({k: v for k, v in kw.items() if v is not None})
                params = CoherenceParams(**merged)
            else:
                params = CoherenceParams(**kw)
        self._data.coherence[element] = params
        self._touch()

    # ------------------------------------------------------------------
    # Pulse calibrations
    # ------------------------------------------------------------------
    def get_pulse_calibration(self, name: str) -> PulseCalibration | None:
        return self._data.pulse_calibrations.get(name)

    def set_pulse_calibration(self, name: str, cal: PulseCalibration | None = None, **kw) -> None:
        if cal is None:
            existing = self._data.pulse_calibrations.get(name)
            if existing:
                merged = existing.model_dump()
                merged.update({k: v for k, v in kw.items() if v is not None})
                cal = PulseCalibration(**merged)
            else:
                kw.setdefault("pulse_name", name)
                kw.setdefault("element", "")
                cal = PulseCalibration(**kw)
        self._data.pulse_calibrations[name] = cal
        self._touch()

    # ------------------------------------------------------------------
    # Fit history
    # ------------------------------------------------------------------
    def store_fit(self, record: FitRecord) -> None:
        """Append a fit result to the history for its experiment."""
        if record.timestamp is None:
            record.timestamp = datetime.now().isoformat()
        self._data.fit_history.setdefault(record.experiment, []).append(record)
        self._touch()

    def get_latest_fit(self, experiment: str) -> FitRecord | None:
        history = self._data.fit_history.get(experiment, [])
        return history[-1] if history else None

    def get_fit_history(self, experiment: str) -> list[FitRecord]:
        return list(self._data.fit_history.get(experiment, []))

    # ------------------------------------------------------------------
    # Pulse train results
    # ------------------------------------------------------------------
    def get_pulse_train_result(self, element: str) -> PulseTrainResult | None:
        return self._data.pulse_train_results.get(element)

    def set_pulse_train_result(self, element: str, result: PulseTrainResult) -> None:
        self._data.pulse_train_results[element] = result
        self._touch()

    # ------------------------------------------------------------------
    # Fock SQR calibrations
    # ------------------------------------------------------------------
    def get_fock_sqr_calibrations(self, element: str) -> list[FockSQRCalibration]:
        return list(self._data.fock_sqr_calibrations.get(element, []))

    def set_fock_sqr_calibrations(self, element: str, cals: list[FockSQRCalibration]) -> None:
        self._data.fock_sqr_calibrations[element] = cals
        self._touch()

    # ------------------------------------------------------------------
    # Multi-state calibration
    # ------------------------------------------------------------------
    def get_multi_state_calibration(self, element: str) -> MultiStateCalibration | None:
        return self._data.multi_state_calibration.get(element)

    def set_multi_state_calibration(self, element: str, cal: MultiStateCalibration) -> None:
        self._data.multi_state_calibration[element] = cal
        self._touch()

    # ------------------------------------------------------------------
    # Bulk access
    # ------------------------------------------------------------------
    @property
    def data(self) -> CalibrationData:
        """Direct access to the underlying data model."""
        return self._data

    def to_dict(self) -> dict[str, Any]:
        return self._data.model_dump()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def save(self) -> None:
        """Write calibration data to JSON."""
        self._data.last_modified = datetime.now().isoformat()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data.model_dump(), f, indent=2, default=str)
        _logger.info("Calibration saved to %s", self._path)

    def snapshot(self, tag: str = "") -> Path:
        """Create a timestamped backup of the current calibration file.

        Returns the path to the snapshot file.
        """
        self.save()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = f"_{tag}" if tag else ""
        snap_path = self._path.with_name(
            f"{self._path.stem}_{ts}{suffix}{self._path.suffix}"
        )
        shutil.copy2(self._path, snap_path)
        _logger.info("Calibration snapshot: %s", snap_path)
        return snap_path

    def reload(self) -> None:
        """Reload from disk, discarding in-memory changes."""
        self._data = self._load_or_create()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _touch(self) -> None:
        """Mark data as modified; auto-save if enabled."""
        self._data.last_modified = datetime.now().isoformat()
        if self._auto_save:
            self.save()
