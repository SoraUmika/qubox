from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
from typing import Any


@dataclass(frozen=True)
class GateFamily:
    name: str
    base_operation: str
    derived_operations: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class GateTuningRecord:
    family: str
    target: str
    base_operation: str
    amplitude_scale: float = 1.0
    detune_hz: float = 0.0
    phase_offset_rad: float = 0.0
    source_experiment: str | None = None
    notes: str | None = None
    derived_operations: dict[str, float] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def record_id(self) -> str:
        payload = {
            "family": self.family,
            "target": self.target,
            "base_operation": self.base_operation,
            "amplitude_scale": self.amplitude_scale,
            "detune_hz": self.detune_hz,
            "phase_offset_rad": self.phase_offset_rad,
            "derived_operations": self.derived_operations,
            "timestamp": self.timestamp,
        }
        blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()[:16]

    def derive_for_operation(self, operation: str) -> dict[str, Any] | None:
        if operation == self.base_operation:
            factor = 1.0
        else:
            factor = self.derived_operations.get(operation)
            if factor is None:
                return None

        return {
            "family": self.family,
            "target": self.target,
            "operation": operation,
            "base_operation": self.base_operation,
            "amplitude_scale": float(self.amplitude_scale) * float(factor),
            "detune_hz": float(self.detune_hz),
            "phase_offset_rad": float(self.phase_offset_rad),
            "derived_factor": float(factor),
            "record_id": self.record_id,
        }


@dataclass
class GateTuningStore:
    records: list[GateTuningRecord] = field(default_factory=list)

    def add_record(self, record: GateTuningRecord) -> None:
        self.records.append(record)

    def resolve(self, *, target: str, operation: str) -> dict[str, Any] | None:
        for record in reversed(self.records):
            if record.target != target:
                continue
            resolved = record.derive_for_operation(operation)
            if resolved is not None:
                return resolved
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "records": [
                {
                    "record_id": rec.record_id,
                    "family": rec.family,
                    "target": rec.target,
                    "base_operation": rec.base_operation,
                    "amplitude_scale": rec.amplitude_scale,
                    "detune_hz": rec.detune_hz,
                    "phase_offset_rad": rec.phase_offset_rad,
                    "source_experiment": rec.source_experiment,
                    "notes": rec.notes,
                    "derived_operations": dict(rec.derived_operations),
                    "timestamp": rec.timestamp,
                }
                for rec in self.records
            ]
        }


def default_xy_family() -> GateFamily:
    return GateFamily(
        name="X",
        base_operation="x180",
        derived_operations={"x90": 0.5, "xn90": -0.5},
    )


def make_xy_tuning_record(
    *,
    target: str,
    amplitude_scale: float,
    detune_hz: float = 0.0,
    phase_offset_rad: float = 0.0,
    source_experiment: str | None = None,
    notes: str | None = None,
) -> GateTuningRecord:
    family = default_xy_family()
    return GateTuningRecord(
        family=family.name,
        target=target,
        base_operation=family.base_operation,
        amplitude_scale=float(amplitude_scale),
        detune_hz=float(detune_hz),
        phase_offset_rad=float(phase_offset_rad),
        source_experiment=source_experiment,
        notes=notes,
        derived_operations=dict(family.derived_operations),
    )
