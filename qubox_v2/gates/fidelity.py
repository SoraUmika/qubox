import numpy as np
from qubox_v2.gates.liouville import unitary_to_superop  # adjust import path if needed

def entanglement_fidelity_from_superop(S: np.ndarray, d: int) -> float:
    """
    Compute entanglement fidelity Fe of channel with Liouville superop S
    (column-stacking convention), using Choi J(E) in the *unnormalized*
    convention based on |Î©> = sum_i |i,i>.

    Fe = ( <Î©| J(E) |Î©> ) / d^2
    """
    S = np.asarray(S, dtype=np.complex128)

    # Reshuffle superop -> Choi:
    # J_{i,k; j,l} = S_{i,j; k,l}   (for column-stacking convention)
    J = S.reshape(d, d, d, d).transpose(0, 2, 1, 3).reshape(d * d, d * d)

    # |Î©> = vec(I) (unnormalized)
    omega = np.zeros((d * d,), dtype=np.complex128)
    for i in range(d):
        omega[i * d + i] = 1.0

    Fe = np.vdot(omega, J @ omega) / (d * d)
    Fe = float(np.real_if_close(Fe))

    # numerical guard (should already be in [0,1] for CPTP maps)
    if Fe < -1e-12 or Fe > 1 + 1e-12:
        # don't hard fail; clip for stability
        Fe = float(np.clip(Fe, 0.0, 1.0))
    else:
        Fe = float(np.clip(Fe, 0.0, 1.0))
    return Fe


def avg_gate_fidelity_superop(S_impl: np.ndarray, U_target: np.ndarray) -> float:
    """
    Average gate fidelity between a channel (superop S_impl) and target unitary U_target.

    We compute E' = U_target^\dagger âˆ˜ E, then:
      Favg = (d * Fe(E') + 1) / (d + 1)
    """
    U_target = np.asarray(U_target, dtype=np.complex128)
    d = U_target.shape[0]

    S_t = unitary_to_superop(U_target)
    # Pull back by target: E' = Uâ€  âˆ˜ E
    S_pull = S_t.conj().T @ np.asarray(S_impl, dtype=np.complex128)

    Fe = entanglement_fidelity_from_superop(S_pull, d)
    Favg = (d * Fe + 1.0) / (d + 1.0)
    Favg = float(np.real_if_close(Favg))
    return float(np.clip(Favg, 0.0, 1.0))

