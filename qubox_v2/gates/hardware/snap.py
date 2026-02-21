# qubox/gates_v2/hardware/snap.py
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

from ..hardware_base import GateHardware
from ..hash_utils import array_md5

# Adjust to your real module paths:
from qubox_v2.pulse_manager import PulseOp


def _get_attr(att, name, default=None):
    return getattr(att, name, default)


def _resolve_chis(att):
    """
    Support both old attribute names (chi, chi2, chi3) and new (st_chi, st_chi2, st_chi3).
    All are assumed in Hz (cycles/s), consistent with your legacy waveform code.
    """
    chi  = _get_attr(att, "st_chi",  _get_attr(att, "chi",  None))
    if chi is None:
        raise AttributeError("SNAPHardware: cannot find chi (att.st_chi or att.chi).")

    chi2 = _get_attr(att, "st_chi2", _get_attr(att, "chi2", 0.0))
    chi3 = _get_attr(att, "st_chi3", _get_attr(att, "chi3", 0.0))
    return float(chi), float(chi2), float(chi3)


@dataclass
class SNAPHardware(GateHardware):
    """
    Hardware backend for SNAP.

    Parameters follow your legacy implementation:
      - angles[n] : target SNAP phase angle (rad) (paper parameterization)
      - d_lambda[n], d_alpha[n], d_omega[n] : per-Fock corrections for the selective Ï€ synthesis
      - include_unselective : choose implementation variant
      - unselective_axis : 'x' or 'y'
      - unselective_position : 'before' or 'after'
          * default 'before' to match your provided code (even though doc said 'append').

    Pulse IDs are configurable (so you can match your lab config):
      - sel_x180_pulse_id / sel_y180_pulse_id
      - unsel_x180_pulse_id / unsel_y180_pulse_id
    """
    angles: np.ndarray
    d_lambda: np.ndarray
    d_alpha: np.ndarray
    d_omega: np.ndarray

    include_unselective: bool = False
    unselective_axis: str = "x"
    unselective_position: str = "before"  # matches your current code

    sel_x180_pulse_id: str = "sel_x180_pulse"
    sel_y180_pulse_id: str = "sel_y180_pulse"
    unsel_x180_pulse_id: str = "x180_pulse"
    unsel_y180_pulse_id: str = "y180_pulse"

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
                "sel_y180_pulse_id": self.sel_y180_pulse_id,
                "unsel_x180_pulse_id": self.unsel_x180_pulse_id,
                "unsel_y180_pulse_id": self.unsel_y180_pulse_id,
                "op": getattr(self, "op", None),
            },
        }

    @classmethod
    def from_dict(cls, d: dict, *, hw_ctx) -> "SNAPHardware":
        P = d.get("params", {})
        target = d.get("target", None)
        if target is None:
            attr = getattr(hw_ctx, "attributes", None)
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
            sel_y180_pulse_id=str(P.get("sel_y180_pulse_id", "sel_y180_pulse")),
            unsel_x180_pulse_id=str(P.get("unsel_x180_pulse_id", "x180_pulse")),
            unsel_y180_pulse_id=str(P.get("unsel_y180_pulse_id", "y180_pulse")),
            target=target,
        )
        if P.get("op"):
            obj.op = str(P["op"])
        return obj

    # --------------------
    # waveform synthesis
    # --------------------
    def waveforms(self, *, hw_ctx) -> tuple[np.ndarray, np.ndarray, int, bool | str]:
        mgr = hw_ctx.mgr
        att = hw_ctx.attributes

        chi, chi2, chi3 = _resolve_chis(att)
        dt = float(_get_attr(att, "dt_s", 1e-9))

        # calibrated selective Ï€ templates
        xid = self.sel_x180_pulse_id
        yid = self.sel_y180_pulse_id
        I_x0, Q_x0 = mgr.get_pulse_waveforms(xid)
        I_y0, Q_y0 = mgr.get_pulse_waveforms(yid)

        # pad to multiple of 4
        pad = (-len(I_x0)) % 4
        if pad:
            I_x0 = np.pad(I_x0, (0, pad)); Q_x0 = np.pad(Q_x0, (0, pad))
            I_y0 = np.pad(I_y0, (0, pad)); Q_y0 = np.pad(Q_y0, (0, pad))

        len_pi = len(I_x0)
        t_pi = len_pi * dt

        add_unsel = bool(self.include_unselective)
        len_u = 0
        I_u = Q_u = None

        if add_unsel:
            uid = self.unsel_x180_pulse_id if self.unselective_axis == "x" else self.unsel_y180_pulse_id
            I_u, Q_u = mgr.get_pulse_waveforms(uid)
            pad_u = (-len(I_u)) % 4
            if pad_u:
                I_u = np.pad(I_u, (0, pad_u)); Q_u = np.pad(Q_u, (0, pad_u))
            len_u = len(I_u)

        def rot(I, Q, w):
            t = (np.arange(1, len(I) + 1)) * dt
            c, s = np.cos(w * t), np.sin(w * t)
            return I * c - Q * s, I * s + Q * c

        def mix(phi, I_x, Q_x, I_y, Q_y):
            c, s = np.cos(phi), np.sin(phi)
            return c * I_x + s * I_y, c * Q_x + s * Q_y

        use_two_selective = (not add_unsel)

        if use_two_selective:
            # TWO selective Ï€â€™s (legacy)
            win_len = 2 * len_pi
            T_sel = 2 * t_pi
            lam0 = np.pi / (2.0 * T_sel)
            inv_lam0 = (1.0 / lam0) if lam0 != 0.0 else 1.0

            I_tot = np.zeros(win_len, dtype=float)
            Q_tot = np.zeros(win_len, dtype=float)

            for n, theta_n in enumerate(self.angles):
                th = float(theta_n)
                if not np.isfinite(th):
                    continue

                dlam = float(self.d_lambda[n])
                dalp = float(self.d_alpha[n])
                dome = float(self.d_omega[n])

                scale_n = 1.0 + dlam * inv_lam0

                w_n = (2 * np.pi) * (
                    n * chi + chi2 * n * (n - 1) + chi3 * n * (n - 1) * (n - 2)
                ) + dome

                Ix, Qx = rot(I_x0, Q_x0, w_n)
                Iy, Qy = rot(I_y0, Q_y0, w_n)

                # Ï€1 axis = 0; Ï€2 axis = Î¸_n + dÎ±_n âˆ’ Î”Ï‰_n * (T_sel/2)
                phi2 = (th + dalp) - dome * (0.5 * T_sel)

                I1, Q1 = mix(0.0,  Ix, Qx, Iy, Qy)
                I2, Q2 = mix(phi2, Ix, Qx, Iy, Qy)

                I_tot[:len_pi]         += scale_n * I1
                Q_tot[:len_pi]         += scale_n * Q1
                I_tot[len_pi:2*len_pi] -= scale_n * I2
                Q_tot[len_pi:2*len_pi] -= scale_n * Q2

            marker = mgr._perm.pulses[xid].get("digital_marker", "ON")
            return I_tot, Q_tot, len(I_tot), marker

        # ONE selective Ï€ + ONE unselective Ï€
        win_len = len_pi
        T_sel = t_pi
        lam0 = np.pi / (2.0 * T_sel)
        inv_lam0 = (1.0 / lam0) if lam0 != 0.0 else 1.0

        I_sel = np.zeros(win_len, dtype=float)
        Q_sel = np.zeros(win_len, dtype=float)

        for n, theta_n in enumerate(self.angles):
            th = float(theta_n)
            if not np.isfinite(th):
                continue

            dlam = float(self.d_lambda[n])
            dalp = float(self.d_alpha[n])
            dome = float(self.d_omega[n])

            scale_n = 1.0 + dlam * inv_lam0

            w_n = (2 * np.pi) * (
                n * chi + chi2 * n * (n - 1) + chi3 * n * (n - 1) * (n - 2)
            ) + dome

            Ix, Qx = rot(I_x0, Q_x0, w_n)
            Iy, Qy = rot(I_y0, Q_y0, w_n)

            phi = (th + dalp) - dome * (0.5 * T_sel)
            I1, Q1 = mix(phi, Ix, Qx, Iy, Qy)

            I_sel += scale_n * I1
            Q_sel += scale_n * Q1

        # Stitch in the unselective pulse before/after (default before to match your code)
        if self.unselective_position == "before":
            I_tot = np.concatenate([I_u, I_sel])
            Q_tot = np.concatenate([Q_u, Q_sel])
        else:
            I_tot = np.concatenate([I_sel, I_u])
            Q_tot = np.concatenate([Q_sel, Q_u])

        marker = mgr._perm.pulses[xid].get("digital_marker", "ON")
        return I_tot, Q_tot, len(I_tot), marker

    # --------------------
    # build / play
    # --------------------
    def build(self, *, hw_ctx) -> None:
        mgr = hw_ctx.mgr

        # refresh op if angles/params changed externally
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

