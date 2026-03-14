# qubox_v2/pulses/models.py
"""Pulse data models and resource store."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np


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

    Used internally by PulseOperationManager for dual perm/volatile stores.
    """

    def __init__(self) -> None:
        self.waveforms: Dict[str, Dict[str, Any]] = {}
        self.dig_waveforms: Dict[str, Dict[str, Any]] = {}
        self.pulses: Dict[str, Dict[str, Any]] = {}
        self.weights: Dict[str, Dict[str, Any]] = {}
        self.el_ops: Dict[str, Dict[str, str]] = {}

    def merge_into(self, cfg: Dict[str, Any]) -> None:
        cfg.setdefault("waveforms", {}).update(self.waveforms)
        cfg.setdefault("digital_waveforms", {}).update(self.dig_waveforms)
        cfg.setdefault("pulses", {}).update(self.pulses)
        cfg.setdefault("integration_weights", {}).update(self.weights)
        elems = cfg.setdefault("elements", {})
        for el, ops in self.el_ops.items():
            elems.setdefault(el, {}).setdefault("operations", {}).update(ops)

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
