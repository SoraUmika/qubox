from typing import Callable, List
from skopt import gp_minimize
from skopt.space import Real, Integer, Categorical

def bayesian_optimize(
    objective_func: Callable[[List[float]], float],
    param_space: List,
    n_calls: int = 25,
    n_random_starts: int = 5,
    random_state: int = None,
    callback = None
):
    """
    Performs Bayesian Optimization on a given black-box objective function.

    Parameters
    ----------
    objective_func : Callable[[List[float]], float]
        A function that takes a list of parameters (floats, ints, etc.) and returns a scalar score.
        (You want to minimize this score.)
    param_space : List
        A list of search space dimensions, where each dimension can be:
          - skopt.space.Real(a, b, prior='log-uniform'), or
          - skopt.space.Integer(a, b), or
          - skopt.space.Categorical(categories)
        Example:
          [
            Real(1e-6, 1e-1, prior='log-uniform', name='learning_rate'),
            Integer(1, 100, name='max_depth')
          ]
    n_calls : int, default=25
        The number of total optimization calls (function evaluations).
    n_random_starts : int, default=5
        The number of random initial points before fitting the surrogate model.
    random_state : int, optional
        Seed used to reproduce the results.
    callback : callable, optional
        Callback function called after each iteration. If it returns True, optimization stops.

    Returns
    -------
    result : skopt.OptimizeResult
        The optimization result object returned by scikit-optimize's gp_minimize. 
        Notable attributes:
          - result.x : list of best-found parameters
          - result.fun : minimal value of the objective function
          - result.x_iters : all parameter sets evaluated
          - result.func_vals : objective function values for each set
    """

    result = gp_minimize(
        func=objective_func,
        dimensions=param_space,
        n_calls=n_calls,
        n_random_starts=n_random_starts,
        random_state=random_state,
        callback=callback
    )
    return result

def test_bayesian_optimize_simple():
    # Define a simple dummy objective function
    def objective(params):
        x, y = params
        # A simple 2D paraboloid with its minimum at x=2, y=3
        return (x - 2) ** 2 + (y - 3) ** 2

    # Define the parameter space
    param_space = [
        Real(-10, 10, name="x"),
        Integer(-10, 10, name="y"),
    ]

    # Run Bayesian optimization
    result = bayesian_optimize(
        objective_func=objective,
        param_space=param_space,
        n_calls=15,
        n_random_starts=5,
        random_state=42
    )

    # Print optimization result
    print("All evaluated points (x_iters):", result.x_iters)
    print("All objective values (func_vals):", result.func_vals)
    print("Best found parameters (result.x):", result.x)
    print("Best objective value (result.fun):", result.fun)

    # You can also include simple assertions, e.g.:
    # Expect that the best parameters found are near [2, 3].
    assert abs(result.x[0] - 2) <= 2  # within some tolerance
    assert abs(result.x[1] - 3) <= 2
    print("Test passed!")


if __name__ == "__main__":
    test_bayesian_optimize_simple()