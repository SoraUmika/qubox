# qubox/gates_v2/hardware/sqr.py
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

from ..hardware_base import GateHardware
from ..hash_utils import array_md5

# Adjust imports to your project layout:
from qubox_v2.pulse_manager import PulseOp


@dataclass
class SQRHardware(GateHardware):
    """
    Hardware backend for SQR waveform synthesis.

    This is your existing waveform generator:
      - uses calibrated selective x/y base pulses
      - frequency shifts by chi, chi2, chi3 from attributes
      - per-n scale & phase offsets (d_lambda, d_alpha, d_omega)
    """
    thetas: np.ndarray
    phis: np.ndarray
    d_lambda: np.ndarray
    d_alpha: np.ndarray
    d_omega: np.ndarray

    b_x180_pulse: str = "sel_x180_pulse"
    b_y180_pulse: str = "sel_y180_pulse"
    target: str | None = None
    gate_type: str = "SQR"

    def __post_init__(self):
        self.thetas = np.asarray(self.thetas, dtype=float)
        self.phis = np.asarray(self.phis, dtype=float)
        self.d_lambda = np.asarray(self.d_lambda, dtype=float)
        self.d_alpha = np.asarray(self.d_alpha, dtype=float)
        self.d_omega = np.asarray(self.d_omega, dtype=float)

        if self.target is None:
            self.target = "qubit"

        payload = np.concatenate([self.thetas, self.phis, self.d_lambda, self.d_alpha, self.d_omega])
        self.op = f"SQR_{array_md5(payload)}"

    def to_dict(self) -> dict:
        return {
            "type": self.gate_type,
            "target": self.target,
            "params": {
                "thetas": self.thetas.tolist(),
                "phis": self.phis.tolist(),
                "d_lambda": self.d_lambda.tolist(),
                "d_alpha": self.d_alpha.tolist(),
                "d_omega": self.d_omega.tolist(),
                "b_x180_pulse": self.b_x180_pulse,
                "b_y180_pulse": self.b_y180_pulse,
                "op": getattr(self, "op", None),
            },
        }

    @classmethod
    def from_dict(cls, d: dict, *, hw_ctx) -> "SQRHardware":
        P = d.get("params", {})
        target = d.get("target", None)
        if target is None:
            attr = getattr(hw_ctx, "attributes", None)
            target = getattr(attr, "qb_el", "qubit") if attr is not None else "qubit"

        obj = cls(
            thetas=np.asarray(P["thetas"], dtype=float),
            phis=np.asarray(P["phis"], dtype=float),
            d_lambda=np.asarray(P.get("d_lambda", np.zeros_like(P["thetas"])), dtype=float),
            d_alpha=np.asarray(P.get("d_alpha", np.zeros_like(P["thetas"])), dtype=float),
            d_omega=np.asarray(P.get("d_omega", np.zeros_like(P["thetas"])), dtype=float),
            b_x180_pulse=str(P.get("b_x180_pulse", "sel_x180_pulse")),
            b_y180_pulse=str(P.get("b_y180_pulse", "sel_y180_pulse")),
            target=target,
        )
        if P.get("op"):
            obj.op = str(P["op"])
        return obj

    def waveforms(self, *, hw_ctx) -> tuple[np.ndarray, np.ndarray, int, bool | str]:
        mgr = hw_ctx.mgr
        att = hw_ctx.attributes

        # dt from attributes if available, else fallback
        dt = float(getattr(att, "dt_s", 1e-9))

        chi  = float(getattr(att, "st_chi"))
        chi2 = float(getattr(att, "st_chi2", 0.0))
        chi3 = float(getattr(att, "st_chi3", 0.0))

        xid = self.b_x180_pulse
        yid = self.b_y180_pulse

        I_x0, Q_x0 = mgr.get_pulse_waveforms(xid)
        I_y0, Q_y0 = mgr.get_pulse_waveforms(yid)

        # pad to multiple of 4
        pad = (-len(I_x0)) % 4
        if pad:
            I_x0 = np.pad(I_x0, (0, pad)); Q_x0 = np.pad(Q_x0, (0, pad))
            I_y0 = np.pad(I_y0, (0, pad)); Q_y0 = np.pad(Q_y0, (0, pad))

        win_len = len(I_x0)
        T_sel = win_len * dt
        lam0 = np.pi / (2.0 * T_sel)
        inv_lam0 = (1.0 / lam0) if lam0 != 0.0 else 1.0

        marker = mgr._perm.pulses[xid].get("digital_marker", "ON")

        I_tot = np.zeros(win_len, dtype=float)
        Q_tot = np.zeros(win_len, dtype=float)

        def rot(I, Q, w):
            t = (np.arange(1, len(I) + 1)) * dt
            c, s = np.cos(w * t), np.sin(w * t)
            return I * c - Q * s, I * s + Q * c

        def mix(phi, I_x, Q_x, I_y, Q_y):
            c, s = np.cos(phi), np.sin(phi)
            return c * I_x + s * I_y, c * Q_x + s * Q_y

        for n, (th, ph, dlam, dalp, dome) in enumerate(
            zip(self.thetas, self.phis, self.d_lambda, self.d_alpha, self.d_omega)
        ):
            if (not np.isfinite(th)) or (th == 0.0):
                continue

            scale = (float(th) / np.pi) * (1.0 + float(dlam) * inv_lam0)

            w_n = (2 * np.pi) * (
                n * chi + chi2 * n * (n - 1) + chi3 * n * (n - 1) * (n - 2)
            ) + float(dome)

            Ix, Qx = rot(I_x0, Q_x0, w_n)
            Iy, Qy = rot(I_y0, Q_y0, w_n)

            phi_eff = float(ph) + float(dalp) - float(dome) * (0.5 * T_sel)

            I_rot, Q_rot = mix(phi_eff, Ix, Qx, Iy, Qy)
            I_tot += scale * I_rot
            Q_tot += scale * Q_rot

        return I_tot, Q_tot, win_len, marker

    def build(self, *, hw_ctx) -> None:
        mgr = hw_ctx.mgr

        I_tot, Q_tot, win_len, marker = self.waveforms(hw_ctx=hw_ctx)

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

    def play(self, *, hw_ctx, align_after: bool = True) -> None:
        from qm import qua
        qua.play(self.op, self.target)
        if align_after:
            qua.align()

