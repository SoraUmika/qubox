from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Artifact:
    """Execution output artifact.

    - data: persistable/small arrays and scalar metadata
    - raw: large shot-level buffers kept memory-only by policy
    """

    name: str
    data: dict[str, Any]
    raw: dict[str, Any] | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def artifact_id(self) -> str:
        ts = self.meta.get("timestamp") or datetime.now().isoformat()
        return f"{self.name}:{ts}"


@dataclass
class CalibrationResult:
    """Pure analysis product used to build mutation patches."""

    kind: str
    transition: str | None = None  # "ge" or "ef"; None treated as "ge"
    params: dict[str, Any] = field(default_factory=dict)
    uncertainties: dict[str, Any] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return bool(self.quality.get("passed", False))


@dataclass
class UpdateOp:
    op: str
    payload: dict[str, Any]


@dataclass
class Patch:
    updates: list[UpdateOp] = field(default_factory=list)
    reason: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)

    def add(self, op: str, **payload: Any) -> None:
        self.updates.append(UpdateOp(op=op, payload=payload))

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason": self.reason,
            "provenance": self.provenance,
            "updates": [{"op": u.op, "payload": u.payload} for u in self.updates],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Patch":
        patch = cls(
            reason=str(data.get("reason", "")),
            provenance=dict(data.get("provenance", {}) or {}),
        )
        for item in data.get("updates", []) or []:
            patch.add(str(item.get("op", "")), **dict(item.get("payload", {}) or {}))
        return patch
