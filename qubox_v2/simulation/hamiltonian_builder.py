# hamiltonian_builder.py

import qutip as qt
from typing import Callable, Dict, List, Optional, Union
from dataclasses import dataclass, field
import numpy as np
import scipy.sparse as sp

@dataclass
class Term:
    op: qt.Qobj                            
    omega: float                            
    envelope: Callable[[float, dict], complex]  
    charges: Dict[str, int] = field(default_factory=dict)
    label: str = ""

# -----------------------------------------------------------------------------
# Term: one time-dependent piece A(t) * e^(âˆ’i Ï‰ t) * op
# -----------------------------------------------------------------------------

def _iter_nz(Q, tol=1e-12):
    """
    Yield (i, j, value) for all entries with |value| > tol.
    This is used to decompose operators into rank-1 pieces |i><j|.
    """
    data = Q.data
    if hasattr(data, "tocoo"):
        coo = data.tocoo()
        for i, j, v in zip(coo.row, coo.col, coo.data):
            if abs(v) > tol:
                yield i, j, v
    else:
        M = Q.full()
        rows, cols = np.nonzero(np.abs(M) > tol)
        for i, j in zip(rows, cols):
            yield i, j, M[i, j]

# -----------------------------------------------------------------------------
# Build H'(t) in LAB basis corresponding to rotation by U=exp(âˆ’i F t)
# -----------------------------------------------------------------------------

def build_rotated_hamiltonian(
    H_static_lab: qt.Qobj,
    terms_lab: List[Term],
    H_frame_lab: Optional[qt.Qobj] = None,
    use_rwa: bool = False,
    rwa_cutoff: Optional[float] = None,   # e.g., 2*np.pi*50e6
    args: Optional[dict] = None,
    rotate_static_offdiag: bool = False,  # handle [H_static, F] â‰  0
) -> Union[qt.Qobj, list]:
    """
    Return a QuTiP time-dependent Hamiltonian (list format) in the LAB basis
    that implements the exact frame transform H'(t) = Uâ€ (t) H(t) U(t) âˆ’ F.

    â€¢ If H_frame_lab is None: no rotation, i.e., H(t) = H_static_lab + Î£ terms.
    â€¢ If rotate_static_offdiag=False and [H_static, F]=0 (e.g., diagonal case),
      then the static base is simply H_static_lab âˆ’ H_frame_lab and time-independent.
    â€¢ If rotate_static_offdiag=True, we decompose H_static in the frame basis and
      add off-diagonal elements as oscillating terms (to avoid double-counting).
    â€¢ Driven terms are also transformed element-wise; RWA can drop fast pieces.
    """
    if args is None:
        args = {}

    # 0) No frame: simple case
    if H_frame_lab is None:
        if not terms_lab:
            return H_static_lab
        H = [H_static_lab]
        for term in terms_lab:
            def f(t, args=None, te=term):
                return te.envelope(t, args or {}) * np.exp(-1j * te.omega * t)
            H.append([term.op, f])
        return H

    if not H_frame_lab.isherm:
        raise ValueError("H_frame_lab must be Hermitian.")

    # 1) Diagonalize the frame: F = V D Vâ€ 
    evals, evecs = H_frame_lab.eigenstates()
    d = np.array([ev for ev in evals], dtype=float)  # (N,)
    # Build unitary V with columns = eigenvectors |i>
    V = qt.Qobj(np.column_stack([v.full() for v in evecs]), dims=H_frame_lab.dims)

    # Helper: transform labâ†”frame basis
    def to_frame(op_lab: qt.Qobj) -> qt.Qobj:
        return V.dag() * op_lab * V
    def to_lab(op_frame: qt.Qobj) -> qt.Qobj:
        return V * op_frame * V.dag()

    # 2) Static part: H'0 = Uâ€  H_static U - F
    #    If [H_static, F]=0, this is simply H_static_lab - H_frame_lab (time-independent).
    #    Otherwise, you can either (a) accept time dependence (rotate_static_offdiag=True),
    #    or (b) assume commuting and keep the simple subtraction.
    if rotate_static_offdiag:
        H0_frame = to_frame(H_static_lab)

        # keep ONLY diagonal of H_static in frame as static:
        H0_frame_full = H0_frame.full()
        diag_vals = np.diag(H0_frame_full)
        Hdiag_frame = qt.Qobj(np.diag(diag_vals), dims=H0_frame.dims)
        H_static_diag_lab = to_lab(Hdiag_frame)
        H = [H_static_diag_lab - H_frame_lab]   # base static part

        # add OFF-diagonal pieces as time-dependent:
        for i, j, val in _iter_nz(H0_frame):
            if i == j:
                continue
            Delta = d[i] - d[j]
            Eij_frame = qt.Qobj(sp.csr_matrix(([val], ([i], [j])), shape=H0_frame.shape),
                                dims=H0_frame.dims)
            Eij_lab = to_lab(Eij_frame)
            def f_static(t, args=None, we=-Delta):
                return np.exp(-1j * we * t)
            H.append([Eij_lab, f_static])
    else:
        H = [H_static_lab - H_frame_lab]

    # 3) Sub-terms: rotate exactly and (optionally) apply an RWA filter
    for term in terms_lab:
        O_frame = to_frame(term.op)
        for i, j, val in _iter_nz(O_frame):             # <-- CHANGED
            Delta = d[i] - d[j]
            omega_eff = term.omega - Delta
            if use_rwa and (rwa_cutoff is not None) and (abs(omega_eff) > rwa_cutoff):
                continue  # drop fast piece

            # |i><j| piece scaled by the matrix element, mapped back to LAB
            Eij_frame = qt.Qobj(
                sp.csr_matrix(([val], ([i], [j])), shape=O_frame.shape),
                dims=O_frame.dims
            )
            Eij_lab = to_lab(Eij_frame)

            # bind term & omega_eff to avoid late binding
            def f_term(t, args=None, te=term, we=omega_eff):
                return te.envelope(t, args or {}) * np.exp(-1j * we * t)
            H.append([Eij_lab, f_term])

    return H
