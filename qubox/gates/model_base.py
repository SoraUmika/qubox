# qubox_v2/gates/model_base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Type, Optional

import numpy as np

from .contexts import ModelContext, NoiseConfig
from .hash_utils import stable_hash
from .liouville import unitary_to_kraus, compose_kraus, kraus_to_superop
from .noise import NoiseModel

@dataclass(frozen=True)
class GateKey:
    gate_type: str
    target: str
    param_hash: str

    def key(self) -> str:
        return stable_hash(self.__dict__)

_MODEL_REGISTRY: Dict[str, Type["GateModel"]] = {}

class GateModel(ABC):
    """
    Pure model. No QUA. No PulseOperationManager.
    """
    gate_type: str
    target: str

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if getattr(cls, "gate_type", None):
            _MODEL_REGISTRY[cls.gate_type] = cls

    @abstractmethod
    def key(self) -> GateKey: ...

    @abstractmethod
    def to_dict(self) -> dict: ...

    @classmethod
    @abstractmethod
    def from_dict(cls, d: dict) -> "GateModel": ...

    @abstractmethod
    def duration_s(self, ctx: ModelContext) -> float:
        """
        Used when NoiseConfig.dt is None.
        Return 0.0 if you want to force caller to supply dt explicitly.
        """
        ...

    @abstractmethod
    def unitary(self, *, n_max: int, ctx: ModelContext) -> np.ndarray: ...

    def kraus(
        self,
        *,
        n_max: int,
        ctx: ModelContext,
        noise: NoiseConfig,
        noise_model: NoiseModel,
    ) -> list[np.ndarray]:
        U = self.unitary(n_max=n_max, ctx=ctx)
        U = np.asarray(U, dtype=np.complex128)

        dim_c = n_max + 1
        qubit_dim = ctx.qubit_dim
        dim_total = qubit_dim * dim_c
        if U.shape != (dim_total, dim_total):
            raise ValueError(f"{self.gate_type}.unitary returned {U.shape}, expected {(dim_total, dim_total)}")

        K_unitary = unitary_to_kraus(U)

        dt_eff = noise.dt
        if dt_eff is None:
            dt_eff = self.duration_s(ctx)
        noise_eff = NoiseConfig(dt=dt_eff, T1=noise.T1, T2=noise.T2, order=noise.order)

        K_noise = noise_model.kraus_total(dim_c=dim_c, noise=noise_eff, ctx=ctx)

        if noise.order == "noise_after":
            return compose_kraus(K_noise, K_unitary)   # Noise âˆ˜ Unitary
        elif noise.order == "noise_before":
            return compose_kraus(K_unitary, K_noise)   # Unitary âˆ˜ Noise
        else:
            raise ValueError("noise.order must be 'noise_after' or 'noise_before'")

    def superop(
        self,
        *,
        n_max: int,
        ctx: ModelContext,
        noise: NoiseConfig,
        noise_model: NoiseModel,
    ) -> np.ndarray:
        return kraus_to_superop(self.kraus(n_max=n_max, ctx=ctx, noise=noise, noise_model=noise_model))

def model_from_dict(d: dict) -> GateModel:
    gtype = d["type"]
    cls = _MODEL_REGISTRY[gtype]
    return cls.from_dict(d)

