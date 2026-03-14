# qubox_v2/gates/models/sqr.py
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

from ..model_base import GateModel, GateKey
from ..hash_utils import array_md5, stable_hash
from ..contexts import ModelContext
from .common import single_qubit_rotation
from ..free_evolution import dress_unitary_with_free_evolution

def _sqr_dispersive_dressing(
    *,
    n_max: int,
    chi: float,
    chi2: float,
    t: float,
    chi_is_angular: bool = False,
) -> np.ndarray:
    """
    Build U_disp = CR'(chi2*t) CR(chi*t) in basis/order:
      |q, n> with idx(q,n) = q*n_levels + n (qubit-major)
      sigma_z eigenvalue: +1 for q=0 (g), -1 for q=1 (e)

    CR(Theta)  = exp(-i Theta/2 * sigma_z * n)
    CR'(Theta) = exp(-i Theta/2 * sigma_z * n(n-1))
    """
    n_levels = int(n_max) + 1
    qubit_dim = 2  # Dispersive dressing assumes 2-level qubit
    dim = qubit_dim * n_levels

    chi = float(chi)
    chi2 = float(chi2)
    t = float(t)

    # if chi in Hz (cycles/s), convert to rad/s
    if not chi_is_angular:
        chi = 2.0 * np.pi * chi
        chi2 = 2.0 * np.pi * chi2

    n_arr = np.arange(n_levels, dtype=float)
    n1 = n_arr
    n2 = n_arr * (n_arr - 1.0)

    coeff = 0.5 * t * (chi * n1 + chi2 * n2)

    phase_g = np.exp(-1j * (+1.0) * coeff)  # q=0
    phase_e = np.exp(-1j * (-1.0) * coeff)  # q=1

    U = np.eye(dim, dtype=np.complex128)
    for n in range(n_levels):
        U[0 * n_levels + n, 0 * n_levels + n] = phase_g[n]
        U[1 * n_levels + n, 1 * n_levels + n] = phase_e[n]
    return U


@dataclass(frozen=True)
class SQRModel(GateModel):
    """
    Pure model for your photon-number selective qubit rotation (SQR).

    Block structure:
      For each photon number n, apply a 2x2 qubit rotation U(theta_n, phi_n)
      on the span{|g,n>, |e,n>}.

    Optional dressing:
      U_total = U_disp @ U_block  (default, 'after')
      where U_disp is built from ctx.st_chi, ctx.st_chi2, and duration.

    Inputs:
      thetas, phis, d_lambda, d_alpha, d_omega are stored for compatibility
      with your hardware synthesis, but only (thetas, phis) affect U_block.

    NOTE: This matches your existing ideal_unitary() behavior:
      - If ctx.st_chi is None OR duration is unavailable -> returns U_block only.
      - chi2 defaults to ctx.st_chi2 (0.0 ok).
    """
    thetas: np.ndarray
    phis: np.ndarray
    d_lambda: np.ndarray
    d_alpha: np.ndarray
    d_omega: np.ndarray

    target: str = "qubit"
    gate_type: str = "SQR"

    # Dressing options
    chi_is_angular: bool = False
    dress_order: str = "after"  # 'after'|'before'|'symmetric'

    # Optional per-gate override for dressing duration
    duration_override_s: float | None = None

    def __post_init__(self):
        # Ensure arrays are float numpy arrays
        object.__setattr__(self, "thetas",   np.asarray(self.thetas, dtype=float))
        object.__setattr__(self, "phis",     np.asarray(self.phis, dtype=float))
        object.__setattr__(self, "d_lambda", np.asarray(self.d_lambda, dtype=float))
        object.__setattr__(self, "d_alpha",  np.asarray(self.d_alpha, dtype=float))
        object.__setattr__(self, "d_omega",  np.asarray(self.d_omega, dtype=float))

    def key(self) -> GateKey:
        payload = np.concatenate([self.thetas, self.phis, self.d_lambda, self.d_alpha, self.d_omega])
        # include dressing controls too
        ph = stable_hash({
            "payload_md5": array_md5(payload),
            "chi_is_angular": bool(self.chi_is_angular),
            "dress_order": str(self.dress_order),
            "duration_override_s": self.duration_override_s,
        })
        return GateKey(gate_type=self.gate_type, target=self.target, param_hash=ph)

    def duration_s(self, ctx: ModelContext) -> float:
        if self.duration_override_s is not None:
            return float(self.duration_override_s)
        # use the global table first, fall back to 0.0
        return ctx.duration_for("SQR", default=0.0)

    def unitary(self, *, n_max: int, ctx: ModelContext) -> np.ndarray:
        n_levels = int(n_max) + 1
        qubit_dim = ctx.qubit_dim
        dim = qubit_dim * n_levels

        # 1) U_block exactly as you have it
        U_block = np.eye(dim, dtype=np.complex128)
        max_n = min(n_levels, int(self.thetas.size))
        for n in range(max_n):
            theta_n = float(self.thetas[n])
            if (not np.isfinite(theta_n)) or (theta_n == 0.0):
                continue
            phi_n = float(self.phis[n]) if n < self.phis.size else 0.0
            U_n = single_qubit_rotation(theta_n, phi_n)
            U_block[n,             n]             = U_n[0, 0]
            U_block[n,             n_levels + n]  = U_n[0, 1]
            U_block[n_levels + n,  n]             = U_n[1, 0]
            U_block[n_levels + n,  n_levels + n]  = U_n[1, 1]

        # 2) duration
        t = float(self.duration_override_s) if (self.duration_override_s is not None) else float(ctx.duration_for("SQR", default=0.0))
        if t == 0.0:
            return U_block

        # 3) apply unified free evolution dressing (includes chi/chi2/chi3 and kerr/kerr2)
        return dress_unitary_with_free_evolution(
            U_gate=U_block,
            n_max=n_max,
            ctx=ctx,
            t=t,
            order=self.dress_order,          # 'after'|'before'|'symmetric'
            chi_is_angular=self.chi_is_angular,
        )
    # --------------------
    # serialization
    # --------------------
    def to_dict(self) -> dict:
        return {
            "type": self.gate_type,
            "target": self.target,
            "params": {
                "thetas": self.thetas.tolist(),
                "phis": self.phis.tolist(),
                "d_lambda": self.d_lambda.tolist(),
                "d_alpha": self.d_alpha.tolist(),
                "d_omega": self.d_omega.tolist(),
                "chi_is_angular": bool(self.chi_is_angular),
                "dress_order": str(self.dress_order),
                "duration_override_s": self.duration_override_s,
            },
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SQRModel":
        P = d.get("params", {})
        return cls(
            thetas=np.asarray(P["thetas"], dtype=float),
            phis=np.asarray(P["phis"], dtype=float),
            d_lambda=np.asarray(P.get("d_lambda", np.zeros_like(P["thetas"])), dtype=float),
            d_alpha=np.asarray(P.get("d_alpha", np.zeros_like(P["thetas"])), dtype=float),
            d_omega=np.asarray(P.get("d_omega", np.zeros_like(P["thetas"])), dtype=float),
            target=d.get("target", "qubit"),
            chi_is_angular=bool(P.get("chi_is_angular", False)),
            dress_order=str(P.get("dress_order", "after")),
            duration_override_s=P.get("duration_override_s", None),
        )

