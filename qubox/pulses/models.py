"""Pulse data models and resource store."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

_logger = logging.getLogger(__name__)


@dataclass
class WaveformSpec:
    """Specification for a waveform."""
    name: str
    type: str = "arbitrary"  # "arbitrary" | "constant"
    samples: Optional[list] = None
    sample: Optional[float] = None

    def to_qm_dict(self) -> dict:
        if self.type == "constant":
            return {"type": self.type, "sample": self.sample}
        return {"type": self.type, "samples": self.samples}


@dataclass
class PulseSpec:
    """Specification for a pulse."""
    name: str
    operation: str = "control"  # "control" | "measurement"
    length: int = 0
    waveforms: Dict[str, str] = field(default_factory=dict)
    digital_marker: Optional[str] = None
    integration_weights: Optional[Dict[str, str]] = None

    def to_qm_dict(self) -> dict:
        d = {"operation": self.operation, "length": self.length, "waveforms": self.waveforms}
        if self.digital_marker:
            d["digital_marker"] = self.digital_marker
        if self.integration_weights:
            d["integration_weights"] = self.integration_weights
        return d


class ResourceStore:
    """Container for waveforms, pulses, weights and element-op mappings.

    Used internally by PulseOperationManager and PulseRegistry for dual
    perm/volatile stores.  Supports collision warnings and wildcard ``*``
    element-operation broadcasting during merge.
    """

    def __init__(self) -> None:
        self.waveforms: Dict[str, Dict[str, Any]] = {}
        self.dig_waveforms: Dict[str, Dict[str, Any]] = {}
        self.pulses: Dict[str, Dict[str, Any]] = {}
        self.weights: Dict[str, Dict[str, Any]] = {}
        self.el_ops: Dict[str, Dict[str, str]] = {}

    def merge_into(
        self,
        cfg: Dict[str, Any],
        *,
        warn_collisions: bool = False,
        tag: str = "",
    ) -> None:
        """Merge this store's resources into a QM config dict.

        Parameters
        ----------
        cfg : dict
            Target QM configuration dictionary (mutated in place).
        warn_collisions : bool
            If ``True``, log a warning when overwriting existing keys.
        tag : str
            Label included in collision warnings for debugging.
        """
        for section, store in [
            ("waveforms", self.waveforms),
            ("digital_waveforms", self.dig_waveforms),
            ("pulses", self.pulses),
            ("integration_weights", self.weights),
        ]:
            target = cfg.setdefault(section, {})
            if warn_collisions:
                collisions = set(target) & set(store)
                if collisions:
                    _logger.warning(
                        "ResourceStore %s: %d key collision(s) in '%s': %s (overwriting)",
                        tag, len(collisions), section, sorted(collisions)[:5],
                    )
            target.update(store)

        elems = cfg.setdefault("elements", {})

        # Broadcast wildcard ops to all existing elements
        wildcard_ops = self.el_ops.get("*") or {}
        if isinstance(wildcard_ops, dict) and wildcard_ops:
            for el_name, el_cfg in elems.items():
                if not isinstance(el_cfg, dict) or str(el_name).startswith("__"):
                    continue
                el_cfg.setdefault("operations", {}).update(wildcard_ops)

        # Merge per-element operations
        for el, ops in self.el_ops.items():
            if el == "*":
                continue
            if not isinstance(ops, dict) or not ops:
                continue
            el_cfg = elems.get(el)
            if not isinstance(el_cfg, dict):
                _logger.warning(
                    "ResourceStore %s: skipping operation map for unknown element '%s'",
                    tag, el,
                )
                continue
            el_cfg.setdefault("operations", {}).update(ops)

    def as_dict(self) -> dict:
        return dict(
            waveforms=self.waveforms,
            digital_waveforms=self.dig_waveforms,
            pulses=self.pulses,
            integration_weights=self.weights,
            element_operations=self.el_ops,
        )

    def load_from_dict(self, d: Dict[str, Any]) -> None:
        self.waveforms.update(d.get("waveforms", {}))
        self.dig_waveforms.update(d.get("digital_waveforms", {}))
        self.pulses.update(d.get("pulses", {}))
        self.weights.update(d.get("integration_weights", {}))
        self.el_ops.update(d.get("element_operations", {}))

    def clear(self) -> None:
        self.waveforms.clear()
        self.dig_waveforms.clear()
        self.pulses.clear()
        self.weights.clear()
        self.el_ops.clear()
