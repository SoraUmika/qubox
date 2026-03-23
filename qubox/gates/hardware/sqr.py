# qubox_v2/gates/hardware/sqr.py
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

from ..hardware_base import GateHardware
from ..hash_utils import array_md5

from qubox.analysis.pulseOp import PulseOp


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


def _resolve_fock_detunings(att, n_levels, *, from_chi=None):
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
class SQRHardware(GateHardware):
    """
    Hardware backend for SQR (Selective Qubit Rotation) waveform synthesis.

    Uses a single calibrated selective-X reference template and complex
    rotation, matching the legacy SQR convention:

        w0 = pad_to_4(I_ref + 1j*Q_ref)
        t = centered_time_array
        phi_eff = phi_n + d_alpha_n
        scale = (theta_n / pi) * (1.0 + d_lambda_n / lam0)
        w_axis = w0 * exp(-1j * phi_eff)
        w_tot += scale * w_axis * exp(1j * omega_n * t)
    """
    thetas: np.ndarray
    phis: np.ndarray
    d_lambda: np.ndarray
    d_alpha: np.ndarray
    d_omega: np.ndarray

    ref_sel_x180_pulse: str = "sel_x180_pulse"
    fock_fqs_from_chi: bool = False

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
                "ref_sel_x180_pulse": self.ref_sel_x180_pulse,
                "fock_fqs_from_chi": bool(self.fock_fqs_from_chi),
                "op": getattr(self, "op", None),
            },
        }

    @classmethod
    def from_dict(cls, d: dict, *, hw_ctx) -> "SQRHardware":
        P = d.get("params", {})
        target = d.get("target", None)
        if target is None:
            snapshot = getattr(hw_ctx, "context_snapshot", None)
            attr = snapshot() if callable(snapshot) else None
            target = getattr(attr, "qb_el", "qubit") if attr is not None else "qubit"

        # Support legacy serialized keys
        ref_pulse = str(P.get("ref_sel_x180_pulse", P.get("b_x180_pulse", "sel_x180_pulse")))

        obj = cls(
            thetas=np.asarray(P["thetas"], dtype=float),
            phis=np.asarray(P["phis"], dtype=float),
            d_lambda=np.asarray(P.get("d_lambda", np.zeros_like(P["thetas"])), dtype=float),
            d_alpha=np.asarray(P.get("d_alpha", np.zeros_like(P["thetas"])), dtype=float),
            d_omega=np.asarray(P.get("d_omega", np.zeros_like(P["thetas"])), dtype=float),
            ref_sel_x180_pulse=ref_pulse,
            fock_fqs_from_chi=bool(P.get("fock_fqs_from_chi", False)),
            target=target,
        )
        if P.get("op"):
            obj.op = str(P["op"])
        return obj

    def waveforms(self, *, hw_ctx, from_chi: bool | None = None, d_omega_is_hz: bool = False
                  ) -> tuple[np.ndarray, np.ndarray, int, bool | str]:
        mgr = hw_ctx.mgr
        att = hw_ctx.context_snapshot()

        dt = float(getattr(att, "dt_s", 1e-9))

        xid = self.ref_sel_x180_pulse
        I_x0, Q_x0 = mgr.get_pulse_waveforms(xid)

        # Build padded complex template
        w0 = _as_padded_complex(I_x0, Q_x0, pad_to_4=True)
        N = len(w0)
        T_sel = N * dt

        # Centered time array (matching legacy convention)
        t = (np.arange(N) - (N - 1) / 2.0) * dt

        marker = mgr._perm.pulses[xid].get("digital_marker", "ON")

        max_n = min(self.thetas.size, int(getattr(att, "max_fock_level", self.thetas.size - 1)) + 1)

        # Resolve per-Fock detunings
        if from_chi is None:
            from_chi = self.fock_fqs_from_chi or not (
                hasattr(att, "fock_fqs") and (getattr(att, "fock_fqs") is not None)
            )
        omega_det = _resolve_fock_detunings(att, max_n, from_chi=from_chi)

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

            # Rotate template in IQ plane by phi_eff (legacy convention: exp(-1j * phi_eff))
            w_axis = w0 * np.exp(-1j * phi_eff)

            # Digital modulation for the nth tone
            w_tot += scale * w_axis * np.exp(1j * (omega_n * t))

        I_tot = np.real(w_tot).astype(float)
        Q_tot = np.imag(w_tot).astype(float)

        return I_tot, Q_tot, N, marker

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
