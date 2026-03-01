from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any


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
):
    if readout is not None:
        from .macros.measure import emit_measurement

        if with_state and state is None:
            from qm.qua import declare
            state = declare(bool)

        return emit_measurement(
            readout,
            targets=targets,
            state=state if with_state else None,
            gain=gain,
            timestamp_stream=timestamp_stream,
            adc_stream=adc_stream,
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
        )

    raise ValueError(f"Unsupported measurement kind: {spec.kind!r}")
