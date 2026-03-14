from __future__ import annotations

from typing import Any

import numpy as np


def _extract(output: Any, key: str):
    if output is None:
        return None
    extract = getattr(output, "extract", None)
    if callable(extract):
        try:
            return extract(key)
        except Exception:
            return None
    if isinstance(output, dict):
        return output.get(key)
    return None


def _first_measure_key(build: Any, output: Any) -> str | None:
    metadata = dict(getattr(build, "metadata", {}) or {})
    schema = metadata.get("measurement_schema") or {}
    records = list(schema.get("records") or [])
    if records:
        return str(records[0].get("key"))
    if isinstance(output, dict):
        for key in output:
            if isinstance(key, str) and key.endswith(".I"):
                return key[:-2]
    return None


def run_named_pipeline(name: str | None, *, run_result: Any, build: Any = None) -> dict[str, Any]:
    """Lightweight registry for custom-sequence analysis."""

    pipeline = str(name or "raw").strip().lower()
    output = getattr(run_result, "output", None)
    if pipeline == "raw":
        return {"mode": "raw", "data": dict(output or {})}

    measure_key = _first_measure_key(build, output)
    if measure_key is None:
        return {"mode": pipeline, "data": dict(output or {})}

    I = _extract(output, f"{measure_key}.I")
    Q = _extract(output, f"{measure_key}.Q")
    if I is None or Q is None:
        return {"mode": pipeline, "data": dict(output or {}), "measure_key": measure_key}

    I_arr = np.asarray(I)
    Q_arr = np.asarray(Q)
    signal = I_arr + 1j * Q_arr
    payload = {
        "mode": pipeline,
        "measure_key": measure_key,
        "I": I_arr,
        "Q": Q_arr,
        "signal": signal,
        "magnitude": np.abs(signal),
        "phase": np.angle(signal),
    }

    if pipeline in {"iq_magnitude", "ramsey_like", "classified"}:
        state = _extract(output, f"{measure_key}.state")
        if state is not None:
            state_arr = np.asarray(state)
            payload["state"] = state_arr
            payload["population_e"] = float(np.mean(state_arr))
        return payload

    return {"mode": pipeline, "data": dict(output or {})}
