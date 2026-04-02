# qubox_v2/core/measurement_config.py
"""Session-scoped measurement configuration (P1.2).

``MeasurementConfig`` is a frozen dataclass that captures the readout
discrimination and quality parameters required to build measurement
programs.  It replaces the pattern of mutating the global
``measureMacro`` singleton for configuration and instead provides an
immutable, session-owned snapshot.

Usage::

    from qubox_v2.core.measurement_config import MeasurementConfig

    # Build from CalibrationStore (single source of truth)
    cfg = MeasurementConfig.from_calibration_store(store, element="rr")

    # Build from the legacy measureMacro snapshot
    cfg = MeasurementConfig.from_measure_macro_snapshot(measureMacro._snapshot())

.. versionadded:: 2.1.0
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class MeasurementConfig:
    """Immutable measurement configuration snapshot.

    This replaces direct mutation of the ``measureMacro`` class-singleton
    with a value object that can be passed around, stored, and compared.

    Parameters are intentionally kept as simple types (dicts frozen into
    ``MappingProxyType`` for safety) so the object can be serialised
    and round-tripped through JSON.
    """

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

    # -- Element binding --
    element: str | None = None

    # -- Provenance metadata --
    source: str = "unknown"
    """Where this config was built from: 'calibration_store', 'measure_macro', 'manual'."""

    @classmethod
    def from_calibration_store(
        cls,
        store: Any,
        element: str,
    ) -> "MeasurementConfig":
        """Build a MeasurementConfig from CalibrationStore data.

        Parameters
        ----------
        store : CalibrationStore
            Calibration store to pull discrimination/quality data from.
        element : str
            Readout element name (e.g. ``"rr"``).

        Returns
        -------
        MeasurementConfig
        """
        disc = store.get_discrimination(element)
        qual = store.get_readout_quality(element)

        kw: dict[str, Any] = {"element": element, "source": "calibration_store"}

        if disc is not None:
            d = disc.model_dump()
            for f in (
                "threshold", "angle", "fidelity", "fidelity_definition",
                "sigma_g", "sigma_e",
            ):
                if d.get(f) is not None:
                    kw[f] = d[f]
            # Complex centroids
            for f in ("rot_mu_g", "rot_mu_e", "unrot_mu_g", "unrot_mu_e"):
                val = d.get(f)
                if val is not None:
                    if isinstance(val, (list, tuple)) and len(val) == 2:
                        kw[f] = complex(val[0], val[1])
                    else:
                        kw[f] = val
            if d.get("norm_params"):
                kw["norm_params"] = dict(d["norm_params"])

        if qual is not None:
            q = qual.model_dump()
            for f in ("alpha", "beta", "F", "Q", "V", "t01", "t10", "eta_g", "eta_e"):
                if q.get(f) is not None:
                    kw[f] = q[f]
            for f in ("confusion_matrix", "transition_matrix"):
                if q.get(f) is not None:
                    kw[f] = q[f]
            if q.get("affine_n") is not None:
                kw["affine_n"] = dict(q["affine_n"])

        return cls(**kw)

    @classmethod
    def from_measure_macro_snapshot(cls, snapshot: dict[str, Any]) -> "MeasurementConfig":
        """Build from a ``measureMacro._snapshot()`` dict.

        This bridges the legacy singleton pattern to the new immutable
        config pattern.

        Parameters
        ----------
        snapshot : dict
            The dict returned by ``measureMacro._snapshot()``.
        """
        disc = snapshot.get("ro_disc_params") or {}
        qual = snapshot.get("ro_quality_params") or {}

        return cls(
            threshold=disc.get("threshold"),
            angle=disc.get("angle"),
            fidelity=disc.get("fidelity"),
            fidelity_definition=disc.get("fidelity_definition"),
            rot_mu_g=disc.get("rot_mu_g"),
            rot_mu_e=disc.get("rot_mu_e"),
            unrot_mu_g=disc.get("unrot_mu_g"),
            unrot_mu_e=disc.get("unrot_mu_e"),
            sigma_g=disc.get("sigma_g"),
            sigma_e=disc.get("sigma_e"),
            norm_params=dict(disc.get("norm_params") or {}),
            alpha=qual.get("alpha"),
            beta=qual.get("beta"),
            F=qual.get("F"),
            Q=qual.get("Q"),
            V=qual.get("V"),
            t01=qual.get("t01"),
            t10=qual.get("t10"),
            eta_g=qual.get("eta_g"),
            eta_e=qual.get("eta_e"),
            confusion_matrix=qual.get("confusion_matrix"),
            transition_matrix=qual.get("transition_matrix"),
            affine_n=qual.get("affine_n"),
            element=None,
            source="measure_macro",
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-friendly dict."""
        d: dict[str, Any] = {}
        for f_name in (
            "threshold", "angle", "fidelity", "fidelity_definition",
            "sigma_g", "sigma_e", "norm_params",
            "alpha", "beta", "F", "Q", "V", "t01", "t10",
            "eta_g", "eta_e", "element", "source",
        ):
            val = getattr(self, f_name)
            if val is not None:
                d[f_name] = val
        # Complex → [real, imag]
        for f_name in ("rot_mu_g", "rot_mu_e", "unrot_mu_g", "unrot_mu_e"):
            val = getattr(self, f_name)
            if val is not None:
                if isinstance(val, complex):
                    d[f_name] = [val.real, val.imag]
                else:
                    d[f_name] = val
        for f_name in ("confusion_matrix", "transition_matrix", "affine_n"):
            val = getattr(self, f_name)
            if val is not None:
                d[f_name] = val
        return d
