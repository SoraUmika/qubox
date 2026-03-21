# qubox_v2/gates/hardware/qubit_rotation.py
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np

from ..hardware_base import GateHardware
from ..hash_utils import stable_hash

from qubox.legacy.analysis.pulseOp import PulseOp
from qubox.legacy.core.types import MAX_AMPLITUDE


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


@dataclass
class QubitRotationHardware(GateHardware):
    """
    Hardware backend for QubitRotation.

    Uses a single calibrated X reference template and complex rotation
    to synthesize arbitrary equatorial rotations, matching the legacy
    QubitRotation convention:

        w0 = pad_to_4(I_ref + 1j*Q_ref)
        phi_eff = phi + d_alpha
        amp_scale = (theta/pi) * (1.0 + d_lambda/lam0)
        w_axis = w0 * exp(-1j * phi_eff)
        if d_omega != 0:
            t = centered_time_array
            w_axis *= exp(1j * d_omega * t)
        w_new = amp_scale * w_axis
    """
    theta: float
    phi: float
    ref_x180_pulse: str = "x180_pulse"
    d_lambda: float = 0.0
    d_alpha: float = 0.0
    d_omega: float = 0.0
    target: str | None = None

    gate_type: str = "QubitRotation"

    def __post_init__(self):
        self.theta = float(self.theta)
        self.phi = float(self.phi)
        self.d_lambda = float(self.d_lambda)
        self.d_alpha = float(self.d_alpha)
        self.d_omega = float(self.d_omega)

        if self.target is None:
            self.target = "qubit"

        self.op = f"Rotation_th{self.theta:.12g}_ph{self.phi:.12g}"

    # --------------------
    # serialization
    # --------------------
    def to_dict(self) -> dict:
        return {
            "type": self.gate_type,
            "target": self.target,
            "params": {
                "theta": float(self.theta),
                "phi": float(self.phi),
                "ref_x180_pulse": self.ref_x180_pulse,
                "d_lambda": float(self.d_lambda),
                "d_alpha": float(self.d_alpha),
                "d_omega": float(self.d_omega),
                "op": getattr(self, "op", None),
            },
        }

    @classmethod
    def from_dict(cls, d: dict, *, hw_ctx) -> "QubitRotationHardware":
        P = d.get("params", {})
        target = d.get("target", None)
        if target is None:
            snapshot = getattr(hw_ctx, "context_snapshot", None)
            attr = snapshot() if callable(snapshot) else None
            target = getattr(attr, "qb_el", "qubit") if attr is not None else "qubit"

        # Support legacy serialized keys
        ref_pulse = str(P.get("ref_x180_pulse", P.get("b_x180_pulse", "x180_pulse")))

        obj = cls(
            theta=float(P["theta"]),
            phi=float(P["phi"]),
            ref_x180_pulse=ref_pulse,
            d_lambda=float(P.get("d_lambda", 0.0)),
            d_alpha=float(P.get("d_alpha", 0.0)),
            d_omega=float(P.get("d_omega", 0.0)),
            target=target,
        )
        if P.get("op"):
            obj.op = str(P["op"])
        return obj

    # --------------------
    # waveforms / build / play
    # --------------------
    def waveforms(self, *, hw_ctx) -> tuple[np.ndarray, np.ndarray, int, bool | str]:
        mgr = hw_ctx.mgr
        att = hw_ctx.context_snapshot()

        dt = float(getattr(att, "dt_s", 1e-9))

        xid = self.ref_x180_pulse
        I_x, Q_x = mgr.get_pulse_waveforms(xid)

        base = mgr._perm.pulses[xid]
        marker = base.get("digital_marker", "ON")

        # Build padded complex template
        w0 = _as_padded_complex(I_x, Q_x, pad_to_4=True)
        N = len(w0)
        T = N * dt

        # Amplitude scaling with d_lambda correction
        lam0 = (np.pi / (2.0 * T)) if T != 0.0 else 1.0
        amp_scale = (self.theta / np.pi) * (1.0 + self.d_lambda / lam0)

        # Phase rotation
        phi_eff = self.phi + self.d_alpha
        w_axis = w0 * np.exp(-1j * phi_eff)

        # Frequency modulation via d_omega (centered time array)
        if self.d_omega != 0.0:
            t = (np.arange(N) - (N - 1) / 2.0) * dt
            w_axis = w_axis * np.exp(1j * self.d_omega * t)

        w_new = amp_scale * w_axis

        I_new = np.real(w_new).astype(float)
        Q_new = np.imag(w_new).astype(float)

        # Clip protection
        amp = np.maximum(np.abs(I_new), np.abs(Q_new))
        if np.any(amp > MAX_AMPLITUDE):
            scale = MAX_AMPLITUDE / float(np.max(amp))
            I_new *= scale
            Q_new *= scale

        return I_new, Q_new, N, marker

    def build(self, *, hw_ctx) -> None:
        mgr = hw_ctx.mgr

        I_new, Q_new, length, marker = self.waveforms(hw_ctx=hw_ctx)

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

    def play(self, *, hw_ctx, align_after: bool = True) -> None:
        from qm import qua
        qua.play(self.op, self.target)
        if align_after:
            qua.align()
