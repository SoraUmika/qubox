# qubox_v2/gates/models/snap.py
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

from ..model_base import GateModel, GateKey
from ..hash_utils import stable_hash, array_md5
from ..contexts import ModelContext
from ..free_evolution import dress_unitary_with_free_evolution

@dataclass(frozen=True)
class SNAPModel(GateModel):
    """
    Ideal SNAP unitary in qubit âŠ— cavity space:

        U = Î£_n ( |g,n><g,n| + e^{i Î¸_n} |e,n><e,n| )

    Basis: |q, n> with idx(q,n) = q*n_levels + n (qubit-major).
    """
    angles: np.ndarray
    target: str = "qubit"
    gate_type: str = "SNAP"

    def __post_init__(self):
        object.__setattr__(self, "angles", np.asarray(self.angles, dtype=float))

    def key(self) -> GateKey:
        ph = stable_hash({"angles_md5": array_md5(self.angles)})
        return GateKey(gate_type=self.gate_type, target=self.target, param_hash=ph)

    def duration_s(self, ctx: ModelContext) -> float:
        # Uses your new per-gate duration table
        return float(ctx.duration_for("SNAP", default=0.0))

    def unitary(self, *, n_max: int, ctx: ModelContext) -> np.ndarray:
        n_levels = int(n_max) + 1
        qubit_dim = ctx.qubit_dim
        dim = qubit_dim * n_levels

        U_gate = np.eye(dim, dtype=np.complex128)
        max_n = min(n_levels, self.angles.size)

        for n in range(max_n):
            theta_n = float(self.angles[n])
            if not np.isfinite(theta_n):
                continue
            # SNAP acts on excited state: |e,nâŸ© has index (qubit_dim-1)*n_levels + n
            # For qubit_dim=2: idx = 1*n_levels + n (excited state)
            # For qubit_dim=1: idx = 0*n_levels + n (only state, acts on all)
            idx_en = (qubit_dim - 1) * n_levels + n
            U_gate[idx_en, idx_en] = np.exp(1j * theta_n)

        t = float(self.duration_s(ctx))
        return dress_unitary_with_free_evolution(
            U_gate=U_gate, n_max=n_max, ctx=ctx, t=t,
            order="after",  # any order is fine; it's diagonal anyway
            chi_is_angular=False,
        )

    def to_dict(self) -> dict:
        return {
            "type": self.gate_type,
            "target": self.target,
            "params": {"angles": self.angles.tolist()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SNAPModel":
        P = d.get("params", {})
        return cls(
            angles=np.asarray(P["angles"], dtype=float),
            target=d.get("target", "qubit"),
        )

