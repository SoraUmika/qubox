#circitQED.py
import numpy as np
import qutip as qt
from tqdm import tqdm
import matplotlib.pyplot as plt
from typing import Callable, Dict, List, Tuple, Optional, Union, Sequence
from dataclasses import dataclass, field
import scipy.sparse as sp
from .hamiltonian_builder import build_rotated_hamiltonian
# -----------------------------------------------------------------------------
# High-level notes (applies to the whole file)
# -----------------------------------------------------------------------------
# • Units: all frequencies are ANGULAR (rad/s). We set ℏ = 1, so H has units of rad/s.
# • Model: cavity mode a, weakly-anharmonic qubit (transmon truncation) b.
# • Drives: represented as complex exponentials; a "cosine" drive gets split into ±ω parts.
# • Rotating frame: we build H'(t) = U†(t) H(t) U(t) − F with U(t) = exp(−i F t).
#   In the eigenbasis of F, each matrix element |i><j| picks up a phase e^(−i(d_i − d_j)t).
# • RWA: optional filter that drops fast-rotating terms with |ω_eff| above a cutoff.
# -----------------------------------------------------------------------------

@dataclass
class Term:
    op: qt.Qobj                            
    omega: float                            
    envelope: Callable[[float, dict], complex]  
    charges: Dict[str, int] = field(default_factory=dict)
    label: str = ""

Frames = Dict[str, Tuple[float, qt.Qobj]]

# -----------------------------------------------------------------------------
# circuitQED: cavity–transmon model and utilities
# -----------------------------------------------------------------------------
class circuitQED:
    def __init__(self, cavity_freq=0, qubit_freq=0, qubit_anharmonicity=0, cavity_T=None, 
                 qubit_T1=None, qubit_T2=None, Nc=5, Nq=2, chi=0, chi2=0, kerr=0, kerr2=0, drives={}):
        """
        Parameters are in angular units (rad/s) except lifetimes T (seconds).
        H_static = ωc a†a + ωq b†b + (α/2) b†2 b2 + χ (a†a)(b†b) + (K/2) a†2 a2.
        Notes:
          • α<0 for transmon Kerr, χ is dispersive cross-Kerr.
          • κ = 1/T_cavity, Γ1 = 1/T1, Γφ = max(0, 1/T2 − 1/(2T1)).
        """
        # Store system parameters.
        self.wc = cavity_freq
        self.wq = qubit_freq
        self.alpha = qubit_anharmonicity
        self.chi = chi
        self.kerr = kerr

        if cavity_T is not None:
            self.kappa = 1.0 / cavity_T
        else:
            self.kappa = 0
        if qubit_T1 is not None:
            self.Γ_1 = 1/qubit_T1
        else:
            self.Γ_1 = 0
        if qubit_T2 is not None:
            invT1 = 0.0 if qubit_T1 is None else 1.0/qubit_T1
            self.Γ_ϕ = max(0.0, 1.0/qubit_T2 - 0.5*invT1)
        else:
            self.Γ_ϕ = 0.0  

        self.Nc = Nc
        self.Nq = Nq
        self.drives: List[dict] = []

        self.H_cavity = self.H_qubit = self.H_anharm = self.H_chi = self.H_kerr = None

        self.proj = {"g": {}, "e": {}}

        self.c_ops = None
        self.iq_mixer_sign = -1
        self._init_system_operators()
    
    def _init_system_operators(self):
        Nc, Nq = int(self.Nc), int(self.Nq)

        # --- identities as proper Qobj ---
        I_cav = qt.qeye(Nc)                      # [[Nc],[Nc]]
        I_qub = qt.qeye(Nq)

        # --- annihilation operators (handle Nc==1 / Nq==1 cleanly) ---
        if Nc >= 2:
            a_cavity = qt.destroy(Nc)
        else:
            # explicit 1x1 zero with dims to avoid tensor oddities
            a_cavity = qt.Qobj(np.zeros((1, 1)), dims=[[1], [1]])

        if Nq >= 2:
            b_transmon = qt.destroy(Nq)
        else:
            b_transmon = qt.Qobj(np.zeros((1, 1)), dims=[[1], [1]])

        # embed into full space
        self.a    = qt.tensor(a_cavity, I_qub)
        self.adag = self.a.dag()
        self.b    = qt.tensor(I_cav, b_transmon)
        self.bdag = self.b.dag()

        self.nc = self.adag * self.a
        self.nq = self.bdag * self.b

        self.H_cavity = self.wc * self.nc
        self.H_qubit  = self.wq * self.nq
        self.H_anharm = (self.alpha / 2.0) * (self.bdag**2) * (self.b**2)
        self.H_chi    = self.chi  * self.nc * self.nq
        self.H_kerr   = (self.kerr / 2.0) * (self.adag**2) * (self.a**2)

        # ---- cavity observables (Nc==1 → trivial but well-typed) ----
        if Nc == 1:
            parity_cav = qt.Qobj(np.array([[1.0]]), dims=[[1],[1]])
        else:
            parity_diag = np.array([1 if (n % 2 == 0) else -1 for n in range(Nc)], dtype=float)
            parity_cav = qt.Qobj(np.diag(parity_diag), dims=[[Nc],[Nc]])
        self.Parity_cavity = qt.tensor(parity_cav, I_qub)
        self.X_cavity = (self.a + self.adag) * 0.5
        self.P_cavity = (self.a - self.adag) / (2.0j)

        if Nq >= 2:
            g = qt.basis(Nq, 0); e = qt.basis(Nq, 1)
            Pg_qubit = g * g.dag(); Pe_qubit = e * e.dag()
            sx_qubit = (g * e.dag() + e * g.dag())
            sy_qubit = (-1j * g * e.dag() + 1j * e * g.dag())
            sz_qubit = (Pe_qubit - Pg_qubit)

            self.Pg = qt.tensor(I_cav, Pg_qubit)
            self.Pe = qt.tensor(I_cav, Pe_qubit)
            self.sx = qt.tensor(I_cav, sx_qubit)
            self.sy = qt.tensor(I_cav, sy_qubit)
            self.sz = qt.tensor(I_cav, sz_qubit)
            self.sigma_plus  = qt.tensor(I_cav, e * g.dag())
            self.sigma_minus = qt.tensor(I_cav, g * e.dag())

            # projectors |g,n>, |e,n| — when Nc==1, only n=0 exists
            self.proj = {"g": {}, "e": {}}
            if Nc == 1:
                Pn_c = qt.Qobj(np.array([[1.0]]), dims=[[1],[1]])
                self.proj["g"][0] = qt.tensor(Pn_c, Pg_qubit)
                self.proj["e"][0] = qt.tensor(Pn_c, Pe_qubit)
                self.proj["g"]["0"] = self.proj["g"][0]
                self.proj["e"]["0"] = self.proj["e"][0]
            else:
                for n in range(Nc):
                    Pn_c = qt.basis(Nc, n) * qt.basis(Nc, n).dag()
                    self.proj["g"][n]      = qt.tensor(Pn_c, Pg_qubit)
                    self.proj["e"][n]      = qt.tensor(Pn_c, Pe_qubit)
                    self.proj["g"][str(n)] = self.proj["g"][n]
                    self.proj["e"][str(n)] = self.proj["e"][n]
        else:
            # degenerate qubit (Nq==1): build zeros on full space with explicit dims
            Z = qt.Qobj(np.zeros((Nc*Nq, Nc*Nq)), dims=[[Nc, Nq], [Nc, Nq]])
            self.Pg = self.Pe = self.sx = self.sy = self.sz = Z
            self.sigma_plus = self.sigma_minus = Z

        self.c_ops = self.construct_collapse_operators()

    def add_drive(self,
                name: str = None,
                operator: str = "qubit",      # legacy kw; alias for channel
                channel: str = None,          # "qubit" or "cavity"
                carrier_freq: float = 0.0,
                amplitude: float = 0.0,
                envelope_type: Union[str, Callable] = "constant",
                envelope_params: Optional[dict] = None,
                encoding: str = "cos"):       # "cos" or "iq"
        """
        Add a single drive. For IQ-style complex envelopes, use encoding="iq".
        """
        ch = (channel or operator)
        assert ch in ("qubit", "cavity"), "channel must be 'qubit' or 'cavity'"
        ep = {} if envelope_params is None else dict(envelope_params)
        self.drives.append({
            "name": name or f"{ch}_drive_{len(self.drives)}",
            "channel": ch,
            "carrier_freq": float(carrier_freq),
            "amplitude": amplitude,
            "envelope_type": envelope_type,   # "constant"/"gaussian"/callable
            "envelope_params": ep,            # may include t_start, duration, sigma, ramps...
            "encoding": encoding              # "cos" (4-term) or "iq" (2-term)
        })

    def clear_drives(self): self.drives.clear()

    def _drive_envelope(self, t, drive_def, args):
        env_type  = drive_def["envelope_type"]
        amplitude = drive_def["amplitude"]
        p         = drive_def.get("envelope_params", {}) or {}

        # ----- gating window (robust defaults) -----
        t0  = p.get("t_start", -np.inf)
        dur = p.get("duration",  np.inf)
        # If no finite window specified, pass-through
        pass_through = (np.isinf(t0) and np.isinf(dur))
        t1 = (t0 + dur) if not pass_through else np.inf

        # ramps
        t_rise = p.get("t_rise", 0.0)
        t_rise = 0.0 if t_rise is None else float(t_rise)
        _tfall = p.get("t_fall", None)
        t_fall = float(_tfall) if (_tfall is not None) else t_rise
        t_rise = max(0.0, t_rise)
        t_fall = max(0.0, t_fall)

        def window(t):
            if pass_through:
                return 1.0
            if not (t0 <= t <= t1):
                return 0.0
            # cosine ramps (C1)
            if t_rise > 0.0 and t < t0 + t_rise:
                x = (t - t0)/t_rise
                return 0.5*(1 - np.cos(np.pi*x))
            if t_fall > 0.0 and t > t1 - t_fall:
                x = (t1 - t)/t_fall
                return 0.5*(1 - np.cos(np.pi*x))
            return 1.0

        # ----- base shapes -----
        if callable(env_type):
            base = amplitude * env_type(t, args or {})
        elif env_type == "constant":
            base = amplitude
        elif env_type == "gaussian":
            tcen  = p.get("t0", (t0 + 0.5*dur) if not pass_through else t)
            sigma = float(p.get("sigma", max(1e-12, 0.25*(dur if np.isfinite(dur) else 1.0))))
            base  = amplitude * np.exp(- (t - tcen)**2 / (2 * sigma**2))
        else:
            raise ValueError("Invalid envelope_type; use 'constant', 'gaussian', or callable.")

        return base * window(t)


    def show_drive(self, tlist, mode="env", args=None, ax=None, legend=True, figsize=(8,4)):
        import matplotlib.pyplot as plt
        args = args or {}
        created_ax = ax is None
        if created_ax:
            fig, ax = plt.subplots(figsize=figsize)
        if not self.drives:
            ax.text(0.5,0.5,"No drives registered",ha="center",va="center")
            if created_ax: plt.tight_layout(); plt.show()
            return ax

        for d in self.drives:
            name = d.get("name","drive")
            ch   = d.get("channel","?")
            ω    = float(d.get("carrier_freq",0.0))
            A    = np.array([self._drive_envelope(t, d, args) for t in tlist], dtype=complex)

            label = f"{name} [{ch}] @ ω/2π={ω/2/np.pi/1e9:.3f} GHz"
            m = mode.lower()
            if m == "env":
                if np.any(np.abs(A.imag) > 0): 
                    ax.plot(tlist*1e9, A.real, label=label+" (I)")
                    ax.plot(tlist*1e9, A.imag, "--", label=label+" (Q)")
                else:
                    ax.plot(tlist*1e9, A.real, label=label+" (env)")
                ax.set_ylabel("Envelope A(t) [rad/s]")
            elif m == "iq":
                ax.plot(tlist*1e9, A.real, label=label+" (I)")
                ax.plot(tlist*1e9, A.imag, "--", label=label+" (Q)")
                ax.set_ylabel("Baseband A(t) [rad/s]")
            elif m == "lab":
                y = np.real(A * np.exp(-1j*ω*tlist))
                ax.plot(tlist*1e9, y, label=label+" (lab)")
                ax.set_ylabel("Drive coeff. [rad/s]")
            else:
                raise ValueError("mode ∈ {'env','lab','iq'}")

        ax.set_xlabel("time [ns]")
        ax.grid(True, alpha=0.25)

        if legend:
            ax.legend(fontsize=9, bbox_to_anchor=(1.05, 0.5), loc="center left", borderaxespad=0.)

        if created_ax:
            plt.tight_layout()
            plt.show()

        return ax


    def _collect_terms(self, frame_spec: Optional[str] = None) -> List[Term]:
        terms: List[Term] = []
        for d in self.drives:
            if self.Nc == 1 and d.get("channel") == "cavity" and abs(d.get("amplitude",0)) > 0:
                raise ValueError("Nc=1 (no cavity). Remove cavity drives.")
            ch   = d.get("channel", "qubit")
            enc  = d.get("encoding", "cos")
            wcar = float(d.get("carrier_freq", 0.0))

            # operator selection (supports explicit operator for diag_n)
            if "explicit_op" in d:
                op = d["explicit_op"]
            elif ch == "cavity":
                op = self.a
            elif ch == "qubit":
                op = self.b
            elif ch.startswith("diag_n:"):
                n = int(ch.split(":")[1])
                if not (0 <= n < self.Nc):
                    raise ValueError(f"diag_n:{n} out of range for Nc={self.Nc}")
                Pn_c = qt.basis(self.Nc, n) * qt.basis(self.Nc, n).dag()
                op = qt.tensor(Pn_c, qt.qeye(self.Nq))
            else:
                raise ValueError(f"Unknown channel '{ch}'")

            if enc == "cos":
                def env(t, args, dd=d): return 0.5 * self._drive_envelope(t, dd, args)
                terms += [
                    Term(op=op,       omega=+wcar, envelope=env, label=f"{d['name']} a+"),
                    Term(op=op,       omega=-wcar, envelope=env, label=f"{d['name']} a-"),
                    Term(op=op.dag(), omega=+wcar, envelope=env, label=f"{d['name']} a†+"),
                    Term(op=op.dag(), omega=-wcar, envelope=env, label=f"{d['name']} a†-"),
                ]

            elif enc == "iq":
                w = wcar
                def A(t, args, dd=d): return self._drive_envelope(t, dd, args)
                def Aconj(t, args, dd=d): return np.conj(A(t, args, dd))

                if op.isherm:
                    # Hermitian operator: split into two half-terms so H = Re[A e^{-iwt}] op
                    def env_minus(t, args, dd=d): return 0.5 * A(t, args, dd)     # with omega = -w
                    def env_plus (t, args, dd=d): return 0.5 * Aconj(t, args, dd)  # with omega = +w
                    terms += [
                        Term(op=op, omega=-w, envelope=env_minus, label=f"{d['name']}(IQ) herm-"),
                        Term(op=op, omega=+w, envelope=env_plus,  label=f"{d['name']}(IQ) herm+"),
                    ]
                else:
                    # Ladder operator: A b e^{-iwt} + A* b† e^{+iwt}
                    def env_lower(t, args, dd=d): return A(t, args, dd)       # op, omega = -w
                    def env_raise(t, args, dd=d):  return Aconj(t, args, dd)  # op†, omega = +w
                    terms += [
                        Term(op=op,       omega=-w, envelope=env_lower, label=f"{d['name']}(IQ)+"),
                        Term(op=op.dag(), omega=+w, envelope=env_raise, label=f"{d['name']}(IQ)-"),
                    ]
            else:
                raise ValueError("encoding must be 'cos' or 'iq'")
        return terms

    def H_static_lab(self):
        """
        H_static in LAB basis:
          ωc a†a + ωq b†b + (α/2) b†2 b2 + χ (a†a)(b†b) + (K/2) a†2 a2.
        α and K are Kerr (self-nonlinearities), χ is cross-Kerr (dispersive coupling).
        """
        return self.H_cavity + self.H_qubit + self.H_anharm + self.H_chi + self.H_kerr

    def H_frame_lab(self, which="cavity_qubit"):
        """
        Choose a generator F for the rotating frame (all in LAB basis).
        Common choices:
          - "cavity":    F = ωc a†a               (makes cavity-resonant drive slow)
          - "qubit":     F = ωq b†b               (makes qubit-resonant drive slow)
          - "both_diag": F = ωc a†a + ωq b†b + diagonal Kerr terms
          - "full_diag": F = H_static itself      (if H_static is diagonal in the chosen basis)
          - Qobj:        supply any Hermitian operator directly
        """
        nc = self.adag * self.a
        nq = self.bdag * self.b
        if which == "cavity":
            return self.wc * nc
        elif which == "qubit":
            return self.wq * nq
        elif which == "cavity_qubit":
            return (self.wc * nc + self.wq * nq)
        elif which == "full":
            # if H_static is diagonal in your basis, this equals H_static
            return self.H_static_lab()
        elif isinstance(which, qt.Qobj):
            return which
        else:
            raise ValueError(f"Unknown frame spec: {which}")
            
    def construct_hamiltonian(self, frame: Union[str, qt.Qobj, None] = "cavity_qubit",
                            use_RWA=False, rwa_cutoff=100e6*2*np.pi,
                            rotate_static_offdiag=False, args=None):
        Hs = self.H_static_lab()

        if frame is None:
            F = None
            frame_spec = None
        elif isinstance(frame, str):
            F = self.H_frame_lab(frame)
            frame_spec = frame  # "cavity", "qubit", "cavity_qubit", ...
        else:
            F = frame
            frame_spec = "custom"

        terms = self._collect_terms(frame_spec) 
        return build_rotated_hamiltonian(H_static_lab=Hs, terms_lab=terms,
                                        H_frame_lab=F, use_rwa=use_RWA,
                                        rwa_cutoff=rwa_cutoff, args=args,
                                        rotate_static_offdiag=rotate_static_offdiag)

    
    def construct_collapse_operators(self):
        """
        Return Lindblad jump operators:
          • sqrt(κ) a          : cavity photon loss
          • sqrt(Γ1) b         : qubit relaxation |e>→|g|
          • sqrt(2Γφ) n_q      : pure dephasing; this choice makes ρ_ge decay at Γφ.
        """
        collapse_ops = []
        if self.kappa > 0:
            collapse_ops.append(np.sqrt(self.kappa) * self.a)
        if self.Γ_1 > 0:
            collapse_ops.append(np.sqrt(self.Γ_1) * self.b)
        if self.Γ_ϕ > 0:
            # use L = sqrt(2 Γ_ϕ) * n so that ρ_ge decays at Γ_ϕ
            n_q = (self.bdag * self.b)
            collapse_ops.append(np.sqrt(2.0 * self.Γ_ϕ) * n_q)
        return collapse_ops

    def initial_state(self):
        """Cavity vacuum ⊗ qubit ground."""
        psi_cavity = qt.basis(self.Nc, 0)
        psi_qubit = qt.basis(self.Nq, 0)
        return qt.tensor(psi_cavity, psi_qubit)
    
    def initial_state_excited(self):
        """Cavity vacuum ⊗ qubit excited."""
        psi_cavity = qt.basis(self.Nc, 0)
        psi_qubit = qt.basis(self.Nq, 1)
        return qt.tensor(psi_cavity, psi_qubit)


###-----------------------------------------------------------
    def U_displacement(self, alpha: complex) -> qt.Qobj:
        """
        Ideal displacement on the cavity, identity on the qubit.
        """
        Uc = qt.displace(self.Nc, alpha)
        return qt.tensor(Uc, qt.qeye(self.Nq))

    def U_snap(self, thetas: Sequence[float]) -> qt.Qobj:
        """
        Ideal SNAP: diag(e^{i theta_n}) on the cavity number basis, identity on qubit.
        thetas may be shorter than Nc; we pad with zeros.
        """
        thetas = np.asarray(list(thetas), dtype=float)
        if thetas.size < self.Nc:
            thetas = np.pad(thetas, (0, self.Nc - thetas.size), constant_values=0.0)
        phases = np.exp(1j * thetas[:self.Nc])
        Uc = qt.Qobj(np.diag(phases), dims=[[self.Nc], [self.Nc]])
        return qt.tensor(Uc, qt.qeye(self.Nq))

    def apply_ideal_sequence(self, sequence: List[dict], psi0: Optional[qt.Qobj] = None):
        """
        Apply a sequence of ideal ops to psi0 (ket). Each item in `sequence` is a dict like
        {'op': 'D', 'alpha': 0.8+0.3j} or {'op': 'SNAP', 'thetas': [0, 0.5, ...]}.
        Returns (psi_final, U_total).
        """
        if psi0 is None:
            psi0 = self.initial_state()
        I_full = qt.tensor(qt.qeye(self.Nc), qt.qeye(self.Nq))
        U = I_full
        for step in sequence:
            op = step.get('op', '').upper()
            if op == 'D':
                U_step = self.U_displacement(step['alpha'])
            elif op == 'SNAP':
                U_step = self.U_snap(step['thetas'])
            else:
                raise ValueError(f"Unknown op '{op}'. Use 'D' or 'SNAP'.")
            U = U_step * U  # left-multiply so sequence order is natural
        psi_f = U * psi0

        rho_cav = self.cavity_reduced(psi_f)             # ideal cavity state (dm)
        P_n = np.real(np.diag(rho_cav.full())) 
        return psi_f, U, P_n

    def cavity_reduced(self, state: qt.Qobj) -> qt.Qobj:
        """
        Partial trace to the cavity. Accepts ket or density matrix.
        """
        rho = state if state.isoper else qt.ket2dm(state)
        return rho.ptrace(0)  # 0 = first subsystem (cavity)