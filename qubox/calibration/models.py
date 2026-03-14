from __future__ import annotations

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
    source_path: str
    data: dict[str, Any]
    overrides: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_session(cls, session, *, overrides: dict[str, Any] | None = None) -> "CalibrationSnapshot":
        raw = dict(session.legacy_session.calibration.to_dict())
        merged = _merge_override(raw, overrides or {})
        return cls(
            source_path=str(session.legacy_session.calibration.path),
            data=merged,
            overrides=dict(overrides or {}),
        )


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
        from qubox_v2_legacy.calibration.contracts import Patch

        patch = Patch(reason=self.reason or "Applied from qubox result proposal")
        for update in self.updates:
            patch.add(str(update.get("op", "")), **dict(update.get("payload", {}) or {}))
        return session.legacy_session.orchestrator.apply_patch(patch, dry_run=dry_run)
