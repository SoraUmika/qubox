# qubox_v2/compile/optimizers.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Dict, Any
import numpy as np
from scipy.optimize import minimize

from .param_space import ParamSpace


@dataclass
class OptimizerConfig:
    method: str = "Powell"
    maxiter: int = 300
    restarts: int = 5
    seed: int = 0
    init_scale: float = 0.2
    use_bounds: bool = True

    # progress printing
    progress: bool = True
    progress_every: int = 10          # print every N iterations
    progress_prefix: str = ""         # e.g. "UNITARY" or "NOISY"
    progress_eval_on_print: bool = True  # re-evaluate loss at xk when printing (more accurate)
    
    # early termination
    early_stop_threshold: float = 0.0  # stop if loss < threshold (0.0 = disabled)
    early_stop_fidelity: float = 0.0   # stop if fidelity > threshold (0.0 = disabled)
    stagnation_iters: int = 0          # stop if no improvement for N iters (0 = disabled)


def _fmt(x: Optional[float]) -> str:
    if x is None:
        return "None"
    return f"{x:.6g}"


def run_optimization(
    *,
    loss_fn: Callable[[np.ndarray], float],
    ps: ParamSpace,
    opt_cfg: OptimizerConfig,
    x0: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    rng = np.random.default_rng(opt_cfg.seed)

    bnds = ps.bounds() if opt_cfg.use_bounds else None
    method = str(opt_cfg.method)

    x0_list = []
    if x0 is not None:
        x0_list.append(ps.apply_fixed(np.asarray(x0, dtype=float)))
    else:
        x0_list.append(ps.apply_fixed(np.zeros(ps.dim(), dtype=float)))

    for _ in range(int(opt_cfg.restarts)):
        x0_list.append(ps.random_x0(rng, scale=float(opt_cfg.init_scale)))

    best_res = None
    best_fun = np.inf
    best_x = None

    # function-eval counter (across a single restart)
    def make_counted_loss():
        evals = {"n": 0}

        def counted(x: np.ndarray) -> float:
            evals["n"] += 1
            return loss_fn(x)

        counted.evals = evals  # type: ignore[attr-defined]
        return counted

    for restart_idx, x0i in enumerate(x0_list):
        counted_loss = make_counted_loss()

        iter_counter = {"k": 0}
        best_restart = {"loss": np.inf, "fid": None}
        stagnation_counter = {"count": 0, "best_so_far": np.inf}

        prefix = opt_cfg.progress_prefix.strip()
        prefix = (prefix + " ") if prefix else ""

        if opt_cfg.progress:
            print(f"{prefix}Restart {restart_idx+1}/{len(x0_list)} | method={method} | dim={ps.dim()}")

        def callback(xk: np.ndarray, *args):
            # SciPy calls callback with xk for most methods; some pass extra args.
            iter_counter["k"] += 1
            k = iter_counter["k"]
            
            # OPTIMIZATION: Only evaluate loss if needed for early stopping or progress printing
            current_loss = None
            
            # Early stopping checks
            if opt_cfg.progress_eval_on_print or opt_cfg.early_stop_threshold > 0 or opt_cfg.early_stop_fidelity > 0 or opt_cfg.stagnation_iters > 0:
                current_loss = float(counted_loss(xk))
                
                # Check early termination conditions
                if opt_cfg.early_stop_threshold > 0 and current_loss < opt_cfg.early_stop_threshold:
                    if opt_cfg.progress:
                        print(f"{prefix}  [iter {k}] Early stop: loss {current_loss:.6f} < threshold {opt_cfg.early_stop_threshold:.6f}")
                    raise StopIteration("Early stop: loss threshold reached")
                
                # Check fidelity-based early stop (assuming loss function has last_info)
                if opt_cfg.early_stop_fidelity > 0 and hasattr(loss_fn, 'last_info'):
                    fid = loss_fn.last_info.get('fidelity', 0.0)
                    if fid > opt_cfg.early_stop_fidelity:
                        if opt_cfg.progress:
                            print(f"{prefix}  [iter {k}] Early stop: fidelity {fid:.6f} > threshold {opt_cfg.early_stop_fidelity:.6f}")
                        raise StopIteration("Early stop: fidelity threshold reached")
                
                # Check stagnation
                if opt_cfg.stagnation_iters > 0:
                    if current_loss < stagnation_counter["best_so_far"] - 1e-9:
                        stagnation_counter["best_so_far"] = current_loss
                        stagnation_counter["count"] = 0
                    else:
                        stagnation_counter["count"] += 1
                        if stagnation_counter["count"] >= opt_cfg.stagnation_iters:
                            if opt_cfg.progress:
                                print(f"{prefix}  [iter {k}] Early stop: no improvement for {opt_cfg.stagnation_iters} iterations")
                            raise StopIteration("Early stop: stagnation detected")

            if not opt_cfg.progress:
                return

            if opt_cfg.progress_every <= 0:
                return

            if (k % opt_cfg.progress_every) != 0:
                return

            # Print "current" status:
            # Optionally re-evaluate at xk to ensure last_info corresponds to this iterate.
            if opt_cfg.progress_eval_on_print:
                L = current_loss if current_loss is not None else float(counted_loss(xk))
            else:
                # if we don't re-evaluate, we rely on whatever was last evaluated
                # (might not be exactly xk)
                li = getattr(loss_fn, "last_info", {})  # type: ignore[attr-defined]
                L = float(li.get("loss")) if li.get("loss") is not None else float("nan")

            li = getattr(loss_fn, "last_info", {})  # type: ignore[attr-defined]
            F = li.get("fidelity", None)

            if L < best_restart["loss"]:
                best_restart["loss"] = L
                best_restart["fid"] = F

            ev = counted_loss.evals["n"]  # type: ignore[attr-defined]
            msg = (
                f"{prefix}iter={k}  evals={ev}  "
                f"loss={_fmt(L)}  fidelity={_fmt(F)}  "
                f"best_loss={_fmt(best_restart['loss'])}  best_fid={_fmt(best_restart['fid'])}"
            )
            print(msg)

        use_bnds = (
            bnds is not None
            and method.lower() in ("powell", "l-bfgs-b", "tnc", "slsqp", "trust-constr")
        )

        try:
            res = minimize(
                counted_loss,
                x0=x0i,
                method=method,
                bounds=bnds if use_bnds else None,
                callback=callback,
                options={"maxiter": int(opt_cfg.maxiter), "disp": False},
            )
        except StopIteration as e:
            # Early stopping triggered - create result object
            if opt_cfg.progress:
                print(f"{prefix}  Stopped early: {str(e)}")
            # Create a minimal result object
            class EarlyStopResult:
                def __init__(self, x, fun, nit, success=True):
                    self.x = x
                    self.fun = fun
                    self.nit = nit
                    self.success = success
                    self.nfev = counted_loss.evals["n"]
            
            # Use best known solution
            final_loss = best_restart["loss"] if best_restart["loss"] < np.inf else np.inf
            res = EarlyStopResult(x=best_x if best_x is not None else x0i, fun=final_loss, nit=iter_counter["k"], success=True)

        # one final evaluation to refresh last_info at solution
        final_loss = float(counted_loss(res.x))
        li = getattr(loss_fn, "last_info", {})  # type: ignore[attr-defined]
        final_fid = li.get("fidelity", None)

        if opt_cfg.progress:
            ev = counted_loss.evals["n"]  # type: ignore[attr-defined]
            print(
                f"{prefix}done restart {restart_idx+1}: "
                f"iters={iter_counter['k']} evals={ev} "
                f"loss={_fmt(final_loss)} fidelity={_fmt(final_fid)} success={res.success}"
            )

        if final_loss < best_fun:
            best_fun = float(final_loss)
            best_res = res
            best_x = ps.apply_fixed(np.asarray(res.x, dtype=float))

    assert best_res is not None and best_x is not None
    return {
        "result": best_res,
        "best_x": best_x,
        "best_loss": best_fun,
    }

