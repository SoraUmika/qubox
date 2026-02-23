# qubox_v2/core/experiment_context.py
"""Immutable experiment context carrying device and cooldown identity.

An ExperimentContext is a frozen passport that travels through the system,
binding a session to a specific device, cooldown, and hardware wiring
configuration.  It is constructed once during session setup and never mutated.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExperimentContext:
    """Immutable identity context for an experiment session.

    Attributes
    ----------
    device_id : str
        Unique identifier for a physical sample + wiring configuration.
    cooldown_id : str
        Identifier for a specific cooldown cycle of the device.
    wiring_rev : str
        SHA-256 prefix (first 8 hex chars) of hardware.json content.
    schema_version : str
        Calibration schema version (e.g., ``"4.0.0"``).
    config_hash : str
        Combined SHA-256 hash from SessionState or config directory.
    """

    device_id: str
    cooldown_id: str
    wiring_rev: str
    schema_version: str = "4.0.0"
    config_hash: str = ""

    def to_dict(self) -> dict[str, str]:
        """Serialize to a JSON-compatible dict."""
        return {
            "device_id": self.device_id,
            "cooldown_id": self.cooldown_id,
            "wiring_rev": self.wiring_rev,
            "schema_version": self.schema_version,
            "config_hash": self.config_hash,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ExperimentContext:
        """Deserialize from a dict."""
        return cls(
            device_id=str(d.get("device_id", "")),
            cooldown_id=str(d.get("cooldown_id", "")),
            wiring_rev=str(d.get("wiring_rev", "")),
            schema_version=str(d.get("schema_version", "4.0.0")),
            config_hash=str(d.get("config_hash", "")),
        )

    def matches_device(self, other_device_id: str) -> bool:
        """Check whether this context belongs to the given device."""
        return self.device_id == other_device_id

    def matches_wiring(self, hardware_hash: str) -> bool:
        """Check whether the hardware wiring revision matches."""
        return self.wiring_rev == hardware_hash

    def matches_cooldown(self, other_cooldown_id: str) -> bool:
        """Check whether the cooldown identifier matches."""
        return self.cooldown_id == other_cooldown_id

    @staticmethod
    def compute_wiring_rev(hardware_path: Path) -> str:
        """Compute SHA-256 first 8 hex chars of hardware.json content."""
        raw = hardware_path.read_bytes()
        return hashlib.sha256(raw).hexdigest()[:8]
