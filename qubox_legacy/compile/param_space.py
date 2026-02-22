# qubox/compile/param_space.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import numpy as np


@dataclass(frozen=True)
class ParamBlock:
    """
    A contiguous parameter block inside the global vector x.

    - size: number of scalar parameters in this block
    - bounds: list[(lo, hi)] length == size
    - names: optional per-parameter names (for debugging/printing)
    - fixed: optional list[Optional[float]] length == size
             if fixed[i] is not None, that entry is forced to fixed value
    """
    name: str
    size: int
    bounds: List[Tuple[float, float]]
    names: Optional[List[str]] = None
    fixed: Optional[List[Optional[float]]] = None

    def __post_init__(self):
        if len(self.bounds) != self.size:
            raise ValueError(f"{self.name}: bounds length must equal size")
        if self.names is not None and len(self.names) != self.size:
            raise ValueError(f"{self.name}: names length must equal size")
        if self.fixed is not None and len(self.fixed) != self.size:
            raise ValueError(f"{self.name}: fixed length must equal size")


@dataclass
class ParamSpace:
    blocks: List[ParamBlock] = field(default_factory=list)

    def add(self, block: ParamBlock) -> None:
        self.blocks.append(block)

    def dim(self) -> int:
        return sum(b.size for b in self.blocks)

    def bounds(self) -> List[Tuple[float, float]]:
        out: List[Tuple[float, float]] = []
        for b in self.blocks:
            out.extend(b.bounds)
        return out

    def names(self) -> List[str]:
        out: List[str] = []
        for b in self.blocks:
            if b.names is None:
                out.extend([f"{b.name}[{i}]" for i in range(b.size)])
            else:
                out.extend([f"{b.name}:{n}" for n in b.names])
        return out

    def apply_fixed(self, x: np.ndarray) -> np.ndarray:
        """
        Return a copy of x with any fixed entries overwritten.
        """
        x = np.array(x, dtype=float, copy=True)
        offset = 0
        for b in self.blocks:
            if b.fixed is not None:
                for i, v in enumerate(b.fixed):
                    if v is not None:
                        x[offset + i] = float(v)
            offset += b.size
        return x

    def random_x0(self, rng: np.random.Generator, scale: float = 0.2) -> np.ndarray:
        """
        Random init near 0 (Gaussian) clipped to bounds, then apply fixed entries.
        """
        x = np.zeros(self.dim(), dtype=float)
        bds = self.bounds()
        for i, (lo, hi) in enumerate(bds):
            val = rng.normal(0.0, scale)
            x[i] = float(np.clip(val, lo, hi))
        return self.apply_fixed(x)
