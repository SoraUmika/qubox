# Optimization

Bayesian, local, and stochastic optimization for experiment tuning.

## Bayesian Optimization (`qubox_tools.optimization.bayesian`)

Gaussian Process-based Bayesian optimization for multi-parameter tuning:

```python
from qubox_tools.optimization.bayesian import BayesianOptimizer

optimizer = BayesianOptimizer(
    bounds={
        "readout_freq": (7.15e9, 7.25e9),
        "readout_amp": (0.1, 0.5),
        "readout_duration": (500, 2000),
    },
    objective="maximize",
    n_initial=10,
    kernel="matern",
)

# Optimization loop
for i in range(50):
    params = optimizer.suggest()
    # Run experiment with suggested params...
    fidelity = run_readout_experiment(**params)
    optimizer.observe(params, fidelity)

best = optimizer.best_params()
print(f"Optimal params: {best}")
```

### Key Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `bounds` | `dict[str, tuple]` | Parameter bounds |
| `objective` | `str` | `"maximize"` or `"minimize"` |
| `n_initial` | `int` | Random initial samples |
| `kernel` | `str` | GP kernel (`"matern"`, `"rbf"`, `"rational_quadratic"`) |
| `acquisition` | `str` | Acquisition function (`"ei"`, `"ucb"`, `"pi"`) |

## Local Optimization (`qubox_tools.optimization.local`)

Wrapper around `scipy.optimize.minimize`:

```python
from qubox_tools.optimization.local import local_minimize

result = local_minimize(
    objective_fn=cost_function,
    x0=initial_params,
    method="Nelder-Mead",
    bounds=param_bounds,
    maxiter=100,
)
```

### Supported Methods

| Method | Use Case |
|--------|----------|
| `"Nelder-Mead"` | Derivative-free, robust default |
| `"L-BFGS-B"` | Bounded gradient-based |
| `"Powell"` | Conjugate direction |

## Stochastic Optimization (`qubox_tools.optimization.stochastic`)

Global optimization for challenging landscapes:

```python
from qubox_tools.optimization.stochastic import (
    differential_evolution, cma_es
)

# Differential Evolution
result = differential_evolution(
    objective_fn=cost_function,
    bounds=param_bounds,
    maxiter=200,
    popsize=15,
)

# CMA-ES
result = cma_es(
    objective_fn=cost_function,
    x0=initial_params,
    sigma0=0.1,
    maxiter=500,
)
```

## Use Cases

| Scenario | Recommended Optimizer |
|----------|-----------------------|
| Readout optimization (3-5 params) | Bayesian |
| Pulse calibration fine-tuning | Local (Nelder-Mead) |
| Gate fidelity landscape (~10 params) | CMA-ES |
| Multi-modal search | Differential Evolution |
| Quick 1D optimization | Local (L-BFGS-B) |
