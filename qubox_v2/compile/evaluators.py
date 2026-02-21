# qubox_v2/compile/evaluators.py
from __future__ import annotations

from typing import Any, Optional, Sequence
import numpy as np

from qubox_v2.gates.cache import ModelCache
from qubox_v2.gates.contexts import ModelContext, NoiseConfig


def compose_unitary(
    gates: Sequence[Any],
    *,
    n_max: int,
    ctx: ModelContext,
    cache: Optional[ModelCache] = None,
) -> np.ndarray:
    """
    Implemented unitary U = U_last @ ... @ U_first
    
    OPTIMIZATION: Uses efficient matrix chain multiplication.
    For short sequences, direct multiplication is fastest.
    """
    if not gates:
        qubit_dim = ctx.qubit_dim
        d = qubit_dim * (n_max + 1)
        return np.eye(d, dtype=np.complex128)
    
    # Pre-fetch all unitaries (enables better cache locality)
    if cache is not None:
        unitaries = [cache.unitary(g, n_max=n_max, ctx=ctx) for g in gates]
    else:
        unitaries = [g.unitary(n_max=n_max, ctx=ctx) for g in gates]
    
    # Fast path for single gate
    if len(unitaries) == 1:
        return unitaries[0]
    
    # Efficient chain multiplication (right-to-left)
    # U = U_last @ ... @ U_first
    U = unitaries[0].copy()  # Start with first gate
    for Ug in unitaries[1:]:
        U = Ug @ U  # BLAS-optimized matrix multiplication
    return U


def unitary_avg_fidelity(U_impl: np.ndarray, U_target: np.ndarray) -> float:
    """
    Average gate fidelity for two unitaries:
      Favg = (d*Fp + 1)/(d+1), Fp = |Tr(Uâ€ V)|^2 / d^2
    
    OPTIMIZATION: Uses vectorized operations and avoids redundant copies.
    """
    # Avoid redundant asarray calls if already correct type
    if U_impl.dtype != np.complex128:
        U_impl = np.asarray(U_impl, dtype=np.complex128)
    if U_target.dtype != np.complex128:
        U_target = np.asarray(U_target, dtype=np.complex128)
    
    d = U_target.shape[0]
    
    # OPTIMIZATION: Compute trace(U_targetâ€  @ U_impl) efficiently using element-wise operations
    # trace(Aâ€  @ B) = sum(conj(A) * B)
    tr = np.sum(np.conj(U_target) * U_impl)
    
    # Process fidelity
    Fp = (np.abs(tr) ** 2) / (d * d)
    return float((d * Fp + 1.0) / (d + 1.0))


def compose_superop(
    gates: Sequence[Any],
    *,
    n_max: int,
    ctx: ModelContext,
    noise: NoiseConfig,
    cache: ModelCache,
    noise_model: Any,
) -> np.ndarray:
    """
    Implemented channel in Liouville form:
      S = S_last @ ... @ S_first
    
    OPTIMIZATION: Pre-fetches superoperators for better cache locality.
    """
    if not gates:
        qubit_dim = ctx.qubit_dim
        d = qubit_dim * (n_max + 1)
        return np.eye(d * d, dtype=np.complex128)
    
    # Pre-fetch all superoperators (enables better cache locality)
    superops = [cache.superop(g, n_max=n_max, ctx=ctx, noise=noise, noise_model=noise_model) 
                for g in gates]
    
    # Fast path for single gate
    if len(superops) == 1:
        return superops[0]
    
    # Efficient chain multiplication
    S = superops[0].copy()
    for Sg in superops[1:]:
        S = Sg @ S
    return S

