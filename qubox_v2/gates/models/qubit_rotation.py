# qubox/gates_v2/models/qubit_rotation.py
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

from ..model_base import GateModel, GateKey
from ..hash_utils import stable_hash
from ..contexts import ModelContext
from .common import single_qubit_rotation
from ..free_evolution import dress_unitary_with_free_evolution

@dataclass(frozen=True)
class QubitRotationModel(GateModel):
    """
    Pure model for your QubitRotation.

    Basis convention: |q, n> with idx(q,n) = q*n_levels + n (qubit-major),
    consistent with np.kron(Uq, I_cav).
    """
    theta: float
    phi: float
    target: str = "qubit"
    gate_type: str = "QubitRotation"

    # Optional: store duration if you want noise.dt to default to it
    duration_override_s: float | None = None

    def key(self) -> GateKey:
        ph = stable_hash({"theta": float(self.theta), "phi": float(self.phi), "duration_s": self.duration_override_s})
        return GateKey(gate_type=self.gate_type, target=self.target, param_hash=ph)

    def duration_s(self, ctx: ModelContext) -> float:
        if self.duration_override_s is not None:
            return float(self.duration_override_s)
        return ctx.duration_for("QubitRotation", default=0.0)


    def unitary(self, *, n_max: int, ctx: ModelContext) -> np.ndarray:
        n_levels = int(n_max) + 1
        qubit_dim = ctx.qubit_dim
        
        # For cavity-only (qubit_dim=1), rotation does nothing
        if qubit_dim == 1:
            return np.eye(n_levels, dtype=np.complex128)
        
        Uq = single_qubit_rotation(self.theta, self.phi)
        U_gate = np.kron(Uq, np.eye(n_levels, dtype=np.complex128))

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
                "theta": float(self.theta),
                "phi": float(self.phi),
                "duration_override_s": self.duration_override_s,
            },
        }

    @classmethod
    def from_dict(cls, d: dict) -> "QubitRotationModel":
        P = d.get("params", {})
        return cls(
            theta=float(P["theta"]),
            phi=float(P["phi"]),
            target=d.get("target", "qubit"),
            duration_override_s=P.get("duration_override_s", None),
        )

