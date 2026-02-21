# qubox/gates_v2/models/displacement.py
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
import numpy as np

from ..model_base import GateModel, GateKey
from ..hash_utils import stable_hash
from ..contexts import ModelContext
from .common import annihilation_operator
from ..free_evolution import dress_unitary_with_free_evolution

@dataclass(frozen=True)
class DisplacementModel(GateModel):
    """
    Pure model cavity displacement:
        U = I_q âŠ— exp(alpha aâ€  - alpha* a)

    Uses truncation n_max => n_levels = n_max+1.

    Note: This uses scipy.linalg.expm (imported lazily).
    """
    alpha: complex
    target: str = "storage"
    gate_type: str = "Displacement"

    duration_override_s: float | None = None

    def key(self) -> GateKey:
        ph = stable_hash({
            "re": float(np.real(self.alpha)),
            "im": float(np.imag(self.alpha)),
            "duration_s": self.duration_override_s,
        })
        return GateKey(gate_type=self.gate_type, target=self.target, param_hash=ph)

    def duration_s(self, ctx: ModelContext) -> float:
        if self.duration_override_s is not None:
            return float(self.duration_override_s)
        return ctx.duration_for("Displacement", default=0.0)

    @staticmethod
    @lru_cache(maxsize=256)  # OPTIMIZATION: Increased cache size from 128 to 256
    def _cached_displacement_op(n_levels: int, alpha_real: float, alpha_imag: float) -> np.ndarray:
        """
        Cache displacement operator for common alpha values.
        
        OPTIMIZATION: Uses cached computation of displacement operator.
        For small displacements, uses Taylor expansion for faster computation.
        """
        from scipy.linalg import expm
        alpha = complex(alpha_real, alpha_imag)
        alpha_mag = abs(alpha)
        
        a = annihilation_operator(n_levels)
        
        # OPTIMIZATION: For very small displacements, use Taylor expansion (faster than expm)
        if alpha_mag < 0.01:
            # Taylor: D(alpha) â‰ˆ I + (alpha aâ€  - alpha* a) + O(alpha^2)
            H = alpha * a.conj().T - np.conj(alpha) * a
            return np.eye(n_levels, dtype=np.complex128) + H
        
        # For larger displacements, use full expm
        H = alpha * a.conj().T - np.conj(alpha) * a
        return expm(H)



    def unitary(self, *, n_max: int, ctx: ModelContext) -> np.ndarray:
        n_levels = int(n_max) + 1
        
        # OPTIMIZATION: Use cached displacement operator for repeated calculations
        # Round alpha to avoid cache misses from floating point noise
        alpha_real = round(float(np.real(self.alpha)), 10)
        alpha_imag = round(float(np.imag(self.alpha)), 10)
        
        try:
            U_cav = self._cached_displacement_op(n_levels, alpha_real, alpha_imag)
        except TypeError:
            # Fallback if caching fails (e.g., unhashable types)
            from scipy.linalg import expm
            alpha = complex(self.alpha)
            a = annihilation_operator(n_levels)
            K = alpha * a.conj().T - np.conj(alpha) * a
            U_cav = expm(K)

        # Use qubit_dim from context (default 2, can be 1 for cavity-only)
        qubit_dim = ctx.qubit_dim
        U_gate = np.kron(np.eye(qubit_dim, dtype=np.complex128), U_cav)

        t = float(self.duration_s(ctx))
        return dress_unitary_with_free_evolution(
            U_gate=U_gate, n_max=n_max, ctx=ctx, t=t,
            order="symmetric", chi_is_angular=False,
        )

    # --------------------
    # serialization
    # --------------------
    def to_dict(self) -> dict:
        return {
            "type": self.gate_type,
            "target": self.target,
            "params": {
                "re": float(np.real(self.alpha)),
                "im": float(np.imag(self.alpha)),
                "duration_override_s": self.duration_override_s,
            },
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DisplacementModel":
        P = d.get("params", {})
        alpha = complex(float(P["re"]), float(P["im"]))
        return cls(
            alpha=alpha,
            target=d.get("target", "storage"),
            duration_override_s=P.get("duration_override_s", None),
        )

