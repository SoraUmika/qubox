from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Type, Optional

_HARDWARE_REGISTRY: Dict[str, Type["GateHardware"]] = {}

class GateHardware(ABC):
    """
    Hardware backend: QUA play/build/waveforms live here.
    Can depend on PulseOperationManager, qm.qua, attributes, etc.
    """
    gate_type: str  # must match model gate_type
    target: str

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if getattr(cls, "gate_type", None):
            _HARDWARE_REGISTRY[cls.gate_type] = cls

    @abstractmethod
    def to_dict(self) -> dict: ...

    @classmethod
    @abstractmethod
    def from_dict(cls, d: dict, *, hw_ctx) -> "GateHardware": ...

    @abstractmethod
    def build(self, *, hw_ctx) -> None: ...

    @abstractmethod
    def play(self, *, hw_ctx, align_after: bool = True) -> None: ...

def hardware_from_dict(d: dict, *, hw_ctx) -> GateHardware:
    gtype = d["type"]
    cls = _HARDWARE_REGISTRY[gtype]
    return cls.from_dict(d, hw_ctx=hw_ctx)

