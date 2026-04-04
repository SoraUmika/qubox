from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any


def _merge_override(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_override(merged[key], value)
        else:
            merged[key] = value
    return merged


@dataclass(frozen=True)
class CalibrationSnapshot:
    """Frozen record of calibration state at a specific point in time.

    Captures the full calibration data, the source path, any overrides applied,
    and provenance metadata (version, timestamp, build_hash).  Attached to
    ``ProgramBuildResult`` and ``ExperimentResult`` so that every compiled
    program can answer "what calibration was active when this was built?"
    """

    source_path: str
    data: dict[str, Any]
    overrides: dict[str, Any] = field(default_factory=dict)
    version: str = ""
    build_hash: str = ""
    mixer_calibration_path: str = ""
    timestamp: str = field(default_factory=lambda: datetime.datetime.now().isoformat())

    @classmethod
    def from_session(cls, session: Any, *, overrides: dict[str, Any] | None = None) -> CalibrationSnapshot:
        """Capture calibration snapshot from a session object.

        Works with both the new Session facade (``session.session_manager``)
        and direct ``SessionManager`` instances (``session.calibration``).
        """
        # Try new facade first, fall back to direct calibration access
        cal = getattr(session, "calibration", None)
        session_manager = getattr(session, "session_manager", None)
        if session_manager is not None:
            cal = getattr(session_manager, "calibration", cal)

        if cal is None:
            return cls(source_path="<unavailable>", data={}, overrides=dict(overrides or {}))

        raw = dict(cal.to_dict()) if hasattr(cal, "to_dict") else {}
        merged = _merge_override(raw, overrides or {})
        source = str(getattr(cal, "path", "<in-memory>"))
        version = str(raw.get("version", ""))
        build_hash = str(raw.get("build_hash", ""))

        # Detect mixer calibration DB path from hardware controller
        mixer_path = ""
        hw = getattr(session, "hardware", getattr(session, "hw", None))
        if session_manager is not None and hw is None:
            hw = getattr(session_manager, "hardware", getattr(session_manager, "hw", None))
        cal_db = getattr(hw, "_cal_db_path", None)
        if cal_db is not None:
            mixer_path = str(cal_db)

        return cls(
            source_path=source,
            data=merged,
            overrides=dict(overrides or {}),
            version=version,
            build_hash=build_hash,
            mixer_calibration_path=mixer_path,
        )

    def to_dict(self, *, include_data: bool = False) -> dict[str, Any]:
        """Serialise to a JSON-friendly dict.

        Parameters
        ----------
        include_data : bool
            If ``True``, include the full calibration data payload.
            Default ``False`` to keep manifests lightweight.
        """
        d: dict[str, Any] = {
            "source_path": self.source_path,
            "version": self.version,
            "build_hash": self.build_hash,
            "mixer_calibration_path": self.mixer_calibration_path,
            "timestamp": self.timestamp,
        }
        if self.overrides:
            d["overrides"] = dict(self.overrides)
        if include_data:
            d["data"] = dict(self.data)
        return d


@dataclass
class CalibrationProposal:
    updates: list[dict[str, Any]]
    reason: str = ""
    preview: dict[str, Any] | None = None

    def review(self) -> str:
        lines = [self.reason or "Calibration proposal"]
        for update in self.updates:
            lines.append(f"- {update.get('op')}: {update.get('payload')}")
        return "\n".join(lines)

    def apply(self, session, *, dry_run: bool = False) -> dict[str, Any]:
        from qubox.calibration.contracts import Patch

        patch = Patch(reason=self.reason or "Applied from qubox result proposal")
        for update in self.updates:
            patch.add(str(update.get("op", "")), **dict(update.get("payload", {}) or {}))
        return session.orchestrator.apply_patch(patch, dry_run=dry_run)
