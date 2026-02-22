import scipy.optimize

def scipy_minimize(fun, x0, args=(), method=None, jac=None, hess=None, hessp=None,
                    bounds=None, constraints=(), tol=None, callback=None, options=None):
    """
    A wrapper around scipy.optimize.minimize that provides default methods and options.

    Parameters:
      fun : callable
          The objective function to be minimized.
      x0 : array_like
          Initial guess for the parameters.
      args : tuple, optional
          Extra arguments passed to the objective function.
      method : str, optional
          Optimization method. If None, defaults to:
            - 'L-BFGS-B' if bounds are provided, or
            - 'BFGS' if no bounds are provided.
      jac : callable, optional
          Function to compute the gradient (Jacobian) of the objective.
      hess : callable, optional
          Function to compute the Hessian of the objective.
      hessp : callable, optional
          Function to compute the Hessian-product.
      bounds : sequence or None, optional
          Bounds for variables as a sequence of (min, max) pairs.
      constraints : dict or sequence, optional
          Constraint definitions (equality, inequality constraints).
      tol : float, optional
          Tolerance for termination.
      callback : callable, optional
          Called after each iteration.
      options : dict, optional
          A dictionary of solver options.

    Returns:
      result : OptimizeResult
          The optimization result returned by scipy.optimize.minimize.
    """
    # Choose a default method based on the presence of bounds
    if method is None:
        method = 'L-BFGS-B' if bounds is not None else 'BFGS'
    
    # Ensure options is a dictionary; set tolerance if provided
    if options is None:
        options = {}
    if tol is not None:
        options['tol'] = tol
    
    # Call the scipy.optimize.minimize function with all provided arguments.
    result = scipy.optimize.minimize(fun, x0, args=args, method=method, jac=jac, hess=hess,
                                     hessp=hessp, bounds=bounds, constraints=constraints,
                                     callback=callback, options=options)
    return result

# Example usage:
if __name__ == "__main__":
    pass
