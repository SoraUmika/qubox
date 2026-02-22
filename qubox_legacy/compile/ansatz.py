# qubox/compile/ansatz.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

import numpy as np

from .param_space import ParamSpace
from .templates import GateTemplate


@dataclass
class Ansatz:
    templates: List[GateTemplate]

    def param_space(self) -> ParamSpace:
        ps = ParamSpace()
        for t in self.templates:
            for b in t.param_blocks():
                ps.add(b)
        return ps

    def build_gates(
        self,
        x: np.ndarray,
        *,
        ctx: Any,
        n_max: int,
        ps: Optional[ParamSpace] = None,
    ) -> List[Any]:
        """
        Decode x into GateModels in template order.
        If ps is provided, fixed entries are applied.
        """
        x = np.asarray(x, dtype=float)
        if ps is not None:
            x = ps.apply_fixed(x)

        gates: List[Any] = []
        idx = 0

        for t in self.templates:
            blocks = t.param_blocks()
            size = sum(b.size for b in blocks)
            x_slice = x[idx : idx + size]
            idx += size
            gates.extend(t.build(x_slice, ctx=ctx, n_max=n_max))

        if idx != x.size:
            raise ValueError(f"Ansatz build mismatch: consumed {idx} params but x has {x.size}")

        return gates
