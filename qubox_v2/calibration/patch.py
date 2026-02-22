# qubox_v2/calibration/patch.py
"""CalibrationPatch application logic.

Provides the ``apply_patch`` function that safely applies a CalibrationPatch
to a CalibrationStore, enforcing stale-value checks and creating snapshots.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .state_machine import CalibrationPatch, PatchEntry

_logger = logging.getLogger(__name__)


class StalePatchError(Exception):
    """Raised when a patch entry's old_value doesn't match the current store."""

    def __init__(self, entry: PatchEntry, actual_value: Any):
        self.entry = entry
        self.actual_value = actual_value
        super().__init__(
            f"Stale patch: {entry.path} expected old_value={entry.old_value!r} "
            f"but current value is {actual_value!r}. "
            f"Re-run the experiment to produce a fresh patch."
        )


def _get_nested(data: dict, dotted_path: str) -> Any:
    """Retrieve a value from a nested dict using dotted path notation.

    >>> _get_nested({"a": {"b": 1}}, "a.b")
    1
    """
    keys = dotted_path.split(".")
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
        if current is None:
            return None
    return current


def _set_nested(data: dict, dotted_path: str, value: Any) -> None:
    """Set a value in a nested dict using dotted path notation.

    Creates intermediate dicts as needed.

    >>> d = {}
    >>> _set_nested(d, "a.b.c", 42)
    >>> d
    {'a': {'b': {'c': 42}}}
    """
    keys = dotted_path.split(".")
    current = data
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


def validate_patch_freshness(patch: CalibrationPatch, store_data: dict) -> list[str]:
    """Check that all patch entries have matching old_values in the store.

    Returns a list of stale entry descriptions. Empty list means all fresh.
    """
    stale = []
    for entry in patch.changes:
        actual = _get_nested(store_data, entry.path)
        if entry.old_value is not None and actual != entry.old_value:
            stale.append(
                f"{entry.path}: expected {entry.old_value!r}, got {actual!r}"
            )
    return stale


def apply_patch(
    store,  # CalibrationStore
    patch: CalibrationPatch,
    *,
    force: bool = False,
    snapshot: bool = True,
    history_path: str | Path | None = None,
) -> None:
    """Apply a CalibrationPatch to a CalibrationStore.

    Parameters
    ----------
    store : CalibrationStore
        The calibration store to modify.
    patch : CalibrationPatch
        The patch to apply. Must be approved (validation passed or overrides set).
    force : bool
        If True, skip stale-value checks. Use with caution.
    snapshot : bool
        If True, create a snapshot before applying.
    history_path : str | Path | None
        Path to calibration_history.jsonl. If None, uses
        ``store.path.parent / "calibration_history.jsonl"``.

    Raises
    ------
    ValueError
        If the patch is not approved.
    StalePatchError
        If any entry's old_value doesn't match the current store (unless force=True).
    """
    if not patch.is_approved() and not force:
        raise ValueError(
            f"Patch for {patch.experiment!r} is not approved. "
            f"Call patch.override_validation() for failed gates or re-analyze."
        )

    # Stale check
    if not force:
        store_data = store.to_dict()
        stale = validate_patch_freshness(patch, store_data)
        if stale:
            raise StalePatchError(patch.changes[0], _get_nested(store_data, patch.changes[0].path))

    # Snapshot
    if snapshot:
        try:
            snap_path = store.snapshot(tag=f"pre_{patch.experiment}")
            _logger.info("Calibration snapshot saved: %s", snap_path)
        except Exception as exc:
            _logger.warning("Failed to create snapshot: %s", exc)

    # Apply changes
    store_data = store.to_dict()
    for entry in patch.changes:
        _set_nested(store_data, entry.path, entry.new_value)
        _logger.info(
            "Applying patch: %s = %r → %r",
            entry.path, entry.old_value, entry.new_value,
        )

    # Update timestamp
    store_data["last_modified"] = datetime.now().isoformat()

    # Write back to store
    store.reload_from_dict(store_data)
    store.save()

    # Append to history
    if history_path is None:
        history_path = Path(store.path).parent / "calibration_history.jsonl"
    else:
        history_path = Path(history_path)

    history_entry = {
        **patch.to_dict(),
        "action": "commit",
    }
    try:
        with open(history_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(history_entry, default=str) + "\n")
        _logger.info("Calibration history appended: %s", history_path)
    except Exception as exc:
        _logger.error("Failed to write calibration history: %s", exc)

    _logger.info(
        "CalibrationPatch applied: %s (%d changes)",
        patch.experiment, len(patch.changes),
    )
