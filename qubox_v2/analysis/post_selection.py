from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Tuple, Union, Optional
import numpy as np

TargetState = Literal["g", "e"]


@dataclass
class PostSelectionConfig:
    """
    Offline post-selection configuration for single-shot readout data.

    This class supports two complementary workflows:

    1) Hard post-selection (legacy):
       - Return boolean masks / indices for accepted shots according to a chosen policy
         (e.g. "BLOBS", "THRESHOLD", "ZSCORE", "AFFINE", "HYSTERESIS").

    2) Soft (posterior) weighting (recommended when discrimination is imperfect):
       - Compute per-shot posterior weights w_g = P(g|S), w_e = P(e|S) using a simple
         generative likelihood model.
       - Use weights directly in estimators (preferred) or convert to a "soft" mask
         via a probability threshold.

    Posterior model notes
    ---------------------
    If your discrimination calibration uses a 1D Gaussian mixture model (GMM) on an
    optimal axis (a rotated I axis), the consistent posterior model is:

        p(I|g) = Normal(Ig, sigma_g^2)
        p(I|e) = Normal(Ie, sigma_e^2)

    which yields the Bayes posterior
        P(e|I) = 1 / (1 + exp(-LLR(I)))
    with
        LLR(I) = log p(I|e) - log p(I|g) + log(pi_e/pi_g).

    This avoids the bias introduced by hard "core" cuts (BLOBS-exclusive) that reject
    ambiguous shots and break complementarity (i.e. Pg + Pe != 1 for accepted sets).

    Data format
    -----------
    All APIs accept:
      - homogeneous numpy arrays of complex S = I + 1jQ, any shape, OR
      - a list/tuple of 1D arrays (column-wise, potentially different lengths).

    In the list-of-arrays case, methods return lists of arrays with matching lengths.
    """

    policy: str = "BLOBS"
    kwargs: dict = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Builders / utilities
    # ------------------------------------------------------------------
    @classmethod
    def from_discrimination_results(
        cls,
        output,
        blob_k_g: float = 3.0,
        blob_k_e: float | None = None,
        *,
        require_exclusive: bool = True,
        extend_halfplane: bool = True,
        extend_mode: str = "circle_edge",   # "circle_edge" or "threshold"
        extend_margin: float = 0.0,
        # Posterior defaults
        posterior_dim: str = "1d",          # "1d" (recommended) or "2d"
        pi_e_default: float = 0.5,
    ) -> "PostSelectionConfig":
        """
        Construct a BLOBS post-selection configuration from discrimination results.

        Parameters
        ----------
        output:
            Object that supports `.extract(...)` returning discrimination calibration
            values. Expected keys:
              - rot_mu_g, rot_mu_e : complex means in the rotated IQ plane (optimal axis)
              - threshold          : scalar I threshold used by some policies
              - sigma_g, sigma_e   : spreads (typically from 1D GMM on the rotated I axis)

        blob_k_g, blob_k_e:
            Multipliers for defining hard BLOBS acceptance radii:
                rg = blob_k_g * sigma_g
                re = blob_k_e * sigma_e
            Only used for hard masks/indices. If blob_k_e is None, it equals blob_k_g.

        require_exclusive:
            If True, hard BLOBS acceptance uses exclusive crescents:
                accept g: inside g circle AND not inside e circle
                accept e: inside e circle AND not inside g circle

        extend_halfplane, extend_mode, extend_margin:
            Optional hard BLOBS extension (legacy heuristic). Not needed for posterior
            weighting (posterior already smoothly saturates far from overlap).

        posterior_dim:
            Posterior likelihood dimension.
              - "1d" (recommended): uses only rotated I with sigma_g/sigma_e from 1D GMM.
              - "2d" (advanced): assumes isotropic circular 2D Gaussians in IQ with
                radial sigmas; only use if your sigma parameters truly represent radial
                spread in IQ.

        pi_e_default:
            Default prior P(e). Used only if `posterior_weights(..., pi_e=None)`.

        Returns
        -------
        PostSelectionConfig
            policy="BLOBS" with kwargs populated for both hard BLOBS and posterior API.

        Raises
        ------
        ValueError
            If sigma_g or sigma_e are invalid.
        """
        if blob_k_e is None:
            blob_k_e = blob_k_g

        rot_mu_g, rot_mu_e, threshold = output.extract("rot_mu_g", "rot_mu_e", "threshold")
        sigma_g, sigma_e = output.extract("sigma_g", "sigma_e")

        sigma_g = float(sigma_g)
        sigma_e = float(sigma_e)
        if not (np.isfinite(sigma_g) and sigma_g > 0):
            raise ValueError(f"Invalid sigma_g: {sigma_g}")
        if not (np.isfinite(sigma_e) and sigma_e > 0):
            raise ValueError(f"Invalid sigma_e: {sigma_e}")

        kwargs = {
            "Ig": float(np.real(rot_mu_g)),
            "Qg": float(np.imag(rot_mu_g)),
            "Ie": float(np.real(rot_mu_e)),
            "Qe": float(np.imag(rot_mu_e)),

            # hard BLOBS radii (squared)
            "rg2": float((blob_k_g * sigma_g) ** 2),
            "re2": float((blob_k_e * sigma_e) ** 2),

            "threshold": float(threshold),
            "require_exclusive": bool(require_exclusive),

            # hard BLOBS extension (legacy)
            "extend_halfplane": bool(extend_halfplane),
            "extend_mode": str(extend_mode),
            "extend_margin": float(extend_margin),

            # posterior parameters
            "sigma_g": sigma_g,
            "sigma_e": sigma_e,
            "posterior_dim": str(posterior_dim).lower(),
            "pi_e_default": float(pi_e_default),
            
        }
        return cls(policy="BLOBS", kwargs=kwargs)

    @classmethod
    def from_dict(cls, d: dict | None) -> Optional["PostSelectionConfig"]:
        """
        Inverse of to_dict(). Returns None if d is None/empty.
        """
        if not d:
            return None
        policy = d.get("policy", "BLOBS")
        kwargs = d.get("kwargs", {}) or {}
        if not isinstance(kwargs, dict):
            raise TypeError(f"PostSelectionConfig.from_dict: expected kwargs dict, got {type(kwargs)}")
        return cls(policy=str(policy), kwargs=dict(kwargs))

    def to_dict(self) -> dict:
        """
        JSON-safe dict representation (no numpy scalars/arrays).
        """
        def _jsonify(x):
            if isinstance(x, np.generic):
                return x.item()
            if isinstance(x, np.ndarray):
                return x.tolist()
            if isinstance(x, dict):
                return {str(k): _jsonify(v) for k, v in x.items()}
            if isinstance(x, (list, tuple)):
                return [_jsonify(v) for v in x]
            return x

        return {"policy": str(self.policy), "kwargs": _jsonify(dict(self.kwargs))}

    def update(self, **kwargs):
        """Update in-place stored parameters."""
        self.kwargs.update(kwargs)

    def copy(self) -> "PostSelectionConfig":
        """Shallow copy."""
        return PostSelectionConfig(policy=str(self.policy), kwargs=dict(self.kwargs))

    # ------------------------------------------------------------------
    # Existing hard post-select methods (as you had them)
    # ------------------------------------------------------------------
    def post_select_indices(
        self,
        S: Union[np.ndarray, list, tuple],
        *,
        target_state: TargetState = "g",
        return_mask: bool = False,
        require_finite: bool = True,
        override_policy: str | None = None,
        **override_kwargs: Any,
    ) -> Union[np.ndarray, Tuple[np.ndarray, np.ndarray]]:
        """
        Apply hard post-selection on offline readout points S = I + 1j*Q.

        Returns indices of accepted points, optionally also returning the acceptance mask.

        Supports:
          - homogeneous numpy arrays
          - column-wise list/tuple of arrays with different lengths (inhomogeneous)

        Notes
        -----
        For policy="BLOBS" with require_exclusive=True, this defines "core" regions and
        rejects ambiguous points. This is useful for diagnostics but can bias population
        estimates. Prefer posterior weighting for accurate probabilities under overlap.
        """
        ts = str(target_state).lower()
        if ts not in ("g", "e"):
            raise ValueError(f"target_state must be 'g' or 'e', got {target_state!r}")

        policy = override_policy if override_policy is not None else self.policy
        policy_norm = policy.upper() if isinstance(policy, str) else "THRESHOLD"

        kw: Dict[str, Any] = dict(self.kwargs)
        kw.update(override_kwargs)

        # Detect inhomogeneous (different lengths) list-of-arrays
        is_inhomogeneous = False
        if isinstance(S, (list, tuple)):
            if len(S) > 0 and isinstance(S[0], (np.ndarray, list)):
                lengths = [len(item) for item in S]
                if len(set(lengths)) > 1:
                    is_inhomogeneous = True

        if is_inhomogeneous:
            results_idx = []
            results_mask = []
            for col in S:
                col_arr = np.asarray(col)
                if col_arr.ndim == 0:
                    col_arr = col_arr.reshape(1)
                idx, mask = self._post_select_single_array(
                    col_arr, ts, policy_norm, kw, require_finite, return_mask=True
                )
                results_idx.append(idx)
                results_mask.append(mask)

            return (results_idx, results_mask) if return_mask else results_idx

        # homogeneous case
        S = np.asarray(S)
        if S.ndim == 0:
            S = S.reshape(1)

        return self._post_select_single_array(S, ts, policy_norm, kw, require_finite, return_mask)

    def _post_select_single_array(
        self,
        S: np.ndarray,
        ts: str,
        policy_norm: str,
        kw: Dict[str, Any],
        require_finite: bool,
        return_mask: bool,
    ) -> Union[np.ndarray, Tuple[np.ndarray, np.ndarray]]:
        I = np.real(S)
        Q = np.imag(S)

        if require_finite:
            finite = np.isfinite(I) & np.isfinite(Q)
        else:
            finite = np.ones(I.shape, dtype=bool)

        thr = float(kw.get("threshold", 0.0))

        if policy_norm == "ZSCORE":
            mu_g = float(kw["mu_g"])
            sig_g = float(kw["sigma_g"])
            mu_e = float(kw["mu_e"])
            sig_e = float(kw["sigma_e"])
            k = float(kw.get("k", 2.5))
            if ts == "e":
                accept = (I - mu_e) > (k * sig_e)
            else:
                accept = (mu_g - I) > (k * sig_g)

        elif policy_norm == "AFFINE":
            a = float(kw["a"])
            b = float(kw["b"])
            c = float(kw["c"])
            margin = float(kw.get("margin", 0.0))
            v = a * I + b * Q
            if ts == "e":
                accept = v > (c + margin)
            else:
                accept = v < (c - margin)

        elif policy_norm == "HYSTERESIS":
            T_low = float(kw.get("T_low", thr))
            T_high = float(kw.get("T_high", thr))
            if not (T_low < T_high):
                raise ValueError("HYSTERESIS requires T_low < T_high")
            if ts == "e":
                accept = I >= T_high
            else:
                accept = I <= T_low

        elif policy_norm == "BLOBS":
            Ig0 = float(kw["Ig"])
            Qg0 = float(kw["Qg"])
            Ie0 = float(kw["Ie"])
            Qe0 = float(kw["Qe"])

            rg2 = float(kw["rg2"]) if "rg2" in kw else float(kw["rg"]) ** 2
            re2 = float(kw["re2"]) if "re2" in kw else float(kw["re"]) ** 2

            require_exclusive = bool(kw.get("require_exclusive", True))

            inside_g = ((I - Ig0) ** 2 + (Q - Qg0) ** 2) <= rg2
            inside_e = ((I - Ie0) ** 2 + (Q - Qe0) ** 2) <= re2

            if ts == "e":
                accept = (inside_e & (~inside_g)) if require_exclusive else inside_e
            else:
                accept = (inside_g & (~inside_e)) if require_exclusive else inside_g

            if bool(kw.get("extend_halfplane", False)):
                mode = str(kw.get("extend_mode", "circle_edge")).lower()
                margin = float(kw.get("extend_margin", 0.0))

                if mode == "threshold":
                    thr = float(kw.get("threshold", 0.0))
                    if ts == "e":
                        accept = accept | (I >= (thr + margin))
                    else:
                        accept = accept | (I <= (thr - margin))
                else:
                    rg = float(np.sqrt(rg2))
                    re = float(np.sqrt(re2))
                    if ts == "e":
                        accept = accept | (I >= (Ig0 + rg + margin))
                    else:
                        accept = accept | (I <= (Ie0 - re - margin))

        else:
            if ts == "e":
                accept = I > thr
            else:
                accept = I < thr

        mask = finite & accept
        idx = np.flatnonzero(mask)
        return (idx, mask) if return_mask else idx

    def post_select_mask(
        self,
        S: Union[np.ndarray, list, tuple],
        *,
        target_state: TargetState = "g",
        require_finite: bool = True,
        override_policy: str | None = None,
        **override_kwargs: Any,
    ) -> Union[np.ndarray, list]:
        """
        Convenience: return only the boolean acceptance mask for hard post-selection.

        For posterior-based soft selection, use:
          - posterior_state_weight(...) for weights, or
          - soft_post_select_mask(...) for a probability-threshold mask.
        """
        _, mask = self.post_select_indices(
            S,
            target_state=target_state,
            return_mask=True,
            require_finite=require_finite,
            override_policy=override_policy,
            **override_kwargs,
        )
        return mask

