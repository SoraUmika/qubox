"""qubox.calibration.history — calibration snapshot utilities.

No external dependencies beyond the standard library and Pydantic.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .store_models import CalibrationData

_logger = logging.getLogger(__name__)


def list_snapshots(calibration_dir: str | Path) -> list[Path]:
    """List all calibration snapshot files in *calibration_dir*, sorted by mtime."""
    d = Path(calibration_dir)
    snapshots = sorted(d.glob("calibration_*.json"), key=lambda p: p.stat().st_mtime)
    return snapshots


def load_snapshot(path: str | Path) -> CalibrationData:
    """Load a specific calibration snapshot from *path*."""
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return CalibrationData.model_validate(raw)


def diff_snapshots(
    old: CalibrationData, new: CalibrationData
) -> dict[str, Any]:
    """Compare two calibration snapshots and return changed top-level keys.

    Returns a dict mapping each changed key to ``{"old": ..., "new": ...}``.
    Timestamp keys (``last_modified``, ``created``) are excluded.
    """
    old_d = old.model_dump()
    new_d = new.model_dump()
    changes: dict[str, Any] = {}
    for key in set(old_d) | set(new_d):
        if key in ("last_modified", "created"):
            continue
        old_val = old_d.get(key)
        new_val = new_d.get(key)
        if old_val != new_val:
            changes[key] = {"old": old_val, "new": new_val}
    return changes
