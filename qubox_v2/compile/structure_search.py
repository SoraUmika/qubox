# qubox_v2/compile/structure_search.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Any, Tuple
import numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed

from qubox_v2.gates.contexts import ModelContext, NoiseConfig
from qubox_v2.gates.cache import ModelCache
from qubox_v2.gates.noise import QubitT1T2Noise

from .ansatz import Ansatz
from .objectives import ObjectiveConfig
from .optimizers import OptimizerConfig
from .api import compile_with_ansatz


# ----------------------------
# Template factory interface
# ----------------------------
@dataclass(frozen=True)
class TemplateFactory:
    """
    A factory that can create a GateTemplate at a given position in a sequence.

    kind: short label like "D", "SQR", "R"
    make: function(pos:int, n_max:int) -> GateTemplate
    """
    kind: str
    make: Callable[[int, int], Any]


# ----------------------------
# Search config (FIXED: use default_factory for dataclass defaults)
# ----------------------------
@dataclass
class SearchConfig:
    """
    Beam search settings.
    """
    depth: int = 6
    beam_width: int = 8
    branch_factor: Optional[int] = None
    seed: int = 0

    # Coarse evaluation (fast pruning)
    coarse_opt: OptimizerConfig = field(default_factory=lambda: OptimizerConfig(
        method="Powell", maxiter=40, restarts=1, seed=0, progress=False
    ))
    coarse_obj: ObjectiveConfig = field(default_factory=lambda: ObjectiveConfig(
        mode="unitary", l2_weight=0.0
    ))

    # Adaptive pruning settings
    adaptive_beam_width: bool = True           # Enable dynamic pruning
    min_fidelity_threshold: float = 0.001      # Keep only candidates within this gap from best

    # Refinement (slower, accurate)
    refine_top_k: int = 3
    refine_opt: OptimizerConfig = field(default_factory=lambda: OptimizerConfig(
        method="Powell", maxiter=500, restarts=3, seed=0,
        progress=True, progress_every=10, progress_prefix="REFINE"
    ))
    refine_obj: ObjectiveConfig = field(default_factory=lambda: ObjectiveConfig(
        mode="unitary", l2_weight=0.0
    ))

    # Optional noisy finetune on the best refined candidate
    do_noisy_finetune: bool = False
    noisy_opt: OptimizerConfig = field(default_factory=lambda: OptimizerConfig(
        method="Powell", maxiter=180, restarts=1, seed=0,
        progress=True, progress_every=5, progress_prefix="NOISY"
    ))
    noisy_obj: ObjectiveConfig = field(default_factory=lambda: ObjectiveConfig(
        mode="noisy", l2_weight=0.0
    ))

    # Parallelization settings
    parallel_beam: bool = True     # Enable parallel beam expansion
    max_workers: int = 8           # Number of parallel workers


# ----------------------------
# Parallel worker function
# ----------------------------
def _evaluate_candidate_worker(
    args: Tuple[np.ndarray, List[Any], ModelContext, NoiseConfig, int, ObjectiveConfig, OptimizerConfig, List[str], Optional[np.ndarray]]
) -> Tuple[Dict[str, Any], List[str], List[Any]]:
    """
    Worker function for parallel beam expansion.
    Must be at module level to be picklable by ProcessPoolExecutor.
    
    Returns: (compile_output, kinds, templates)
    """
    U_target, templates, ctx, noise, n_max, coarse_obj, coarse_opt, kinds, x0 = args
    
    out = compile_with_ansatz(
        U_target=U_target,
        ansatz=Ansatz(templates),
        ctx=ctx,
        noise=noise,
        n_max=n_max,
        obj_cfg=coarse_obj,
        opt_cfg=coarse_opt,
        x0=x0,  # Use warm-start if available
    )
    
    return out, kinds, templates


# ----------------------------
# Optional ordering constraints
# ----------------------------
def default_constraint(prev_kinds: Sequence[str], next_kind: str) -> bool:
    """
    Return True if appending next_kind is allowed given the current prefix.
    Customize as needed.

    Default: disallow identical adjacent gate *kinds* to reduce redundancy.
    """
    if len(prev_kinds) > 0 and prev_kinds[-1] == next_kind:
        return False
    return True


# ----------------------------
# Beam search core
# ----------------------------
@dataclass
class Candidate:
    kinds: List[str]
    ansatz: Ansatz
    best_fidelity: float
    best_x: np.ndarray
    out: Dict[str, Any]  # compile_with_ansatz output


@dataclass
class _Node:
    kinds: List[str]
    templates: List[Any]
    best_fid: float
    best_x: Optional[np.ndarray]
    out: Optional[Dict[str, Any]]


def beam_search_orderings(
    *,
    U_target: np.ndarray,
    ctx: ModelContext,
    noise: NoiseConfig,
    n_max: int,
    factories: List[TemplateFactory],
    cfg: SearchConfig,
    constraint: Callable[[Sequence[str], str], bool] = default_constraint,
) -> Dict[str, Any]:
    """
    Search over gate ordering (structure) using beam search.
    Each candidate structure is scored by running continuous parameter optimization
    using compile_with_ansatz().

    Returns:
      - best_candidate: refined best
      - refined_candidates: list of refined candidates
      - beam_history: list of candidate lists per depth (coarse stage)
      - noisy_out: optional noisy finetune output
    """
    rng = np.random.default_rng(cfg.seed)
    qubit_dim = ctx.qubit_dim
    d = qubit_dim * (n_max + 1)
    U_target = np.asarray(U_target, dtype=np.complex128)
    if U_target.shape != (d, d):
        raise ValueError(f"U_target shape {U_target.shape} != {(d, d)}")

    # start with empty prefix
    nodes: List[_Node] = [_Node(kinds=[], templates=[], best_fid=-np.inf, best_x=None, out=None)]
    beam_history: List[List[Candidate]] = []

    for depth in range(cfg.depth):
        expanded: List[_Node] = []

        # Prepare candidate tasks
        tasks: List[Tuple] = []
        for node in nodes:
            # generate allowed next moves
            possible = [f for f in factories if constraint(node.kinds, f.kind)]
            if cfg.branch_factor is not None and len(possible) > cfg.branch_factor:
                possible = list(rng.choice(possible, size=cfg.branch_factor, replace=False))

            for f in possible:
                pos = len(node.kinds)
                t = f.make(pos, n_max)
                new_templates = node.templates + [t]
                new_kinds = node.kinds + [f.kind]
                
                # Smart x0 warm-start: extend parent's parameters with zeros for new template
                x0_warm = None
                if node.best_x is not None and node.best_x.size > 0:
                    # Calculate new parameter space size
                    new_ps = Ansatz(new_templates).param_space()
                    x0_warm = np.zeros(new_ps.dim(), dtype=float)
                    # Copy parent parameters (they correspond to first templates)
                    copy_size = min(node.best_x.size, x0_warm.size)
                    x0_warm[:copy_size] = node.best_x[:copy_size]
                
                # Package task for worker (need to pass x0_warm somehow)
                # Since worker uses x0=None currently, we'll need to modify approach
                # For now, store x0_warm in the task tuple
                tasks.append((
                    U_target, new_templates, ctx, noise, n_max,
                    cfg.coarse_obj, cfg.coarse_opt, new_kinds, x0_warm
                ))

        # Evaluate candidates (parallel or sequential)
        if cfg.parallel_beam and cfg.max_workers > 1 and len(tasks) > 1:
            # Parallel execution
            # OPTIMIZATION: Use chunksize for better load balancing with ProcessPoolExecutor
            print(f"[beam] depth={depth+1}/{cfg.depth} evaluating {len(tasks)} candidates in parallel (workers={cfg.max_workers})...")
            with ProcessPoolExecutor(max_workers=cfg.max_workers) as executor:
                # Submit all tasks and collect futures
                futures = {executor.submit(_evaluate_candidate_worker, task): idx 
                          for idx, task in enumerate(tasks)}
                
                # Process results as they complete (faster feedback)
                for future in as_completed(futures):
                    try:
                        out, kinds, templates = future.result()
                        expanded.append(_Node(
                            kinds=kinds,
                            templates=templates,
                            best_fid=float(out["best_fidelity"]),
                            best_x=np.asarray(out["best_x"], dtype=float),
                            out=out,
                        ))
                    except Exception as e:
                        # Log errors but continue processing other tasks
                        idx = futures[future]
                        print(f"[beam] Warning: Task {idx} failed with error: {e}")
                        continue
        else:
            # Sequential execution (fallback)
            for task in tasks:
                out, kinds, templates = _evaluate_candidate_worker(task)
                expanded.append(_Node(
                    kinds=kinds,
                    templates=templates,
                    best_fid=float(out["best_fidelity"]),
                    best_x=np.asarray(out["best_x"], dtype=float),
                    out=out,
                ))

        # keep top beam_width with adaptive pruning
        expanded.sort(key=lambda n: n.best_fid, reverse=True)
        
        # Adaptive pruning: only keep candidates close to the best
        if cfg.adaptive_beam_width and depth > 0 and len(expanded) > 0:
            best_fid = expanded[0].best_fid
            threshold = best_fid - cfg.min_fidelity_threshold
            expanded = [n for n in expanded if n.best_fid >= threshold]
            if len(expanded) > cfg.beam_width:
                expanded = expanded[: cfg.beam_width]
            print(f"[beam] adaptive pruning: kept {len(expanded)}/{len(expanded)} candidates above threshold {threshold:.6f}")
        else:
            expanded = expanded[: cfg.beam_width]
        
        nodes = expanded

        beam_history.append([
            Candidate(
                kinds=n.kinds,
                ansatz=Ansatz(n.templates),
                best_fidelity=n.best_fid,
                best_x=n.best_x if n.best_x is not None else np.array([], dtype=float),
                out=n.out if n.out is not None else {},
            )
            for n in nodes
        ])

        best_time_us = nodes[0].out.get("total_time_us", 0.0) if nodes[0].out else 0.0
        best_num_gates = nodes[0].out.get("num_gates", 0) if nodes[0].out else 0
        print(f"[beam] depth={depth+1}/{cfg.depth} best_fid={nodes[0].best_fid:.6f} time={best_time_us:.3f}us gates={best_num_gates} kinds={nodes[0].kinds}")

    # refine top candidates
    refined: List[Candidate] = []
    for n in nodes[: cfg.refine_top_k]:
        out_ref = compile_with_ansatz(
            U_target=U_target,
            ansatz=Ansatz(n.templates),
            ctx=ctx,
            noise=noise,
            n_max=n_max,
            obj_cfg=cfg.refine_obj,
            opt_cfg=cfg.refine_opt,
            x0=n.best_x,
        )
        refined.append(Candidate(
            kinds=n.kinds,
            ansatz=Ansatz(n.templates),
            best_fidelity=float(out_ref["best_fidelity"]),
            best_x=np.asarray(out_ref["best_x"], dtype=float),
            out=out_ref,
        ))

    refined.sort(key=lambda c: c.best_fidelity, reverse=True)
    best = refined[0]

    # optional noisy finetune on best refined candidate
    noisy_out = None
    if cfg.do_noisy_finetune:
        noisy_out = compile_with_ansatz(
            U_target=U_target,
            ansatz=best.ansatz,
            ctx=ctx,
            noise=noise,
            n_max=n_max,
            obj_cfg=cfg.noisy_obj,
            opt_cfg=cfg.noisy_opt,
            x0=best.best_x,
            cache=ModelCache(),
            noise_model=QubitT1T2Noise(),
        )

    return {
        "best_candidate": best,
        "refined_candidates": refined,
        "beam_history": beam_history,
        "noisy_out": noisy_out,
    }

