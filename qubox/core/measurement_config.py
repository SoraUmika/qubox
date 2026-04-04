"""Explicit readout configuration persistence.

``MeasurementConfig`` captures the session-owned readout state needed to
reload calibrated readout behavior without relying on hidden global state.
It persists the active element / operation, demod weight labels, readout
discrimination and quality metrics, and optional post-selection metadata.

Legacy ``measureConfig.json`` files written by the old singleton
implementation are still readable so existing cooldown directories keep
working. New writes use the explicit v6 format defined here.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .persistence import sanitize_mapping_for_json


def _coerce_complex(value: Any) -> complex | None:
    if value is None:
        return None
    if isinstance(value, complex):
        return value
    if isinstance(value, Mapping):
        real = value.get("re")
        imag = value.get("im")
        if real is not None and imag is not None:
            return complex(float(real), float(imag))
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return complex(float(value[0]), float(value[1]))
    return value


def _jsonify(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if isinstance(value, Mapping):
        return {str(key): _jsonify(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonify(item) for item in value]
    return value


def _normalize_weight_sets(value: Any) -> tuple[tuple[str, ...], ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return ((str(value),),)
    normalized: list[tuple[str, ...]] = []
    for spec in value:
        if isinstance(spec, str):
            normalized.append((str(spec),))
            continue
        if isinstance(spec, (list, tuple)):
            values = tuple(str(item) for item in spec if item is not None)
            if values:
                normalized.append(values)
    return tuple(normalized)


def _dict_or_none(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return {str(key): value[key] for key in value}
    return None


@dataclass(frozen=True)
class MeasurementConfig:
    """Immutable persisted readout configuration."""

    # -- Readout routing / pulse binding --
    element: str | None = None
    operation: str | None = None
    drive_frequency: float | None = None
    gain: float | None = None
    demod_method: str = "dual_demod.full"
    weight_sets: tuple[tuple[str, ...], ...] = ()
    weight_length: int | None = None

    # -- Discrimination parameters --
    threshold: float | None = None
    angle: float | None = None
    fidelity: float | None = None
    fidelity_definition: str | None = None
    rot_mu_g: complex | None = None
    rot_mu_e: complex | None = None
    unrot_mu_g: complex | None = None
    unrot_mu_e: complex | None = None
    sigma_g: float | None = None
    sigma_e: float | None = None
    norm_params: dict[str, Any] = field(default_factory=dict)

    # -- Quality parameters --
    alpha: float | None = None
    beta: float | None = None
    F: float | None = None
    Q: float | None = None
    V: float | None = None
    t01: float | None = None
    t10: float | None = None
    eta_g: float | None = None
    eta_e: float | None = None
    confusion_matrix: Any = None
    transition_matrix: Any = None
    affine_n: dict[str, Any] | None = None

    # -- Runtime metadata --
    post_select_config: dict[str, Any] | None = None
    readout_state_signature: dict[str, Any] | None = None

    # -- Provenance --
    source: str = "unknown"

    @classmethod
    def from_calibration_store(
        cls,
        store: Any,
        element: str,
    ) -> "MeasurementConfig":
        """Build from persisted CalibrationStore data only."""
        disc = store.get_discrimination(element)
        qual = store.get_readout_quality(element)
        payload: dict[str, Any] = {
            "element": element,
            "source": "calibration_store",
        }

        if disc is not None:
            disc_payload = getattr(disc, "model_dump", None)
            disc_data = disc_payload() if callable(disc_payload) else dict(getattr(disc, "__dict__", {}) or {})
            for key in (
                "threshold",
                "angle",
                "fidelity",
                "fidelity_definition",
                "sigma_g",
                "sigma_e",
            ):
                value = disc_data.get(key)
                if value is not None:
                    payload[key] = value
            for key in ("rot_mu_g", "rot_mu_e", "unrot_mu_g", "unrot_mu_e"):
                value = disc_data.get(key)
                if value is None:
                    legacy_key = {
                        "rot_mu_g": "mu_g",
                        "rot_mu_e": "mu_e",
                    }.get(key)
                    if legacy_key is not None:
                        value = disc_data.get(legacy_key)
                coerced = _coerce_complex(value)
                if coerced is not None:
                    payload[key] = coerced
            norm_params = disc_data.get("norm_params")
            if isinstance(norm_params, Mapping):
                payload["norm_params"] = dict(norm_params)

        if qual is not None:
            qual_payload = getattr(qual, "model_dump", None)
            qual_data = qual_payload() if callable(qual_payload) else dict(getattr(qual, "__dict__", {}) or {})
            for key in ("alpha", "beta", "F", "Q", "V", "t01", "t10", "eta_g", "eta_e"):
                value = qual_data.get(key)
                if value is not None:
                    payload[key] = value
            for key in ("confusion_matrix", "transition_matrix", "affine_n"):
                value = qual_data.get(key)
                if value is not None:
                    payload[key] = value

        return cls(**payload)

    @classmethod
    def from_readout_handle(
        cls,
        readout: Any,
        *,
        post_select_config: Any = None,
        readout_state_signature: Mapping[str, Any] | None = None,
        source: str = "readout_handle",
    ) -> "MeasurementConfig":
        """Capture a persisted config from an explicit ReadoutHandle."""
        cal = getattr(readout, "cal", None)
        binding = getattr(readout, "binding", None)
        if cal is None or binding is None:
            raise TypeError("from_readout_handle expects a ReadoutHandle-like object.")

        discrimination = dict(getattr(binding, "discrimination", {}) or {})
        quality = dict(getattr(binding, "quality", {}) or {})
        if post_select_config is not None and hasattr(post_select_config, "to_dict"):
            post_select_payload = post_select_config.to_dict()
        else:
            post_select_payload = _dict_or_none(post_select_config)

        return cls(
            element=getattr(readout, "element", None),
            operation=getattr(readout, "operation", None),
            drive_frequency=getattr(cal, "drive_frequency", None),
            gain=getattr(readout, "gain", None),
            demod_method=getattr(cal, "demod_method", "dual_demod.full"),
            weight_sets=_normalize_weight_sets(
                getattr(readout, "demod_weight_sets", None) or getattr(binding, "demod_weight_sets", None)
            ),
            weight_length=getattr(cal, "weight_length", None),
            threshold=getattr(cal, "threshold", None) if getattr(cal, "threshold", None) is not None else discrimination.get("threshold"),
            angle=getattr(cal, "rotation_angle", None) if getattr(cal, "rotation_angle", None) is not None else discrimination.get("angle"),
            fidelity=getattr(cal, "fidelity", None) if getattr(cal, "fidelity", None) is not None else discrimination.get("fidelity"),
            fidelity_definition=(
                getattr(cal, "fidelity_definition", None)
                if getattr(cal, "fidelity_definition", None) is not None
                else discrimination.get("fidelity_definition")
            ),
            rot_mu_g=_coerce_complex(discrimination.get("rot_mu_g")),
            rot_mu_e=_coerce_complex(discrimination.get("rot_mu_e")),
            unrot_mu_g=_coerce_complex(discrimination.get("unrot_mu_g")),
            unrot_mu_e=_coerce_complex(discrimination.get("unrot_mu_e")),
            sigma_g=getattr(cal, "sigma_g", None) if getattr(cal, "sigma_g", None) is not None else discrimination.get("sigma_g"),
            sigma_e=getattr(cal, "sigma_e", None) if getattr(cal, "sigma_e", None) is not None else discrimination.get("sigma_e"),
            norm_params=dict(discrimination.get("norm_params") or {}),
            alpha=quality.get("alpha"),
            beta=quality.get("beta"),
            F=quality.get("F"),
            Q=quality.get("Q"),
            V=quality.get("V"),
            t01=quality.get("t01"),
            t10=quality.get("t10"),
            eta_g=quality.get("eta_g"),
            eta_e=quality.get("eta_e"),
            confusion_matrix=(
                getattr(cal, "confusion_matrix", None)
                if getattr(cal, "confusion_matrix", None) is not None
                else quality.get("confusion_matrix")
            ),
            transition_matrix=quality.get("transition_matrix"),
            affine_n=_dict_or_none(quality.get("affine_n")),
            post_select_config=post_select_payload,
            readout_state_signature=dict(readout_state_signature) if isinstance(readout_state_signature, Mapping) else None,
            source=source,
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MeasurementConfig":
        """Decode either explicit v6 config or legacy v5/v4 snapshot format."""
        version = int(payload.get("_version", 1) or 1)

        # Legacy singleton payload: {"_version": 5, "current": {...}}
        if "current" in payload and isinstance(payload.get("current"), Mapping):
            return cls._from_legacy_snapshot_json(payload["current"])

        data = dict(payload)
        if version >= 6:
            kwargs = {
                "element": data.get("element"),
                "operation": data.get("operation"),
                "drive_frequency": data.get("drive_frequency"),
                "gain": data.get("gain"),
                "demod_method": data.get("demod_method", "dual_demod.full"),
                "weight_sets": _normalize_weight_sets(data.get("weight_sets")),
                "weight_length": data.get("weight_length"),
                "threshold": data.get("threshold"),
                "angle": data.get("angle"),
                "fidelity": data.get("fidelity"),
                "fidelity_definition": data.get("fidelity_definition"),
                "rot_mu_g": _coerce_complex(data.get("rot_mu_g")),
                "rot_mu_e": _coerce_complex(data.get("rot_mu_e")),
                "unrot_mu_g": _coerce_complex(data.get("unrot_mu_g")),
                "unrot_mu_e": _coerce_complex(data.get("unrot_mu_e")),
                "sigma_g": data.get("sigma_g"),
                "sigma_e": data.get("sigma_e"),
                "norm_params": dict(data.get("norm_params") or {}),
                "alpha": data.get("alpha"),
                "beta": data.get("beta"),
                "F": data.get("F"),
                "Q": data.get("Q"),
                "V": data.get("V"),
                "t01": data.get("t01"),
                "t10": data.get("t10"),
                "eta_g": data.get("eta_g"),
                "eta_e": data.get("eta_e"),
                "confusion_matrix": data.get("confusion_matrix"),
                "transition_matrix": data.get("transition_matrix"),
                "affine_n": dict(data.get("affine_n")) if isinstance(data.get("affine_n"), Mapping) else data.get("affine_n"),
                "post_select_config": _dict_or_none(data.get("post_select_config")),
                "readout_state_signature": _dict_or_none(data.get("readout_state_signature")),
                "source": str(data.get("source", "unknown")),
            }
            return cls(**kwargs)

        return cls._from_legacy_snapshot_json(data)

    @classmethod
    def load_json(cls, path: str | Path) -> "MeasurementConfig":
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, Mapping):
            raise TypeError(f"MeasurementConfig JSON must be a mapping, got {type(payload).__name__}.")
        return cls.from_dict(payload)

    @classmethod
    def _from_legacy_snapshot_json(cls, snapshot_json: Mapping[str, Any]) -> "MeasurementConfig":
        pulse_op = snapshot_json.get("pulse_op")
        ro_disc = dict(snapshot_json.get("ro_disc_params") or {})
        ro_quality = dict(snapshot_json.get("ro_quality_params") or snapshot_json.get("ro_quality_metrics") or {})

        element = None
        operation = snapshot_json.get("active_op")
        if isinstance(pulse_op, Mapping):
            element = pulse_op.get("element")
            operation = operation or pulse_op.get("op") or pulse_op.get("pulse")

        return cls(
            element=element,
            operation=operation,
            drive_frequency=snapshot_json.get("drive_frequency"),
            gain=snapshot_json.get("gain"),
            demod_method=str(snapshot_json.get("demod_fn", "dual_demod.full")),
            weight_sets=_normalize_weight_sets(snapshot_json.get("weights")),
            weight_length=snapshot_json.get("demod_weight_len"),
            threshold=ro_disc.get("threshold"),
            angle=ro_disc.get("angle"),
            fidelity=ro_disc.get("fidelity"),
            fidelity_definition=ro_disc.get("fidelity_definition"),
            rot_mu_g=_coerce_complex(ro_disc.get("rot_mu_g")),
            rot_mu_e=_coerce_complex(ro_disc.get("rot_mu_e")),
            unrot_mu_g=_coerce_complex(ro_disc.get("unrot_mu_g")),
            unrot_mu_e=_coerce_complex(ro_disc.get("unrot_mu_e")),
            sigma_g=ro_disc.get("sigma_g"),
            sigma_e=ro_disc.get("sigma_e"),
            norm_params=dict(ro_disc.get("norm_params") or {}),
            alpha=ro_quality.get("alpha"),
            beta=ro_quality.get("beta"),
            F=ro_quality.get("F"),
            Q=ro_quality.get("Q"),
            V=ro_quality.get("V"),
            t01=ro_quality.get("t01"),
            t10=ro_quality.get("t10"),
            eta_g=ro_quality.get("eta_g"),
            eta_e=ro_quality.get("eta_e"),
            confusion_matrix=ro_quality.get("confusion_matrix"),
            transition_matrix=ro_quality.get("transition_matrix"),
            affine_n=_dict_or_none(ro_quality.get("affine_n")),
            post_select_config=_dict_or_none(snapshot_json.get("post_select_config")),
            readout_state_signature=_dict_or_none(ro_disc.get("qbx_readout_state")),
            source="legacy_measure_config",
        )

    def discrimination_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for key in (
            "threshold",
            "angle",
            "fidelity",
            "fidelity_definition",
            "rot_mu_g",
            "rot_mu_e",
            "unrot_mu_g",
            "unrot_mu_e",
            "sigma_g",
            "sigma_e",
            "norm_params",
        ):
            value = getattr(self, key)
            if value is not None:
                payload[key] = value
        return payload

    def quality_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for key in (
            "alpha",
            "beta",
            "F",
            "Q",
            "V",
            "t01",
            "t10",
            "eta_g",
            "eta_e",
            "confusion_matrix",
            "transition_matrix",
            "affine_n",
        ):
            value = getattr(self, key)
            if value is not None:
                payload[key] = value
        return payload

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "_version": 6,
            "source": self.source,
        }
        for key in (
            "element",
            "operation",
            "drive_frequency",
            "gain",
            "demod_method",
            "weight_length",
            "threshold",
            "angle",
            "fidelity",
            "fidelity_definition",
            "sigma_g",
            "sigma_e",
            "alpha",
            "beta",
            "F",
            "Q",
            "V",
            "t01",
            "t10",
            "eta_g",
            "eta_e",
        ):
            value = getattr(self, key)
            if value is not None:
                payload[key] = value

        if self.weight_sets:
            payload["weight_sets"] = _jsonify(self.weight_sets)
        if self.norm_params:
            payload["norm_params"] = _jsonify(self.norm_params)
        if self.rot_mu_g is not None:
            payload["rot_mu_g"] = _jsonify(self.rot_mu_g)
        if self.rot_mu_e is not None:
            payload["rot_mu_e"] = _jsonify(self.rot_mu_e)
        if self.unrot_mu_g is not None:
            payload["unrot_mu_g"] = _jsonify(self.unrot_mu_g)
        if self.unrot_mu_e is not None:
            payload["unrot_mu_e"] = _jsonify(self.unrot_mu_e)
        if self.confusion_matrix is not None:
            payload["confusion_matrix"] = _jsonify(self.confusion_matrix)
        if self.transition_matrix is not None:
            payload["transition_matrix"] = _jsonify(self.transition_matrix)
        if self.affine_n is not None:
            payload["affine_n"] = _jsonify(self.affine_n)
        if self.post_select_config is not None:
            payload["post_select_config"] = _jsonify(self.post_select_config)
        if self.readout_state_signature is not None:
            payload["readout_state_signature"] = _jsonify(self.readout_state_signature)
        return payload

    def save_json(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload, dropped = sanitize_mapping_for_json(self.to_dict())
        if dropped:
            payload["_persistence"] = {
                "raw_data_policy": "drop_shot_level_arrays",
                "dropped_fields": dropped,
            }
        with open(destination, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        return destination
