# qubox_v2/gates/hardware/displacement.py
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import warnings

from ..hardware_base import GateHardware

from qubox_v2.analysis.pulseOp import PulseOp
from qubox_v2.core.types import MAX_AMPLITUDE


@dataclass
class DisplacementHardware(GateHardware):
    """
    Hardware backend for cavity displacement.

    Scales a reference calibrated coherent pulse (attr.b_alpha, attr.b_coherent_amp/len).
    """
    alpha: complex
    target: str | None = None
    gate_type: str = "Displacement"

    def __post_init__(self):
        self.alpha = complex(self.alpha)

        if self.target is None:
            self.target = "storage"

        r = f"{self.alpha.real:.3f}".replace(".", "p").replace("-", "m")
        i = f"{self.alpha.imag:.3f}".replace(".", "p").replace("-", "m")
        self.op = f"Disp_r{r}_i{i}"

    def to_dict(self) -> dict:
        return {
            "type": self.gate_type,
            "target": self.target,
            "params": {
                "re": float(np.real(self.alpha)),
                "im": float(np.imag(self.alpha)),
                "op": getattr(self, "op", None),
            },
        }

    @classmethod
    def from_dict(cls, d: dict, *, hw_ctx) -> "DisplacementHardware":
        P = d.get("params", {})
        target = d.get("target", None)
        if target is None:
            attr = getattr(hw_ctx, "attributes", None)
            target = getattr(attr, "st_el", "storage") if attr is not None else "storage"

        obj = cls(alpha=complex(float(P["re"]), float(P["im"])), target=target)
        if P.get("op"):
            obj.op = str(P["op"])
        return obj

    def waveforms(self, *, hw_ctx) -> tuple[np.ndarray, np.ndarray, int, bool | str]:
        mgr = hw_ctx.mgr
        attr = hw_ctx.attributes

        L = int(getattr(attr, "b_coherent_len"))
        marker = True

        I_tpl = np.ones(L, dtype=float) * float(getattr(attr, "b_coherent_amp"))
        Q_tpl = np.zeros(L, dtype=float)

        alpha_ref = complex(getattr(attr, "b_alpha"))
        if abs(alpha_ref) == 0.0:
            raise ValueError("DisplacementHardware: reference b_alpha is 0; cannot scale.")

        ratio = self.alpha / alpha_ref
        c, s = float(np.real(ratio)), float(np.imag(ratio))

        I_new = c * I_tpl - s * Q_tpl
        Q_new = s * I_tpl + c * Q_tpl

        amp = np.maximum(np.abs(I_new), np.abs(Q_new))
        if np.any(amp > MAX_AMPLITUDE):
            scale = MAX_AMPLITUDE / float(np.max(amp))
            I_new *= scale
            Q_new *= scale
            warnings.warn(f"{self.op}: clipped to MAX_AMPLITUDE ({MAX_AMPLITUDE}).")

        return I_new, Q_new, L, marker

    def build(self, *, hw_ctx) -> None:
        mgr = hw_ctx.mgr

        I_new, Q_new, L, marker = self.waveforms(hw_ctx=hw_ctx)

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

    def play(self, *, hw_ctx, align_after: bool = True) -> None:
        from qm import qua
        qua.play(self.op, self.target)
        if align_after:
            qua.align(self.target)

