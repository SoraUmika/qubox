from pprint import pprint
from qm.qua import *
import logging
import json
from ...pulses.manager import PulseOp  # single canonical import
from contextlib import contextmanager
from ...analysis.analysis_tools import (
    complex_encoder, complex_decoder,
    interp_logpdf, bilinear_interp_logpdf,
    compile_1d_kde_to_grid, compile_2d_kde_to_grid
)
from ...analysis.post_selection import PostSelectionConfig
from ...core.persistence_policy import sanitize_mapping_for_json
import numpy as np

logger = logging.getLogger(__name__)

# Canonical readout weight sets
DEFAULT_WEIGHT_SETS = {
    "base": [["cos", "sin"], ["minus_sin", "cos"]],
    # later you can add e.g. "rot": [["rot_cos", "rot_sin"], ["rot_m_sin", "rot_cos"]]
}


def _format_ndarray_for_display(arr, indent: str = "  ") -> str:
    """
    Pretty-format a 1D or 2D numpy array so rows/cols line up nicely.
    Returns a multi-line string.
    """
    arr = np.asarray(arr)

    # 1D case: [ v0  v1  v2 ... ]
    if arr.ndim == 1:
        cells = []
        for val in arr:
            if isinstance(val, (int, np.integer)):
                s = f"{int(val)}"
            elif isinstance(val, (float, np.floating)):
                s = f"{val:.4g}"   # 4 sig figs
            else:
                s = str(val)
            cells.append(s)
        widths = [max(len(c) for c in cells)] if cells else [0]
        padded = [c.rjust(widths[0]) for c in cells]
        return "[ " + "  ".join(padded) + " ]"

    # 2D case: nicely aligned rows/cols
    if arr.ndim == 2:
        nrows, ncols = arr.shape
        cell_strs = [[None] * ncols for _ in range(nrows)]

        # Convert each entry to a short string
        for i in range(nrows):
            for j in range(ncols):
                val = arr[i, j]
                if isinstance(val, (int, np.integer)):
                    s = f"{int(val)}"
                elif isinstance(val, (float, np.floating)):
                    s = f"{val:.4g}"
                else:
                    s = str(val)
                cell_strs[i][j] = s

        # Column widths
        col_widths = [
            max(len(cell_strs[i][j]) for i in range(nrows))
            for j in range(ncols)
        ]

        # Build lines
        lines = []
        for i in range(nrows):
            padded = [cell_strs[i][j].rjust(col_widths[j]) for j in range(ncols)]
            lines.append(indent + "[ " + "  ".join(padded) + " ]")

        return "[\n" + "\n".join(lines) + "\n]"

    # Fallback for higher-dim arrays
    return repr(arr)


def _pretty_fn(fn):
    return getattr(fn, "__qualname__", None) or getattr(fn, "__name__", None) or repr(fn)


def _normalize_weight_sets(val):
    """
    Accepts:
      - None â†’ DEFAULT_WEIGHT_SETS["base"]
      - str  â†’ key into DEFAULT_WEIGHT_SETS
      - 2x2 sequence of strings, e.g. [["cos","sin"], ["minus_sin","cos"]]
    Returns a validated 2x2 list of strings.
    """
    if val is None:
        return [w[:] for w in DEFAULT_WEIGHT_SETS["base"]]

    if isinstance(val, str):
        try:
            return [w[:] for w in DEFAULT_WEIGHT_SETS[val]]
        except KeyError as e:
            raise ValueError(
                f"Unknown weights preset {val!r}. "
                f"Available: {list(DEFAULT_WEIGHT_SETS.keys())}"
            ) from e

    # User provided a sequence â€“ validate it's 2x2 strings
    try:
        if (len(val) == 2 and all(len(p) == 2 for p in val) and
            all(isinstance(x, str) for p in val for x in p)):
            return [[str(val[0][0]), str(val[0][1])],
                    [str(val[1][0]), str(val[1][1])]]
    except Exception:
        pass

    raise TypeError(
        "weights must be None, a preset name (str), or a 2x2 sequence of strings "
        'like [["cos","sin"], ["minus_sin","cos"]].'
    )


class measureMacro:

    # --- Pulse / op binding ---------------------------------------------------
    _pulse_op: PulseOp | None = None
    _active_op: str | None = None

    # --- Demod / outputs config ----------------------------------------------
    _demod_weight_sets = [["cos", "sin"], ["minus_sin", "cos"]]
    _demod_weight_len = None

    _demod_fn       = dual_demod.full
    _demod_args     = ()
    _demod_kwargs   = {}

    _per_fn         = None
    _per_args       = None
    _per_kwargs     = None

    _gain           = None  # None => no scaling

    _state_stack: list[tuple[str, dict]] = []
    _state_index: dict[str, int] = {}   # state_id -> index in _state_stack
    _state_counter: int = 0             # for auto-generated IDs

    _drive_frequency = None
    _save_raw_data = False
    
    _ro_disc_params = {
        "threshold": None,
        "angle": None,
        "fidelity": None,
        "rot_mu_g": None,
        "unrot_mu_g": None,
        "sigma_g": None,
        "rot_mu_e": None,
        "unrot_mu_e": None,
        "sigma_e": None,
        "norm_params": {},
    }

    _ro_quality_params = {
        "alpha": None,
        "beta":  None,
        "F":     None,
        "Q":     None,
        "V":     None,
        "t01":   None,
        "t10":   None,
        "eta_g": None,
        "eta_e": None,
        "confusion_matrix": None,
        "transition_matrix": None,
        "affine_n": None,  # Dict keyed by n: {"0": {"A": 3x3, "b": 3x1}, "1": {...}, ...}
    }

    _post_select_config: PostSelectionConfig | None = None
    
    @classmethod
    def compute_Pe_from_S(cls, S):
        mu_g = cls._ro_disc_params.get("rot_mu_g", 0.0 + 0.0j)
        mu_e = cls._ro_disc_params.get("rot_mu_e", 1.0 + 0.0j)

        S = np.asarray(S)  # scalar -> 0-d array, array stays array

        d = mu_e - mu_g
        denom = float(np.abs(d) ** 2)  # |d|^2, real scalar

        if denom == 0.0:
            out = np.full(S.shape, np.nan, dtype=float)
            return float(out) if out.shape == () else out

        pe = np.real((S - mu_g) * np.conj(d)) / denom  # projection ratio, float array

        # optional: keep in [0,1]
        # pe = np.clip(pe, 0.0, 1.0)

        return float(pe) if pe.shape == () else pe
    
    # ---------------------------------------------------------------------- #
    #  Core properties
    # ---------------------------------------------------------------------- #
    @classmethod
    def active_element(cls) -> str:
        """
        Element name used for measure().

        Requires: a PulseOp has been bound with element.
        """
        if cls._pulse_op and cls._pulse_op.element:
            return cls._pulse_op.element
        raise RuntimeError("measureMacro: no PulseOp bound with element; call set_pulse_op(...) first.")

    @classmethod
    def active_op(cls) -> str:
        """
        QUA operation handle used in measure().

        Resolution:
          1) explicit _active_op if set
          2) PulseOp.op
          3) PulseOp.pulse
        """
        if cls._active_op:
            return cls._active_op
        if cls._pulse_op:
            if cls._pulse_op.op:
                return cls._pulse_op.op
            if cls._pulse_op.pulse:
                return cls._pulse_op.pulse
        raise RuntimeError(
            "measureMacro: no active_op configured; call set_pulse_op(...) or set_active_op(...)."
        )

    @classmethod
    def active_length(cls) -> int | None:
        """
        Length of the readout pulse in ns if known.
        """
        if cls._pulse_op and cls._pulse_op.length is not None:
            return int(cls._pulse_op.length)
        return None

    # ---------------------------------------------------------------------- #
    #  PulseOp binding
    # ---------------------------------------------------------------------- #

    @classmethod
    def set_pulse_op(
        cls,
        pulse_op: PulseOp,
        *,
        active_op: str | None = None,
        weights: str | list | tuple | None = None,
        weight_len: int | None = None,
    ):
        """
        Bind a measurement PulseOp to measureMacro.

        Args
        ----
        pulse_op : PulseOp
            Measurement pulse to bind (its element will be used as the readout element).
        active_op : str | None, optional
            Override the QUA operation handle; otherwise derive from PulseOp.
        weights : None | str | 2x2 sequence[str], optional
            - None â†’ use DEFAULT_WEIGHT_SETS["base"]
            - str  â†’ name of a preset in DEFAULT_WEIGHT_SETS
            - 2x2  â†’ explicit [[I_w, Q_w], [I_w2, Q_w2]]
        weight_len : int | None, optional
            If provided, sets cls._demod_weight_len.

        Side effects
        ------------
        Updates:
        - _pulse_op
        - _active_op
        - _demod_weight_sets
        - _demod_weight_len (if weight_len is not None)
        """
        if pulse_op is None:
            raise ValueError("set_pulse_op: 'pulse_op' is None.")

        if getattr(pulse_op, "type", None) and pulse_op.type != "measurement":
            logger.warning(
                "set_pulse_op: PulseOp %r has type=%r (expected 'measurement'); using anyway.",
                pulse_op.pulse, pulse_op.type
            )

        cls._pulse_op = pulse_op
        cls._active_op = active_op or pulse_op.op or pulse_op.pulse or None
        if cls._active_op is None:
            raise RuntimeError(
                "set_pulse_op: No active_op resolved; please supply 'active_op' "
                "or ensure PulseOp has op/pulse."
            )

        # Normalize and set demod weights
        cls._demod_weight_sets = _normalize_weight_sets(weights)

        # Optional demod length override
        if weight_len is not None:
            if not isinstance(weight_len, int) or weight_len <= 0:
                raise ValueError("set_pulse_op: 'weight_len' must be a positive integer.")
            cls._demod_weight_len = weight_len

    @classmethod
    def set_active_op(cls, op_handle: str):
        """
        Explicitly set the op handle used in measure().
        """
        if not op_handle:
            raise ValueError("set_active_op: op_handle must be non-empty.")
        cls._active_op = op_handle

    # ---------------------------------------------------------------------- #
    #  Post-selection config storage
    # ---------------------------------------------------------------------- #
    @classmethod
    def set_post_select_config(cls, cfg: PostSelectionConfig | None, *, copy: bool = True) -> None:
        if cfg is None:
            cls._post_select_config = None
            return
        if not isinstance(cfg, PostSelectionConfig):
            if isinstance(cfg, dict):
                cfg = PostSelectionConfig.from_dict(cfg)
            elif hasattr(cfg, "to_dict") and callable(getattr(cfg, "to_dict")):
                cfg = PostSelectionConfig.from_dict(cfg.to_dict())
            else:
                raise TypeError(
                    f"set_post_select_config: expected PostSelectionConfig-compatible object or None, got {type(cfg)}"
                )
            if cfg is None:
                cls._post_select_config = None
                return
        cls._post_select_config = cfg.copy() if copy else cfg

    @classmethod
    def get_post_select_config(cls, *, copy: bool = True) -> PostSelectionConfig | None:
        if cls._post_select_config is None:
            return None
        return cls._post_select_config.copy() if copy else cls._post_select_config

    @classmethod
    def clear_post_select_config(cls) -> None:
        cls._post_select_config = None


    # ---------------------------------------------------------------------- #
    #  Readout calibration accessors
    # ---------------------------------------------------------------------- #
    @classmethod
    def get_readout_calibration(cls):
        merged = {}
        merged.update(cls._ro_disc_params)
        merged.update(cls._ro_quality_params)
        return merged

    @classmethod
    def _update_readout_discrimination(cls, out: dict):
        dp = cls._ro_disc_params

        # numeric scalars (robust defaults)
        dp["threshold"] = float(out.get("threshold", dp.get("threshold", 0.0)))
        dp["angle"]     = float(out.get("angle",     dp.get("angle", 0.0)))
        dp["fidelity"]  = float(out.get("fidelity",  dp.get("fidelity", 0.0)))

        # complex centers
        dp["rot_mu_g"]   = out.get("rot_mu_g",   dp.get("rot_mu_g",   0.0 + 0.0j))
        dp["rot_mu_e"]   = out.get("rot_mu_e",   dp.get("rot_mu_e",   0.0 + 0.0j))   # <-- MISSING BEFORE
        dp["unrot_mu_g"] = out.get("unrot_mu_g", dp.get("unrot_mu_g", 0.0 + 0.0j))
        dp["unrot_mu_e"] = out.get("unrot_mu_e", dp.get("unrot_mu_e", 0.0 + 0.0j))

        # widths (Iâ€™d cast to float for consistency)
        dp["sigma_g"] = float(out.get("sigma_g", dp.get("sigma_g", 0.0)))
        dp["sigma_e"] = float(out.get("sigma_e", dp.get("sigma_e", 0.0)))

        # dict, no float-cast
        dp["norm_params"] = out.get("norm_params", dp.get("norm_params", {}))


    @classmethod
    def _update_readout_quality(cls, out: dict):
        alpha = out.get("a0", None)
        beta  = out.get("a1", None)
        if alpha is not None:
            cls._ro_quality_params["alpha"] = float(alpha)
        if beta is not None:
            cls._ro_quality_params["beta"]  = float(beta)
        if "confusion_matrix" in out:
            cls._ro_quality_params["confusion_matrix"] = out["confusion_matrix"].to_numpy()
        if "transition_matrix" in out:
            cls._ro_quality_params["transition_matrix"] = out["transition_matrix"].to_numpy()
        if "F" in out:
            cls._ro_quality_params["F"] = float(out["F"])
        if "Q" in out:
            cls._ro_quality_params["Q"] = float(out["Q"])
        if "V" in out:
            cls._ro_quality_params["V"] = float(out["V"])
        
        # Handle affine_n: dictionary keyed by n with A and b for each
        if "A_n" in out and "b_n" in out:
            A_n = out["A_n"]
            b_n = out["b_n"]
            
            # Assume both are lists of same length
            if isinstance(A_n, list) and isinstance(b_n, list):
                if len(A_n) == len(b_n):
                    affine_dict = {}
                    for n, (A, b) in enumerate(zip(A_n, b_n)):
                        affine_dict[str(n)] = {
                            "A": np.asarray(A),
                            "b": np.asarray(b)
                        }
                    cls._ro_quality_params["affine_n"] = affine_dict
        elif "affine_n" in out:
            # Direct dictionary format
            affine_n = out["affine_n"]
            if isinstance(affine_n, dict):
                affine_dict = {}
                for n, params in affine_n.items():
                    affine_dict[str(n)] = {
                        "A": np.asarray(params["A"]),
                        "b": np.asarray(params["b"])
                    }
                cls._ro_quality_params["affine_n"] = affine_dict

    """ 
        # Update eta parameters from butterfly measurement
        if "eta_g" in out:
            cls._ro_quality_params["eta_g"] = float(out["eta_g"])
        if "eta_e" in out:
            cls._ro_quality_params["eta_e"] = float(out["eta_e"])
        if "eta_fp_e_given_g" in out:
            cls._ro_quality_params["eta_fp_e_given_g"] = float(out["eta_fp_e_given_g"])
        if "eta_fp_g_given_e" in out:
            cls._ro_quality_params["eta_fp_g_given_e"] = float(out["eta_fp_g_given_e"])
        if "eta_unknown_g" in out:
            cls._ro_quality_params["eta_unknown_g"] = float(out["eta_unknown_g"])
        if "eta_unknown_e" in out:
            cls._ro_quality_params["eta_unknown_e"] = float(out["eta_unknown_e"])
        if "eta_acc_gcore_rate" in out:
            # Convert to list for JSON serialization
            val = out["eta_acc_gcore_rate"]
            cls._ro_quality_params["eta_acc_gcore_rate"] = val.tolist() if hasattr(val, 'tolist') else list(val)
        if "eta_acc_ecore_rate" in out:
            # Convert to list for JSON serialization
            val = out["eta_acc_ecore_rate"]
            cls._ro_quality_params["eta_acc_ecore_rate"] = val.tolist() if hasattr(val, 'tolist') else list(val)
        
        # Update p_S_measured from butterfly measurement
        if "p_S_measured_given_g" in out:
            cls._ro_quality_params["p_S_measured_given_g"] = float(out["p_S_measured_given_g"])
        if "p_S_measured_given_e" in out:
            cls._ro_quality_params["p_S_measured_given_e"] = float(out["p_S_measured_given_e"])
        
        # Update posterior models from butterfly measurement
        if "posterior_model_1d" in out:
            cls._ro_quality_params["posterior_model_1d"] = out["posterior_model_1d"]
        if "posterior_model_2d" in out:
            cls._ro_quality_params["posterior_model_2d"] = out["posterior_model_2d"]

    """


    @classmethod
    def compute_posterior_weights(
        cls,
        S,
        model_type: str = "1d",
        pi_e: float = 0.5,
        require_finite: bool = True,
    ):
        """
        Compute posterior weights (w_g, w_e) from signal data using simple Gaussian model.

        Uses parameters from _ro_disc_params (rot_mu_g, rot_mu_e, sigma_g, sigma_e).

        Parameters
        ----------
        S : array-like
            Complex signal data (IQ measurements).
        model_type : str, optional
            Which model to use: "1d" or "2d" (default: "1d").
        pi_e : float, optional
            Prior probability of excited state (default: 0.5).
        require_finite : bool, optional
            If True, non-finite values produce NaN weights (default: True).

        Returns
        -------
        w_g : ndarray
            Posterior probability of ground state P(g|S).
        w_e : ndarray
            Posterior probability of excited state P(e|S).

        Raises
        ------
        ValueError
            If required parameters are not available in _ro_disc_params.
        """
        # Validate pi_e
        pi_e = float(pi_e)
        if not (0.0 < pi_e < 1.0):
            raise ValueError(f"pi_e must be in (0,1), got {pi_e}")
        pi_g = 1.0 - pi_e

        # Get parameters from _ro_disc_params
        rot_mu_g = cls._ro_disc_params.get("rot_mu_g")
        rot_mu_e = cls._ro_disc_params.get("rot_mu_e")
        sigma_g = cls._ro_disc_params.get("sigma_g")
        sigma_e = cls._ro_disc_params.get("sigma_e")

        if rot_mu_g is None or rot_mu_e is None:
            raise ValueError(
                "rot_mu_g and rot_mu_e must be set in _ro_disc_params. "
                "Run readout discrimination calibration first."
            )
        if sigma_g is None or sigma_e is None:
            raise ValueError(
                "sigma_g and sigma_e must be set in _ro_disc_params. "
                "Run readout discrimination calibration first."
            )

        Ig = float(np.real(rot_mu_g))
        Ie = float(np.real(rot_mu_e))
        Qg = float(np.imag(rot_mu_g))
        Qe = float(np.imag(rot_mu_e))
        sigma_g = float(sigma_g)
        sigma_e = float(sigma_e)

        if not (np.isfinite(sigma_g) and sigma_g > 0):
            raise ValueError(f"Invalid sigma_g: {sigma_g}")
        if not (np.isfinite(sigma_e) and sigma_e > 0):
            raise ValueError(f"Invalid sigma_e: {sigma_e}")

        # Prepare signal data
        S = np.asarray(S)
        if S.ndim == 0:
            S = S.reshape(1)
        if not np.iscomplexobj(S):
            S = S.astype(np.complex128, copy=False)

        I = np.real(S)
        Q = np.imag(S)

        # Validate model_type
        model_type = str(model_type).lower()
        if model_type not in ("1d", "2d"):
            raise ValueError(f"model_type must be '1d' or '2d', got {model_type!r}")

        # Check finite values
        if require_finite:
            finite = np.isfinite(I) if model_type == "1d" else (np.isfinite(I) & np.isfinite(Q))
        else:
            finite = np.ones(I.shape, dtype=bool)

        # Helper function for stable sigmoid
        def _stable_sigmoid(x):
            x = np.clip(x, -60.0, 60.0)
            return 1.0 / (1.0 + np.exp(-x))

        # Compute LLR = log p(S|e) - log p(S|g) + log(pi_e/pi_g)
        if model_type == "2d":
            # 2D Gaussian model (assumes isotropic circular spreads)
            dg2 = (I - Ig) ** 2 + (Q - Qg) ** 2
            de2 = (I - Ie) ** 2 + (Q - Qe) ** 2
            sg2 = sigma_g ** 2
            se2 = sigma_e ** 2

            llr = (
                -de2 / (2.0 * se2) + dg2 / (2.0 * sg2)
                - np.log(se2 / sg2)
                + np.log(pi_e / pi_g)
            )
        else:
            # 1D Gaussian model on rotated I-axis (consistent with 1D GMM calibration)
            zg2 = ((I - Ig) / sigma_g) ** 2
            ze2 = ((I - Ie) / sigma_e) ** 2
            llr = (
                -0.5 * ze2 + 0.5 * zg2
                - np.log(sigma_e / sigma_g)
                + np.log(pi_e / pi_g)
            )

        w_e = _stable_sigmoid(llr)
        w_e = np.where(finite, w_e, np.nan)
        w_g = 1.0 - w_e
        return w_g, w_e

    @classmethod
    def compute_posterior_state_weight(
        cls,
        S,
        target_state: str = "g",
        model_type: str = "1d",
        pi_e: float = 0.5,
        require_finite: bool = True,
    ):
        """
        Convenience wrapper: compute posterior weight for a single target state.

        Parameters
        ----------
        S : array-like
            Complex signal data (IQ measurements).
        target_state : str, optional
            Target state: "g" for ground or "e" for excited (default: "g").
        model_type : str, optional
            Which model to use: "1d" or "2d" (default: "1d").
        pi_e : float, optional
            Prior probability of excited state (default: 0.5).
        require_finite : bool, optional
            If True, non-finite values produce NaN weights (default: True).

        Returns
        -------
        w : ndarray
            Posterior probability P(target_state|S).

        Raises
        ------
        ValueError
            If target_state is invalid or required parameters are missing.
        """
        target_state = str(target_state).lower()
        if target_state not in ("g", "e"):
            raise ValueError(f"target_state must be 'g' or 'e', got {target_state!r}")

        w_g, w_e = cls.compute_posterior_weights(
            S, model_type=model_type, pi_e=pi_e, require_finite=require_finite
        )
        return w_e if target_state == "e" else w_g

    # ---------------------------------------------------------------------- #
    #  Snapshot / restore (PulseOp-based)
    # ---------------------------------------------------------------------- #
    @classmethod
    def _snapshot(cls):
        return {
            "pulse_op":         cls._pulse_op.to_dict() if cls._pulse_op else None,
            "active_op":        cls._active_op,
            "weights":          [(w if isinstance(w, str) else list(w)) for w in cls._demod_weight_sets],
            "demod_fn":         cls._demod_fn,
            "demod_args":       cls._demod_args,
            "demod_kwargs":     dict(cls._demod_kwargs) if isinstance(cls._demod_kwargs, dict) else cls._demod_kwargs,
            "per_fn":           list(cls._per_fn) if cls._per_fn else None,
            "per_args":         [tuple(a) for a in cls._per_args] if cls._per_args else None,
            "per_kwargs":       [dict(k) for k in cls._per_kwargs] if cls._per_kwargs else None,
            "gain":             cls._gain,
            "demod_weight_len": cls._demod_weight_len,
            "ro_disc_params":    dict(cls._ro_disc_params),
            "ro_quality_params": dict(cls._ro_quality_params),
            "drive_frequency":   cls._drive_frequency,
            "post_select_config": (cls._post_select_config.to_dict() if cls._post_select_config else None),

        }

    @classmethod
    def _restore_from_snapshot(cls, s: dict):
        """
        Internal: load a snapshot dict into the class variables.
        """
        pulse_op_data = s.get("pulse_op")
        cls._pulse_op = PulseOp(**pulse_op_data) if pulse_op_data is not None else None
        cls._active_op = s.get("active_op")

        cls._demod_weight_sets = s["weights"]
        cls._demod_fn          = s["demod_fn"]
        cls._demod_args        = s["demod_args"]
        cls._demod_kwargs      = s["demod_kwargs"]
        cls._per_fn            = s.get("per_fn")
        cls._per_args          = s.get("per_args")
        cls._per_kwargs        = s.get("per_kwargs")
        cls._gain              = s["gain"]
        cls._demod_weight_len  = s.get("demod_weight_len", None)

        # Discrimination / quality params â€” keep backward-compat logic
        cls._ro_disc_params    = dict(s.get("ro_disc_params", {}))
        cls._ro_quality_params = dict(
            s.get("ro_quality_params", s.get("ro_quality_metrics", {}))
        )

        _df = s.get("drive_frequency", None)
        cls._drive_frequency   = None if _df is None else float(_df)
        cls._post_select_config = PostSelectionConfig.from_dict(s.get("post_select_config", None))


    @classmethod
    def _rebuild_state_index(cls):
        cls._state_index.clear()
        for i, (sid, _) in enumerate(cls._state_stack):
            cls._state_index[sid] = i

    @classmethod
    def push_settings(cls, state_id: str | int | None = None) -> str:
        """
        Save current settings on the internal stack.

        Parameters
        ----------
        state_id : str | int | None
            Optional identifier. If None, an auto-incrementing integer
            (as a string) is used. If given, must be unique.

        Returns
        -------
        state_id : str
            The identifier actually used for this saved state.
        """
        # Normalize / auto-generate ID
        if state_id is None:
            cls._state_counter += 1
            state_id = str(cls._state_counter)
        else:
            state_id = str(state_id)

        if state_id in cls._state_index:
            raise ValueError(
                f"measureMacro.push_settings: state_id {state_id!r} already exists"
            )

        snap = cls._snapshot()
        cls._state_stack.append((state_id, snap))
        cls._state_index[state_id] = len(cls._state_stack) - 1
        return state_id

    @classmethod
    def restore_settings(cls, state_id: str | int | None = None):
        """
        Restore a previously saved state.

        - If state_id is None: behaves like a stack pop (last pushed state).
        - If state_id is given: restores that specific snapshot and removes it
          from the stack.
        """
        if not cls._state_stack:
            raise RuntimeError("measureMacro.restore_settings(): no saved state to restore")

        if state_id is None:
            # Classic stack behavior
            _, snap = cls._state_stack.pop()
        else:
            state_id = str(state_id)
            try:
                idx = cls._state_index[state_id]
            except KeyError:
                raise KeyError(
                    f"measureMacro.restore_settings: unknown state_id {state_id!r}"
                )
            _, snap = cls._state_stack.pop(idx)

        # Rebuild index after removing an entry
        cls._rebuild_state_index()
        cls._restore_from_snapshot(snap)

    @classmethod
    def retrieve_state(cls, state_id: str | int):
        """
        Convenience alias for restore_settings(state_id=...).
        """
        return cls.restore_settings(state_id=state_id)

    @classmethod
    def export_readout_calibration(cls) -> dict:
        return {
            "discrimination": dict(cls._ro_disc_params),
            "butterfly":      dict(cls._ro_quality_params),
        }

    # ---------------------------------------------------------------------- #
    #  JSON save/load (PulseOp-based; backward compatible)
    # ---------------------------------------------------------------------- #
    @staticmethod
    def _kde_to_dict(kde_obj):
        """
        Convert a scipy.stats.gaussian_kde object to a serializable dict.
        
        Parameters
        ----------
        kde_obj : scipy.stats.gaussian_kde
            The KDE object to serialize.
            
        Returns
        -------
        dict
            A dictionary containing the dataset, covariance, and bandwidth method.
        """
        if kde_obj is None:
            return None
            
        include_dataset = bool(getattr(measureMacro, "_save_raw_data", False))
        out = {
            "covariance": kde_obj.covariance.tolist(),
            "bw_method": kde_obj.covariance_factor(),
            "n_samples": int(kde_obj.dataset.shape[1]),
            "dimension": int(kde_obj.dataset.shape[0]),
            "serialization": "summary_only",
        }
        if include_dataset:
            out["dataset"] = kde_obj.dataset.tolist()
            out["serialization"] = "full"
        return out
    
    @staticmethod
    def _dict_to_kde(kde_dict):
        """
        Reconstruct a scipy.stats.gaussian_kde object from a serialized dict.
        
        Parameters
        ----------
        kde_dict : dict
            Dictionary containing dataset, covariance, and bw_method.
            
        Returns
        -------
        scipy.stats.gaussian_kde
            The reconstructed KDE object.
        """
        if kde_dict is None:
            return None

        if "dataset" not in kde_dict:
            return None
            
        from scipy.stats import gaussian_kde
        
        dataset = np.array(kde_dict["dataset"])
        
        # Reconstruct the KDE - we need to set the covariance manually
        kde = gaussian_kde(dataset)
        kde.set_bandwidth(bw_method=kde_dict["bw_method"])
        
        return kde
    
    @classmethod
    def _serialize_posterior_model(cls, model):
        """
        Serialize a posterior model dict by converting KDE objects to dicts.
        Grid-based models (kde_grid, B_2d_grid) are already serializable.
        
        Parameters
        ----------
        model : dict or None
            The posterior model dictionary.
            
        Returns
        -------
        dict or None
            Serialized model with KDE objects converted to dicts.
        """
        if model is None:
            return None
            
        model = dict(model)  # shallow copy
        
        # Grid-based models are already serializable (numpy arrays will be converted to lists by JSON encoder)
        if model.get("method") == "kde_grid" or model.get("type") == "B_2d_grid":
            return model
        
        # Convert KDE objects if present (legacy models)
        if "kde_g" in model:
            model["kde_g"] = cls._kde_to_dict(model["kde_g"])
        if "kde_e" in model:
            model["kde_e"] = cls._kde_to_dict(model["kde_e"])
            
        return model
    
    @classmethod
    def _deserialize_posterior_model(cls, model):
        """
        Deserialize a posterior model dict by reconstructing KDE objects.
        Grid-based models need arrays converted back from lists.
        
        Parameters
        ----------
        model : dict or None
            The serialized posterior model dictionary.
            
        Returns
        -------
        dict or None
            Model with KDE dicts converted back to KDE objects.
        """
        if model is None:
            return None
            
        model = dict(model)  # shallow copy
        
        # Grid-based models: convert lists back to numpy arrays
        if model.get("method") == "kde_grid":
            model["grid_x"] = np.asarray(model["grid_x"])
            model["logpdf_g_grid"] = np.asarray(model["logpdf_g_grid"])
            model["logpdf_e_grid"] = np.asarray(model["logpdf_e_grid"])
            return model
        
        if model.get("type") == "B_2d_grid":
            model["grid_I"] = np.asarray(model["grid_I"])
            model["grid_Q"] = np.asarray(model["grid_Q"])
            model["logpdf_g_grid"] = np.asarray(model["logpdf_g_grid"])
            model["logpdf_e_grid"] = np.asarray(model["logpdf_e_grid"])
            return model
        
        # Reconstruct KDE objects if present (legacy models)
        if "kde_g" in model and isinstance(model["kde_g"], dict):
            model["kde_g"] = cls._dict_to_kde(model["kde_g"])
        if "kde_e" in model and isinstance(model["kde_e"], dict):
            model["kde_e"] = cls._dict_to_kde(model["kde_e"])
            
        return model
    
    @classmethod
    def to_json_dict(cls) -> dict:
        """
        Serialize only the current state (stack is excluded).

        Format (version 5)
        ------------------
        {
          "_version": 5,
          "current": <snapshot_json>
        }
        """
        # Current live state only
        current_snap = cls._snapshot()
        current_json = cls._snapshot_to_json(current_snap)

        return {
            "_version": 5,
            "current": current_json,
            "raw_data_persistence": bool(cls._save_raw_data),
        }

    @classmethod
    def save_json(cls, path: str) -> None:
        payload, dropped = sanitize_mapping_for_json(cls.to_json_dict())
        if dropped:
            payload["_persistence"] = {
                "raw_data_policy": "drop_shot_level_arrays",
                "dropped_fields": dropped,
            }
        with open(path, "w") as f:
            json.dump(
                payload,
                f,
                indent=2,
                default=complex_encoder,  # <-- handle complex types
            )
        logger.info("measureMacro state (current only, no stack) saved to %s", path)

    @classmethod
    def set_save_raw_data(cls, enabled: bool) -> None:
        """Enable/disable raw-data persistence for debug-only workflows."""
        cls._save_raw_data = bool(enabled)

    @classmethod
    def load_json(cls, path: str) -> None:
        with open(path, "r") as f:
            s = json.load(f, object_hook=complex_decoder)

        version = s.get("_version", 1)

        # ------------------------------
        # New-style (v5): current only
        # ------------------------------
        if version >= 5:
            # Restore current state only
            current_json = s["current"]
            current_snap = cls._snapshot_from_json(current_json)
            cls._restore_from_snapshot(current_snap)

            # Clear stack bookkeeping (stack not saved in v5)
            cls._state_stack.clear()
            cls._state_index.clear()
            cls._state_counter = 0

            logger.info("measureMacro state (current only) loaded from %s", path)
            return

        # ------------------------------
        # Old-style (v4): full stack
        # ------------------------------
        if version >= 4:
            # 1) Restore current state
            current_json = s["current"]
            current_snap = cls._snapshot_from_json(current_json)
            cls._restore_from_snapshot(current_snap)

            # 2) Restore stack
            cls._state_stack = []
            for entry in s.get("stack", []):
                state_id = str(entry["id"])
                snap_json = entry["snapshot"]
                snap = cls._snapshot_from_json(snap_json)
                cls._state_stack.append((state_id, snap))

            # 3) Rebuild index + counter
            cls._rebuild_state_index()
            cls._state_counter = int(s.get("_state_counter", len(cls._state_stack)))

            logger.info("measureMacro state (including stack) loaded from %s", path)
            return

        # -----------------------------------------
        # Legacy (v3 and earlier): single snapshot
        # -----------------------------------------
        snap = cls._snapshot_from_json(s)

        # Apply decoded snapshot to live class variables
        cls._restore_from_snapshot(snap)

        # Clear stack bookkeeping (no stack stored in old files)
        cls._state_stack.clear()
        cls._state_index.clear()
        cls._state_counter = 0

        logger.info("measureMacro legacy state (no stack) loaded from %s", path)

    @classmethod
    def _key_to_callable(cls, key: str):
        reg, _ = cls._callable_registry()
        if key not in reg:
            raise KeyError(
                f"Unknown demod function key: {key!r}. Add it to measureMacro._callable_registry()."
            )
        return reg[key]

    # ------------------------------------------------------------------ #
    #  Snapshot â‡„ JSON helpers (for current state + stack entries)
    # ------------------------------------------------------------------ #
    @classmethod
    def _snapshot_to_json(cls, snap: dict) -> dict:
        """
        Convert an in-memory snapshot (with callables, tuples, etc.)
        into a JSON-serializable dict.
        """
        s = dict(snap)  # shallow copy

        # callable â†’ key
        s["demod_fn"] = cls._callable_to_key(s["demod_fn"])
        if s.get("per_fn"):
            s["per_fn"] = [cls._callable_to_key(f) for f in s["per_fn"]]

        # tuples â†’ lists
        s["demod_args"] = list(s.get("demod_args") or ())
        if s.get("per_args") is not None:
            s["per_args"] = [list(t or ()) for t in s["per_args"]]

        # Serialize posterior models (convert KDE objects to dicts)
        if "ro_quality_params" in s and s["ro_quality_params"]:
            ro_params = dict(s["ro_quality_params"])
            if "posterior_model_1d" in ro_params:
                ro_params["posterior_model_1d"] = cls._serialize_posterior_model(
                    ro_params["posterior_model_1d"]
                )
            if "posterior_model_2d" in ro_params:
                ro_params["posterior_model_2d"] = cls._serialize_posterior_model(
                    ro_params["posterior_model_2d"]
                )
            
            # Serialize affine_n: dict of {n: {"A": ndarray, "b": ndarray}} -> JSON-serializable
            if "affine_n" in ro_params and ro_params["affine_n"] is not None:
                affine_dict = {}
                for n, params in ro_params["affine_n"].items():
                    affine_dict[str(n)] = {
                        "A": np.asarray(params["A"]).tolist(),
                        "b": np.asarray(params["b"]).tolist()
                    }
                ro_params["affine_n"] = affine_dict
            
            s["ro_quality_params"] = ro_params

        # keep other fields (weights, thresholds, ro_* params, etc.) as-is
        return s

    @classmethod
    def _snapshot_from_json(cls, s: dict) -> dict:
        """
        Build an in-memory snapshot dict from a JSON-serialized snapshot.
        This is the inverse of _snapshot_to_json (plus some defaults).
        """
        # PulseOp data is already a dict of kwargs (or None)
        pulse_op_data = s.get("pulse_op")
        active_op = s.get("active_op")
        if active_op is None and pulse_op_data is not None:
            op    = pulse_op_data.get("op")
            pulse = pulse_op_data.get("pulse")
            active_op = op or pulse or None

        # Weights
        weights = s["weights"]

        # Demodulator
        demod_fn     = cls._key_to_callable(s["demod_fn"])
        demod_args   = tuple(s.get("demod_args") or ())
        demod_kwargs = dict(s.get("demod_kwargs") or {})

        # Per-output overrides
        per_fn = s.get("per_fn")
        if per_fn is not None:
            per_fn = [cls._key_to_callable(k) for k in per_fn]

        per_args = s.get("per_args")
        if per_args is not None:
            per_args = [tuple(a or ()) for a in per_args]

        per_kwargs = s.get("per_kwargs")
        if per_kwargs is not None:
            per_kwargs = [dict(k) for k in per_kwargs]

        # Threshold / gain
        gain      = s.get("gain", None)

        # Demod weight length
        demod_weight_len = s.get("demod_weight_len", None)

        # Readout metrics
        ro_disc_params = dict(
            s.get("ro_disc_params", cls._ro_disc_params)
        )
        ro_quality_params = dict(
            s.get("ro_quality_params", s.get("ro_quality_metrics", cls._ro_quality_params))
        )
        
        # Deserialize posterior models (convert KDE dicts back to objects)
        if "posterior_model_1d" in ro_quality_params:
            ro_quality_params["posterior_model_1d"] = cls._deserialize_posterior_model(
                ro_quality_params["posterior_model_1d"]
            )
        if "posterior_model_2d" in ro_quality_params:
            ro_quality_params["posterior_model_2d"] = cls._deserialize_posterior_model(
                ro_quality_params["posterior_model_2d"]
            )
        
        # Deserialize affine_n: dict of {n: {"A": list, "b": list}} -> {n: {"A": ndarray, "b": ndarray}}
        if "affine_n" in ro_quality_params and ro_quality_params["affine_n"] is not None:
            affine_dict = {}
            for n, params in ro_quality_params["affine_n"].items():
                affine_dict[str(n)] = {
                    "A": np.asarray(params["A"]),
                    "b": np.asarray(params["b"])
                }
            ro_quality_params["affine_n"] = affine_dict

        # Drive frequency (may be absent in old JSON)
        drive_frequency = s.get("drive_frequency", None)
        
        post_select_config = s.get("post_select_config", None)

        snap = {
            "pulse_op":          pulse_op_data,
            "active_op":         active_op,
            "weights":           weights,
            "demod_fn":          demod_fn,
            "demod_args":        demod_args,
            "demod_kwargs":      demod_kwargs,
            "per_fn":            per_fn,
            "per_args":          per_args,
            "per_kwargs":        per_kwargs,
            "gain":              gain,
            "demod_weight_len":  demod_weight_len,
            "ro_disc_params":    ro_disc_params,
            "ro_quality_params": ro_quality_params,
            "drive_frequency":   drive_frequency,
            "post_select_config": post_select_config,
        }
        return snap

    # ---------------------------------------------------------------------- #
    #  Basic setters / resets (no legacy element/op)
    # ---------------------------------------------------------------------- #
    def __new__(cls, *args, **kwargs):
        raise TypeError("This class cannot be instantiated and is meant to be used as a macro")

    @classmethod
    def set_gain(cls, gain):
        cls._gain = gain

    @classmethod
    def set_demod_weight_len(cls, demod_weight_len):
        cls._demod_weight_len = demod_weight_len

    @classmethod
    def reset_pulse(cls):
        cls._pulse_op = None
        cls._active_op = None

    @classmethod
    def reset_weights(cls):
        cls.use_default_outputs()

    @classmethod
    def reset_demodulator(cls):
        cls.set_demodulator(dual_demod.full)

    @classmethod
    def reset_gain(cls):
        cls._gain = None

    @classmethod
    def reset(cls):
        cls._apply_defaults()
        cls._state_stack.clear()
        cls._state_index.clear()
        cls._state_counter = 0
        

    @classmethod
    def _apply_defaults(cls):
        """
        Apply the canonical 'default' readout settings *without* touching
        the state stack.

        Used by:
          - reset()      (plus stack clear)
          - context managers (no stack clear)
        """
        # Pulse/op
        cls.reset_pulse()

        # Weights + demodulator
        cls.reset_weights()
        cls.reset_demodulator()

        # Threshold + gain
        cls.reset_gain()

        # Clear readout metrics
        cls._ro_disc_params    = {k: None for k in cls._ro_disc_params}
        cls._ro_quality_params = {k: None for k in cls._ro_quality_params}

        # Clear drive frequency
        cls._drive_frequency   = None
        cls._post_select_config = None
    @classmethod
    def set_drive_frequency(cls, freq):
        """
        Set the drive frequency (e.g. IF) used by higher-level macros.

        freq : int | float | None
            If None, clears the drive frequency.
        """
        cls._drive_frequency = None if freq is None else float(freq)

    @classmethod
    def get_drive_frequency(cls):
        """
        Return the currently configured drive frequency (or None).
        """
        return cls._drive_frequency

    @classmethod
    def default(cls):
        cls.reset()

    @classmethod
    @contextmanager
    def using_defaults(
        cls,
        *,
        pulse_op: PulseOp | None = None,
        active_op: str | None = None,
        weight_len: int | None = None,
    ):
        """
        Temporary 'clean default' configuration:

        - Save current measureMacro state.
        - Apply defaults:
            * no bound PulseOp (unless `pulse_op` provided)
            * weights = DEFAULT_WEIGHT_SETS["base"]
            * demodulator = dual_demod.full
            * threshold = 0, gain = None
            * cleared readout metrics
        - Optionally bind `pulse_op` + `active_op` and override weight_len.
        - Restore previous state after the 'with' block.
        """
        cls.push_settings()
        try:
            # 1) Base defaults (does NOT touch _state_stack)
            cls._apply_defaults()

            # 2) Optionally bind a specific measurement PulseOp
            if pulse_op is not None:
                cls.set_pulse_op(pulse_op, active_op=active_op)

            # 3) Optionally override integration weight length, keeping same specs
            if weight_len is not None:
                cls.set_outputs(cls.get_outputs(), weight_len=weight_len)

            yield
        finally:
            cls.restore_settings()

    # ---------------------------------------------------------------------- #
    #  Outputs / demod config
    # ---------------------------------------------------------------------- #
    @classmethod
    def set_IQ_mod(cls, I_mod_weights=("cos", "sin"), Q_mod_weights=("minus_sin", "cos")):
        I = list(I_mod_weights)
        Q = list(Q_mod_weights)
        if not (len(I) == len(Q) == 2 and all(isinstance(x, str) for x in I + Q)):
            raise ValueError("set_IQ_mod: each must be a 2-tuple/list of weight names (str).")
        cls.set_outputs([I, Q])

    @classmethod
    def set_demodulator(cls, fn, *args, **kwargs):
        cls._demod_fn     = fn
        cls._demod_args   = args
        cls._demod_kwargs = dict(kwargs) if kwargs else {}
        cls._per_fn = cls._per_args = cls._per_kwargs = None

    @classmethod
    def set_per_output_demodulators(
        cls,
        fns: list,
        args_list: list | None = None,
        kwargs_list: list | None = None,
    ):
        num = len(cls._demod_weight_sets)
        if len(fns) != num:
            raise ValueError(f"set_per_output_demodulators: len(fns)={len(fns)} != outputs={num}")
        args_list   = [()] * num if args_list   is None else args_list
        kwargs_list = [{}] * num if kwargs_list is None else kwargs_list
        if len(args_list) != num or len(kwargs_list) != num:
            raise ValueError("set_per_output_demodulators: args_list/kwargs_list must match number of outputs")
        cls._per_fn     = list(fns)
        cls._per_args   = [tuple(a) for a in args_list]
        cls._per_kwargs = [dict(k) for k in kwargs_list]

    @classmethod
    def set_outputs(cls, weight_specs: list, weight_len=None):
        if not weight_specs:
            raise ValueError("set_outputs: provide at least one output")
        norm = []
        for w in weight_specs:
            if isinstance(w, str):
                norm.append(w)
            elif (
                isinstance(w, (list, tuple))
                and len(w) == 2
                and all(isinstance(x, str) for x in w)
            ):
                norm.append([w[0], w[1]])
            else:
                raise ValueError("set_outputs: each item must be a str or a 2-tuple of str")
        cls._demod_weight_sets = norm

        if weight_len is not None:
            if not isinstance(weight_len, int):
                raise TypeError("set_outputs: weight_len must be an int (or None).")
            if weight_len <= 0:
                raise ValueError("set_outputs: weight_len must be > 0.")
            cls._demod_weight_len = weight_len

    @classmethod
    def set_output_ports(cls, ports: list[str]):
        num = len(cls._demod_weight_sets)
        if len(ports) != num:
            raise ValueError(f"set_output_ports: len(ports)={len(ports)} != outputs={num}")
        cls._per_fn     = [cls._demod_fn] * num
        cls._per_args   = [tuple(cls._demod_args)] * num
        cls._per_kwargs = []
        for p in ports:
            kw = dict(cls._demod_kwargs) if isinstance(cls._demod_kwargs, dict) else {}
            if p:
                kw["element_output"] = p
            cls._per_kwargs.append(kw)

    @classmethod
    def add_output(cls, weight_spec):
        if isinstance(weight_spec, str):
            cls._demod_weight_sets.append(weight_spec)
        elif (
            isinstance(weight_spec, (list, tuple))
            and len(weight_spec) == 2
            and all(isinstance(weight_spec_i, str) for weight_spec_i in weight_spec)
        ):
            cls._demod_weight_sets.append([weight_spec[0], weight_spec[1]])
        else:
            raise ValueError("add_output: need str or 2-tuple[str,str]")

    @classmethod
    def get_outputs(cls):
        return [(w if isinstance(w, str) else list(w)) for w in cls._demod_weight_sets]

    @classmethod
    def get_gain(cls):
        return cls._gain

    @classmethod
    def get_IQ_mod(cls):
        outs = cls.get_outputs()
        if len(outs) >= 2 and all(isinstance(outs[i], list) and len(outs[i]) == 2 for i in (0, 1)):
            return outs[0], outs[1]
        raise RuntimeError("get_IQ_mod: current outputs are not two dual-weight channels.")

    @classmethod
    def get_demod_weight_len(cls):
        return cls._demod_weight_len

    # ---------------------------------------------------------------------- #
    #  Demod resolution
    # ---------------------------------------------------------------------- #
    @classmethod
    def _resolve_demod_spec(cls, k: int):
        if cls._per_fn is not None:
            fn   = cls._per_fn[k]
            args = cls._per_args[k] if cls._per_args else ()
            kw   = cls._per_kwargs[k] if cls._per_kwargs else {}
        else:
            fn   = cls._demod_fn
            args = cls._demod_args
            kw   = cls._demod_kwargs if isinstance(cls._demod_kwargs, dict) else {}
        return fn, args, dict(kw)

    @classmethod
    def use_weight_set(cls, set_name: str, weight_len: int | None = None):
        """
        Switch to a named weight set defined in DEFAULT_WEIGHT_SETS.
        """
        try:
            weight_specs = DEFAULT_WEIGHT_SETS[set_name]
        except KeyError:
            raise ValueError(f"use_weight_set: unknown set {set_name!r}")
        cls.set_outputs(weight_specs, weight_len=weight_len)

    @classmethod
    def use_default_outputs(cls, weight_len: int | None = None):
        """
        Convenience wrapper for the canonical 'base' cos/sin weights.
        """
        cls.use_weight_set("base", weight_len=weight_len)

    # ---------------------------------------------------------------------- #
    #  Introspection
    # ---------------------------------------------------------------------- #
    @classmethod
    def show_settings(cls, *, return_dict: bool = False):
        settings = cls._snapshot()
        settings["demod_fn"] = _pretty_fn(settings["demod_fn"])
        settings["demod_args"] = cls._demod_args
        settings["demod_kwargs"] = (
            dict(cls._demod_kwargs) if isinstance(cls._demod_kwargs, dict) else cls._demod_kwargs
        )
        settings["stack_depth"] = len(cls._state_stack)
        settings["ro_disc_params"] = dict(cls._ro_disc_params)
        settings["ro_quality_params"] = dict(cls._ro_quality_params)

        if return_dict:
            # For programmatic access, give the raw objects (arrays included)
            return settings

        # --- For pretty-printing, replace arrays inside the nested dicts with short placeholders
        ro_disc = settings["ro_disc_params"]
        ro_qual = settings["ro_quality_params"]

        def _strip_arrays(d: dict) -> dict:
            out = dict(d)
            for k, v in list(out.items()):
                if isinstance(v, np.ndarray):
                    out[k] = f"<ndarray shape={v.shape}>"
                elif isinstance(v, dict):
                    # Handle nested dict (e.g., affine_n)
                    if all(isinstance(vv, dict) for vv in v.values()):
                        # Check if it looks like affine_n structure
                        first_val = next(iter(v.values()), {})
                        if "A" in first_val and "b" in first_val:
                            out[k] = f"<dict with {len(v)} entries containing A and b>"
                        else:
                            out[k] = _strip_arrays(v)
                elif isinstance(v, list) and len(v) > 0 and isinstance(v[0], np.ndarray):
                    # Handle list of numpy arrays
                    shapes = [arr.shape for arr in v]
                    out[k] = f"<list of {len(v)} ndarrays, shapes={shapes}>"
            return out

        settings["ro_disc_params"] = _strip_arrays(ro_disc)
        settings["ro_quality_params"] = _strip_arrays(ro_qual)

        # 1) High-level view of everything
        pprint(settings)

        # 2) Nicely aligned matrices / arrays printed underneath
        cm = cls._ro_quality_params.get("confusion_matrix")
        tm = cls._ro_quality_params.get("transition_matrix")
        affine_n = cls._ro_quality_params.get("affine_n")

        if isinstance(cm, np.ndarray):
            print("\nro_quality_params.confusion_matrix =")
            print(_format_ndarray_for_display(cm))

        if isinstance(tm, np.ndarray):
            print("ro_quality_params.transition_matrix =")
            print(_format_ndarray_for_display(tm))

        if isinstance(affine_n, dict) and len(affine_n) > 0:
            print("\nro_quality_params.affine_n =")
            for n in sorted(affine_n.keys(), key=lambda x: int(x) if x.isdigit() else x):
                params = affine_n[n]
                print(f"  n={n}:")
                print(f"    A =")
                print(_format_ndarray_for_display(np.asarray(params["A"]), indent="      "))
                print(f"    b =")
                print(_format_ndarray_for_display(np.asarray(params["b"]), indent="      "))

    # ---------------------------------------------------------------------- #
    #  Callable registry for JSON
    # ---------------------------------------------------------------------- #
    @classmethod
    def _callable_registry(cls):
        reg = {
            "dual_demod.full":          dual_demod.full,
            "dual_demod.sliced":        dual_demod.sliced,
            "dual_demod.accumulated":   dual_demod.accumulated,
            "dual_demod.moving_window": dual_demod.moving_window,
            "demod.sliced":             demod.sliced,
        }
        rev = {v: k for k, v in reg.items()}
        return reg, rev

    @classmethod
    def _callable_to_key(cls, fn):
        reg, rev = cls._callable_registry()
        key = rev.get(fn)
        if key is None:
            return (
                getattr(fn, "__module__", "unknown")
                + "."
                + getattr(fn, "__name__", "unknown")
            )
        return key

    @classmethod
    def _build_demod(cls, weight_spec, target, k: int):
        fn, args, kw = cls._resolve_demod_spec(k)
        if isinstance(weight_spec, str):
            return fn(weight_spec, target, *args, **kw)
        else:
            iw1, iw2 = weight_spec
            return fn(iw1, iw2, *args, target, **kw)

    @classmethod
    def measure(
        cls,
        *,
        with_state: bool = False,
        gain=None,
        timestamp_stream=None,
        adc_stream=None,
        state=None,
        targets: list = None,
        axis="z",
        x90="x90",
        yn90="yn90",
        qb_el="qubit",
    ):
        num_out = len(cls._demod_weight_sets)

        if num_out < 1 and not adc_stream:
            raise RuntimeError("measure(): no outputs configured; call set_outputs/add_output")

        # targets
        if targets is not None:
            if len(targets) != num_out:
                raise ValueError(f"measure(): len(targets)={len(targets)} != outputs={num_out}")
            target_vars = list(targets)
        else:
            target_vars = [declare(fixed) for _ in range(num_out)]

        # state
        make_state = with_state or (state is not None)
        if make_state and state is None:
            state = declare(bool)

        # op handle with optional gain
        eff_gain = gain if gain is not None else cls._gain
        base_op = cls.active_op()
        pulse_handle = base_op if eff_gain is None else base_op * amp(eff_gain)

        # demod objects
        outputs = [cls._build_demod(cls._demod_weight_sets[k], target_vars[k], k) for k in range(num_out)]

        # Basis rotation for qubit tomography
        if axis == "x":
            play(yn90, qb_el)
            align(qb_el, cls.active_element())
        elif axis == "y":
            play(x90, qb_el)
            align(qb_el, cls.active_element())

        measure(
            pulse_handle,
            cls.active_element(),
            None,
            *outputs,
            timestamp_stream=timestamp_stream,
            adc_stream=adc_stream,
        )
        align()
        if make_state:
            if num_out > 0:
                assign(state, target_vars[0] > cls._ro_disc_params["threshold"])
            else:
                assign(state, False)
            return (*target_vars, state)
     




