# qubox_v2/gates/hardware/qubit_rotation.py
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

from ..hardware_base import GateHardware
from ..hash_utils import stable_hash

from qubox_v2.analysis.pulseOp import PulseOp
from qubox_v2.core.types import MAX_AMPLITUDE

@dataclass
class QubitRotationHardware(GateHardware):
    """
    Hardware backend for QubitRotation.

    Uses base calibrated x180/y180 pulses and mixes them to synthesize arbitrary equatorial rotation.
    """
    theta: float
    phi: float
    b_x180_pulse: str = "x180_pulse"
    b_y180_pulse: str = "y180_pulse"
    target: str | None = None

    gate_type: str = "QubitRotation"

    def __post_init__(self):
        self.theta = float(self.theta)
        self.phi = float(self.phi)

        # default target from attributes if not provided
        if self.target is None:
            self.target = "qubit"

        # Op name: keep simple & reproducible (avoid huge float repr)
        # If you want exact old naming, use f"Rotation_{self.theta}_{self.phi}"
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
                "b_x180_pulse": self.b_x180_pulse,
                "b_y180_pulse": self.b_y180_pulse,
                "op": getattr(self, "op", None),
            },
        }

    @classmethod
    def from_dict(cls, d: dict, *, hw_ctx) -> "QubitRotationHardware":
        P = d.get("params", {})
        target = d.get("target", None)
        if target is None:
            attr = getattr(hw_ctx, "attributes", None)
            target = getattr(attr, "qb_el", "qubit") if attr is not None else "qubit"

        obj = cls(
            theta=float(P["theta"]),
            phi=float(P["phi"]),
            b_x180_pulse=str(P.get("b_x180_pulse", "x180_pulse")),
            b_y180_pulse=str(P.get("b_y180_pulse", "y180_pulse")),
            target=target,
        )
        # preserve op if present
        if P.get("op"):
            obj.op = str(P["op"])
        return obj

    # --------------------
    # waveforms / build / play
    # --------------------
    def waveforms(self, *, hw_ctx) -> tuple[np.ndarray, np.ndarray, int, bool | str]:
        mgr = hw_ctx.mgr
        xid = self.b_x180_pulse
        yid = self.b_y180_pulse

        I_x, Q_x = mgr.get_pulse_waveforms(xid)
        I_y, Q_y = mgr.get_pulse_waveforms(yid)

        base = mgr._perm.pulses[xid]
        length = int(base["length"])
        marker = base.get("digital_marker", "ON")

        I_x = np.broadcast_to(np.asarray(I_x, dtype=float), (length,))
        Q_x = np.broadcast_to(np.asarray(Q_x, dtype=float), (length,))
        I_y = np.broadcast_to(np.asarray(I_y, dtype=float), (length,))
        Q_y = np.broadcast_to(np.asarray(Q_y, dtype=float), (length,))

        # mix X and Y bases
        a = self.theta / np.pi
        cx = a * np.cos(self.phi)
        cy = a * np.sin(self.phi)

        I_new = cx * I_x + cy * I_y
        Q_new = cx * Q_x + cy * Q_y

        # clip protection
        amp = np.maximum(np.abs(I_new), np.abs(Q_new))
        if np.any(amp > MAX_AMPLITUDE):
            scale = MAX_AMPLITUDE / float(np.max(amp))
            I_new *= scale
            Q_new *= scale

        return I_new, Q_new, length, marker

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

