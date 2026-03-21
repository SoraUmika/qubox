"""qubox.core.persistence — JSON sanitization and array persistence policy.

Migrated from ``qubox_v2_legacy.core.persistence_policy`` with no changes to
logic.  Provides helpers used by CalibrationStore, ArtifactManager, and the
config-snapshot utilities to ensure JSON serialisability and to drop
shot-level raw arrays that would bloat disk artifacts.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

import numpy as np


DEFAULT_MAX_ARRAY_ELEMS = 8192

_RAW_KEY_RE = re.compile(
    r"(?:^|[_-])(raw|shot|shots|sample|samples|buffer|acq|acquisition)(?:$|[_-])",
    re.IGNORECASE,
)


def is_raw_like_key(key: str | None) -> bool:
    if not key:
        return False
    return _RAW_KEY_RE.search(str(key)) is not None


def should_persist_array(
    key: str | None,
    arr: "np.ndarray",
    *,
    max_array_elems: int = DEFAULT_MAX_ARRAY_ELEMS,
) -> bool:
    if is_raw_like_key(key):
        return False
    return int(arr.size) <= int(max_array_elems)


def split_output_for_persistence(
    data: Mapping[str, Any],
    *,
    max_array_elems: int = DEFAULT_MAX_ARRAY_ELEMS,
) -> tuple[dict[str, "np.ndarray"], dict[str, Any], dict[str, Any]]:
    """Split a data mapping into (arrays, meta, dropped).

    - *arrays*: numpy arrays suitable for np.savez_compressed.
    - *meta*: JSON-serialisable scalars/lists.
    - *dropped*: fields omitted due to raw-data policy, with shape metadata.
    """
    arrays: dict[str, Any] = {}
    meta: dict[str, Any] = {}
    dropped: dict[str, Any] = {}

    for key, value in data.items():
        if isinstance(value, np.ndarray):
            if should_persist_array(key, value, max_array_elems=max_array_elems):
                arrays[key] = value
            else:
                dropped[key] = {
                    "kind": "ndarray",
                    "shape": list(value.shape),
                    "size": int(value.size),
                }
            continue

        sanitized, dropped_local = _sanitize_with_drops(
            value,
            key=key,
            path=str(key),
            max_array_elems=max_array_elems,
        )
        if sanitized is _DROP:
            dropped[str(key)] = {"kind": type(value).__name__}
        else:
            meta[key] = sanitized
        dropped.update(dropped_local)

    return arrays, meta, dropped


_DROP = object()


def sanitize_for_json(
    value: Any,
    *,
    key: str | None = None,
    max_array_elems: int = DEFAULT_MAX_ARRAY_ELEMS,
) -> Any:
    """Return a JSON-serialisable version of *value*, dropping oversized arrays."""
    sanitized, _ = _sanitize_with_drops(
        value,
        key=key,
        path=(str(key) if key is not None else "root"),
        max_array_elems=max_array_elems,
    )
    return sanitized


def sanitize_mapping_for_json(
    data: Mapping[str, Any],
    *,
    max_array_elems: int = DEFAULT_MAX_ARRAY_ELEMS,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(sanitized_dict, dropped_dict)`` from a mapping."""
    out: dict[str, Any] = {}
    dropped: dict[str, Any] = {}
    for key, value in data.items():
        sanitized, dropped_local = _sanitize_with_drops(
            value,
            key=str(key),
            path=str(key),
            max_array_elems=max_array_elems,
        )
        if sanitized is _DROP:
            dropped[str(key)] = {"kind": type(value).__name__}
        else:
            out[str(key)] = sanitized
        dropped.update(dropped_local)
    return out, dropped


def _sanitize_with_drops(
    value: Any,
    *,
    key: str | None,
    path: str,
    max_array_elems: int,
) -> tuple[Any, dict[str, Any]]:
    dropped: dict[str, Any] = {}

    if isinstance(value, np.ndarray):
        if not should_persist_array(key, value, max_array_elems=max_array_elems):
            dropped[path] = {
                "kind": "ndarray",
                "shape": list(value.shape),
                "size": int(value.size),
            }
            return _DROP, dropped
        return value.tolist(), dropped

    if isinstance(value, (np.integer,)):
        return int(value), dropped
    if isinstance(value, (np.floating,)):
        return float(value), dropped
    if isinstance(value, (np.complexfloating, complex)):
        return {"re": float(value.real), "im": float(value.imag)}, dropped

    if isinstance(value, Path):
        return str(value), dropped

    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for child_key, child_value in value.items():
            child_path = f"{path}.{child_key}"
            child, child_dropped = _sanitize_with_drops(
                child_value,
                key=str(child_key),
                path=child_path,
                max_array_elems=max_array_elems,
            )
            if child is not _DROP:
                out[str(child_key)] = child
            dropped.update(child_dropped)
        return out, dropped

    if isinstance(value, (list, tuple)):
        if is_raw_like_key(key) and len(value) > 0:
            dropped[path] = {"kind": type(value).__name__, "len": len(value)}
            return _DROP, dropped
        if len(value) > max_array_elems and _is_numeric_sequence(value):
            dropped[path] = {"kind": type(value).__name__, "len": len(value)}
            return _DROP, dropped
        out_list: list[Any] = []
        for idx, item in enumerate(value):
            child, child_dropped = _sanitize_with_drops(
                item,
                key=key,
                path=f"{path}[{idx}]",
                max_array_elems=max_array_elems,
            )
            if child is not _DROP:
                out_list.append(child)
            dropped.update(child_dropped)
        return out_list, dropped

    if isinstance(value, (str, bool, int, float)) or value is None:
        return value, dropped

    return str(value), dropped


def _is_numeric_sequence(value: "list[Any] | tuple[Any, ...]") -> bool:
    if not value:
        return False
    for item in value:
        if isinstance(item, (int, float, np.integer, np.floating)):
            continue
        return False
    return True
