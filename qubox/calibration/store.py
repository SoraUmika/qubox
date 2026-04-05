"""qubox.calibration.store — JSON-backed calibration data store.

This module depends only on the qubox package.

Usage::

    store = CalibrationStore("./config/calibration.json")

    store.set_discrimination("resonator", DiscriminationParams(...))
    disc = store.get_discrimination("resonator")

    store.save()
    store.snapshot("pre_optimization")
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.errors import ContextMismatchError
from ..core.persistence import sanitize_mapping_for_json
from .store_models import (
    CalibrationContext,
    CalibrationData,
    CQEDParams,
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
from .transitions import resolve_pulse_name

_logger = logging.getLogger(__name__)
_SUPPORTED_CALIBRATION_VERSIONS = {"5.0.0", "5.1.0"}


def _infer_cqed_alias(key: str, alias_index: dict[str, str] | None = None) -> str:
    alias_index = alias_index or {}
    if key in alias_index:
        return key
    reverse_alias = {v: k for k, v in alias_index.items()}
    if key in reverse_alias:
        return reverse_alias[key]
    lowered = str(key).lower()
    if any(token in lowered for token in ("resonator", "readout", "rr")):
        return "resonator"
    if any(token in lowered for token in ("transmon", "qubit", "qb")):
        return "transmon"
    if any(token in lowered for token in ("storage", "st")):
        return "storage"
    return key


def _migrate_legacy_to_cqed_params(raw: dict[str, Any]) -> dict[str, Any]:
    """Migrate v5.0.0 flat frequency/coherence dicts into cqed_params."""
    migrated = dict(raw)
    alias_index = dict(migrated.get("alias_index", {}) or {})
    cqed = dict(migrated.get("cqed_params", {}) or {})

    for element_key, freq_payload in dict(migrated.get("frequencies", {}) or {}).items():
        alias = _infer_cqed_alias(str(element_key), alias_index)
        entry = dict(cqed.get(alias, {}) or {})
        if isinstance(freq_payload, dict):
            for field in (
                "lo_freq", "if_freq", "rf_freq", "resonator_freq", "qubit_freq",
                "storage_freq", "ef_freq", "anharmonicity", "fock_freqs",
                "chi", "chi2", "chi3", "kappa", "kerr", "kerr2",
            ):
                if field in freq_payload and freq_payload[field] is not None:
                    entry[field] = freq_payload[field]
        cqed[alias] = entry

    for element_key, coh_payload in dict(migrated.get("coherence", {}) or {}).items():
        alias = _infer_cqed_alias(str(element_key), alias_index)
        entry = dict(cqed.get(alias, {}) or {})
        if isinstance(coh_payload, dict):
            for field in (
                "T1", "T1_us", "T2_ramsey", "T2_star_us", "T2_echo", "T2_echo_us",
                "qb_therm_clks", "ro_therm_clks", "st_therm_clks",
            ):
                if field in coh_payload and coh_payload[field] is not None:
                    entry[field] = coh_payload[field]
        cqed[alias] = entry

    migrated["cqed_params"] = cqed
    migrated["version"] = "5.1.0"
    return migrated


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
        matches this sample/cooldown/wiring context.
    strict_context : bool
        If True (default), a sample or wiring mismatch raises
        :class:`~qubox.core.errors.ContextMismatchError`.
        If False, mismatches are logged as warnings only.
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
                try:
                    raw = json.load(f)
                except json.JSONDecodeError as e:
                    raise ValueError(
                        f"Malformed calibration JSON at {self._path}: {e}"
                    ) from e
            if not isinstance(raw, dict):
                raise ValueError(
                    f"Calibration file {self._path} must contain a JSON object, "
                    f"got {type(raw).__name__}"
                )
            version_str = str(raw.get("version", ""))
            if version_str not in _SUPPORTED_CALIBRATION_VERSIONS:
                raise ValueError(
                    f"Unsupported calibration schema version '{version_str}' in {self._path}. "
                    "Supported: v5.0.0, v5.1.0. Migrate calibration.json before loading."
                )
            raw = _migrate_legacy_to_cqed_params(raw)
            return CalibrationData.model_validate(raw)
        ctx_block = None
        if self._context is not None:
            ctx_block = CalibrationContext(
                sample_id=self._context.sample_id,
                cooldown_id=self._context.cooldown_id,
                wiring_rev=self._context.wiring_rev,
                schema_version=str(getattr(self._context, "schema_version", "4.0.0")),
                config_hash=getattr(self._context, "config_hash", "") or "",
                created=datetime.now().isoformat(),
            )
        data = CalibrationData(
            version="5.1.0",
            context=ctx_block,
            created=datetime.now().isoformat(),
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(data)
        _logger.info("Default calibration created at %s", self._path)
        return data

    # ------------------------------------------------------------------
    # Alias index
    # ------------------------------------------------------------------
    def register_alias(self, alias: str, physical_id: str) -> None:
        """Map a human-friendly name to a physical channel ID."""
        self._data.alias_index[alias] = physical_id
        self._touch()

    def _resolve_key(self, key: str) -> str:
        return self._data.alias_index.get(key, key)

    def _dual_lookup(self, store: dict, key: str):
        result = store.get(key)
        if result is not None:
            return result
        physical_id = self._data.alias_index.get(key)
        if physical_id:
            return store.get(physical_id)
        return None

    def _resolve_cqed_alias(self, key: str) -> str:
        if key in self._data.cqed_params:
            return key
        return _infer_cqed_alias(key, self._data.alias_index)

    # ------------------------------------------------------------------
    # cQED params
    # ------------------------------------------------------------------
    def get_cqed_params(self, alias: str) -> CQEDParams | None:
        resolved = self._resolve_cqed_alias(alias)
        return self._data.cqed_params.get(resolved)

    def set_cqed_params(self, alias: str, params: CQEDParams | None = None, **kw) -> None:
        resolved = self._resolve_cqed_alias(alias)
        if params is None:
            existing = self._data.cqed_params.get(resolved)
            if existing:
                merged = existing.model_dump()
                merged.update({k: v for k, v in kw.items() if v is not None})
                params = CQEDParams(**merged)
            else:
                params = CQEDParams(**kw)
        self._data.cqed_params[resolved] = params
        self._touch()

    # ------------------------------------------------------------------
    # Discrimination
    # ------------------------------------------------------------------
    def get_discrimination(self, element: str) -> DiscriminationParams | None:
        return self._dual_lookup(self._data.discrimination, element)

    def set_discrimination(self, element: str, params: DiscriminationParams | None = None, **kw) -> None:
        physical_id = self._resolve_key(element)
        if params is None:
            existing = self._dual_lookup(self._data.discrimination, element)
            if existing:
                merged = existing.model_dump()
                merged.update({k: v for k, v in kw.items() if v is not None})
                params = DiscriminationParams(**merged)
            else:
                params = DiscriminationParams(**kw)
        self._data.discrimination[physical_id] = params
        self._touch()

    # ------------------------------------------------------------------
    # Readout quality
    # ------------------------------------------------------------------
    def get_readout_quality(self, element: str) -> ReadoutQuality | None:
        return self._dual_lookup(self._data.readout_quality, element)

    def set_readout_quality(self, element: str, params: ReadoutQuality | None = None, **kw) -> None:
        physical_id = self._resolve_key(element)
        if params is None:
            existing = self._dual_lookup(self._data.readout_quality, element)
            if existing:
                merged = existing.model_dump()
                merged.update({k: v for k, v in kw.items() if v is not None})
                params = ReadoutQuality(**merged)
            else:
                params = ReadoutQuality(**kw)
        self._data.readout_quality[physical_id] = params
        self._touch()

    # ------------------------------------------------------------------
    # Frequencies (proxied through cqed_params)
    # ------------------------------------------------------------------
    def get_frequencies(self, element: str) -> ElementFrequencies | None:
        cqed = self.get_cqed_params(element)
        if cqed is not None:
            freq_fields = set(ElementFrequencies.model_fields.keys())
            payload = {
                k: v for k, v in cqed.model_dump().items()
                if k in freq_fields and v is not None
            }
            if payload:
                return ElementFrequencies(**payload)
        return self._dual_lookup(self._data.frequencies, element)

    def set_frequencies(self, element: str, freqs: ElementFrequencies | None = None, **kw) -> None:
        if freqs is None:
            existing = self.get_frequencies(element)
            if existing:
                merged = existing.model_dump()
                merged.update({k: v for k, v in kw.items() if v is not None})
                freqs = ElementFrequencies(**merged)
            else:
                freqs = ElementFrequencies(**kw)
        self.set_cqed_params(element, **freqs.model_dump(exclude_none=True))

    # ------------------------------------------------------------------
    # Coherence (proxied through cqed_params)
    # ------------------------------------------------------------------
    def get_coherence(self, element: str) -> CoherenceParams | None:
        cqed = self.get_cqed_params(element)
        if cqed is not None:
            coherence_fields = set(CoherenceParams.model_fields.keys())
            payload = {
                k: v for k, v in cqed.model_dump().items()
                if k in coherence_fields and v is not None
            }
            if payload:
                return CoherenceParams(**payload)
        return self._dual_lookup(self._data.coherence, element)

    def set_coherence(self, element: str, params: CoherenceParams | None = None, **kw) -> None:
        if params is None:
            existing = self.get_coherence(element)
            if existing:
                merged = existing.model_dump()
                merged.update({k: v for k, v in kw.items() if v is not None})
                params = CoherenceParams(**merged)
            else:
                params = CoherenceParams(**kw)
        self.set_cqed_params(element, **params.model_dump(exclude_none=True))

    # ------------------------------------------------------------------
    # Pulse calibrations
    # ------------------------------------------------------------------
    def get_pulse_calibration(self, name: str) -> PulseCalibration | None:
        canonical = resolve_pulse_name(name)
        result = self._data.pulse_calibrations.get(canonical)
        if result is None and canonical != name:
            result = self._data.pulse_calibrations.get(name)
        return result

    def set_pulse_calibration(self, name: str, cal: PulseCalibration | None = None, **kw) -> None:
        canonical = resolve_pulse_name(name)
        if cal is None:
            existing = self._data.pulse_calibrations.get(canonical)
            if existing:
                merged = existing.model_dump()
                merged.update({k: v for k, v in kw.items() if v is not None})
                cal = PulseCalibration(**merged)
            else:
                kw.setdefault("pulse_name", canonical)
                cal = PulseCalibration(**kw)
        if cal.pulse_name != canonical:
            cal = cal.model_copy(update={"pulse_name": canonical})
        self._data.pulse_calibrations[canonical] = cal
        self._touch()

    # ------------------------------------------------------------------
    # Fit history
    # ------------------------------------------------------------------
    def store_fit(self, record: FitRecord) -> None:
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
        numeric = {k: float(v) for k, v in weight_info.items() if isinstance(v, (int, float))}
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
    # Transactional snapshot / restore
    # ------------------------------------------------------------------
    def create_in_memory_snapshot(self) -> dict[str, Any]:
        """Capture current in-memory state as a serialisable dict."""
        return self._data.model_dump()

    def restore_in_memory_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Restore from a previous snapshot dict (does not write to disk)."""
        self._data = CalibrationData.model_validate(
            _migrate_legacy_to_cqed_params(snapshot)
        )

    # ------------------------------------------------------------------
    # Bulk access
    # ------------------------------------------------------------------
    @property
    def data(self) -> CalibrationData:
        return self._data

    def to_dict(self) -> dict[str, Any]:
        return self._data.model_dump()

    def summary(self) -> str:
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
            ("cqed_params", self._data.cqed_params),
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
        """Create a timestamped backup of the current calibration file."""
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
        """Replace in-memory state from a raw dict."""
        self._data = CalibrationData.model_validate(_migrate_legacy_to_cqed_params(raw))
        self._touch()

    def stamp_context(self, context: Any) -> None:
        """Write or overwrite the context block from an ExperimentContext."""
        self._data.context = CalibrationContext(
            sample_id=context.sample_id,
            cooldown_id=context.cooldown_id,
            wiring_rev=context.wiring_rev,
            schema_version=str(getattr(context, "schema_version", "4.0.0")),
            config_hash=getattr(context, "config_hash", "") or "",
            created=datetime.now().isoformat(),
        )
        self._data.version = "5.1.0"
        self._touch()

    # ------------------------------------------------------------------
    # Context validation
    # ------------------------------------------------------------------
    def _validate_context(self, *, strict: bool = True) -> None:
        stored = self._data.context
        ctx = self._context
        if ctx is None:
            return
        if stored is None:
            raise ContextMismatchError(
                f"Calibration file {self._path} has no context block; v5.x context is required."
            )
        if stored.sample_id and ctx.sample_id and stored.sample_id != ctx.sample_id:
            msg = (
                f"Sample mismatch: calibration was made for sample "
                f"'{stored.sample_id}' but session uses '{ctx.sample_id}'"
            )
            if strict:
                raise ContextMismatchError(msg)
            _logger.warning(msg)
        if stored.wiring_rev and ctx.wiring_rev and stored.wiring_rev != ctx.wiring_rev:
            msg = (
                f"Wiring revision mismatch: calibration has '{stored.wiring_rev}' "
                f"but hardware.json hashes to '{ctx.wiring_rev}'"
            )
            if strict:
                raise ContextMismatchError(msg)
            _logger.warning(msg)
        if stored.cooldown_id and ctx.cooldown_id and stored.cooldown_id != ctx.cooldown_id:
            _logger.warning(
                "Cooldown mismatch: calibration was made for cooldown "
                "'%s' but session uses '%s'. Calibrations may be stale.",
                stored.cooldown_id, ctx.cooldown_id,
            )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _atomic_write(self, data: CalibrationData) -> None:
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=self._path.parent, prefix=".cal_tmp_", suffix=".json",
        )
        payload, dropped = sanitize_mapping_for_json(data.model_dump(exclude_none=True))
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
        self._data.last_modified = datetime.now().isoformat()
        if self._auto_save:
            self.save()
