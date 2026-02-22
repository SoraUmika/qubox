# qubox/compile/objectives.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional, Dict, Any
import numpy as np

from qubox.gates.contexts import ModelContext, NoiseConfig
from qubox.gates.cache import ModelCache
from qubox.gates.noise import QubitT1T2Noise
from qubox.gates.fidelity import avg_gate_fidelity_superop

from .ansatz import Ansatz
from .param_space import ParamSpace
from .evaluators import compose_unitary, compose_superop, unitary_avg_fidelity


PenaltyFn = Callable[[np.ndarray, List[object]], float]


def compute_total_gate_time(
    gates: List[object], 
    ctx: ModelContext
) -> float:
    """
    Compute total gate duration in microseconds.
    Each gate should have a duration_s(ctx) method.
    """
    total_s = 0.0
    for gate in gates:
        if hasattr(gate, 'duration_s'):
            total_s += gate.duration_s(ctx)
        else:
            # If gate doesn't have duration_s, try to infer from class name
            gate_type = gate.__class__.__name__.replace('Model', '')
            total_s += ctx.duration_for(gate_type, default=0.0)
    return total_s * 1e6  # Convert to microseconds


def density_matrix_fidelity(
    rho_result: np.ndarray,
    rho_target: np.ndarray,
    metric: str = "hilbert_schmidt"
) -> float:
    """
    Compute fidelity between two density matrices.
    
    Args:
        rho_result: Resulting density matrix
        rho_target: Target density matrix
        metric: 'hilbert_schmidt' (fast) or 'bures' (standard quantum fidelity)
    
    Returns:
        Fidelity in [0, 1]
    """
    rho_result = np.asarray(rho_result, dtype=np.complex128)
    rho_target = np.asarray(rho_target, dtype=np.complex128)
    
    if metric == "hilbert_schmidt":
        # F = Tr(ρ_result† ρ_target) / d
        # For density matrices: F = Tr(ρ_result ρ_target)
        d = rho_target.shape[0]
        F = np.real(np.trace(rho_result @ rho_target)) / d
        return float(np.clip(F, 0.0, 1.0))
    
    elif metric == "bures":
        # F = [Tr(√(√ρ_target ρ_result √ρ_target))]²
        # More expensive but standard quantum fidelity
        sqrt_rho_target = _matrix_sqrt(rho_target)
        M = sqrt_rho_target @ rho_result @ sqrt_rho_target
        sqrt_M = _matrix_sqrt(M)
        F = np.real(np.trace(sqrt_M)) ** 2
        return float(np.clip(F, 0.0, 1.0))
    
    else:
        raise ValueError(f"Unknown metric: {metric}. Use 'hilbert_schmidt' or 'bures'.")


def _matrix_sqrt(A: np.ndarray) -> np.ndarray:
    """Compute matrix square root via eigendecomposition."""
    eigvals, eigvecs = np.linalg.eigh(A)
    eigvals = np.maximum(eigvals, 0.0)  # Ensure non-negative
    return eigvecs @ np.diag(np.sqrt(eigvals)) @ eigvecs.conj().T


def apply_gates_to_density_matrix(
    rho_initial: np.ndarray,
    gates: List[object],
    ctx: ModelContext,
    noise: Optional[NoiseConfig] = None,
    n_max: Optional[int] = None,
    cache: Optional[ModelCache] = None,
    noise_model: Optional[QubitT1T2Noise] = None
) -> np.ndarray:
    """
    Apply gate sequence to density matrix.
    
    Each gate is applied as a quantum channel: ρ → Σ_i K_i ρ K_i†
    where K_i are Kraus operators from gate.kraus() or gate.get_kraus().
    
    OPTIMIZATION: Uses in-place operations and pre-allocated arrays to reduce memory allocation.
    
    Args:
        rho_initial: Initial density matrix
        gates: List of gate objects
        ctx: Model context
        noise: Noise configuration
        n_max: Maximum cavity Fock level (inferred from rho_initial if not provided)
        cache: Optional cache for Kraus operators
        noise_model: Noise model for T1/T2
    
    Returns:
        Final density matrix after all gates
    """
    rho = np.asarray(rho_initial, dtype=np.complex128).copy()  # Work on a copy
    
    # Infer n_max from density matrix dimension if not provided
    if n_max is None:
        d = rho_initial.shape[0]
        qubit_dim = ctx.qubit_dim
        if d % qubit_dim != 0:
            raise ValueError(f"Density matrix dimension {d} must be divisible by qubit_dim={qubit_dim}")
        n_max = d // qubit_dim - 1
    
    # Pre-allocate temp arrays for Kraus operations (reused across gates)
    d = rho.shape[0]
    temp = np.empty((d, d), dtype=np.complex128)
    rho_new = np.empty((d, d), dtype=np.complex128)
    
    for gate in gates:
        # Get Kraus operators for this gate
        if hasattr(gate, 'kraus'):
            # New GateModel interface: kraus(n_max=..., ctx=..., noise=..., noise_model=...)
            noise_cfg = noise if noise else NoiseConfig(dt=0.0, T1=None, T2=None, order="noise_after")
            noise_mdl = noise_model if noise_model else QubitT1T2Noise()
            K_list = gate.kraus(
                n_max=n_max,
                ctx=ctx,
                noise=noise_cfg,
                noise_model=noise_mdl,
            )
        elif hasattr(gate, 'get_kraus'):
            # Legacy interface: get_kraus(n_max=..., dt=..., T1=..., T2=...)
            K_list = gate.get_kraus(
                n_max=n_max,
                dt=noise.dt if noise else 0.0,
                T1=noise.T1 if noise else None,
                T2=noise.T2 if noise else None,
            )
        elif hasattr(gate, 'unitary'):
            # Fallback: use unitary method
            U = gate.unitary(n_max=n_max, ctx=ctx)
            K_list = [U]
        elif hasattr(gate, 'matrix'):
            # Older fallback: matrix(ctx)
            U = gate.matrix(ctx)
            K_list = [U]
        else:
            raise AttributeError(f"Gate {gate} has no kraus(), get_kraus(), unitary(), or matrix() method")
        
        # Ensure K_list is iterable
        if not isinstance(K_list, (list, tuple)):
            K_list = [K_list]
        
        # Apply channel: ρ → Σ_i K_i ρ K_i†
        # OPTIMIZATION: Pre-allocate and reuse arrays for common case (single Kraus operator)
        if len(K_list) == 1:
            # Fast path for unitary gates (no noise)
            K = np.asarray(K_list[0], dtype=np.complex128)
            # Use @ operator which is optimized for matrix multiplication
            # OPTIMIZATION: Use np.matmul with out parameter for in-place operations
            np.matmul(K, rho, out=temp)  # temp = K @ rho
            np.matmul(temp, K.conj().T, out=rho)  # rho = temp @ K†
        else:
            # General case: multiple Kraus operators
            rho_new.fill(0.0)  # Reset accumulator
            for K in K_list:
                K = np.asarray(K, dtype=np.complex128)
                # Compute K ρ K† efficiently
                np.matmul(K, rho, out=temp)
                # Accumulate into rho_new
                rho_new += temp @ K.conj().T
            rho, rho_new = rho_new, rho  # Swap references
    
    return rho


@dataclass
class ObjectiveConfig:
    """
    mode:
      - 'unitary': compare U_impl to U_target (fast)
      - 'noisy'  : compare S_impl to target unitary channel (slower)
      - 'density_matrix': compare ρ_impl to ρ_target (mixed states)

    robust_contexts:
      - if provided, loss averages fidelity over these ModelContext's

    penalty_fn:
      - optional extra penalty computed from (x, gates)

    time_weight:
      - coefficient for gate duration penalty (0.0 = ignore time, higher = prefer faster gates)
      - penalty = time_weight * (total_duration_us / reference_duration_us)
      - reference_duration_us defaults to 10.0 for normalization

    depth_weight:
      - coefficient for gate depth penalty (0.0 = ignore depth, higher = prefer fewer gates)
      - penalty = depth_weight * (num_gates / reference_depth)
      - reference_depth defaults to 10.0 for normalization
      - Fewer gates → less error accumulation → higher fidelity

    Notes:
      The returned loss function exposes a .last_info dict containing
      the most recent evaluation information (loss, fidelity, etc.).
    """
    mode: str = "unitary"
    l2_weight: float = 0.0
    time_weight: float = 0.0
    time_reference_us: float = 10.0
    depth_weight: float = 0.0
    depth_reference: float = 10.0
    density_metric: str = "hilbert_schmidt"  # or "bures" for density_matrix mode
    robust_contexts: Optional[List[ModelContext]] = None
    penalty_fn: Optional[PenaltyFn] = None


def make_objective(
    *,
    U_target: np.ndarray,
    ansatz: Ansatz,
    ps: ParamSpace,
    ctx: ModelContext,
    noise: NoiseConfig,
    n_max: int,
    obj_cfg: ObjectiveConfig,
    cache: Optional[ModelCache] = None,
    noise_model: Optional[object] = None,
) -> Callable[[np.ndarray], float]:
    """
    Returns loss(x) to minimize.
    Also sets loss.last_info dict after each call.

    last_info keys:
      - loss
      - fidelity
      - fidelities_per_context
      - reg
      - penalty
    """
    target_array = np.asarray(U_target, dtype=np.complex128)
    qubit_dim = ctx.qubit_dim
    d = qubit_dim * (n_max + 1)
    
    mode = str(obj_cfg.mode).lower()
    if mode not in ("unitary", "noisy", "density_matrix"):
        raise ValueError("ObjectiveConfig.mode must be 'unitary', 'noisy', or 'density_matrix'")
    
    # Determine if target is density matrix or unitary
    is_density_mode = (mode == "density_matrix")
    
    if is_density_mode:
        rho_target = target_array
        if rho_target.shape != (d, d):
            raise ValueError(f"rho_target must be {(d, d)}, got {rho_target.shape}")
    else:
        U_target_matrix = target_array
        if U_target_matrix.shape != (d, d):
            raise ValueError(f"U_target must be {(d, d)}, got {U_target_matrix.shape}")

    # Always create cache for speedup (both unitary and noisy modes)
    if cache is None:
        cache = ModelCache()
    
    if mode == "noisy":
        if noise_model is None:
            noise_model = QubitT1T2Noise()

    ctx_list = obj_cfg.robust_contexts if obj_cfg.robust_contexts else [ctx]

    last_info: Dict[str, Any] = {
        "loss": None,
        "fidelity": None,
        "fidelities_per_context": None,
        "reg": None,
        "penalty": None,
        "time_penalty": None,
        "total_time_us": None,
        "depth_penalty": None,
        "num_gates": None,
    }

    def loss(x: np.ndarray) -> float:
        x = np.asarray(x, dtype=float)
        x = ps.apply_fixed(x)

        fidelities: List[float] = []
        last_gates: Optional[List[object]] = None

        for c in ctx_list:
            gates = ansatz.build_gates(x, ctx=c, n_max=n_max, ps=None)
            last_gates = gates

            if mode == "unitary":
                U_impl = compose_unitary(gates, n_max=n_max, ctx=c, cache=cache)
                f = unitary_avg_fidelity(U_impl, target_array)
            elif mode == "density_matrix":
                # Start from |0⟩⟨0|
                rho_initial = np.zeros((d, d), dtype=np.complex128)
                rho_initial[0, 0] = 1.0
                rho_result = apply_gates_to_density_matrix(rho_initial, gates, c, noise, n_max, cache, noise_model)
                f = density_matrix_fidelity(rho_result, target_array, metric=obj_cfg.density_metric)
            else:  # noisy
                assert cache is not None and noise_model is not None
                S_impl = compose_superop(
                    gates, n_max=n_max, ctx=c, noise=noise, cache=cache, noise_model=noise_model
                )
                f = avg_gate_fidelity_superop(S_impl, target_array)

            fidelities.append(float(f))

        F = float(np.mean(fidelities))
        reg = float(obj_cfg.l2_weight) * float(np.dot(x, x))

        penalty = 0.0
        if obj_cfg.penalty_fn is not None:
            penalty = float(obj_cfg.penalty_fn(x, last_gates or []))

        # Time penalty: encourage shorter gate sequences
        time_penalty = 0.0
        total_time_us = 0.0
        if obj_cfg.time_weight > 0.0 and last_gates:
            total_time_us = compute_total_gate_time(last_gates, ctx_list[0])
            # Normalize by reference time and apply weight
            time_penalty = obj_cfg.time_weight * (total_time_us / obj_cfg.time_reference_us)

        # Depth penalty: encourage fewer gates (higher fidelity, less error accumulation)
        depth_penalty = 0.0
        num_gates = len(last_gates) if last_gates else 0
        if obj_cfg.depth_weight > 0.0 and num_gates > 0:
            # Normalize by reference depth and apply weight
            depth_penalty = obj_cfg.depth_weight * (num_gates / obj_cfg.depth_reference)

        L = (1.0 - F) + reg + penalty + time_penalty + depth_penalty

        # record for progress printing
        last_info["loss"] = float(L)
        last_info["fidelity"] = float(F)
        last_info["fidelities_per_context"] = fidelities
        last_info["reg"] = float(reg)
        last_info["penalty"] = float(penalty)
        last_info["time_penalty"] = float(time_penalty)
        last_info["total_time_us"] = float(total_time_us)
        last_info["depth_penalty"] = float(depth_penalty)
        last_info["num_gates"] = int(num_gates)

        return float(L)

    # expose last_info to the outside
    loss.last_info = last_info  # type: ignore[attr-defined]
    return loss
