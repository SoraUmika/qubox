from __future__ import annotations
import hashlib
import json
from typing import Any

def stable_hash(obj: Any) -> str:
    """
    Stable md5 hash for dict-like objects.
    - sort_keys=True for determinism
    - default=str to serialize numpy scalars, etc.
    """
    s = json.dumps(obj, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.md5(s).hexdigest()

def array_md5(arr) -> str:
    """
    Stable md5 for numeric arrays (float64 view + shape header).
    Matches what you already do, just centralized.
    """
    import numpy as np
    a = np.asarray(arr, dtype=np.float64)
    header = str(a.shape).encode("utf-8")
    m = hashlib.md5()
    m.update(header)
    m.update(a.tobytes(order="C"))
    return m.hexdigest()

