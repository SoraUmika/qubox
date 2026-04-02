# qubox_v2/gates/hardware/snap.py
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

from ..hardware_base import GateHardware
from ..hash_utils import array_md5

from qubox.core.pulse_op import PulseOp


def _as_padded_complex(I, Q, *, pad_to_4: bool = True) -> np.ndarray:
    """Combine I/Q into complex array, optionally padded to multiple of 4."""
    I = np.asarray(I, dtype=float)
    Q = np.asarray(Q, dtype=float)
    if pad_to_4:
        pad = (-len(I)) % 4
        if pad:
            I = np.pad(I, (0, pad))
            Q = np.pad(Q, (0, pad))
    return I + 1j * Q


def _get_attr(att, name, default=None):
    return getattr(att, name, default)


def _resolve_fock_detunings(att, n_levels, *, from_chi=None, d_omega_is_hz=False):
    """Resolve per-Fock detuning frequencies (Hz) from attributes.

    Priority:
      1) att.get_fock_frequencies() if available (from calibration)
      2) chi/chi2/chi3 polynomial formula (fallback)
    """
    if from_chi is None:
        from_chi = not (hasattr(att, "fock_fqs") and (getattr(att, "fock_fqs") is not None))

    levels = np.arange(n_levels, dtype=int)

    if hasattr(att, "get_fock_frequencies") and not from_chi:
        f_abs = np.asarray(att.get_fock_frequencies(levels, from_chi=False), dtype=float)
        df = f_abs - float(f_abs[0])
    else:
        chi  = float(getattr(att, "st_chi"))
        chi2 = float(getattr(att, "st_chi2", 0.0))
        chi3 = float(getattr(att, "st_chi3", 0.0))
        n = levels.astype(float)
        df = chi*n + chi2*n*(n-1) + chi3*n*(n-1)*(n-2)

    return 2.0 * np.pi * df  # rad/s


@dataclass
class SNAPHardware(GateHardware):
    """
    Hardware backend for SNAP gate.

    Uses a single calibrated selective-X reference template and complex
    phase rotation, matching the legacy SNAP convention:

    Mode A (two selective, include_unselective=False):
      - Pulse 1: w0 * exp(+1j * 0)      [identity phase]
      - Pulse 2: w0 * exp(+1j * phi2)    [phi2 = (pi - theta_n) + d_alpha_n]
      - Both frequency-shifted per Fock number
      - w_tot[seg1] += scale_n * w1, w_tot[seg2] += scale_n * w2

    Mode B (sel+unsel, include_unselective=True):
      - phi_sel = theta_n + phi_uns - pi + d_alpha_n
      - Selective pulse frequency-shifted, then unselective appended
    """
    angles: np.ndarray
    d_lambda: np.ndarray
    d_alpha: np.ndarray
    d_omega: np.ndarray

    include_unselective: bool = False
    unselective_axis: str = "x"
    unselective_position: str = "before"

    sel_x180_pulse_id: str = "sel_x180_pulse"
    unsel_x180_pulse_id: str = "x180_pulse"

    fock_fqs_from_chi: bool = False

    target: str | None = None
    gate_type: str = "SNAP"

    def __post_init__(self):
        self.angles = np.asarray(self.angles, dtype=float)
        L = int(self.angles.size)

        def _arr(x):
            x = np.asarray(x, dtype=float)
            if x.ndim == 0:
                x = np.full(L, float(x))
            if len(x) < L:
                x = np.pad(x, (0, L - len(x)))
            elif len(x) > L:
                x = x[:L]
            return x

        self.d_lambda = _arr(self.d_lambda) if self.d_lambda is not None else np.zeros(L, dtype=float)
        self.d_alpha  = _arr(self.d_alpha)  if self.d_alpha  is not None else np.zeros(L, dtype=float)
        self.d_omega  = _arr(self.d_omega)  if self.d_omega  is not None else np.zeros(L, dtype=float)

        self.include_unselective = bool(self.include_unselective)
        self.unselective_axis = str(self.unselective_axis).lower()
        self.unselective_position = str(self.unselective_position).lower()
        if self.unselective_axis not in ("x", "y"):
            raise ValueError("unselective_axis must be 'x' or 'y'")
        if self.unselective_position not in ("before", "after"):
            raise ValueError("unselective_position must be 'before' or 'after'")

        if self.target is None:
            self.target = "qubit"

        payload = np.concatenate([
            self.angles,
            self.d_lambda,
            self.d_alpha,
            self.d_omega,
            np.array([
                1.0 if self.include_unselective else 0.0,
                0.0 if self.unselective_axis == "x" else 1.0,
                0.0 if self.unselective_position == "before" else 1.0,
            ], dtype=float),
        ])
        self.op = f"SNAP_{array_md5(payload)}"

    # --------------------
    # serialization
    # --------------------
    def to_dict(self) -> dict:
        return {
            "type": self.gate_type,
            "target": self.target,
            "params": {
                "angles": self.angles.tolist(),
                "d_lambda": self.d_lambda.tolist(),
                "d_alpha": self.d_alpha.tolist(),
                "d_omega": self.d_omega.tolist(),
                "include_unselective": bool(self.include_unselective),
                "unselective_axis": str(self.unselective_axis),
                "unselective_position": str(self.unselective_position),
                "sel_x180_pulse_id": self.sel_x180_pulse_id,
                "unsel_x180_pulse_id": self.unsel_x180_pulse_id,
                "fock_fqs_from_chi": bool(self.fock_fqs_from_chi),
                "op": getattr(self, "op", None),
            },
        }

    @classmethod
    def from_dict(cls, d: dict, *, hw_ctx) -> "SNAPHardware":
        P = d.get("params", {})
        target = d.get("target", None)
        if target is None:
            snapshot = getattr(hw_ctx, "context_snapshot", None)
            attr = snapshot() if callable(snapshot) else None
            target = getattr(attr, "qb_el", "qubit") if attr is not None else "qubit"

        obj = cls(
            angles=np.asarray(P["angles"], dtype=float),
            d_lambda=np.asarray(P.get("d_lambda", np.zeros_like(P["angles"])), dtype=float),
            d_alpha=np.asarray(P.get("d_alpha", np.zeros_like(P["angles"])), dtype=float),
            d_omega=np.asarray(P.get("d_omega", np.zeros_like(P["angles"])), dtype=float),
            include_unselective=bool(P.get("include_unselective", False)),
            unselective_axis=str(P.get("unselective_axis", "x")),
            unselective_position=str(P.get("unselective_position", "before")),
            sel_x180_pulse_id=str(P.get("sel_x180_pulse_id", "sel_x180_pulse")),
            unsel_x180_pulse_id=str(P.get("unsel_x180_pulse_id", "x180_pulse")),
            fock_fqs_from_chi=bool(P.get("fock_fqs_from_chi", False)),
            target=target,
        )
        if P.get("op"):
            obj.op = str(P["op"])
        return obj

    # --------------------
    # waveform synthesis
    # --------------------
    def waveforms(self, *, hw_ctx, from_chi: bool | None = None, d_omega_is_hz: bool = False
                  ) -> tuple[np.ndarray, np.ndarray, int, bool | str]:
        mgr = hw_ctx.mgr
        att = hw_ctx.context_snapshot()

        dt = float(_get_attr(att, "dt_s", 1e-9))

        # Calibrated selective pi template (complex)
        xid = self.sel_x180_pulse_id
        I_x0, Q_x0 = mgr.get_pulse_waveforms(xid)
        w0 = _as_padded_complex(I_x0, Q_x0, pad_to_4=True)
        N = len(w0)

        L = int(self.angles.size)

        # Resolve per-Fock detunings
        if from_chi is None:
            from_chi = self.fock_fqs_from_chi or not (
                hasattr(att, "fock_fqs") and (getattr(att, "fock_fqs") is not None)
            )
        omega_det = _resolve_fock_detunings(att, L, from_chi=from_chi)

        add_unsel = bool(self.include_unselective)
        use_two_selective = (not add_unsel)

        marker = mgr._perm.pulses[xid].get("digital_marker", "ON")

        if use_two_selective:
            # Mode A: Two selective pi pulses back-to-back
            win = 2 * N
            T_sel = win * dt
            lam0 = (np.pi / (2.0 * T_sel)) if T_sel != 0.0 else 1.0

            t = (np.arange(win) - (win - 1) / 2.0) * dt
            w_tot = np.zeros(win, dtype=np.complex128)

            seg1 = slice(0, N)
            seg2 = slice(N, 2 * N)

            for n in range(L):
                theta_n = float(self.angles[n])
                if not np.isfinite(theta_n):
                    continue

                dlam = float(self.d_lambda[n])
                dalp = float(self.d_alpha[n])
                dome = float(self.d_omega[n])

                scale_n = 1.0 + dlam / lam0
                if d_omega_is_hz:
                    dome = 2.0 * np.pi * dome

                omega_n = omega_det[n] + dome

                # Pulse 1: +X (identity phase)
                w1 = (w0 * np.exp(1j * 0.0)) * np.exp(1j * (omega_n * t[seg1]))

                # Pulse 2: phi2 = (pi - theta_n) + d_alpha_n
                phi2 = (np.pi - theta_n) + dalp
                w2 = (w0 * np.exp(1j * phi2)) * np.exp(1j * (omega_n * t[seg2]))

                w_tot[seg1] += scale_n * w1
                w_tot[seg2] += scale_n * w2

            I_tot = np.real(w_tot).astype(float)
            Q_tot = np.imag(w_tot).astype(float)
            return I_tot, Q_tot, len(I_tot), marker

        # Mode B: One selective pi + one unselective pi
        phi_uns = 0.0 if self.unselective_axis == "x" else (np.pi / 2.0)

        win_sel = N
        T_sel = win_sel * dt
        lam0 = (np.pi / (2.0 * T_sel)) if T_sel != 0.0 else 1.0

        t = (np.arange(win_sel) - (win_sel - 1) / 2.0) * dt
        w_sel = np.zeros(win_sel, dtype=np.complex128)

        for n in range(L):
            theta_n = float(self.angles[n])
            if not np.isfinite(theta_n):
                continue

            dlam = float(self.d_lambda[n])
            dalp = float(self.d_alpha[n])
            dome = float(self.d_omega[n])

            scale_n = 1.0 + dlam / lam0
            if d_omega_is_hz:
                dome = 2.0 * np.pi * dome

            omega_n = omega_det[n] + dome

            # phi_sel = theta + phi_uns - pi + d_alpha
            phi_sel = (theta_n + phi_uns - np.pi) + dalp

            w_sel += scale_n * (w0 * np.exp(1j * phi_sel)) * np.exp(1j * (omega_n * t))

        # Unselective pi template
        uid = self.unsel_x180_pulse_id
        I_u, Q_u = mgr.get_pulse_waveforms(uid)
        w_uns = _as_padded_complex(I_u, Q_u, pad_to_4=True)
        if self.unselective_axis == "y":
            w_uns = w_uns * np.exp(1j * (np.pi / 2.0))

        I_sel = np.real(w_sel).astype(float)
        Q_sel = np.imag(w_sel).astype(float)
        I_uns = np.real(w_uns).astype(float)
        Q_uns = np.imag(w_uns).astype(float)

        if self.unselective_position == "before":
            I_tot = np.concatenate([I_uns, I_sel])
            Q_tot = np.concatenate([Q_uns, Q_sel])
        else:
            I_tot = np.concatenate([I_sel, I_uns])
            Q_tot = np.concatenate([Q_sel, Q_uns])

        return I_tot, Q_tot, len(I_tot), marker

    # --------------------
    # build / play
    # --------------------
    def build(self, *, hw_ctx) -> None:
        mgr = hw_ctx.mgr

        # Refresh op hash
        payload = np.concatenate([
            self.angles,
            self.d_lambda,
            self.d_alpha,
            self.d_omega,
            np.array([
                1.0 if self.include_unselective else 0.0,
                0.0 if self.unselective_axis == "x" else 1.0,
                0.0 if self.unselective_position == "before" else 1.0,
            ], dtype=float),
        ])
        self.op = f"SNAP_{array_md5(payload)}"

        I_tot, Q_tot, L, marker = self.waveforms(hw_ctx=hw_ctx)

        I_name = f"{self.op}_I"
        Q_name = f"{self.op}_Q"
        mgr.add_waveform(I_name, "arbitrary", I_tot.tolist(), persist=False)
        mgr.add_waveform(Q_name, "arbitrary", Q_tot.tolist(), persist=False)

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
            I_wf=I_tot.tolist(),
            Q_wf=Q_tot.tolist(),
        )
        mgr.register_pulse_op(pulse, override=True, persist=False)
        self._pulse_name = pulse_name

    def play(self, *, hw_ctx, align_after: bool = True) -> None:
        from qm import qua
        qua.play(self.op, self.target)
        if align_after:
            qua.align()
