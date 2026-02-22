# qubox/gates_v2/gate.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from .model_base import GateModel, model_from_dict
from .hardware_base import GateHardware, hardware_from_dict

@dataclass
class Gate:
    """
    Combined object: carries a pure model and (optionally) a hardware backend.
    Optimizers use gate.model only.
    """
    model: GateModel
    hw: Optional[GateHardware] = None

    def to_dict(self) -> dict:
        out = {"model": self.model.to_dict()}
        if self.hw is not None:
            out["hw"] = self.hw.to_dict()
        return out

    @classmethod
    def from_dict(cls, d: dict, *, hw_ctx=None) -> "Gate":
        model = model_from_dict(d["model"])
        hw = None
        if "hw" in d and hw_ctx is not None:
            hw = hardware_from_dict(d["hw"], hw_ctx=hw_ctx)
        return cls(model=model, hw=hw)
