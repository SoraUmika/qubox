# drive_builder.py
import numpy as np
from math import erf, sqrt, pi
from typing import Optional, Dict, Tuple, List, Callable, Sequence, Any, Union
from .cQED import circuitQED  # type: ignore[import]
import math
import copy

def _read_duration_strict(drive: Dict[str, Any]) -> float:
    ep = drive.get("envelope_params")
    if not isinstance(ep, dict):
        raise KeyError(f"{drive.get('name','<unnamed>')}: missing envelope_params dict.")
    # Accept either 'duration' or 'Duration' (normalize to float)
    if "duration" in ep:
        dur = ep["duration"]
    elif "Duration" in ep:
        dur = ep["Duration"]
    else:
        raise KeyError(f"{drive.get('name','<unnamed>')}: missing 'duration'/'Duration' in envelope_params.")
    dur = float(dur)
    if not math.isfinite(dur) or dur <= 0.0:
        raise ValueError(f"{drive.get('name','<unnamed>')}: duration must be positive, got {dur}.")
    return dur

def chain_drives_strict(
    drives: Sequence[Dict[str, Any]],
    *, t0: float = 0.0,
    gap: Union[float, Sequence[float]] = 0.0,
) -> Tuple[List[Dict[str, Any]], float]:
    if not drives:
        return [], float(t0)

    # normalize gaps
    if isinstance(gap, (int, float)):
        gaps = [float(gap)] * (len(drives) - 1)
    else:
        gaps = list(map(float, gap))
        if len(gaps) != len(drives) - 1:
            raise ValueError("gap list must have length len(drives)-1")

    out: List[Dict[str, Any]] = []
    cursor = float(t0)

    for i, drv in enumerate(drives):
        d  = copy.deepcopy(drv)
        ep = d.setdefault("envelope_params", {})

        # read & normalize duration
        dur = _read_duration_strict(d)      # your existing helper
        ep["duration"] = float(dur)
        ep.pop("Duration", None)

        # retime
        old_ts = float(ep.get("t_start", 0.0))
        ep["t_start"] = cursor
        dt_shift = cursor - old_ts

        # --- move the base shape as well ---
        env_type = d.get("envelope_type", None)

        if callable(env_type):
            # shift the time seen by the original callable
            orig = env_type
            def shifted_env(t, args, _orig=orig, _dt=dt_shift):
                return _orig(t - _dt, args)
            d["envelope_type"] = shifted_env

        elif isinstance(env_type, str) and env_type.lower() == "gaussian":
            # keep the Gaussian center relative to its start
            # default center was old_ts + 0.5*dur unless 't0' was specified
            old_center = float(ep.get("t0", old_ts + 0.5*dur))
            rel_center = old_center - old_ts
            ep["t0"]   = cursor + rel_center   # preserve relative center

        # advance
        out.append(d)
        cursor += dur
        if i < len(drives) - 1:
            cursor += gaps[i]

    return out, cursor


def validate_no_overlap_strict(drives: Sequence[Dict[str, Any]]) -> None:
    """Sanity check: no pulse starts before the previous ends (based on duration)."""
    spans = []
    for d in drives:
        ep = d.get("envelope_params", {})
        ts = float(ep.get("t_start", None))
        if ts is None:
            raise KeyError(f"{d.get('name','<unnamed>')}: missing t_start after scheduling.")
        dur = _read_duration_strict(d)
        spans.append((ts, ts + dur, d.get("name", "<unnamed>")))
    spans.sort(key=lambda x: x[0])
    for (s0, e0, n0), (s1, e1, n1) in zip(spans, spans[1:]):
        if s1 < e0 - 1e-15:
            raise RuntimeError(f"Overlap: '{n1}' starts at {s1:.3e}s before '{n0}' ends at {e0:.3e}s.")
        
class DriveGenerator:
    """
    Build drive dictionaries compatible with circuitQED._collect_terms:
      { "name", "channel", "carrier_freq", "amplitude", "envelope_type",
        "envelope_params", "encoding" }
    Frequencies are ANGULAR (rad/s). Time is in seconds. â„ = 1.
    """
    def __init__(self, sys: "circuitQED"):
        self.sys = sys

    # ------------------------ helpers ------------------------
    @staticmethod
    def _integral_constant(duration: float, t_rise: float = 0.0, t_fall: Optional[float] = None) -> float:
        """Exact integral of the 'constant' base shape under the cosine ramps used in circuitQED._drive_envelope()."""
        t_fall = t_rise if (t_fall is None) else float(t_fall)
        return max(0.0, duration - 0.5*(t_rise + t_fall))

    @staticmethod
    def _integral_gaussian(t_start: float, duration: float, t0: float, sigma: float) -> float:
        """
        Exact integral of exp(-(t - t0)^2/(2Ïƒ^2)) over [t_start, t_start+duration].
        (Does not include additional cosine rampsâ€”set ramps=0 for Gaussian.)
        """
        a = (t_start - t0) / (sqrt(2.0)*sigma)
        b = (t_start + duration - t0) / (sqrt(2.0)*sigma)
        return sqrt(pi/2.0) * sigma * (erf(b) - erf(a))

    def idle(self,
             duration: float,
             t0: float = 0.0,
             *,
             channel: str = "qubit",            # "qubit" or "cavity"
             name: Optional[str] = None,
             carrier: Optional[float] = None) -> Dict:
        """
        Return a 'do nothing' drive occupying [t0, t0+duration] with zero amplitude.
        Useful for inserting gaps while keeping scheduling/plotting machinery happy.

        Parameters
        ----------
        duration : float
            Positive duration in seconds.
        t0 : float
            Start time in seconds.
        channel : {"qubit","cavity"}
            Which channel timeline this idle belongs to (for bookkeeping/plots).
        name : Optional[str]
            Custom name; if None, an informative default is used.
        carrier : Optional[float]
            Override carrier frequency (rad/s). Defaults to system wq/wc for the channel.

        Returns
        -------
        Dict
            Drive dictionary compatible with circuitQED._collect_terms.
        """
        dur = float(duration)
        if not math.isfinite(dur) or dur <= 0.0:
            raise ValueError(f"idle(): duration must be positive, got {duration!r}.")

        ch = channel.lower()
        if ch not in ("qubit", "cavity"):
            raise ValueError("idle(): channel must be 'qubit' or 'cavity'.")

        if carrier is None:
            w = float(self.sys.wq) if ch == "qubit" else float(self.sys.wc)
        else:
            w = float(carrier)

        return {
            "name": name or f"idle_{ch}_T{dur*1e9:.1f}ns",
            "channel": ch,
            "carrier_freq": w,                # irrelevant since amplitude=0, but kept for consistency
            "amplitude": 0.0,                 # ensures zero contribution regardless of encoding/envelope
            "envelope_type": "constant",      # simple constant window with zero amplitude
            "envelope_params": {
                "t_start": float(t0),
                "duration": dur,
                "t_rise": 0.0,
                "t_fall": 0.0
            },
            "encoding": "iq",
        }

    def qubit_rotation_tp(self,
                          theta: float,             # rotation angle (rad)
                          phi: float,               # azimuth of rotation axis (rad); 0â†’x, pi_val/2â†’y
                          duration: float,          # gate time (s)
                          t0: float = 0.0,
                          shape: str = "constant",  # "constant" or "gaussian"
                          shape_params: Optional[dict] = None,
                          name: Optional[str] = None,
                          carrier: Optional[float] = None) -> Dict:
        """
        Implements U = exp[-i (Î¸/2) (cosphi Ïƒ_x + sinphi Ïƒ_y)] using a single IQ envelope.
        Area convention: Î¸ = 2 âˆ« A(t) dt, with complex baseband A(t) = |A| e^{iphi} * shape(t).
        """
        shape_params = shape_params or {}
        w = float(self.sys.wq) if (carrier is None) else float(carrier)

        area = float(theta) / 2.0  # Î¸ = 2 âˆ« A dt
        phi  = float(phi)

        if shape == "constant":
            t_rise = float(shape_params.get("t_rise", 0.0))
            t_fall = float(shape_params.get("t_fall", t_rise))
            integral = self._integral_constant(duration, t_rise, t_fall)
            if integral <= 0:
                raise ValueError("Non-positive effective duration for constant shape.")
            A_mag = area / integral
            env_type = "constant"
            env = {"t_start": t0, "duration": duration, "t_rise": t_rise, "t_fall": t_fall}

        elif shape == "gaussian":
            sigma = float(shape_params.get("sigma", max(1e-12, duration/6.0)))
            tcen  = float(shape_params.get("t0", t0 + 0.5*duration))
            integral = self._integral_gaussian(t0, duration, tcen, sigma)
            if integral <= 0:
                raise ValueError("Zero/negative Gaussian integralâ€”check sigma/timing.")
            A_mag = area / integral
            env_type = "gaussian"
            env = {"t_start": t0, "duration": duration, "t0": tcen, "sigma": sigma,
                   "t_rise": 0.0, "t_fall": 0.0}
        else:
            raise ValueError("shape must be 'constant' or 'gaussian'.")

        return {
            "name": name or f"qubit_rot_tp_theta{theta:.6f}_phi{phi:.6f}_T{duration*1e9:.1f}ns",
            "channel": "qubit",
            "carrier_freq": w,
            "amplitude": A_mag * np.exp(1j*phi),
            "envelope_type": env_type,
            "envelope_params": env,
            "encoding": "iq",
            "type": "rotation"
        }

    # ---------------------- 4b) SQR (Î¸_n, phi_n; equatorial axes) ----------------------
    def sqr_tp(self,
               thetas: np.ndarray,                 # per-Fock rotation angles Î¸_n (rad)
               phis:   np.ndarray,                 # per-Fock azimuths phi_n (rad) for axes
               T: float,                           # selective window duration (s)
               *,
               d_lambda: Optional[np.ndarray] = None,  # per-n amplitude tweak
               d_alpha:  Optional[np.ndarray] = None,  # per-n phase tweak
               d_omega:  Optional[np.ndarray] = None,  # per-n detuning tweak [rad/s]
               t0: float = 0.0,
               name: str = "SQR(tp)",
               shape: str = "gaussian",            # selective; 6Ïƒ â‰ˆ T by default
               shape_params: Optional[dict] = None,
               carrier: Optional[float] = None
        ) -> Dict:
        """
        Multi-tone selective qubit rotation:
          U_n = exp[-i (Î¸_n/2) (cosphi_n Ïƒ_x + sinphi_n Ïƒ_y)] acting only when the cavity is in |n>.
        Uses a single selective Gaussian window. Zeros in Î¸_n act as spectators.

        Baseband per-tone envelope:
          A_n(t) = (Î»_n + dÎ»_n) * g(t) * exp[ +i(phi_n + dalpha_n) ] * exp[ -i (nchi_val + domega_n) (t - t_mid) ],
        with Î»_n chosen so that 2 * âˆ« g(t) dt * Î»_n = Î¸_n.
        """
        import math
        shape_params = shape_params or {}

        thetas = np.asarray(thetas, float)
        phis   = np.asarray(phis,   float)
        if phis.size not in (1, thetas.size):
            raise ValueError("phis must be scalar or match len(thetas).")
        if phis.size == 1:
            phis = np.full_like(thetas, float(phis))

        L = int(thetas.size)

        d_lambda = np.zeros(L, dtype=float) if d_lambda is None else np.asarray(d_lambda, float)
        d_alpha  = np.zeros(L, dtype=float) if d_alpha  is None else np.asarray(d_alpha,  float)
        d_omega  = np.zeros(L, dtype=float) if d_omega  is None else np.asarray(d_omega,  float)
        if d_lambda.size != L or d_alpha.size != L or d_omega.size != L:
            raise ValueError("d_lambda/d_alpha/d_omega must all match len(thetas).")

        wq  = float(self.sys.wq) if (carrier is None) else float(carrier)
        chi = -float(getattr(self.sys, "chi", 0.0))  # keep same sign convention as snap()

        if shape.lower() != "gaussian":
            raise NotImplementedError("sqr_tp() supports shape='gaussian' only (selective).")

        sigma = float(shape_params.get("sigma", max(1e-12, T/6.0)))
        t_mid = float(shape_params.get("t0", t0 + 0.5*T))

        def g_sel(t):
            return np.exp(-(t - t_mid)**2/(2.0*sigma**2))

        # Finite-window area of the Gaussian over [t0, t0+T]
        z    = T / (2.0*np.sqrt(2.0)*sigma)
        A_g  = np.sqrt(2.0*np.pi)*sigma*math.erf(z)

        # Set per-tone amplitudes to realize Î¸_n: Î¸_n = 2 Î»_n A_g
        lam0 = thetas / (2.0 * A_g)

        # Effective phases & detunings
        alp  = phis + d_alpha
        delt = (np.arange(L, dtype=float) * chi) + d_omega

        def sqr_env(t, _args=None):
            return g_sel(t) * np.sum(
                (lam0 + d_lambda) * np.exp(1j * alp) * np.exp(-1j * delt * (t - t_mid))
            )

        drive = {
            "name": name,
            "channel": "qubit",
            "carrier_freq": wq,
            "amplitude": 1.0,               # callable returns complex baseband
            "envelope_type": sqr_env,       # callable IQ envelope
            "envelope_params": {
                "t_start": float(t0),
                "duration": float(T),
                "t_rise": 0.0,
                "t_fall": 0.0
            },
            "encoding": "iq",
            "params": {"thetas": thetas, "phis": phis},
            "type": "SQR"
        }
        return drive
    # ------------------ 1) QUBIT ROTATION --------------------
    def qubit_rotation(self,
                       angle: float,                # rotation angle (rad), e.g. pi_val for 180Â°
                       duration: float,             # gate time (s)
                       axis: str = "x",             # "x", "y" or "phase" (use 'phase' + phase)
                       phase: Optional[float] = None,  # radians; if None, uses axis â†’ 0 or +pi_val/2
                       t0: float = 0.0,
                       shape: str = "constant",     # "constant" or "gaussian"
                       shape_params: Optional[dict] = None,
                       name: Optional[str] = None,
                       carrier: Optional[float] = None) -> Dict:
        """
        Returns a drive dict for a qubit rotation using IQ encoding.
        Conventions: in the rotating frame, H = A(t) b + A*(t) bâ€ , so a real A gives Ïƒ_x.
        For a constant A, rotation angle Î¸ = 2 * âˆ« A dt  â‡’  A_const = Î¸/(2*duration).
        """
        shape_params = shape_params or {}
        w = float(self.sys.wq) if (carrier is None) else float(carrier)

        # axis / phase
        if phase is None:
            axis = axis.lower()
            if axis == "x":   phi = 0.0
            elif axis == "y": phi = +0.5*np.pi
            elif axis == "phase":
                raise ValueError("axis='phase' requires explicit 'phase' value")
            else:
                raise ValueError("axis must be 'x','y', or 'phase'")
        else:
            phi = float(phase)

        # area needed in baseband units
        area = float(angle) / 2.0  # since Î¸ = 2 âˆ« A dt

        if shape == "constant":
            t_rise = float(shape_params.get("t_rise", 0.0))
            t_fall = float(shape_params.get("t_fall", t_rise))
            integral = self._integral_constant(duration, t_rise, t_fall)
            if integral <= 0:
                raise ValueError("Non-positive effective duration for constant shape.")
            A_mag = area / integral
            env_type = "constant"
            env = {"t_start": t0, "duration": duration, "t_rise": t_rise, "t_fall": t_fall}

        elif shape == "gaussian":
            # default: 4Ïƒ = duration
            sigma = float(shape_params.get("sigma", max(1e-12, duration/6.0)))
            tcen  = float(shape_params.get("t0", t0 + 0.5*duration))
            integral = self._integral_gaussian(t0, duration, tcen, sigma)
            if integral <= 0:
                raise ValueError("Zero/negative Gaussian integralâ€”check sigma/timing.")
            A_mag = area / integral
            env_type = "gaussian"
            env = {"t_start": t0, "duration": duration, "t0": tcen, "sigma": sigma,
                   "t_rise": 0.0, "t_fall": 0.0}  # ramps off for Gaussian

        else:
            raise ValueError("shape must be 'constant' or 'gaussian'.")

        return {
            "name": name or f"qubit_rot_{axis}_{angle:.6f}_T{duration*1e9:.1f}ns",
            "channel": "qubit",
            "carrier_freq": w,
            "amplitude": A_mag * np.exp(1j*phi),  # complex baseband
            "envelope_type": env_type,
            "envelope_params": env,
            "encoding": "iq",
            "type": "rotation"
        }

    # ---------------- 2) CAVITY DISPLACEMENT -----------------
    def cavity_displacement(self,
                            beta: complex,           # target complex displacement (dimensionless cavity alpha)
                            duration: float,
                            t0: float = 0.0,
                            detuning: float = 0.0,   # Deltaomega from wc (rad/s); usually 0
                            shape: str = "constant",
                            shape_params: Optional[dict] = None,
                            name: Optional[str] = None,
                            carrier: Optional[float] = None) -> Dict:
        """
        Displacement under H = A(t) a e^{-iomegat} + A*(t) aâ€  e^{+iomegat}.
        In the cavity rotating frame, dâŸ¨aâŸ©/dt = -i A*(t). To get DeltaâŸ¨aâŸ© = Î², we need âˆ« A(t) dt = -i Î²*.
        This picks the complex amplitude so the time integral equals -i*conj(beta).
        """
        shape_params = shape_params or {}
        w = float(self.sys.wc) if (carrier is None) else float(carrier)
        w = w + float(detuning)

        target_area = -1j * np.conj(beta)  # âˆ« A dt must equal this

        if shape == "constant":
            t_rise = float(shape_params.get("t_rise", 0.0))
            t_fall = float(shape_params.get("t_fall", t_rise))
            integral = self._integral_constant(duration, t_rise, t_fall)
            if integral <= 0:
                raise ValueError("Non-positive effective duration for constant shape.")
            A = target_area / integral
            env_type = "constant"
            env = {"t_start": t0, "duration": duration, "t_rise": t_rise, "t_fall": t_fall}

        elif shape == "gaussian":
            sigma = float(shape_params.get("sigma", max(1e-12, duration/4.0)))
            tcen  = float(shape_params.get("t0", t0 + 0.5*duration))
            integral = self._integral_gaussian(t0, duration, tcen, sigma)
            if integral <= 0:
                raise ValueError("Zero/negative Gaussian integralâ€”check sigma/timing.")
            A = target_area / integral
            env_type = "gaussian"
            env = {"t_start": t0, "duration": duration, "t0": tcen, "sigma": sigma,
                   "t_rise": 0.0, "t_fall": 0.0}
        else:
            raise ValueError("shape must be 'constant' or 'gaussian'.")

        # Optional: center-of-window phase compensation for detuning (keep displacement phase referenced at mid-point)
        if detuning != 0.0:
            A = A * np.exp(-1j * detuning * (0.5*duration))

        return {
            "name": name or f"cav_disp_{beta.real:+.3f}{beta.imag:+.3f}i_T{duration*1e9:.1f}ns",
            "channel": "cavity",
            "carrier_freq": w,
            "amplitude": A,
            "envelope_type": env_type,
            "envelope_params": env,
            "encoding": "iq",
            "params": {"beta": beta},
            "type": "DISPLACEMENT"
        }

        # ---------------------- 3) SNAP --------------------------
    def snap(self,
            thetas: np.ndarray,          # Î¸_n for n=0..L-1 (phase-imparting stage)
            T: float,                    # duration of ONE selective Gaussian (s)
            d_lambda: Optional[np.ndarray] = None,
            d_alpha:  Optional[np.ndarray] = None,
            d_omega:  Optional[np.ndarray] = None,   # per-n detuning tweak [rad/s]
            t0: float = 0.0,
            name: str = "SNAP/single",
            include_unselective: bool = False,
            T_pi: Optional[float] = None,            # unselective (fast) pi_val/2 pulse length (s), default 24 ns
            unselective_axis: str = "x",
            unselective_gain = 1.0,
            t_gap: float = 0.0
        ) -> Dict:
        """
        One-drive SNAP:
            Stage-1:  fast pi_val/2 comb (if include_unselective) OR selective pi_val/2
            gap
            Stage-2:  selective pi_val/2 with per-n phase thetas (phase-imparting)

        â€¢ Unselective stage (include_unselective=True): a *sum over tones* at
        omega_q + nchi_val for n = 0..Nc-1, all using the same short Gaussian and per-tone
        area = pi_val/2 (scaled by `unselective_gain`). This guarantees |g,n> â†’ |e,n>
        ideally for each addressed n.
        â€¢ Selective stages use a Gaussian of length T (6Ïƒ = T) with per-tone area pi_val/2.
        """
        import math
        thetas = np.asarray(thetas, float)
        L = len(thetas)
        d_lambda = np.zeros(L) if d_lambda is None else np.asarray(d_lambda, float)
        d_alpha  = np.zeros(L) if d_alpha  is None else np.asarray(d_alpha,  float)
        d_omega  = np.zeros(L) if d_omega  is None else np.asarray(d_omega,  float)

        wq  = float(self.sys.wq)
        chi = -float(getattr(self.sys, "chi", 0.0))
        Nc  = int(getattr(self.sys, "Nc", L))  # use system cavity truncation as comb size

        # ------------ Gaussian helpers + per-tone pi_val/2 calibration ------------
        # Selective Gaussian (length T: 6Ïƒ = T)
        sigma_sel = T/6.0
        def g_sel(t, tm): return np.exp(-(t - tm)**2/(2.0*sigma_sel**2))

        z_sel    = T / (2.0*np.sqrt(2.0)*sigma_sel)
        area_sel = np.sqrt(2.0*np.pi)*sigma_sel*math.erf(z_sel)   # finite-window area
        lam0     = np.pi/(2.0*area_sel)                           # per-tone amplitude â†’ pi_val/2 area

        # ---------------- timing ----------------
        if include_unselective:
            Tpi = 24e-9 if (T_pi is None) else float(T_pi)
            t1_start, t1_dur = t0, Tpi
            t2_start, t2_dur = t1_start + t1_dur + t_gap, T
            T_total = t1_dur + t_gap + t2_dur
        else:
            # two selective pi_val/2 stages (legacy)
            t1_start, t1_dur = t0, T
            t2_start, t2_dur = t1_start + t1_dur + t_gap, T
            T_total = t1_dur + t_gap + t2_dur

        t1_mid = t1_start + 0.5*t1_dur
        t2_mid = t2_start + 0.5*t2_dur

        # ---------------- detunings & weights ----------------
        nL      = np.arange(L, dtype=float)
        delta1  = nL*chi                       # stage-1 detunings (if selective)
        delta2  = nL*chi + d_omega             # stage-2 detunings (phase-imparting)
        lam2    = lam0 + d_lambda
        alp2    = thetas + d_alpha

        # ------------- UNSELECTIVE = multi-tone fast pi_val/2 comb ----------------
        if include_unselective:
            # axis choice: xâ†’0, yâ†’+pi_val/2 (IQ convention A = |A| e^{iphi})
            phi_unsel = 0.0 if (unselective_axis.lower() == "x") else (np.pi/2)

            sigma_u = t1_dur/6.0
            z_u     = t1_dur / (2.0*np.sqrt(2.0)*sigma_u)
            area_u  = np.sqrt(2.0*np.pi)*sigma_u*math.erf(z_u)
            Om_pi   = np.pi/(2.0*area_u)   # per-tone amplitude for pi_val/2 area

            # Detuning set for the comb: n = 0..Nc-1
            nU     = np.arange(Nc, dtype=float)
            deltaU = nU * chi

            def g_unsel(t): return np.exp(-(t - t1_mid)**2/(2.0*sigma_u**2))
        else:
            phi_unsel = 0.0
            Om_pi = 0.0
            deltaU = np.array([0.0])
            def g_unsel(t): return 0.0

        # -------- single callable envelope over [t0, t0+T_total] --------
        def snap_env(t, _args=None):
            A = 0.0 + 0.0j

            if include_unselective:
                # Multi-tone sum: same short Gaussian, same per-tone pi_val/2 area
                # Centered at t1_mid so the complex exponentials are (t - t1_mid).
                A += unselective_gain * np.exp(1j*phi_unsel) * g_unsel(t) * np.sum(
                    Om_pi * np.exp(-1j * deltaU * (t - t1_mid))
                )
            else:
                # Selective pi_val/2 (legacy): sum over tones up to L
                A += g_sel(t, t1_mid) * lam0 * np.sum(np.exp(-1j * delta1 * (t - t1_mid)))

            # Phase-imparting selective pi_val/2 (minus sign follows your convention)
            A -= g_sel(t, t2_mid) * np.sum(
                lam2 * np.exp(1j*alp2) * np.exp(-1j * delta2 * (t - t2_mid))
            )
            return A

        drive = {
            "name": name,
            "channel": "qubit",
            "carrier_freq": wq,                 # single qubit carrier
            "amplitude": 1.0,                   # callable returns complex baseband A(t)
            "envelope_type": snap_env,          # callable IQ envelope
            "envelope_params": {
                "t_start": t0,
                "duration": T_total,
                "t_rise": 0.0,
                "t_fall": 0.0
            },
            "encoding": "iq",
            "params": {"thetas": thetas},
            "type": "SNAP"
        }
        return drive

    # ---------------- utility ----------------
    def add(self, drive_def: Dict) -> None:
        """Append a drive dictionary to the system (helper)."""
        self.sys.drives.append(drive_def)

import numpy as np
import matplotlib.pyplot as plt
from typing import Optional, Dict, Tuple

def plot_drive_time_and_freq(
    sys: "circuitQED",
    drive_def: Dict,
    dt: Optional[float] = None,          # sample step [s]; default auto (â‰ˆ T/2000)
    t_margin: float = 0.0,               # extra time before/after gate [s]
    mode: str = "lab",                   # "lab" (A e^{-iomegat}) or "baseband" (A)
    window: str = "hann",                # None | "hann" | "hamming"
    zero_pad: int = 0,                   # extra zeros appended (for FFT interpolation)
    db: bool = False,                    # plot frequency magnitude in dB
    freq_unit: str = "MHz",              # "Hz" | "kHz" | "MHz" | "GHz"
    iq_time: bool = True,                # plot I (real) and Q (imag) in time
    show_phase: bool = False,            # also plot instantaneous phase in time
    title: Optional[str] = None,
    freq_range: Optional[Tuple[float, float]] = None,  # (fmin, fmax) in freq_unit
) -> Tuple[plt.Axes, plt.Axes]:
    """
    Time & frequency plots for a single drive dict.

    Time trace:
      - baseband: A(t) = complex envelope from sys._drive_envelope
      - lab:      x(t) = A(t) * exp(-i * omega_carrier * t)

    Frequency trace:
      - FFT with chosen window; frequency axis centered (fftshift).
      - Magnitude scaled by dt so units are consistent (area-preserving).
      - Use `freq_range=(fmin,fmax)` (in freq_unit) to zoom the spectrum.
    """
    # ---- pull timing from drive ----
    p = drive_def.get("envelope_params", {}) or {}
    t0 = float(p.get("t_start", 0.0))
    T  = float(p.get("duration", 0.0))
    if T <= 0:
        raise ValueError("Drive has non-positive duration.")

    # sampling grid
    if dt is None:
        dt = max(1e-12, T/2000.0)  # ~2000 samples across the pulse by default
    t_start = t0 - max(0.0, t_margin)
    t_stop  = t0 + T + max(0.0, t_margin)
    t = np.arange(t_start, t_stop, dt)
    if t.size < 8:
        t = np.linspace(t_start, t_stop, 1024)
        dt = float(t[1]-t[0])

    # ---- build complex waveform ----
    A = np.array([sys._drive_envelope(tt, drive_def, args={}) for tt in t], dtype=complex)
    wcar = float(drive_def.get("carrier_freq", 0.0))
    if mode.lower() in ("lab","rf","carrier"):
        x = A * np.exp(-1j * wcar * t)
    elif mode.lower() in ("baseband","env","iq"):
        x = A
    else:
        raise ValueError("mode must be 'lab' or 'baseband'")

    # ---- window & zero-pad for FFT ----
    n = len(x)
    if window is None:
        win = np.ones(n)
    else:
        wname = window.lower()
        if wname == "hann":
            win = np.hanning(n)
        elif wname == "hamming":
            win = np.hamming(n)
        else:
            raise ValueError("window âˆˆ {None,'hann','hamming'}")

    xw = x * win
    if zero_pad > 0:
        xw = np.pad(xw, (0, int(zero_pad)), mode="constant")
    N = len(xw)

    # ---- FFT (properly scaled) ----
    X = np.fft.fftshift(np.fft.fft(xw)) * dt
    freqs = np.fft.fftshift(np.fft.fftfreq(N, d=dt))  # Hz

    # unit conversion
    scale = {"Hz":1.0, "kHz":1e-3, "MHz":1e-6, "GHz":1e-9}[freq_unit]
    f_plot = freqs * scale

    mag = np.abs(X)
    if db:
        yfreq = 20.0*np.log10(np.maximum(mag, 1e-18))
        ylab = "Magnitude [dB]"
    else:
        mmax = np.max(mag) if mag.size else 1.0
        yfreq = mag / (mmax if mmax > 0 else 1.0)
        ylab = "Normalized |FFT|"

    # ---- plotting ----
    fig, (ax_t, ax_f) = plt.subplots(1, 2, figsize=(11, 3.6))

    # Time plot
    tt_ns = (t - t0) * 1e9
    if iq_time:
        ax_t.plot(tt_ns, x.real, label="I(t)")
        ax_t.plot(tt_ns, x.imag, linestyle="--", label="Q(t)")
        ax_t.set_ylabel("Amplitude (arb.)")
    else:
        ax_t.plot(tt_ns, np.abs(x), label="|x(t)|")
        ax_t.set_ylabel("|x(t)| (arb.)")

    if show_phase:
        ax_p = ax_t.twinx()
        ax_p.plot(tt_ns, np.unwrap(np.angle(x)), linestyle=":", label="phase")
        ax_p.set_ylabel("Phase [rad]")

    ax_t.set_xlabel("Time relative to t_start [ns]")
    ax_t.grid(True, alpha=0.3)
    ax_t.legend(fontsize=9, loc="best")

    # Frequency plot
    ax_f.plot(f_plot, yfreq, label=f"Spectrum ({mode})")
    ax_f.set_xlabel(f"Frequency offset [{freq_unit}]")
    ax_f.set_ylabel(ylab)
    ax_f.grid(True, alpha=0.3)
    ax_f.legend(fontsize=9, loc="best")

    # ---- range zoom (in freq_unit) ----
    if freq_range is not None:
        fmin, fmax = float(freq_range[0]), float(freq_range[1])
        if fmin >= fmax:
            raise ValueError("freq_range must be (fmin, fmax) with fmin < fmax.")
        ax_f.set_xlim(fmin, fmax)

    if title:
        fig.suptitle(title, y=1.02)

    plt.tight_layout()
    return ax_t, ax_f
