"""
Shared utility functions used across qubox subsystems.
"""
from __future__ import annotations

import contextlib
import json
import time
from copy import deepcopy
from typing import Any, Callable, Dict, Set

import numpy as np


# ---------------------------------------------------------------------------
# JSON / dict helpers
# ---------------------------------------------------------------------------
def numeric_keys_to_ints(obj: Any) -> Any:
    """Recursively coerce string-digit keys to ints (for QM config dicts)."""
    if isinstance(obj, dict):
        return {
            (int(k) if isinstance(k, str) and k.isdigit() else k): numeric_keys_to_ints(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [numeric_keys_to_ints(v) for v in obj]
    return obj


def json_dump(obj: Any, **kw) -> str:
    """JSON-serialize with numpy type handling."""
    def _default(o):
        if isinstance(o, (np.floating, np.integer)):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
        raise TypeError(f"Unserializable: {type(o)}")
    return json.dumps(obj, default=_default, **kw)


def deep_merge(dst: dict, src: dict) -> dict:
    """
    Deep-merge *src* into *dst* (non-mutating).
    If both values are dicts, merges recursively; otherwise src overwrites.
    """
    out = deepcopy(dst)
    for k, v in (src or {}).items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = deepcopy(v)
    return out


def key_like(d: dict, k: int | str) -> int | str:
    """Return the existing key in *d* that matches *k* (handles '3' vs 3)."""
    if k in d:
        return k
    if isinstance(k, int) and str(k) in d:
        return str(k)
    if isinstance(k, str) and k.isdigit() and int(k) in d:
        return int(k)
    return k


def get_nested(d: dict, path: list, default=None):
    """Traverse nested dicts by key path."""
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def select_keys(d: dict, keys: Set[str]) -> dict:
    """Return a deep copy of only the specified keys."""
    return {k: deepcopy(v) for k, v in d.items() if k in keys}


def require(cond: bool, msg: str, exc_type: type = RuntimeError) -> None:
    """Compact guard: raise *exc_type(msg)* if *cond* is False."""
    if not cond:
        raise exc_type(msg)


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------
def with_retries(
    fn: Callable,
    *,
    attempts: int = 3,
    backoff: float = 0.5,
    exc_types: tuple = (),
):
    """Call *fn()* with exponential-backoff retries on transient exceptions."""
    for k in range(attempts):
        try:
            return fn()
        except exc_types as e:
            if k == attempts - 1:
                raise
            sleep_s = backoff * (2 ** k)
            time.sleep(sleep_s)
