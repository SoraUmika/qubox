import numpy as np

from ..data.containers import Output
from .transforms import apply_norm_IQ, bools_to_sigma_z, demod2volts
def _infer_tag(i_key: str) -> str:
    # Heuristics: strip leading 'I'/'Q' and underscores, keep remainder
    if not isinstance(i_key, str):
        return ""
    s = i_key
    if s.startswith("I") or s.startswith("Q"):
        s = s[1:]
    s = s.lstrip("_")
    # Allow alnum tags only; else return empty
    return s if s and all(c.isalnum() or c in ("-",) for c in s) else ""

def proc_attach(key, val):
    """Factory: return a processor that attaches a constant array/obj to Output."""
    def _p(out: Output, **_):
        out[key] = val
        return out
    return _p

def bare_proc(output: Output):
    return output 

def proc_default(output: Output, axis: int = 0, targets=None, **kwargs) -> Output:
    """
    Demodulate one or more (I, Q) pairs into complex/phase representations.

    Notes
    -----
    In some backends, `output.extract()` returns structured arrays (e.g.
    dtype([('value','<f8')])) rather than plain float arrays. This function
    unwraps such arrays into plain numpy arrays before forming complex S.
    """

    def _plain_ndarray(x):
        """Convert structured arrays into plain numeric arrays."""
        a = np.asarray(x)
        if a.dtype.fields is not None:
            if "value" in a.dtype.fields:
                a = a["value"]
            else:
                first = next(iter(a.dtype.fields.keys()))
                a = a[first]
        return np.asarray(a)

    if targets is None:
        targets = [("I", "Q")]

    if targets == [("I", "Q")] and ('I' not in output or 'Q' not in output):
        print("Warning: cannot demodulate without I/Q.")
        return output

    for t in targets:
        if len(t) == 2:
            I_key, Q_key = t
            tag = _infer_tag(I_key)
        elif len(t) == 3:
            I_key, Q_key, tag = t
            tag = str(tag) if tag is not None else _infer_tag(I_key)
        else:
            print(f"Warning: target spec {t} must be (I_key, Q_key[, tag]); skipping.")
            continue

        suf = f"_{tag}" if tag else ""

        if I_key not in output or Q_key not in output:
            print(f"Warning: cannot demodulate pair ({I_key}, {Q_key}) â€” missing key(s).")
            continue

        try:
            I, Q = output.extract(I_key, Q_key)

            # --- unwrap structured dtypes (critical) ---
            I = _plain_ndarray(I)
            Q = _plain_ndarray(Q)

            S = I + 1j * Q

            Phases = np.angle(S)
            if np.ndim(S) == 0:
                uPhases = Phases
            else:
                uPhases = np.unwrap(np.asarray(Phases), axis=axis)

            output[f"S{suf}"] = S
            output[f"Phases{suf}"] = Phases
            output[f"uPhases{suf}"] = uPhases

            try:
                del output[I_key]
                del output[Q_key]
            except Exception:
                pass

        except Exception as e:
            print(f"Demodulation failed for pair ({I_key}, {Q_key}) with error {e}. Leaving I/Q as-is.")

    return output


def ro_state_correct_proc(
    output,
    targets=None,
    confusion=None,
    *,
    clip: bool = True,
    renormalize: bool = True,
    to_sigmaz: bool = False,
    **kwargs,
):
    """
    For each (target_str, output_str) in `targets`, read probabilities from
    output[target_str], interpret EVERY entry as P_e (excited-state probability),
    convert to [P_g, P_e], optionally apply confusion-matrix correction, and
    store the result in:

        - if output_str is NOT explicitly given:
              output["corrected_" + target_str]
        - if output_str IS explicitly given (tuple length >= 2 and non-None):
              output[output_str]

    If output_str is not provided (tuple of length 1 or None), it defaults to target_str.

    **Layout assumption (NEW / STRICT):**
        For ANY ndarray `a` (scalar, 1D, 2D, ND):
            - Each element of `a` is interpreted as P_e.
            - Internally we build an array PgPe with shape a.shape + (2,),
              where the last axis is [P_g, P_e] = [1 - P_e, P_e].
            - Confusion-matrix corrections act on that last axis only.

    If `to_sigmaz=False`:
        - We store corrected P_e with the SAME SHAPE as the original data.

    If `to_sigmaz=True`:
        - We store corrected <Ïƒ_z> = P_e - P_g with the SAME SHAPE
          as the original data and also store an uncorrected "raw_" version.
    """
    # --- handle optional arguments ---
    if confusion is None or targets is None:
        missing = []
        if confusion is None:
            missing.append("confusion matrix")
        if targets is None:
            missing.append("targets list")
        print(
            f"Warning: {', '.join(missing)} not provided; "
            "skipping ro_state_correct_proc and returning output unchanged."
        )
        return output

    # --- validate and invert confusion matrix ---
    Lambda = np.asarray(confusion, dtype=float)
    if Lambda.shape[0] != Lambda.shape[1]:
        raise ValueError("Confusion matrix must be square (n_outcomes, n_states).")
    if np.linalg.det(Lambda) == 0:
        raise ValueError("Confusion matrix is singular; cannot invert.")

    Lambda_inv = np.linalg.inv(Lambda)

    def _to_PgPe(a: np.ndarray):
        """
        Given an arbitrary array `a` whose entries are all P_e, return:

            PgPe  : ndarray with shape a.shape + (2,)
                    last axis is [P_g, P_e] = [1 - P_e, P_e]
            orig_shape : the original shape of `a`
        """
        a = np.asarray(a, dtype=float)
        orig_shape = a.shape

        # Build (â€¦, 2) where last axis is [P_g, P_e]
        Pe = a
        Pg = 1.0 - Pe
        # Broadcast stack along a new last axis
        PgPe = np.stack([Pg, Pe], axis=-1)

        return PgPe, orig_shape

    def _correct(PgPe: np.ndarray) -> np.ndarray:
        """
        Apply Lambdaâ»Â¹ to PgPe along the last axis, with basic physicality fixes.
        PgPe is assumed to have shape (..., 2).
        Returns an array of the SAME SHAPE as PgPe.
        """
        PgPe = np.asarray(PgPe, dtype=float)
        if PgPe.shape[-1] != 2:
            raise ValueError(
                f"_correct expects last dimension 2 (Pg,Pe), got shape {PgPe.shape}."
            )

        # Flatten all but last axis for convenience
        orig_shape = PgPe.shape
        flat = PgPe.reshape(-1, 2)  # (M, 2)

        # Apply inverse confusion matrix on each row
        # p_true_flat[i] = Lambda_inv @ flat[i]
        p_true_flat = (Lambda_inv @ flat.T).T  # still (M, 2)

        if clip:
            p_true_flat = np.maximum(p_true_flat, 0.0)
        if renormalize:
            s = p_true_flat.sum(axis=-1, keepdims=True)
            p_true_flat = np.where(s > 0, p_true_flat / s, p_true_flat)

        # Reshape back
        p_true = p_true_flat.reshape(orig_shape)
        return p_true

    # --- main loop over targets ---
    for t in targets:
        if not (isinstance(t, tuple) or isinstance(t, list)):
            print(f"Warning: target spec {t!r} is not a tuple/list; skipping.")
            continue

        # Track whether output_str was explicitly given
        if len(t) == 1:
            target_str = t[0]
            output_str = target_str
            explicit_output = False
        elif len(t) >= 2:
            target_str = t[0]
            raw_output = t[1]
            if raw_output is None:
                output_str = target_str
                explicit_output = False
            else:
                output_str = raw_output
                explicit_output = True
        else:
            print(f"Warning: target spec {t!r} has invalid length; skipping.")
            continue

        if target_str not in output:
            print(f"Warning: '{target_str}' not in output; skipping.")
            continue

        raw = output[target_str]
        a = np.asarray(raw, dtype=float)

        # Convert Pe â†’ PgPe (...,2) and remember original shape
        PgPe, orig_shape = _to_PgPe(a)
        p_true = _correct(PgPe)

        # p_true[..., 0] = corrected P_g
        # p_true[..., 1] = corrected P_e

        if to_sigmaz:
            # Ïƒ_z = P_g - P_e  (standard: |g>=|0> -> +1, |e>=|1> -> -1)
            sigmaz_corr   = p_true[..., 0] - p_true[..., 1]
            sigmaz_uncorr = PgPe[..., 0]   - PgPe[..., 1]

            value_to_store    = sigmaz_corr.reshape(orig_shape)
            uncorrected_value = sigmaz_uncorr.reshape(orig_shape)
        else:
            # Store corrected P_e with the SAME SHAPE as original data
            Pe_corr = p_true[..., 1]  # shape orig_shape
            value_to_store    = Pe_corr.reshape(orig_shape)
            uncorrected_value = None  # not used

        # Choose key based on whether output_str was explicit
        if explicit_output:
            corrected_key = output_str
        else:
            corrected_key = f"corrected_{output_str}"

        output[corrected_key] = value_to_store

        if to_sigmaz:
            uncorrected_key = f"raw_{output_str}"
            output[uncorrected_key] = uncorrected_value

    return output


def qubit_proc(output: Output,
               normalize_params: dict = {},
               axis: int = 0,
               targets=None) -> dict:
    """
    Demodulate via default_proc (which may delete I/Q) and then apply normalization
    to each resulting complex stream S{_tag} â†’ States{_tag}.
    """

    output = proc_default(output, axis, targets=targets)

    def _infer_tag(i_key: str) -> str:
        if not isinstance(i_key, str):
            return ""
        s = i_key
        if s.startswith(("I", "Q")):
            s = s[1:]
        s = s.lstrip("_")
        return s if s and all(c.isalnum() or c == "-" for c in s) else ""

    if targets is None:
        # Backward-compat: single pair ("I","Q") â†’ S (no suffix)
        suffixes = [""]
    else:
        suffixes = []
        for t in targets:
            if len(t) == 2:
                I_key, _ = t
                tag = _infer_tag(I_key)
            elif len(t) == 3:
                I_key, _, tag = t
                tag = str(tag) if tag is not None else _infer_tag(I_key)
            else:
                print(f"Warning: target spec {t} must be (I_key, Q_key[, tag]); skipping.")
                continue
            suffixes.append(("" if not tag else f"_{tag}"))

    # 3) Apply normalization to each S{_tag}
    if not normalize_params:
        print("Warning: No normalization parameters provided. Skipping normalization.")
        #return output

    factor = normalize_params.get("factor", 1.0)
    offset = normalize_params.get("offset", 0.0)

    for suf in suffixes:
        S_key = f"S{suf}"
        if S_key not in output:
            # This can happen if the pair was missing or demod failed for that target.
            print(f"Warning: {S_key} not found; skipping normalization for this target.")
            continue
        S = output[S_key]
        output[f"States{suf}"] = apply_norm_IQ(S, factor, offset)
    return output
    
# NEW: commonly needed for spectroscopy plots
def proc_magnitude(output: Output, **_) -> Output:
    if "S" in output:
        output["magnitude"] = np.abs(output["S"])
    return output
