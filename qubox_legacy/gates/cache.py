# qubox/gates_v2/cache.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np

from .model_base import GateModel
from .contexts import ModelContext, NoiseConfig
from .noise import NoiseModel

class ModelCache:
    """
    Cache U and S for repeated optimization calls.
    Keyed by (gate_key, n_max, ctx_key, noise_key, noise_model_type).
    """
    def __init__(self):
        self._U: Dict[Tuple[str,int,str], np.ndarray] = {}
        self._S: Dict[Tuple[str,int,str,str,str], np.ndarray] = {}

    def unitary(self, g: GateModel, *, n_max: int, ctx: ModelContext) -> np.ndarray:
        k = (g.key().key(), n_max, ctx.key())
        if k not in self._U:
            self._U[k] = g.unitary(n_max=n_max, ctx=ctx)
        return self._U[k]

    def superop(self, g: GateModel, *, n_max: int, ctx: ModelContext, noise: NoiseConfig, noise_model: NoiseModel) -> np.ndarray:
        k = (g.key().key(), n_max, ctx.key(), noise.key(), type(noise_model).__name__)
        if k not in self._S:
            self._S[k] = g.superop(n_max=n_max, ctx=ctx, noise=noise, noise_model=noise_model)
        return self._S[k]

    def clear(self) -> None:
        self._U.clear()
        self._S.clear()
