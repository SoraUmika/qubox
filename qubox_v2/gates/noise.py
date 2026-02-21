# qubox_v2/gates/noise.py
from __future__ import annotations
import math
import numpy as np
from typing import List
from .liouville import compose_kraus
from .contexts import NoiseConfig, ModelContext

def qubit_amplitude_damping_kraus(gamma: float) -> List[np.ndarray]:
    gamma = float(gamma)
    if not (0.0 <= gamma <= 1.0):
        raise ValueError("gamma must be in [0,1]")
    K0 = np.array([[1.0, 0.0],
                   [0.0, math.sqrt(1.0 - gamma)]], dtype=np.complex128)
    K1 = np.array([[0.0, math.sqrt(gamma)],
                   [0.0, 0.0]], dtype=np.complex128)
    return [K0, K1]

def diag_dephasing_kraus(dim: int, p: float) -> List[np.ndarray]:
    dim = int(dim); p = float(p)
    if dim <= 0:
        raise ValueError("dim must be positive")
    if not (0.0 <= p <= 1.0):
        raise ValueError("p must be in [0,1]")

    I = np.eye(dim, dtype=np.complex128)
    Ks = [math.sqrt(1.0 - p) * I]
    for i in range(dim):
        P = np.zeros((dim, dim), dtype=np.complex128)
        P[i, i] = 1.0
        Ks.append(math.sqrt(p) * P)
    return Ks

def embed_kraus_on_total(Ks_sub: List[np.ndarray], *, dim_left: int, dim_right: int, on: str) -> List[np.ndarray]:
    dim_left = int(dim_left); dim_right = int(dim_right)
    if dim_left <= 0 or dim_right <= 0:
        raise ValueError("dims must be positive")

    I_left = np.eye(dim_left, dtype=np.complex128)
    I_right = np.eye(dim_right, dtype=np.complex128)

    out: List[np.ndarray] = []
    for K in Ks_sub:
        K = np.asarray(K, dtype=np.complex128)
        if on == "left":
            out.append(np.kron(K, I_right))
        elif on == "right":
            out.append(np.kron(I_left, K))
        else:
            raise ValueError("on must be 'left' or 'right'")
    return out

class NoiseModel:
    """Interface: returns Kraus ops on full (qubit âŠ— cavity) space."""
    def kraus_total(self, *, dim_c: int, noise: NoiseConfig, ctx: ModelContext) -> List[np.ndarray]:
        raise NotImplementedError

class QubitT1T2Noise(NoiseModel):
    """
    Default: qubit-only T1/T2 embedded into (qubit âŠ— cavity).
    Matches your current Gate.get_kraus() behavior.
    """
    def kraus_total(self, *, dim_c: int, noise: NoiseConfig, ctx: ModelContext) -> List[np.ndarray]:
        qubit_dim = ctx.qubit_dim
        dim_total = qubit_dim * int(dim_c)

        if noise.dt is None or (noise.T1 is None and noise.T2 is None):
            return [np.eye(dim_total, dtype=np.complex128)]

        dt = float(noise.dt)
        if dt < 0:
            raise ValueError("noise.dt must be >= 0")

        # --- T1 amplitude damping ---
        gamma = 0.0
        if noise.T1 is not None:
            T1 = float(noise.T1)
            if T1 <= 0:
                raise ValueError("T1 must be > 0")
            gamma = 1.0 - math.exp(-dt / T1)

        # --- T2 -> extra pure dephasing ---
        p_phi = 0.0
        if noise.T2 is not None:
            T2 = float(noise.T2)
            if T2 <= 0:
                raise ValueError("T2 must be > 0")

            if noise.T1 is None:
                Tphi = T2
            else:
                T1 = float(noise.T1)
                invTphi = (1.0 / T2) - (1.0 / (2.0 * T1))
                if invTphi < -1e-15:
                    raise ValueError("Unphysical: T2 > 2*T1 for this simple model.")
                Tphi = float("inf") if invTphi <= 0 else (1.0 / invTphi)

            p_phi = 0.0 if math.isinf(Tphi) else (1.0 - math.exp(-dt / Tphi))

        K_noise: List[np.ndarray] = [np.eye(dim_total, dtype=np.complex128)]

        if gamma > 0:
            Ks = qubit_amplitude_damping_kraus(gamma)
            Ks = embed_kraus_on_total(Ks, dim_left=2, dim_right=dim_c, on="left")
            K_noise = compose_kraus(Ks, K_noise)

        if p_phi > 0:
            Ks = diag_dephasing_kraus(dim=2, p=p_phi)
            Ks = embed_kraus_on_total(Ks, dim_left=2, dim_right=dim_c, on="left")
            K_noise = compose_kraus(Ks, K_noise)

        return K_noise

