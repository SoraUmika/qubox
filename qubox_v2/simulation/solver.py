# solver.py
import qutip as qt

def _compile_hamiltonian(H, tlist, args=None):
    """
    Turn list-format H with Python callables into a compiled QobjEvo whose
    coefficients are Cubic_Splines sampled on tlist (C-level eval in solver).
    If H is already a QobjEvo, just compile it. If H is a time-independent Qobj,
    return it unchanged.
    """
    args = args or {}
    # Already compiled or time-independent?
    if isinstance(H, qt.QobjEvo):
        Hevo = H.copy()
        Hevo.compile(inplace=True)
        return Hevo
    if not isinstance(H, list):
        return H  # plain Qobj, time-independent

    # Import Cubic_Spline (compat across QuTiP versions)
    try:
        from qutip.coefficient import Cubic_Spline
    except Exception:
        from qutip.interpolate import Cubic_Spline

    tlist = np.asarray(tlist, dtype=float)
    t0, t1 = float(tlist[0]), float(tlist[-1])

    compiled_terms = [H[0]]  # static base
    coeff_cache = {}         # reuse sampled arrays when functions repeat

    for term in H[1:]:
        if not isinstance(term, (list, tuple)) or len(term) != 2:
            raise TypeError("Each time-dependent term must be [op, coeff].")
        op, coeff = term

        # If it's already a coefficient object (has C-level call), keep as is
        if hasattr(coeff, "call") or hasattr(coeff, "cfunc"):
            compiled_terms.append([op, coeff])
            continue

        # If it's a numpy array of samples (must match tlist), wrap directly
        if isinstance(coeff, np.ndarray):
            if coeff.shape[0] != tlist.shape[0]:
                raise ValueError("Coefficient array length must match tlist length.")
            compiled_terms.append([op, Cubic_Spline(t0, t1, np.asarray(coeff, dtype=complex))])
            continue

        # Strings are supported by QobjEvo; leave them (can still compile, albeit slower)
        if isinstance(coeff, str):
            compiled_terms.append([op, coeff])
            continue

        # Numeric constant â†’ fold into static term
        try:
            c = complex(coeff)
            compiled_terms[0] = compiled_terms[0] + (c * op)
            continue
        except Exception:
            pass  # not a plain number; fall through

        # Python callable: sample once on tlist and spline it
        if callable(coeff):
            key = id(coeff)
            vals = coeff_cache.get(key)
            if vals is None:
                # Expect signature f(t, args). If user wrote f(t), args is ignored safely.
                vals = np.asarray([coeff(float(t), args) for t in tlist], dtype=complex)
                coeff_cache[key] = vals
            compiled_terms.append([op, Cubic_Spline(t0, t1, vals)])
            continue

        raise TypeError(f"Unsupported coefficient type: {type(coeff)}")

    Hevo = qt.QobjEvo(compiled_terms)
    Hevo.compile(inplace=True)
    return Hevo


def solve_lindblad(H, tlist, rho0, *, c_ops=None, e_ops=None,
                   args=None, store_states=False, progress_bar=False, options=None):
    """
    Wrapper for qt.mesolve that:
      â€¢ accepts kets or density matrices for rho0,
      â€¢ uses a dict for `options` (avoids FutureWarning in newer QuTiP),
      â€¢ lets you choose a progress bar (many builds read it from options).
    """

    rho0_dm = rho0 if rho0.isoper else qt.ket2dm(rho0)
    c_ops = [] if c_ops is None else c_ops
    e_ops = [] if e_ops is None else e_ops

    # Build a dict of options (no qt.Options() to avoid the warning)
    if isinstance(options, dict):
        opts = options.copy()
    else:
        opts = {}
    opts.setdefault('nsteps', 5000)
    opts.setdefault('store_states', store_states)

    if isinstance(progress_bar, str):
        opts['progress_bar'] = progress_bar
    elif progress_bar is False:
        opts.pop('progress_bar', None)
    else:
        opts.setdefault('progress_bar', 'enhanced')

    try:
        return qt.mesolve(H, rho0_dm, tlist, c_ops=c_ops, e_ops=e_ops,
                          args=args or {}, options=opts)
    except (TypeError, KeyError):
        opts.pop('progress_bar', None)
        return qt.mesolve(H, rho0_dm, tlist, c_ops=c_ops, e_ops=e_ops,
                          args=args or {}, options=opts)
