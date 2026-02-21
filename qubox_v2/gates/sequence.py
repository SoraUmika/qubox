# qubox_v2/gates/sequence.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List

import numpy as np

from .model_base import GateModel
from .contexts import ModelContext, NoiseConfig
from .cache import ModelCache
from .noise import NoiseModel

@dataclass
class GateSequence:
    gates: List[GateModel]

    def superop(
        self,
        *,
        n_max: int,
        ctx: ModelContext,
        noise: NoiseConfig,
        noise_model: NoiseModel,
        cache: ModelCache,
    ) -> np.ndarray:
        S = None
        for g in self.gates:
            Sg = cache.superop(g, n_max=n_max, ctx=ctx, noise=noise, noise_model=noise_model)
            S = Sg if S is None else (Sg @ S)  # composition: after âˆ˜ before
        if S is None:
            qubit_dim = ctx.qubit_dim
            d = qubit_dim * (n_max + 1)
            return np.eye(d*d, dtype=np.complex128)
        return S

