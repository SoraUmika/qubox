from pprint import pprint
from qm.qua import *
import logging
import json
from ...pulses.manager import PulseOp  # single canonical import
from contextlib import contextmanager
from qubox_tools.algorithms.transforms import (
    complex_encoder, complex_decoder,
)
from qubox_tools.algorithms.post_selection import PostSelectionConfig
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
    
    _ro_disc_params = {
        "threshold": None,
        "angle": None,
        "fidelity": None,
        "fidelity_definition": None,
        "rot_mu_g": None,
        "unrot_mu_g": None,
        "sigma_g": None,
        "rot_mu_e": None,
        "unrot_mu_e": None,
        "sigma_e": None,
        "norm_params": {},
        "qbx_readout_state": None,
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


    # ---------------------------------------------------------------------- #
    #  Readout calibration accessors
    # ---------------------------------------------------------------------- #
    @classmethod
    def _update_readout_discrimination(cls, out: dict):
        dp = cls._ro_disc_params

        # numeric scalars (robust defaults)
        dp["threshold"] = float(out.get("threshold", dp.get("threshold", 0.0)))
        dp["angle"]     = float(out.get("angle",     dp.get("angle", 0.0)))
        dp["fidelity"]  = float(out.get("fidelity",  dp.get("fidelity", 0.0)))
        if "fidelity_definition" in out:
            dp["fidelity_definition"] = str(out.get("fidelity_definition"))

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

        # Update t01/t10 transition probabilities from butterfly measurement
        if "t01" in out:
            cls._ro_quality_params["t01"] = float(out["t01"])
        if "t10" in out:
            cls._ro_quality_params["t10"] = float(out["t10"])

        # Update eta parameters from butterfly measurement
        if "eta_g" in out:
            cls._ro_quality_params["eta_g"] = float(out["eta_g"])
        if "eta_e" in out:
            cls._ro_quality_params["eta_e"] = float(out["eta_e"])

    @classmethod
    def sync_from_calibration(cls, cal_store, element: str) -> None:
        """Populate discrimination and quality params from the canonical CalibrationStore.

        Direction: CalibrationStore → measureMacro (never reverse).
        Called by ``SessionManager.open()`` and after calibration commits.

        The ``qbx_readout_state`` hash (a runtime-only field set by
        GE Discrimination) is preserved across sync because it is not
        stored in the CalibrationStore.

        Parameters
        ----------
        cal_store : CalibrationStore
            The calibration store to read from.
        element : str
            Readout element name (e.g. ``"resonator"``).
        """
        import warnings as _warnings

        # Preserve runtime-only fields that are not in CalibrationStore
        saved_readout_state = cls._ro_disc_params.get("qbx_readout_state")

        disc = cal_store.get_discrimination(element)
        if disc is not None:
            dp = cls._ro_disc_params
            if disc.threshold is not None:
                dp["threshold"] = float(disc.threshold)
            if disc.angle is not None:
                dp["angle"] = float(disc.angle)
            if disc.fidelity is not None:
                dp["fidelity"] = float(disc.fidelity)
            if hasattr(disc, "mu_g") and disc.mu_g is not None:
                dp["rot_mu_g"] = complex(disc.mu_g[0], disc.mu_g[1]) if isinstance(disc.mu_g, (list, tuple)) else disc.mu_g
            if hasattr(disc, "mu_e") and disc.mu_e is not None:
                dp["rot_mu_e"] = complex(disc.mu_e[0], disc.mu_e[1]) if isinstance(disc.mu_e, (list, tuple)) else disc.mu_e
            if hasattr(disc, "sigma_g") and disc.sigma_g is not None:
                dp["sigma_g"] = float(disc.sigma_g)
            if hasattr(disc, "sigma_e") and disc.sigma_e is not None:
                dp["sigma_e"] = float(disc.sigma_e)

        # Restore runtime-only fields
        if saved_readout_state is not None:
            cls._ro_disc_params["qbx_readout_state"] = saved_readout_state

        quality = cal_store.get_readout_quality(element)
        if quality is not None:
            qp = cls._ro_quality_params
            for key in ("alpha", "beta", "F", "Q", "V", "t01", "t10"):
                val = getattr(quality, key, None)
                if val is not None:
                    qp[key] = float(val)
            if quality.confusion_matrix is not None:
                qp["confusion_matrix"] = np.asarray(quality.confusion_matrix)
            if hasattr(quality, "affine_n") and quality.affine_n is not None:
                qp["affine_n"] = quality.affine_n


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
            
        include_dataset = False  # raw-data persistence removed
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
            "raw_data_persistence": False,
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

        # Clear readout metrics — restore non-None defaults where applicable
        cls._ro_disc_params    = {k: ({} if k == "norm_params" else None) for k in cls._ro_disc_params}
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
    def set_demodulator(cls, fn, *args, **kwargs):
        cls._demod_fn     = fn
        cls._demod_args   = args
        cls._demod_kwargs = dict(kwargs) if kwargs else {}
        cls._per_fn = cls._per_args = cls._per_kwargs = None

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
    def get_outputs(cls):
        return [(w if isinstance(w, str) else list(w)) for w in cls._demod_weight_sets]

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
    def use_weight_set(cls, set_name: str, *, weight_len: int | None = None):
        """Switch to a named weight set defined in DEFAULT_WEIGHT_SETS."""
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


# ---------------------------------------------------------------------------
# emit_measurement() — canonical ReadoutHandle-based measurement (v2.1 API)
# ---------------------------------------------------------------------------
def emit_measurement(
    readout: "ReadoutHandle",
    *,
    targets: list | None = None,
    with_state: bool = False,
    state: "Any | None" = None,
    gain: float | None = None,
    timestamp_stream: "Any | None" = None,
    adc_stream: "Any | None" = None,
    axis: str = "z",
    x90: str = "x90",
    yn90: str = "yn90",
    qb_el: str | None = None,
) -> tuple:
    """Emit a QUA ``measure()`` statement using a ``ReadoutHandle``.

    This is the canonical replacement for ``measureMacro.measure()``.
    It is a **pure function** -- it reads from the ``ReadoutHandle`` and
    emits QUA statements.  It has no class-level state.

    Parameters
    ----------
    readout : ReadoutHandle
        Immutable readout channel configuration (from ``core.bindings``).
    targets : list, optional
        ``[I, Q]`` pre-declared QUA fixed variables to receive demodulated
        results.  If *None*, fresh variables are declared internally.
    state : QUA variable, optional
        Boolean variable for state discrimination.  If *None* and the
        ``ReadoutCal`` has a threshold, no discrimination is performed.
    gain : float, optional
        Override readout gain for this measurement.
    timestamp_stream, adc_stream
        QUA stream handles passed through to ``measure()``.

    Returns
    -------
    tuple
        ``(I, Q)`` when ``state`` is *None*; ``(I, Q, state)`` otherwise.
    """
    from ...core.bindings import ReadoutHandle as _RH

    if not isinstance(readout, _RH):
        raise TypeError(
            f"emit_measurement: expected ReadoutHandle, got {type(readout).__name__}"
        )

    element = readout.element
    op = readout.operation
    cal = readout.cal

    # Declare targets if not provided
    if targets is None:
        targets = [declare(fixed), declare(fixed)]

    # Build demod output tuple from ReadoutCal weight keys
    weight_keys = cal.weight_keys  # ("cos", "sin", "minus_sin")
    outputs = []
    if len(weight_keys) >= 2:
        # Standard dual_demod.full with cos/sin pair
        outputs.append(dual_demod.full(weight_keys[0], weight_keys[1], targets[0]))
    if len(weight_keys) >= 3 and len(targets) >= 2:
        # Second demod output (minus_sin/cos pair)
        outputs.append(dual_demod.full(weight_keys[2], weight_keys[0], targets[1]))

    # Build pulse handle with optional gain
    pulse = op if gain is None else op * amp(gain)

    # Basis rotation for qubit tomography
    if axis == "x" and qb_el is not None:
        play(yn90, qb_el)
        align(qb_el, element)
    elif axis == "y" and qb_el is not None:
        play(x90, qb_el)
        align(qb_el, element)

    measure(
        pulse,
        element,
        None,
        *outputs,
        timestamp_stream=timestamp_stream,
        adc_stream=adc_stream,
    )
    align()

    # State discrimination
    make_state = with_state or (state is not None)
    if make_state and state is None:
        state = declare(bool)
    threshold = cal.threshold if cal is not None else None
    if make_state and threshold is not None:
        I_var = targets[0]
        if cal.rotation_angle is not None:
            # Apply IQ rotation before thresholding
            Q_var = targets[1] if len(targets) > 1 else None
            if Q_var is not None:
                I_rot = declare(fixed)
                assign(
                    I_rot,
                    Math.cos2pi(cal.rotation_angle / (2.0 * 3.141592653589793)) * I_var
                    - Math.sin2pi(cal.rotation_angle / (2.0 * 3.141592653589793)) * Q_var,
                )
                assign(state, I_rot > cal.threshold)
            else:
                assign(state, I_var > cal.threshold)
        else:
            assign(state, I_var > cal.threshold)
        return (*targets, state)

    return tuple(targets)

