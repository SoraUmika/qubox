from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

import numpy as np


@dataclass(frozen=True)
class MeasureSpec:
    kind: str
    acquire: tuple[str, ...] = ("I", "Q")
    policy: str | None = None
    policy_kwargs: dict[str, Any] = field(default_factory=dict)
    calibration_snapshot: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MeasureGate:
    target: str | tuple[str, ...]
    spec: MeasureSpec


@dataclass(frozen=True)
class StateRule:
    """Post-processing rule that derives a boolean state from IQ data."""

    kind: str = "I_threshold"
    threshold: Any = 0.0
    sense: str = "greater"
    rotation_angle: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _stable_hash(payload: dict[str, Any]) -> str:
    try:
        blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    except Exception:
        blob = repr(payload).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def build_readout_snapshot_from_macro() -> dict[str, Any]:
    from .macros.measure import measureMacro

    ro_disc = dict(getattr(measureMacro, "_ro_disc_params", {}) or {})
    snapshot = {
        "source": "measureMacro",
        "element": measureMacro.active_element(),
        "operation": measureMacro.active_op(),
        "threshold": ro_disc.get("threshold"),
        "rotation_angle": ro_disc.get("angle"),
        "fidelity": ro_disc.get("fidelity"),
        "fidelity_definition": ro_disc.get("fidelity_definition"),
        "sigma_g": ro_disc.get("sigma_g"),
        "sigma_e": ro_disc.get("sigma_e"),
        "weights": tuple(tuple(w) if isinstance(w, (list, tuple)) else (str(w),) for w in (measureMacro.get_outputs() or [])),
        "policy": {
            "name": None,
            "kwargs": {},
        },
    }
    snapshot["version_hash"] = _stable_hash(snapshot)
    return snapshot


def try_build_readout_snapshot_from_macro() -> dict[str, Any] | None:
    try:
        return build_readout_snapshot_from_macro()
    except Exception:
        return None


def build_readout_snapshot_from_handle(readout: Any) -> dict[str, Any]:
    cal = getattr(readout, "cal", None)
    snapshot = {
        "source": "ReadoutHandle",
        "element": getattr(readout, "element", None),
        "operation": getattr(readout, "operation", None),
        "threshold": getattr(cal, "threshold", None),
        "rotation_angle": getattr(cal, "rotation_angle", None),
        "fidelity": getattr(cal, "fidelity", None),
        "fidelity_definition": getattr(cal, "fidelity_definition", None),
        "sigma_g": getattr(cal, "sigma_g", None),
        "sigma_e": getattr(cal, "sigma_e", None),
        "weights": tuple(getattr(cal, "weight_keys", ()) or ()),
        "policy": {
            "name": None,
            "kwargs": {},
        },
    }
    snapshot["version_hash"] = _stable_hash(snapshot)
    return snapshot


def emit_measurement_spec(
    spec: MeasureSpec,
    *,
    targets: list | None = None,
    with_state: bool = False,
    state: Any = None,
    gain: float | None = None,
    timestamp_stream: Any = None,
    adc_stream: Any = None,
    readout: Any = None,
    axis: str = "z",
    x90: str = "x90",
    yn90: str = "yn90",
    qb_el: str | None = None,
):
    if readout is not None:
        from .macros.measure import emit_measurement

        return emit_measurement(
            readout,
            with_state=with_state,
            targets=targets,
            state=state,
            gain=gain,
            timestamp_stream=timestamp_stream,
            adc_stream=adc_stream,
            axis=axis,
            x90=x90,
            yn90=yn90,
            qb_el=qb_el,
        )

    from .macros.measure import measureMacro

    kind = (spec.kind or "").lower()
    if kind in {"iq", "discriminate", "butterfly", "adc"}:
        return measureMacro.measure(
            with_state=with_state,
            targets=targets,
            state=state,
            gain=gain,
            timestamp_stream=timestamp_stream,
            adc_stream=adc_stream,
            axis=axis,
            x90=x90,
            yn90=yn90,
            qb_el=qb_el,
        )

    raise ValueError(f"Unsupported measurement kind: {spec.kind!r}")


def _coerce_state_numeric(value: Any, *, field_name: str) -> float:
    if value is None:
        raise ValueError(f"StateRule.{field_name} is required for derive_state().")
    if isinstance(value, (int, float, np.floating, np.integer)):
        return float(value)
    raise TypeError(
        f"derive_state() expected a resolved numeric StateRule.{field_name}, "
        f"got {type(value).__name__}."
    )


def _coerce_iq_arrays(iq: Any) -> tuple[np.ndarray, np.ndarray]:
    if isinstance(iq, dict):
        if "I" not in iq or "Q" not in iq:
            raise ValueError("IQ dict input must contain 'I' and 'Q' keys.")
        return np.asarray(iq["I"], dtype=float), np.asarray(iq["Q"], dtype=float)

    if isinstance(iq, np.ndarray) and np.iscomplexobj(iq):
        return np.asarray(iq.real, dtype=float), np.asarray(iq.imag, dtype=float)

    if isinstance(iq, (tuple, list)) and len(iq) == 2:
        return np.asarray(iq[0], dtype=float), np.asarray(iq[1], dtype=float)

    raise TypeError(
        "derive_state() expects IQ data as {'I': ..., 'Q': ...}, "
        "(I, Q), or a complex numpy array."
    )


def derive_state(iq: Any, rule: StateRule) -> np.ndarray:
    """Derive boolean state labels from IQ data using a resolved StateRule."""

    kind = str(rule.kind or "").strip().lower()
    if kind != "i_threshold":
        raise ValueError(f"Unsupported StateRule.kind: {rule.kind!r}")

    I_data, Q_data = _coerce_iq_arrays(iq)
    threshold = _coerce_state_numeric(rule.threshold, field_name="threshold")
    rotation_angle = 0.0 if rule.rotation_angle is None else _coerce_state_numeric(
        rule.rotation_angle,
        field_name="rotation_angle",
    )

    if rotation_angle:
        cos_theta = float(np.cos(rotation_angle))
        sin_theta = float(np.sin(rotation_angle))
        rotated_I = (I_data * cos_theta) - (Q_data * sin_theta)
    else:
        rotated_I = I_data

    sense = str(rule.sense or "greater").strip().lower()
    if sense in {"greater", "gt", ">"}:
        return np.asarray(rotated_I > threshold, dtype=bool)
    if sense in {"less", "lt", "<"}:
        return np.asarray(rotated_I < threshold, dtype=bool)
    raise ValueError(f"Unsupported StateRule.sense: {rule.sense!r}")
