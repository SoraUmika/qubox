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
from ..core.persistence_policy import sanitize_mapping_for_json
from .models import (
    CalibrationContext,
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
    context : ExperimentContext, optional
        If provided, the store validates that the on-disk calibration
        matches this device/cooldown/wiring context.
    strict_context : bool
        If True (default), a device or wiring mismatch raises
        ``ContextMismatchError``.  If False, mismatches are logged as
        warnings only.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        auto_save: bool = False,
        context: Any = None,
        strict_context: bool = True,
    ) -> None:
        self._path = Path(path)
        self._auto_save = auto_save
        self._context = context
        self._data = self._load_or_create()
        if context is not None:
            self._validate_context(strict=strict_context)

    @property
    def path(self) -> Path:
        return self._path

    # ------------------------------------------------------------------
    # Load / create
    # ------------------------------------------------------------------
    def _load_or_create(self) -> CalibrationData:
        if self._path.exists():
            _logger.info("Loading calibration from %s", self._path)
            with open(self._path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            # Auto-migrate v3 → v4 in memory (adds context=None)
            version_str = raw.get("version", "3.0.0")
            if version_str == "3.0.0":
                raw["version"] = "4.0.0"
                raw.setdefault("context", None)
                _logger.info("Auto-migrated calibration in-memory from v3.0.0 to v4.0.0")
            return CalibrationData.model_validate(raw)
        # Write defaults to disk immediately so the file actually exists.
        # Cannot call self.save() here because self._data is not yet assigned.
        ctx_block = None
        if self._context is not None:
            ctx_block = CalibrationContext(
                device_id=self._context.device_id,
                cooldown_id=self._context.cooldown_id,
                wiring_rev=self._context.wiring_rev,
                schema_version=self._context.schema_version,
                config_hash=getattr(self._context, "config_hash", "") or "",
                created=datetime.now().isoformat(),
            )
        data = CalibrationData(
            version="4.0.0",
            context=ctx_block,
            created=datetime.now().isoformat(),
        )
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

    def reload_from_dict(self, raw: dict[str, Any]) -> None:
        """Replace in-memory state from a raw dict.

        This is used by patch/orchestrator flows that stage batched mutations
        before persisting.
        """
        self._data = CalibrationData.model_validate(raw)
        self._touch()

    # ------------------------------------------------------------------
    # Context validation
    # ------------------------------------------------------------------
    def _validate_context(self, *, strict: bool = True) -> None:
        """Check that the on-disk context matches the session context.

        Parameters
        ----------
        strict : bool
            If True, device or wiring mismatches raise
            ``ContextMismatchError``.  Cooldown mismatches always warn.
        """
        from ..core.errors import ContextMismatchError

        stored = self._data.context
        ctx = self._context
        if ctx is None:
            return

        # No context block on disk (legacy v3 file) — skip
        if stored is None:
            _logger.warning(
                "Calibration file has no context block (legacy v3). "
                "Skipping context validation for %s", self._path,
            )
            return

        # Device mismatch
        if stored.device_id and ctx.device_id and stored.device_id != ctx.device_id:
            msg = (
                f"Device mismatch: calibration was made for device "
                f"'{stored.device_id}' but session uses '{ctx.device_id}'"
            )
            if strict:
                raise ContextMismatchError(msg)
            _logger.warning(msg)

        # Wiring mismatch
        if stored.wiring_rev and ctx.wiring_rev and stored.wiring_rev != ctx.wiring_rev:
            msg = (
                f"Wiring revision mismatch: calibration has '{stored.wiring_rev}' "
                f"but hardware.json hashes to '{ctx.wiring_rev}'"
            )
            if strict:
                raise ContextMismatchError(msg)
            _logger.warning(msg)

        # Cooldown mismatch — always warn, never raise
        if stored.cooldown_id and ctx.cooldown_id and stored.cooldown_id != ctx.cooldown_id:
            _logger.warning(
                "Cooldown mismatch: calibration was made for cooldown "
                "'%s' but session uses '%s'. Calibrations may be stale.",
                stored.cooldown_id, ctx.cooldown_id,
            )

    def stamp_context(self, context: Any) -> None:
        """Write or overwrite the context block from an ExperimentContext."""
        self._data.context = CalibrationContext(
            device_id=context.device_id,
            cooldown_id=context.cooldown_id,
            wiring_rev=context.wiring_rev,
            schema_version=context.schema_version,
            config_hash=getattr(context, "config_hash", "") or "",
            created=datetime.now().isoformat(),
        )
        self._data.version = "4.0.0"
        self._touch()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _atomic_write(self, data: CalibrationData) -> None:
        """Write data to JSON via temp file + os.replace (atomic on same FS).

        Uses ``exclude_none=True`` so that unset optional fields are omitted
        from the persisted JSON rather than stored as ``null`` placeholders.
        Calibration records should reflect actual pipeline outputs only.
        """
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=self._path.parent, prefix=".cal_tmp_", suffix=".json",
        )
        payload, dropped = sanitize_mapping_for_json(
            data.model_dump(exclude_none=True)
        )
        if dropped:
            payload["_persistence"] = {
                "raw_data_policy": "drop_shot_level_arrays",
                "dropped_fields": dropped,
            }
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, default=str)
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
