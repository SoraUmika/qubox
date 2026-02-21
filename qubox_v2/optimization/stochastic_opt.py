import random
import time
import numpy as np

from types import SimpleNamespace
from scipy.optimize import differential_evolution
import cma  # pip install pycma
# from skopt import gp_minimize
# from skopt.space import Real
# from skopt.utils import use_named_args
# from skopt.callbacks import CheckpointSaver

# ======================================================================
# TEST FUNCTION & BOUNDS
# ======================================================================
def noisy_quadratic_3d(x):
    """
    3D function + noise:
      f(x0, x1, x2) = (x0 - 3)^2 + (x1 + 2)^2 + (x2 - 1.5)^2 + noise
    """
    noise = random.gauss(0, 0.1)
    return ((x[0] - 3)**2 +
            (x[1] + 2)**2 +
            (x[2] - 1.5)**2 +
             noise)

three_d_bounds = [(-10, 10),  # for x0
                  (-10, 10),  # for x1
                  (-10, 10)]  # for x2

# ======================================================================
# 1) SciPy Differential Evolution -> opt_result
# ======================================================================
def scipy_de(obj_func,
             bounds=[(-10, 10), (-10, 10)],
             popsize=20,
             maxiter=100,
             recombination=0.9,
             mutation=(0.5, 1.0),
             strategy='best1exp'):
    """
    SciPy's Differential Evolution with advanced settings,
    returning an opt_result object.
    """
    start_time = time.perf_counter()

    result = differential_evolution(
        func=obj_func,
        bounds=bounds,
        popsize=popsize,
        maxiter=maxiter,
        recombination=recombination,
        mutation=mutation,
        strategy=strategy,
        polish=False,   # skip local refinement
        seed=42
    )

    end_time = time.perf_counter()

    opt_result = SimpleNamespace()
    opt_result.x = result.x.tolist()
    opt_result.fun = result.fun
    opt_result.n_iterations = result.nit
    opt_result.n_fevals = result.nfev
    opt_result.elapsed_time_s = end_time - start_time
    return opt_result

# ======================================================================
# 2) pycma CMA-ES -> opt_result
# ======================================================================
def cma_es(obj_func,
           bounds=[(-10, 10), (-10, 10)],
           sigma=1.0,
           maxiter=100,
           popsize=21):
    """
    pycma CMA-ES approach, returning an opt_result object.
    """
    start_time = time.perf_counter()

    # Convert bounds for CMA usage
    lower_bounds, upper_bounds = zip(*bounds)
    lower_bounds = np.array(lower_bounds)
    upper_bounds = np.array(upper_bounds)
    x0 = (lower_bounds + upper_bounds) / 2.0  # middle of the domain

    cma_opts = {
        'bounds': [list(lower_bounds), list(upper_bounds)],
        'popsize': popsize,
        'maxiter': maxiter,
        'randn': np.random.randn,  # for reproducibility if seed is fixed
        'seed': 42,
        'verbose': -9,  # reduce console output
    }

    es = cma.CMAEvolutionStrategy(x0.tolist(), sigma, cma_opts)

    while not es.stop():
        solutions = es.ask()
        fitness = [obj_func(s) for s in solutions]
        es.tell(solutions, fitness)

    end_time = time.perf_counter()

    cma_res = es.result  # CMAEvolutionStrategyResult

    opt_result = SimpleNamespace()
    opt_result.x = cma_res.xbest
    opt_result.fun = cma_res.fbest
    opt_result.n_iterations = cma_res.iterations
    opt_result.n_fevals = cma_res.evaluations
    opt_result.elapsed_time_s = end_time - start_time
    return opt_result

# ======================================================================
# 3) SPSA -> opt_result
# ======================================================================
def spsa(
    cost_function,
    x0,
    n_iter=100,
    a=0.1,
    c=0.1,
    alpha=0.602,
    gamma=0.101,
    A=10,
    callback=None,
    bounds=None
):
    """
    SPSA with optional bounding, returning an opt_result.
    """
    start_time = time.perf_counter()

    x = np.array(x0, dtype=float)

    def clamp(z):
        if bounds is not None:
            for i, (low, high) in enumerate(bounds):
                z[i] = np.clip(z[i], low, high)
        return z

    cost_history = []
    x = clamp(x)

    for k in range(1, n_iter + 1):
        ak = a / (k + A)**alpha
        ck = c / (k)**gamma

        delta = 2 * np.random.randint(0, 2, size=x.shape) - 1

        x_plus = clamp(x + ck * delta)
        x_minus = clamp(x - ck * delta)

        cost_plus = cost_function(x_plus)
        cost_minus = cost_function(x_minus)

        g_approx = (cost_plus - cost_minus) / (2.0 * ck) * (1.0 / delta)

        x = x - ak * g_approx
        x = clamp(x)

        cost_estimate = 0.5 * (cost_plus + cost_minus)
        cost_history.append(cost_estimate)

        if callback is not None:
            callback(k, x.copy(), cost_plus, cost_minus)

    end_time = time.perf_counter()

    opt_result = SimpleNamespace()
    opt_result.x = x.tolist()
    opt_result.fun = cost_history[-1]  # final cost estimate
    opt_result.n_iterations = n_iter
    # Each iteration does 2 cost calls => 2*n_iter total calls
    opt_result.n_fevals = 2 * n_iter
    opt_result.elapsed_time_s = end_time - start_time

    return opt_result

# ======================================================================
# 4) A simple Adam-based finite-diff optimizer -> opt_result
# ======================================================================
def adam_optimize(
    cost_fn,
    x0,
    max_iter=200,
    lr=0.01,
    beta1=0.9,
    beta2=0.999,
    epsilon=1e-8,
    bounds=None
):
    """
    Adam optimizer for a noisy cost function, returning an opt_result.
    Uses finite-difference approximations for the gradient.
    """
    start_time = time.perf_counter()

    x = np.array(x0, dtype=float)

    if bounds is not None:
        lb = np.array([b[0] for b in bounds])
        ub = np.array([b[1] for b in bounds])
        x = np.clip(x, lb, ub)

    m = np.zeros_like(x)
    v = np.zeros_like(x)
    cost_log = []

    for t in range(1, max_iter + 1):
        grad = np.zeros_like(x)
        eps = 1e-4  # step for finite difference

        for i in range(len(x)):
            delta = np.zeros_like(x)
            delta[i] = eps

            if bounds is not None:
                plus = np.clip(x + delta, lb, ub)
                minus = np.clip(x - delta, lb, ub)
            else:
                plus = x + delta
                minus = x - delta

            c_plus = cost_fn(plus)
            c_minus = cost_fn(minus)
            grad[i] = (c_plus - c_minus) / (2 * eps)

        # Adam updates
        m = beta1 * m + (1 - beta1) * grad
        v = beta2 * v + (1 - beta2) * (grad ** 2)
        m_hat = m / (1 - beta1**t)
        v_hat = v / (1 - beta2**t)

        x = x - lr * m_hat / (np.sqrt(v_hat) + epsilon)

        if bounds is not None:
            x = np.clip(x, lb, ub)

        # For demonstration: store cost after each iteration
        current_cost = cost_fn(x)
        cost_log.append(current_cost)

    end_time = time.perf_counter()

    opt_result = SimpleNamespace()
    opt_result.x = x.tolist()
    opt_result.fun = cost_log[-1]
    opt_result.n_iterations = max_iter
    # 2 fevals per dimension each iteration => 2*d*max_iter
    opt_result.n_fevals = 2 * len(x0) * max_iter
    opt_result.elapsed_time_s = end_time - start_time

    return opt_result

# ======================================================================
# 5) (Optional) scikit-optimize Bayesian Optimization -> opt_result
# ======================================================================
"""
from skopt import gp_minimize
from skopt.space import Real
from skopt.utils import use_named_args
from skopt.callbacks import CheckpointSaver

def skopt_bo(obj_func,
             bounds=[(-10, 10), (-10, 10)],
             n_calls=30,
             n_random_starts=5):
    start_time = time.perf_counter()

    dimensions = [
        Real(low=b[0], high=b[1], name=f"x{i}")
        for i, b in enumerate(bounds)
    ]

    @use_named_args(dimensions)
    def wrapped_obj_func(**kwargs):
        x_list = [kwargs[f"x{i}"] for i in range(len(bounds))]
        return obj_func(x_list)

    checkpoint_saver = CheckpointSaver("./skopt_checkpoint.pkl", store_objective=False)

    res = gp_minimize(
        func=wrapped_obj_func,
        dimensions=dimensions,
        n_calls=n_calls,
        n_random_starts=n_random_starts,
        acq_func="EI",
        acq_optimizer="auto",
        random_state=42,
        callback=[checkpoint_saver]
    )

    end_time = time.perf_counter()

    opt_result = SimpleNamespace()
    opt_result.x = res.x
    opt_result.fun = res.fun
    opt_result.n_iterations = len(res.x_iters)  # or res.n_iters if available
    opt_result.n_fevals = len(res.x_iters)
    opt_result.elapsed_time_s = end_time - start_time

    return opt_result
"""

# ======================================================================
# TEST SCRIPT
# ======================================================================
if __name__ == "__main__":
    random.seed(42)
    np.random.seed(42)

    print("========== Sophisticated Stochastic Optimization Demo (3D) ==========")
    print("Objective: noisy_quadratic_3d(x0, x1, x2).")
    print("True noiseless minimum is [3, -2, 1.5].")
    print("====================================================================\n")

    # 1) SciPy Differential Evolution
    de_result = scipy_de(
        obj_func=noisy_quadratic_3d,
        bounds=three_d_bounds,
        popsize=15,
        maxiter=80,
        strategy='rand1bin',
        recombination=0.7,
        mutation=(0.5, 1.0)
    )
    print("[SciPy DE]")
    print("  best_x =", de_result.x)
    print("  best_val =", de_result.fun)
    print("  n_iterations =", de_result.n_iterations)
    print("  n_fevals =", de_result.n_fevals)
    print(f"  elapsed_time_s = {de_result.elapsed_time_s:.4f}\n")

    # 2) pycma CMA-ES
    cma_result = cma_es(
        obj_func=noisy_quadratic_3d,
        bounds=three_d_bounds,
        sigma=0.5,
        maxiter=50,
        popsize=14
    )
    print("[pycma CMA-ES]")
    print("  best_x =", cma_result.x)
    print("  best_val =", cma_result.fun)
    print("  n_iterations =", cma_result.n_iterations)
    print("  n_fevals =", cma_result.n_fevals)
    print(f"  elapsed_time_s = {cma_result.elapsed_time_s:.4f}\n")

    # 3) SPSA
    spsa_result = spsa(
        cost_function=noisy_quadratic_3d,
        x0=[0.0, 0.0, 0.0],
        n_iter=300,  # e.g. 300 steps
        a=0.1,
        c=0.1,
        alpha=0.602,
        gamma=0.101,
        A=10,
        bounds=three_d_bounds
    )
    print("[SPSA]")
    print("  best_x =", spsa_result.x)
    print("  best_val =", spsa_result.fun)
    print("  n_iterations =", spsa_result.n_iterations)
    print("  n_fevals =", spsa_result.n_fevals)
    print(f"  elapsed_time_s = {spsa_result.elapsed_time_s:.4f}")
    print("  distance from true minimum:",
          np.linalg.norm(np.array(spsa_result.x) - [3, -2, 1.5]), "\n")

    # 4) Adam-based Finite Difference
    adam_result = adam_optimize(
        cost_fn=noisy_quadratic_3d,
        x0=[0.0, 0.0, 0.0],
        max_iter=200,
        lr=0.01,
        bounds=three_d_bounds
    )
    print("[Adam Finite-Diff]")
    print("  best_x =", adam_result.x)
    print("  best_val =", adam_result.fun)
    print("  n_iterations =", adam_result.n_iterations)
    print("  n_fevals =", adam_result.n_fevals)
    print(f"  elapsed_time_s = {adam_result.elapsed_time_s:.4f}")
    print("  distance from true minimum:",
          np.linalg.norm(np.array(adam_result.x) - [3, -2, 1.5]), "\n")

    # 5) (Optional) scikit-optimize Bayesian Optimization
    """
    bo_result = skopt_bo(
        obj_func=noisy_quadratic_3d,
        bounds=three_d_bounds,
        n_calls=25,
        n_random_starts=5
    )
    print("[scikit-optimize BO]")
    print("  best_x =", bo_result.x)
    print("  best_val =", bo_result.fun)
    print("  n_iterations =", bo_result.n_iterations)
    print("  n_fevals =", bo_result.n_fevals)
    print(f"  elapsed_time_s = {bo_result.elapsed_time_s:.4f}")
    """


