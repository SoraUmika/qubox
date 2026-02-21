from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional
import hashlib
import json
import math
import pathlib
import warnings

import numpy as np
from qm import qua

from ..pulses.manager import PulseOperationManager, PulseOp, MAX_AMPLITUDE
from ..analysis.cQED_attributes import cQED_attributes
from ..programs.macros.measure import measureMacro
from ..programs.macros.sequence import sequenceMacros


# ============================================================
#  Channel helpers (Liouville superoperator, column-stacking)
# ============================================================

def unitary_to_kraus(U: np.ndarray) -> list[np.ndarray]:
    """Unitary channel has a single Kraus operator."""
    U = np.asarray(U, dtype=np.complex128)
    return [U]


def compose_kraus(K_after: list[np.ndarray], K_before: list[np.ndarray]) -> list[np.ndarray]:
    """
    Kraus set for composition:  E_after âˆ˜ E_before

    If:
      E_before(Ï) = Î£_i A_i Ï A_iâ€ 
      E_after (Ï) = Î£_j B_j Ï B_jâ€ 

    then:
      (E_afterâˆ˜E_before)(Ï) = Î£_{j,i} (B_j A_i) Ï (B_j A_i)â€ 
    """
    if len(K_after) == 0 or len(K_before) == 0:
        raise ValueError("compose_kraus: empty Kraus list")

    out: list[np.ndarray] = []
    for B in K_after:
        B = np.asarray(B, dtype=np.complex128)
        for A in K_before:
            A = np.asarray(A, dtype=np.complex128)
            out.append(B @ A)
    return out

def unitary_to_superop(U: np.ndarray) -> np.ndarray:
    """
    Liouville superoperator (column-stacking / Fortran vec):
        vec(U Ï Uâ€ ) = (U âŠ— U*) vec(Ï)
    """
    U = np.asarray(U, dtype=np.complex128)
    return np.kron(U, U.conj())


def kraus_to_superop(kraus: list[np.ndarray]) -> np.ndarray:
    """
    Liouville superoperator for Ï -> Î£_k K_k Ï K_kâ€ :
        S = Î£_k (K_k âŠ— K_k*)
    """
    if len(kraus) == 0:
        raise ValueError("kraus_to_superop: empty Kraus list")

    S = np.zeros((kraus[0].shape[0] ** 2, kraus[0].shape[0] ** 2), dtype=np.complex128)
    for K in kraus:
        K = np.asarray(K, dtype=np.complex128)
        S += np.kron(K, K.conj())
    return S


def qubit_amplitude_damping_kraus(gamma: float) -> list[np.ndarray]:
    """Qubit amplitude damping with probability gamma."""
    gamma = float(gamma)
    if not (0.0 <= gamma <= 1.0):
        raise ValueError(f"gamma must be in [0,1], got {gamma}")
    K0 = np.array([[1.0, 0.0],
                   [0.0, math.sqrt(1.0 - gamma)]], dtype=np.complex128)
    K1 = np.array([[0.0, math.sqrt(gamma)],
                   [0.0, 0.0]], dtype=np.complex128)
    return [K0, K1]


def diag_dephasing_kraus(dim: int, p: float) -> list[np.ndarray]:
    """
    Computational-basis dephasing on dim-d system:
        E(Ï) = (1-p) Ï + p * Diag(Ï)

    Kraus: sqrt(1-p) I, plus sqrt(p) |i><i| for i=0..dim-1
    """
    dim = int(dim)
    p = float(p)
    if dim <= 0:
        raise ValueError(f"dim must be positive, got {dim}")
    if not (0.0 <= p <= 1.0):
        raise ValueError(f"p must be in [0,1], got {p}")

    I = np.eye(dim, dtype=np.complex128)
    Ks = [math.sqrt(1.0 - p) * I]
    for i in range(dim):
        P = np.zeros((dim, dim), dtype=np.complex128)
        P[i, i] = 1.0
        Ks.append(math.sqrt(p) * P)
    return Ks


def embed_kraus_on_total(
    Ks_sub: list[np.ndarray],
    dim_left: int,
    dim_right: int,
    on: str,
) -> list[np.ndarray]:
    """
    Embed Kraus ops acting on a subsystem into total space H_left âŠ— H_right.

    on="left"  => K âŠ— I_right
    on="right" => I_left âŠ— K
    """
    dim_left = int(dim_left)
    dim_right = int(dim_right)
    if dim_left <= 0 or dim_right <= 0:
        raise ValueError("embed_kraus_on_total: dims must be positive")

    I_left = np.eye(dim_left, dtype=np.complex128)
    I_right = np.eye(dim_right, dtype=np.complex128)

    out: list[np.ndarray] = []
    for K in Ks_sub:
        K = np.asarray(K, dtype=np.complex128)
        if on == "left":
            out.append(np.kron(K, I_right))
        elif on == "right":
            out.append(np.kron(I_left, K))
        else:
            raise ValueError("on must be 'left' or 'right'")
    return out


# ============================================================
#  Gate helpers
# ============================================================

def _single_qubit_rotation(theta: float, phi: float) -> np.ndarray:
    """
    Ideal single-qubit rotation about equatorial axis (cos Ï†, sin Ï†, 0):
        U(Î¸, Ï†) = exp[-i Î¸/2 (cos Ï† Ïƒ_x + sin Ï† Ïƒ_y)]
    """
    theta = float(theta)
    phi = float(phi)

    cx = np.cos(theta / 2.0)
    sx = np.sin(theta / 2.0)

    nx = np.cos(phi)
    ny = np.sin(phi)

    sigma_x = np.array([[0, 1],
                        [1, 0]], dtype=np.complex128)
    sigma_y = np.array([[0, -1j],
                        [1j, 0]], dtype=np.complex128)

    n_dot_sigma = nx * sigma_x + ny * sigma_y
    return cx * np.eye(2, dtype=np.complex128) - 1j * sx * n_dot_sigma


def array_to_md5(arr: np.ndarray) -> str:
    a = np.asarray(arr, dtype=np.float64)
    header = str(a.shape).encode("utf-8")
    m = hashlib.md5()
    m.update(header)
    m.update(a.tobytes(order="C"))
    return m.hexdigest()


_GATE_REGISTRY: dict[str, type["Gate"]] = {}


# ============================================================
#  Gate base class
# ============================================================

class Gate(ABC):
    attributes: Optional[cQED_attributes] = None
    mgr: Optional[PulseOperationManager] = None

    def __init__(self, op: str, target: str):
        self.op = op
        self.target = target

    def __init_subclass__(cls, **kw):
        super().__init_subclass__(**kw)
        _GATE_REGISTRY[cls.__name__] = cls

    def __repr__(self):
        return f"<{self.__class__.__name__} op={self.op}>"

    # ----------------------------
    # Serialization
    # ----------------------------
    def to_dict(self) -> dict:
        return {
            "type": self.__class__.__name__,
            "op": self.op,
            "target": self.target,
            "params": self._serialize_params(),
        }

    @classmethod
    def from_dict(
        cls,
        d: dict,
        mgr: Optional[PulseOperationManager] = None,
        attributes: Optional[cQED_attributes] = None,
        build: bool = False,
    ) -> "Gate":
        g_cls = _GATE_REGISTRY[d["type"]]
        obj = g_cls.__new__(g_cls)

        obj.__dict__["op"] = d.get("op", d["type"])
        obj.__dict__["target"] = d.get("target", "qubit")
        obj._deserialize_params(d.get("params", {}))

        if mgr is not None or attributes is not None:
            g_cls.set_context(mgr=mgr, attributes=attributes)

        if build:
            if mgr is None:
                raise ValueError("from_dict(build=True) requires mgr (PulseOperationManager).")
            obj.build(mgr=mgr)

        return obj

    def get_kraus(
        self,
        *,
        dt: float | None = None,
        T1: float | None = None,
        T2: float | None = None,
        n_max: int = 0,
        order: str = "noise_after",
        **kwargs,
    ) -> list[np.ndarray]:
        """
        Return a Kraus list {K_m} for the channel implemented by this gate.

        NOTE: now forwards **kwargs to ideal_unitary so gates can implement
              optional frame/dressing/convention parameters.
        """
        U = self.ideal_unitary(n_max, **kwargs)   # <--- CHANGED
        U = np.asarray(U, dtype=np.complex128)

        dim_c = int(n_max) + 1
        dim_total = 2 * dim_c
        if U.shape != (dim_total, dim_total):
            raise ValueError(f"ideal_unitary returned shape {U.shape}, expected {(dim_total, dim_total)}")

        K_unitary = unitary_to_kraus(U)

        if dt is None or (T1 is None and T2 is None):
            return K_unitary

        dt = float(dt)
        if dt < 0:
            raise ValueError(f"dt must be >= 0, got {dt}")

        # --- T1 amplitude damping ---
        gamma = 0.0
        if T1 is not None:
            T1 = float(T1)
            if T1 <= 0:
                raise ValueError(f"T1 must be > 0, got {T1}")
            gamma = 1.0 - math.exp(-dt / T1)

        # --- T2 via additional pure dephasing ---
        p_phi = 0.0
        if T2 is not None:
            T2 = float(T2)
            if T2 <= 0:
                raise ValueError(f"T2 must be > 0, got {T2}")

            if T1 is None:
                # interpret T2 as pure dephasing time when T1 is unknown
                Tphi = T2
            else:
                invTphi = (1.0 / T2) - (1.0 / (2.0 * float(T1)))
                if invTphi < -1e-15:
                    raise ValueError("Unphysical for this model: T2 > 2*T1.")
                Tphi = float("inf") if invTphi <= 0 else (1.0 / invTphi)

            p_phi = 0.0 if math.isinf(Tphi) else (1.0 - math.exp(-dt / Tphi))

        # Build *noise* Kraus on qubit, embedded into (qubit âŠ— cavity)
        K_noise: list[np.ndarray] = [np.eye(dim_total, dtype=np.complex128)]

        if gamma > 0.0:
            Ks = qubit_amplitude_damping_kraus(gamma)  # 2x2
            Ks = embed_kraus_on_total(Ks, dim_left=2, dim_right=dim_c, on="left")  # (2*dim_c)x(2*dim_c)
            K_noise = compose_kraus(Ks, K_noise)

        if p_phi > 0.0:
            Ks = diag_dephasing_kraus(dim=2, p=p_phi)  # 2x2
            Ks = embed_kraus_on_total(Ks, dim_left=2, dim_right=dim_c, on="left")
            K_noise = compose_kraus(Ks, K_noise)

        # Compose noise and unitary in the requested order
        if order == "noise_after":
            # Noise âˆ˜ Unitary
            return compose_kraus(K_noise, K_unitary)
        if order == "noise_before":
            # Unitary âˆ˜ Noise
            return compose_kraus(K_unitary, K_noise)

        raise ValueError("order must be 'noise_after' or 'noise_before'")

    def get_channel(self, **kwargs) -> np.ndarray:
        """
        Convenience: return the Liouville superoperator S from the stored Kraus list.
        """
        return kraus_to_superop(self.get_kraus(**kwargs))
    
    @classmethod
    def set_context(
        cls,
        mgr: Optional[PulseOperationManager] = None,
        attributes: Optional[cQED_attributes] = None,
    ) -> None:
        if attributes is not None:
            cls.attributes = attributes
        if mgr is not None:
            cls.mgr = mgr

    # Backwards-compat alias if old code calls set_attributes
    @classmethod
    def set_attributes(cls, mgr: PulseOperationManager, attributes: cQED_attributes) -> None:
        cls.set_context(mgr=mgr, attributes=attributes)

    # ----------------------------
    # Required overrides
    # ----------------------------
    @abstractmethod
    def _serialize_params(self) -> dict: ...

    @abstractmethod
    def _deserialize_params(self, P: dict) -> None: ...

    @abstractmethod
    def play(self, *args, **kwargs) -> None: ...

    @abstractmethod
    def build(self, mgr: PulseOperationManager | None = None): ...

    @abstractmethod
    def ideal_unitary(self, n_max: int, **kwargs) -> np.ndarray: ...

    def waveforms(self) -> tuple[np.ndarray, np.ndarray, int, bool | str]:
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement waveforms(); "
            "override it to use GateArray."
        )


# ============================================================
#  Concrete gates
# ============================================================
from typing import Optional

class QubitRotation(Gate):
    """
    Global qubit rotation R(theta, phi), with optional scalar tweaks:
      - d_lambda: amplitude/rate tweak (same normalization idea as SQR)
      - d_alpha : axis/phase tweak (adds to phi)
      - d_omega : frequency tweak (digital modulation), assumed rad/s by default

    Reference template source:
      - If ref_I_x180_wf/ref_Q_x180_wf are provided: use them.
      - Otherwise: look up ref_r180_pulse from Gate.mgr.
    """

    def __init__(
        self,
        theta: float,
        phi: float,
        d_lambda: float | None = None,
        d_alpha: float | None = None,
        d_omega: float | None = None,
        *,
        ref_I_x180_wf=None,
        ref_Q_x180_wf=None,
        ref_r180_pulse: str = "ref_r180_pulse",
        target: Optional[str] = None,
        build: bool = False,
    ):
        if target is None:
            attr = type(self).attributes
            target = getattr(attr, "qb_el", "qubit") if attr is not None else "qubit"

        self.theta = float(theta)
        self.phi = float(phi)

        self.d_lambda = float(d_lambda) if d_lambda is not None else 0.0
        self.d_alpha  = float(d_alpha)  if d_alpha  is not None else 0.0
        self.d_omega  = float(d_omega)  if d_omega  is not None else 0.0

        self.ref_r180_pulse = str(ref_r180_pulse)

        # Optional reference waveform storage (may be None)
        self.ref_I_x180_wf = None if ref_I_x180_wf is None else np.asarray(ref_I_x180_wf, dtype=float)
        self.ref_Q_x180_wf = None if ref_Q_x180_wf is None else np.asarray(ref_Q_x180_wf, dtype=float)

        if (self.ref_I_x180_wf is None) ^ (self.ref_Q_x180_wf is None):
            raise ValueError("Provide both ref_I_x180_wf and ref_Q_x180_wf, or neither.")

        payload = np.array(
            [self.theta, self.phi, self.d_lambda, self.d_alpha, self.d_omega],
            dtype=float,
        )
        op_hash = array_to_md5(payload)

        super().__init__(op=f"Rotation_{op_hash}_{self.ref_r180_pulse}", target=target)

        if build:
            self.build()

    def _serialize_params(self) -> dict:
        out = {
            "theta": float(self.theta),
            "phi": float(self.phi),
            "d_lambda": float(self.d_lambda),
            "d_alpha": float(self.d_alpha),
            "d_omega": float(self.d_omega),
            "ref_r180_pulse": getattr(self, "ref_r180_pulse", "ref_r180_pulse"),
        }
        if self.ref_I_x180_wf is not None:
            out["ref_I_x180_wf"] = self.ref_I_x180_wf.tolist()
            out["ref_Q_x180_wf"] = self.ref_Q_x180_wf.tolist()
        return out

    def _deserialize_params(self, P: dict) -> None:
        self.theta = float(P["theta"])
        self.phi   = float(P["phi"])

        self.d_lambda = float(P.get("d_lambda", 0.0))
        self.d_alpha  = float(P.get("d_alpha", 0.0))
        self.d_omega  = float(P.get("d_omega", 0.0))

        self.ref_r180_pulse = str(P.get("ref_r180_pulse", "ref_r180_pulse"))

        refI = P.get("ref_I_x180_wf", None)
        refQ = P.get("ref_Q_x180_wf", None)
        if (refI is None) ^ (refQ is None):
            raise ValueError("Corrupt JSON: must contain both ref_I_x180_wf and ref_Q_x180_wf or neither.")
        if refI is None:
            self.ref_I_x180_wf = None
            self.ref_Q_x180_wf = None
        else:
            self.ref_I_x180_wf = np.asarray(refI, dtype=float)
            self.ref_Q_x180_wf = np.asarray(refQ, dtype=float)

        payload = np.array([self.theta, self.phi, self.d_lambda, self.d_alpha, self.d_omega], dtype=float)
        op_hash = array_to_md5(payload)
        self.op = f"Rotation_{op_hash}_{self.ref_r180_pulse}"

    # --------- FIX STARTS HERE ---------

    @staticmethod
    def _safe_get_marker(mgr, xid: str) -> bool | str:
        """Best-effort marker lookup; never throws."""
        try:
            base = mgr._perm.pulses.get(xid, None)
            if base is None:
                return "ON"
            return base.get("digital_marker", "ON")
        except Exception:
            return "ON"

    def _lookup_ref_iq_from_mgr(self, mgr, xid: str) -> tuple[np.ndarray, np.ndarray, bool | str]:
        """
        Robust lookup in manager: try xid, then toggle '_pulse' suffix.
        Returns I, Q, marker.
        """
        last_err = None
        candidates = [xid]
        candidates.append(xid[:-6] if xid.endswith("_pulse") else f"{xid}_pulse")

        for key in candidates:
            try:
                I, Q = mgr.get_pulse_waveforms(key)
                mk = self._safe_get_marker(mgr, key)
                return np.asarray(I, float), np.asarray(Q, float), mk
            except Exception as e:
                last_err = e

        raise RuntimeError(
            f"QubitRotation: failed to look up reference pulse '{xid}' in manager "
            f"(also tried toggling '_pulse'). Last error: {last_err}"
        )

    def _get_ref_w0_and_marker(self) -> tuple[np.ndarray, bool | str]:
        """
        Returns:
          w0 (complex template), marker

        Priority:
          1) If explicit ref_I_x180_wf/ref_Q_x180_wf provided, use them.
          2) Else, look up ref_r180_pulse from manager.
        """
        mgr = type(self).mgr

        # (1) Prefer explicit reference waveform if provided
        if self.ref_I_x180_wf is not None:
            I = np.asarray(self.ref_I_x180_wf, dtype=float)
            Q = np.asarray(self.ref_Q_x180_wf, dtype=float)
            w0 = _as_padded_complex(I, Q, pad_to_4=True)

            # marker: copy from manager if available, else default
            mk = "ON"
            if mgr is not None:
                mk = self._safe_get_marker(mgr, self.ref_r180_pulse)
            return w0, mk

        # (2) Otherwise, must use manager lookup
        if mgr is None:
            raise RuntimeError(
                "QubitRotation: no explicit ref_I_x180_wf/ref_Q_x180_wf provided and Gate.mgr is None; "
                "cannot extract reference pulse."
            )

        xid = str(self.ref_r180_pulse)
        I, Q, mk = self._lookup_ref_iq_from_mgr(mgr, xid)
        w0 = _as_padded_complex(I, Q, pad_to_4=True)
        return w0, mk

    # --------- FIX ENDS HERE ---------

    def ideal_unitary(self, n_max: int, **kwargs) -> np.ndarray:
        theta_eff = float(self.theta)
        phi_eff   = float(self.phi) + float(self.d_alpha)

        n_levels = int(n_max) + 1
        Uq = _single_qubit_rotation(theta_eff, phi_eff)
        I_cav = np.eye(n_levels, dtype=np.complex128)
        return np.kron(Uq, I_cav)

    def waveforms(self) -> tuple[np.ndarray, np.ndarray, int, bool | str]:
        att = type(self).attributes
        if att is None:
            raise RuntimeError("QubitRotation.waveforms requires Gate.attributes to be set (for dt).")

        dt = float(getattr(att, "dt_s", 1e-9))

        w0, marker = self._get_ref_w0_and_marker()
        N = len(w0)
        T = N * dt

        phi_eff = float(self.phi) + float(self.d_alpha)

        lam0 = np.pi / (2.0 * T) if T != 0.0 else 1.0
        amp_scale = (float(self.theta) / np.pi) * (1.0 + float(self.d_lambda) / lam0)

        w_axis = w0 * np.exp(-1j * phi_eff)

        omega = float(self.d_omega)
        if omega != 0.0:
            t = (np.arange(N) - (N - 1) / 2.0) * dt
            w_axis = w_axis * np.exp(1j * omega * t)

        w_new = amp_scale * w_axis
        I_new = np.real(w_new).astype(float)
        Q_new = np.imag(w_new).astype(float)

        return I_new, Q_new, N, marker

    def play(self, align_after: bool = True, **kwargs) -> None:
        qua.play(self.op, self.target)
        if align_after:
            qua.align()

    def build(self, mgr: PulseOperationManager | None = None):
        mgr = mgr or type(self).mgr
        if mgr is None:
            raise RuntimeError("QubitRotation.build requires a PulseOperationManager (mgr).")

        I_new, Q_new, length, marker = self.waveforms()

        I_name = f"{self.op}_I"
        Q_name = f"{self.op}_Q"
        mgr.add_waveform(I_name, "arbitrary", I_new.tolist(), persist=False)
        mgr.add_waveform(Q_name, "arbitrary", Q_new.tolist(), persist=False)

        pulse_name = f"{self.op}_pulse"
        p = PulseOp(
            element=self.target,
            op=self.op,
            pulse=pulse_name,
            type="control",
            length=length,
            digital_marker=marker,
            I_wf_name=I_name,
            Q_wf_name=Q_name,
            I_wf=I_new.tolist(),
            Q_wf=Q_new.tolist(),
        )
        mgr.register_pulse_op(p, override=True, persist=False)
        self._pulse_name = pulse_name
        return self.op




class Displacement(Gate):
    def __init__(
        self,
        alpha: complex,
        target: Optional[str] = None,
        build: bool = False,
    ):
        if target is None:
            attr = type(self).attributes
            target = getattr(attr, "st_el", "storage") if attr is not None else "storage"

        alpha = complex(alpha)
        r = f"{alpha.real:.3f}".replace(".", "p").replace("-", "m")
        i = f"{alpha.imag:.3f}".replace(".", "p").replace("-", "m")
        op = f"Disp_r{r}_i{i}"

        super().__init__(op=op, target=target)
        self.alpha = alpha

        if build:
            self.build()

    def _serialize_params(self) -> dict:
        return {"re": float(self.alpha.real), "im": float(self.alpha.imag)}

    def _deserialize_params(self, P: dict) -> None:
        self.alpha = complex(float(P["re"]), float(P["im"]))

    def ideal_unitary(self, n_max: int, **kwargs) -> np.ndarray:
        import scipy.linalg as la  # (keep your try/except if you want)

        n_levels = int(n_max) + 1
        a = np.zeros((n_levels, n_levels), dtype=np.complex128)
        for n in range(1, n_levels):
            a[n - 1, n] = np.sqrt(n)
        adag = a.conj().T

        K = self.alpha * adag - np.conjugate(self.alpha) * a
        U_cav = la.expm(K)
        I_q = np.eye(2, dtype=np.complex128)
        return np.kron(I_q, U_cav)

    def waveforms(self) -> tuple[np.ndarray, np.ndarray, int, bool | str]:
        mgr = type(self).mgr
        attr = type(self).attributes
        if mgr is None or attr is None:
            raise RuntimeError("Displacement.waveforms requires Gate.mgr and Gate.attributes to be set.")

        L = int(attr.b_coherent_len)
        marker = True

        I_tpl = np.ones(L, dtype=float) * float(attr.b_coherent_amp)
        Q_tpl = np.zeros(L, dtype=float)

        alpha_ref = complex(attr.b_alpha)
        if abs(alpha_ref) == 0.0:
            raise ValueError("Displacement.waveforms: reference b_alpha is 0; cannot scale.")

        ratio = self.alpha / alpha_ref
        c, s = ratio.real, ratio.imag

        I_new = c * I_tpl - s * Q_tpl
        Q_new = s * I_tpl + c * Q_tpl

        amp = np.maximum(np.abs(I_new), np.abs(Q_new))
        if np.any(amp > MAX_AMPLITUDE):
            scale = MAX_AMPLITUDE / np.max(amp)
            I_new *= scale
            Q_new *= scale
            warnings.warn(f"{self.op}: clipped to MAX_AMPLITUDE ({MAX_AMPLITUDE}).")

        return I_new, Q_new, L, marker

    def play(self, align_after: bool = True, **kwargs) -> None:
        qua.play(self.op, self.target)
        if align_after:
            qua.align(self.target)

    def build(self, mgr: PulseOperationManager | None = None):
        mgr = mgr or type(self).mgr
        if mgr is None:
            raise RuntimeError("Displacement.build requires a PulseOperationManager (mgr).")

        I_new, Q_new, L, marker = self.waveforms()

        I_name = f"{self.op}_I"
        Q_name = f"{self.op}_Q"
        mgr.add_waveform(I_name, "arbitrary", I_new.tolist(), persist=False)
        mgr.add_waveform(Q_name, "arbitrary", Q_new.tolist(), persist=False)

        pulse_name = f"{self.op}_pulse"
        pulse = PulseOp(
            element=self.target,
            op=self.op,
            pulse=pulse_name,
            type="control",
            length=L,
            digital_marker=marker,
            I_wf_name=I_name,
            Q_wf_name=Q_name,
            I_wf=I_new.tolist(),
            Q_wf=Q_new.tolist(),
        )
        mgr.register_pulse_op(pulse, override=True, persist=False)
        self._pulse_name = pulse_name
        return self.op


def _sqr_dispersive_dressing(
    *,
    n_max: int,
    chi: float,
    chi2: float,
    t: float,
    chi_is_angular: bool = False,
) -> np.ndarray:
    """
    Build U_disp = CR'(chi2*t) CR(chi*t) in the SAME basis/order as your SQR block:
      basis is |q, n> with idx(q,n) = q*n_levels + n (qubit-major)
      sigma_z eigenvalue: +1 for q=0 (g), -1 for q=1 (e)

    CR(Theta)  = exp(-i Theta/2 * sigma_z * n)
    CR'(Theta) = exp(-i Theta/2 * sigma_z * n(n-1))
    """
    n_levels = int(n_max) + 1
    dim = 2 * n_levels

    chi = float(chi)
    chi2 = float(chi2)
    t = float(t)

    # If chi is provided in Hz (cycles/s), convert to angular (rad/s)
    if not chi_is_angular:
        chi = 2.0 * np.pi * chi
        chi2 = 2.0 * np.pi * chi2

    U = np.eye(dim, dtype=np.complex128)

    # Precompute photon-number functions
    n_arr = np.arange(n_levels, dtype=float)
    n1 = n_arr                      # n
    n2 = n_arr * (n_arr - 1.0)      # n(n-1)

    # Phase factor per photon number:
    # total phase operator exponent coefficient for sigma_z:
    #   exp(-i * (t/2) * sigma_z * [chi*n + chi2*n(n-1)])
    # So for each qubit eigenvalue s in {+1,-1}:
    #   phase = exp(-i * s * (t/2) * [chi*n + chi2*n(n-1)])
    coeff = 0.5 * t * (chi * n1 + chi2 * n2)

    # q=0 (g): sigma_z = +1
    phase_g = np.exp(-1j * (+1.0) * coeff)
    # q=1 (e): sigma_z = -1
    phase_e = np.exp(-1j * (-1.0) * coeff)

    # Fill diagonal in qubit-major indexing
    for n in range(n_levels):
        U[0 * n_levels + n, 0 * n_levels + n] = phase_g[n]
        U[1 * n_levels + n, 1 * n_levels + n] = phase_e[n]

    return U


def _as_padded_complex(I, Q, *, pad_to_4: bool = True) -> np.ndarray:
    I = np.asarray(I, dtype=float)
    Q = np.asarray(Q, dtype=float)
    if I.shape != Q.shape:
        raise ValueError("I and Q must have the same shape.")
    if pad_to_4:
        pad = (-len(I)) % 4
        if pad:
            I = np.pad(I, (0, pad))
            Q = np.pad(Q, (0, pad))
    return I + 1j * Q

def _wf_hash(I, Q) -> str:
    payload = np.concatenate([np.asarray(I, float).ravel(), np.asarray(Q, float).ravel()])
    return array_to_md5(payload)


class SQR(Gate):
    """
    Photon-number-Selective Qubit Rotation (generalisation of SNAP).

    Reference template source:
      - If ref_I_x180_wf/ref_Q_x180_wf are provided: use them (X-selective Ï€ template).
      - Otherwise: look up ref_sel_x180_pulse from Gate.mgr (robustly, with '_pulse' toggling).

    Waveform:
      w_tot(t) = Î£_n  scale_n * w0(t) * exp[-i(phi_n + d_alpha_n)] * exp(+i( (Ï‰_det[n]+d_omega_n) t ))
    where w0(t) is the complex template extracted from the reference pulse.
    """

    def __init__(
        self,
        thetas,
        phis,
        *,
        ref_I_x180_wf=None,
        ref_Q_x180_wf=None,
        ref_sel_x180_pulse: str = "sel_x180_pulse",
        d_lambda=None,
        d_alpha=None,
        d_omega=None,
        marker: bool | str | None = None,
        target: Optional[str] = None,
        build: bool = False,
        fock_fqs_from_chi: bool = False,  # if True, set from_chi=True when building waveforms
    ):
        thetas = np.asarray(thetas, dtype=float)
        L = int(thetas.size)

        def _arr(x):
            if x is None:
                return np.zeros(L, dtype=float)
            x = np.asarray(x, dtype=float)
            if x.ndim == 0:
                x = np.full(L, float(x))
            if len(x) < L:
                x = np.pad(x, (0, L - len(x)))
            elif len(x) > L:
                x = x[:L]
            return x

        if np.ndim(phis) == 0:
            phis = np.full(L, float(phis), dtype=float)
        else:
            phis = _arr(phis)

        self.thetas   = thetas
        self.phis     = phis
        self.d_lambda = _arr(d_lambda)
        self.d_alpha  = _arr(d_alpha)
        self.d_omega  = _arr(d_omega)

        self.fock_fqs_from_chi = bool(fock_fqs_from_chi)

        # Reference pulse name (used if ref_I/Q not explicitly provided)
        self.ref_sel_x180_pulse = str(ref_sel_x180_pulse)

        # Optional reference waveform storage (may be None)
        self.ref_I_x180_wf = None if ref_I_x180_wf is None else np.asarray(ref_I_x180_wf, dtype=float)
        self.ref_Q_x180_wf = None if ref_Q_x180_wf is None else np.asarray(ref_Q_x180_wf, dtype=float)
        if (self.ref_I_x180_wf is None) ^ (self.ref_Q_x180_wf is None):
            raise ValueError("Provide both ref_I_x180_wf and ref_Q_x180_wf, or neither.")

        # marker override (if None, pull from mgr if possible)
        self.marker = marker

        if target is None:
            attr = type(self).attributes
            target = getattr(attr, "qb_el", "qubit") if attr is not None else "qubit"

        # op hash should include numeric params + reference identity
        payload = np.concatenate([self.thetas, self.phis, self.d_lambda, self.d_alpha, self.d_omega])

        if self.ref_I_x180_wf is not None:
            wf_h = _wf_hash(self.ref_I_x180_wf, self.ref_Q_x180_wf)
            op = f"SQR_{array_to_md5(payload)}_{wf_h}"
        else:
            op = f"SQR_{array_to_md5(payload)}_{self.ref_sel_x180_pulse}"

        super().__init__(op=op, target=target)

        if build:
            self.build()

    def _serialize_params(self):
        out = {
            "thetas":   self.thetas.tolist(),
            "phis":     self.phis.tolist(),
            "d_lambda": self.d_lambda.tolist(),
            "d_alpha":  self.d_alpha.tolist(),
            "d_omega":  self.d_omega.tolist(),
            "marker":   self.marker,
            "fock_fqs_from_chi": self.fock_fqs_from_chi,
            "ref_sel_x180_pulse": self.ref_sel_x180_pulse,
        }
        if self.ref_I_x180_wf is not None:
            out["ref_I_x180_wf"] = self.ref_I_x180_wf.tolist()
            out["ref_Q_x180_wf"] = self.ref_Q_x180_wf.tolist()
        return out

    def _deserialize_params(self, P):
        self.thetas   = np.asarray(P["thetas"], dtype=float)
        self.phis     = np.asarray(P["phis"], dtype=float)
        self.d_lambda = np.asarray(P.get("d_lambda", np.zeros_like(self.thetas)), dtype=float)
        self.d_alpha  = np.asarray(P.get("d_alpha",  np.zeros_like(self.thetas)), dtype=float)
        self.d_omega  = np.asarray(P.get("d_omega",  np.zeros_like(self.thetas)), dtype=float)

        self.marker = P.get("marker", None)
        self.fock_fqs_from_chi = bool(P.get("fock_fqs_from_chi", False))
        self.ref_sel_x180_pulse = str(P.get("ref_sel_x180_pulse", "sel_x180_pulse"))

        refI = P.get("ref_I_x180_wf", None)
        refQ = P.get("ref_Q_x180_wf", None)
        if (refI is None) ^ (refQ is None):
            raise ValueError("Corrupt JSON: must contain both ref_I_x180_wf and ref_Q_x180_wf or neither.")
        if refI is None:
            self.ref_I_x180_wf = None
            self.ref_Q_x180_wf = None
        else:
            self.ref_I_x180_wf = np.asarray(refI, dtype=float)
            self.ref_Q_x180_wf = np.asarray(refQ, dtype=float)

        payload = np.concatenate([self.thetas, self.phis, self.d_lambda, self.d_alpha, self.d_omega])
        if self.ref_I_x180_wf is not None:
            wf_h = _wf_hash(self.ref_I_x180_wf, self.ref_Q_x180_wf)
            self.op = f"SQR_{array_to_md5(payload)}_{wf_h}"
        else:
            self.op = f"SQR_{array_to_md5(payload)}_{self.ref_sel_x180_pulse}"

    # ----------------------------
    # Reference waveform lookup (robust, like QubitRotation)
    # ----------------------------

    @staticmethod
    def _safe_get_marker(mgr, xid: str) -> bool | str:
        try:
            base = mgr._perm.pulses.get(xid, None)
            if base is None:
                return "ON"
            return base.get("digital_marker", "ON")
        except Exception:
            return "ON"

    def _lookup_ref_iq_from_mgr(self, mgr, xid: str) -> tuple[np.ndarray, np.ndarray, bool | str]:
        """
        Robust lookup in manager: try xid, then toggle '_pulse' suffix.
        Returns I, Q, marker.
        """
        last_err = None
        candidates = [xid, xid[:-6] if xid.endswith("_pulse") else f"{xid}_pulse"]

        for key in candidates:
            try:
                I, Q = mgr.get_pulse_waveforms(key)
                mk = self._safe_get_marker(mgr, key)
                return np.asarray(I, float), np.asarray(Q, float), mk
            except Exception as e:
                last_err = e

        raise RuntimeError(
            f"SQR: failed to look up reference pulse '{xid}' in manager "
            f"(also tried toggling '_pulse'). Last error: {last_err}"
        )

    def _get_ref_w0_and_marker(self) -> tuple[np.ndarray, bool | str]:
        """
        Returns:
          w0 (complex template), marker

        Priority:
          1) If explicit ref_I_x180_wf/ref_Q_x180_wf provided, use them.
          2) Else, look up ref_sel_x180_pulse from manager.
        """
        mgr = type(self).mgr

        # (1) explicit reference waveforms
        if self.ref_I_x180_wf is not None:
            I = np.asarray(self.ref_I_x180_wf, dtype=float)
            Q = np.asarray(self.ref_Q_x180_wf, dtype=float)
            w0 = _as_padded_complex(I, Q, pad_to_4=True)

            # marker: explicit override if provided, else best-effort from mgr, else ON
            if self.marker is not None:
                mk = self.marker
            elif mgr is not None:
                mk = self._safe_get_marker(mgr, self.ref_sel_x180_pulse)
            else:
                mk = "ON"
            return w0, mk

        # (2) fallback: manager lookup
        if mgr is None:
            raise RuntimeError(
                "SQR: no explicit ref_I_x180_wf/ref_Q_x180_wf provided and Gate.mgr is None; "
                "cannot extract reference pulse."
            )

        xid = str(self.ref_sel_x180_pulse)
        I, Q, mk0 = self._lookup_ref_iq_from_mgr(mgr, xid)
        w0 = _as_padded_complex(I, Q, pad_to_4=True)

        mk = mk0 if (self.marker is None) else self.marker
        return w0, mk

    # ----------------------------
    # Waveform construction
    # ----------------------------

    def waveforms(self, *, from_chi: bool | None = None, d_omega_is_hz: bool = False):
        att = type(self).attributes
        if att is None:
            raise RuntimeError("SQR.waveforms requires Gate.attributes to be set.")

        dt = float(getattr(att, "dt_s", 1e-9))

        w0, marker = self._get_ref_w0_and_marker()
        N = len(w0)
        T_sel = N * dt
        t = (np.arange(N) - (N - 1) / 2.0) * dt  # centered

        max_n = min(self.thetas.size, int(getattr(att, "max_fock_level", self.thetas.size - 1)) + 1)

        # detunings Î”f_n (Hz) -> omega_det (rad/s)
        if from_chi is None:
            from_chi = not (hasattr(att, "fock_fqs") and (getattr(att, "fock_fqs") is not None))

        if hasattr(att, "get_fock_frequencies"):
            levels = np.arange(max_n, dtype=int)
            f_abs = np.asarray(att.get_fock_frequencies(levels, from_chi=from_chi), dtype=float)
            df = f_abs - float(f_abs[0])
        else:
            chi  = float(getattr(att, "st_chi"))
            chi2 = float(getattr(att, "st_chi2", 0.0))
            chi3 = float(getattr(att, "st_chi3", 0.0))
            n = np.arange(max_n, dtype=float)
            df = chi*n + chi2*n*(n-1) + chi3*n*(n-1)*(n-2)

        omega_det = 2.0 * np.pi * df  # rad/s

        lam0 = (np.pi / (2.0 * T_sel)) if T_sel != 0.0 else 1.0

        w_tot = np.zeros(N, dtype=np.complex128)

        for n in range(max_n):
            th = float(self.thetas[n])
            if (not np.isfinite(th)) or (th == 0.0):
                continue

            ph   = float(self.phis[n])
            dlam = float(self.d_lambda[n])
            dalp = float(self.d_alpha[n])
            dome = float(self.d_omega[n])

            scale = (th / np.pi) * (1.0 + dlam / lam0)
            phi_eff = ph + dalp

            if d_omega_is_hz:
                dome = 2.0 * np.pi * dome

            omega_n = omega_det[n] + dome

            # Rotate template in IQ plane by phi_eff
            w_axis = w0 * np.exp(-1j * phi_eff)

            # Digital modulation for the nth tone
            w_tot += scale * w_axis * np.exp(1j * (omega_n * t))

        I_tot = np.real(w_tot).astype(float)
        Q_tot = np.imag(w_tot).astype(float)
        return I_tot, Q_tot, N, marker

    def play(self, align_after: bool = True, **kwargs) -> None:
        qua.play(self.op, self.target)
        if align_after:
            qua.align()

    def ideal_unitary(self, n_max: int, **kwargs) -> np.ndarray:
        """
        Block-diagonal selective rotation:
          for each n <= n_max, apply qubit rotation (theta_n, phi_n) on |n>.
        """
        n_levels = int(n_max) + 1
        dim = 2 * n_levels

        U = np.eye(dim, dtype=np.complex128)
        max_n = min(n_levels, self.thetas.size)

        for n in range(max_n):
            theta_n = float(self.thetas[n])
            if (not np.isfinite(theta_n)) or (theta_n == 0.0):
                continue
            phi_n = float(self.phis[n])
            U_n = _single_qubit_rotation(theta_n, phi_n)

            U[n,             n]            = U_n[0, 0]
            U[n,             n_levels + n] = U_n[0, 1]
            U[n_levels + n,  n]            = U_n[1, 0]
            U[n_levels + n,  n_levels + n] = U_n[1, 1]

        return U

    def build(self, mgr: PulseOperationManager | None = None):
        mgr = mgr or type(self).mgr
        if mgr is None:
            raise RuntimeError("SQR.build requires a PulseOperationManager (mgr).")

        from_chi_flag = True if self.fock_fqs_from_chi else None
        I_tot, Q_tot, win_len, marker = self.waveforms(from_chi=from_chi_flag)

        I_name = f"{self.op}_I"
        Q_name = f"{self.op}_Q"
        mgr.add_waveform(I_name, "arbitrary", I_tot.tolist(), persist=False)
        mgr.add_waveform(Q_name, "arbitrary", Q_tot.tolist(), persist=False)

        pulse_name = f"{self.op}_sqr"
        pulse = PulseOp(
            element=self.target,
            op=self.op,
            pulse=pulse_name,
            type="control",
            length=win_len,
            digital_marker=marker,
            I_wf_name=I_name,
            Q_wf_name=Q_name,
            I_wf=I_tot.tolist(),
            Q_wf=Q_tot.tolist(),
        )
        mgr.register_pulse_op(pulse, override=True, persist=False)
        self._pulse_name = pulse_name
        return self.op


class SNAP(Gate):
    """
    SNAP with per-Fock corrections, built using ONLY X reference templates.

    We support two constructions:

    (A) include_unselective=False  -> two *selective* Ï€ pulses back-to-back
        Implements the user's intended mapping:
          Î¸=Ï€  -> X180 then  X180
          Î¸=0  -> X180 then -X180

    (B) include_unselective=True   -> one *selective* Ï€ pulse + one *unselective* Ï€ pulse
        We rewrite this branch so it implements the SAME Î¸-mapping as (A), by choosing the
        selective pulse axis Ï†_sel(Î¸) relative to the fixed unselective axis Ï†_uns.

        Derivation (equatorial axes):
          R(Ï€, Ï†_uns) R(Ï€, Ï†_sel) = -exp(i(Ï†_uns-Ï†_sel) Ïƒz)
        Acting on |g> gives phase  -exp(-i(Ï†_uns-Ï†_sel)).
        Choose Ï†_sel so that this phase equals exp(i Î¸) up to a global constant.

        Taking Ï†_sel = Î¸ + Ï†_uns - Ï€  gives:
          -exp(-i(Ï†_uns-Ï†_sel)) = -exp(-i(Ï†_uns-(Î¸+Ï†_uns-Ï€))) = -exp(-i(Ï€-Î¸)) = exp(iÎ¸)
        (exactly; no leftover global aside from 2Ï€ periodicity).

        So for Ï†_uns = 0 (X), Ï†_sel = Î¸ - Ï€:
          Î¸=Ï€ -> Ï†_sel=0  ( +X )
          Î¸=0 -> Ï†_sel=Ï€  ( -X )
        which matches the same rule you stated.
    """

    def __init__(
        self,
        angles,
        *,
        ref_I_sel_x180_wf=None,
        ref_Q_sel_x180_wf=None,
        d_lambda=None,
        d_alpha=None,
        d_omega=None,
        include_unselective: bool = False,
        unselective_axis: str = "x",
        ref_I_unsel_x180_wf=None,
        ref_Q_unsel_x180_wf=None,
        marker: bool | str | None = None,
        target: str = "qubit",
        op: Optional[str] = None,
        build: bool = False,
        fock_fqs_from_chi: bool = False,       # if True, set from_chi=True when building waveforms
    ):
        self.raw_angles = np.asarray(angles, dtype=float)
        L = int(self.raw_angles.size)

        def _arr(x):
            if x is None:
                return np.zeros(L, dtype=float)
            x = np.asarray(x, dtype=float)
            if x.ndim == 0:
                x = np.full(L, float(x))
            if len(x) < L:
                x = np.pad(x, (0, L - len(x)))
            elif len(x) > L:
                x = x[:L]
            return x

        self.d_lambda = _arr(d_lambda)
        self.d_alpha  = _arr(d_alpha)
        self.d_omega  = _arr(d_omega)

        self.include_unselective = bool(include_unselective)
        self.unselective_axis = str(unselective_axis).lower()
        if self.unselective_axis not in ("x", "y"):
            raise ValueError("unselective_axis must be 'x' or 'y'.")
        self.fock_fqs_from_chi = bool(fock_fqs_from_chi)

        # Optional reference waveforms (may be None)
        self.ref_I_sel_x180_wf = None if ref_I_sel_x180_wf is None else np.asarray(ref_I_sel_x180_wf, dtype=float)
        self.ref_Q_sel_x180_wf = None if ref_Q_sel_x180_wf is None else np.asarray(ref_Q_sel_x180_wf, dtype=float)
        if (self.ref_I_sel_x180_wf is None) ^ (self.ref_Q_sel_x180_wf is None):
            raise ValueError("Provide both ref_I_sel_x180_wf and ref_Q_sel_x180_wf, or neither.")

        self.ref_I_unsel_x180_wf = None if ref_I_unsel_x180_wf is None else np.asarray(ref_I_unsel_x180_wf, dtype=float)
        self.ref_Q_unsel_x180_wf = None if ref_Q_unsel_x180_wf is None else np.asarray(ref_Q_unsel_x180_wf, dtype=float)
        if (self.ref_I_unsel_x180_wf is None) ^ (self.ref_Q_unsel_x180_wf is None):
            raise ValueError("Provide both ref_I_unsel_x180_wf and ref_Q_unsel_x180_wf, or neither.")

        self.marker = marker  # if None, weâ€™ll pull marker from mgr pulse metadata

        payload = np.concatenate([
            self.raw_angles, self.d_lambda, self.d_alpha, self.d_omega,
            np.array([
                1.0 if self.include_unselective else 0.0,
                0.0 if self.unselective_axis == "x" else 1.0,
            ], dtype=float),
        ])
        h_sel = _wf_hash(self.ref_I_sel_x180_wf, self.ref_Q_sel_x180_wf)
        h_uns = _wf_hash(self.ref_I_unsel_x180_wf, self.ref_Q_unsel_x180_wf)

        sel_tag = h_sel if h_sel != "none" else "sel_x180_pulse"
        uns_tag = h_uns if (h_uns != "none") else ("x180_pulse" if self.include_unselective else "none")

        super().__init__(op=f"SNAP_{array_to_md5(payload)}_{sel_tag}_{uns_tag}", target=target)
        
        if op is not None:
            self.op = str(op)
        if build:
            self.build()

    # ------------------------- serialization -------------------------
    def _serialize_params(self) -> dict:
        out = {
            "angles": self.raw_angles.tolist(),
            "d_lambda": self.d_lambda.tolist(),
            "d_alpha": self.d_alpha.tolist(),
            "d_omega": self.d_omega.tolist(),
            "include_unselective": self.include_unselective,
            "unselective_axis": self.unselective_axis,
            "marker": self.marker,
            "fock_fqs_from_chi": self.fock_fqs_from_chi,
        }
        if self.ref_I_sel_x180_wf is not None:
            out["ref_I_sel_x180_wf"] = self.ref_I_sel_x180_wf.tolist()
            out["ref_Q_sel_x180_wf"] = self.ref_Q_sel_x180_wf.tolist()
        if self.ref_I_unsel_x180_wf is not None:
            out["ref_I_unsel_x180_wf"] = self.ref_I_unsel_x180_wf.tolist()
            out["ref_Q_unsel_x180_wf"] = self.ref_Q_unsel_x180_wf.tolist()
        return out

    def _deserialize_params(self, P: dict) -> None:
        self.raw_angles = np.asarray(P["angles"], dtype=float)
        self.d_lambda   = np.asarray(P.get("d_lambda", np.zeros_like(self.raw_angles)), dtype=float)
        self.d_alpha    = np.asarray(P.get("d_alpha",  np.zeros_like(self.raw_angles)), dtype=float)
        self.d_omega    = np.asarray(P.get("d_omega",  np.zeros_like(self.raw_angles)), dtype=float)

        self.include_unselective = bool(P.get("include_unselective", False))
        self.unselective_axis    = str(P.get("unselective_axis", "x")).lower()
        self.fock_fqs_from_chi   = bool(P.get("fock_fqs_from_chi", False))
        self.marker              = P.get("marker", None)

        refI = P.get("ref_I_sel_x180_wf", None)
        refQ = P.get("ref_Q_sel_x180_wf", None)
        if (refI is None) ^ (refQ is None):
            raise ValueError("Corrupt JSON: must contain both ref_I_sel_x180_wf and ref_Q_sel_x180_wf or neither.")
        if refI is None:
            self.ref_I_sel_x180_wf = None
            self.ref_Q_sel_x180_wf = None
        else:
            self.ref_I_sel_x180_wf = np.asarray(refI, dtype=float)
            self.ref_Q_sel_x180_wf = np.asarray(refQ, dtype=float)

        refIu = P.get("ref_I_unsel_x180_wf", None)
        refQu = P.get("ref_Q_unsel_x180_wf", None)
        if (refIu is None) ^ (refQu is None):
            raise ValueError("Corrupt JSON: must contain both ref_I_unsel_x180_wf and ref_Q_unsel_x180_wf or neither.")
        if refIu is None:
            self.ref_I_unsel_x180_wf = None
            self.ref_Q_unsel_x180_wf = None
        else:
            self.ref_I_unsel_x180_wf = np.asarray(refIu, dtype=float)
            self.ref_Q_unsel_x180_wf = np.asarray(refQu, dtype=float)

        payload = np.concatenate([
            self.raw_angles, self.d_lambda, self.d_alpha, self.d_omega,
            np.array([
                1.0 if self.include_unselective else 0.0,
                0.0 if self.unselective_axis == "x" else 1.0,
            ], dtype=float),
        ])
        h_sel = _wf_hash(self.ref_I_sel_x180_wf, self.ref_Q_sel_x180_wf)
        h_uns = _wf_hash(self.ref_I_unsel_x180_wf, self.ref_Q_unsel_x180_wf)
        sel_tag = h_sel if h_sel != "none" else "sel_x180_pulse"
        uns_tag = h_uns if (h_uns != "none") else ("x180_pulse" if self.include_unselective else "none")
        self.op = f"SNAP_{array_to_md5(payload)}_{sel_tag}_{uns_tag}"

    # ------------------------- unitary -------------------------
    def ideal_unitary(self, n_max: int) -> np.ndarray:
        n_levels = int(n_max) + 1
        dim = 2 * n_levels
        U = np.eye(dim, dtype=complex)

        max_n = min(n_levels, self.raw_angles.size)
        for n in range(max_n):
            theta_n = float(self.raw_angles[n])
            if not np.isfinite(theta_n):
                continue
            idx_en = 1 * n_levels + n
            U[idx_en, idx_en] = np.exp(1j * theta_n)
        return U

    # ------------------------- waveform fetch helpers -------------------------
    def _get_sel_w0_and_marker(self) -> tuple[np.ndarray, bool | str]:
        mgr = type(self).mgr

        if self.ref_I_sel_x180_wf is not None:
            w_sel = _as_padded_complex(self.ref_I_sel_x180_wf, self.ref_Q_sel_x180_wf, pad_to_4=True)
            mk = "ON" if (self.marker is None) else self.marker
            return w_sel, mk

        if mgr is None:
            raise RuntimeError("SNAP.waveforms: selective refs not provided and Gate.mgr is None.")

        xid = "sel_x180_pulse"
        I, Q = mgr.get_pulse_waveforms(xid)
        w_sel = _as_padded_complex(I, Q, pad_to_4=True)

        if self.marker is not None:
            mk = self.marker
        else:
            mk = mgr._perm.pulses[xid].get("digital_marker", "ON")
        return w_sel, mk

    def _get_unsel_wx(self) -> np.ndarray:
        mgr = type(self).mgr

        if self.ref_I_unsel_x180_wf is not None:
            return _as_padded_complex(self.ref_I_unsel_x180_wf, self.ref_Q_unsel_x180_wf, pad_to_4=True)

        if mgr is None:
            raise RuntimeError("SNAP.waveforms: unselective refs not provided and Gate.mgr is None.")
        I, Q = mgr.get_pulse_waveforms("x180_pulse")
        return _as_padded_complex(I, Q, pad_to_4=True)

    # ------------------------- waveforms -------------------------
    def waveforms(self, *, from_chi: bool | None = None, d_omega_is_hz: bool = False):
        att = type(self).attributes
        if att is None:
            raise RuntimeError("SNAP.waveforms requires Gate.attributes to be set.")

        dt = float(getattr(att, "dt_s", 1e-9))

        w0, marker = self._get_sel_w0_and_marker()
        N = len(w0)

        L = int(self.raw_angles.size)
        levels = np.arange(L, dtype=int)

        # detunings Î”f_n in Hz
        if from_chi is None:
            from_chi = not (hasattr(att, "fock_fqs") and (getattr(att, "fock_fqs") is not None))

        if hasattr(att, "get_fock_frequencies"):
            f_abs = np.asarray(att.get_fock_frequencies(levels, from_chi=from_chi), dtype=float)
            df = f_abs - float(f_abs[0])
        else:
            chi  = float(getattr(att, "st_chi"))
            chi2 = float(getattr(att, "st_chi2", 0.0))
            chi3 = float(getattr(att, "st_chi3", 0.0))
            n = levels.astype(float)
            df = chi*n + chi2*n*(n-1) + chi3*n*(n-1)*(n-2)

        omega_det = 2.0 * np.pi * df  # rad/s

        add_unsel = bool(self.include_unselective)
        use_two_selective = (not add_unsel)

        if use_two_selective:
            # Two selective Ï€ back-to-back (FIXED mapping):
            #   Î¸=Ï€ -> X then X
            #   Î¸=0 -> X then -X
            win = 2 * N
            T_sel = win * dt
            lam0 = (np.pi / (2.0 * T_sel)) if T_sel != 0.0 else 1.0

            t = (np.arange(win) - (win - 1) / 2.0) * dt
            w_tot = np.zeros(win, dtype=np.complex128)

            seg1 = slice(0, N)
            seg2 = slice(N, 2 * N)

            for n in range(L):
                theta_n = float(self.raw_angles[n])
                if not np.isfinite(theta_n):
                    continue

                dlam = float(self.d_lambda[n])
                dalp = float(self.d_alpha[n])
                dome = float(self.d_omega[n])

                scale_n = 1.0 + dlam / lam0
                if d_omega_is_hz:
                    dome = 2.0 * np.pi * dome

                omega_n = omega_det[n] + dome

                # Pulse 1: +X
                w1 = (w0 * np.exp(1j * 0.0)) * np.exp(1j * (omega_n * t[seg1]))

                # Pulse 2 axis: Ï†2 = Ï€ - Î¸  (so Î¸=Ï€ -> 0, Î¸=0 -> Ï€)
                phi2 = (np.pi - theta_n) + dalp
                w2 = (w0 * np.exp(1j * phi2)) * np.exp(1j * (omega_n * t[seg2]))

                w_tot[seg1] += scale_n * w1
                w_tot[seg2] += scale_n * w2

            w_out = w_tot

        else:
            # One selective Ï€ then append unselective Ï€,
            # rewritten to produce the SAME Î¸ mapping as above.

            # Unselective axis angle Ï†_uns in the equatorial plane:
            #   X => 0
            #   Y => Ï€/2  (synthesized by multiplying by exp(iÏ€/2))
            phi_uns = 0.0 if self.unselective_axis == "x" else (np.pi / 2.0)

            win_sel = N
            T_sel = win_sel * dt
            lam0 = (np.pi / (2.0 * T_sel)) if T_sel != 0.0 else 1.0

            print(lam0, T_sel)
            t = (np.arange(win_sel) - (win_sel - 1) / 2.0) * dt
            w_sel = np.zeros(win_sel, dtype=np.complex128)

            for n in range(L):
                theta_n = float(self.raw_angles[n])
                if not np.isfinite(theta_n):
                    continue

                dlam = float(self.d_lambda[n])
                dalp = float(self.d_alpha[n])
                dome = float(self.d_omega[n])

                scale_n = 1.0 + dlam / lam0
                if d_omega_is_hz:
                    dome = 2.0 * np.pi * dome

                omega_n = omega_det[n] + dome

                # Choose selective axis so that:
                #   phase(|g>) after [selective Ï€, then unselective Ï€] equals exp(i Î¸_n)
                #   Ï†_sel = Î¸ + Ï†_uns - Ï€  (plus calibration correction dalp)
                phi_sel = (theta_n + phi_uns - np.pi) + dalp

                w_sel += scale_n * (w0 * np.exp(1j * phi_sel)) * np.exp(1j * (omega_n * t))

            # Unselective Ï€ template (no per-n detuning modulation here)
            w_uns = self._get_unsel_wx()
            if self.unselective_axis == "y":
                w_uns = w_uns * np.exp(1j * (np.pi / 2.0))

            w_out = np.concatenate([w_sel, w_uns])

        I_tot = np.real(w_out).astype(float)
        Q_tot = np.imag(w_out).astype(float)
        return I_tot, Q_tot, len(I_tot), marker

    # ------------------------- QUA hooks -------------------------
    def play(self, align_after: bool = True, **kwargs):
        qua.play(self.op, self.target)
        if align_after:
            qua.align()

    def build(self, mgr: PulseOperationManager | None = None):
        mgr = mgr or type(self).mgr
        if mgr is None:
            raise RuntimeError("SNAP.build requires a PulseOperationManager (mgr).")

        from_chi_flag = True if self.fock_fqs_from_chi else None
        I_tot, Q_tot, L, marker = self.waveforms(from_chi=from_chi_flag)

        I_name = f"{self.op}_I"
        Q_name = f"{self.op}_Q"
        mgr.add_waveform(I_name, "arbitrary", I_tot.tolist(), persist=False)
        mgr.add_waveform(Q_name, "arbitrary", Q_tot.tolist(), persist=False)

        pulse_name = f"{self.op}_sel2pi" if (not self.include_unselective) else f"{self.op}_sel1pi_plus_unsel"
        pulse = PulseOp(
            element=self.target,
            op=self.op,
            pulse=pulse_name,
            type="control",
            length=L,
            digital_marker=marker,
            I_wf_name=I_name,
            Q_wf_name=Q_name,
            I_wf=I_tot.tolist(),
            Q_wf=Q_tot.tolist(),
        )
        mgr.register_pulse_op(pulse, override=True, persist=False)
        self._pulse_name = pulse_name
        return self.op


class Idle(Gate):
    """
    Simple idle / wait gate.

    wait_time is in ns; internally converted to QUA wait clocks (multiples of 4 ns).
    """

    def __init__(self, wait_time: int, target: Optional[str] = None):
        wait_time = int(wait_time)

        # convert ns â†’ QUA clocks (4 ns units), rounded down to multiple of 4
        wait_clks = (wait_time - (wait_time % 4)) // 4
        self.wait_time_ns = wait_time
        self.wait_clks    = wait_clks

        if target is None:
            # fall back to qubit element if available, otherwise "qubit"
            attr = type(self).attributes
            if attr is not None and hasattr(attr, "qb_el"):
                target = attr.qb_el
            else:
                target = "qubit"

        op = f"IDLE_{wait_time}ns"
        super().__init__(op=op, target=target)

    # serialization
    def _serialize_params(self) -> dict:
        return {"wait_time_ns": int(self.wait_time_ns)}

    def _deserialize_params(self, P: dict) -> None:
        self.wait_time_ns = int(P["wait_time_ns"])
        self.wait_clks = (self.wait_time_ns - (self.wait_time_ns % 4)) // 4
        self.op = f"IDLE_{self.wait_time_ns}ns"

    # ideal unitary: identity in qubit âŠ— cavity space
    def ideal_unitary(self, n_max: int) -> np.ndarray:
        n_levels = int(n_max) + 1
        dim = 2 * n_levels
        return np.eye(dim, dtype=complex)
    
    # no waveforms: Idle is implemented as QUA wait only
    def waveforms(self) -> tuple[np.ndarray, np.ndarray, int, bool | str]:
        raise NotImplementedError(
            "Idle gate has no analog waveforms; it is implemented as a pure wait."
        )

    def play(self, *args, **kwargs):
        """
        Idle gate has no analog waveform; it is implemented as a bare wait.

        Any *args / **kwargs are accepted and ignored, to stay compatible with
        the generic Gate interface.
        """
        qua.wait(self.wait_clks)

    def build(self, mgr: PulseOperationManager | None = None):
        # nothing to build in the waveform DB for a pure wait gate
        return self.op

class Measure(Gate):
    """
    Measurement gate.

    axis âˆˆ {"x", "y", "z", "none"} chooses measurement basis.

    - "x", "y", "z": real measurements in the corresponding basis.
    - "none" or None: a *null* measurement gate â€” a placeholder that
      does nothing when played (no measurement pulse / macro).

    The actual basis rotation / behavior is delegated to measureMacro.measure
    via its `axis` argument.

    This gate does not generate analog waveforms; it only emits a QUA
    measurement macro for the non-null cases.
    """

    def __init__(self, axis: str | None = "z", target: str = "resonator"):
        # Allow axis=None as a shorthand for "none"
        if axis is None:
            axis = "none"

        axis = str(axis).lower()
        if axis not in ("x", "y", "z", "none"):
            raise ValueError(
                f"Measure: invalid axis={axis!r}; must be 'x', 'y', 'z', or 'none'"
            )

        self.axis = axis

        # Distinguish the null gate in its op name if you like
        if self.axis == "none":
            op = "MEASURE_NULL"
        else:
            op = f"MEASURE_{self.axis.upper()}"

        super().__init__(op=op, target=target)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------
    def _serialize_params(self) -> dict:
        return {
            "axis": self.axis,
        }

    def _deserialize_params(self, P: dict) -> None:
        axis = P.get("axis", "z")
        if axis is None:
            axis = "none"
        axis = str(axis).lower()

        if axis not in ("x", "y", "z", "none"):
            raise ValueError(
                f"Measure._deserialize_params: invalid axis={axis!r}"
            )

        self.axis = axis

        if self.axis == "none":
            self.op = "MEASURE_NULL"
        else:
            self.op = f"MEASURE_{self.axis.upper()}"

    # ------------------------------------------------------------------
    # "Ideal" unitary (keep as identity for now)
    # ------------------------------------------------------------------
    def ideal_unitary(self, n_max: int) -> np.ndarray:
        """
        For now, model measurement (or null measurement) as an identity
        on the Hilbert space, since projective measurement is not unitary.
        This keeps it compatible with the rest of the Gate simulation stack.
        """
        n_levels = int(n_max) + 1
        dim = 2 * n_levels
        return np.eye(dim, dtype=complex)

    # ------------------------------------------------------------------
    # Waveforms
    # ------------------------------------------------------------------
    def waveforms(self) -> tuple[np.ndarray, np.ndarray, int, bool | str]:
        raise NotImplementedError(
            "Measure gate has no analog waveforms; it is implemented as a QUA "
            "measurement macro (or as a null op for axis='none')."
        )

    # ------------------------------------------------------------------
    # QUA hook
    # ------------------------------------------------------------------
    def play(
        self,
        targets=None,
        state=None,
        with_state: bool | None = None,
        **kwargs,
    ):
        # Null gate: do nothing at runtime
        if self.axis == "none":
            return

        # Real measurement
        measureMacro.measure(
            targets=targets,
            state=state,
            with_state=with_state,
            axis=self.axis,
            **kwargs,
        )

    def build(self, mgr: PulseOperationManager | None = None):
        # nothing to build in the waveform DB for a measurement gate
        return self.op

    
@dataclass
class GateArray(Gate):
    """
    Take a *time-ordered* list of Gate objects and build one big waveform
    per target element, with implicit zero-padding whenever that target
    is idle.

    Behaves like a Gate:
      â€¢ registered in _GATE_REGISTRY via Gate.__init_subclass__
      â€¢ supports ideal_unitary(n_max)
      â€¢ has _serialize_params / _deserialize_params
      â€¢ has play() and build() in the Gate style
    """
    gates: Iterable[Gate]
    op_prefix: str = "GA"

    # internal cache of built ops: target -> op_name
    _ops_by_target: Dict[str, str] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self):
        # make sure we can iterate multiple times
        self.gates = list(self.gates)
        if not self.gates:
            raise ValueError("GateArray requires at least one gate")

        # Use the first gate's target as a representative just to satisfy Gate.__init__.
        # The real per-target ops are created in build().
        first_target = getattr(self.gates[0], "target", "qubit")
        Gate.__init__(self, op=f"{self.op_prefix}", target=first_target)

    # ------------------------------------------------------------------
    # Serialization hooks for Gate.to_dict / Gate.from_dict
    # ------------------------------------------------------------------
    def _serialize_params(self) -> dict:
        return {
            "op_prefix": self.op_prefix,
            "gates": [g.to_dict() for g in self.gates],
        }

    def _deserialize_params(self, P: dict) -> None:
        self.op_prefix = P.get("op_prefix", "GA")
        gates_data = P.get("gates", [])
        self.gates = [Gate.from_dict(gd) for gd in gates_data]  # loads only, no mgr required

        if self.gates:
            first_target = getattr(self.gates[0], "target", "qubit")
        else:
            first_target = "qubit"
        self.op = f"{self.op_prefix}"
        self.target = first_target
        self._ops_by_target = {}

    def ideal_unitary(self, n_max: int) -> np.ndarray:
        # keep your old get_unitary logic (renamed)
        n_levels = int(n_max) + 1
        dim = 2 * n_levels
        U_tot = np.eye(dim, dtype=complex)
        for g in self.gates:
            U_g = g.ideal_unitary(n_max)
            U_tot = U_g @ U_tot
        return U_tot

    def get_channel(self, n_max: int, **kwargs) -> np.ndarray:
        n_levels = int(n_max) + 1
        dim = 2 * n_levels
        S_tot = np.eye(dim * dim, dtype=np.complex128)

        for g in self.gates:
            S_g = g.get_channel(n_max, **kwargs)
            if S_g.shape != (dim*dim, dim*dim):
                raise ValueError(f"{g}: channel shape {S_g.shape}, expected {(dim*dim, dim*dim)}")
            S_tot = S_g @ S_tot

        return S_tot

    def waveforms(self) -> tuple[np.ndarray, np.ndarray, int, bool | str]:
        raise NotImplementedError(
            "GateArray is multi-target; use build() to register per-target waveforms "
            "and play() to emit them. A single (I, Q, length, marker) is not defined."
        )

    # ------------------------------------------------------------------
    # Build (unchanged)
    # ------------------------------------------------------------------
    def build(
        self,
        mgr: Optional[PulseOperationManager] = None
    ) -> Dict[str, str]:
        if self._ops_by_target:
            return self._ops_by_target

        gates = list(self.gates)
        if not gates:
            raise ValueError("GateArray.build: empty gate list")

        if mgr is None:
            mgr = type(gates[0]).mgr

        seg_lengths: list[int] = []
        segments: list[tuple[Gate, str, np.ndarray, np.ndarray, int, bool | str]] = []

        for g in gates:
            I, Q, L, marker = g.waveforms()
            I = np.asarray(I, dtype=float)
            Q = np.asarray(Q, dtype=float)
            if I.shape != Q.shape:
                raise ValueError(f"{g}: I and Q have different shapes {I.shape} vs {Q.shape}")

            if L is None:
                L = len(I)
            L = int(L)
            if L != len(I):
                I = np.broadcast_to(I, (L,))
                Q = np.broadcast_to(Q, (L,))

            segments.append((g, g.target, I, Q, L, marker))
            seg_lengths.append(L)

        total_len = int(sum(seg_lengths))

        targets = sorted({tgt for (_g, tgt, *_rest) in segments})
        I_tot: Dict[str, np.ndarray] = {tgt: np.zeros(total_len, dtype=float) for tgt in targets}
        Q_tot: Dict[str, np.ndarray] = {tgt: np.zeros(total_len, dtype=float) for tgt in targets}
        marker_by_tgt: dict[str, bool | str | None] = {tgt: None for tgt in targets}

        offset = 0
        for (g, tgt, I, Q, L, marker) in segments:
            sl = slice(offset, offset + L)
            I_tot[tgt][sl] += I
            Q_tot[tgt][sl] += Q
            if marker_by_tgt[tgt] is None:
                marker_by_tgt[tgt] = marker
            offset += L

        ops_by_target: Dict[str, str] = {}
        for tgt in targets:
            I_arr = I_tot[tgt]
            Q_arr = Q_tot[tgt]
            marker = marker_by_tgt[tgt]
            if marker is None:
                marker = "ON"

            op_name    = f"{self.op_prefix}_{tgt}"
            pulse_name = f"{op_name}_pulse"
            I_name     = f"{op_name}_I"
            Q_name     = f"{op_name}_Q"

            mgr.add_waveform(I_name, "arbitrary", I_arr.tolist(), persist=False)
            mgr.add_waveform(Q_name, "arbitrary", Q_arr.tolist(), persist=False)

            pulse = PulseOp(
                element        = tgt,
                op             = op_name,
                pulse          = pulse_name,
                type           = "control",
                length         = total_len,
                digital_marker = marker,
                I_wf_name      = I_name,
                Q_wf_name      = Q_name,
                I_wf           = I_arr.tolist(),
                Q_wf           = Q_arr.tolist(),
            )
            mgr.register_pulse_op(pulse, override=True, persist=False)
            ops_by_target[tgt] = op_name

        self._ops_by_target = ops_by_target
        return ops_by_target

    # ------------------------------------------------------------------
    # Play (NO mgr; assumes already built)
    # ------------------------------------------------------------------
    def play(self, align_after: bool = False, **kwargs) -> None:
        """
        QUA-level play: emit play() for all targets.

        Assumes build() has already been called; otherwise raises.

        Parameters
        ----------
        align_after : bool, optional
            If True, calls `qua.align()` after playing all targets.
        **kwargs :
            Accepted for compatibility (e.g. higher-level code can pass options
            without crashing). Currently ignored by GateArray itself.
        """
        if not self._ops_by_target:
            raise RuntimeError(
                "GateArray.play called before build(); call .build(mgr) during setup."
            )

        for tgt in sorted(self._ops_by_target.keys()):
            op = self._ops_by_target[tgt]
            qua.play(op, tgt)

        if align_after:
            qua.align()



def save_gates(path: str | pathlib.Path, gates: list[Gate]) -> None:
    with open(path, "w") as fp:
        json.dump([g.to_dict() for g in gates], fp, indent=2)

def load_gates(
    path: str | pathlib.Path,
    mgr: Optional[PulseOperationManager] = None,
    attributes: Optional[cQED_attributes] = None,
    build: bool = False,
) -> list[Gate]:
    """
    Load gates from JSON.

    - If mgr is None (default): loads gates as parameter-only objects.
      You can still call ideal_unitary/get_unitaries, inspect params, etc.
    - If build=True: registers waveforms and requires mgr.
    """
    with open(path) as fp:
        gate_dicts = json.load(fp)

    return [Gate.from_dict(d, mgr=mgr, attributes=attributes, build=build) for d in gate_dicts]

def attach_and_build_gates(
    gates: list[Gate],
    mgr: PulseOperationManager,
    attributes: cQED_attributes,
) -> None:
    """
    After loading gates without a manager, call this once you have mgr/attrs.
    """
    # attach class-level context per concrete gate class
    for g in gates:
        type(g).set_context(mgr=mgr, attributes=attributes)

    # build only the ones that need waveforms registered
    for g in gates:
        g.build(mgr=mgr)


