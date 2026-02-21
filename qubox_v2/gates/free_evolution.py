# qubox/gates_v2/models/free_evolution.py
from __future__ import annotations
import numpy as np
from .contexts import ModelContext


def _to_rad_per_s(x_hz: float, *, is_angular: bool) -> float:
    x_hz = float(x_hz)
    return x_hz if is_angular else (2.0 * np.pi * x_hz)


def free_evolution_unitary(
    *,
    n_max: int,
    ctx: ModelContext,
    t: float,
    chi_is_angular: bool = False,
) -> np.ndarray:
    """
    U_free(t) for qubit âŠ— cavity, in |q,n> qubit-major ordering:
      idx(q,n) = q*n_levels + n

    Conventions (match your SQR dressing):
      - sigma_z eigenvalue: +1 for q=0 (g), -1 for q=1 (e)
      - dispersive part implemented as exp[-i * (sigma_z) * (1/2) * t * f(n)]
        where f(n) = chi*n + chi2*n(n-1) + chi3*n(n-1)(n-2)
      - Kerr part implemented as exp[-i * t * ( K/2 * n(n-1) + K2/6 * n(n-1)(n-2) )] on BOTH qubit blocks

    ctx.* are assumed Hz unless chi_is_angular=True.
    """
    t = float(t)
    n_levels = int(n_max) + 1
    qubit_dim = ctx.qubit_dim
    dim = qubit_dim * n_levels
    
    if t == 0.0:
        return np.eye(dim, dtype=np.complex128)

    # Read params; treat None as 0
    chi  = 0.0 if ctx.st_chi  is None else float(ctx.st_chi)
    chi2 = 0.0 if ctx.st_chi2 is None else float(ctx.st_chi2)
    chi3 = 0.0 if ctx.st_chi3 is None else float(ctx.st_chi3)

    K  = 0.0 if ctx.st_kerr  is None else float(ctx.st_kerr)
    K2 = 0.0 if ctx.st_kerr2 is None else float(ctx.st_kerr2)

    # Fast exit if nothing to do
    if (chi == 0.0 and chi2 == 0.0 and chi3 == 0.0 and K == 0.0 and K2 == 0.0):
        return np.eye(dim, dtype=np.complex128)

    # Convert to angular frequency if needed
    chi  = _to_rad_per_s(chi,  is_angular=chi_is_angular)
    chi2 = _to_rad_per_s(chi2, is_angular=chi_is_angular)
    chi3 = _to_rad_per_s(chi3, is_angular=chi_is_angular)

    K  = _to_rad_per_s(K,  is_angular=chi_is_angular)
    K2 = _to_rad_per_s(K2, is_angular=chi_is_angular)

    n = np.arange(n_levels, dtype=float)
    n2 = n * (n - 1.0)
    n3 = n * (n - 1.0) * (n - 2.0)

    # Dispersive: exp[-i * (sigma_z) * 1/2 * t * (chi*n + chi2*n2 + chi3*n3)]
    coeff_disp = 0.5 * t * (chi * n + chi2 * n2 + chi3 * n3)
    phase_g_disp = np.exp(-1j * (+1.0) * coeff_disp)
    phase_e_disp = np.exp(-1j * (-1.0) * coeff_disp)

    # Kerr: exp[-i * t * (K/2*n2 + K2/6*n3)] on cavity regardless of qubit
    coeff_kerr = t * (0.5 * K * n2 + (1.0 / 6.0) * K2 * n3)
    phase_kerr = np.exp(-1j * coeff_kerr)

    phase_g = phase_kerr * phase_g_disp
    phase_e = phase_kerr * phase_e_disp

    U = np.eye(dim, dtype=np.complex128)
    for nn in range(n_levels):
        U[0 * n_levels + nn, 0 * n_levels + nn] = phase_g[nn]
        # Only apply excited state phase if qubit exists
        if qubit_dim >= 2:
            U[1 * n_levels + nn, 1 * n_levels + nn] = phase_e[nn]
    return U


def dress_unitary_with_free_evolution(
    *,
    U_gate: np.ndarray,
    n_max: int,
    ctx: ModelContext,
    t: float,
    order: str = "symmetric",
    chi_is_angular: bool = False,
) -> np.ndarray:
    """
    Wrap U_gate with U_free(t) using chosen order.
    """
    order = str(order).lower()
    t = float(t)
    if t == 0.0:
        return U_gate

    U_free = free_evolution_unitary(n_max=n_max, ctx=ctx, t=t, chi_is_angular=chi_is_angular)

    # If U_free is identity (nothing set), skip
    if np.allclose(U_free, np.eye(U_free.shape[0], dtype=U_free.dtype)):
        return U_gate

    if order == "after":
        return U_free @ U_gate
    if order == "before":
        return U_gate @ U_free
    if order == "symmetric":
        U_half = free_evolution_unitary(n_max=n_max, ctx=ctx, t=t/2.0, chi_is_angular=chi_is_angular)
        return U_half @ U_gate @ U_half

    raise ValueError("order must be 'after', 'before', or 'symmetric'")

