"""qubox.session.context — experiment context and wiring revision.

Migrated from ``qubox_v2_legacy.core.experiment_context``.
No external dependencies beyond the standard library.

An :class:`ExperimentContext` is a frozen record that ties a calibration file
to the exact physical hardware setup (sample + cooldown + wiring hash) that
produced it.  The ``wiring_rev`` is the first 8 hex characters of the
SHA-256 of ``hardware.json``, making it cheap to verify that the hardware
description has not been changed between sessions.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExperimentContext:
    """Immutable record linking a session to a physical device state.

    Parameters
    ----------
    sample_id : str
        Identifier for the physical sample (chip).
    cooldown_id : str
        Identifier for the fridge cooldown cycle.
    wiring_rev : str
        First 8 hex characters of SHA-256(hardware.json).
    schema_version : int
        Schema version of the context record (default 1).
    config_hash : str
        First 12 hex characters of SHA-256(all config files), or empty.
    """

    sample_id: str = ""
    cooldown_id: str = ""
    wiring_rev: str = ""
    schema_version: int = 1
    config_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "cooldown_id": self.cooldown_id,
            "wiring_rev": self.wiring_rev,
            "schema_version": self.schema_version,
            "config_hash": self.config_hash,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ExperimentContext":
        return cls(
            sample_id=str(d.get("sample_id", "")),
            cooldown_id=str(d.get("cooldown_id", "")),
            wiring_rev=str(d.get("wiring_rev", "")),
            schema_version=int(d.get("schema_version", 1)),
            config_hash=str(d.get("config_hash", "")),
        )


def compute_wiring_rev(hardware_path: str | Path) -> str:
    """Compute an 8-character wiring revision hash from *hardware.json*.

    The hash is the first 8 hex characters of SHA-256 of the canonical
    (sorted-keys) JSON serialisation of the file.  This is stable across
    whitespace changes but sensitive to any structural modification.

    Parameters
    ----------
    hardware_path : str | Path
        Path to ``hardware.json``.

    Returns
    -------
    str
        8-character lowercase hex string, e.g. ``"a3f9b21c"``.
    """
    path = Path(hardware_path)
    raw = json.loads(path.read_bytes())
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    return digest[:8]
