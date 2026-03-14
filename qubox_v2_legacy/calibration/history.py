# qubox_v2/calibration/history.py
"""Calibration history utilities.

Provides helpers for comparing snapshots and restoring previous states.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.logging import get_logger
from .models import CalibrationData

_logger = get_logger(__name__)


def list_snapshots(calibration_dir: str | Path) -> list[Path]:
    """List all calibration snapshot files in a directory, sorted by time."""
    d = Path(calibration_dir)
    pattern = "calibration_*.json"
    snapshots = sorted(d.glob(pattern), key=lambda p: p.stat().st_mtime)
    return snapshots


def load_snapshot(path: str | Path) -> CalibrationData:
    """Load a specific calibration snapshot."""
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return CalibrationData.model_validate(raw)


def diff_snapshots(
    old: CalibrationData, new: CalibrationData
) -> dict[str, Any]:
    """Compare two calibration snapshots and return differences.

    Returns a dict with keys that changed, each mapping to
    {"old": ..., "new": ...}.
    """
    old_d = old.model_dump()
    new_d = new.model_dump()
    changes: dict[str, Any] = {}

    all_keys = set(old_d) | set(new_d)
    for key in all_keys:
        if key in ("last_modified", "created"):
            continue
        old_val = old_d.get(key)
        new_val = new_d.get(key)
        if old_val != new_val:
            changes[key] = {"old": old_val, "new": new_val}

    return changes
