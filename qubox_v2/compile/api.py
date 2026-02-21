# qubox/compile/api.py
from __future__ import annotations

from typing import Any, Dict, Optional
import numpy as np

from qubox_v2.gates.contexts import ModelContext, NoiseConfig
from qubox_v2.gates.cache import ModelCache
from qubox_v2.gates.noise import QubitT1T2Noise
from qubox_v2.gates.fidelity import avg_gate_fidelity_superop

from .ansatz import Ansatz
from .param_space import ParamSpace
from .objectives import ObjectiveConfig, make_objective, compute_total_gate_time
from .optimizers import OptimizerConfig, run_optimization
from .evaluators import compose_unitary, unitary_avg_fidelity, compose_superop


def compile_with_ansatz(
    *,
    U_target: np.ndarray,
    ansatz: Ansatz,
    ctx: ModelContext,
    noise: NoiseConfig,
    n_max: int,
    obj_cfg: ObjectiveConfig,
    opt_cfg: OptimizerConfig,
    x0: Optional[np.ndarray] = None,
    cache: Optional[ModelCache] = None,
    noise_model: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    One-stop compilation run:
      - builds ParamSpace from Ansatz
      - creates loss function
      - runs optimizer
      - returns best gates + best fidelity (unitary/noisy based on obj_cfg.mode)
    """
    ps = ansatz.param_space()

    if obj_cfg.mode.lower() == "noisy":
        if cache is None:
            cache = ModelCache()
        if noise_model is None:
            noise_model = QubitT1T2Noise()

    loss_fn = make_objective(
        U_target=U_target,
        ansatz=ansatz,
        ps=ps,
        ctx=ctx,
        noise=noise,
        n_max=n_max,
        obj_cfg=obj_cfg,
        cache=cache,
        noise_model=noise_model,
    )

    opt_out = run_optimization(loss_fn=loss_fn, ps=ps, opt_cfg=opt_cfg, x0=x0)
    x_best = opt_out["best_x"]
    gates_best = ansatz.build_gates(x_best, ctx=ctx, n_max=n_max, ps=ps)

    # Compute total gate time and depth
    total_time_us = compute_total_gate_time(gates_best, ctx)
    num_gates = len(gates_best)

    mode = obj_cfg.mode.lower()
    if mode == "unitary":
        U_best = compose_unitary(gates_best, n_max=n_max, ctx=ctx, cache=None)
        F_best = unitary_avg_fidelity(U_best, np.asarray(U_target, dtype=np.complex128))
        extra = {"U_best": U_best}
    elif mode == "density_matrix":
        from qubox_v2.compile.objectives import apply_gates_to_density_matrix, density_matrix_fidelity
        # Start from |0âŸ©âŸ¨0| (vacuum state)
        qubit_dim = ctx.qubit_dim
        d = qubit_dim * (n_max + 1)
        rho_initial = np.zeros((d, d), dtype=np.complex128)
        rho_initial[0, 0] = 1.0
        rho_best = apply_gates_to_density_matrix(rho_initial, gates_best, ctx, noise, n_max, cache, noise_model)
        rho_target = np.asarray(U_target, dtype=np.complex128)
        F_best = density_matrix_fidelity(rho_best, rho_target, metric=obj_cfg.density_metric)
        extra = {"rho_best": rho_best}
    else:  # noisy
        assert cache is not None and noise_model is not None
        S_best = compose_superop(gates_best, n_max=n_max, ctx=ctx, noise=noise, cache=cache, noise_model=noise_model)
        F_best = avg_gate_fidelity_superop(S_best, np.asarray(U_target, dtype=np.complex128))
        extra = {"S_best": S_best}

    return {
        "param_space": ps,
        "x_best": x_best,
        "gates_best": gates_best,
        "best_fidelity": float(F_best),
        "total_time_us": float(total_time_us),
        "num_gates": int(num_gates),
        **opt_out,
        **extra,
    }

