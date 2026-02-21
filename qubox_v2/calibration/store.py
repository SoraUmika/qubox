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
import os
import shutil
import tempfile
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
        # Write defaults to disk immediately so the file actually exists.
        # Cannot call self.save() here because self._data is not yet assigned.
        data = CalibrationData(created=datetime.now().isoformat())
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(data)
        _logger.info("Default calibration created at %s", self._path)
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

    def store_weight_snapshot(self, element: str, weight_info: dict) -> None:
        """Store a weight optimisation snapshot with timestamp.

        Uses the existing :class:`FitRecord` model keyed under
        ``"weight_optimization_{element}"`` so that weight history can
        be queried via :meth:`get_fit_history`.
        """
        numeric = {k: float(v) for k, v in weight_info.items()
                   if isinstance(v, (int, float))}
        record = FitRecord(
            experiment=f"weight_optimization_{element}",
            model_name="segmented_weights",
            params=numeric,
            metadata=weight_info,
        )
        self.store_fit(record)

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

    def summary(self) -> str:
        """Return a human-readable summary of stored calibration data."""
        lines = [
            f"CalibrationStore: {self._path}",
            f"  file exists: {self._path.exists()}",
            f"  auto_save:   {self._auto_save}",
            f"  version:     {self._data.version}",
            f"  created:     {self._data.created}",
            f"  modified:    {self._data.last_modified}",
            "",
        ]
        sections = [
            ("discrimination", self._data.discrimination),
            ("readout_quality", self._data.readout_quality),
            ("frequencies", self._data.frequencies),
            ("coherence", self._data.coherence),
            ("pulse_calibrations", self._data.pulse_calibrations),
            ("fit_history", self._data.fit_history),
            ("pulse_train_results", self._data.pulse_train_results),
            ("fock_sqr_calibrations", self._data.fock_sqr_calibrations),
            ("multi_state_calibration", self._data.multi_state_calibration),
        ]
        for name, store in sections:
            count = len(store)
            if count:
                keys = ", ".join(sorted(store.keys()))
                lines.append(f"  {name}: {count} entries [{keys}]")
            else:
                lines.append(f"  {name}: (empty)")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def save(self) -> None:
        """Write calibration data to JSON (atomic via temp file + rename)."""
        self._data.last_modified = datetime.now().isoformat()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(self._data)
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
    def _atomic_write(self, data: CalibrationData) -> None:
        """Write data to JSON via temp file + os.replace (atomic on same FS)."""
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=self._path.parent, prefix=".cal_tmp_", suffix=".json",
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(data.model_dump(), f, indent=2, default=str)
            os.replace(tmp_path, self._path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def _touch(self) -> None:
        """Mark data as modified; auto-save if enabled."""
        self._data.last_modified = datetime.now().isoformat()
        if self._auto_save:
            self.save()
